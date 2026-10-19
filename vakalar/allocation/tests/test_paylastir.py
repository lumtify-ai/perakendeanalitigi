"""`allocation.paylastir`: paket içeriği, gönderilebilir üst sınır U, aday maskesi, paylaştırma.

Oyuncak dünya (`conftest`): option 2 (OPT-A, Erkek Harf, SKU 10..14), option 5 (OPT-X, Aksesuar
tek beden, SKU 25); mağazalar M1..M4 (fiziksel), MO (Outlet), ONL."""

import copy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from allocation import paylastir, sabitler
from allocation.kaynak import harita_kur
from allocation.paylastir import TAVANSIZ, paylastir as dagit

M = 6   # oyuncak dünyada mağaza: M1 M2 M3 M4 MO ONL
SKU_A = slice(10, 15)    # OPT-A'nın bedenleri
SKU_X = 25               # OPT-X (aksesuar)


def _gorunum(w, depo=None, kapanacak=(), kapali=()):
    """Karar anının açık görünümü: `depo` [S], kapanış kararlı ve bugün kapalı mağaza indisleri."""
    S, Mm = len(w.urunler), len(w.magazalar)
    k = np.zeros(Mm, dtype=bool)
    k[list(kapanacak)] = True
    a = np.ones(Mm, dtype=bool)
    a[list(kapali)] = False
    return SimpleNamespace(dunya=w, depo=np.full(S, 10**6) if depo is None else depo,
                           kapanacak=k, acik_magaza=a)


def _dunya_ilk_alim(w, o, adet):
    w2 = copy.copy(w)
    w2.ilk_alim = w.ilk_alim.copy()
    w2.ilk_alim[o] = adet
    return w2


# ---------------------------------------------------------------------------
# Paket içeriği
# ---------------------------------------------------------------------------


def test_paket_icerigi(dunya):
    np.testing.assert_array_equal(paylastir.paket_icerigi(dunya, 2), [1, 2, 2, 1, 1])
    np.testing.assert_array_equal(paylastir.paket_icerigi(dunya, 0), [1, 2, 2, 1, 1])
    np.testing.assert_array_equal(paylastir.paket_icerigi(dunya, 5), [6])      # aksesuar tek beden
    assert paylastir.paket_adedi(dunya, 2) == 7
    assert paylastir.paket_adedi(dunya, 5) == 6


def test_paket_icerigi_beden_sirasina_gore(dunya):
    w = copy.copy(dunya)
    p = dunya.paketler.iloc[::-1].reset_index(drop=True)      # satır sırası ters
    w.paketler = p
    np.testing.assert_array_equal(paylastir.paket_icerigi(w, 2), [1, 2, 2, 1, 1])
    p = dunya.paketler.copy()
    p.loc[p["beden_seti"] == "Erkek Harf", "adet"] = [3, 1, 4, 1, 5]
    w.paketler = p
    np.testing.assert_array_equal(paylastir.paket_icerigi(w, 2), [3, 1, 4, 1, 5])
    assert paylastir.paket_adedi(w, 2) == 14


# ---------------------------------------------------------------------------
# Gönderilebilir üst sınır U
# ---------------------------------------------------------------------------


def _depo_bedenler(w, depo_a):
    depo = np.full(len(w.urunler), 10**6)
    depo[SKU_A] = depo_a
    return depo


def test_ust_sinir_en_kucuk_beden_baglar(dunya):
    """İlk alım 1.000, bedenler 10/22/32/24/12 -> 100 paket; en küçük bedende depo 90 -> 90."""
    w = _dunya_ilk_alim(dunya, 2, 1000)
    h = harita_kur(w)
    depo = _depo_bedenler(w, [100, 220, 320, 240, 120])
    assert paylastir.ust_sinir(_gorunum(w, depo), 2, h) == 100
    depo[10] = 90
    assert paylastir.ust_sinir(_gorunum(w, depo), 2, h) == 90
    depo[10] = 100
    depo[11] = 150          # ikinci beden pakette 2 adet: ⌊150 / 2⌋ = 75
    assert paylastir.ust_sinir(_gorunum(w, depo), 2, h) == 75
    depo[11] = 220
    depo[14] = 99           # son beden
    assert paylastir.ust_sinir(_gorunum(w, depo), 2, h) == 99


