"""Ortak fikstürler: v4 şemalı oyuncak tablolar.

**Mağazalar** (8; karar günü 2025-02-07 cuma, lansman 2025-02-10 pazartesi). Beden kayması
(gizli gerçeğin oyuncak karşılığı) üç profildir: `kucuk` küçük bedene, `orta` ortaya, `buyuk`
büyük bedene kayar. Kayma yalnız `gizli` fikstüründe ve satışı üreten `PROFIL` kurgusundadır;
`tablolar` kaymayı taşımaz.

    S01 İstanbul AVM      Marmara       kucuk
    S02 İstanbul Cadde    Marmara       kucuk
    S03 Ankara AVM        İç Anadolu    kucuk
    S04 Bursa AVM         Marmara       orta
    S05 Konya Cadde       İç Anadolu    orta
    S06 Erzurum AVM       Doğu Anadolu  buyuk
    S07 Antalya AVM       Akdeniz       buyuk
    S08 Kocaeli AVM       Marmara       orta; YENİ: 2024-12-02'de açıldı (10 tam satışlı hafta,
                                        yalnız Basic ve NOS satışı: Collection geçmişi yok)

Kapsam: 8 aday; 7 kümelenir (Kümeleme eşiği 26 hafta), S08 yeni.

**Ürünler** (26 SKU, 6 option). Collection: SS24 ve SS25'in ikişer option'ı (`OPT-SS24-A` Kadın
Harf XS..XL, `OPT-SS24-B` Kadın Numara 34..42; SS25 aynı iki set), Basic (`OPT-BAS`, Kadın Harf) ve
NOS aksesuarı (`OPT-NOS-STD`, Standart tek beden). Beş bedenli SKU: 25; aksesuar: 1.

**Satış**: her mağaza açıldığı pazartesiden (en erken 2023-01-02) 2025-02-03'e dek her pazartesi
Basic ve NOS; SS24 Collection yalnız 2024-02-12 … 2024-08-26 pazartesileri. Beden payı mağazanın
profilinden gelir (`PAY`); haftalık toplam mağazaya ve haftaya göre sabit bir formülle değişir
(rastgelelik yok). Karar gününden sonra (2025-02-10) her mağazaya SS25 ve Basic satırları vardır:
eğri ve kapsam bunu görmemelidir.

**Stok** (pazartesi fotoğrafları): satışlı her hafta için ertesi pazartesi, o hafta satılan her
SKU'da adet 10, `stoklu_gun` 7. `ONL` yoktur; outlet yoktur.

**Paket** (yayımlanan biçim): her beş bedenli set 1-2-2-1-1, Standart tek bedende 6.
**Sevkiyat**: SS24 ilk dağıtımı (`ilk_dagitim`, paket_id'li) ve replenishment (paket_idsiz),
biri karar gününden sonra. **Depo**: SS25 SKU'larında karar günü stoğu. **Sezon**, **takvim**.
"""

import duckdb
import numpy as np
import pandas as pd
import pytest

KARAR = pd.Timestamp("2025-02-07")
LANSMAN = pd.Timestamp("2025-02-10")
KAL_KARAR = pd.Timestamp("2024-02-09")

_S, _T = "string", "datetime64[ns]"

_MAGAZALAR = [   # magaza_id, ad, sehir, bolge, tip, enlem, metrekare, acilis
    ("S01", "İstanbul 1", "İstanbul", "Marmara", "AVM", 41.01, 700, "2015-03-02"),
    ("S02", "İstanbul 2", "İstanbul", "Marmara", "Cadde", 41.03, 350, "2016-03-07"),
    ("S03", "Ankara 1", "Ankara", "İç Anadolu", "AVM", 39.93, 650, "2015-09-07"),
    ("S04", "Bursa 1", "Bursa", "Marmara", "AVM", 40.19, 600, "2016-10-03"),
    ("S05", "Konya 1", "Konya", "İç Anadolu", "Cadde", 37.87, 320, "2018-04-02"),
    ("S06", "Erzurum 1", "Erzurum", "Doğu Anadolu", "AVM", 39.90, 580, "2019-05-06"),
    ("S07", "Antalya 1", "Antalya", "Akdeniz", "AVM", 36.89, 540, "2019-06-03"),
    ("S08", "Kocaeli 1", "Kocaeli", "Marmara", "AVM", 40.85, 900, "2024-12-02"),
]
_OLAY = [("S08", "acilis", "2024-09-01", "2024-12-02", None)]
YENI = "S08"

# satışı üreten oyuncak beden kayması (gizli segment kurgusu); `gizli` fikstürü aynısını taşır
PROFIL = {"S01": "kucuk", "S02": "kucuk", "S03": "kucuk", "S04": "orta", "S05": "orta",
          "S06": "buyuk", "S07": "buyuk", "S08": "orta"}
