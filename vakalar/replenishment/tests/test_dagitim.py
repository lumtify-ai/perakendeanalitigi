import numpy as np

from replenishment.dagitim import KoliKurali, dagit, koli_uygun
from replenishment.depo import Depo

KOLI = np.array([1, 2, 2, 2, 1])


def test_koli_kurali_a_tek_beden_ihtiyacinda_koli_gondermez():
    assert not koli_uygun(np.array([0, 0, 5, 0, 0]), KoliKurali("A"))
    assert koli_uygun(np.array([1, 2, 2, 1, 1]), KoliKurali("A"))


def test_koli_kurali_b_karsilama_orani():
    assert koli_uygun(np.array([1, 1, 1, 1, 1]), KoliKurali("B", gama=0.6))   # 5/8
    assert not koli_uygun(np.array([0, 1, 1, 1, 0]), KoliKurali("B", gama=0.6))  # 3/8


def test_koli_kurali_c_a_ve_b_birlikte():
    # A geçer (deficit < beta, sum >= alfa*8), B geçmez (karşılama < gama) -> C false.
    n = np.array([1, 2, 2, 1, 0])  # sum=6>=4.8, koli-n=[0,0,0,1,1] max=1<2 (A ok)
    assert koli_uygun(n, KoliKurali("A"))
    assert not koli_uygun(n, KoliKurali("B", gama=0.8))
    assert not koli_uygun(n, KoliKurali("C", gama=0.8))
    # Hem A hem B geçtiğinde C de geçer.
    n2 = np.array([1, 2, 2, 2, 1])
    assert koli_uygun(n2, KoliKurali("A"))
    assert koli_uygun(n2, KoliKurali("B"))
    assert koli_uygun(n2, KoliKurali("C"))


def test_koli_kurali_yok_hep_false():
    assert not koli_uygun(np.array([1, 2, 2, 2, 1]), KoliKurali("yok"))


def test_kisitli_acik_stok_en_dusuk_covera_gider(mini_dunya_10):
    # 10 mağaza, tek option, depoda 10 açık adet (beden 3), koli yok.
    # 3 mağazanın ihtiyacı 3, 7'sinin 1; öngörü: ilk üçü 6/hafta, diğerleri 1/hafta.
    d = mini_dunya_10
    ihtiyac = np.zeros((10, 5), int); ihtiyac[:3, 2] = 3; ihtiyac[3:, 2] = 1
    ongoru = np.array([6.0] * 3 + [1.0] * 7)
    depo = Depo(koli=np.array([0]), acik=np.array([[0, 0, 10, 0, 0]]))
    sevk = dagit(ihtiyac, ongoru, np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("yok"), acik_kapasite=100)
    giden = [int(sevk.gelen[d.oc_hucre[oc]].sum()) for oc in range(10)]
    assert sum(giden) == 10 and depo.acik.sum() == 0
    assert giden[:3] == [3, 3, 3]            # hızlı satanlar tam karşılanır
    assert sum(giden[3:]) == 1


def test_esit_oncelik_herkese_birer(mini_dunya_10):
    d = mini_dunya_10
    ihtiyac = np.zeros((10, 5), int); ihtiyac[:3, 2] = 3; ihtiyac[3:, 2] = 1
    depo = Depo(koli=np.array([0]), acik=np.array([[0, 0, 10, 0, 0]]))
    sevk = dagit(ihtiyac, np.ones(10), np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("yok"), 100, oncelik="esit")
    assert [int(sevk.gelen[d.oc_hucre[oc]].sum()) for oc in range(10)] == [1] * 10


def test_acik_kapasite_asilmaz(mini_dunya_10):
    d = mini_dunya_10
    ihtiyac = np.full((10, 5), 2)
    depo = Depo(koli=np.array([0]), acik=np.full((1, 5), 100))
    sevk = dagit(ihtiyac, np.ones(10), np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("yok"), acik_kapasite=7)
    assert sevk.acik_adet == 7 and int(sevk.gelen.sum()) == 7


