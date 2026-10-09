"""Vakanın ön hazırlığı: `python -m rpt.hazirla`.

Bir adım, bir dosya:

    gunluk   cikti/gunluk.parquet   2023-01-01 .. 2025-12-31 mağaza + online günlük
                                    tablosu (`perakende_analitik.hazirlik.gunluk_yaz`;
                                    durum: stoklu / tukenen / bos). Yok-satma ve
                                    blok-transfer'le aynı tanım. ~6–10 dk, bir kez.

Sonraki bütün görevler (eğri, karar anı katmanları, aday etiketleri, kalibrasyon)
bu dosyayı okur. Okuyucular:

    gunluk_yolu(cikti, con)     dosyanın yolu; yoksa ya da başka bir v4 dosyasından
                                kurulmuşsa koşulacak komutu söyleyen RuntimeError
    havuz_gunlugu(yol, con, havuz, t)
                                karar havuzunun (`sansur.karar_ani_talep`) satırları,
                                yalnız `tarih < t`, Basit'in özellik sütunlarıyla
                                (`ozellikler.ekle`, yayımlanan tablolardan)
    carpanlar(con, yol, t)      karar anı çarpanları (`hazirlik.carpanlar_kapanmis`),
                                kapanmış sezon kümesi başına diskte önbellekli

Önbellek: `kaynak.json` çıktının hangi v4 dosyasından ve hangi pencereyle
kurulduğunu tutar (mutlak yol, boyut, mtime); biri değişince dizindeki günlük
ve çarpan dosyaları silinir, baştan kurulur. Çarpan dosyası adı kapanmış sezon
kümesini taşır (`carpanlar_SS23-AW23.pkl`): çarpanlar yalnız o kümeyle değişir
(`hazirlik.carpanlar_kapanmis`), bu yüzden sonraki bir karar anında kurulan
dosya önceki bir anın kümesine karışmaz.

Bu modül politikaya girmez (motorun `KOSU_DISI`'ndadır): ürettiği tablodan
öğrenilen her şey (eğri, model) politikaya `parametreler` üstünden verilir.
Gizli gerçeğe (`hakem`, `perakende_veri`, `rpt.motor`) dokunmaz.
"""

import argparse
import json
import pickle
import time
from datetime import date
from pathlib import Path

import pandas as pd
from perakende_analitik import hazirlik, ozellikler
from perakende_analitik import kaynak as ortak

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))     # yok-satma, blok-transfer ile aynı
VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"
GUNLUK = "gunluk.parquet"
KAYNAK = "kaynak.json"
KOMUT = "cd vakalar/rpt && .venv/Scripts/python -m rpt.hazirla"

# Basit'in okuduğu özellik sütunları (ortak paketle aynı liste)
BASIT_OZELLIKLERI = list(hazirlik.KESTIRICI_OZELLIKLERI["basit"])
GUNLUK_SUTUNLARI = list(hazirlik.GUNLUK_SUTUNLARI)


def _parmak_izi(db: Path) -> dict:
    bilgi = Path(db).stat()
    return {"yol": str(Path(db).resolve()), "boyut": bilgi.st_size, "mtime_ns": bilgi.st_mtime_ns}


def _iz(db: Path) -> dict:
    return {"db": _parmak_izi(db), "pencere": [PENCERE[0].isoformat(), PENCERE[1].isoformat()]}


def _baglanti_dosyasi(con) -> Path | None:
    satirlar = con.execute(
        "select path from duckdb_databases() where not internal and path is not null").fetchall()
    return Path(satirlar[0][0]) if satirlar else None


def gunluk_yolu(cikti: Path = VARSAYILAN_CIKTI, con=None) -> Path:
    """`gunluk.parquet`in yolu. Dosya ya da `kaynak.json` yoksa, ya da `con`un
    dosyası kayıttakinden farklıysa (yol, boyut, mtime) `RuntimeError`."""
    cikti = Path(cikti)
    yol, iz_yolu = cikti / GUNLUK, cikti / KAYNAK
    if not yol.exists() or not iz_yolu.exists():
        raise RuntimeError(f"{yol} yok. Önce koşun: {KOMUT}")
    kayitli = json.loads(iz_yolu.read_text(encoding="utf-8"))
    if kayitli.get("pencere") != _iz_pencere():
        raise RuntimeError(f"{yol} başka bir pencereyle kurulmuş. Koşun: {KOMUT} --yeniden")
    db = _baglanti_dosyasi(con) if con is not None else None
    if db is not None and kayitli.get("db") != _parmak_izi(db):
        raise RuntimeError(f"{yol} başka bir v4 dosyasından kurulmuş ({kayitli.get('db')}); "
                           f"şimdiki {db}. Koşun: {KOMUT}")
    return yol


