"""Ortak fikstürler: v4 şemalı oyuncak tablolar.

**Mağazalar** (12; karar günü 2025-02-07 cuma, lansman 2025-02-10 pazartesi):

    M01 İstanbul AVM      Marmara      metropol
    M02 İstanbul Cadde    Marmara      metropol
    M03 Ankara AVM        İç Anadolu   metropol
    M04 Ankara Cadde      İç Anadolu   metropol
    M05 Bursa AVM         Marmara
    M06 Konya Cadde       İç Anadolu
    M07 Denizli AVM       Ege
    M08 Bodrum AVM        Ege          turistik
    M09 Kocaeli AVM       Marmara      YENİ: 2024-11-23'te açıldı, karar gününe 10 tam satışlı hafta
    M10 İstanbul AVM      Marmara      kapalı: 2024-09-18'de kapandı
    M11 İstanbul Outlet   Marmara      outlet (kapsam dışı)
    ONL Online            Marmara      online (kapsam dışı)

Kapsam: M01-M09 (9; 8 kümelenir, 1 yeni). Üç görünür bölge: Marmara, İç Anadolu, Ege.

**Ürünler** (7 SKU, 4 option): Collection SS24 Tişört (`SKU-SS24` M/3 ve `SKU-SS24-S` S/2) ve
AW24 Ceket (`SKU-AW24` M/3 ve `SKU-AW24-L` L/4), Kadın Harf; Basic Pantolon (`SKU-BAS-36` 36/2,
`SKU-BAS-40` 40/4), Kadın Numara; NOS Çanta (`SKU-NOS-STD`, Standart tek beden).

**Satış** (iki sezon): her mağaza açıldığı pazartesiden 2025-02-03'e kadar her pazartesi;
2024-02-05 … 2024-08-26 arası SS24 Collection SKU'ları, sonrası AW24 Collection SKU'ları; Basic ve
NOS her hafta. Ana Collection satırı (`SKU-SS24` / `SKU-AW24`) kapsam testlerinin dayandığı
satırdır; diğer SKU'lar aynı pazartesilere eklenir (satışlı hafta sayısı değişmez). Miktarlar
mağazanın oyuncak profiline göre (`_PROFIL`; gizli segment değil, satışı üreten kurgu): `genc`
(M01, M03) Collection'ı ve küçük bedeni, `aile` Basic'i ve büyük bedeni, `turistik` (M08) yazı
çok satar. Her dördüncü haftanın salısı bir iade satırı (`SKU-BAS-40`, -1) vardır. Karar
gününden sonra (2025-02-10) her açık mağazaya bir satır daha vardır: kapsam ve özellikler bunu
görmemelidir.

**Stok** (pazartesi fotoğrafları): fiziksel her mağazanın sezondaki her SKU'su için, satışlı her
haftanın ertesi pazartesisi (fotoğraf önceki 7 günü anlatır) adet 10, `stoklu_gun` 7; ayrıca karar
gününden sonra 2025-02-10 ve 2025-02-17 fotoğrafları. `ONL` stok tutmaz.

**Gizli segment** yalnız `gizli` fikstüründe (`gizli_magaza`: magaza_id, segment); `tablolar`
onu taşımaz.
"""

import duckdb
import pandas as pd
import pytest

KARAR = pd.Timestamp("2025-02-07")
LANSMAN = pd.Timestamp("2025-02-10")

