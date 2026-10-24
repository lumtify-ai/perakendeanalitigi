"""`markdown.politika`: kolların sözleşmeleri (spec §3.4–3.5; Ruling R6, R9, R12).

**Sarmalayıcı oyuncağı** (`_dunya`): dört option, gün ekseni 2022-07-04'ten.

    0  SS25-a  dalga 1  lansman 2025-02-10  indirim 2025-06-30 (pzt)  çıkış 2025-08-25
               serbest pencere max(05-05, 03-24) = 2025-05-05
    1  SS25-e  dalga 3  lansman 2025-04-21  aynı indirim/çıkış
               serbest pencere max(05-05, 06-02) = 2025-06-02 (RPT penceresinin sonu)
    2  AW24-a  dalga 1  lansman 2024-08-19  indirim 2025-01-02 (perşembe)  çıkış 2025-02-24
               serbest pencere 2024-11-07 (perşembe) -> 2024-11-11 pazartesi (R9); takvim 2025-01-02
    3  BAS-1   Basic (test dışı)

Sahte temel (`_temel`) Lumoda gibi bütün option'ların normal/online sütununu %20'ye, outlet sütununu
%50'ye yazar. Hücreler: option 0'ın S1, S2 ve ONL hücresi (tek SKU), Basic'in S1 hücresi.

Optimizasyon testleri `test_tahmin`'in oyuncağını (`_dunya`, `_g`, `_ogrenilen`) kullanır; indirim
günü GUN + 28, çıkış GUN + 84'e çekilir (serbest pencere GUN − 28 ≤ GUN).
"""

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest
from conftest import AcikDunya, gorunum, gun_indisi

from markdown import model, politika, tahmin
from markdown.sabitler import KADEMELER

L0, L1, L2 = gun_indisi("2025-02-10"), gun_indisi("2025-04-21"), gun_indisi("2024-08-19")
IND_SS, CIK_SS = gun_indisi("2025-06-30"), gun_indisi("2025-08-25")
IND_AW, CIK_AW = gun_indisi("2025-01-02"), gun_indisi("2025-02-24")
PEN = {0: gun_indisi("2025-05-05"), 1: gun_indisi("2025-06-02"), 2: gun_indisi("2024-11-11")}
TEST = np.array([0, 1, 2])


def _dunya() -> AcikDunya:
    opt = pd.DataFrame({
        "option_id": ["SS25-a", "SS25-e", "AW24-a", "BAS-1"],
        "sezon_kodu": ["SS25", "SS25", "AW24", "DEVAMLI"],
        "line": ["Collection"] * 3 + ["Basic"], "dalga": [1, 3, 1, 0],
        "lansman_gun": [L0, L1, L2, 0], "indirim_gun": [IND_SS, IND_SS, IND_AW, 10**6],
        "cikis_gun": [CIK_SS, CIK_SS, CIK_AW, 10**6], "sezonluk": [True, True, True, False],
        "ust_kategori": ["Üst Giyim"] * 4, "alt_kategori": ["Tişört"] * 4,
        "liste_fiyati": [500.0, 600.0, 700.0, 300.0],
    })
    return AcikDunya(optionlar=opt, hucre_option=np.array([0, 0, 0, 3]),
                     hucre_sku=np.array([0, 0, 0, 3]), hucre_magaza=np.array([0, 1, 2, 0]),
                     hucre_online=np.array([False, False, True, False]),
                     hucre_outlet_akisi=np.zeros(4, bool), sku_option=np.array([0, 1, 2, 3]))


def _temel(g):
    y = np.array(g.fiyat_orani, dtype=float, copy=True)
    y[:, [0, 2]] = 0.2
    y[:, 1] = 0.5
    return y