def test_ust_sinir_lumoda_payi_baglar(dunya):
    h = harita_kur(dunya)
    w = _dunya_ilk_alim(dunya, 2, 1004)
    assert paylastir.ust_sinir(_gorunum(w), 2, h) == 100            # ⌊1004 × 0,70 ÷ 7⌋ = ⌊100,4⌋
    w = _dunya_ilk_alim(dunya, 2, 1000)
    assert paylastir.ust_sinir(_gorunum(w), 2, h) == 100
    # Lumoda payı depo yetmediğinde değil, yettiğinde bağlar: depo bol, U = payın tavanı
    depo = _depo_bedenler(w, [10**5] * 5)
    assert paylastir.ust_sinir(_gorunum(w, depo), 2, h) == 100


def test_ust_sinir_tam_sayi_aritmetigi(dunya):
    """ilk alım × 0,70 ÷ paket adedi tam bölünürken kayan nokta 1 eksik verir
    (700 × 0,70 = 489,99… // 7 = 69 değil, 70); U tam sayı hesabıyla 70."""
    assert 700 * 0.70 // 7 == 69.0            # kayan nokta tuzağının kendisi
    w = _dunya_ilk_alim(dunya, 2, 700)
    assert paylastir.ust_sinir(_gorunum(w), 2, harita_kur(w)) == 70
    assert isinstance(paylastir.ust_sinir(_gorunum(w), 2, harita_kur(w)), int)


def test_ust_sinir_aksesuar_tek_beden(dunya):
    h = harita_kur(dunya)
    assert dunya.ilk_alim[5] == 600
    assert paylastir.ust_sinir(_gorunum(dunya), 5, h) == 70       # ⌊600 × 0,70 ÷ 6⌋
    depo = np.full(len(dunya.urunler), 10**6)
    depo[SKU_X] = 25
    assert paylastir.ust_sinir(_gorunum(dunya, depo), 5, h) == 4  # ⌊25 ÷ 6⌋


def test_ust_sinir_depo_bos(dunya):
    h = harita_kur(dunya)
    depo = _depo_bedenler(dunya, [100, 100, 0, 100, 100])
    assert paylastir.ust_sinir(_gorunum(dunya, depo), 2, h) == 0


def test_ust_sinir_pay_sabitinden(dunya, monkeypatch):
    """Pay `sabitler.LUMODA_ILK_PAYI`'ndan okunur (sabit değişirse U değişir)."""
    w = _dunya_ilk_alim(dunya, 2, 1000)
    monkeypatch.setattr(sabitler, "LUMODA_ILK_PAYI", 0.5)
    assert paylastir.ust_sinir(_gorunum(w), 2, harita_kur(w)) == 71       # ⌊500 ÷ 7⌋


# ---------------------------------------------------------------------------
# Aday maskesi
# ---------------------------------------------------------------------------


def test_aday_maskesi_varsayilan(dunya):
    h = harita_kur(dunya)
    g = _gorunum(dunya)
    np.testing.assert_array_equal(paylastir.aday_maskesi(g, 2, h), [1, 1, 1, 1, 0, 0])
    # Outlet option'ının tek fiziksel hücresi (MO) outlet akışı: aday yok
    assert not paylastir.aday_maskesi(g, 4, h).any()
    assert paylastir.aday_maskesi(g, 5, h).dtype == bool


def test_aday_maskesi_kapanis_karari(dunya):
    h = harita_kur(dunya)
    np.testing.assert_array_equal(
        paylastir.aday_maskesi(_gorunum(dunya, kapanacak=[1]), 2, h), [1, 0, 1, 1, 0, 0])


