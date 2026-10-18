"""Ortak fikstürler: v4 şemalı oyuncak dünya ve yayımlanan tabloların oyuncak karşılığı.

**Dünya** (`oyuncak_dunya`): `perakende_veri.v4.dunya.Dunya`nın açık alanlarını taşıyan
küçük bir nesne. Gizli alanlar (`lam`, `gizli_*`, `esneklik*`, `ilk_siparisler`, `sapma_*`)
okunursa test patlar (`harita_kur` ve politikalar bunlara dokunmamalı).

    mağazalar   M1 İstanbul (AVM), M2 Ankara (Cadde), M3 Bursa (AVM), M4 İzmir (Cadde),
                MO İstanbul (Outlet tipi), ONL (online, son satır)
    option'lar  6, öznitelikleri farklı (SKU = option × beden; aksesuar tek beden):

        0 GA  SS23 Collection d1  Kadın Üst Giyim   Kadın Harf   (5 beden)
        1 GB  SS24 Collection d2  Erkek Alt Giyim   Erkek Numara (5)
        2 A   SS25 Collection d1  Erkek Üst Giyim   Erkek Harf   (5)  <- izlenen option
        3 B   SS25 Collection d2  Kadın Dış Giyim   Kadın Harf   (5)  lansmanı pencere sonrası
        4 C   SS25 Outlet    d1   Unisex Üst Giyim  Unisex Harf  (5)
        5 X   SS25 Collection d3  Aksesuar          Standart     (1)

    hücreler    fiziksel mağaza × Collection SKU'ları, MO × Outlet SKU'ları, ONL × bütün SKU'lar
    paketler    5 bedenli setlerde 1-2-2-1-1 (= 7), Standart tek beden (6)
    takvim      2025-02-03 (pazartesi, gün 0) – 2025-02-23, 21 gün

**Tablolar** (`oyuncak_tablolar`): `A-1` SKU'sunun (`OPT-A-1`) elle izlenebilir iki haftası.
Lansman G0 = 2025-02-10 (pazartesi, dünya günü 7); g0…g13 = dünya günleri 7…20; pazartesi
fotoğrafları g0, g7, g14. Yalnız bu SKU'nun hücrelerinde akış vardır:

    (M1, A-1)   g0'da 6 gelir; satış g0:2 g1:2 g2:2 g5:1 g6:1 g8:1; g5'te 4 gelir (replenishment);
                g7'de 1 iade (negatif satır, günün sonunda rafa döner); g1'in satırı mükerrer.
                satış öncesi raf g0…g13: 6 4 2 0 0 4 3 2(+1 iade gün sonu) 3 2 2 2 2 2
                stoklu: T T T F F T T T T T T T T T      (g2 tükenen: brüt >= raf, yine stoklu)
    (M2, A-1)   g0'da 3 gelir, g0 g1 g2'de 1'er satılır; sonra boş
                stoklu: T T T F F F F F F F F F F F
    (ONL, A-1)  depo sabah stoğu g0…g14: 6 5 4 3 2 1 0 0 …; g0…g5'te 1'er online satış
                stoklu: T T T T T T F F F F F F F F

Pazartesi fotoğrafları akışlardan `_foto` ile hesaplanır (stok korunumu tutarlı).
"""

from types import SimpleNamespace

import duckdb
import numpy as np
import pandas as pd
import pytest

G0 = pd.Timestamp("2025-02-10")      # A seçeneğinin lansmanı, pazartesi
DUNYA_BASI = pd.Timestamp("2025-02-03")   # oyuncak dünyanın 0. günü (pazartesi)
GUN_G0 = (G0 - DUNYA_BASI).days           # g0'ın dünya günü (7)


def gun(n: int) -> pd.Timestamp:
    return G0 + pd.Timedelta(days=n)


# ---------------------------------------------------------------------------
# Dünya
# ---------------------------------------------------------------------------

