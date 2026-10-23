"""Ortak fikstürler: v4 şemalı oyuncak tablolar ve sahte `Gorunum` üreticisi.

**Gün ekseni.** Dünyanın gün indisi 0 = 2022-07-04 (ısınma başı, pazartesi; `takvim.gun_indisi`).
Oyuncak `optionlar` bu eksendedir (`GUN_SIFIRI`).

**Mağazalar** (6 + ONL):

    S1 İstanbul 1   Marmara        S4 İzmir 1     Ege
    S2 İstanbul 2   Marmara        S5 Antalya 1   Akdeniz
    S3 Ankara 1     İç Anadolu     S6 Trabzon 1   Karadeniz     ONL  (Marmara, online)

**Option'lar** (13): iki Collection sezonu (AW24, SS25) × 6 option × 3 beden ve 1 Basic.
Her sezonda dalga 1 (a, b, c), dalga 2 (d), dalga 3 (e, f). Dönem: AW24 lansman 2024-08-19 / 09-23 /
10-28, indirim 2025-01-02, çıkış 2025-02-24; SS25 lansman 2025-02-10 / 03-17 / 04-21, indirim
2025-06-30, çıkış 2025-08-25. Her sezonun `b` option'ı erken biter (lansmandan 6 hafta satar, sonra
stok 0), `c` option'ı hiç satmaz; öteki dört option çıkışa dek haftada 2 adet/SKU/mağaza satar.

**Satış** her pazartesi (mağaza başına SKU başına); 2025-01-13 haftasında `KMP1` kampanyası yalnız
Marmara bölgesi mağazalarındadır (S1, S2, ONL): kapsamlı mağazada satırlar kampanya kimliği ve
indirim tutarı taşır, kapsamsız mağazada taşımaz. **Fiyat**: normal ve online hat, her option için
haftalık; indirim gününden sonra %30.
"""

import duckdb
import numpy as np
import pandas as pd
import pytest
from perakende_veri.v4.motor.durum import Gorunum, salt_okunur

GUN_SIFIRI = pd.Timestamp("2022-07-04")

_S, _T = "string", "datetime64[ns]"

_MAGAZALAR = [   # magaza_id, ad, sehir, bolge, tip
    ("S1", "İstanbul 1", "İstanbul", "Marmara", "AVM"),
    ("S2", "İstanbul 2", "İstanbul", "Marmara", "Cadde"),
    ("S3", "Ankara 1", "Ankara", "İç Anadolu", "AVM"),
    ("S4", "İzmir 1", "İzmir", "Ege", "AVM"),
    ("S5", "Antalya 1", "Antalya", "Akdeniz", "AVM"),
    ("S6", "Trabzon 1", "Trabzon", "Karadeniz", "Cadde"),
    ("ONL", "Online", "İstanbul", "Marmara", "Online"),
]
MAGAZALAR = [m[0] for m in _MAGAZALAR]
BEDENLER = ("S", "M", "L")

SEZON_DONEMI = {   # sezon -> (indirim, çıkış)
    "AW24": ("2025-01-02", "2025-02-24"),
    "SS25": ("2025-06-30", "2025-08-25"),
}
_LANSMAN = {   # sezon -> dalga başına lansman
    "AW24": {1: "2024-08-19", 2: "2024-09-23", 3: "2024-10-28"},
    "SS25": {1: "2025-02-10", 2: "2025-03-17", 3: "2025-04-21"},
}
_DALGA = {"a": 1, "b": 1, "c": 1, "d": 2, "e": 3, "f": 3}
ERKEN_BITEN, SATMAYAN = "b", "c"
SATIS_BITIS = pd.Timestamp("2025-07-07")   # son satış pazartesisi
KAMPANYA_HAFTASI = pd.Timestamp("2025-01-13")
KAMPANYA_BOLGE = "Marmara"
SIPARIS_TARIHLERI = ("2025-01-06", "2025-03-03")


def _optionlar() -> list[tuple]:
    """option_id, sezon, line, dalga, lansman, ust, alt, liste_fiyati (sezon sırası AW24, SS25)."""
    satir = []
    for sezon in ("AW24", "SS25"):
        for harf, dalga in _DALGA.items():
            satir.append((f"{sezon}-{harf}", sezon, "Collection", dalga, _LANSMAN[sezon][dalga],
                          "Üst Giyim" if harf in "abc" else "Alt Giyim",
                          "Tişört" if harf in "abc" else "Pantolon", 400.0 + 50 * len(satir)))
    satir.append(("BAS-1", "DEVAMLI", "Basic", 0, "2022-07-04", "Üst Giyim", "Tişört", 300.0))
    return satir