def _g(w, gun, fiyat_orani=None, **kw):
    C = len(w.hucre_option)
    sg = kw.pop("satis_gecmisi", np.zeros((gun, C), np.int64))
    st = kw.pop("stoklu_gecmisi", np.zeros((gun, C), bool))
    return gorunum(gun, kw.pop("stok", np.zeros(C, np.int64)), kw.pop("depo", np.zeros(4, np.int64)),
                   sg, st, np.zeros((4, 3)) if fiyat_orani is None else fiyat_orani, dunya=w, **kw)


def _kos(kol, w, gunler):
    """Motor gibi: her gün kolu çağırır, çıktıyı bir sonraki günün `fiyat_orani`sı yapar."""
    f = np.zeros((4, 3))
    cikti = {}
    for d in gunler:
        f = np.asarray(kol(_g(w, int(d), f)), dtype=float)
        cikti[int(d)] = f.copy()
    return cikti


def _pazartesiler(bas, son):
    return [d for d in range(bas, son) if d % 7 == 0]


class _Sayac:
    """Karar çağrılarını sayan sabit oranlı karar."""

    def __init__(self, oran):
        self.oran = oran
        self.cagri = []

    def __call__(self, g, oo, oran):
        self.cagri.append((int(g.gun), tuple(int(o) for o in oo)))
        hedef = self.oran(int(g.gun)) if callable(self.oran) else self.oran
        return np.full(len(oo), hedef, dtype=float), None


# ------------------------------------------------------------------ sarmalayıcı


def test_lumodaya_devir():
    """Test dışı option'ın her sütunu ve test option'larının outlet sütunu temelin çıktısıdır."""
    w = _dunya()
    kol = politika.Sarmalayici(_temel, TEST, _Sayac(0.7))
    for d in (IND_AW, PEN[0] - 7, PEN[0]):
        y = kol(_g(w, d))
        np.testing.assert_array_equal(y[3], [0.2, 0.5, 0.2])
        np.testing.assert_array_equal(y[TEST, 1], 0.5)


def test_pencere_oncesi_sifir():
    """Pencereden önce test option'larının normal/online oranı 0 (temel %20 yazsa da); karar çağrılmaz."""
    w = _dunya()
    karar = _Sayac(0.7)
    kol = politika.Sarmalayici(_temel, TEST, karar)
    gunler = range(PEN[2] - 21, PEN[2])
    for d, y in _kos(kol, w, gunler).items():
        np.testing.assert_array_equal(y[TEST][:, [0, 2]], 0.0, err_msg=str(d))
    assert karar.cagri == []


def test_pencere_rpt_sonrasi():
    """Serbest pencere `max(indirim − 56, lansman + 42)`'nin pazartesisi (R9): dalga 3 option'ı RPT
    penceresinin sonuna (06-02) kadar indirilmez; AW24 perşembesi bir sonraki pazartesiye yuvarlanır.
    Karar yalnız pazartesi ve pencere içinde; çıkıştan sonra karar yok."""
    w = _dunya()
    karar = _Sayac(0.7)
    kol = politika.Sarmalayici(_temel, TEST, karar)
    cikti = _kos(kol, w, range(PEN[2] - 7, CIK_SS + 14))
    for o in TEST:
        ilk = min(d for d, y in cikti.items() if y[o, 0] > 0)
        assert ilk == PEN[o], (o, ilk)
        assert cikti[ilk][o, 2] == 0.7
    for d, oo in karar.cagri:
        assert d % 7 == 0
        for o in oo:
            assert PEN[o] <= d < (CIK_AW if o == 2 else CIK_SS)
    # takvim penceresi: indirim günü (yuvarlamasız); perşembe karar günü değil -> ilk karar pazartesi
    kol = politika.Sarmalayici(_temel, TEST, _Sayac(0.4), pencere="takvim")
    cikti = _kos(kol, w, range(IND_AW - 7, IND_AW + 14))
    ilk = min(d for d, y in cikti.items() if y[2, 0] > 0)
    assert ilk == IND_AW + (7 - IND_AW % 7) % 7 and ilk % 7 == 0