_MAGAZALAR = [   # magaza_id, ad, sehir, bolge, tip, enlem, metrekare, acilis, kapanis
    ("M01", "İstanbul 1", "İstanbul", "Marmara", "AVM", 41.01, 700, "2015-03-02", None),
    ("M02", "İstanbul 2", "İstanbul", "Marmara", "Cadde", 41.03, 350, "2016-03-07", None),
    ("M03", "Ankara 1", "Ankara", "İç Anadolu", "AVM", 39.93, 650, "2015-09-07", None),
    ("M04", "Ankara 2", "Ankara", "İç Anadolu", "Cadde", 39.91, 380, "2017-02-06", None),
    ("M05", "Bursa 1", "Bursa", "Marmara", "AVM", 40.19, 600, "2016-10-03", None),
    ("M06", "Konya 1", "Konya", "İç Anadolu", "Cadde", 37.87, 320, "2018-04-02", None),
    ("M07", "Denizli 1", "Denizli", "Ege", "AVM", 37.78, 560, "2019-05-06", None),
    ("M08", "Bodrum 1", "Bodrum", "Ege", "AVM", 37.04, 540, "2019-06-03", None),
    ("M09", "Kocaeli 1", "Kocaeli", "Marmara", "AVM", 40.85, 900, "2024-11-23", None),
    ("M10", "İstanbul 3", "İstanbul", "Marmara", "AVM", 41.00, 410, "2016-05-02", "2024-09-18"),
    ("M11", "İstanbul Outlet", "İstanbul", "Marmara", "Outlet", 41.05, 800, "2017-01-02", None),
    ("ONL", "Online", "Gebze", "Marmara", "Online", 40.80, 0, "2015-01-05", None),
]
_OLAY = [   # magaza_id, olay, karar_tarihi, olay_tarihi, bitis_tarihi
    ("M09", "acilis", "2024-09-01", "2024-11-23", None),
    ("M10", "kapanis", "2024-07-01", "2024-09-18", None),
]
SKU_SS24, SKU_AW24 = "SKU-SS24", "SKU-AW24"
_URUNLER = [   # urun_id, option_id, line, sezon_kodu, dalga, lansman, cikis, ust, alt, segment, kalip, beden_seti, beden, sira
    (SKU_SS24, "OPT-SS24", "Collection", "SS24", 1, "2024-02-12", "2024-08-26",
     "Üst Giyim", "Tişört", "orta", "regular", "Kadın Harf", "M", 3),
    ("SKU-SS24-S", "OPT-SS24", "Collection", "SS24", 1, "2024-02-12", "2024-08-26",
     "Üst Giyim", "Tişört", "orta", "regular", "Kadın Harf", "S", 2),
    (SKU_AW24, "OPT-AW24", "Collection", "AW24", 1, "2024-09-02", "2025-02-24",
     "Dış Giyim", "Ceket", "üst", "slim", "Kadın Harf", "M", 3),
    ("SKU-AW24-L", "OPT-AW24", "Collection", "AW24", 1, "2024-09-02", "2025-02-24",
     "Dış Giyim", "Ceket", "üst", "slim", "Kadın Harf", "L", 4),
    ("SKU-BAS-36", "OPT-BAS", "Basic", "DEVAMLI", 0, "2022-07-04", None,
     "Alt Giyim", "Pantolon", "giris", "relaxed", "Kadın Numara", "36", 2),
    ("SKU-BAS-40", "OPT-BAS", "Basic", "DEVAMLI", 0, "2022-07-04", None,
     "Alt Giyim", "Pantolon", "giris", "relaxed", "Kadın Numara", "40", 4),
    ("SKU-NOS-STD", "OPT-NOS", "NOS", "DEVAMLI", 0, "2022-07-04", None,
     "Aksesuar", "Çanta", "orta", "regular", "Standart", "STD", 1),
]

# satışı üreten oyuncak profil (gizli segment değil); belirtilmeyen mağaza "aile"
_PROFIL = {"M01": "genc", "M03": "genc", "M08": "turistik"}
# profil -> (ikinci Collection bedeni, Basic 36, Basic 40, NOS) haftalık adet; yaz aylarında turistik x3
_MIKTAR = {"genc": (3, 2, 1, 1), "aile": (1, 1, 3, 1), "turistik": (2, 2, 2, 2)}

_S, _T = "string", "datetime64[ns]"
SEMA = {   # gerçek v4 şemasının oyuncak tablolarda kullanılan sütunları
    "magaza": {"magaza_id": _S, "ad": _S, "sehir": _S, "bolge": _S, "enlem": "float64",
               "boylam": "float64", "tip": _S, "metrekare": "int64", "kat_sayisi": "int64",
               "kapasite": "int64", "acilis_tarihi": _T, "kapanis_tarihi": _T},
    "magaza_olay": {"magaza_id": _S, "olay": _S, "karar_tarihi": _T, "olay_tarihi": _T,
                    "bitis_tarihi": _T},
    "urun": {"urun_id": _S, "option_id": _S, "line": _S, "sezon_kodu": _S, "dalga": "int64",
             "lansman_tarihi": _T, "cikis_tarihi": _T, "ust_kategori": _S, "alt_kategori": _S,
             "fiyat_segmenti": _S, "kalip": _S, "beden_seti": _S, "beden": _S, "beden_sira": "int64"},
    "satis": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "tutar": "float64",
              "indirim_tutari": "float64", "kampanya_id": _S},
    "stok": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "stoklu_gun": "int8"},
}


def doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=list(SEMA[tablo]))
    for s, t in SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


def _haftalar(acilis, kapanis) -> pd.DatetimeIndex:
    """Mağazanın satışlı pazartesileri (2024-02-05 … 2025-02-03 ya da kapanışa dek)."""
    ilk = pd.Timestamp(acilis)
    ilk = ilk + pd.Timedelta(days=(7 - ilk.weekday()) % 7)         # açıldığı hafta ya da sonraki pazartesi
    ilk = max(ilk, pd.Timestamp("2024-02-05"))
    son = pd.Timestamp(kapanis) if kapanis else pd.Timestamp("2025-02-03")
    return pd.date_range(ilk, son, freq="7D")


def _sezon_skulari(t: pd.Timestamp) -> tuple[str, str]:
    return (SKU_SS24, "SKU-SS24-S") if t < pd.Timestamp("2024-09-02") else (SKU_AW24, "SKU-AW24-L")


def _satis() -> list[tuple]:
    satir = []
    for i, (m, _ad, _sh, _bl, _tip, _en, _m2, acilis, kapanis) in enumerate(_MAGAZALAR):
        ikinci, b36, b40, nos = _MIKTAR[_PROFIL.get(m, "aile")]
        for j, t in enumerate(_haftalar(acilis, kapanis)):
            ana, yan = _sezon_skulari(t)
            adet = 1 + (i + t.isocalendar().week) % 4
            satir.append((t, m, ana, adet, 100.0 * adet, 0.0, None))
            kat = 3 if _PROFIL.get(m) == "turistik" and t.month in (6, 7, 8) else 1
            satir += [(t, m, sku, a * kat, 50.0 * a * kat, 0.0, None)
                      for sku, a in ((yan, ikinci), ("SKU-BAS-36", b36), ("SKU-BAS-40", b40),
                                     ("SKU-NOS-STD", nos))]
            if j % 4 == 3:      # iade: rafa dönen bir Basic
                satir.append((t + pd.Timedelta(days=1), m, "SKU-BAS-40", -1, -50.0, 0.0, None))
        if not kapanis:     # karar gününden sonra: kapsam görmemeli
            satir.append((LANSMAN, m, SKU_AW24, 3, 300.0, 0.0, None))
    return satir


def _stok() -> list[tuple]:
    satir = []
    for m, _ad, _sh, _bl, tip, _en, _m2, acilis, kapanis in _MAGAZALAR:
        if tip == "Online":
            continue
        for t in _haftalar(acilis, kapanis):
            d = t + pd.Timedelta(days=7)                            # fotoğraf önceki haftayı anlatır
            satir += [(d, m, sku, 10, 7) for sku in _sezon_skulari(t) + ("SKU-BAS-36", "SKU-BAS-40",
                                                                         "SKU-NOS-STD")]
        if not kapanis:     # karar gününden sonraki fotoğraflar
            satir += [(d, m, sku, 10, 7) for d in (LANSMAN, LANSMAN + pd.Timedelta(days=7))
                      for sku in (SKU_AW24, "SKU-AW24-L", "SKU-BAS-36")]
    return satir


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    magaza = doldur("magaza", [(m, ad, sh, bl, en, 29.0, tip, m2, 1, 8 * m2 + 100, a, k)
                               for m, ad, sh, bl, tip, en, m2, a, k in _MAGAZALAR])
    return {
        "magaza": magaza,
        "magaza_olay": doldur("magaza_olay", _OLAY),
        "urun": doldur("urun", _URUNLER),
        "satis": doldur("satis", _satis()),
        "stok": doldur("stok", _stok()),
    }


@pytest.fixture
def tablolar() -> dict[str, pd.DataFrame]:
    return oyuncak_tablolar()


@pytest.fixture
def gizli() -> pd.DataFrame:
    """Gizli segment tablosu (yalnız hakem/ölçüm testleri için)."""
    seg = {"M01": "metropol_genc", "M02": "anadolu_aile", "M03": "metropol_genc",
           "M04": "metropol_aile", "M05": "anadolu_aile", "M06": "anadolu_aile",
           "M07": "anadolu_aile", "M08": "turistik", "M09": "anadolu_aile"}
    return pd.DataFrame({"magaza_id": list(seg), "segment": list(seg.values())})


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    return con
