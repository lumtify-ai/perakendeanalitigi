"""`markdown.tahmin.Tahminci`: tam fiyat taban talebi, satılabilir stok, fiyat çarpanları.

**Tahmin oyuncağı.** Dünya (`AcikDunya`, yalnız açık alanlar): S1 (Marmara), S2 (Ege), S3 (Marmara),
ONL (Marmara, online; son satır). Üç SS25 Collection option'ı (iki beden) ve bir Basic:

    0  SS25-a  Üst Giyim / Tişört    satar (S3'te son 28 günde hiç stok yok)
    1  SS25-b  Alt Giyim / Pantolon  stoklu ama hiç satmaz
    2  SS25-c  Üst Giyim / Tişört    her yerde satar (mağaza payı için)
    3  BAS-1   Basic                 (servis edilmez)

Hücreler: her beden × {S1, S2, S3, ONL}. Kampanya: Üst Giyim, Marmara, %20 (ONL'yi kapsamaz),
geçmişte ve ufukta birer pencere. Satış geçmişi gerçek modelden üretilir:
`taban_m × pay × hafta günü × özel gün × yaşam × (1 − max(md, kampanya))^(−ε)` (yuvarlanmadan önce
×100 ölçek; int16'ya sığar), markdown son 10 günde %30 (`fiyat_gecmisi` olaylarıyla).
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest
from conftest import AcikDunya, gorunum, gun_indisi

from markdown import ogrenme, sabitler, tahmin

EPS = 1.8
LANSMAN = gun_indisi("2025-02-10")
INDIRIM = gun_indisi("2025-06-30")
CIKIS = gun_indisi("2025-08-25")
GUN = LANSMAN + 7 * 10                     # karar pazartesisi
assert GUN % 7 == 0
MD_BAS = GUN - 10                          # geçmişte markdown %30 başlangıcı
KMP_GECMIS = (GUN - 20, GUN - 16)          # geçmiş kampanya (dahil)
KMP_UFUK = (GUN + 9, GUN + 12)             # ufuk kampanyası (dahil)
TATIL = GUN + 3                            # ufukta bir tatil
MAGAZA = ["S1", "S2", "S3", "ONL"]
BOLGE = ["Marmara", "Ege", "Marmara", "Marmara"]
TABAN = {"S1": 6.0, "S2": 4.0, "S3": 5.0, "ONL": 10.0}      # option-gün taban (I = 1, hg = 1)
OPTIONLAR = [   # option_id, ust, alt, liste
    ("SS25-a", "Üst Giyim", "Tişört", 500.0),
    ("SS25-b", "Alt Giyim", "Pantolon", 800.0),
    ("SS25-c", "Üst Giyim", "Tişört", 400.0),
]
PAY = (0.4, 0.6)
HG = {"magaza": [0.9, 0.9, 0.9, 1.0, 1.1, 1.2, 1.0], "online": [1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 0.9]}
OZEL = {"tatil": 1.5}
OLCEK = 100.0


def _dunya():
    opt = pd.DataFrame({
        "option_id": [o[0] for o in OPTIONLAR] + ["BAS-1"],
        "sezon_kodu": ["SS25"] * 3 + ["DEVAMLI"], "line": ["Collection"] * 3 + ["Basic"],
        "dalga": [1, 1, 1, 0], "lansman_gun": [LANSMAN] * 3 + [0],
        "indirim_gun": [INDIRIM] * 3 + [10**6], "cikis_gun": [CIKIS] * 3 + [10**6],
        "sezonluk": [True] * 3 + [False],
        "ust_kategori": [o[1] for o in OPTIONLAR] + ["Üst Giyim"],
        "alt_kategori": [o[2] for o in OPTIONLAR] + ["Tişört"],
        "liste_fiyati": [o[3] for o in OPTIONLAR] + [300.0],
    })
    urunler = pd.DataFrame({"urun_id": [f"{o[0]}-{b}" for o in OPTIONLAR for b in "SM"] + ["BAS-1-S"],
                            "option_id": [o[0] for o in OPTIONLAR for _b in "SM"] + ["BAS-1"]})
    sku_option = np.array([0, 0, 1, 1, 2, 2, 3])
    hm, hs = [], []
    for s in range(6):
        for m in range(4):
            hm.append(m)
            hs.append(s)
    hm.append(0)
    hs.append(6)
    hm, hs = np.array(hm), np.array(hs)
    magazalar = pd.DataFrame({"magaza_id": MAGAZA, "bolge": BOLGE,
                              "tip": ["AVM", "AVM", "Cadde", "Online"]})
    kampanya = pd.DataFrame({
        "kampanya_id": ["K1", "K2", "K3"], "tip": ["kategori", "kategori", "kategori"],
        "baslangic": [sabitler_tarih(KMP_GECMIS[0]), sabitler_tarih(KMP_UFUK[0]), sabitler_tarih(GUN + 40)],
        "bitis": [sabitler_tarih(KMP_GECMIS[1]), sabitler_tarih(KMP_UFUK[1]), sabitler_tarih(GUN + 45)],
        "kapsam_ust_kategori": ["Üst Giyim", "Üst Giyim", "Alt Giyim"], "kapsam_line": ["", "", ""],
        "kapsam_bolge": ["Marmara", "Marmara", ""], "oran": [0.2, 0.2, 0.25],
    })
    takvim = pd.DataFrame({"tarih": pd.date_range(sabitler.GUN_SIFIRI, periods=CIKIS + 200),
                           "tatil_mi": False})
    takvim.loc[TATIL, "tatil_mi"] = True
    return AcikDunya(
        optionlar=opt, urunler=urunler, magazalar=magazalar, kampanya=kampanya, takvim=takvim,
        hucre_magaza=hm, hucre_sku=hs, hucre_option=sku_option[hs], hucre_online=hm == 3,
        hucre_outlet_akisi=np.zeros(len(hm), bool), sku_option=sku_option,
        sku_beden_payi=np.array([0.4, 0.6, 0.5, 0.5, 0.4, 0.6, 1.0]))


def sabitler_tarih(gun: int) -> pd.Timestamp:
    return pd.Timestamp(sabitler.GUN_SIFIRI) + pd.Timedelta(days=int(gun))


def _egri() -> np.ndarray:
    return 0.97 ** np.arange(40)


def _ogrenilen(**degis) -> ogrenme.Ogrenilen:
    e = _egri()
    yasam = pd.DataFrame({"sezon_tipi": "SS", "duzey": "alt_kategori", "grup": "Tişört", "dalga": 1,
                          "hafta": np.arange(len(e)), "carpan": e, "kaynak": "alt_kategori"})
    o = ogrenme.Ogrenilen(
        test_sezonu="SS25", bitis=pd.Timestamp("2025-05-05").date(), sezonlar=("SS23", "SS24"),
        eps_kampanya={"*": EPS, "Üst Giyim": EPS, "Alt Giyim": EPS}, eps_markdown={"*": 1.2},
        eps_saf=0.2, yasam=yasam,
        hafta_gunu={(k, g): v for k, vs in HG.items() for g, v in enumerate(vs)}, ozel_gun=OZEL,
        beden_payi=pd.DataFrame({"magaza_id": ["*"] * 6, "option_id": [o[0] for o in OPTIONLAR for _ in "SM"],
                                 "urun_id": [f"{o[0]}-{b}" for o in OPTIONLAR for b in "SM"],
                                 "pay": [*PAY, 0.5, 0.5, *PAY]}),
        kalinti=0.13, iade={"magaza": 0.06, "online": 0.27}, islem=0.024)
    return dataclasses.replace(o, **degis)


def _kamp(m: int, o: int, d: int) -> float:
    ust = OPTIONLAR[o][1] if o < 3 else "Üst Giyim"
    for a, b, k_ust, bolge in ((*KMP_GECMIS, "Üst Giyim", "Marmara"), (*KMP_UFUK, "Üst Giyim", "Marmara")):
        if a <= d <= b and ust == k_ust and BOLGE[m] == bolge and MAGAZA[m] != "ONL":
            return 0.2
    if GUN + 40 <= d <= GUN + 45 and ust == "Alt Giyim":
        return 0.25
    return 0.0


def _ozel(d: int) -> float:
    return OZEL["tatil"] if d == TATIL else 1.0


def gercek_gunluk(w, o: int, gunler, md: float | np.ndarray = 0.0, fiyatsiz: bool = False) -> np.ndarray:
    """[U, C(o)] gerçek beklenen günlük satış (fiyat dahil; `fiyatsiz`ta tam fiyat taban)."""
    hucre = np.flatnonzero(w.hucre_option == o)
    e = _egri()
    out = np.zeros((len(gunler), len(hucre)))
    md = np.broadcast_to(np.asarray(md, float), (len(gunler),))
    for j, c in enumerate(hucre):
        m = int(w.hucre_magaza[c])
        pay = PAY[int(w.hucre_sku[c]) % 2] if o != 1 else 0.5
        kanal = "online" if MAGAZA[m] == "ONL" else "magaza"
        for i, d in enumerate(gunler):
            f = TABAN[MAGAZA[m]] * pay * HG[kanal][d % 7] * _ozel(d) * e[min((d - LANSMAN) // 7, 39)]
            if not fiyatsiz:
                f *= (1 - max(md[i], _kamp(m, o, d))) ** (-EPS)
            out[i, j] = f
    return out


def _gecmis(w, s3_stoksuz=True, s2_yalniz_eski=True):
    """[GUN + 30, C] satış (×OLCEK, yuvarlanmış; bugünden sonrası çöp) ve stoklu bayrakları."""
    C = len(w.hucre_magaza)
    D = GUN + 30
    sg = np.zeros((D, C), np.int64)
    st = np.zeros((D, C), bool)
    gunler = np.arange(GUN - 40, GUN)
    md = np.where(gunler >= MD_BAS, 0.3, 0.0)
    for o in range(3):
        hucre = np.flatnonzero(w.hucre_option == o)
        g = gercek_gunluk(w, o, gunler, md) * OLCEK
        for j, c in enumerate(hucre):
            st[gunler, c] = True
            if o != 1:
                sg[gunler, c] = np.round(g[:, j])
    a = np.flatnonzero(w.hucre_option == 0)
    if s3_stoksuz:                       # option a, S3: 28 günde hiç stok yok
        s3 = a[w.hucre_magaza[a] == 2]
        st[GUN - 28:, s3] = False
        sg[GUN - 28:, s3] = 0
    if s2_yalniz_eski:                   # option a, S2: yalnız 15–28 gün önce stoklu
        s2 = a[w.hucre_magaza[a] == 1]
        st[GUN - 14:, s2] = False
        sg[GUN - 14:, s2] = 0
    sg[GUN:] = 7777                      # bugün ve sonrası: görünmemeli
    st[GUN:] = True
    return sg, st


def _fiyat_orani():
    f = np.zeros((4, 3))
    f[:3, [0, 2]] = 0.3
    return f


def _fiyat_gecmisi():
    """Lansmanda 0, MD_BAS'ta %30 (normal ve online hat), bir de bugünden sonrası (görünmemeli)."""
    o = np.array([0, 0, 1, 1, 2, 2])
    h = np.array([0, 2, 0, 2, 0, 2])
    return ((LANSMAN, o, h, np.zeros(6)), (MD_BAS, o, h, np.full(6, 0.3)),
            (GUN + 1, o, h, np.full(6, 0.7)))


