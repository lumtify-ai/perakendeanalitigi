"""`markdown.olcutler`: elle hesaplanmış oyuncak koşuda her ölçüt, korunum, isabet, çeyrek, yan etki.

Oyuncak dünya (gün ekseni `GUN_SIFIRI`): üç option — A ve B SS25 Collection (test), X Basic; birer
SKU; mağazalar S1 (AVM), ONL (Online), OUT (Outlet; outlet akışı hücreleri). Lansman L = 980,
indirim I = 1092, çıkış C = 1148 (hepsi pazartesi); serbest karar penceresi max(I − 56, L + 42) = 1036.
A normal/online hattında 1078 haftası %20, 1085 haftası %30; B hiç indirilmez. KÜÇÜK dünyada gerçek
koşularla tutarlılık `test_simulasyon.py`'de.
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from allocation import motor

from markdown import olcutler
from markdown.politika import KAYIT_SUTUNLARI

GUN0 = pd.Timestamp("2022-07-04")
L, I, C = 980, 1092, 1148


def tarih(d):
    return GUN0 + pd.Timedelta(days=int(d))


def oyuncak_dunya():
    optionlar = pd.DataFrame({
        "option_id": ["A", "B", "X"], "line": ["Collection", "Collection", "Basic"],
        "sezon_kodu": ["SS25", "SS25", "DEVAMLI"], "sezonluk": [True, True, False],
        "lansman_gun": [L, L, 0], "indirim_gun": [I, I, 10**6], "cikis_gun": [C, C, 10**6],
        "ust_kategori": ["Üst Giyim", "Alt Giyim", "Üst Giyim"]})
    urunler = pd.DataFrame({"urun_id": ["A-M", "B-M", "X-M"], "liste_fiyati": [100.0, 200.0, 50.0],
                            "alis_fiyati": [40.0, 80.0, 20.0]})
    magazalar = pd.DataFrame({"magaza_id": ["S1", "ONL", "OUT"], "tip": ["AVM", "Online", "Outlet"]})
    hm = np.repeat([0, 1, 2], 3)          # hücre = (mağaza, SKU)
    hs = np.tile([0, 1, 2], 3)
    return SimpleNamespace(optionlar=optionlar, urunler=urunler, magazalar=magazalar,
                           sku_option=np.array([0, 1, 2]), hucre_magaza=hm, hucre_sku=hs,
                           hucre_option=hs.copy(), hucre_outlet_akisi=(hm == 2) & (hs < 2))


def _satis(satirlar):
    df = pd.DataFrame(satirlar, columns=["gun", "magaza_id", "urun_id", "adet", "tutar", "indirim_tutari",
                                         "kampanya_id"])
    df.insert(0, "tarih", [tarih(d) for d in df.pop("gun")])
    df["kampanya_id"] = pd.Categorical(df["kampanya_id"], categories=["KMP1"])
    df["adet"] = df["adet"].astype(np.int32)
    return df


SATIS = [   # gün, mağaza, ürün, adet, tutar, indirim, kampanya
    (1000, "S1", "A-M", 3, 300.0, 0.0, None),          # tam fiyat
    (1010, "ONL", "A-M", 1, 90.0, 10.0, "KMP1"),       # kampanya
    (1012, "S1", "A-M", 2, 196.0, 4.0, None),          # işlem indirimi (tam fiyat sayılır)
    (1080, "S1", "A-M", 2, 160.0, 40.0, None),         # markdown %20
    (1086, "ONL", "A-M", 1, 70.0, 30.0, None),         # markdown %30, online
    (1090, "S1", "A-M", -1, -70.0, -30.0, None),       # iade
    (1150, "OUT", "A-M", 2, 100.0, 100.0, None),       # outlet penceresi
    (1240, "OUT", "A-M", 1, 50.0, 50.0, None),         # outlet penceresinden sonra: dışarıda
    (1000, "S1", "B-M", 5, 1000.0, 0.0, None),
    (1100, "S1", "B-M", 1, 200.0, 0.0, None),          # indirimden sonra, tam fiyat
    (1149, "S1", "B-M", -1, -200.0, 0.0, None),        # çıkıştan sonra iade: outlet penceresi
    (1000, "S1", "X-M", 4, 200.0, 0.0, None),          # kapsam dışı (Basic)
]


def _fiyat(ek=()):
    """Normal/online haftalık panel; `ek` (hafta, option, hat, oran) satırları aynı anahtarı değiştirir."""
    satir = []
    for o in ("A", "B"):
        for h in range(1071, 1148, 7):
            r = (0.2 if h == 1078 else 0.3 if h >= 1085 else 0.0) if o == "A" else 0.0
            satir += [(tarih(h), o, hat, r) for hat in ("normal", "online")]
    satir += [(tarih(1148), "A", "outlet", 0.5)]
    yeni = {(e[0], e[1], e[2]): e for e in ek}
    satir = [yeni.pop((a[0], a[1], a[2]), a) for a in satir] + list(yeni.values())
    df = pd.DataFrame(satir, columns=["hafta_baslangic", "option_id", "hat", "indirim_orani"])
    df["hat"] = pd.Categorical(df["hat"], categories=["normal", "outlet", "online"])
    return df


def _siparis(rpt_adet=5):
    df = pd.DataFrame([
        ("SP1", "ilk", "A", "A-M", 960, 975, 20), ("SP2", "rpt", "A", "A-M", 1001, 1050, rpt_adet),
        ("SP3", "rpt", "A", "A-M", 1220, None, 7), ("SP4", "ilk", "B", "B-M", 960, 975, 10),
        ("SP5", "ilk", "X", "X-M", 0, 0, 100)],
        columns=["siparis_id", "tip", "option_id", "urun_id", "siparis_gun", "teslim_gun", "adet"])
    df["siparis_tarihi"] = [tarih(d) for d in df.pop("siparis_gun")]
    df["gerceklesen_teslim"] = [pd.NaT if d is None or pd.isna(d) else tarih(d) for d in df.pop("teslim_gun")]
    return df


def _stok():
    return pd.DataFrame({"tarih": [tarih(1134), tarih(1141), tarih(1141)], "magaza_id": ["S1"] * 3,
                         "urun_id": ["A-M", "A-M", "B-M"], "adet": np.array([9, 4, 2], np.int32)})


def _depo():
    return pd.DataFrame({"tarih": [tarih(d) for d in (1141, 1141, 1268, 1268, 1300)],
                         "urun_id": ["A-M", "B-M", "A-M", "B-M", "A-M"],
                         "adet": np.array([3, 0, 2, 1, 5], np.int32)})


def _gercek():
    return pd.DataFrame({
        "tarih": [tarih(d) for d in (1000, 1040, 1100, 1050, 1045)],
        "magaza_id": ["S1", "S1", "S1", "ONL", "S1"], "urun_id": ["A-M", "A-M", "A-M", "A-M", "B-M"],
        "talep": [5, 2, 3, 1, 1], "kendi_satis": [3, 2, 0, 0, 1], "karsilanmayan": [2, 0, 3, 1, 0],
        "ikameye_giden": [1, 0, 1, 0, 0], "kalici_kayip": [1, 0, 2, 1, 0]})


def _sevkiyat(elle_a=3, ilk_a=12):
    df = pd.DataFrame([
        (975, 977, "DEPO", "S1", "A-M", ilk_a, "ilk_dagitim", "P1"),
        (975, 977, "DEPO", "S1", "B-M", 8, "ilk_dagitim", "P1"),
        (1100, 1102, "S1", "S1", "A-M", elle_a, "elle_transfer", None),
        (1100, 1102, "S1", "S1", "X-M", 2, "elle_transfer", None)],
        columns=["gun", "varis", "kaynak", "hedef", "urun_id", "adet", "tip", "paket_id"])
    df.insert(0, "tarih", [tarih(d) for d in df.pop("gun")])
    df.insert(1, "varis_tarihi", [tarih(d) for d in df.pop("varis")])
    df = df[df["adet"] > 0].reset_index(drop=True)
    df["tip"] = pd.Categorical(df["tip"], categories=["ilk_dagitim", "replenishment", "elle_transfer"])
    return df


def _kayit(satirlar=None):
    if satirlar is None:
        satirlar = [(d, o, 0.0, np.nan) for d in range(1036, 1078, 7) for o in (0, 1)]
        satirlar += [(1078, 0, 0.2, 6.0), (1085, 0, 0.3, 1.0), (1078, 1, 0.0, 2.0), (1085, 1, 0.0, np.nan)]
    df = pd.DataFrame(satirlar, columns=["gun", "option", "oran", "tahmini_satis"])
    df["satilabilir"] = 10.0
    df["beklenen_kalan"] = np.nan
    return df[list(KAYIT_SUTUNLARI)].astype({"gun": np.int64, "option": np.int64})


def oyuncak_kosu(*, satis=SATIS, fiyat=None, siparis=None, sevkiyat=None, kayit=None, pencere="serbest",
                 taban=0.0):
    tablolar = {"satis": _satis(satis), "fiyat": _fiyat() if fiyat is None else fiyat,
                "siparis": _siparis() if siparis is None else siparis, "stok": _stok(), "depo_stok": _depo(),
                "sevkiyat": _sevkiyat() if sevkiyat is None else sevkiyat,
                "kalite_kontrol": pd.DataFrame({"siparis_id": ["SP1", "SP2"], "hatali": [1, 0]})}
    meta = {"olcek": "oyuncak", "tablolar": sorted(tablolar),
            "politikalar": {"markdown": {"parametreler": {"pencere": pencere, "taban": taban,
                                                          "test_optionlari": [0, 1]}}}}
    return motor.Kosu(tablolar=tablolar, gercek=_gercek(), meta=meta,
                      kayitlar={"markdown": _kayit() if kayit is None else kayit})


@pytest.fixture
def w():
    return oyuncak_dunya()


def test_olcutler_oyuncak(w):
    """Her ölçüt elle (modül notu): A ciro sezon 746, outlet 100; B 1200 ve −200 (çıkış sonrası iade)."""
    r = olcutler.hesapla(oyuncak_kosu(), w, "SS25")
    beklenen = {
        "option_sayisi": 2,
        "ciro_sezon": 746 + 1200, "ciro_outlet": 100 - 200, "ciro_toplam": 1846,
        "brut_kar": 1846 - (40 * 10 + 80 * 5),            # net adet A 10, B 5
        "katki": 1846 - (40 * 25 + 80 * 10),              # arz: A ilk 20 + RPT 5 (teslimsiz RPT yok), B 10
        "markdown_tl": 70, "markdown_tl_online": 30, "kampanya_tl": 10, "islem_tl": 4,
        "outlet_indirim_tl": 100, "arz_adet": 35, "arz_alis": 1800,
        "tam_fiyat_str": 100 * (5 + 6) / 35, "son_str": 100 * (9 + 6) / 35,
        "cikis_kalan_adet": 9, "cikis_kalan_magaza_adet": 6, "cikis_kalan_depo_adet": 3,
        "cikis_kalan_liste": 7 * 100 + 2 * 200, "cikis_kalan_alis": 7 * 40 + 2 * 80,
        "olu_stok_adet": 3, "olu_stok_alis": 2 * 40 + 1 * 80,
        "indirilen_option": 1, "ilk_indirim_hafta_medyan": -2.0, "ort_en_derin": 30.0,
        "muaf_str_ind": 100 * 5 / 10,
        "bulunabilirlik": 100 * 2 / 3, "kayip_orani": 100 * 3 / 6,
    }
    assert set(r) == set(beklenen)
    for a, v in beklenen.items():
        assert r[a] == pytest.approx(v), a
    s = olcutler.indirim_basi_str(oyuncak_kosu(), w, "SS25")
    assert s.to_dict() == pytest.approx({"A": 100 * 9 / 25, "B": 50.0})


def test_olcutler_bos_davranis(w):
    """Hiç indirilen yoksa medyan ve ortalama derinlik NaN, muaf STR herkes; payda 0'da oran 0."""
    f = _fiyat()
    f["indirim_orani"] = np.where(f["hat"].astype(str) == "outlet", f["indirim_orani"], 0.0)
    r = olcutler.hesapla(oyuncak_kosu(fiyat=f), w, "SS25")
    assert r["indirilen_option"] == 0 and np.isnan(r["ilk_indirim_hafta_medyan"]) and np.isnan(r["ort_en_derin"])
    assert r["muaf_str_ind"] == pytest.approx(100 * (9 + 5) / 35)
    assert r["markdown_tl"] == 0 and r["islem_tl"] == 4 + 40 + 30   # oran 0 haftasındaki indirim işlem sayılır
    assert olcutler._oran(1, 0) == 0.0


