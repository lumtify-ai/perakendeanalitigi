"""Ortak fikstürler ve geçici v2 atlama listesi.

`GECICI_V2`: v4'e henüz taşınmamış modüllerin eski (v2) testleri. Her biri
dosyasının başında `gecici_atla(__name__)` çağırır; modül listeden çıkarılınca
atlama kalkar. Liste yalnız küçülür; son görev (Görev 16) boş olduğunu sınar.

`oyuncak_tablolar` / `oyuncak_con`: v4 şemalı oyuncak dünya (bellekte DuckDB).
Lansman 2025-02-10 (pazartesi, g0); 14 gün (g0…g13), pazartesi fotoğrafları
g0, g7, g14. İki ürün (A-S, A-M, tek option); mağazalar:

    M1  İstanbul (Marmara)   A-S ve A-M her gün satar, stoğu bol
    M2  Ankara (İç Anadolu)  A-S'nin 3 adedi ilk üç günde satılır, sonra boş;
                             A-M stoklu ama hiç satmaz
    M3  Bursa (Marmara)      İstanbul DEĞİL (Marmara bölgesi ≠ İstanbul); hareketsiz
    ONL online               A-S her gün 1; A-M g5'te 2; A-M'nin depo stoğu g10'da biter

Mükerrer satış (M1 A-S g3 ikinci kopya) ve iade (M1 A-M g4, -1) bilerek vardır.
Pazartesi fotoğrafları `_foto` ile akışlardan hesaplanır; stok korunumu tutarlıdır.
"""

import duckdb
import pandas as pd
import pytest

# Henüz v4'e taşınmamış v2 testleri: modül adı -> taşınacağı görev
GECICI_V2: dict[str, str] = {
    "test_tahmin": "Görev 7",
    "test_kalibrasyon": "Görev 9",
    "test_rapor": "Görev 12",
}
GECICI_V2_ILK = frozenset(GECICI_V2)  # muafiyet yalnız küçülür


def gecici_atla(modul_adi: str) -> None:
    """Modül `GECICI_V2`deyse (eski v2 testi) modül düzeyinde atlar. Eski testin
    içe aktardığı modüller silinmiş olabilir; bu yüzden içe aktarmadan ÖNCE çağrılır."""
    ad = modul_adi.rsplit(".", 1)[-1]
    if ad in GECICI_V2:
        pytest.skip(f"v2 testi; v4'e taşınması: {GECICI_V2[ad]}", allow_module_level=True)


G0 = pd.Timestamp("2025-02-10")  # lansman, pazartesi


def gun(n: int) -> pd.Timestamp:
    return G0 + pd.Timedelta(days=n)


_S, _T = "string", "datetime64[ns]"
# Gerçek v4 şeması (yalnız vakanın okuduğu tablolar ve sütunlar)
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


URUNLER = ("A-S", "A-M")
# hücre -> {varış günü: adet} (ilk dağıtım g0; sonrakiler replenishment / outlet akışı)
_VARIS = {
    ("M1", "A-S"): {0: 60, 8: 12},
    ("M1", "A-M"): {0: 30, 1: 7},
    ("M2", "A-S"): {0: 3},
    ("M2", "A-M"): {0: 10, 9: 4},
}
_BRUT = {  # hücre -> {gün: pozitif satış satırı}
    ("M1", "A-S"): {i: 2 for i in range(14)},
    ("M1", "A-M"): {i: 1 for i in range(14)},
    ("M2", "A-S"): {0: 1, 1: 1, 2: 1},
    ("M2", "A-M"): {},
}
_IADE = {("M1", "A-M"): {4: 1}}  # g4'te 1 adet iade (negatif satır)
_ONLINE = {"A-S": {i: 1 for i in range(14)}, "A-M": {5: 2}}