def _g(w=None, sg=None, st=None, fiyat_gecmisi="var", **kw):
    w = w or _dunya()
    if sg is None:
        sg, st = _gecmis(w)
    C = len(w.hucre_magaza)
    stok = kw.pop("stok", np.full(C, 5, np.int64))
    stok = np.where(w.hucre_online, 0, stok)
    g = gorunum(GUN, stok, kw.pop("depo", np.full(7, 100)), np.clip(sg, 0, 32000), st, _fiyat_orani(),
                dunya=w, yolda=kw.pop("yolda", np.zeros(C, np.int64)))
    # sahte görünüm geçmişi gün'e keser; ham dizileri (bugünden sonrası çöp) doğrudan ver
    g = dataclasses.replace(g, satis_gecmisi=np.clip(sg, 0, 32000).astype(np.int16),
                            stoklu_gecmisi=st.copy(),
                            fiyat_gecmisi=_fiyat_gecmisi() if fiyat_gecmisi == "var" else fiyat_gecmisi,
                            **kw)
    return g


UFUK = np.arange(GUN, CIKIS)


def _haftalik(x: np.ndarray) -> np.ndarray:
    return np.add.reduceat(x, np.arange(0, len(x), 7), axis=0)


# ------------------------------------------------------------------ taban


def test_taban_tam_fiyata_cevirir():
    """S1 ve ONL'de son 14 gün yeterli: markdown (%30, son 10 gün) ve geçmiş kampanya çarpanına
    bölünmüş hız; ileriye hafta günü × özel gün (tatil) × yaşam oranıyla taşınır."""
    w = _dunya()
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(_g(w), 0, UFUK)
    beklenen = _haftalik(gercek_gunluk(w, 0, UFUK, fiyatsiz=True)) * OLCEK
    np.testing.assert_array_equal(hucre, np.flatnonzero(w.hucre_option == 0))
    assert d.shape == (len(range(0, len(UFUK), 7)), len(hucre))
    for m in (0, 3):
        j = w.hucre_magaza[hucre] == m
        np.testing.assert_allclose(d[:, j], beklenen[:, j], rtol=0.01)
    # tatil haftası: özel gün çarpanı yalnız o günde
    assert d[0, 0] / beklenen[0, 0] == pytest.approx(d[1, 0] / beklenen[1, 0], rel=1e-9)


