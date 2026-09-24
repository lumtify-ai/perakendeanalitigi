import numpy as np

from replenishment import sabitler
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


def test_uzun_gecmisle_kurulunca_kuyruk_yediye_kirpilir_ve_tam_yedi_gun_once_doner():
    # IADE_GECIKME'den (7) fazla geçmiş verilirse kuyruk yalnızca son 7'yi
    # tutmalı; aksi halde her gün +1 ekleyip tek `pop` ile -1 çıkarmak
    # kuyruğu kalıcı olarak uzun tutar ve iade[0] hep 7 günden eskiyi işaret eder.
    gecmis = [np.array([100 + g]) for g in range(10)]  # en eski başta, 100..109
    d = baslangic_durumu(np.array([1000]), gecmis)
    assert len(d.iade_kuyrugu) == sabitler.IADE_GECIKME
    # kırpılan kuyruğun başı tam olarak "7 gün önceki" satış olmalı: son 7
    # girişin ilki, yani 10 - 7 = 3. indeks → 103.
    assert d.iade_kuyrugu[0].tolist() == [103]

    rng_beklenen = np.random.default_rng(0)
    beklenen_iade = rng_beklenen.binomial(103, sabitler.IADE_ORANI)

    stok_once = int(d.stok[0])
    rng = np.random.default_rng(0)
    gunu_isle(d, 0, np.array([0]), None, None, rng)

    assert int(d.stok[0]) == stok_once + beklenen_iade
    assert len(d.iade_kuyrugu) == sabitler.IADE_GECIKME