def gun_indisi(tarih) -> int:
    return int((pd.Timestamp(tarih) - GUN_SIFIRI).days)


def oyuncak_optionlar() -> pd.DataFrame:
    """Dünyanın `optionlar` biçimi (oyuncak): gün sütunları 2022-07-04'e göre; sezonluk olmayan
    option'ın indirim ve çıkış günü 10**6."""
    satir = []
    for o, sezon, line, dalga, lansman, ust, alt, fiyat in _optionlar():
        sezonluk = sezon != "DEVAMLI"
        indirim, cikis = SEZON_DONEMI.get(sezon, (None, None))
        satir.append({
            "option_id": o, "sezon_kodu": sezon, "line": line, "dalga": dalga,
            "lansman_gun": gun_indisi(lansman),
            "indirim_gun": gun_indisi(indirim) if sezonluk else 10**6,
            "cikis_gun": gun_indisi(cikis) if sezonluk else 10**6,
            "sezonluk": sezonluk, "ust_kategori": ust, "alt_kategori": alt, "liste_fiyati": fiyat,
        })
    o = pd.DataFrame(satir)
    o["lansman_gun"] = o["lansman_gun"].astype("int64")
    return o


SEMA = {   # gerçek v4 şemasının oyuncak tablolarda kullanılan sütunları
    "magaza": {"magaza_id": _S, "ad": _S, "sehir": _S, "bolge": _S, "tip": _S},
    "urun": {"urun_id": _S, "option_id": _S, "line": _S, "sezon_kodu": _S, "dalga": "int64",
             "ust_kategori": _S, "alt_kategori": _S, "beden": _S, "beden_sira": "int64",
             "liste_fiyati": "float64", "lansman_tarihi": _T, "cikis_tarihi": _T},
    "satis": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "tutar": "float64",
              "indirim_tutari": "float64", "kampanya_id": _S},
    "stok": {"tarih": _T, "magaza_id": _S, "urun_id": _S, "adet": "int32", "stoklu_gun": "int8"},
    "depo_stok": {"tarih": _T, "urun_id": _S, "adet": "int32"},
    "fiyat": {"hafta_baslangic": _T, "option_id": _S, "hat": _S, "indirim_orani": "float64"},
    "kampanya": {"kampanya_id": _S, "tip": _S, "baslangic": _T, "bitis": _T,
                 "kapsam_ust_kategori": _S, "kapsam_line": _S, "kapsam_bolge": _S, "oran": "float64"},
    "sezon": {"sezon_kodu": _S, "dalga": "int64", "lansman_tarihi": _T, "indirim_baslangic": _T,
              "cikis_tarihi": _T},
    "takvim": {"tarih": _T, "hafta": "int64", "ay": "int32", "yil": "int32", "sezon": _S,
               "sezon_kodu": _S, "tatil_mi": "bool", "indirim_donemi_mi": "bool"},
    "siparis": {"siparis_id": _S, "tip": _S, "option_id": _S, "urun_id": _S, "tedarikci_id": _S,
                "siparis_tarihi": _T, "planlanan_teslim": _T, "gerceklesen_teslim": _T,
                "adet": "int32"},
}


def doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=list(SEMA[tablo]))
    for s, t in SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


def urun_id(option_id: str, beden: str) -> str:
    return f"{option_id}-{beden}"


def _urunler() -> list[tuple]:
    return [(urun_id(o, b), o, line, sezon, dalga, ust, alt, b, i + 1, fiyat, lansman,
             None if sezon == "DEVAMLI" else SEZON_DONEMI[sezon][1])
            for o, sezon, line, dalga, lansman, ust, alt, fiyat in _optionlar()
            for i, b in enumerate(BEDENLER)]


def _adet(option_id: str, hafta: int) -> int:
    """Lansmandan `hafta` hafta sonra SKU başına mağaza satışı (0 = satış satırı yok)."""
    harf = option_id.rsplit("-", 1)[1]
    if harf == SATMAYAN:
        return 0
    if harf == ERKEN_BITEN:
        return 3 if hafta < 6 else 0
    return 2