def test_stoksuz_hucre():
    """S2 son 14 günde stoksuz, 15–28 gün önce stoklu: uzun pencere. S3 28 günde hiç stoksuz:
    option'ın zincir hızı × mağaza payı (payı test option'larının son 28 gün satışından)."""
    w = _dunya()
    g = _g(w)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(g, 0, UFUK)
    beklenen = _haftalik(gercek_gunluk(w, 0, UFUK, fiyatsiz=True)) * OLCEK
    mag = w.hucre_magaza[hucre]
    np.testing.assert_allclose(d[:, mag == 1], beklenen[:, mag == 1], rtol=0.01)
    # zincir: S1, S2, ONL'nin hızları toplamı × S3 payı ÷ (S1 + S2 + ONL payı)
    servis = np.isin(w.hucre_option, [0, 1, 2])
    satis = np.asarray(g.satis_gecmisi[GUN - 28:GUN], float)[:, servis].sum(0)
    pay_m = np.bincount(w.hucre_magaza[servis], satis, minlength=4)
    v = {m: TABAN[MAGAZA[m]] * OLCEK for m in (0, 1, 3)}
    v3 = sum(v.values()) * pay_m[2] / (pay_m[0] + pay_m[1] + pay_m[3])
    j = mag == 2
    oran = d[:, j] / (beklenen[:, j] / TABAN["S3"] * v3 / OLCEK * 1.0)
    np.testing.assert_allclose(oran, 1.0, rtol=0.02)
    assert (d[:, j] > 0).all()