_MAGAZALAR = [   # magaza_id, ad, sehir, bolge, tip
    ("M1", "Bir", "İstanbul", "Marmara", "AVM"),
    ("M2", "İki", "Ankara", "İç Anadolu", "Cadde"),
    ("M3", "Üç", "Bursa", "Marmara", "AVM"),
    ("M4", "Dört", "İzmir", "Ege", "Cadde"),
    ("MO", "Outlet", "İstanbul", "Marmara", "Outlet"),
    ("ONL", "Online", "Gebze", "Marmara", "Online"),
]
_OPTIONLAR = [   # option_id, sezon, line, dalga, ust_kategori, cinsiyet, beden_seti, beden sayısı
    ("OPT-GA", "SS23", "Collection", 1, "Üst Giyim", "Kadın", "Kadın Harf", 5),
    ("OPT-GB", "SS24", "Collection", 2, "Alt Giyim", "Erkek", "Erkek Numara", 5),
    ("OPT-A", "SS25", "Collection", 1, "Üst Giyim", "Erkek", "Erkek Harf", 5),
    ("OPT-B", "SS25", "Collection", 2, "Dış Giyim", "Kadın", "Kadın Harf", 5),
    ("OPT-C", "SS25", "Outlet", 1, "Üst Giyim", "Unisex", "Unisex Harf", 5),
    ("OPT-X", "SS25", "Collection", 3, "Aksesuar", "Unisex", "Standart", 1),
]
_SEZON = [   # sezon, dalga, lansman, indirim_baslangic, cikis (yayımlanan v4'ten)
    ("SS23", 1, "2023-02-13", "2023-07-03", "2023-08-28"),
    ("SS23", 2, "2023-03-20", "2023-07-03", "2023-08-28"),
    ("SS23", 3, "2023-04-24", "2023-07-03", "2023-08-28"),
    ("SS24", 1, "2024-02-12", "2024-07-01", "2024-08-26"),
    ("SS24", 2, "2024-03-18", "2024-07-01", "2024-08-26"),
    ("SS24", 3, "2024-04-22", "2024-07-01", "2024-08-26"),
    ("SS25", 1, "2025-02-10", "2025-06-30", "2025-08-25"),
    ("SS25", 2, "2025-03-17", "2025-06-30", "2025-08-25"),
    ("SS25", 3, "2025-04-21", "2025-06-30", "2025-08-25"),
]
_BEDEN_PAYI = np.array([1, 2, 2, 1, 1]) / 7


class _Gizli:
    """Gizli alan: okunursa test patlar."""

    def __init__(self, ad: str):
        self.ad = ad

    def __get__(self, nesne, tur=None):
        raise AssertionError(f"gizli alan okundu: {self.ad}")


class OyuncakDunya(SimpleNamespace):
    lam = _Gizli("lam")
    gizli_magaza = _Gizli("gizli_magaza")
    gizli_tedarikci = _Gizli("gizli_tedarikci")
    gizli_talep = _Gizli("gizli_talep")
    esneklik = _Gizli("esneklik")
    esneklik_hucre = _Gizli("esneklik_hucre")
    ilk_siparisler = _Gizli("ilk_siparisler")
    sapma_rpt = _Gizli("sapma_rpt")
    sapma_surekli = _Gizli("sapma_surekli")


