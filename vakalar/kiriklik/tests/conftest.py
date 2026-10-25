"""Ortak fikstürler: yayımlanan v4 şemasında oyuncak tablolar ve gerçek veri bağlantısı.

**Oyuncak dünya** (karar günü AW24: 2024-12-09 pazartesi; indirim 2025-01-02):

    S1 AVM       açık                                  S5 AVM    kapanış kararı 2024-11-20 (olay 2025-02-01)
    S2 Cadde     açık                                  S6 AVM    kapanış kararı 2024-12-20 (karardan sonra: bilinmez)
    S3 Outlet    fiziksel değil                        S7 AVM    tadilatta 2024-12-01 .. 2024-12-20
    ONL Online   fiziksel değil                        S8 AVM    açılışı 2025-01-05 (karar günü kapalı)
    S4 AVM       kapanmış (kapanis_tarihi 2024-10-01)

Option'lar: `AW24-a` (Collection, Kadın Harf, 5 beden), `AW24-s` (Collection, Standart, tek beden),
`AW24-o` (Outlet line), `SS25-a` (öteki test sezonu). Yalnız `AW24-a` kapsamdadır.

`takvim` günlük (tatil: 2024-11-29, 2025-01-01); `kampanya`: Black Friday 2024-11-29..12-02 (%30) ve
karardan sonrası bir kategori kampanyası.

**`AW24-a-2` (ikinci beden) siparişleri** (karar gününe göre): A açık ve indirimden önce teslim
planlı (10, sayılır); B planı indirimden sonra (sayılmaz); C karardan önce teslim edilmiş (sayılmaz); D
siparişi karardan sonra verilmiş (sayılmaz); E karar günü teslim edilmiş (7, sayılır: `>= karar`); F
karardan sonra teslim edilmiş, planı indirimden önce (3, sayılır). Toplam 20.
"""

import duckdb
import pandas as pd
import pytest

from kiriklik import kaynak

_S, _T = "string", "datetime64[ns]"

KARAR = pd.Timestamp("2024-12-09")
INDIRIM = pd.Timestamp("2025-01-02")
CIKIS = pd.Timestamp("2025-02-24")
ACIK_SIPARIS_TOPLAMI = 20

SEMA = {
    "magaza": {"magaza_id": _S, "ad": _S, "sehir": _S, "bolge": _S, "tip": _S,
               "acilis_tarihi": _T, "kapanis_tarihi": _T},
    "magaza_olay": {"magaza_id": _S, "olay": _S, "karar_tarihi": _T, "olay_tarihi": _T, "bitis_tarihi": _T},
    "urun": {"urun_id": _S, "option_id": _S, "line": _S, "sezon_kodu": _S, "dalga": "int64",
             "ust_kategori": _S, "alt_kategori": _S, "beden_seti": _S, "beden": _S, "beden_sira": "int64",
             "liste_fiyati": "float64", "alis_fiyati": "float64", "lansman_tarihi": _T, "cikis_tarihi": _T},
    "stok": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "stoklu_gun": "int8"},
    "depo_stok": {"tarih": _T, "urun_id": _S, "adet": "int32"},
    "satis": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "tutar": "float64",
              "indirim_tutari": "float64", "kampanya_id": _S},
    "sezon": {"sezon_kodu": _S, "dalga": "int64", "lansman_tarihi": _T, "indirim_baslangic": _T,
              "cikis_tarihi": _T},
    "takvim": {"tarih": _T, "tatil_mi": "bool"},
    "kampanya": {"kampanya_id": _S, "tip": _S, "baslangic": _T, "bitis": _T, "oran": "float64"},
    "siparis": {"siparis_id": _S, "tip": _S, "option_id": _S, "urun_id": _S, "tedarikci_id": _S,
                "siparis_tarihi": _T, "planlanan_teslim": _T, "gerceklesen_teslim": _T, "adet": "int32"},
}