def test_ceyrek_gruplama(w, monkeypatch):
    """Çeyrek Lumoda STR'sinin sırasıyla (eşitlikte option_id); toplanır ölçütler çeyreklerin toplamı."""
    t = olcutler.option_tablosu(oyuncak_kosu(), w, "SS25")
    sekiz = pd.concat([t.assign(option_id=[f"{a}{i}" for a in t["option_id"]]) for i in range(4)],
                      ignore_index=True)
    monkeypatch.setattr(olcutler, "option_tablosu", lambda *a: sekiz)
    lumoda = pd.Series({o: float(v) for o, v in zip(sekiz["option_id"], [5, 1, 3, 3, 8, 2, 0, 7])})
    c = olcutler.ceyrek(None, w, "SS25", lumoda)
    assert c["ceyrek"].tolist() == [1, 2, 3, 4] and c["option_sayisi"].tolist() == [2, 2, 2, 2]
    # sıra: A3 (0), B0 (1) | B2 (2), A1 (3) | B1 (3), A0 (5) | B3 (7), A2 (8)
    assert c["str_alt"].tolist() == [0, 2, 3, 7] and c["str_ust"].tolist() == [1, 3, 5, 8]
    toplam = olcutler.ozetle(sekiz)
    for a in ("ciro_toplam", "markdown_tl", "katki", "olu_stok_adet"):
        assert c[a].sum() == pytest.approx(toplam[a]), a
    with pytest.raises(ValueError, match="lumoda_str"):
        olcutler.ceyrek(None, w, "SS25", lumoda.iloc[:-1])