def test_takvim_tabani():
    """Takvim tabanı indirim gününden (perşembe dahil) çıkışa: oran en az %30; öncesi 0."""
    w = _dunya()
    kol = politika.Sarmalayici(_temel, TEST, _Sayac(0.0), pencere="takvim", taban=0.3)
    cikti = _kos(kol, w, range(IND_AW - 10, IND_AW + 10))
    for d, y in cikti.items():
        assert y[2, 0] == y[2, 2] == (0.3 if d >= IND_AW else 0.0), d
        assert y[0, 0] == 0.0                                 # SS25'in indirimi daha gelmedi
    cikti = _kos(kol, w, range(IND_SS - 3, IND_SS + 3))
    assert all(y[0, 0] == (0.3 if d >= IND_SS else 0.0) for d, y in cikti.items())


def test_pazartesi_disi_cagri():
    """Pazartesi olmayan çağrı (AW24 indirim perşembesi): karar yok; yalnız takvim kolunun tabanı."""
    w = _dunya()
    assert IND_AW % 7 != 0
    karar = _Sayac(0.7)
    serbest = politika.Sarmalayici(_temel, TEST, karar)
    _kos(serbest, w, [IND_AW - 3])                            # pazartesi: 0,7
    y = serbest(_g(w, IND_AW))
    assert karar.cagri == [(IND_AW - 3, (2,))]
    np.testing.assert_array_equal(y[TEST, 0], [0.0, 0.0, 0.7])
    takvim = politika.Sarmalayici(_temel, TEST, _Sayac(0.0), pencere="takvim", taban=0.3)
    y = takvim(_g(w, IND_AW))
    np.testing.assert_array_equal(y[TEST, 0], [0.0, 0.0, 0.3])


def test_sigilasmaz():
    """İç durum geri alınmaz: daha sığ karar yok sayılır; oran geçmişi yalnız değişimleri kaydeder."""
    w = _dunya()
    karar = _Sayac(lambda d: 0.5 if d < PEN[0] + 14 else 0.2)
    kol = politika.Sarmalayici(_temel, TEST, karar)
    cikti = _kos(kol, w, _pazartesiler(PEN[0], PEN[0] + 35))
    assert [y[0, 0] for y in cikti.values()] == [0.5] * 5
    gunler, oranlar = kol.oran_gecmisi(0)
    np.testing.assert_array_equal(gunler, [PEN[0]])
    np.testing.assert_array_equal(oranlar, [0.5])
    gunler, oranlar = kol.oran_gecmisi(1)                     # dalga 3: kendi penceresinde
    np.testing.assert_array_equal(gunler, [PEN[1]])
    with pytest.raises(KeyError):
        kol.oran_gecmisi(3)
    with pytest.raises(ValueError, match="geri"):             # kol bir koşu içindir
        kol(_g(w, PEN[0]))


def test_merdiven_sigdirma():
    """Merdiven dışı oran üstteki basamağa (en çok %70) sığdırılır."""
    w = _dunya()
    for hedef, beklenen in ((0.25, 0.3), (0.65, 0.7), (0.9, 0.7), (0.0, 0.0), (0.2, 0.2)):
        kol = politika.Sarmalayici(_temel, TEST, _Sayac(hedef))
        assert kol(_g(w, PEN[0]))[0, 0] == beklenen
    assert set(np.round(politika.merdivene(np.linspace(0, 1, 41)), 12)) <= set(KADEMELER)