_MAGAZALAR = [   # magaza_id, ad, sehir, bolge, tip, acilis, kapanis
    ("S1", "İstanbul 1", "İstanbul", "Marmara", "AVM", "2023-01-01", None),
    ("S2", "İstanbul 2", "İstanbul", "Marmara", "Cadde", "2023-01-01", None),
    ("S3", "Outlet 1", "Kocaeli", "Marmara", "Outlet", "2023-01-01", None),
    ("ONL", "Online", "İstanbul", "Marmara", "Online", "2023-01-01", None),
    ("S4", "İzmir 1", "İzmir", "Ege", "AVM", "2023-01-01", "2024-10-01"),
    ("S5", "Ankara 1", "Ankara", "İç Anadolu", "AVM", "2023-01-01", "2025-02-01"),
    ("S6", "Antalya 1", "Antalya", "Akdeniz", "AVM", "2023-01-01", "2025-03-01"),
    ("S7", "Trabzon 1", "Trabzon", "Karadeniz", "AVM", "2023-01-01", None),
    ("S8", "Van 1", "Van", "Doğu Anadolu", "AVM", "2025-01-05", None),
]
_OLAYLAR = [   # magaza_id, olay, karar_tarihi, olay_tarihi, bitis_tarihi
    ("S5", "kapanis", "2024-11-20", "2025-02-01", None),
    ("S6", "kapanis", "2024-12-20", "2025-03-01", None),
    ("S7", "tadilat", "2024-11-25", "2024-12-01", "2024-12-20"),
    ("S8", "acilis", "2024-10-01", "2025-01-05", None),
]
# option_id, line, sezon, beden_seti, bedenler, liste, alis
_OPTIONLAR = [
    ("AW24-a", "Collection", "AW24", "Kadın Harf", ("XS", "S", "M", "L", "XL"), 500.0, 200.0),
    ("AW24-s", "Collection", "AW24", "Standart", ("STD",), 100.0, 40.0),
    ("AW24-o", "Outlet", "AW24", "Kadın Harf", ("XS", "S", "M", "L", "XL"), 300.0, 120.0),
    ("SS25-a", "Collection", "SS25", "Kadın Harf", ("XS", "S", "M", "L", "XL"), 600.0, 250.0),
]
_PAZARTESILER = ("2024-11-25", "2024-12-02", "2024-12-09", "2024-12-16")   # sonuncusu karardan sonra


def urun_id(option_id: str, sira: int) -> str:
    return f"{option_id}-{sira}"


def _doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=list(SEMA[tablo]))
    for s, t in SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


def _urunler() -> list[tuple]:
    return [(urun_id(o, i + 1), o, line, sezon, 1, "Üst Giyim", "Tişört", seti, b, i + 1, liste, alis,
             "2024-08-19", "2025-02-24" if sezon == "AW24" else "2025-08-25")
            for o, line, sezon, seti, bedenler, liste, alis in _OPTIONLAR for i, b in enumerate(bedenler)]


def _stok() -> list[tuple]:
    """AW24-a: S1 her tarihte 1-0-2-1-1 (kırık: ikinci beden yok), S2 tam set 1-2-2-1-1. Karardan sonraki
    pazartesi (2024-12-16) ayırt edilsin diye S1'de dolu (9 adet). S5'te bir satır, S3 / Standart / öteki
    sezon hücreye girmemeli."""
    satir = []
    for t in _PAZARTESILER:
        sonra = t == "2024-12-16"
        for i, a in enumerate((1, 0, 2, 1, 1)):
            satir.append((t, "S1", urun_id("AW24-a", i + 1), 9 if sonra else a, 7))
        for i, a in enumerate((1, 2, 2, 1, 1)):
            satir.append((t, "S2", urun_id("AW24-a", i + 1), a, 7))
        satir.append((t, "S5", urun_id("AW24-a", 1), 3, 7))
        satir.append((t, "S3", urun_id("AW24-a", 1), 4, 7))      # Outlet: hücreye girmez
        satir.append((t, "S1", urun_id("AW24-s", 1), 5, 7))      # Standart: girmez
        satir.append((t, "S1", urun_id("SS25-a", 1), 5, 7))      # öteki sezon: girmez
    return satir


def _depo() -> list[tuple]:
    return [(t, urun_id("AW24-a", i), a) for t in ("2024-12-08", "2024-12-09", "2024-12-10")
            for i, a in ((1, 0), (2, 6), (3, 0), (4, 0), (5, 0))]