def test_isabet_oyuncak(w):
    """Kayıt satırı (1078, A) tahmin 6 ↔ [1078, C) gerçek 3; (1085, A) 1 ↔ 1; (1078, B) 2 ↔ 1; NaN girmez."""
    r = olcutler.isabet(oyuncak_kosu(), w)
    assert r == pytest.approx({"wape": 100 * 4 / 5, "yanlilik": 100 * 4 / 5, "wape_ilk": 100 * 4 / 4,
                               "satir": 3.0})
    k = oyuncak_kosu()
    k.kayitlar["markdown"] = pd.DataFrame({"gun": [1], "indis": [0], "sutun": [0], "deger": [0.3]})
    with pytest.raises(ValueError, match="kolun kaydı değil"):
        olcutler.isabet(k, w)


def test_korunum_saglam(w):
    r = olcutler.korunum(oyuncak_kosu(), oyuncak_kosu(), "serbest", w)
    assert r == {"rpt_birebir": True, "ilk_dagitim_birebir": True, "arz_birebir": True, "merdiven": True,
                 "siglasmaz": True, "pencere": True, "takvim_tabani": True}


def _bozuk_kayit(degisim):
    k = _kayit()
    for (gun, o), oran in degisim.items():
        k.loc[(k["gun"] == gun) & (k["option"] == o), "oran"] = oran
    return k