def test_aday_maskesi_acilis_ve_kapanis_tarihi(dunya):
    h = harita_kur(dunya)
    lansman = dunya.optionlar["lansman_tarihi"].iloc[2]
    w = copy.copy(dunya)
    m = dunya.magazalar.copy()
    m.loc[0, "acilis_tarihi"] = lansman + pd.Timedelta(days=30)    # M1: lansmandan sonra açılıyor
    m.loc[1, "acilis_tarihi"] = lansman - pd.Timedelta(days=5)     # M2: lansmandan önce açılacak
    m.loc[2, "kapanis_tarihi"] = lansman                           # M3: lansman gününde kapanıyor
    m.loc[3, "kapanis_tarihi"] = lansman + pd.Timedelta(days=1)    # M4: lansmandan sonra kapanıyor
    w.magazalar = m
    # bugün hepsi kapalı: yalnız lansmana kadar açılacak ve lansmandan önce kapanmayanlar
    g = _gorunum(w, kapali=[0, 1, 2, 3])
    np.testing.assert_array_equal(paylastir.aday_maskesi(g, 2, h), [0, 1, 0, 1, 0, 0])
    # bugün açık: açılış tarihi aranmaz, kapanış tarihi yine eler
    g = _gorunum(w)
    np.testing.assert_array_equal(paylastir.aday_maskesi(g, 2, h), [1, 1, 0, 1, 0, 0])


def test_aday_maskesi_cikis_yok_acilis_nat(dunya):
    h = harita_kur(dunya)
    w = copy.copy(dunya)
    m = dunya.magazalar.copy()
    m["acilis_tarihi"] = pd.NaT
    w.magazalar = m
    g = _gorunum(w, kapali=[0])
    np.testing.assert_array_equal(paylastir.aday_maskesi(g, 2, h), [0, 1, 1, 1, 0, 0])


# ---------------------------------------------------------------------------
# Paylaştırma
# ---------------------------------------------------------------------------


def _hepsi(n):
    return np.ones(n, dtype=bool)


def test_paylastir_en_buyuk_kalan():
    # hedefler 3,5 / 2,1 / 1,4 -> tabanlar 3,2,1; kalan 1 en büyük kesre (0,5) gider
    s = dagit(7, np.array([5., 3., 2.]), _hepsi(3), en_az_gosterim=False)
    np.testing.assert_array_equal(s, [4, 2, 1])
    # kesirler eşit: önce gelen indis kazanır
    s = dagit(10, np.ones(3), _hepsi(3), en_az_gosterim=False)
    np.testing.assert_array_equal(s, [4, 3, 3])
    s = dagit(11, np.ones(3), _hepsi(3), en_az_gosterim=False)
    np.testing.assert_array_equal(s, [4, 4, 3])
    assert s.dtype == np.int64


def test_paylastir_esitlik_kayan_nokta_gurultusunde_indise_gider():
    pay = np.array([0.1, 0.2, 0.3, 0.4, 0.1, 0.2, 0.3, 0.4])      # çiftler kayan noktada ayrışır
    s = dagit(5, pay, _hepsi(8), en_az_gosterim=False)
    np.testing.assert_array_equal(s, dagit(5, pay, _hepsi(8), en_az_gosterim=False))
    # eşit paylı çiftler: ilk indis ikincisinden az almaz
    assert (s[:4] >= s[4:]).all()


def test_paylastir_toplam_korunur():
    rng = np.random.default_rng(7)
    for _ in range(300):
        n = int(rng.integers(1, 30))
        toplam = int(rng.integers(0, 120))
        pay = rng.random(n) * (rng.random(n) < 0.8)
        aday = rng.random(n) < 0.8
        for en_az in (True, False):
            s = dagit(toplam, pay, aday, en_az_gosterim=en_az)
            var = aday & (pay > 0)
            assert s.shape == (n,) and s.dtype == np.int64
            assert (s >= 0).all() and (s[~var] == 0).all()
            assert s.sum() == (toplam if var.any() else 0)


