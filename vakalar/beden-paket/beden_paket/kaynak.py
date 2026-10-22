"""Yayımlanan v4 verisinden okuma, vaka kapsamı ve beş bedenli SKU'lar.

Kural: bu modül gizli gerçeğe (`perakende_veri`, gizli mağaza tablosu, `beden_kayma`) ve hakeme
dokunmaz (AST kilidi, `tests/test_sizinti.py`). Veri `veri/cikti/v4/perakende.duckdb` (ya da
`PERAKENDE_V4_DB`) üstünden ortak paketin bağlantısıyla okunur.

**Kapsam** (`kapsam`). Karar gününde paket alacak mağazalar Kümeleme vakasının kapsamıdır
(`kumeleme.kaynak.kapsam`): fiziksel, outlet olmayan ve İlk Sevkiyat'ın aday tanımını sağlayan
mağazalar; SS25 karar gününde 69 aday. Aynı mağazalar, aynı sıra: Kümeleme, İlk Sevkiyat ve bu
vaka aynı mağaza kümesini kıyaslar. Burada yalnız sütunlar vaka diline çevrilir:

    istanbul       İstanbul mağazası mı (Ali'nin mağazaları; Anadolu Veli'nin)
    gecmis_hafta   karar gününe dek tamamlanmış, brüt satışlı hafta sayısı
    yeni           gecmis_hafta Kümeleme eşiğinin (`kumeleme.sabitler.GECMIS_HAFTA_ESIGI`)
                   altında: kendi eğrisi güvenilmez, profil ya da zincir eğrisi kullanılır

`bes_bedenli`: beden eğrisinin tanımlı olduğu SKU'lar. Aksesuar ve tek bedenli setler (Standart)
dışarıda kalır; geriye `BEDEN_SAYISI` bedenli (beden_sira 1..5) setlerin SKU'ları kalır.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
from kumeleme import kaynak as kumeleme_kaynak
from perakende_analitik import kaynak as ortak

from beden_paket import sabitler

VERITABANI = ortak.VARSAYILAN_YOL

_AD = re.compile(r"^[a-z_]+$")
GIZLI_TABLO_ONEKI = "gizli_"       # gizli gerçeğin tabloları (yalnız hakem okur); kara liste
AKSESUAR = "Aksesuar"

KAPSAM_SUTUNLARI = ["magaza_id", "ad", "sehir", "bolge", "istanbul", "tip", "metrekare", "enlem",
                    "gecmis_hafta", "yeni"]


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


def kapsam_tablolari(con, karar_gunu) -> dict[str, pd.DataFrame]:
    """`kapsam` için gereken üç tablo: `magaza`, `magaza_olay` ve karar gününden önceki
    (tarih, magaza_id, adet) brüt satış günleri. 18 milyon satırlık `satis` bellekte tutulmaz;
    kapsamın okuduğu üç sütun gün düzeyinde tekilleştirilir."""
    t = yayimlanan_tablolar(con, ("magaza", "magaza_olay"))
    t["satis"] = con.execute(
        "select distinct tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
        "1 as adet from satis where adet > 0 and tarih < ?", [pd.Timestamp(karar_gunu)]).df()
    return t


def kapsam(tablolar: dict[str, pd.DataFrame], karar_gunu) -> pd.DataFrame:
    """Karar gününde paket alacak mağazalar (Kümeleme kapsamının vaka diline çevrilmişi).

    `tablolar`: `magaza`, `magaza_olay`, `satis` (en az tarih, magaza_id, adet). Dönüş sütunları
    `KAPSAM_SUTUNLARI`; satır sırası `magaza` tablosununkiyle, yani Kümeleme'ninkiyle aynıdır.
    Yalnız karar gününden önceki satış okunur."""
    k = kumeleme_kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"], tablolar["satis"],
                               karar_gunu)
    return k[KAPSAM_SUTUNLARI].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Beş bedenli SKU'lar
# ---------------------------------------------------------------------------

_URUN_SUTUNLARI = ("urun_id", "option_id", "ust_kategori", "beden_seti", "beden", "beden_sira")


def bes_bedenli(urunler: pd.DataFrame) -> pd.DataFrame:
    """Beden eğrisinin tanımlı olduğu SKU'lar: aksesuar ve tek bedenli setler hariç.

    Bir beden seti `BEDEN_SAYISI` ayrı beden sırasına (1..5) sahipse beş bedenlidir. Dönüş:
    `urunler`'in bu SKU'lardaki satırları (sütunları aynı), `beden_sira` int64, `urunler`
    sırasıyla."""
    eksik = [s for s in _URUN_SUTUNLARI if s not in urunler.columns]
    if eksik:
        raise KeyError(f"urun sütunları eksik: {eksik}")
    sira = set(range(1, sabitler.BEDEN_SAYISI + 1))
    kume = urunler.groupby(urunler["beden_seti"].astype(str))["beden_sira"].agg(set)
    bes = {ad for ad, v in kume.items() if v == sira}
    maske = (urunler["beden_seti"].astype(str).isin(bes)
             & (urunler["ust_kategori"].astype(str) != AKSESUAR))
    u = urunler.loc[maske].copy()
    u["beden_sira"] = u["beden_sira"].astype("int64")
    return u.reset_index(drop=True)
