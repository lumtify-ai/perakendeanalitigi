"""Görev 4: yaşam döngüsü, terk tetikleyicileri, 2026 LTV."""

import copy
import dataclasses

import numpy as np
import pytest

from perakende_veri.v4.crm.sabitler import CRM_TOHUM


@pytest.fixture(scope="module")
def _taban(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import nufus_baslat

    return nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi)


@pytest.fixture()
def nuf(_taban):
    """Her test için taze kopya (testler nüfusu değiştirir; mağaza bilgisi
    paylaşılır, salt okunur)."""
    n = copy.copy(_taban)
    n._tampon = {ad: a.copy() for ad, a in _taban._tampon.items()}
    n._goster()
    return n


def test_crm_uretici_amac_ve_gun_bagimsiz():
    from perakende_veri.v4.crm.rastgele import AMACLAR, crm_uretici

    assert AMACLAR == {
        "katilis": 1, "ziyaret": 2, "atama": 3, "iade": 4, "kart": 5,
        "terk": 6, "online": 7, "yorum": 8, "kargo": 9, "ltv": 10,
    }
    a = crm_uretici(5, "terk").random(4)
    assert np.array_equal(a, crm_uretici(5, "terk").random(4))
    assert not np.array_equal(a, crm_uretici(6, "terk").random(4))
    assert not np.array_equal(a, crm_uretici(5, "kart").random(4))
    assert not np.array_equal(a, crm_uretici(5, "terk", tohum=1).random(4))


def test_ay_basi_mi():
    from perakende_veri.v4.crm.yasam import ay_basi_mi
    from perakende_veri.v4.takvim import gun_indisi

    assert ay_basi_mi(gun_indisi("2023-01-01"))
    assert ay_basi_mi(gun_indisi("2024-03-01"))
    assert not ay_basi_mi(gun_indisi("2024-03-02"))
    assert not ay_basi_mi(0)  # 2022-07-04


def test_ay_basi_degilse_cekilis_yok(nuf):
    from perakende_veri.v4.crm.yasam import Tetik, gunluk_terk

    nuf.terk_p[:] = 0.9
    tetik = Tetik.bos(nuf.K)
    terk = gunluk_terk(np.random.default_rng(0), nuf, tetik, 10, ay_basi=False)
    assert not terk.any() and nuf.hayatta.all()


def test_olen_musteri_tekrar_hayatta_olmaz(nuf):
    from perakende_veri.v4.crm.yasam import Tetik, gunluk_terk

    nuf.terk_p[:] = 0.5
    tetik = Tetik.bos(nuf.K)
    olu_gecmis = np.zeros(nuf.K, dtype=bool)
    terk_gun = np.full(nuf.K, -1)
    for i, d in enumerate([100, 130, 160, 190]):
        terk = gunluk_terk(np.random.default_rng(i), nuf, tetik, d, ay_basi=True)
        assert not (terk & olu_gecmis).any()           # ölü tekrar ölmez
        assert (nuf.terk_gun[terk] == d).all()
        olu_gecmis |= terk
        terk_gun[terk] = d
        assert not nuf.hayatta[olu_gecmis].any()        # ölü dirilmez
        assert (nuf.terk_gun == terk_gun).all()         # terk günü değişmez
    assert olu_gecmis.mean() > 0.9


def test_tetiksiz_aylik_terk_parametre_ortalamasina_yakinsar(nuf):
    from perakende_veri.v4.crm.yasam import Tetik, gunluk_terk

    assert nuf.K > 20_000
    tetik = Tetik.bos(nuf.K)
    oranlar, beklenen = [], []
    for i, d in enumerate([100, 130, 160]):
        hayatta = nuf.hayatta.copy()
        terk = gunluk_terk(np.random.default_rng(10 + i), nuf, tetik, d, ay_basi=True)
        oranlar.append(terk[hayatta].mean())
        beklenen.append(nuf.terk_p[hayatta].mean())
    for o, b in zip(oranlar, beklenen):
        assert abs(o / b - 1) < 0.10, (o, b)


def test_stoksuzluk_penceresi_60_gun_sonra_etkisiz():
    from perakende_veri.v4.crm.yasam import STOKSUZLUK_GUN, Tetik, terk_carpani

    assert STOKSUZLUK_GUN == 60
    t = Tetik.bos(3)
    t.stoksuzluk(np.array([0]), 200)
    assert t.stoksuz_bitis_gun[0] == 260
    assert terk_carpani(t, 200)[0] == pytest.approx(1.5)
    assert terk_carpani(t, 260)[0] == pytest.approx(1.5)
    assert terk_carpani(t, 261)[0] == pytest.approx(1.0)
    assert np.allclose(terk_carpani(t, 200)[1:], 1.0)


