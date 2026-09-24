import dataclasses

import numpy as np

from replenishment import ihtiyac
from replenishment.ihtiyac import GuvenlikStoku


def test_hafta_katsayisi_oran_olarak(mini_dunya):
    d = mini_dunya
    k = d.gun("2025-10-27")          # pazartesi; 29 Ekim çarşamba tatil
    assert d.tatil[d.gun("2025-10-29")]
    assert abs(ihtiyac.hafta_katsayisi(d, k, 1.35) - (6 + 1.35) / 7) < 1e-9


def test_hafta_katsayisi_gecen_haftada_tatil_varsa_duser(mini_dunya):
    d = mini_dunya
    k = d.gun("2025-11-03")          # geçen 7 gün 29 Ekim'i içerir
    assert ihtiyac.hafta_katsayisi(d, k, 1.35) < 1


def test_istatistik_ailesi_sifir_gecmiste_sifir(mini_dunya):
    s = np.zeros((365, len(mini_dunya.hucre_urun)), dtype=np.int32)
    ss = ihtiyac.guvenlik_stoku(GuvenlikStoku("istatistik"), s, mini_dunya, 243)
    assert (ss == 0).all() and not np.isnan(ss).any()


def test_bedene_bol_stoku_dusur_negatife_inme(mini_dunya):
    paylar = np.tile([0.1, 0.2, 0.4, 0.2, 0.1], (1, 1))
    stok = np.zeros(len(mini_dunya.hucre_urun), dtype=np.int64)
    stok[mini_dunya.oc_hucre[0]] = [0, 5, 0, 0, 0]
    n = ihtiyac.bedene_bol(np.array([10.0]), paylar, stok, mini_dunya, oc=[0])
    assert n.tolist() == [[1, 0, 4, 2, 1]]


def test_bedene_bol_oc_verilmezse_butun_oc(mini_dunya):
    d = mini_dunya
    OC = d.oc_hucre.shape[0]
    paylar = np.tile([0.1, 0.2, 0.4, 0.2, 0.1], (OC, 1))
    stok = np.zeros(len(d.hucre_urun), dtype=np.int64)
    hedef = np.full(OC, 10.0)
    n = ihtiyac.bedene_bol(hedef, paylar, stok, d)
    assert n.shape == (OC, 5)
    assert n[0].tolist() == [1, 2, 4, 2, 1]


