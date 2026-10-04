"""Vakanın bütün ara çıktılarını üretir: `python -m yok_satma.hazirla`.

Adımlar (her biri kendi dosyasına yazılır):

    gunluk      gunluk.parquet     `stok.gunluk_magaza` + `stok.gunluk_online`,
                                   2023-01-01 .. 2025-12-31, bütün uygun satırlar
                                   (stoklu dahil). Yıl yıl kurulur ve parquet'e
                                   satır grubu olarak eklenir: bütün pencere
                                   bellekte hiç birlikte durmaz.
    carpanlar   carpanlar.pkl      `carpanlar.ogren`, yalnız 2023–2024'ün stoklu
                                   günleriyle (+ gereken `ozellikler` sütunları)
    naif        kayip_naif.parquet  her kestirici için: `egit` bütün pencerenin
    basit       kayip_basit.parquet stoklu günleriyle, `tahmin` bütün pencerenin
    ml          kayip_ml.parquet    `bos` ve `tukenen` günleri; `kayip.kayip_yaz`
                                   yalnız bu satırlara (R5), sonra
                                   `agac.kaynak_ata`

Önbellek kuralları (bağımlılıklar: carpanlar, naif, ml <- gunluk;
basit <- gunluk + carpanlar):

    - Dosyası olan adım atlanır; `--yeniden` hepsini yeniden koşar, `--adim AD`
      (tekrarlanabilir) yalnız seçilenleri koşar ve onları zorla yeniden kurar.
    - Bu çağrıda koşan bir adımın bağımlıları da koşar (seçiliyse ya da seçim
      yoksa); `--adim` seçiminin dışında kalan bağımlıların dosyası SİLİNİR
      (geçersiz), bir sonraki çağrı onları yeniden kurar. Böylece eski
      girdiden kalan bir çıktı hiçbir zaman yeni bir girdinin yanında durmaz.
    - `kaynak.json` çıktının hangi v4 dosyasından kurulduğunu tutar (mutlak yol,
      boyut, mtime). `--db` farklıysa ya da `kaynak.json` yoksa dizindeki bütün
      çıktılar silinir.

Kayıp parquet'lerinin sütunları: günlük tablonun sütunları + `tahmini_talep`,
`satis`, `kayip`, `kayip_saf`, `kaynak`, `firsat`.

Bellek: her adım parquet'ten yalnız ihtiyaç duyduğu sütun ve satırları okur;
`ozellikler.ekle` yalnız kestiricinin okuduğu sütunları hesaplar; kestiriciler
arasında her şey bırakılır (`gc.collect`). Gizli gerçeğe (`hakem`) dokunulmaz.

`sure.json`: adım başına saniye ve tepe bellek. `tepe_gb` adımın süresince
0,1 sn'de bir örneklenen süreç RSS'inin (Windows'ta çalışma kümesi) en büyüğü;
`surec_tepe_gb` adım sonunda sürecin o ana kadarki tepe çalışma kümesi
(psutil `peak_wset`; Windows dışında örneklenen tepe). Atlanan adımın önceki
kaydı korunur.
"""

import argparse
import gc
import json
import pickle
import threading
import time
from datetime import date
from pathlib import Path

import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq

from perakende_analitik import agac, carpanlar, kayip, kaynak, ozellikler, stok, talep

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))
OGRENME_BITIS = pd.Timestamp("2024-12-31")       # çarpanlar 2023–2024'ten öğrenir
YILLAR = range(PENCERE[0].year, PENCERE[1].year + 1)

VARSAYILAN_CIKTI = Path(__file__).resolve().parents[1] / "cikti"
GUNLUK_SUTUNLARI = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi",
                    "brut_satis", "net_satis", "durum"]
# gözlem havuzundan okunan günlük sütunları (satis_oncesi ve net_satis hiçbir
# kestiricide okunmaz; durum yalniz_stoklu ve ML'in havuz üyeliği için)
_GOZLEM_SUTUNLARI = ["tarih", "magaza_id", "urun_id", "option_id", "brut_satis", "durum"]