def test_tetik_carpanlari_carpilir():
    from perakende_veri.v4.crm.yasam import Tetik, terk_carpani

    t = Tetik.bos(5)
    t.iade(np.array([1, 4]), 100)
    t.beden_uyumsuz(np.array([2, 2, 4, 4]))
    t.stoksuzluk(np.array([3, 4]), 100)
    t.ev_kapandi[[3, 4]] = True
    c = terk_carpani(t, 150)
    assert c == pytest.approx([1.0, 1.2, 1.3, 1.5 * 2.0, 1.2 * 1.3 * 1.5 * 2.0])
    assert t.iade_sayisi.tolist() == [0, 1, 0, 0, 1]
    # iade 90 gün sonra etkisiz; ikinci iade pencereyi tazeler
    assert terk_carpani(t, 190)[1] == pytest.approx(1.2)
    assert terk_carpani(t, 191)[1] == pytest.approx(1.0)
    t.iade(np.array([1]), 250)
    assert terk_carpani(t, 300)[1] == pytest.approx(1.2) and t.iade_sayisi[1] == 2
    # tek beden uyumsuzluğu çarpmaz
    t.beden_uyumsuz(np.array([0]))
    assert terk_carpani(t, 400)[0] == pytest.approx(1.0)


def test_terk_olasiligi_ust_siniri(nuf):
    from perakende_veri.v4.crm.yasam import P_UST, Tetik, terk_olasiligi

    t = Tetik.bos(nuf.K)
    t.stoksuzluk(np.arange(nuf.K), 0)
    t.iade(np.arange(nuf.K), 0)
    t.beden_uyumsuz(np.repeat(np.arange(nuf.K), 2))
    t.ev_kapandi[:] = True
    nuf.terk_p[:] = 0.3
    p = terk_olasiligi(nuf, t, 10)
    assert P_UST == 0.95 and (p == 0.95).all()


def test_tetik_nufusla_buyur(nuf):
    from perakende_veri.v4.crm.yasam import Tetik, gunluk_terk

    t = Tetik.bos(nuf.K)
    K0 = nuf.K
    nuf.ekle(np.random.default_rng(3), 50, ev_magaza=0, kayit_gun=90)
    gunluk_terk(np.random.default_rng(0), nuf, t, 100, ay_basi=True)
    assert t.K == nuf.K == K0 + 50 and len(t.stoksuz_bitis_gun) == nuf.K
    assert (t.stoksuz_bitis_gun[K0:] == -1).all() and not t.ev_kapandi[K0:].any()


def _tek_ilde_magaza(nuf) -> int:
    """En kalabalık fiziksel mağazayı, nüfusun mağaza bilgisinde kendi
    başına yeni bir ile taşır (ilinde başka mağaza kalmaz); indisini döndürür."""
    mb = nuf.magaza
    sayi = np.bincount(nuf.ev_magaza[nuf.hayatta], minlength=mb.M)
    sayi[mb.onl] = 0
    m = int(np.argmax(sayi))
    il = mb.il.copy()
    il[m] = len(mb.il_adlari)
    nuf.magaza = dataclasses.replace(mb, il=il, il_adlari=mb.il_adlari + ("Yok",))
    return m


def test_ev_kapanisi_ilinde_magaza_yoksa_gecis_yok(nuf, kucuk_girdi):
    from perakende_veri.v4.crm.yasam import Tetik, ev_kapanisi

    m = _tek_ilde_magaza(nuf)
    t = Tetik.bos(nuf.K)
    ev = (nuf.ev_magaza == m) & nuf.hayatta
    assert ev.sum() > 100
    onl0 = nuf.online_payi.copy()
    gecen = ev_kapanisi(np.random.default_rng(0), nuf, t, kucuk_girdi, m, 500)
    assert len(gecen) == 0 and (nuf.ev_magaza[ev] == m).all()
    assert t.ev_kapandi[ev].all() and not t.ev_kapandi[~ev].any()
    assert np.allclose(nuf.online_payi[ev], np.minimum(2 * onl0[ev], 1.0))
    assert np.array_equal(nuf.online_payi[~ev], onl0[~ev])