def test_haftalik_bloklari_dogru_toplar(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    k = d.gun("2025-09-08")
    for hucre in d.oc_hucre[0]:
        satis[d.gun("2025-09-02"):k + 1, hucre] = 1
    sonuc = ihtiyac.haftalik(satis, d, k, hafta=2)
    assert sonuc.shape == (2, d.oc_hucre.shape[0])
    assert sonuc[1, 0] == 35          # 5 beden × 7 gün × 1
    assert sonuc[0, 0] == 0           # o hafta hiç satış yok


def test_haftalik_veri_basindan_once_sifir(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    satis[360:365, :] = 100           # yıl sonuna sahte büyük satış
    k = 5                             # yılın başına yakın karar günü
    sonuc = ihtiyac.haftalik(satis, d, k, hafta=3)
    assert (sonuc[0] == 0).all()      # en eski blok veri başından önceye taşar; yıl sonu sızmaz


def test_ozel_gun_katsayisi_oran_hesaplar(mini_dunya):
    d = mini_dunya
    tatil = np.zeros(365, dtype=bool)
    h = 200
    tatil[h] = True
    d = dataclasses.replace(d, tatil=tatil)
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    haftanin_gunu = np.arange(365) % 7
    aday = np.flatnonzero(
        (haftanin_gunu == haftanin_gunu[h]) & (np.abs(np.arange(365) - h) <= 14) & ~tatil
    )
    satis[aday, 0] = 10
    satis[h, 0] = 40
    katsayilar = ihtiyac.ozel_gun_katsayilari(satis, d, bit_gunu=300)
    assert abs(katsayilar["Üst Giyim"] - 4.0) < 1e-9


def test_ozel_gun_katsayisi_gelecekteki_tatili_yoksayar(mini_dunya):
    d = mini_dunya
    tatil = np.zeros(365, dtype=bool)
    h = 200
    tatil[h] = True
    d = dataclasses.replace(d, tatil=tatil)
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    satis[h, 0] = 999
    katsayilar = ihtiyac.ozel_gun_katsayilari(satis, d, bit_gunu=h)
    assert katsayilar == {}


def test_ozel_gun_katsayisi_pencere_bit_gununu_asmaz(mini_dunya):
    d = mini_dunya
    tatil = np.zeros(365, dtype=bool)
    h = 200
    tatil[h] = True
    d = dataclasses.replace(d, tatil=tatil)
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    bit_gunu = 205  # h'nin +14 penceresi (214'e kadar) bit_gunu'nü aşar

    haftanin_gunu = np.arange(365) % 7
    pencere_tum = np.arange(max(h - 14, 0), min(h + 14, 364) + 1)
    aday_tum = pencere_tum[(haftanin_gunu[pencere_tum] == haftanin_gunu[h]) & ~tatil[pencere_tum]]
    aday_gecmis = aday_tum[aday_tum < bit_gunu]
    aday_gelecek = aday_tum[aday_tum >= bit_gunu]
    assert aday_gecmis.size > 0 and aday_gelecek.size > 0  # senaryo geçerli

    satis[aday_gecmis, 0] = 10
    satis[aday_gelecek, 0] = 1000     # sızarsa katsayıyı çarpıcı şekilde değiştirir
    satis[h, 0] = 40

    katsayilar = ihtiyac.ozel_gun_katsayilari(satis, d, bit_gunu=bit_gunu)
    assert abs(katsayilar["Üst Giyim"] - 4.0) < 1e-9   # yalnız geçmiş günler paydada: 40/10


def test_ozel_gun_katsayisi_pencere_bossa_kategori_yok(mini_dunya):
    d = mini_dunya
    tatil = np.zeros(365, dtype=bool)
    h = 5
    tatil[h] = True
    d = dataclasses.replace(d, tatil=tatil)
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    satis[h, 0] = 999
    katsayilar = ihtiyac.ozel_gun_katsayilari(satis, d, bit_gunu=6)
    assert katsayilar == {}       # bit_gunu'nde kırpılan pencerede karşılaştırma günü yok


def test_sabit_ailesi_degeri_sabit_dondurur(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    ss = ihtiyac.guvenlik_stoku(GuvenlikStoku("sabit", 3.0), satis, d, 250)
    assert (ss == 3.0).all() and ss.shape == (d.oc_hucre.shape[0],)


def test_ros_ailesi_son_28_gun_ortalamasi_carpi_gun(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    k = 250
    for hucre in d.oc_hucre[0]:
        satis[k - 27:k + 1, hucre] = 1   # 28 gün × 5 beden × 1
    ss = ihtiyac.guvenlik_stoku(GuvenlikStoku("ros", 4.0), satis, d, k)
    assert abs(ss[0] - 20.0) < 1e-9      # (140/28) × 4


def test_kural_ongorusu_son_hafta_carpi_katsayi(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    k = 250
    for hucre in d.oc_hucre[0]:
        satis[k - 6:k + 1, hucre] = 2    # son 7 gün, 5 beden × 2 = 70
    ongoru = ihtiyac.kural_ongorusu(satis, d, k, {"Üst Giyim": 1.2})
    beklenen_katsayi = ihtiyac.hafta_katsayisi(d, k, 1.2)
    assert abs(ongoru[0] - 70 * beklenen_katsayi) < 1e-9


def test_kural_ongorusu_katsayi_yoksa_bir_varsayilir(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    k = 250
    for hucre in d.oc_hucre[0]:
        satis[k - 6:k + 1, hucre] = 2
    ongoru = ihtiyac.kural_ongorusu(satis, d, k, {})
    assert abs(ongoru[0] - 70 * ihtiyac.hafta_katsayisi(d, k, 1.0)) < 1e-9


def test_magaza_beden_paylari_kategori_gecmisinden(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    satis[100, d.oc_hucre[0, 0]] = 10    # M1-A, beden 1
    satis[100, d.oc_hucre[1, 2]] = 30    # M1-B, beden 3 (aynı mağaza, aynı kategori)
    paylar = ihtiyac.magaza_beden_paylari(satis, d, bit_gunu=200)
    assert abs(paylar[0, 0] - 0.25) < 1e-9
    assert abs(paylar[0, 2] - 0.75) < 1e-9
    assert (paylar[0] == paylar[1]).all()


def test_magaza_beden_paylari_satis_yoksa_zincir_payi(mini_dunya):
    d = mini_dunya
    satis = np.zeros((365, len(d.hucre_urun)), dtype=np.int32)
    paylar = ihtiyac.magaza_beden_paylari(satis, d, bit_gunu=200)
    assert np.allclose(paylar[0], d.zincir_beden_payi)