def _satis() -> list[tuple]:
    satir = []
    for o, sezon, line, dalga, lansman, *_r in _optionlar():
        if sezon == "DEVAMLI":
            lansman, cikis = "2024-08-19", "2025-07-07"
        else:
            cikis = SEZON_DONEMI[sezon][1]
        for h, t in enumerate(pd.date_range(lansman, min(pd.Timestamp(cikis), SATIS_BITIS), freq="7D")):
            a = _adet(o, h) if sezon != "DEVAMLI" else 2
            if a == 0:
                continue
            for m, _ad, _sh, bolge, _tip in _MAGAZALAR:
                kampanyali = t == KAMPANYA_HAFTASI and bolge == KAMPANYA_BOLGE
                for b in BEDENLER:
                    satir.append((t, m, urun_id(o, b), a, 100.0 * a * (0.8 if kampanyali else 1.0),
                                  20.0 * a if kampanyali else 0.0, "KMP1" if kampanyali else None))
    return satir


def _stok() -> list[tuple]:
    satir = []
    for t in pd.date_range("2024-08-19", "2025-07-07", freq="7D"):
        for o, sezon, line, dalga, lansman, *_r in _optionlar():
            if sezon != "DEVAMLI" and not pd.Timestamp(lansman) <= t <= pd.Timestamp(SEZON_DONEMI[sezon][1]):
                continue
            h = (t - pd.Timestamp(lansman)).days // 7 if sezon != "DEVAMLI" else 0
            kalan = 0 if _adet(o, h) == 0 and o.endswith(ERKEN_BITEN) else 10
            for m, *_x in _MAGAZALAR:
                satir += [(t, m, urun_id(o, b), kalan, 7 if kalan else 0) for b in BEDENLER]
    return satir


def _depo_stok() -> list[tuple]:
    return [(t, urun_id(o, b), 400) for t in pd.date_range("2024-08-19", "2025-07-07", freq="28D")
            for o, *_r in _optionlar() for b in BEDENLER]


def _fiyat() -> list[tuple]:
    satir = []
    for t in pd.date_range("2024-08-19", "2025-07-07", freq="7D"):
        for o, sezon, *_r in _optionlar():
            oran = 0.3 if sezon != "DEVAMLI" and t >= pd.Timestamp(SEZON_DONEMI[sezon][0]) else 0.0
            satir += [(t, o, hat, oran) for hat in ("normal", "online")]
    return satir


def _takvim() -> list[tuple]:
    satir = []
    for d in pd.date_range("2023-01-01", "2025-12-31"):
        kod = (f"SS{d.year % 100}" if 2 <= d.month <= 7 else
               f"AW{d.year % 100}" if d.month >= 8 else f"AW{(d.year - 1) % 100}")
        satir.append((d, d.isocalendar().week, d.month, d.year,
                      "İlkbahar/Yaz" if kod.startswith("SS") else "Sonbahar/Kış", kod, False, False))
    return satir


def _sezon() -> list[tuple]:
    return [(s, d, _LANSMAN[s][d], SEZON_DONEMI[s][0], SEZON_DONEMI[s][1])
            for s in ("AW24", "SS25") for d in (1, 2, 3)]