def oyuncak_dunya() -> OyuncakDunya:
    magazalar = pd.DataFrame(
        [(m, ad, sehir, bolge, tip) for m, ad, sehir, bolge, tip in _MAGAZALAR],
        columns=["magaza_id", "ad", "sehir", "bolge", "tip"])
    magazalar["acilis_tarihi"] = pd.Timestamp("2015-01-01")
    magazalar["kapanis_tarihi"] = pd.NaT

    optionlar = pd.DataFrame(
        [(o, sz, ln, d, uk, c, bs) for o, sz, ln, d, uk, c, bs, _ in _OPTIONLAR],
        columns=["option_id", "sezon_kodu", "line", "dalga", "ust_kategori", "cinsiyet", "beden_seti"])
    optionlar["dalga"] = optionlar["dalga"].astype("Int64")
    lansman = {(r[0], r[1]): pd.Timestamp(r[2]) for r in _SEZON}
    cikis = {r[0]: pd.Timestamp(r[4]) for r in _SEZON}
    optionlar["lansman_tarihi"] = [lansman[(sz, int(d))] for sz, d in
                                   zip(optionlar["sezon_kodu"], optionlar["dalga"])]
    optionlar["cikis_tarihi"] = [cikis[sz] for sz in optionlar["sezon_kodu"]]

    sku_satir, sku_option, sku_payi = [], [], []
    for o, (oid, *_rest, n) in enumerate(_OPTIONLAR):
        for b in range(1, n + 1):
            sku_satir.append((f"{oid}-{b}", oid, b))
            sku_option.append(o)
            sku_payi.append(_BEDEN_PAYI[b - 1] if n == 5 else 1.0)
    urunler = pd.DataFrame(sku_satir, columns=["urun_id", "option_id", "beden_sira"])
    urunler = urunler.merge(optionlar[["option_id", "line", "sezon_kodu", "dalga", "beden_seti",
                                       "lansman_tarihi", "cikis_tarihi"]], on="option_id")

    paketler = pd.DataFrame(
        [(f"PKT{i + 1:02d}", bs, b + 1, a)
         for i, bs in enumerate(["Erkek Harf", "Erkek Numara", "Kadın Harf", "Unisex Harf"])
         for b, a in enumerate([1, 2, 2, 1, 1])] + [("PKT05", "Standart", 1, 6)],
        columns=["paket_id", "beden_seti", "beden_sira", "adet"])

    sezon = pd.DataFrame(_SEZON, columns=["sezon_kodu", "dalga", "lansman_tarihi",
                                          "indirim_baslangic", "cikis_tarihi"])
    for s in ("lansman_tarihi", "indirim_baslangic", "cikis_tarihi"):
        sezon[s] = pd.to_datetime(sezon[s])

    tarih = pd.date_range(DUNYA_BASI, periods=21, freq="D")
    takvim = pd.DataFrame({"tarih": tarih, "pazartesi_mi": tarih.weekday == 0})

    # hücreler: fiziksel mağaza × Collection/Outlet-dışı SKU; MO × Outlet SKU; ONL × hepsi
    onl_m = len(_MAGAZALAR) - 1
    hm, hs = [], []
    for m, (_, _, _, _, tip) in enumerate(_MAGAZALAR):
        for s, o in enumerate(sku_option):
            outlet_option = _OPTIONLAR[o][2] == "Outlet"
            if tip == "Online" or (tip == "Outlet") == outlet_option:
                hm.append(m)
                hs.append(s)
    hm, hs = np.array(hm), np.array(hs)
    sku_option = np.array(sku_option)
    return OyuncakDunya(
        magazalar=magazalar, urunler=urunler, optionlar=optionlar, paketler=paketler,
        sezon=sezon, takvim=takvim, magaza_olay=pd.DataFrame(columns=["magaza_id", "olay"]),
        hucre_magaza=hm, hucre_sku=hs, hucre_option=sku_option[hs],
        hucre_online=hm == onl_m,
        hucre_outlet_akisi=np.array([_MAGAZALAR[m][4] == "Outlet" for m in hm]),
        sku_option=sku_option, sku_beden_payi=np.array(sku_payi), gun_sayisi=len(takvim))


@pytest.fixture
def dunya() -> OyuncakDunya:
    return oyuncak_dunya()


# ---------------------------------------------------------------------------
# Yayımlanan tabloların oyuncak karşılığı
# ---------------------------------------------------------------------------

_S, _T = "string", "datetime64[ns]"
# Gerçek v4 şeması (ortak `stok` modülünün okuduğu tablolar ve sütunlar)
_SEMA = {
    "magaza": {"magaza_id": _S, "ad": _S, "sehir": _S, "bolge": _S, "enlem": "float64",
               "boylam": "float64", "tip": _S, "metrekare": "int64", "kat_sayisi": "int64",
               "kapasite": "int64", "acilis_tarihi": _T, "kapanis_tarihi": _T},
    "magaza_olay": {"magaza_id": _S, "olay": _S, "karar_tarihi": _T, "olay_tarihi": _T,
                    "bitis_tarihi": _T},
    "urun": {"urun_id": _S, "option_id": _S, "line": _S, "sezon_kodu": _S, "dalga": "int64",
             "lansman_tarihi": _T, "cikis_tarihi": _T, "tedarikci_id": _S},
    "satis": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "tutar": "float64",
              "indirim_tutari": "float64", "kampanya_id": _S},
    "stok": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "stoklu_gun": "int8"},
    "depo_stok": {"tarih": _T, "urun_id": _S, "adet": "int32"},
    "sevkiyat": {"tarih": _T, "varis_tarihi": _T, "kaynak": _S, "hedef": _S, "urun_id": _S,
                 "adet": "int32", "tip": _S, "paket_id": _S},
    "siparis": {"siparis_id": _S, "tip": _S, "option_id": _S, "urun_id": _S, "tedarikci_id": _S,
                "siparis_tarihi": _T, "planlanan_teslim": _T, "gerceklesen_teslim": _T,
                "adet": "int32"},
}