def test_satissiz_option():
    """Stoklu ama hiç satmayan option: talep 0, NaN yok; satılabilir payı stoktan; çarpan tanımlı."""
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    g = _g()
    hucre, d = t.taban(g, 1, UFUK)
    assert np.isfinite(d).all() and (d == 0).all()
    X0, pay = t.satilabilir(g, 1, hucre, d)
    assert np.isfinite(pay).all() and pay.sum() == pytest.approx(1.0)
    assert X0 == pytest.approx(3 * 5 * 2 + 2 * 100)
    c, e = t.carpan(g, 1, UFUK, EPS)
    assert np.isfinite(c).all() and np.isfinite(e).all()


def test_hic_veri_yok_sifir_talep():
    """28 günde hiçbir hücresi stoklu olmayan option: zincir hızı yok, talep 0 (NaN değil)."""
    w = _dunya()
    sg, st = _gecmis(w)
    a = np.flatnonzero(w.hucre_option == 0)
    st[:GUN, a] = False
    sg[:GUN, a] = 0
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    _h, d = t.taban(_g(w, sg, st), 0, UFUK)
    assert np.isfinite(d).all() and (d == 0).all()


def test_tahmin_bugunu_gormez():
    """Bugün ve sonrasının satırları (satış, stoklu, satış öncesi, fiyat olayı) çıktıyı değiştirmez."""
    w = _dunya()
    sg, st = _gecmis(w)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    g1 = _g(w, sg, st)
    sg2, st2 = sg.copy(), st.copy()
    sg2[GUN:] = 123
    st2[GUN:] = False
    g2 = _g(w, sg2, st2)
    g2 = dataclasses.replace(g2, fiyat_gecmisi=_fiyat_gecmisi() + ((GUN, np.array([0]), np.array([0]),
                                                                     np.array([0.5])),))
    for o in (0, 1, 2):
        h1, d1 = t.taban(g1, o, UFUK)
        h2, d2 = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2]).taban(g2, o, UFUK)
        np.testing.assert_array_equal(d1, d2)
        np.testing.assert_array_equal(t.satilabilir(g1, o, h1, d1)[1], t.satilabilir(g2, o, h2, d2)[1])
        np.testing.assert_array_equal(t.carpan(g1, o, UFUK, EPS)[0], t.carpan(g2, o, UFUK, EPS)[0])