KAYMA = {"kucuk": -1.0, "orta": 0.0, "buyuk": 1.0}
PAY = {   # profil -> beden sırası 1..5 payı (satışı üreten gerçek eğri)
    "kucuk": (0.35, 0.30, 0.20, 0.10, 0.05),
    "orta": (0.10, 0.25, 0.30, 0.25, 0.10),
    "buyuk": (0.05, 0.10, 0.20, 0.30, 0.35),
}
STANDART_PAKET = (1, 2, 2, 1, 1)

_HARF = ("XS", "S", "M", "L", "XL")
_NUMARA = ("34", "36", "38", "40", "42")
# option_id, line, sezon, lansman, cikis, ust, alt, segment, kalip, beden_seti, bedenler
_OPTIONLAR = [
    ("OPT-SS24-A", "Collection", "SS24", "2024-02-12", "2024-08-26", "Üst Giyim", "Tişört", "orta",
     "regular", "Kadın Harf", _HARF),
    ("OPT-SS24-B", "Collection", "SS24", "2024-02-12", "2024-08-26", "Alt Giyim", "Pantolon", "orta",
     "regular", "Kadın Numara", _NUMARA),
    ("OPT-SS25-A", "Collection", "SS25", "2025-02-10", "2025-08-25", "Üst Giyim", "Tişört", "orta",
     "regular", "Kadın Harf", _HARF),
    ("OPT-SS25-B", "Collection", "SS25", "2025-02-10", "2025-08-25", "Alt Giyim", "Pantolon", "orta",
     "regular", "Kadın Numara", _NUMARA),
    ("OPT-BAS", "Basic", "DEVAMLI", "2022-07-04", None, "Üst Giyim", "Tişört", "giris",
     "relaxed", "Kadın Harf", _HARF),
    ("OPT-NOS-STD", "NOS", "DEVAMLI", "2022-07-04", None, "Aksesuar", "Çanta", "orta",
     "regular", "Standart", ("STD",)),
]

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
    "paket": {"paket_id": _S, "beden_seti": _S, "beden_sira": "int64", "adet": "int64"},
    "sevkiyat": {"tarih": _T, "varis_tarihi": _T, "kaynak": _S, "hedef": _S, "urun_id": _S,
                 "adet": "int32", "tip": _S, "paket_id": _S},
    "depo_stok": {"tarih": _T, "urun_id": _S, "adet": "int32"},
    "sezon": {"sezon_kodu": _S, "dalga": "int64", "lansman_tarihi": _T, "indirim_baslangic": _T,
              "cikis_tarihi": _T},
    "takvim": {"tarih": _T, "hafta": "int64", "ay": "int32", "yil": "int32", "sezon": _S,
               "sezon_kodu": _S, "tatil_mi": "bool", "indirim_donemi_mi": "bool"},
}


