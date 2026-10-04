"""Vakanın bütün ara çıktılarını üretir: `python -m yok_satma.hazirla`.

Adımlar (her biri kendi dosyasına yazılır; dosya varsa adım atlanır,
`--yeniden` hepsini, `--adim` yalnız seçileni yeniden koşar; `--adim gunluk`
sonraki adımların dosyalarını bayatlatır, onları da istemek çağıranın işidir):

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
from contextlib import contextmanager
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

ADIMLAR = ("gunluk", "carpanlar", "naif", "basit", "ml")
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
    with open(yol, "wb") as f:
        pickle.dump(c, f)
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
                   help="yalnız bu adımı (yeniden) koş; tekrarlanabilir")
    return p.parse_args(argv)


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

    secili = list(a.adim) if a.adim else list(ADIMLAR)
    zorla = a.yeniden or bool(a.adim)
    con = kaynak.baglan(a.db)
    try:
        for adim in secili:
            if yol[adim].exists() and not zorla:
                print(f"{adim}: var, atlandi ({yol[adim]})", flush=True)
                continue
            if adim != "gunluk" and not yol["gunluk"].exists():
                raise FileNotFoundError(f"{yol['gunluk']} yok: once `--adim gunluk`")
            if adim == "basit" and not yol["carpanlar"].exists():
                raise FileNotFoundError(f"{yol['carpanlar']} yok: once `--adim carpanlar`")
            print(f"{adim}: basliyor", flush=True)
            with _Olcer() as o:
                if adim == "gunluk":
                    bilgi = {"satir": gunluk_yaz(con, yol["gunluk"])}
                elif adim == "carpanlar":
                    bilgi = {"satir": carpanlar_yaz(con, yol["gunluk"], yol["carpanlar"])}
                else:
                    bilgi = kayip_yaz(con, adim, yol["gunluk"], yol["carpanlar"], yol[adim])
            gc.collect()
            sure["adimlar"][adim] = {"saniye": round(o.saniye, 1),
                                     "tepe_gb": round(o.tepe / _GB, 2),
                                     "surec_tepe_gb": round(o.surec_tepe / _GB, 2), **bilgi}
            sure_yolu.write_text(json.dumps(sure, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{adim}: {o.saniye:.1f} sn, tepe {o.tepe / _GB:.2f} GB, {bilgi}", flush=True)
    finally:
        con.close()
    if not sure_yolu.exists():
        sure_yolu.write_text(json.dumps(sure, ensure_ascii=False, indent=2), encoding="utf-8")
    return sure


if __name__ == "__main__":
    main()