def test_satis_oncesi_varsa_tukenen_gun_disarida():
    """`satis_oncesi_gecmisi` kayıtlıysa gün içinde biten (satış ≥ satış öncesi) gün stoklu sayılmaz."""
    w = _dunya()
    sg, st = _gecmis(w)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    _h, d = t.taban(_g(w, sg, st), 0, UFUK)
    so = np.where(st, sg + 1000, 0)
    a1 = np.flatnonzero((w.hucre_option == 0) & (w.hucre_magaza == 0))
    gun = GUN - 3
    so[gun, a1] = sg[gun, a1]              # bitti: sansürlü
    sg_b = sg.copy()
    sg_b[gun, a1] = sg[gun, a1] // 3       # sansürlü gün düşük satış: dışarıda kalmalı
    so[gun, a1] = sg_b[gun, a1]
    g = _g(w, sg_b, st, satis_oncesi_gecmisi=so.astype(np.int32))
    _h, d_b = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2]).taban(g, 0, UFUK)
    j = np.isin(np.flatnonzero(w.hucre_option == 0), a1)
    np.testing.assert_allclose(d_b[:, j], d[:, j], rtol=0.01)


def test_fiyat_gecmisi_yoksa_simdiki_oran():
    """Geçmiş kaydı kapalıysa (`fiyat_gecmisi` None) geçmiş günlerin markdown'ı bugünkü oran sayılır:
    oran pencerede değişmediyse hız doğru çevrilir."""
    w = _dunya()
    C = len(w.hucre_magaza)
    sg = np.zeros((GUN + 30, C), np.int64)
    st = np.zeros((GUN + 30, C), bool)
    gunler = np.arange(GUN - 40, GUN)
    for o in (0, 2):
        h = np.flatnonzero(w.hucre_option == o)
        sg[np.ix_(gunler, h)] = np.round(gercek_gunluk(w, o, gunler, 0.3) * OLCEK)
        st[np.ix_(gunler, h)] = True
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(_g(w, sg, st, fiyat_gecmisi=None), 0, UFUK)
    beklenen = _haftalik(gercek_gunluk(w, 0, UFUK, fiyatsiz=True)) * OLCEK
    np.testing.assert_allclose(d, beklenen, rtol=0.01)