@pytest.mark.parametrize("bozuk,anahtar", [
    ({"siparis": _siparis(rpt_adet=6)}, "rpt_birebir"),
    ({"sevkiyat": _sevkiyat(ilk_a=11)}, "ilk_dagitim_birebir"),
    ({"kayit": _bozuk_kayit({(1078, 0): 0.25})}, "merdiven"),
    ({"fiyat": _fiyat(ek=[(tarih(1141), "B", "normal", 0.25)])}, "merdiven"),
    ({"kayit": _bozuk_kayit({(1078, 0): 0.3, (1085, 0): 0.2})}, "siglasmaz"),
    # pencere önü (1029 haftasının son günü 1035 < 1036); 1071 de %20: sığlaşma yok
    ({"fiyat": _fiyat(ek=[(tarih(1029), "A", "normal", 0.2), (tarih(1071), "A", "normal", 0.2)])}, "pencere"),
])
def test_korunum_bozuk_kayit(w, bozuk, anahtar):
    """Her bozulma yalnız kendi sözleşmesini düşürür (RPT adedi arzı da)."""
    r = olcutler.korunum(oyuncak_kosu(**bozuk), oyuncak_kosu(), "serbest", w)
    dusen = {a for a, v in r.items() if not v}
    assert dusen == ({anahtar, "arz_birebir"} if anahtar == "rpt_birebir" else {anahtar})