def _siparis() -> list[tuple]:
    return [(f"SP{i}", "rpt", "AW24-a", "AW24-a-M", "T1", t, "2025-01-20", "2025-03-10", 100)
            for i, t in enumerate(SIPARIS_TARIHLERI)]


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    return {
        "magaza": doldur("magaza", _MAGAZALAR),
        "urun": doldur("urun", _urunler()),
        "satis": doldur("satis", _satis()),
        "stok": doldur("stok", _stok()),
        "depo_stok": doldur("depo_stok", _depo_stok()),
        "fiyat": doldur("fiyat", _fiyat()),
        "kampanya": doldur("kampanya", [("KMP1", "kategori", "2025-01-13", "2025-01-19", "", "",
                                         KAMPANYA_BOLGE, 0.2)]),
        "sezon": doldur("sezon", _sezon()),
        "takvim": doldur("takvim", _takvim()),
        "siparis": doldur("siparis", _siparis()),
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


@pytest.fixture
def optionlar() -> pd.DataFrame:
    return oyuncak_optionlar()


# ---------------------------------------------------------------------------
# Sahte Gorunum
# ---------------------------------------------------------------------------


class AcikDunya:
    """`Gorunum.dunya` yerine: yalnız verilen açık alanlar vardır. Başka bir alana (`lam`,
    `esneklik`, `gizli_*` …) erişim `AttributeError` verir; karar kodu gizli gerçeğe sahte
    görünümle de ulaşamaz."""

    def __init__(self, **alanlar):
        self.__dict__.update(alanlar)


def gorunum(gun: int, stok, depo, satis_gecmisi, stoklu_gecmisi, fiyat_orani, *,
            dunya=None, yolda=None, gonderilen_option=None, satilan_option=None,
            satilan_option_magaza=None, rpt_sayisi=None, ilk_dagitim_gun=None, acik_magaza=None,
            kapanacak=None, acik_siparisler=(), operasyon_tohumu: int = 0, magaza_sayisi: int = 1,
            **acik_alanlar) -> Gorunum:
    """Gerçek `perakende_veri.v4.motor.durum.Gorunum` alanlarıyla sahte bir karar anı.

    Zorunlu: `stok` [C] (hücre başına raf), `depo` [S], `satis_gecmisi` [gun, C] ve `stoklu_gecmisi`
    [gun, C] (en az `gun` satır), `fiyat_orani` [O, 3] (normal / outlet / online). Verilmeyen
    alanlar boş/sıfır varsayılan alır (`satis_28` geçmişin son 28 gününden); `magaza_sayisi` yalnız
    `acik_magaza` / `kapanacak` varsayılanının boyunu belirler. `dunya` verilmezse
    `AcikDunya(**acik_alanlar)` (örn. `optionlar=`, `kampanya=`, `urunler=`) kurulur."""
    stok = np.asarray(stok, dtype=np.int64)
    depo = np.asarray(depo, dtype=np.int64)
    satis_gecmisi = np.asarray(satis_gecmisi, dtype=np.int16)
    stoklu_gecmisi = np.asarray(stoklu_gecmisi, dtype=bool)
    fiyat_orani = np.asarray(fiyat_orani, dtype=float)
    C, O = len(stok), len(fiyat_orani)
    if satis_gecmisi.shape[1:] != (C,) or stoklu_gecmisi.shape != satis_gecmisi.shape:
        raise ValueError("satis_gecmisi ve stoklu_gecmisi [gun, C] aynı biçimde olmalı")
    if len(satis_gecmisi) < gun:
        raise ValueError("geçmiş en az `gun` satır olmalı (dünkü akşama kadar)")
    # Gerçek motorda geçmiş [D, C] tam uzunluktadır, bugün ve sonrası 0'dır; sahte görünüm de
    # bugünden önceki satırlarla sınırlanıp sıfırlanır.
    sg = satis_gecmisi.copy()
    sg[gun:] = 0
    st = stoklu_gecmisi.copy()
    st[gun:] = False

    def veya(x, boyut, dtype, dolgu=0):
        return np.full(boyut, dolgu, dtype=dtype) if x is None else np.asarray(x, dtype=dtype)

    return Gorunum(
        dunya=dunya if dunya is not None else AcikDunya(**acik_alanlar),
        gun=gun,
        tarih=GUN_SIFIRI + pd.Timedelta(days=gun),
        magaza_stok=salt_okunur(stok),
        depo=salt_okunur(depo),
        yolda=salt_okunur(veya(yolda, C, np.int64)),
        satis_gecmisi=salt_okunur(sg),
        stoklu_gecmisi=salt_okunur(st),
        satis_28=salt_okunur(sg[max(0, gun - 28):gun].sum(axis=0).astype(np.int64)),
        gonderilen_option=salt_okunur(veya(gonderilen_option, O, np.int64)),
        satilan_option=salt_okunur(veya(satilan_option, O, np.int64)),
        satilan_option_magaza=salt_okunur(veya(satilan_option_magaza, O, np.int64)),
        rpt_sayisi=salt_okunur(veya(rpt_sayisi, O, np.int64)),
        ilk_dagitim_gun=salt_okunur(veya(ilk_dagitim_gun, O, np.int64, 10**6)),
        fiyat_orani=salt_okunur(fiyat_orani),
        acik_magaza=salt_okunur(veya(acik_magaza, magaza_sayisi, bool, True)),
        kapanacak=salt_okunur(veya(kapanacak, magaza_sayisi, bool, False)),
        acik_siparisler=tuple(acik_siparisler),
        operasyon_tohumu=operasyon_tohumu,
    )