# ------------------------------------------------------------- satılabilir


def test_satilabilir_depo_paylasimi():
    """X0 = raf + yolda + depo; depo SKU'su hücrelerine ufuk talebi payıyla, ONL'nin rafı yok."""
    w = _dunya()
    C = len(w.hucre_magaza)
    raf = np.arange(C) % 4 + 2
    yolda = (np.arange(C) % 3).astype(np.int64)
    depo = np.array([50, 70, 10, 10, 30, 30, 5])
    g = _g(w, stok=raf, yolda=yolda, depo=depo)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(g, 0, UFUK)
    X0, pay = t.satilabilir(g, 0, hucre, d)
    onl = w.hucre_online[hucre]
    beklenen_x0 = (raf[hucre][~onl] + yolda[hucre][~onl]).sum() + depo[0] + depo[1]
    assert X0 == pytest.approx(beklenen_x0)
    assert pay.sum() == pytest.approx(1.0)
    D = d.sum(axis=0)
    sku = w.hucre_sku[hucre]
    for s in (0, 1):
        j = sku == s
        dagit = depo[s] * D[j] / D[j].sum()
        kendi = np.where(onl[j], 0, raf[hucre][j] + yolda[hucre][j])
        np.testing.assert_allclose(pay[j] * X0, kendi + dagit, rtol=1e-12)


def test_satilabilir_talep_yoksa_stok_payi_sonra_esit():
    w = _dunya()
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    C = len(w.hucre_magaza)
    raf = np.zeros(C, np.int64)
    g = _g(w, stok=raf, depo=np.zeros(7, np.int64))
    hucre = np.flatnonzero(w.hucre_option == 1)
    X0, pay = t.satilabilir(g, 1, hucre, np.zeros((3, len(hucre))))
    assert X0 == 0 and np.allclose(pay, 1 / len(hucre))
    raf[hucre[0]] = 4
    g = _g(w, stok=raf, depo=np.array([0, 0, 8, 0, 0, 0, 0]))
    X0, pay = t.satilabilir(g, 1, hucre, np.zeros((3, len(hucre))))
    assert X0 == 12
    # SKU 2 (hücre 0'ın SKU'su) depoyu kendi raf payıyla alır: 4 rafı olan tek hücre hepsini
    assert pay[0] * X0 == pytest.approx(12)


# ------------------------------------------------------------------ çarpan


def test_carpan_kampanya_ve_islem():
    w = _dunya()
    g = _g(w)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(g, 0, UFUK)
    c, e = t.carpan(g, 0, UFUK, EPS)
    K = np.array(tahmin.KADEMELER)
    assert c.shape == e.shape == (d.shape[0], len(K))
    # kampanyasız haftada: çarpan (1 − r)^(−ε), etkin oran r; r = 0'da işlem indirimi
    np.testing.assert_allclose(c[0], (1 - K) ** (-EPS), rtol=1e-12)
    np.testing.assert_allclose(e[0], np.where(K > 0, K, 0.024), rtol=1e-12)
    # ufuk kampanyası (2. hafta, Marmara mağazaları, %20): r = 0'da tahminin kendi taban talebiyle
    # ağırlıklı karışım (günlük ağırlıklar tek günlük ufuklardan)
    gunluk = np.vstack([t.taban(g, 0, [dd])[1] for dd in UFUK[7:14]])
    assert (gunluk > 0).all()
    kamp = np.array([[_kamp(int(w.hucre_magaza[c_]), 0, int(dd)) for c_ in hucre] for dd in UFUK[7:14]])
    m = (1 - kamp) ** (-EPS)
    c, e = t.carpan(g, 0, UFUK, EPS)        # (tek günlük çağrılar önbelleği değiştirdi)
    assert c[1, 0] == pytest.approx((gunluk * m).sum() / gunluk.sum(), rel=1e-12)
    assert c[1, 0] > 1.0
    oran = np.where(kamp > 0, kamp, 0.024)
    assert e[1, 0] == pytest.approx((gunluk * m * oran).sum() / (gunluk * m).sum(), rel=1e-12)
    # %30 ve üstü kampanyayı geçer: kampanyasız haftayla aynı
    np.testing.assert_allclose(c[1, 2:], c[0, 2:], rtol=1e-12)
    assert (np.diff(c, axis=1) > 0).all()