def test_kayit_tablosu():
    """Kayıt: her (pazartesi, penceredeki test option'ı) bir satır; oran kararın sonucu."""
    w = _dunya()

    def karar(g, oo, oran):
        n = len(oo)
        return np.full(n, 0.3), {"tahmini_satis": np.arange(n) + 1.0, "satilabilir": np.full(n, 9.0),
                                 "beklenen_kalan": np.full(n, 2.0)}

    kol = politika.Sarmalayici(_temel, TEST, karar)
    gunler = range(PEN[0] - 3, PEN[1] + 3)
    _kos(kol, w, gunler)
    k = kol.kayit_tablosu()
    assert list(k.columns) == list(politika.KAYIT_SUTUNLARI)
    beklenen = [(d, o) for d in _pazartesiler(PEN[0] - 3, PEN[1] + 3)
                for o in TEST if PEN[o] <= d < (CIK_AW if o == 2 else CIK_SS)]
    assert list(zip(k["gun"], k["option"])) == beklenen
    assert (k["oran"] == 0.3).all() and (k["satilabilir"] == 9.0).all()
    assert k["gun"].dtype == np.int64 and k["option"].dtype == np.int64
    # ek bilgi vermeyen karar: sayısal sütunlar NaN
    kol = politika.Sarmalayici(_temel, TEST, _Sayac(0.2))
    _kos(kol, w, [PEN[0]])
    assert kol.kayit_tablosu()["tahmini_satis"].isna().all()


def test_tekduze():
    """Tekdüze: indirim gününden (perşembe dahil) çıkışa aynı oran; öncesi 0; merdiven dışı reddedilir."""
    w = _dunya()
    kol = politika.Tekduze(_temel, TEST, 0.4)
    cikti = _kos(kol, w, range(IND_AW - 5, IND_AW + 9))
    for d, y in cikti.items():
        assert y[2, 0] == (0.4 if d >= IND_AW else 0.0)
    assert set(kol.kayit_tablosu()["gun"]) == {d for d in cikti if d % 7 == 0 and d >= IND_AW}
    with pytest.raises(ValueError):
        politika.Tekduze(_temel, TEST, 0.35)


# ------------------------------------------------------------------ kural


def _kural_g(w, gun, *, depo=300, siparis=100, hiz_ayri=True, **kw):
    """Option 0: S1 her gün 1 satar (14 gün stoklu), S2 son 14 günün 7'sinde stoklu ve o günler
    2 satar, ONL her gün 1. Hız 1 + 2 + 1 = 4/gün. Raf S1 10 (+5 yolda), S2 10; depo SKU 0 `depo`;
    açık RPT siparişi `siparis` adet."""
    C = 4
    sg = np.zeros((gun, C), np.int64)
    st = np.zeros((gun, C), bool)
    sg[gun - 14:, 0], st[gun - 14:, 0] = 1, True
    if hiz_ayri:
        st[gun - 14:gun - 7, 1] = True
        sg[gun - 14:gun - 7, 1] = 2
    sg[gun - 14:, 2], st[gun - 14:, 2] = 1, True
    sip = ({"tip": "rpt", "option": 0, "siparis_gun": gun - 20, "planlanan_gun": gun + 10,
            "skular": np.array([0]), "adetler": np.array([siparis]), "tedarikci": 0},) if siparis else ()
    return _g(w, gun, satis_gecmisi=sg, stoklu_gecmisi=st, stok=kw.pop("stok", np.array([10, 10, 0, 3])),
              yolda=np.array([5, 0, 0, 0]), depo=np.array([depo, 0, 0, 7]), acik_siparisler=sip, **kw)


