"""Ortak fikstürler.

`v4_con`: gerçek v4 verisi (yavaş, `veri` işaretli testler); oturum başına bir
kez açılır, dosya yoksa test atlanır.

`oyuncak_con`: bellekte küçük bir v4 dünyası. Şema gerçek v4'ün şemasıdır
(sütun adları ve türleri); satırları elle izlenebilir. Sonraki görevler
`oyuncak_tablolar()`'ın sözlüğüne `ekle()` ile satır ekleyip `oyuncak_baglan()`
ile yeni bir bağlantı kurar; bu dosyadaki temel senaryo değişmez.

TEMEL SENARYO (2025-01-06 pzt ... 2025-01-26 pzt-pazar, üç tam hafta; pazartesi
fotoğrafları 01-06, 01-13, 01-20 ve 01-27'de):

    mağazalar   M001 (AVM, Marmara), M002 (Outlet, Ege), ONL (Online)
    option      MDL0001-SYH (Erkek, Üst Giyim / Gömlek, Basic); SKU'lar
                -S, -M, -L (beden_sira 2, 3, 4); 2024-11-04'te lanse
    hücreler    M001 x S/M/L, M002 x S/M (her birine 2024-12-31'de varan
                ilk dağıtım) + ONL x her SKU
    M001 x M    pzt 01-06 stok 3; sal 01-07 2 adet satılır (bu satır
                MÜKERRER, iki kez yazılı), çar 01-08 1 adet, per 01-09
                satış yok ve stok 0 (bos), cum 01-10 DEPO -> M001
                replenishment 4 adet (çıkış 01-09, varış 01-10), cum 1 adet
                satılır; pzt 01-13 stok 3
    M002 x L    HAYALET stok: tek stok satırı (pzt 01-06, 2 adet,
                stoklu_gun 7), hiç sevkiyat/satış yok -> çeşitte değil
    depo_stok   2024-12-30 ... 2025-01-27 günlük, SKU başına

Pazartesi fotoğrafı, stoklu gün ve depo stoğu `_simule` ile hesaplanır, bu
yüzden stok korunumu tutarlıdır: pazartesi fotoğrafı = önceki pazartesi +
varışlar - satışlar (iade yok).
"""

import warnings

import duckdb
import pandas as pd
import pytest

from perakende_analitik import kaynak

# numpy 2.5 + pandas 2.3: Timedelta içinde "generic unit" uyarısı (bizim değil)
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)

# --------------------------------------------------------------------- gerçek


@pytest.fixture(scope="session")
def v4_con():
    if not kaynak.VARSAYILAN_YOL.exists():
        pytest.skip("v4 verisi yok (cd veri && python -m perakende_veri.v4.uret)")
    con = kaynak.baglan()
    yield con
    con.close()


# ------------------------------------------------------------------- oyuncak

# Gerçek v4 şeması: tablo -> {sütun: pandas türü}. Boş tabloların türü buradan
# gelir ("string" sütunlar DuckDB'de VARCHAR olur).
_S = "string"
_T = "datetime64[ns]"
_SEMA: dict[str, dict[str, str]] = {
    "magaza": {"magaza_id": _S, "ad": _S, "sehir": _S, "bolge": _S, "enlem": "float64",
               "boylam": "float64", "tip": _S, "metrekare": "int64", "kat_sayisi": "int64",
               "kapasite": "int64", "acilis_tarihi": _T, "kapanis_tarihi": _T},
    "magaza_olay": {"magaza_id": _S, "olay": _S, "karar_tarihi": _T, "olay_tarihi": _T,
                    "bitis_tarihi": _T},
    "urun": {"urun_id": _S, "option_id": _S, "model_kodu": _S, "model_adi": _S, "ad": _S,
             "marka": _S, "cinsiyet": _S, "ust_kategori": _S, "alt_kategori": _S, "line": _S,
             "sezon_kodu": _S, "dalga": "int64", "renk": _S, "renk_kodu": _S, "beden_seti": _S,
             "beden": _S, "beden_sira": "int64", "kumas": _S, "kalip": _S, "desen": _S,
             "detay": _S, "detay_alani": _S, "fiyat_segmenti": _S, "alis_fiyati": "float64",
             "liste_fiyati": "float64", "lansman_tarihi": _T, "cikis_tarihi": _T,
             "tedarikci_id": _S},
    "takvim": {"tarih": _T, "hafta": "int64", "ay": "int32", "yil": "int32", "sezon": _S,
               "sezon_kodu": _S, "tatil_mi": "bool", "indirim_donemi_mi": "bool"},
    "sezon": {"sezon_kodu": _S, "dalga": "int64", "lansman_tarihi": _T,
              "indirim_baslangic": _T, "cikis_tarihi": _T},
    "kampanya": {"kampanya_id": _S, "tip": _S, "baslangic": _T, "bitis": _T,
                 "kapsam_ust_kategori": _S, "kapsam_line": _S, "kapsam_bolge": _S,
                 "oran": "float64"},
    "fiyat": {"hafta_baslangic": _T, "option_id": _S, "hat": _S, "indirim_orani": "float64"},
    "satis": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "tutar": "float64",
              "indirim_tutari": "float64", "kampanya_id": _S},
    "stok": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "stoklu_gun": "int8"},
    "depo_stok": {"tarih": _T, "urun_id": _S, "adet": "int32"},
    "sevkiyat": {"tarih": _T, "varis_tarihi": _T, "kaynak": _S, "hedef": _S, "urun_id": _S,
                 "adet": "int32", "tip": _S, "paket_id": _S},
    "siparis": {"siparis_id": _S, "tip": _S, "option_id": _S, "urun_id": _S, "tedarikci_id": _S,
                "siparis_tarihi": _T, "planlanan_teslim": _T, "gerceklesen_teslim": _T,
                "adet": "int32"},
    "kalite_kontrol": {"siparis_id": _S, "teslim_tarihi": _T, "numune": "int32",
                       "hatali": "int32"},
}