def test_kampanya_orani_motorunkiyle_ayni():
    """Tahminin kampanya oranı açık `kampanya` tablosundan; motorun `kampanya_orani`yla aynı kural."""
    from perakende_veri.v4.kampanya import kampanya_orani
    w = _dunya()
    k = pd.concat([w.kampanya, pd.DataFrame({
        "kampanya_id": ["K4", "K5"], "tip": ["ikinci_urun", "kategori"],
        "baslangic": [sabitler_tarih(GUN + 9), sabitler_tarih(GUN + 10)],
        "bitis": [sabitler_tarih(GUN + 11), sabitler_tarih(GUN + 30)],
        "kapsam_ust_kategori": ["", "Üst Giyim,Alt Giyim"], "kapsam_line": ["", "Collection"],
        "kapsam_bolge": ["", "Ege"], "oran": [0.25, 0.4]})], ignore_index=True)
    w = dataclasses.replace(w, kampanya=k) if dataclasses.is_dataclass(w) else AcikDunya(
        **{**w.__dict__, "kampanya": k})
    gunler = np.arange(GUN - 25, GUN + 50)
    for o in range(4):
        bizim = tahmin.kampanya_oranlari(k, w.magazalar, w.optionlar.iloc[o], gunler)
        motor = np.stack([kampanya_orani(k, int(d), w.magazalar, w.optionlar)[:, o] for d in gunler])
        np.testing.assert_allclose(bizim, motor, err_msg=str(o))


def test_iade_payi_talep_agirlikli():
    w = _dunya()
    g = _g(w)
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    hucre, d = t.taban(g, 0, UFUK)
    D = d.sum(axis=0)
    onl = w.hucre_online[hucre]
    beklenen = (D[onl].sum() * 0.27 + D[~onl].sum() * 0.06) / D.sum()
    assert t.iade_payi(g, 0, hucre, d) == pytest.approx(beklenen)
    _h, d1 = t.taban(g, 1, UFUK)
    assert t.iade_payi(g, 1, _h, d1) == pytest.approx(0.06 * 3 / 4 + 0.27 / 4)   # talep yok: hücre payı


def test_bos_ufuk():
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    g = _g()
    h, d = t.taban(g, 0, np.zeros(0, np.int64))
    assert d.shape == (0, len(h))
    c, e = t.carpan(g, 0, np.zeros(0, np.int64), EPS)
    assert c.shape == e.shape == (0, len(tahmin.KADEMELER))


def test_servis_disi_option_reddedilir():
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 2])
    with pytest.raises(KeyError):
        t.taban(_g(), 1, UFUK)


def test_hiz_olcumu_hizli():
    """210 option × bir pazartesi bütçesi: oyuncakta 3 option'ın taban + satılabilir + çarpanı < 50 ms."""
    import time
    g = _g()
    t = tahmin.Tahminci(_ogrenilen(), optionlar=[0, 1, 2])
    t.taban(g, 0, UFUK)
    t0 = time.perf_counter()
    for _ in range(10):
        for o in (0, 1, 2):
            h, d = t.taban(g, o, UFUK)
            t.satilabilir(g, o, h, d)
            t.carpan(g, o, UFUK, EPS)
    assert (time.perf_counter() - t0) / 10 < 0.05