def test_kural_kapsama():
    """Kapsama = (raf + yolda + depo + açık sipariş) ÷ stoklu gün hızı; kalan güne oranı α'yı aşarsa
    bir kademe (ilk indirim de), aşmazsa yerinde; hiç aşmayan indirilmez."""
    w = _dunya()
    d = PEN[0]
    kalan = CIK_SS - d
    X = 10 + 5 + 10 + 300 + 100
    oran = X / 4.0 / kalan                                    # 0,949
    assert 0.9 < oran < 0.95
    k = politika.Kural(_temel, TEST, alfa=0.9)
    assert k(_kural_g(w, d))[0, 0] == 0.2                     # ilk indirim bir kademe
    assert k(_kural_g(w, d + 7))[0, 0] == 0.3                 # haftada en fazla bir
    satir = k.kayit_tablosu().iloc[0]
    assert satir["satilabilir"] == X
    assert satir["tahmini_satis"] == pytest.approx(min(X, 4.0 * kalan))
    assert satir["beklenen_kalan"] == pytest.approx(X - min(X, 4.0 * kalan))
    assert politika.Kural(_temel, TEST, alfa=1.0)(_kural_g(w, d))[0, 0] == 0.0     # ≤ α: yerinde
    # açık sipariş ve depo sayılır (Lumoda'nın kör noktası): siparişsiz oran 0,726 ≤ 0,8
    assert politika.Kural(_temel, TEST, alfa=0.8)(_kural_g(w, d))[0, 0] == 0.2
    assert politika.Kural(_temel, TEST, alfa=0.8)(_kural_g(w, d, siparis=0))[0, 0] == 0.0
    # hiç aşmayan: depo ve sipariş yok, kapsama 25 ÷ 4 gün; son pazartesi bile 6,25 ÷ 7 < 1
    k = politika.Kural(_temel, TEST, alfa=1.0)
    for gun in _pazartesiler(d, CIK_SS):
        assert k(_kural_g(w, gun, depo=0, siparis=0))[0, 0] == 0.0
    # hız 0, stok var: kapsama sonsuz -> derinleşir; stok 0: derinleşmez
    k = politika.Kural(_temel, TEST, alfa=2.0)
    g0 = _kural_g(w, d)
    g0 = dataclasses.replace(g0, satis_gecmisi=np.zeros_like(g0.satis_gecmisi))
    assert k(g0)[0, 0] == 0.2
    k = politika.Kural(_temel, TEST, alfa=0.1)
    assert k(_kural_g_bos(w, d))[0, 0] == 0.0


def _kural_g_bos(w, d):
    g = _kural_g(w, d, depo=0, siparis=0, stok=np.array([0, 0, 0, 3]))
    return dataclasses.replace(g, yolda=np.zeros(4, np.int64))


# ------------------------------------------------------------------ optimizasyon


@pytest.fixture
def tt():
    import test_tahmin
    return test_tahmin


def _opt_dunya(tt):
    w = tt._dunya()
    o = w.optionlar
    o.loc[:2, "indirim_gun"] = tt.GUN + 28
    o.loc[:2, "cikis_gun"] = tt.GUN + 84
    return w


@pytest.mark.parametrize("depo,indirilen", [(100, set()), (200_000, {0, 2})])
def test_optimizasyon_coz_ile_ayni(tt, depo, indirilen):
    """Pazartesi kararı `model.coz`'un ilk haftası; girdiler kolun kendi oran geçmişiyle kurulan
    tahminciden (R12); kayıt satırı çözümün beklenen satışı ve kalanı. Az stokta indirim yok; çok
    stokta (depo 200 bin) satan iki option indirilir, satmayan (talep 0) indirilmez."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()
    kol = politika.Optimizasyon(_temel, [0, 1, 2], og, kip="serbest", eps="kampanya")
    y = kol(tt._g(w, depo=np.full(7, depo)))
    assert {o for o in (0, 1, 2) if y[o, 0] > 0} == indirilen
    t = tahmin.Tahminci(og, [0, 1, 2], oran_gecmisi=lambda o: (np.zeros(0, np.int64), np.zeros(0)))
    g = tt._g(w, depo=np.full(7, depo))
    k = kol.kayit_tablosu().set_index("option")
    for o in (0, 1, 2):
        ufuk = np.arange(tt.GUN, tt.GUN + 84)
        h, d = t.taban(g, o, ufuk)
        X0, pay = t.satilabilir(g, o, h, d)
        c, e = t.carpan(g, o, ufuk, t.option_eps(g, o))
        z = model.coz(d, pay, X0, float(w.optionlar["liste_fiyati"][o]), c, e, 0,
                      np.ones_like(c, bool), t.iade_payi(g, o, h, d), og.kalinti)
        assert y[o, 0] == y[o, 2] == KADEMELER[z.kademe[0]]
        assert k.loc[o, "tahmini_satis"] == pytest.approx(z.beklenen_satis.sum())
        assert k.loc[o, "beklenen_kalan"] == pytest.approx(z.beklenen_kalan)
        assert k.loc[o, "satilabilir"] == pytest.approx(X0)


def test_optimizasyon_tuzak_esnekligi(tt, monkeypatch):
    """eps = "markdown": çevirme ve fiyat çarpanı ε̂_markdown'la."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()
    kullanilan = []
    asil = tahmin.Tahminci.carpan

    def casus(self, g, o, ufuk, eps, agirlik=None):
        kullanilan.append((self.eps_tablosu, eps))
        return asil(self, g, o, ufuk, eps, agirlik)

    monkeypatch.setattr(tahmin.Tahminci, "carpan", casus)
    politika.Optimizasyon(_temel, [0, 1, 2], og, kip="serbest", eps="markdown")(tt._g(w))
    assert kullanilan and all(t == og.eps_markdown and e == pytest.approx(1.2) for t, e in kullanilan)