def _foto(varis: dict[int, int], brut: dict[int, int], iade: dict[int, int]) -> dict[int, tuple[int, int]]:
    """{pazartesi günü: (fotoğraf adedi, stoklu_gun)}. Fotoğraf pazartesi sabahı, günün
    hareketlerinden önce çekilir (= önceki gün sonu stoğu; g0'da mağaza boş); iade günün
    sonunda rafa döner. Stoklu gün: açılış stoğu (varıştan sonra) > 0 olan gün."""
    son, acilis, gunsonu = 0, {}, {}
    for g in range(14):
        acilis[g] = son + varis.get(g, 0)
        son = acilis[g] - brut.get(g, 0) + iade.get(g, 0)
        gunsonu[g] = son
    return {0: (0, 0),
            7: (gunsonu[6], sum(acilis[g] > 0 for g in range(7))),
            14: (gunsonu[13], sum(acilis[g] > 0 for g in range(7, 14)))}


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    magaza = _doldur("magaza", [
        ("M1", "Bir", "İstanbul", "Marmara", 41.0, 29.0, "AVM", 400, 1, 5000, "2015-01-01", None),
        ("M2", "İki", "Ankara", "İç Anadolu", 39.9, 32.8, "Cadde", 300, 1, 4000, "2016-01-01", None),
        ("M3", "Üç", "Bursa", "Marmara", 40.2, 29.0, "AVM", 350, 1, 4500, "2017-01-01", None),
        ("ONL", "Online", "Gebze", "Marmara", 40.8, 29.4, "Online", 0, 0, 0, "2012-01-01", None),
    ])
    urun = _doldur("urun", [(u, "OPT-A", "Collection", "SS25", 1, G0, gun(28), "T01") for u in URUNLER])
    sevkiyat = [(gun(-2), gun(0), "DEPO", m, u, v[0], "ilk_dagitim", f"PKT-{u}")
                for (m, u), v in _VARIS.items()]
    sevkiyat += [
        # replenishment pazartesileri: g0 (hafta 0, 7 adet), g7 (hafta 1, 12 adet), g14 (pencere dışı)
        (gun(0), gun(1), "DEPO", "M1", "A-M", 7, "replenishment", None),
        (gun(7), gun(8), "DEPO", "M1", "A-S", 12, "replenishment", None),
        (gun(14), gun(16), "DEPO", "M1", "A-S", 9, "replenishment", None),
        # replenishment sayılmayan
        (gun(7), gun(9), "DEPO", "M2", "A-M", 4, "outlet_akisi", None),
    ]
    satis = []
    for (m, u), br in _BRUT.items():
        satis += [(gun(i), m, u, n, 100.0 * n, 0.0, None) for i, n in br.items()]
    for (m, u), ia in _IADE.items():
        satis += [(gun(i), m, u, -n, -100.0 * n, 0.0, None) for i, n in ia.items()]
    for u, d in _ONLINE.items():
        satis += [(gun(i), "ONL", u, n, 100.0 * n, 0.0, None) for i, n in d.items()]
    satis.append((gun(3), "M1", "A-S", 2, 200.0, 0.0, None))  # mükerrer: g3'ün ikinci kopyası
    stok = []
    for (m, u), varis in _VARIS.items():
        for p, (adet, sg) in _foto(varis, _BRUT[(m, u)], _IADE.get((m, u), {})).items():
            stok.append((gun(p), m, u, adet, sg))
    depo = []
    for i in range(15):
        depo.append((gun(i), "A-S", 100 - i))
        depo.append((gun(i), "A-M", 50 if i < 10 else 0))

    t = {ad: _doldur(ad, []) for ad in _SEMA}
    t["magaza"], t["urun"], t["sevkiyat"] = magaza, urun, _doldur("sevkiyat", sevkiyat)
    t["satis"] = _doldur("satis", satis).sort_values(["tarih", "magaza_id", "urun_id"], ignore_index=True)
    t["stok"] = _doldur("stok", stok).sort_values(["tarih", "magaza_id", "urun_id"], ignore_index=True)
    t["depo_stok"] = _doldur("depo_stok", depo)
    return t


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
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