ADIMLAR = ("gunluk", "carpanlar", "naif", "basit", "ml")      # bağımlılık sırasıyla
BAGIMLILIKLAR = {"gunluk": (), "carpanlar": ("gunluk",), "naif": ("gunluk",),
                 "basit": ("gunluk", "carpanlar"), "ml": ("gunluk",)}
DOSYALAR = {"gunluk": "gunluk.parquet", "carpanlar": "carpanlar.pkl",
            "naif": "kayip_naif.parquet", "basit": "kayip_basit.parquet",
            "ml": "kayip_ml.parquet"}

# `carpanlar.ogren` ve `carpanlar.karakter`in okuduğu özellik sütunları
CARPAN_OZELLIKLERI = ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici",
                      "markdown_orani", "kampanya_orani", "kampanya_id", "oran", "yas_gun",
                      "line", "ust_kategori", "alt_kategori", "kanal"]
# kestirici -> egit / tahmin'in okuduğu özellik sütunları
KESTIRICI_OZELLIKLERI = {
    "naif": ["line", "alt_kategori"],
    "basit": ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici", "oran", "yas_gun",
              "line", "ust_kategori", "alt_kategori", "kanal"],
    "ml": sorted(set(talep.ML_SAYISAL) | set(talep.ML_KATEGORIK) | {"line", "alt_kategori"}),
}


# ------------------------------------------------------------------ ölçüm

class _Olcer:
    """Bir adımın süresi ve süreç belleğinin tepesi (örnekleyen iş parçacığı)."""

    ARALIK = 0.1   # sn

    def __init__(self):
        self.surec = psutil.Process()
        self.tepe = 0
        self._dur = threading.Event()

    def _rss(self) -> int:
        return self.surec.memory_info().rss

    def _ornekle(self) -> None:
        while not self._dur.wait(self.ARALIK):
            self.tepe = max(self.tepe, self._rss())

    def __enter__(self):
        self.tepe = self._rss()
        self.bas = time.perf_counter()
        self._is = threading.Thread(target=self._ornekle, daemon=True)
        self._is.start()
        return self

    def __exit__(self, *_):
        self._dur.set()
        self._is.join()
        self.tepe = max(self.tepe, self._rss())
        self.saniye = time.perf_counter() - self.bas
        bilgi = self.surec.memory_info()
        self.surec_tepe = max(getattr(bilgi, "peak_wset", 0), self.tepe)


_GB = 1024 ** 3


# --------------------------------------------------------------- okuma

def _oku(yol: Path, sutunlar: list[str], durumlar: tuple[str, ...],
         bitis: pd.Timestamp | None = None) -> pd.DataFrame:
    """gunluk.parquet'ten istenen sütunlar, yalnız `durumlar`daki (ve `bitis`e
    dek) satırlar; kategoriler yazıldığı gibi döner (bütün evren)."""
    filtre = [("durum", "in", list(durumlar))]
    if bitis is not None:
        filtre.append(("tarih", "<=", bitis))
    return pd.read_parquet(yol, columns=sutunlar, filters=filtre).reset_index(drop=True)


# --------------------------------------------------------------- adımlar

def gunluk_yaz(con, yol: Path) -> int:
    """Mağaza ve online günlük tablosu yıl yıl; satır sayısını döndürür."""
    gecici = yol.with_suffix(".parquet.yaziliyor")
    yazici, n = None, 0
    try:
        for yil in YILLAR:
            bas, bit = max(date(yil, 1, 1), PENCERE[0]), min(date(yil, 12, 31), PENCERE[1])
            for parca in (stok.gunluk_magaza, stok.gunluk_online):
                df = parca(con, bas, bit)
                tablo = pa.Table.from_pandas(df[GUNLUK_SUTUNLARI], preserve_index=False)
                del df
                if yazici is None:
                    yazici = pq.ParquetWriter(gecici, tablo.schema)
                yazici.write_table(tablo)
                n += tablo.num_rows
                del tablo
                gc.collect()
    finally:
        if yazici is not None:
            yazici.close()
    gecici.replace(yol)
    return n