def _satis() -> list[tuple]:
    """S1 / AW24-a-1: karardan önce 2024-12-07 (2 adet; bir mükerrer kopyası), 2024-12-08 (iade, -1),
    karar günü 2024-12-09 (5, dışarıda) ve sonrası 2024-12-10 (7, dışarıda)."""
    u = urun_id("AW24-a", 1)
    return [("2024-12-07", "S1", u, 2, 800.0, 0.0, None),
            ("2024-12-07", "S1", u, 2, 800.0, 0.0, None),       # mükerrer kopya: düşer
            ("2024-12-08", "S1", u, -1, -400.0, 0.0, None),     # iade: ham, işaretli kalır
            ("2024-12-09", "S1", u, 5, 2000.0, 0.0, None),
            ("2024-12-10", "S1", u, 7, 2800.0, 0.0, None),
            ("2024-12-07", "S3", u, 3, 600.0, 0.0, None)]       # Outlet: girmez


def _siparis() -> list[tuple]:
    u = urun_id("AW24-a", 2)
    return [   # siparis_id, tip, option, urun, tedarikci, siparis, planlanan, gerceklesen, adet
        ("A", "rpt", "AW24-a", u, "T1", "2024-11-01", "2024-12-20", None, 10),
        ("B", "rpt", "AW24-a", u, "T1", "2024-11-01", "2025-01-10", None, 100),
        ("C", "rpt", "AW24-a", u, "T1", "2024-10-01", "2024-11-20", "2024-12-01", 200),
        ("D", "rpt", "AW24-a", u, "T1", "2024-12-10", "2024-12-20", None, 300),
        ("E", "rpt", "AW24-a", u, "T1", "2024-11-15", "2024-12-05", "2024-12-09", 7),
        ("F", "rpt", "AW24-a", u, "T1", "2024-11-15", "2024-12-20", "2024-12-30", 3),
        ("G", "rpt", "SS25-a", urun_id("SS25-a", 2), "T1", "2024-11-01", "2024-12-20", None, 400)]


def _takvim() -> list[tuple]:
    """2024-11-01 .. 2025-03-01 günlük; tatil: Black Friday cuması (2024-11-29) ve 2025-01-01."""
    return [(g, g in (pd.Timestamp("2024-11-29"), pd.Timestamp("2025-01-01")))
            for g in pd.date_range("2024-11-01", "2025-03-01")]


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    return {
        "magaza": _doldur("magaza", _MAGAZALAR),
        "magaza_olay": _doldur("magaza_olay", _OLAYLAR),
        "urun": _doldur("urun", _urunler()),
        "stok": _doldur("stok", _stok()),
        "depo_stok": _doldur("depo_stok", _depo()),
        "satis": _doldur("satis", _satis()),
        "sezon": _doldur("sezon", [("AW24", 1, "2024-08-19", "2025-01-02", "2025-02-24"),
                                   ("SS25", 1, "2025-02-10", "2025-06-30", "2025-08-25")]),
        "siparis": _doldur("siparis", _siparis()),
        "takvim": _doldur("takvim", _takvim()),
        "kampanya": _doldur("kampanya", [("BF2024", "black_friday", "2024-11-29", "2024-12-02", 0.3),
                                         ("KAT2025_07", "kategori", "2025-01-12", "2025-01-24", 0.4)]),
    }


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    return con


@pytest.fixture
def tablolar() -> dict[str, pd.DataFrame]:
    return oyuncak_tablolar()


@pytest.fixture
def con(tablolar):
    c = oyuncak_baglan(tablolar)
    yield c
    c.close()


@pytest.fixture(scope="session")
def veri_con():
    """Yayımlanan v4'e salt okunur bağlantı (`PERAKENDE_V4_DB` ya da `veri/cikti/v4/perakende.duckdb`);
    dosya yoksa `veri` işaretli testler atlanır."""
    yol = kaynak.VERITABANI
    if not yol.exists():
        pytest.skip(f"yayımlanan v4 veri yok: {yol}")
    c = kaynak.baglan(yol)
    yield c
    c.close()


def pytest_collection_modifyitems(config, items):
    """`yavas` işaretli testler (TAM koşu, ~4 dk, ~8 GB) yalnız `-m` ifadesi `yavas`ı anarsa koşar
    (`-m "veri and yavas"`); öteki her çağrıda atlanır."""
    if "yavas" in (config.getoption("markexpr") or ""):
        return
    atla = pytest.mark.skip(reason='yavas: -m "veri and yavas" ile koşulur')
    for item in items:
        if "yavas" in item.keywords:
            item.add_marker(atla)
