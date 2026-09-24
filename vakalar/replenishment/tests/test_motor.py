import numpy as np

from replenishment.motor import baslangic_durumu, gunu_isle


def test_satis_stokla_sinirli_kayip_kalan():
    d = baslangic_durumu(np.array([3, 0]), [])
    satis, kayip = gunu_isle(d, 0, np.array([5, 2]), None, np.zeros(2, int), None)
    assert satis.tolist() == [3, 0] and kayip.tolist() == [2, 2]
    assert d.stok.tolist() == [0, 0]


def test_gelen_mal_ayni_gun_satilir_ve_fifo_kaydi_yazilir():
    d = baslangic_durumu(np.array([1]), [])
    gunu_isle(d, 10, np.array([0]), np.array([4]), np.zeros(1, int), None)
    gunu_isle(d, 13, np.array([3]), None, np.zeros(1, int), None)
    # önce eski 1 adet, sonra gönderilen partiden 2 adet, 3 gün sonra
    assert d.gonderilen_satis_gunleri == [(0, 10, 13, 2)]
    assert d.stok.tolist() == [2]


def test_bulunabilirlik_sayaci_satistan_once_olcer():
    d = baslangic_durumu(np.array([1, 0]), [])
    gunu_isle(d, 0, np.array([1, 1]), None, np.zeros(2, int), None)
    assert (d.talepli_gun, d.stoklu_talepli_gun) == (2, 1)


def test_iade_kuyrugu_yedi_gun_sonra_doner():
    rng = np.random.default_rng(0)
    d = baslangic_durumu(np.array([100]), [])
    for g in range(8):
        gunu_isle(d, g, np.array([10 if g == 0 else 0]), None, None, rng)
    # 0. günün 10 satışından binom(10, 0.06) kadarı 7. gün stoğa döndü
    assert d.stok[0] >= 90
