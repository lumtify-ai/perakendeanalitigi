"""Vakanın ön hazırlığı: `python -m blok_transfer.hazirla`.

Ölçüm penceresinde (`[karar, karar + 7·olcum_hafta gün)`) Basit kestiricinin kaybını
üretir. Üç adım, her biri kendi dosyasına yazılır:

    gunluk      gunluk.parquet       2023-01-01 .. 2025-12-31 günlük tablo
                                     (`perakende_analitik.hazirlik.gunluk_yaz`)
    carpanlar   carpanlar.pkl        çarpanlar, yalnız 2023–2024'ün stoklu günleriyle
    basit       kayip_basit.parquet  Basit: `egit` bütün pencerenin stoklu günleriyle
                                     (yok-satma ile aynı havuz), `tahmin` ve kayıp
                                     yalnız ölçüm penceresindeki `bos`/`tukenen`
                                     satırlarına; kaynak ağacı yok (`agacli=False`)

Havuz ve çarpan girdileri yok-satma vakasıyla aynıdır; bu yüzden pencere içindeki
`kayip` değerleri yok-satma'nın `kayip_basit.parquet`'indekiyle satır satır aynıdır.

Önbellek: dosyası olan adım atlanır; bir adım koşarsa ondan sonrakiler de koşar
(`--yeniden` hepsini). `kaynak.json` çıktının hangi v4 dosyasından, hangi karar
anı ve ölçüm haftasıyla kurulduğunu tutar; bunlardan biri değiştiyse dizindeki
bütün çıktılar silinir ve baştan kurulur. `oku_kayip` aynı denetimi okurken yapar:
bayat çıktı sessizce yanlış sayı vermez, hangi komutun koşulacağını söyleyen
`RuntimeError` verir.

`sure.json`: adım başına saniye (`perf_counter`) ve ortak adımın döndürdüğü özet.
Tepe bellek tutulmaz (psutil bu vakanın bağımlılığı değil).
"""

import argparse
import gc
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from perakende_analitik import kaynak
from perakende_analitik.hazirlik import carpanlar_yaz, gunluk_yaz, kayip_yaz

from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cekirdek.veri import karar_ani

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))      # yok-satma ile aynı
OGRENME_BITIS = date(2024, 12, 31)                    # çarpanlar 2023–2024'ten öğrenir
KESTIRICI = "basit"

VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"

ADIMLAR = ("gunluk", "carpanlar", "basit")            # bağımlılık sırasıyla (her biri öncekilere bağlı)
DOSYALAR = {"gunluk": "gunluk.parquet", "carpanlar": "carpanlar.pkl",
            "basit": "kayip_basit.parquet"}
KOMUT = "cd vakalar/blok-transfer && .venv/Scripts/python -m blok_transfer.hazirla"


def pencere(karar: date, hafta: int) -> tuple[date, date]:
    """Ölçüm penceresi `[karar, karar + 7·hafta gün)`; ikinci uç dahil değil.
    Ölçüm (Görev 7) ve bu adım aynı tanımı kullanır."""
    return karar, karar + timedelta(days=7 * hafta)


def _parmak_izi(db: Path) -> dict:
    """v4 dosyasının kimliği: mutlak yol, boyut, mtime (ns)."""
    bilgi = db.stat()
    return {"yol": str(db.resolve()), "boyut": bilgi.st_size, "mtime_ns": bilgi.st_mtime_ns}


def _kaynak(db: Path, karar: date, olcum_hafta: int) -> dict:
    return {"db": _parmak_izi(db), "karar": karar.isoformat(), "olcum_hafta": olcum_hafta}


def _baglanti_dosyasi(con) -> Path | None:
    """Bağlantının açtığı DuckDB dosyası; bellek içi bağlantıda `None`."""
    satirlar = con.execute(
        "select path from duckdb_databases() where not internal and path is not null").fetchall()
    return Path(satirlar[0][0]) if satirlar else None