def test_bedeni_bitmis_acik_atlanir_negatif_yok(mini_dunya_10):
    d = mini_dunya_10
    ihtiyac = np.zeros((10, 5), int); ihtiyac[:, 0] = 2
    depo = Depo(koli=np.array([0]), acik=np.array([[0, 5, 5, 5, 5]]))
    sevk = dagit(ihtiyac, np.ones(10), np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("yok"), 100)
    assert int(sevk.gelen.sum()) == 0 and (depo.acik >= 0).all()


def test_kapasitesi_dolu_magazaya_mal_gitmez(mini_dunya_10):
    d = mini_dunya_10
    stok = np.zeros(len(d.hucre_urun), np.int64)
    stok[d.oc_hucre[0]] = d.kapasite[0] + 5          # kapasitenin üstünde
    ihtiyac = np.zeros((10, 5), int); ihtiyac[0] = [1, 2, 2, 2, 1]
    depo = Depo(koli=np.array([3]), acik=np.full((1, 5), 10))
    sevk = dagit(ihtiyac, np.ones(10), stok, depo, d, KoliKurali("A"), 100)
    assert int(sevk.gelen[d.oc_hucre[0]].sum()) == 0


def test_sifir_ongoru_nan_uretmez(mini_dunya_10):
    d = mini_dunya_10
    ihtiyac = np.zeros((10, 5), int); ihtiyac[:, 2] = 1
    depo = Depo(koli=np.array([0]), acik=np.array([[0, 0, 3, 0, 0]]))
    sevk = dagit(ihtiyac, np.zeros(10), np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("yok"), 100)
    assert int(sevk.gelen.sum()) == 3
    assert not np.isnan(sevk.gelen).any()


def test_koli_fazi_kisitli_koliyle_en_dusuk_covera_gider(mini_dunya_10):
    # 10 mağaza, her biri tam koli ihtiyacında (A kuralı geçer), depoda 3 koli.
    # İlk 3 mağazanın öngörüsü düşük (hızlı satar), geri kalanı yüksek.
    d = mini_dunya_10
    ihtiyac = np.tile(KOLI, (10, 1))
    ongoru = np.array([100.0] * 3 + [1.0] * 7)
    depo = Depo(koli=np.array([3]), acik=np.zeros((1, 5), np.int64))
    sevk = dagit(ihtiyac, ongoru, np.zeros(len(d.hucre_urun), np.int64), depo, d,
                 KoliKurali("A"), acik_kapasite=0)
    giden = [int(sevk.gelen[d.oc_hucre[oc]].sum()) for oc in range(10)]
    assert sevk.koli_sayisi == 3 and depo.koli[0] == 0
    assert giden[:3] == [8, 8, 8] and sum(giden[3:]) == 0


def test_koli_fazi_paylasilan_kapasite_bayat_girdi(mini_dunya_10):
    # Aynı mağazanın kalan kapasitesi tam 8: bir koli gidince ikinci koli
    # adayı artık uygun değil (kalan_kap < 8) — heap'te bayat kalmamalı.
    d = mini_dunya_10
    stok = np.zeros(len(d.hucre_urun), np.int64)
    ihtiyac = np.zeros((10, 5), int)
    ihtiyac[0] = KOLI
    depo = Depo(koli=np.array([5]), acik=np.zeros((1, 5), np.int64))
    d_kapasiteli = d.__class__(**{**d.__dict__, "kapasite": np.array([8] + [1000] * 9, np.int64)})
    sevk = dagit(ihtiyac, np.ones(10), stok, depo, d_kapasiteli, KoliKurali("A"), acik_kapasite=0)
    assert sevk.koli_sayisi == 1 and depo.koli[0] == 4
    assert int(sevk.gelen[d.oc_hucre[0]].sum()) == 8


def test_stok_degismez(mini_dunya_10):
    d = mini_dunya_10
    stok = np.zeros(len(d.hucre_urun), np.int64)
    stok[d.oc_hucre[0]] = [1, 0, 0, 0, 0]
    stok_kopya = stok.copy()
    ihtiyac = np.zeros((10, 5), int); ihtiyac[:, 2] = 1
    depo = Depo(koli=np.array([0]), acik=np.array([[0, 0, 10, 0, 0]]))
    dagit(ihtiyac, np.ones(10), stok, depo, d, KoliKurali("yok"), 100)
    assert (stok == stok_kopya).all()