def doldur(tablo: str, satirlar: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(satirlar, columns=list(SEMA[tablo]))
    for s, t in SEMA[tablo].items():
        df[s] = pd.to_datetime(df[s]) if t == _T else df[s].astype(t)
    return df


def urun_id(option_id: str, beden: str) -> str:
    return f"{option_id}-{beden}"


def _urunler() -> list[tuple]:
    return [(urun_id(o, b), o, line, sezon, 1 if line == "Collection" else 0, lansman, cikis, ust,
             alt, seg, kalip, seti, b, i + 1)
            for o, line, sezon, lansman, cikis, ust, alt, seg, kalip, seti, bedenler in _OPTIONLAR
            for i, b in enumerate(bedenler)]


def _haftalar(acilis, son="2025-02-03") -> pd.DatetimeIndex:
    """Mağazanın satışlı pazartesileri (en erken 2023-01-02)."""
    ilk = pd.Timestamp(acilis)
    ilk = ilk + pd.Timedelta(days=(7 - ilk.weekday()) % 7)
    return pd.date_range(max(ilk, pd.Timestamp("2023-01-02")), pd.Timestamp(son), freq="7D")


def _satilan_optionlar(t: pd.Timestamp, acilis: str) -> list[tuple]:
    """O pazartesi satılan option'lar: Collection yalnız lansman-çıkış arasında; karar sonrası
    (t >= LANSMAN) SS25 Collection ile Basic ve NOS. Yeni mağazanın Collection geçmişi yoktur."""
    yeni = pd.Timestamp(acilis) >= pd.Timestamp("2024-12-01")
    sonuc = []
    for o in _OPTIONLAR:
        if o[1] != "Collection":
            sonuc.append(o)
        elif t >= LANSMAN:
            if o[2] == "SS25":
                sonuc.append(o)
        elif pd.Timestamp(o[3]) <= t <= pd.Timestamp(o[4]) and not yeni:
            sonuc.append(o)
    return sonuc


def _adetler(i: int, t: pd.Timestamp, option: tuple) -> list[int]:
    """Mağaza i'nin t haftasında option'ın beden sırası başına adedi (profil payından)."""
    if option[9] == "Standart":
        return [2]
    toplam = 20 + 5 * (i % 3) + t.isocalendar().week % 4
    toplam *= 0.5 if option[0].endswith("-B") else 0.6 if option[1] == "Basic" else 1.0
    pay = PAY[PROFIL[_MAGAZALAR[i][0]]]
    return [max(1, int(round(toplam * p))) for p in pay]


def _satis() -> list[tuple]:
    satir = []
    for i, (m, *_r, acilis) in enumerate(_MAGAZALAR):
        for t in list(_haftalar(acilis)) + [LANSMAN]:
            for opt in _satilan_optionlar(t, acilis):
                for b, a in zip(opt[10], _adetler(i, t, opt)):
                    satir.append((t, m, urun_id(opt[0], b), a, 100.0 * a, 0.0, None))
    return satir


def _stok() -> list[tuple]:
    satir = []
    for m, *_r, acilis in _MAGAZALAR:
        for t in _haftalar(acilis):
            for opt in _satilan_optionlar(t, acilis):
                satir += [(t + pd.Timedelta(days=7), m, urun_id(opt[0], b), 10, 7) for b in opt[10]]
    return satir


def _paket() -> list[tuple]:
    satir = [(f"PKT0{i}", seti, j + 1, a) for i, seti in ((1, "Kadın Harf"), (2, "Kadın Numara"))
             for j, a in enumerate(STANDART_PAKET)]
    return satir + [("PKT03", "Standart", 1, 6)]


def _sevkiyat() -> list[tuple]:
    """SS24 ilk dağıtımı (paket_id'li, mağaza başına 3 paket) ve replenishment (biri karar
    gününden sonra); yeni mağazaya SS24'te sevkiyat yoktur."""
    satir = []
    for m, *_r, acilis in _MAGAZALAR:
        if m == YENI:
            continue
        for o, pkt, bedenler in (("OPT-SS24-A", "PKT01", _HARF), ("OPT-SS24-B", "PKT02", _NUMARA)):
            satir += [("2024-02-09", "2024-02-10", "DEPO", m, urun_id(o, b), 3 * a, "ilk_dagitim", pkt)
                      for b, a in zip(bedenler, STANDART_PAKET)]
        satir.append(("2024-03-04", "2024-03-05", "DEPO", m, urun_id("OPT-SS24-A", "M"), 5,
                      "replenishment", None))
        satir.append(("2025-02-10", "2025-02-11", "DEPO", m, urun_id("OPT-SS24-A", "M"), 5,
                      "replenishment", None))
    return satir


def _depo_stok() -> list[tuple]:
    return [(KARAR, urun_id(o[0], b), 400 + 50 * i) for o in _OPTIONLAR if o[2] == "SS25"
            for i, b in enumerate(o[10])]


def _takvim() -> list[tuple]:
    satir = []
    for d in pd.date_range("2023-01-01", "2025-03-31"):
        kod = (f"SS{d.year % 100}" if 2 <= d.month <= 7 else
               f"AW{d.year % 100}" if d.month >= 8 else f"AW{(d.year - 1) % 100}")
        satir.append((d, d.isocalendar().week, d.month, d.year,
                      "İlkbahar/Yaz" if kod.startswith("SS") else "Sonbahar/Kış", kod, False, False))
    return satir


def oyuncak_tablolar() -> dict[str, pd.DataFrame]:
    magaza = doldur("magaza", [(m, ad, sh, bl, en, 29.0, tip, m2, 1, 8 * m2 + 100, a, None)
                               for m, ad, sh, bl, tip, en, m2, a in _MAGAZALAR])
    return {
        "magaza": magaza,
        "magaza_olay": doldur("magaza_olay", _OLAY),
        "urun": doldur("urun", _urunler()),
        "satis": doldur("satis", _satis()),
        "stok": doldur("stok", _stok()),
        "paket": doldur("paket", _paket()),
        "sevkiyat": doldur("sevkiyat", _sevkiyat()),
        "depo_stok": doldur("depo_stok", _depo_stok()),
        "sezon": doldur("sezon", [("SS24", 1, "2024-02-12", "2024-07-01", "2024-08-26"),
                                  ("SS25", 1, "2025-02-10", "2025-06-30", "2025-08-25")]),
        "takvim": doldur("takvim", _takvim()),
    }


@pytest.fixture
def tablolar() -> dict[str, pd.DataFrame]:
    return oyuncak_tablolar()


@pytest.fixture
def gizli() -> pd.DataFrame:
    """Gizli beden kayması (yalnız hakem/ölçüm testleri için): -1 küçük, 0 orta, +1 büyük bedene."""
    return pd.DataFrame({"magaza_id": list(PROFIL),
                         "beden_kayma": [KAYMA[p] for p in PROFIL.values()]})


def oyuncak_baglan(tablolar: dict[str, pd.DataFrame]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for ad, df in tablolar.items():
        con.register("_gecici", df)
        con.execute(f"create table {ad} as select * from _gecici")
        con.unregister("_gecici")
    return con


def gercek_pay(profil: str) -> np.ndarray:
    """Profilin satışı üreten beden payı (hakem testleri için)."""
    return np.array(PAY[profil])