def test_paylastir_toplam_sifir():
    np.testing.assert_array_equal(dagit(0, np.ones(3), _hepsi(3)), [0, 0, 0])
    np.testing.assert_array_equal(dagit(-5, np.ones(3), _hepsi(3)), [0, 0, 0])


def test_en_az_gosterim():
    pay = np.array([100., 1., 1., 1.])
    # kapalı: düz en büyük kalan, en büyük mağaza kalan paketi alır
    np.testing.assert_array_equal(dagit(10, pay, _hepsi(4), en_az_gosterim=False), [10, 0, 0, 0])
    # açık: payı 1 paketin altında kalanlar kalan paketler için öne geçer (en büyük kesir sırası,
    # eşitlikte indis); kimse kendi tam kısmından kaybetmez
    np.testing.assert_array_equal(dagit(10, pay, _hepsi(4)), [9, 1, 0, 0])
    np.testing.assert_array_equal(dagit(12, pay, _hepsi(4), en_az_gosterim=False), [12, 0, 0, 0])
    np.testing.assert_array_equal(dagit(12, pay, _hepsi(4)), [11, 1, 0, 0])
    # kalan paket sayısı kadar küçük mağaza 1 alır
    np.testing.assert_array_equal(dagit(10, np.array([10., 1., 1., 1.]), _hepsi(4)), [7, 1, 1, 1])
    # paket yetmezse 1 paket ya da hiç: toplam aşılmaz
    s = dagit(2, pay, _hepsi(4))
    np.testing.assert_array_equal(s, [1, 1, 0, 0])
    assert s.sum() == 2
    # küçük kesirler kendi arasında en büyük kesre göre sıralanır
    s = dagit(10, np.array([100., 1., 3., 2.]), _hepsi(4))
    np.testing.assert_array_equal(s, [9, 0, 1, 0])
    # pay > 0 olmayan mağaza hiç almaz
    s = dagit(5, np.array([10., 0., 0.1]), _hepsi(3))
    assert s[1] == 0 and s.sum() == 5


def test_en_az_gosterim_tam_kisimdan_almaz():
    rng = np.random.default_rng(3)
    for _ in range(200):
        n = int(rng.integers(2, 25))
        toplam = int(rng.integers(1, 80))
        pay = rng.random(n) ** 3
        s_a = dagit(toplam, pay, _hepsi(n), en_az_gosterim=True)
        taban = np.floor(toplam * pay / pay.sum()).astype(int)
        assert (s_a >= taban).all() and s_a.sum() == toplam
        tiny = toplam * pay / pay.sum() < 1
        assert (s_a[tiny] <= 1).all()


def test_aday_disina_paket_yok():
    aday = np.array([True, False, True, False])
    s = dagit(10, np.array([1., 5., 1., 5.]), aday)
    np.testing.assert_array_equal(s, [5, 0, 5, 0])
    s = dagit(10, np.array([1., 5., 1., 5.]), aday, tavan_paket=np.array([2, 9, 9, 9]))
    np.testing.assert_array_equal(s, [2, 0, 8, 0])


def test_sifir_pay_esit_degil_bos():
    """Pay toplamı 0: hiçbir yere paket gitmez (kol kendi geri düşüşünü seçer)."""
    for en_az in (True, False):
        s = dagit(10, np.zeros(4), _hepsi(4), en_az_gosterim=en_az)
        np.testing.assert_array_equal(s, [0, 0, 0, 0])
    # aday olanların payı sıfır, aday olmayanın payı pozitif: yine boş
    s = dagit(10, np.array([0., 0., 5., 5.]), np.array([True, True, False, False]))
    np.testing.assert_array_equal(s, [0, 0, 0, 0])
    # aday yok
    np.testing.assert_array_equal(dagit(10, np.ones(3), np.zeros(3, dtype=bool)), [0, 0, 0])