def test_ev_kapanisi_en_yakin_acik_magazaya_gecis(nuf, kucuk_girdi):
    from perakende_veri.v4.crm.yasam import GECIS_OLASILIGI, Tetik, ev_kapanisi
    from perakende_veri.v4.magaza import haversine_km

    mb = nuf.magaza
    fiz = np.arange(mb.M) != mb.onl
    d = 500
    acik = fiz & (mb.acilis_gun <= d) & (mb.kapanis_gun > d)
    sayi = np.bincount(mb.il[acik], minlength=len(mb.il_adlari))
    adaylar = [m for m in np.flatnonzero(acik) if sayi[mb.il[m]] >= 2
               and ((nuf.ev_magaza == m) & nuf.hayatta).sum() > 200]
    assert adaylar, "KUCUK'ta ilinde ikinci açık mağazası olan mağaza yok"
    m = int(adaylar[0])
    mag = kucuk_girdi.dunya.magazalar
    lat, lon = mag["enlem"].to_numpy(), mag["boylam"].to_numpy()
    ayni = acik & (mb.il == mb.il[m]) & (np.arange(mb.M) != m)
    uzak = np.where(ayni, haversine_km(lat[m], lon[m], lat, lon), np.inf)
    hedef = int(np.argmin(uzak))

    t = Tetik.bos(nuf.K)
    ev = (nuf.ev_magaza == m) & nuf.hayatta
    onl0 = nuf.online_payi.copy()
    ev_kapanisi(np.random.default_rng(1), nuf, t, kucuk_girdi, m, d)
    gecen = ev & (nuf.ev_magaza == hedef)
    kalan = ev & (nuf.ev_magaza == m)
    assert (gecen | kalan)[ev].all()
    assert abs(gecen.sum() / ev.sum() - GECIS_OLASILIGI) < 0.08
    assert not t.ev_kapandi[gecen].any() and t.ev_kapandi[kalan].all()
    assert np.array_equal(nuf.online_payi[gecen], onl0[gecen])
    assert (nuf.il[gecen] == mb.il[hedef]).all()


def _fiyat(nuf):
    return np.random.default_rng(7).uniform(200, 800, nuf.K)


def _olum_ve_ltv(nuf, tohum=CRM_TOHUM):
    from perakende_veri.v4.crm.rastgele import crm_uretici
    from perakende_veri.v4.crm.yasam import Tetik, gunluk_terk, ltv_2026

    t = Tetik.bos(nuf.K)
    gunluk_terk(np.random.default_rng(5), nuf, t, 100, ay_basi=True)
    return ltv_2026(crm_uretici(1277, "ltv", tohum=tohum), nuf, t, _fiyat(nuf))


def test_geri_gelecek_terk_etmiste_hep_false(nuf):
    df = _olum_ve_ltv(nuf)
    assert len(df) == nuf.K
    olu = ~nuf.hayatta
    assert olu.sum() > 100
    assert not df["geri_gelecek_2026"].to_numpy()[olu].any()
    for c in ("hayatta_olasiligi", "beklenen_harcama_2026", "gerceklesen_ziyaret_2026",
              "gerceklesen_harcama_2026"):
        assert (df[c].to_numpy()[olu] == 0).all(), c
    canli = nuf.hayatta
    assert (df["hayatta_olasiligi"].to_numpy()[canli] == 1).all()
    assert df["geri_gelecek_2026"].to_numpy()[canli].mean() > 0.3
    assert np.array_equal(df["geri_gelecek_2026"].to_numpy(),
                          df["gerceklesen_ziyaret_2026"].to_numpy() > 0)


def test_ltv_ayni_tohumla_ayni(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import nufus_baslat

    a = _olum_ve_ltv(nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi))
    b = _olum_ve_ltv(nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi))
    c = _olum_ve_ltv(nufus_baslat(np.random.default_rng(CRM_TOHUM), kucuk_girdi), tohum=1)
    assert a.equals(b)
    assert not a["gerceklesen_ziyaret_2026"].equals(c["gerceklesen_ziyaret_2026"])


def test_ltv_analitik_gerceklesenle_tutarli(nuf):
    df = _olum_ve_ltv(nuf)
    canli = nuf.hayatta
    p = nuf.terk_p[canli]
    m = np.arange(1, 13)
    sag = ((1 - p[:, None]) ** m).mean(axis=1)
    assert np.allclose(df["hayatta_kalma_2026"].to_numpy()[canli], sag)
    bz = nuf.ziyaret_hizi[canli] * sag
    assert np.allclose(df["beklenen_ziyaret_2026"].to_numpy()[canli], bz)
    bh = bz * nuf.sepet_ort[canli] * _fiyat(nuf)[canli]
    assert np.allclose(df["beklenen_harcama_2026"].to_numpy()[canli], bh)
    # toplamda gerçekleşen ≈ beklenen (büyük örnek)
    gz = df["gerceklesen_ziyaret_2026"].to_numpy()[canli].sum()
    gh = df["gerceklesen_harcama_2026"].to_numpy()[canli].sum()
    assert abs(gz / bz.sum() - 1) < 0.03
    assert abs(gh / bh.sum() - 1) < 0.04