def carpanlar_yaz(con, gunluk: Path, yol: Path) -> int:
    """2023–2024 stoklu günlerinden çarpanlar; öğrenilen satır sayısını döndürür."""
    df = _oku(gunluk, _GOZLEM_SUTUNLARI, ("stoklu",), OGRENME_BITIS)
    df = ozellikler.ekle(con, df, CARPAN_OZELLIKLERI)
    c = carpanlar.ogren(df)
    n = len(df)
    del df
    gc.collect()
    gecici = yol.with_suffix(".pkl.yaziliyor")
    with open(gecici, "wb") as f:
        pickle.dump(c, f)
    gecici.replace(yol)
    return n


def _kestirici(ad: str, carpan: Path):
    if ad == "naif":
        return talep.Naif()
    if ad == "basit":
        with open(carpan, "rb") as f:
            return talep.Basit(carpanlar=pickle.load(f))
    if ad == "ml":
        return talep.ML()
    raise ValueError(f"bilinmeyen kestirici: {ad}")


def kayip_yaz(con, ad: str, gunluk: Path, carpan: Path, yol: Path) -> dict:
    """Bir kestiricinin kayıp tablosu (bos + tukenen satırları, kaynak dalıyla)."""
    gerek = KESTIRICI_OZELLIKLERI[ad]
    k = _kestirici(ad, carpan)

    gozlem = _oku(gunluk, _GOZLEM_SUTUNLARI, ("stoklu",))
    havuz = len(gozlem)
    gozlem = ozellikler.ekle(con, gozlem, gerek)
    k.egit(gozlem)
    del gozlem
    gc.collect()

    hedef = _oku(gunluk, GUNLUK_SUTUNLARI, ("bos", "tukenen"))
    tahmin = k.tahmin(ozellikler.ekle(con, hedef, gerek))
    del k
    gc.collect()
    kd = kayip.kayip_yaz(hedef, tahmin)
    kuyruk = int(kd.attrs.get("kuyruk_satir", 0))
    del tahmin, hedef
    kd = agac.kaynak_ata(kd, con)

    gecici = yol.with_suffix(".parquet.yaziliyor")
    kd.to_parquet(gecici, index=False)
    gecici.replace(yol)
    ozet = {"havuz_satir": havuz, "hedef_satir": len(kd),
            "kuyruk_satir": kuyruk,
            "toplam_kayip": float(kd["kayip"].sum())}
    del kd
    gc.collect()
    return ozet


# ----------------------------------------------------------------- akış

def _ayristir(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m yok_satma.hazirla", description=__doc__.split("\n")[0])
    p.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI,
                   help=f"çıktı dizini (varsayılan {VARSAYILAN_CIKTI})")
    p.add_argument("--db", type=Path, default=kaynak.VARSAYILAN_YOL,
                   help=f"v4 DuckDB dosyası (varsayılan {kaynak.VARSAYILAN_YOL})")
    p.add_argument("--yeniden", action="store_true",
                   help="var olan çıktıları da yeniden hesapla")
    p.add_argument("--adim", action="append", choices=ADIMLAR,
                   help="yalnız bu adımı (yeniden) koş; tekrarlanabilir. Seçim dışındaki "
                        "bağımlı adımların dosyaları silinir")
    return p.parse_args(argv)


def _parmak_izi(db: Path) -> dict:
    """v4 dosyasının kimliği: mutlak yol, boyut, mtime (ns)."""
    bilgi = db.stat()
    return {"yol": str(db.resolve()), "boyut": bilgi.st_size, "mtime_ns": bilgi.st_mtime_ns}


def _sil(yol: dict[str, Path], sure: dict, adimlar) -> None:
    for adim in adimlar:
        if yol[adim].exists():
            print(f"{adim}: gecersiz, siliniyor ({yol[adim]})", flush=True)
            yol[adim].unlink()
        sure["adimlar"].pop(adim, None)