@pytest.mark.parametrize("kip,karar_gunde,taban_haftasi", [
    ("serbest", True, None), ("taban", True, 4), ("erken_yok", False, None), ("takvim", False, None)])
def test_optimizasyon_kipleri(tt, monkeypatch, kip, karar_gunde, taban_haftasi):
    """Kip anlamı (spec §3.4): serbest ve taban GUN'de (indirimden 4 hafta önce) karar verir; taban
    kipinde indirim gününden başlayan haftalar ≥ %30; erken_yok ve takvim indirim gününe kadar karar
    vermez; indirim günü takvim kolu ≥ %30, erken_yok tabansız."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()
    izinler = []
    asil = model.coz

    def casus(*a, **k):
        izinler.append(np.asarray(k["izinli"] if "izinli" in k else a[7]))
        return asil(*a, **k)

    monkeypatch.setattr(politika.model, "coz", casus)
    kol = politika.Optimizasyon(_temel, [0, 1, 2], og, kip=kip, eps="kampanya")
    y = kol(tt._g(w))
    assert bool(izinler) == karar_gunde
    if not karar_gunde:
        np.testing.assert_array_equal(y[:3, [0, 2]], 0.0)
    for iz in izinler:
        assert iz.shape == (12, len(KADEMELER))
        if taban_haftasi is None:
            assert iz.all()
        else:
            assert iz[:taban_haftasi].all()
            np.testing.assert_array_equal(iz[taban_haftasi:], np.broadcast_to(
                np.array(KADEMELER) >= 0.3 - 1e-9, iz[taban_haftasi:].shape))
    # indirim günü (pazartesi): geçmiş satış dizileri GUN'den sonrası çöp (7777) ama kip kuralı tutar
    izinler.clear()
    g = dataclasses.replace(tt._g(w), gun=tt.GUN + 28, tarih=tt._g(w).tarih + pd.Timedelta(days=28))
    y = kol(g)
    assert izinler
    if kip in ("takvim", "taban"):
        assert (y[:3, 0] >= 0.3).all()
        assert all(np.array_equal(iz, np.broadcast_to(np.array(KADEMELER) >= 0.3 - 1e-9, iz.shape))
                   for iz in izinler)
    else:
        assert all(iz.all() for iz in izinler)


def test_optimizasyon_oran_gecmisi_tahminciye(tt):
    """Kolun oran kaydı tahminciye gider (R12): kararın oranı sonraki pazartesinin çevirmesinde."""
    w = _opt_dunya(tt)
    kol = politika.Optimizasyon(_temel, [0, 1, 2], tt._ogrenilen(), kip="serbest", eps="kampanya")
    assert kol.tahminci.oran_gecmisi == kol.oran_gecmisi
    y = kol(tt._g(w, depo=np.full(7, 200_000)))
    assert y[0, 0] > 0
    gunler, oranlar = kol.oran_gecmisi(0)
    np.testing.assert_array_equal(gunler, [tt.GUN])
    np.testing.assert_array_equal(oranlar, [y[0, 0]])
    assert len(kol.oran_gecmisi(1)[0]) == 0


# ------------------------------------------------------------------ kahin


def _girdi(tt, w, taban=1.0, eps=1.8, gunler=None, hucre=None):
    hucre = np.flatnonzero(np.isin(w.hucre_option, [0, 1, 2]) & ~w.hucre_outlet_akisi) \
        if hucre is None else hucre
    gunler = np.arange(tt.GUN, tt.GUN + 84) if gunler is None else gunler
    t = np.broadcast_to(np.asarray(taban, float), (len(gunler), len(hucre))).copy()
    return politika.KahinGirdisi(hucre=hucre, gunler=gunler, taban=t,
                                 eps=np.broadcast_to(np.asarray(eps, float), (len(hucre),)).copy())


def test_kahin_gizli_okumaz(tt, monkeypatch):
    """Kahin talebi ve esnekliği yalnız argümanından (`KahinGirdisi`) alır: tahmincinin taban
    tahmini çağrılmaz; DP'nin haftalık talebi girdinin toplamı; fiyat çarpanı hücre çarpanlarının
    talep ağırlıklı ortalaması (ortalama ε'nin çarpanı değil);
    dünya yalnız açık alanlı (`AcikDunya`)."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()

    def yasak(*a, **k):
        raise AssertionError("kahin tahmini kullanmamalı")

    monkeypatch.setattr(tahmin.Tahminci, "taban", yasak)
    yakalanan = []
    asil = model.coz
    monkeypatch.setattr(politika.model, "coz", lambda *a, **k: yakalanan.append((a, k)) or asil(*a, **k))
    hucre = np.flatnonzero(np.isin(w.hucre_option, [0, 1, 2]))
    eps = np.where(w.hucre_option[hucre] == 0, np.where(w.hucre_online[hucre], 3.0, 1.0), 2.0)
    taban = np.where(w.hucre_online[hucre], 3.0, 1.0)[None, :] * np.ones((84, 1))
    girdi = politika.KahinGirdisi(hucre=hucre, gunler=np.arange(tt.GUN, tt.GUN + 84), taban=taban, eps=eps)
    kol = politika.Kahin(_temel, [0, 1, 2], og, girdi)
    kol(tt._g(w))
    assert len(yakalanan) == 3
    d0 = yakalanan[0][0][0]
    h0 = np.flatnonzero(w.hucre_option == 0)
    np.testing.assert_allclose(d0, np.add.reduceat(taban[:, np.isin(hucre, h0)], np.arange(0, 84, 7)))
    # option 0: ONL hücreleri talebin 3 katı, ε 3; fiziksel ε 1 -> hücre çarpanlarının talep ağırlıklı
    # ortalaması (ilk hafta kampanyasız); ortalama ε (2,0) çarpanı derin basamakta daha düşük kalırdı
    on = w.hucre_online[h0]
    K = np.array(KADEMELER)
    a_on, a_fiz = 3.0 * on.sum(), 1.0 * (~on).sum()
    beklenen = (a_on * (1 - K) ** -3.0 + a_fiz * (1 - K) ** -1.0) / (a_on + a_fiz)
    carpan = yakalanan[0][0][4]
    np.testing.assert_allclose(carpan[0], beklenen, rtol=1e-12)
    ort_eps = (a_on * 3.0 + a_fiz * 1.0) / (a_on + a_fiz)
    assert (carpan[0, 1:] > (1 - K[1:]) ** -ort_eps).all()


def test_kahin_girdisi_eksikse_hata(tt):
    w = _opt_dunya(tt)
    og = tt._ogrenilen()
    with pytest.raises(ValueError, match="gün"):
        politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w, gunler=np.arange(tt.GUN, tt.GUN + 50)))(tt._g(w))
    eksik = np.flatnonzero(np.isin(w.hucre_option, [0, 1]))
    with pytest.raises(ValueError, match="hücre"):
        politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w, hucre=eksik))(tt._g(w))
    with pytest.raises(ValueError):
        politika.KahinGirdisi(hucre=np.arange(3), gunler=np.arange(2), taban=np.zeros((2, 2)), eps=np.ones(3))