def oku_kayip(cikti: Path, con, karar: date, olcum_hafta: int) -> pd.DataFrame:
    """`kayip_basit` satırları (ölçüm penceresindeki `bos`/`tukenen` günleri).

    Çıktı yoksa ya da başka bir karar anı, ölçüm haftası ya da v4 dosyası için
    kurulmuşsa (`kaynak.json`) `RuntimeError`; mesaj koşulacak komutu söyler.
    `con` bellek içiyse (dosyası yoksa) v4 dosyası karşılaştırılamaz, yalnız karar
    ve hafta denetlenir."""
    cikti = Path(cikti)
    kaynak_yolu, kayip_yolu = cikti / "kaynak.json", cikti / DOSYALAR["basit"]
    if not kaynak_yolu.exists() or not kayip_yolu.exists():
        raise RuntimeError(f"{kayip_yolu} yok. Önce koşun: {KOMUT}")
    kayitli = json.loads(kaynak_yolu.read_text(encoding="utf-8"))
    beklenen = {"karar": karar.isoformat(), "olcum_hafta": olcum_hafta}
    if {k: kayitli.get(k) for k in beklenen} != beklenen:
        raise RuntimeError(
            f"{cikti} karar {kayitli.get('karar')}, ölçüm {kayitli.get('olcum_hafta')} hafta için "
            f"kurulmuş; istenen karar {beklenen['karar']}, {olcum_hafta} hafta. Koşun: {KOMUT}")
    db = _baglanti_dosyasi(con)
    if db is not None and kayitli.get("db") != _parmak_izi(db):
        raise RuntimeError(f"{cikti} başka bir v4 dosyasından kurulmuş ({kayitli.get('db')}); "
                           f"şimdiki {db}. Koşun: {KOMUT}")
    return pd.read_parquet(kayip_yolu)


def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m blok_transfer.hazirla",
                                description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI,
                   help=f"çıktı dizini (varsayılan {VARSAYILAN_CIKTI})")
    p.add_argument("--db", type=Path, default=kaynak.VARSAYILAN_YOL,
                   help=f"v4 DuckDB dosyası (varsayılan {kaynak.VARSAYILAN_YOL})")
    p.add_argument("--yeniden", action="store_true",
                   help="var olan çıktıları da yeniden hesapla")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> dict:
    a = _ayristir(argv)
    cikti: Path = a.cikti
    cikti.mkdir(parents=True, exist_ok=True)
    yol = {ad: cikti / dosya for ad, dosya in DOSYALAR.items()}
    sure_yolu = cikti / "sure.json"
    sure = json.loads(sure_yolu.read_text(encoding="utf-8")) if sure_yolu.exists() else {}
    sure.setdefault("adimlar", {})
    sure["olcum"] = "saniye: perf_counter; tepe bellek tutulmaz"

    def sure_yaz():
        sure_yolu.write_text(json.dumps(sure, ensure_ascii=False, indent=2), encoding="utf-8")

    olcum_hafta = Parametreler().olcum_hafta
    con = kaynak.baglan(a.db)           # dosya yoksa burada açık hata
    try:
        karar = karar_ani(con, olcum_hafta=olcum_hafta)
        hedef = pencere(karar, olcum_hafta)
        # başka bir v4 dosyasından, karardan ya da ölçüm haftasından kurulmuş çıktılar geçersiz
        kaynak_yolu = cikti / "kaynak.json"
        iz = _kaynak(Path(a.db), karar, olcum_hafta)
        eski = json.loads(kaynak_yolu.read_text(encoding="utf-8")) if kaynak_yolu.exists() else None
        if eski != iz:
            for adim in ADIMLAR:
                if yol[adim].exists():
                    print(f"{adim}: gecersiz, siliniyor ({yol[adim]})", flush=True)
                    yol[adim].unlink()
                sure["adimlar"].pop(adim, None)
            kaynak_yolu.write_text(json.dumps(iz, ensure_ascii=False, indent=2), encoding="utf-8")

        ustte_kosan = False
        for adim in ADIMLAR:
            if yol[adim].exists() and not a.yeniden and not ustte_kosan:
                print(f"{adim}: var, atlandi ({yol[adim]})", flush=True)
                continue
            print(f"{adim}: basliyor", flush=True)
            t0 = time.perf_counter()
            if adim == "gunluk":
                bilgi = {"satir": gunluk_yaz(con, yol["gunluk"], PENCERE)}
            elif adim == "carpanlar":
                bilgi = {"satir": carpanlar_yaz(con, yol["gunluk"], yol["carpanlar"], OGRENME_BITIS)}
            else:
                bilgi = kayip_yaz(con, KESTIRICI, yol["gunluk"], yol["carpanlar"], yol["basit"],
                                  hedef_araligi=hedef, agacli=False)
            saniye = time.perf_counter() - t0
            gc.collect()
            ustte_kosan = True
            sure["adimlar"][adim] = {"saniye": round(saniye, 1), **bilgi}
            sure_yaz()
            print(f"{adim}: {saniye:.1f} sn, {bilgi}", flush=True)
    finally:
        con.close()
    sure_yaz()
    return sure


if __name__ == "__main__":
    main()