def _bagimlilari(adimlar: set[str]) -> set[str]:
    """`adimlar`a (geçişli) bağımlı adımlar, kendileri hariç."""
    sonuc: set[str] = set()
    for adim in ADIMLAR:                       # sıra bağımlılık sırası: tek geçiş yeter
        if any(b in adimlar or b in sonuc for b in BAGIMLILIKLAR[adim]):
            sonuc.add(adim)
    return sonuc - adimlar


def main(argv: list[str] | None = None) -> dict:
    a = _ayristir(argv)
    cikti: Path = a.cikti
    cikti.mkdir(parents=True, exist_ok=True)
    yol = {ad: cikti / dosya for ad, dosya in DOSYALAR.items()}
    sure_yolu = cikti / "sure.json"
    sure = json.loads(sure_yolu.read_text(encoding="utf-8")) if sure_yolu.exists() else {}
    sure.setdefault("adimlar", {})
    sure["olcum"] = ("saniye: perf_counter; tepe_gb: adim boyunca 0,1 sn'de bir orneklenen "
                     "surec RSS'i (Windows calisma kumesi) en buyugu; surec_tepe_gb: adim "
                     "sonunda surecin o ana dek tepe calisma kumesi (psutil peak_wset)")

    def sure_yaz():
        sure_yolu.write_text(json.dumps(sure, ensure_ascii=False, indent=2), encoding="utf-8")

    con = kaynak.baglan(a.db)       # dosya yoksa burada açık hata
    try:
        # başka bir v4 dosyasından kurulmuş çıktılar geçersiz
        kaynak_yolu = cikti / "kaynak.json"
        iz = _parmak_izi(Path(a.db))
        eski = json.loads(kaynak_yolu.read_text(encoding="utf-8")) if kaynak_yolu.exists() else None
        if eski != iz:
            _sil(yol, sure, ADIMLAR)
            kaynak_yolu.write_text(json.dumps(iz, ensure_ascii=False, indent=2), encoding="utf-8")

        secili = list(a.adim) if a.adim else list(ADIMLAR)
        zorla = set(ADIMLAR) if a.yeniden else set(a.adim or ())
        kosan: set[str] = set()
        for adim in ADIMLAR:
            if adim not in secili:
                continue
            ustte_kosan = any(b in kosan for b in BAGIMLILIKLAR[adim])
            if yol[adim].exists() and adim not in zorla and not ustte_kosan:
                print(f"{adim}: var, atlandi ({yol[adim]})", flush=True)
                continue
            for b in BAGIMLILIKLAR[adim]:
                if not yol[b].exists():
                    raise FileNotFoundError(f"{yol[b]} yok: once `--adim {b}`")
            print(f"{adim}: basliyor", flush=True)
            with _Olcer() as o:
                if adim == "gunluk":
                    bilgi = {"satir": gunluk_yaz(con, yol["gunluk"])}
                elif adim == "carpanlar":
                    bilgi = {"satir": carpanlar_yaz(con, yol["gunluk"], yol["carpanlar"])}
                else:
                    bilgi = kayip_yaz(con, adim, yol["gunluk"], yol["carpanlar"], yol[adim])
            gc.collect()
            kosan.add(adim)
            # seçim dışındaki bağımlılar artık eski girdiye dayanıyor
            _sil(yol, sure, sorted(_bagimlilari({adim}) - set(secili), key=ADIMLAR.index))
            sure["adimlar"][adim] = {"saniye": round(o.saniye, 1),
                                     "tepe_gb": round(o.tepe / _GB, 2),
                                     "surec_tepe_gb": round(o.surec_tepe / _GB, 2), **bilgi}
            sure_yaz()
            print(f"{adim}: {o.saniye:.1f} sn, tepe {o.tepe / _GB:.2f} GB, {bilgi}", flush=True)
    finally:
        con.close()
    sure_yaz()
    return sure


if __name__ == "__main__":
    main()