def test_kahin_girdisi_kimlik(tt):
    w = _opt_dunya(tt)
    a = _girdi(tt, w)
    assert a.kimlik() == _girdi(tt, w).kimlik()
    assert a.kimlik() != _girdi(tt, w, taban=1.0000001).kimlik()
    assert a.kimlik() != _girdi(tt, w, eps=1.81).kimlik()
    assert a.kimlik() != _girdi(tt, w, gunler=np.arange(tt.GUN + 1, tt.GUN + 85)).kimlik()


# ------------------------------------------------------------------ parametreler


def test_parametreler_kanonik(tt):
    """`parametreler()` JSON'a gidip dönen sözlük; davranışı değiştiren her şeyle değişir (öğrenilenin
    içeriği, kip, ε kaynağı, α, tekdüze oran, kahin girdisi, test option'ları)."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()

    def anahtar(kol):
        p = kol.parametreler()
        assert json.loads(json.dumps(p, sort_keys=True)) == p
        return json.dumps(p, sort_keys=True)

    temel = anahtar(politika.Optimizasyon(_temel, [0, 1, 2], og, kip="serbest", eps="kampanya"))
    p = json.loads(temel)
    assert p["kol"] == "optimizasyon" and p["kip"] == "serbest" and p["eps"] == "kampanya"
    assert p["ogrenilen"] == og.kimlik() and p["test_optionlari"] == [0, 1, 2]
    degisik = dataclasses.replace(og, kalinti=og.kalinti + 1e-9)
    farkli = {
        anahtar(politika.Optimizasyon(_temel, [0, 1, 2], degisik, kip="serbest", eps="kampanya")),
        anahtar(politika.Optimizasyon(_temel, [0, 1, 2], og, kip="takvim", eps="kampanya")),
        anahtar(politika.Optimizasyon(_temel, [0, 1, 2], og, kip="serbest", eps="markdown")),
        anahtar(politika.Optimizasyon(_temel, [0, 1], og, kip="serbest", eps="kampanya")),
        anahtar(politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w))),
        anahtar(politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w, taban=2.0))),
        anahtar(politika.Kural(_temel, [0, 1, 2], alfa=1.25)),
        anahtar(politika.Kural(_temel, [0, 1, 2], alfa=1.5)),
        anahtar(politika.Tekduze(_temel, [0, 1, 2], 0.3)),
        anahtar(politika.Tekduze(_temel, [0, 1, 2], 0.4)),
    }
    assert len(farkli) == 10 and temel not in farkli
    k = json.loads(anahtar(politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w))))
    assert k["kol"] == "kahin" and k["kahin_girdisi"] == _girdi(tt, w).kimlik()
    with pytest.raises(ValueError):
        politika.Optimizasyon(_temel, [0, 1, 2], og, kip="yanlis", eps="kampanya")
    with pytest.raises(ValueError):
        politika.Optimizasyon(_temel, [0, 1, 2], og, kip="serbest", eps="saf")


def test_kahin_karari_girdiden(tt):
    """Aynı stokta kararı girdinin talebi belirler: az talep derin indirim, bol talep indirimsiz."""
    w = _opt_dunya(tt)
    og = tt._ogrenilen()
    g = tt._g(w, depo=np.full(7, 2000))
    az = politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w, taban=0.5))(g)
    bol = politika.Kahin(_temel, [0, 1, 2], og, _girdi(tt, w, taban=5.0))(g)
    np.testing.assert_array_equal(az[:3, 0], 0.7)
    np.testing.assert_array_equal(bol[:3, 0], 0.0)