def _iz_pencere() -> list[str]:
    return [PENCERE[0].isoformat(), PENCERE[1].isoformat()]


def havuz_gunlugu(yol: Path, con, havuz: pd.DataFrame, t) -> pd.DataFrame:
    """Karar havuzunun günlük satırları: `havuz.option_id`'deki option'lar,
    `min(havuz.bas) <= tarih < t`, Basit'in özellik sütunlarıyla.

    Pencere kesimi (option başına `bas`, `son`) `sansur.karar_ani_talep`in
    işidir; burada yalnız okunacak satırlar daraltılır (bellek). `t` dahil
    değil: karar anı ve sonrası okunmaz bile."""
    t = pd.Timestamp(t).normalize()
    opsiyonlar = sorted(map(str, pd.unique(havuz["option_id"])))
    bas = pd.Timestamp(pd.to_datetime(havuz["bas"]).min())
    filtre = [("option_id", "in", opsiyonlar), ("tarih", ">=", bas), ("tarih", "<", t)]
    df = pd.read_parquet(yol, columns=GUNLUK_SUTUNLARI, filters=filtre).reset_index(drop=True)
    return ozellikler.ekle(con, df, BASIT_OZELLIKLERI)


def carpanlar(con, yol: Path, t, cikti: Path | None = None):
    """Karar anı çarpanları (`hazirlik.carpanlar_kapanmis(con, yol, t)`).

    `cikti` verilirse (varsayılan: günlük dosyasının dizini) kapanmış sezon
    kümesi başına `carpanlar_<küme>.pkl` olarak saklanır ve yeniden kullanılır;
    günlük dosyası yeniden kurulunca `main` bu dosyaları siler."""
    yol = Path(yol)
    cikti = yol.parent if cikti is None else Path(cikti)
    kume = hazirlik.kapanmis_sezonlar(con, yol, pd.Timestamp(t).date())["sezon_kodu"].tolist()
    if not kume:
        raise ValueError(f"carpanlar: {pd.Timestamp(t).date()} tarihinde kapanmış sezon yok")
    dosya = cikti / f"carpanlar_{'-'.join(kume)}.pkl"
    if dosya.exists() and dosya.stat().st_mtime_ns >= yol.stat().st_mtime_ns:
        with open(dosya, "rb") as f:
            return pickle.load(f)
    c = hazirlik.carpanlar_kapanmis(con, yol, pd.Timestamp(t).date())
    gecici = dosya.with_suffix(".pkl.yaziliyor")
    with open(gecici, "wb") as f:
        pickle.dump(c, f)
    gecici.replace(dosya)
    return c


def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m rpt.hazirla", description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    p.add_argument("--db", type=Path, default=ortak.VARSAYILAN_YOL)
    p.add_argument("--yeniden", action="store_true", help="var olan günlük tabloyu yeniden kur")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> dict:
    a = _ayristir(argv)
    cikti: Path = a.cikti
    cikti.mkdir(parents=True, exist_ok=True)
    yol, iz_yolu = cikti / GUNLUK, cikti / KAYNAK
    iz = _iz(a.db)
    eski = json.loads(iz_yolu.read_text(encoding="utf-8")) if iz_yolu.exists() else None
    if eski != iz or a.yeniden:
        for dosya in [yol, *cikti.glob("carpanlar_*.pkl")]:
            if dosya.exists():
                print(f"siliniyor: {dosya}", flush=True)
                dosya.unlink()
        iz_yolu.unlink(missing_ok=True)
    sonuc = {}
    if yol.exists():
        print(f"gunluk: var, atlandi ({yol})", flush=True)
    else:
        con = ortak.baglan(a.db)
        try:
            print("gunluk: basliyor", flush=True)
            t0 = time.perf_counter()
            n = hazirlik.gunluk_yaz(con, yol, PENCERE)
            sonuc = {"satir": n, "saniye": round(time.perf_counter() - t0, 1)}
        finally:
            con.close()
        iz_yolu.write_text(json.dumps(iz, ensure_ascii=False, indent=2), encoding="utf-8")
        (cikti / "hazirla_sure.json").write_text(json.dumps(sonuc, indent=2), encoding="utf-8")
        print(f"gunluk: {sonuc}", flush=True)
    return sonuc


if __name__ == "__main__":
    main()