def test_korunum_takvim_tabani(w):
    """Takvim kipinde pencere indirim günü ve indirim gününden %30 taban (kayıt ve uygulanan fiyat)."""
    f = _fiyat()
    f.loc[f["hafta_baslangic"] < tarih(I), "indirim_orani"] = 0.0
    kayit = _kayit([(1092, 0, 0.3, np.nan), (1092, 1, 0.3, np.nan)])
    f.loc[(f["option_id"] == "B") & (f["hafta_baslangic"] >= tarih(I)) & (f["hat"] != "outlet"),
          "indirim_orani"] = 0.3
    iyi = oyuncak_kosu(fiyat=f, kayit=kayit, pencere="takvim", taban=0.3)
    assert all(olcutler.korunum(iyi, oyuncak_kosu(), "takvim", w).values())
    kotu = oyuncak_kosu(fiyat=f, kayit=_kayit([(1092, 0, 0.3, np.nan), (1092, 1, 0.2, np.nan)]),
                        pencere="takvim", taban=0.3)
    r = olcutler.korunum(kotu, oyuncak_kosu(), "takvim", w)
    assert {a for a, v in r.items() if not v} == {"takvim_tabani"}
    # serbest kolun pencere önü indirimi takvim kipinde pencere ihlalidir
    r = olcutler.korunum(oyuncak_kosu(pencere="takvim", taban=0.3), oyuncak_kosu(), "takvim", w)
    assert not r["pencere"]
    with pytest.raises(ValueError, match="penceresi"):
        olcutler.korunum(oyuncak_kosu(), oyuncak_kosu(), "takvim", w)
    with pytest.raises(ValueError, match="kol_tipi"):
        olcutler.korunum(oyuncak_kosu(), oyuncak_kosu(), "lumoda", w)


def test_yan_etki_oyuncak(w):
    """Test dışı X'in cirosu 200 ↔ Lumoda 150 (Basic +50); elle transfer A 3 ↔ 0; ikame alınan = pozitif
    satış − kendi satış ([L, C + 84)): A 11 − 5, B 6 − 1."""
    lum = oyuncak_kosu(satis=[s if s[2] != "X-M" else (*s[:4], 150.0, *s[5:]) for s in SATIS],
                       sevkiyat=_sevkiyat(elle_a=0))
    r = olcutler.yan_etki(oyuncak_kosu(), lum, w, "SS25")
    assert r["ciro_farki_test_disi"] == pytest.approx(50.0) and r["ciro_test_disi_lumoda"] == pytest.approx(150.0)
    assert r["ciro_farki_basic"] == pytest.approx(50.0) and r["ciro_farki_collection"] == 0.0
    assert r["ikame_alinan"] == r["ikame_alinan_lumoda"] == 11.0 and r["ikame_alinan_farki"] == 0.0
    assert r["ikame_giden"] == 2.0 and r["ikame_giden_farki"] == 0.0
    assert r["elle_transfer_farki"] == 3.0 and r["elle_transfer_farki_test"] == 3.0