def test_tavan_yeniden_paylastirir():
    # eşit pay: 4 mağaza x 25; ilk mağaza tavanı 10 -> artan 15 ötekilere 5'er
    s = dagit(100, np.ones(4), _hepsi(4), tavan_paket=np.array([10, 99, 99, 99]))
    np.testing.assert_array_equal(s, [10, 30, 30, 30])
    # tekrarlı: ikinci tur başka bir mağazayı da bağlar
    s = dagit(100, np.ones(4), _hepsi(4), tavan_paket=np.array([10, 28, 99, 99]))
    np.testing.assert_array_equal(s, [10, 28, 31, 31])
    # üçüncü tur
    s = dagit(100, np.ones(4), _hepsi(4), tavan_paket=np.array([10, 28, 29, 99]))
    np.testing.assert_array_equal(s, [10, 28, 29, 33])
    # tavan bağlamıyorsa sonuç tavansızla aynı
    np.testing.assert_array_equal(
        dagit(100, np.ones(4), _hepsi(4), tavan_paket=np.array([50, 50, 50, 50])),
        dagit(100, np.ones(4), _hepsi(4)))


def test_tavan_yeniden_paylastirir_oransal():
    # pay 1:2:3, toplam 60 -> 10 / 20 / 30; üçüncünün tavanı 12 -> artan 18, 1:2 -> 6 / 12
    s = dagit(60, np.array([1., 2., 3.]), _hepsi(3), tavan_paket=np.array([99, 99, 12]))
    np.testing.assert_array_equal(s, [16, 32, 12])


def test_herkes_tavanda_kalan_dagitilmaz():
    s = dagit(100, np.ones(3), _hepsi(3), tavan_paket=np.array([5, 6, 7]))
    np.testing.assert_array_equal(s, [5, 6, 7])
    assert s.sum() == 18 < 100
    # aday olmayanın tavanı sayılmaz, pay sıfır olanın da
    s = dagit(100, np.array([1., 1., 0., 1.]), np.array([True, True, True, False]),
              tavan_paket=np.array([5, 6, 70, 70]))
    np.testing.assert_array_equal(s, [5, 6, 0, 0])


def test_tavan_sifir_magaza_almaz():
    s = dagit(9, np.ones(3), _hepsi(3), tavan_paket=np.array([0, 99, 99]))
    np.testing.assert_array_equal(s, [0, 5, 4])


def test_tavan_sentineli_tavansiz_demektir():
    """`TAVANSIZ`: mağaza tavansız (öngörüsü NaN olan mağaza); `None` bütün mağazalar tavansız."""
    assert TAVANSIZ == np.iinfo(np.int64).max
    tav = np.array([3, TAVANSIZ, TAVANSIZ, TAVANSIZ])
    s = dagit(40, np.ones(4), _hepsi(4), tavan_paket=tav)
    np.testing.assert_array_equal(s, [3, 13, 12, 12])
    np.testing.assert_array_equal(
        dagit(40, np.ones(4), _hepsi(4), tavan_paket=np.full(4, TAVANSIZ)),
        dagit(40, np.ones(4), _hepsi(4), tavan_paket=None))
    # herkes tavansız ve toplam büyük: sentinel toplamı taşırmaz
    s = dagit(10**6, np.ones(4), _hepsi(4), tavan_paket=np.full(4, TAVANSIZ))
    assert s.sum() == 10**6


def test_tavan_ve_en_az_gosterim_birlikte():
    pay = np.array([100., 1., 1., 1.])
    s = dagit(10, pay, _hepsi(4), tavan_paket=np.array([6, 99, 99, 99]))
    # birinci mağaza 6'da kalır; artan 4 üç küçük mağazaya (her biri 1'in üstü: hedef 1,33)
    np.testing.assert_array_equal(s, [6, 2, 1, 1])
    s = dagit(10, pay, _hepsi(4), tavan_paket=np.array([1, 99, 99, 99]))
    np.testing.assert_array_equal(s, [1, 3, 3, 3])


