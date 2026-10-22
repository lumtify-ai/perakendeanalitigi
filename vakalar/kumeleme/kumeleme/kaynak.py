"""Yayımlanan v4 verisinden okuma, vaka kapsamı ve şehir → iklim tablosu.

Kural: bu modül gizli gerçeğe (`perakende_veri`, gizli mağaza tablosu) ve hakeme dokunmaz (AST
kilidi, `tests/test_sizinti.py`). Veri `veri/cikti/v4/perakende.duckdb` (ya da
`PERAKENDE_V4_DB`) üstünden ortak paketin bağlantısıyla okunur.

**Kapsam** (`kapsam`). Karar gününde kümelenecek mağazalar: fiziksel (ONL değil), outlet
olmayan ve İlk Sevkiyat'ın aday tanımıyla (`allocation.paylastir.aday_maskesi`) aynı
koşulları sağlayan mağazalar:

    - açılış tarihi lansmandan (karar gününden sonraki ilk pazartesi) sonra değil. "Bugün
      açık" (açılış <= karar günü) bunun içindedir: lansmana dek açılacak mağaza da aday;
    - karar gününde kapanış kararı verilmemiş (`magaza_olay`: `olay = 'kapanis'` ve
      `karar_tarihi` <= karar günü yok);
    - lansmandan önce (lansman günü dahil) kapanmıyor (`magaza.kapanis_tarihi`).

Tadilat kapsamı değiştirmez: tadilattaki mağaza lansmana dek açılıyorsa adaydır.

`gecmis_hafta`: karar gününe dek **tamamlanmış** (pazartesi-pazar, pazar < karar günü) ve en az
bir brüt (pozitif adetli) satışı olan takvim haftası sayısı. İlk hafta mağazanın açıldığı
(kısmi) hafta olabilir; karar günü haftası sayılmaz (tamamlanmadı). SS25'te M041 için 19.
`kumelenir = gecmis_hafta >= GECMIS_HAFTA_ESIGI`; kalanlar `yeni` mağazadır.

**Şehir → iklim.** `SEHIR_IKLIM` vakada yazılı, açık bir tablodur; sınıflar genel
coğrafya bilgisinden yazıldı (Köppen/Türkiye iklim bölgeleri). Simülatörün şehir iklim
etiketleriyle 25 şehrin 24'ünde örtüşür (fark İzmir), çünkü sentetik zincir gerçek coğrafya
üstüne kurulmuştur: konum kuralının başarısı kısmen verinin kuruluş biçiminin özelliğidir
(README). Sınıflar:

    soguk        Doğu Anadolu'nun yüksek, uzun kışlı şehirleri
    sicak_sahil  Akdeniz ve Ege kıyısı (turistik tatil beldeleri dahil)
    ılıman       Marmara ve Karadeniz kıyısı, iç Ege (ılıman nemli)
    karasal      İç Anadolu ve güneydoğu/doğu iç kesimleri (sıcak yaz, soğuk kış)

`TURISTIK` tatil beldeleridir; hepsi `sicak_sahil`'dir. `METROPOL` üç büyük şehirdir.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
from perakende_analitik import kaynak as ortak

from kumeleme import sabitler

VERITABANI = ortak.VARSAYILAN_YOL

_AD = re.compile(r"^[a-z_]+$")
GIZLI_TABLO_ONEKI = "gizli_"       # gizli gerçeğin tabloları (yalnız hakem okur); kara liste
YASAK_TIP = ("Online", "Outlet")       # kümelenmeyen mağaza tipleri
_SATIS_SUTUNLARI = ("tarih", "magaza_id", "adet")

METROPOL = {"İstanbul", "Ankara", "İzmir"}

SEHIR_IKLIM: dict[str, str] = {
    # soğuk: yüksek rakım, uzun ve sert kış
    "Erzurum": "soguk",
    "Kars": "soguk",
    "Van": "soguk",
    "Sivas": "soguk",
    # sıcak sahil: Akdeniz ve Ege kıyısı, sıcak ve uzun yaz, ılık kış
    "Antalya": "sicak_sahil",
    "Alanya": "sicak_sahil",
    "Kemer": "sicak_sahil",
    "Fethiye": "sicak_sahil",
    "Bodrum": "sicak_sahil",
    "Mersin": "sicak_sahil",
    "Adana": "sicak_sahil",
    "İzmir": "sicak_sahil",
    # ılıman: Marmara, Karadeniz kıyısı, iç Ege
    "İstanbul": "ılıman",
    "Bursa": "ılıman",
    "Kocaeli": "ılıman",
    "Gebze": "ılıman",
    "Samsun": "ılıman",
    "Trabzon": "ılıman",
    "Denizli": "ılıman",
    # karasal: iç Anadolu, güneydoğu ve doğu iç kesimleri
    "Ankara": "karasal",
    "Eskişehir": "karasal",
    "Konya": "karasal",
    "Kayseri": "karasal",
    "Malatya": "karasal",
    "Diyarbakır": "karasal",
    "Gaziantep": "karasal",
}

TURISTIK = {"Antalya", "Alanya", "Kemer", "Fethiye", "Bodrum"}


def baglan(yol: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """v4 DuckDB dosyasına salt okunur bağlanır (ortak `kaynak.baglan`)."""
    return ortak.baglan(yol)


def yayimlanan_tablolar(con, adlar: Sequence[str]) -> dict[str, pd.DataFrame]:
    """`adlar` tablolarını DataFrame olarak okur (ad -> tablo, `adlar` sırasıyla).

    Büyük tablolarda kimlikler `category` gelir (DuckDB ENUM). `gizli_` önekli tablo adı
    reddedilir (savunma katmanı; yayımlanan veride zaten yoktur)."""
    for ad in adlar:
        if not _AD.match(ad):
            raise ValueError(f"geçersiz tablo adı: {ad!r}")
        if ad.startswith(GIZLI_TABLO_ONEKI):
            raise ValueError(f"gizli tablo okunamaz: {ad!r}")
    return {ad: con.execute(f"select * from {ad}").df() for ad in adlar}


# ---------------------------------------------------------------------------
# Kapsam
# ---------------------------------------------------------------------------


def lansman_gunu(karar_gunu) -> pd.Timestamp:
    """Karar gününden sonraki ilk pazartesi (SS25: cuma 2025-02-07 → 2025-02-10)."""
    k = pd.Timestamp(karar_gunu).normalize()
    return k + pd.Timedelta(days=(7 - k.weekday()) % 7 or 7)


def _gecmis_hafta(satis: pd.DataFrame, karar: pd.Timestamp) -> pd.Series:
    """magaza_id (str) -> karar gününe dek tamamlanmış, brüt satışlı hafta sayısı."""
    eksik = [s for s in _SATIS_SUTUNLARI if s not in satis.columns]
    if eksik:
        raise KeyError(f"satis sütunları eksik: {eksik}")
    s = satis.loc[(satis["adet"] > 0) & (satis["tarih"] < karar), ["tarih", "magaza_id"]]
    gun = s["tarih"].dt.normalize()
    hafta = gun - pd.to_timedelta(gun.dt.weekday, unit="D")           # haftanın pazartesisi
    tam = (hafta + pd.Timedelta(days=6)) < karar                      # pazar karar gününden önce
    h = pd.DataFrame({"magaza_id": s["magaza_id"], "hafta": hafta})[tam].drop_duplicates()
    h["magaza_id"] = h["magaza_id"].astype(str)
    return h.groupby("magaza_id").size()


def kapsam(magazalar: pd.DataFrame, magaza_olay: pd.DataFrame, satis: pd.DataFrame,
           karar_gunu, *, lansman=None) -> pd.DataFrame:
    """Karar gününde kümelenecek (ya da yeni) mağazalar; `magazalar` satır sırasıyla.

    Dönüş sütunları: `magaza_id, ad, sehir, bolge, tip, metrekare, enlem, istanbul, metropol,
    gecmis_hafta, kumelenir, yeni` (tanımlar modül notunda). `lansman` verilmezse karar
    gününden sonraki ilk pazartesidir. Yalnız karar gününden önceki satış okunur."""
    karar = pd.Timestamp(karar_gunu).normalize()
    lansman = lansman_gunu(karar) if lansman is None else pd.Timestamp(lansman).normalize()
    m = magazalar.reset_index(drop=True)
    kimlik = m["magaza_id"].astype(str)

    fiziksel = ~m["tip"].astype(str).isin(YASAK_TIP)
    acilis = pd.to_datetime(m["acilis_tarihi"])
    kapanis = pd.to_datetime(m["kapanis_tarihi"])
    karari_verilmis = set(magaza_olay.loc[
        (magaza_olay["olay"].astype(str) == "kapanis")
        & (pd.to_datetime(magaza_olay["karar_tarihi"]) <= karar), "magaza_id"].astype(str))

    aday = (fiziksel & (acilis <= lansman) & ~kimlik.isin(karari_verilmis)
            & ~(kapanis.notna() & (kapanis <= lansman)))

    k = m.loc[aday, ["magaza_id", "ad", "sehir", "bolge", "tip", "metrekare", "enlem"]].copy()
    k["magaza_id"] = k["magaza_id"].astype(str)
    for s in ("ad", "sehir", "bolge", "tip"):
        k[s] = k[s].astype(str)
    k["istanbul"] = (k["sehir"] == "İstanbul").to_numpy(dtype=bool)
    k["metropol"] = k["sehir"].isin(METROPOL).to_numpy(dtype=bool)
    k["gecmis_hafta"] = (k["magaza_id"].map(_gecmis_hafta(satis, karar)).fillna(0)
                         .astype("int64").to_numpy())
    k["kumelenir"] = (k["gecmis_hafta"] >= sabitler.GECMIS_HAFTA_ESIGI).to_numpy(dtype=bool)
    k["yeni"] = ~k["kumelenir"]
    return k.reset_index(drop=True)