def _doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=list(_SEMA[tablo]))
    for s, t in _SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


IZLENEN = "OPT-A-1"
# hücre -> {varış günü: adet}
_VARIS = {("M1", IZLENEN): {0: 6, 5: 4}, ("M2", IZLENEN): {0: 3}}
_BRUT = {("M1", IZLENEN): {0: 2, 1: 2, 2: 2, 5: 1, 6: 1, 8: 1},
         ("M2", IZLENEN): {0: 1, 1: 1, 2: 1}}
_IADE = {("M1", IZLENEN): {7: 1}}      # günün sonunda rafa döner
_ONLINE = {i: 1 for i in range(6)}     # online satış g0…g5
_DEPO = [6, 5, 4, 3, 2, 1] + [0] * 9   # depo sabah stoğu g0…g14


def _foto(varis: dict[int, int], brut: dict[int, int], iade: dict[int, int]) -> dict[int, tuple[int, int]]:
    """{pazartesi günü: (fotoğraf adedi, stoklu_gun)}. Fotoğraf pazartesi sabahı, günün
    hareketlerinden önce çekilir (= önceki gün sonu; g0'da mağaza boş); iade günün
    sonunda rafa döner."""
    son, acilis, gunsonu = 0, {}, {}
    for g in range(14):
        acilis[g] = son + varis.get(g, 0)
        son = acilis[g] - brut.get(g, 0) + iade.get(g, 0)
        gunsonu[g] = son
    return {0: (0, 0),
            7: (gunsonu[6], sum(acilis[g] > 0 for g in range(7))),
            14: (gunsonu[13], sum(acilis[g] > 0 for g in range(7, 14)))}


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    w = oyuncak_dunya()
    magaza = _doldur("magaza", [
        (m, ad, sehir, bolge, 41.0, 29.0, tip, 400, 1, 5000, "2015-01-01", None)
        for m, ad, sehir, bolge, tip in _MAGAZALAR])
    urun = _doldur("urun", [
        (r.urun_id, r.option_id, r.line, r.sezon_kodu, int(r.dalga), r.lansman_tarihi,
         r.cikis_tarihi, "T01") for r in w.urunler.itertuples()])
    sevkiyat = [(gun(-2), gun(0), "DEPO", m, u, v[0], "ilk_dagitim", f"PKT-{u}")
                for (m, u), v in _VARIS.items()]
    sevkiyat += [(gun(4), gun(5), "DEPO", "M1", IZLENEN, 4, "replenishment", None)]
    satis = []
    for (m, u), br in _BRUT.items():
        satis += [(gun(i), m, u, n, 100.0 * n, 0.0, None) for i, n in br.items()]
    for (m, u), ia in _IADE.items():
        satis += [(gun(i), m, u, -n, -100.0 * n, 0.0, None) for i, n in ia.items()]
    satis += [(gun(i), "ONL", IZLENEN, n, 100.0 * n, 0.0, None) for i, n in _ONLINE.items()]
    satis.append((gun(1), "M1", IZLENEN, 2, 200.0, 0.0, None))   # mükerrer: g1'in ikinci kopyası
    stok = []
    for (m, u), varis in _VARIS.items():
        for p, (adet, sg) in _foto(varis, _BRUT[(m, u)], _IADE.get((m, u), {})).items():
            stok.append((gun(p), m, u, adet, sg))
    depo = [(gun(i), IZLENEN, a) for i, a in enumerate(_DEPO)]

    t = {ad: _doldur(ad, []) for ad in _SEMA}
    t["magaza"], t["urun"], t["sevkiyat"] = magaza, urun, _doldur("sevkiyat", sevkiyat)
    t["satis"] = _doldur("satis", satis).sort_values(["tarih", "magaza_id", "urun_id"], ignore_index=True)
    t["stok"] = _doldur("stok", stok).sort_values(["tarih", "magaza_id", "urun_id"], ignore_index=True)
    t["depo_stok"] = _doldur("depo_stok", depo)
    return t


@pytest.fixture
def tablolar() -> dict[str, pd.DataFrame]:
    return oyuncak_tablolar()


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    return con