def test_tavan_rastgele_ozellikler():
    rng = np.random.default_rng(11)
    for _ in range(400):
        n = int(rng.integers(1, 25))
        toplam = int(rng.integers(0, 150))
        pay = rng.random(n) * (rng.random(n) < 0.85)
        aday = rng.random(n) < 0.85
        tav = rng.integers(0, 12, n)
        tav[rng.random(n) < 0.2] = TAVANSIZ
        for en_az in (True, False):
            s = dagit(toplam, pay, aday, tavan_paket=tav, en_az_gosterim=en_az)
            var = aday & (pay > 0) & (tav > 0)
            assert (s <= tav).all() and (s[~var] == 0).all() and (s >= 0).all()
            kapasite = sum(int(x) for x in tav[var])      # sentinel toplamı int64'ü taşırır
            assert s.sum() == min(toplam, kapasite)


def test_belirlenimcilik_ve_giris_degismez():
    pay = np.array([0.3, 0.3, 0.3, 0.1])
    aday = _hepsi(4)
    tav = np.array([4, 99, 99, 99])
    kopyalar = [a.copy() for a in (pay, aday, tav)]
    a = dagit(23, pay, aday, tavan_paket=tav)
    b = dagit(23, pay, aday, tavan_paket=tav)
    np.testing.assert_array_equal(a, b)
    for x, y in zip((pay, aday, tav), kopyalar):
        np.testing.assert_array_equal(x, y)


def test_girdi_dogrulama():
    with pytest.raises(ValueError, match="pay"):
        dagit(5, np.array([1., -1.]), _hepsi(2))
    with pytest.raises(ValueError, match="pay"):
        dagit(5, np.array([1., np.nan]), _hepsi(2))
    with pytest.raises(ValueError, match="aday"):
        dagit(5, np.ones(3), _hepsi(2))
    with pytest.raises(ValueError, match="tavan"):
        dagit(5, np.ones(2), _hepsi(2), tavan_paket=np.array([1, 2, 3]))
    with pytest.raises(ValueError, match="tavan"):
        dagit(5, np.ones(2), _hepsi(2), tavan_paket=np.array([1, -2]))


# ---------------------------------------------------------------------------
# Gerçek v4 dünyası: Lumoda ile karşılaştırma
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gercek_dunya():
    from allocation import motor
    return motor.dunya()


@pytest.mark.veri
def test_gercek_paket_icerigi_paket_tablosuyla(gercek_dunya):
    from perakende_veri.v4.politika import paket_tablosu
    w = gercek_dunya
    _, set_idx, icerik = paket_tablosu(w.paketler)
    for o in range(len(w.optionlar)):
        beklenen = icerik[set_idx[w.optionlar["beden_seti"].iloc[o]]]
        beklenen = beklenen[beklenen > 0]       # dolu bedenler, beden sırasıyla
        np.testing.assert_array_equal(paylastir.paket_icerigi(w, o), beklenen)
        assert paylastir.paket_adedi(w, o) == beklenen.sum()