def bos(tablo: str) -> pd.DataFrame:
    """Gerçek v4 sütun adları ve türleriyle boş tablo."""
    return pd.DataFrame({s: pd.Series(dtype=t) for s, t in _SEMA[tablo].items()})


def doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    """Şema sırasıyla satır demetlerinden, şema türlerine çevrilmiş tablo."""
    df = pd.DataFrame(satirlar, columns=list(_SEMA[tablo]))
    for s, t in _SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


def ekle(tablolar: dict[str, pd.DataFrame], tablo: str, satirlar: list[tuple]) -> None:
    """Sonraki görevler için: tabloya satır ekler (yerinde)."""
    tablolar[tablo] = pd.concat([tablolar[tablo], doldur(tablo, satirlar)], ignore_index=True)


DONEM = pd.date_range("2025-01-06", "2025-01-26", freq="D")
PAZARTESILER = [pd.Timestamp(g) for g in ("2025-01-06", "2025-01-13", "2025-01-20", "2025-01-27")]
_BASLA = pd.Timestamp("2024-12-30")  # simülasyon başlangıcı (ilk dağıtımdan önce)
_BITIS = pd.Timestamp("2025-01-27")
_ILK_VARIS = pd.Timestamp("2024-12-31")
_ILK_CIKIS = pd.Timestamp("2024-12-30")
_DEPO_BASLANGIC = 100  # SKU başına açılış depo stoğu

SKULAR = ("MDL0001-SYH-S", "MDL0001-SYH-M", "MDL0001-SYH-L")

# hücre -> (ilk dağıtım adedi, {gün: satış adedi}, {varış günü: replenishment adedi})
_HUCRELER: dict[tuple[str, str], tuple[int, dict[str, int], dict[str, int]]] = {
    ("M001", "MDL0001-SYH-S"): (10, {"2025-01-07": 1, "2025-01-09": 1, "2025-01-14": 2,
                                     "2025-01-18": 1, "2025-01-22": 1}, {}),
    ("M001", "MDL0001-SYH-M"): (3, {"2025-01-07": 2, "2025-01-08": 1, "2025-01-10": 1},
                                {"2025-01-10": 4}),
    ("M001", "MDL0001-SYH-L"): (6, {"2025-01-08": 1, "2025-01-16": 1, "2025-01-24": 1}, {}),
    ("M002", "MDL0001-SYH-S"): (5, {"2025-01-11": 1, "2025-01-19": 1}, {}),
    ("M002", "MDL0001-SYH-M"): (4, {"2025-01-15": 1}, {}),
}
_ONLINE = {"MDL0001-SYH-S": {"2025-01-08": 1},
           "MDL0001-SYH-M": {"2025-01-08": 1, "2025-01-15": 1},
           "MDL0001-SYH-L": {"2025-01-12": 1}}
# hayalet stok (M002 x L): gerçek v4'teki gibi tek pazartesi fotoğrafı, 1-3 adet,
# stoklu_gun 7
_HAYALET = {"2025-01-06": 2}
_FIYAT = 250.0


def _simule(ilk: int, satis: dict[str, int], repl: dict[str, int]):
    """Bir hücrenin günlük stoğunu yürür.

    Dönüş: {pazartesi: (fotoğraf adedi, stoklu_gun)}. Gün başı stoğu = önceki
    gün sonu + o gün varanlar; satış ancak gün başı stoğu kadar olabilir
    (kaçırılan talep veride görünmez). Fotoğraf pazartesi sabahıdır;
    stoklu_gun önceki 7 günde gün başı stoğu pozitif olan gün sayısıdır."""
    satis = {pd.Timestamp(g): n for g, n in satis.items()}
    repl = {pd.Timestamp(g): n for g, n in repl.items()}
    stok = 0
    acilista: dict[pd.Timestamp, int] = {}
    for g in pd.date_range(_BASLA, _BITIS, freq="D"):
        if g == _ILK_VARIS:
            stok += ilk
        stok += repl.get(g, 0)
        acilista[g] = stok
        n = satis.get(g, 0)
        assert n <= stok, f"{g.date()}: stoktan fazla satış"
        stok -= n
    foto = {}
    for p in PAZARTESILER:
        sg = sum(acilista[p - pd.Timedelta(days=k)] > 0 for k in range(1, 8))
        foto[p] = (acilista[p], sg)
    return foto