@pytest.mark.veri
def test_gercek_ust_sinir_depo_bol(gercek_dunya):
    """Depo bolken U = tam sayı ⌊ilk alım × 0,70 ÷ paket adedi⌋; Lumoda'nın kayan nokta toplamıyla
    en çok 1 paket farkeder (U büyük olandır)."""
    from perakende_veri.v4.sabitler import ILK_DAGITIM_PAYI
    assert sabitler.LUMODA_ILK_PAYI == ILK_DAGITIM_PAYI
    w = gercek_dunya
    h = harita_kur(w)
    g = _gorunum(w)
    fark = 0
    for o in range(len(w.optionlar)):
        u = paylastir.ust_sinir(g, o, h)
        pk = paylastir.paket_adedi(w, o)
        assert u == int(w.ilk_alim[o]) * 7 // (10 * pk)
        kayan = int(w.ilk_alim[o] * ILK_DAGITIM_PAYI // pk)
        assert u - kayan in (0, 1)
        fark += u != kayan
    print(f"U, Lumoda'nın kayan nokta toplamından {fark}/{len(w.optionlar)} option'da 1 paket büyük")


@pytest.mark.veri
def test_gercek_ust_sinir_depo_bedenlere_bolunmus(gercek_dunya):
    """Depo ilk alımın 10/22/32/24/12'si: 5 bedenli option'da en küçük beden bağlar ve U
    Lumoda payına eşit ya da biraz altında (tam bölünmeyen payda)."""
    w = gercek_dunya
    h = harita_kur(w)
    pay = np.array([10, 22, 32, 24, 12]) / 100
    secili = [o for o in range(len(w.optionlar)) if len(paylastir.paket_icerigi(w, o)) == 5][:50]
    for o in secili:
        skular = np.flatnonzero(h.sku_option == o)
        skular = skular[np.argsort(h.sku_beden_sira[skular])]
        depo = np.zeros(len(w.urunler), dtype=np.int64)
        depo[skular] = np.floor(w.ilk_alim[o] * pay).astype(np.int64)
        u = paylastir.ust_sinir(_gorunum(w, depo), o, h)
        assert u == min(int(depo[skular[b]]) // int(c) for b, c in enumerate(paylastir.paket_icerigi(w, o)))
        assert u <= int(w.ilk_alim[o]) * 7 // (10 * 7)


class _Vekil:
    """Gerçek dünyayı sarar, yalnız `plan_tablolari`'nı eşit hedefle değiştirir."""

    def __init__(self, w):
        self._w = w
        mp = pd.DataFrame([(s, u, mg, 1.0) for s, u in set(zip(w.optionlar["sezon_kodu"],
                                                               w.optionlar["ust_kategori"]))
                           for mg in w.magazalar["magaza_id"]],
                          columns=["sezon_kodu", "ust_kategori", "magaza_id", "satis_hedefi"])
        self.plan_tablolari = {"magaza_plan": mp}

    def __getattr__(self, ad):
        return getattr(self._w, ad)


@pytest.mark.veri
def test_gercek_aday_maskesi_lumoda_ile(gercek_dunya):
    """Her option için `aday_maskesi`, Lumoda'nın ilk dağıtımında paket alan mağazalar kümesinin
    üst kümesidir; toplam paket aday sayısını aşıyorsa eşittir (eşit hedefle, kapanış ve
    kapalı mağaza senaryolarında)."""
    from perakende_veri.v4.politika import lumoda_ilk_dagitim
    w = gercek_dunya
    h = harita_kur(w)
    vekil = _Vekil(w)
    Mg = len(w.magazalar)
    rng = np.random.default_rng(5)
    kapanacak = rng.random(Mg) < 0.08
    kapali = rng.random(Mg) < 0.15
    senaryolar = [_gorunum(vekil), _gorunum(vekil, kapanacak=np.flatnonzero(kapanacak),
                                            kapali=np.flatnonzero(kapali))]
    esit = ustte = 0
    for g in senaryolar:
        g.dunya = vekil
        for o in range(len(w.optionlar)):
            aday = paylastir.aday_maskesi(g, o, h)
            lum = lumoda_ilk_dagitim(g, o)
            assert not (lum > 0)[~aday].any(), f"option {o}: aday dışına paket"
            if aday.any() and lum.sum() >= aday.sum():
                np.testing.assert_array_equal(lum > 0, aday)
                esit += 1
            else:
                ustte += 1
    assert esit > 100
    print(f"aday maskesi Lumoda ile birebir {esit}, yalnız üst küme {ustte} (option x senaryo)")