def _sirala(df: pd.DataFrame, anahtar: list[str]) -> pd.DataFrame:
    return df.sort_values(anahtar, kind="stable", ignore_index=True)


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    """Temel senaryonun v4 şemalı tabloları (bkz. modül açıklaması)."""
    magaza = doldur("magaza", [
        ("M001", "İstanbul AVM", "İstanbul", "Marmara", 41.0, 29.0, "AVM", 400, 1, 5000,
         "2015-01-01", None),
        ("M002", "İzmir Outlet", "İzmir", "Ege", 38.4, 27.1, "Outlet", 600, 1, 8000,
         "2016-01-01", None),
        ("ONL", "Online", "İstanbul", "Marmara", 41.0, 29.0, "Online", 0, 0, 0,
         "2012-01-01", None),
    ])
    urun = doldur("urun", [
        (u, "MDL0001-SYH", "MDL0001", "Basic Gömlek", f"Erkek Basic Gömlek Siyah {b}", "Lumoda",
         "Erkek", "Üst Giyim", "Gömlek", "Basic", "AW24", 1, "Siyah", "SYH", "Erkek Harf", b, sira,
         "pamuk", "regular", "düz", "klasik yaka", "yaka", "orta", 100.0, _FIYAT,
         "2024-11-04", None, "T01")
        for u, b, sira in zip(SKULAR, ("S", "M", "L"), (2, 3, 4))])

    satis_s, stok_s, sevk_s = [], [], []
    depo_cikis: dict[str, dict[pd.Timestamp, int]] = {u: {} for u in SKULAR}
    for (m, u), (ilk, sat, repl) in _HUCRELER.items():
        sevk_s.append((_ILK_CIKIS, _ILK_VARIS, "DEPO", m, u, ilk, "ilk_dagitim", "PKT01"))
        depo_cikis[u][_ILK_CIKIS] = depo_cikis[u].get(_ILK_CIKIS, 0) + ilk
        for gun, n in repl.items():
            cikis = pd.Timestamp(gun) - pd.Timedelta(days=1)
            sevk_s.append((cikis, gun, "DEPO", m, u, n, "replenishment", None))
            depo_cikis[u][cikis] = depo_cikis[u].get(cikis, 0) + n
        for gun, n in sat.items():
            satis_s.append((gun, m, u, n, n * _FIYAT, 0.0, None))
        for p, (adet, sg) in _simule(ilk, sat, repl).items():
            stok_s.append((p, m, u, adet, sg))
    # mükerrer satış: M001 x M, 01-07 satırı iki kez yazılı
    satis_s.append(("2025-01-07", "M001", "MDL0001-SYH-M", 2, 2 * _FIYAT, 0.0, None))
    for u, gunler in _ONLINE.items():
        for gun, n in gunler.items():
            satis_s.append((gun, "ONL", u, n, n * _FIYAT, 0.0, None))
    # hayalet stok: M002 x L, sevkiyatı ve satışı yok
    for gun, n in _HAYALET.items():
        stok_s.append((gun, "M002", "MDL0001-SYH-L", n, 7))

    depo_s = []
    for u in SKULAR:
        kalan = _DEPO_BASLANGIC
        for g in pd.date_range(_BASLA, _BITIS, freq="D"):
            kalan -= depo_cikis[u].get(g, 0)
            depo_s.append((g, u, kalan))

    t = {ad: bos(ad) for ad in _SEMA}
    t["magaza"], t["urun"] = magaza, urun
    t["satis"] = _sirala(doldur("satis", satis_s), ["tarih", "magaza_id", "urun_id"])
    t["stok"] = _sirala(doldur("stok", stok_s), ["tarih", "magaza_id", "urun_id"])
    t["depo_stok"] = doldur("depo_stok", depo_s)
    t["sevkiyat"] = _sirala(doldur("sevkiyat", sevk_s), ["tarih", "hedef", "urun_id"])
    return t


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    """Tablo sözlüğünü bellekte bir DuckDB'ye gerçek tablolar olarak yazar."""
    con = duckdb.connect(":memory:")
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    return con


@pytest.fixture
def oyuncak_con():
    con = oyuncak_baglan(oyuncak_tablolar())
    yield con
    con.close()
