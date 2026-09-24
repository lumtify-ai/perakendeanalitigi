import numpy as np
import pytest

from replenishment import kaynak, sabitler
from replenishment.dunya import dunya_kur
from replenishment.gecmis import V2Politikasi, gecmisi_oynat, yol_baslangici
from replenishment.motor import Durum


def test_v2_politikasi_acilis_gununde_her_hucreye_hedef(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    pol = V2Politikasi()
    stok = np.zeros(H, dtype=np.int64)
    gonderilen = pol.gonderilecek(mini_dunya, 0, stok, [])
    # plan = 0.1/gün → hedef = rint(0.1*7*6) = 4
    assert (gonderilen == 4).all()


def test_v2_politikasi_olu_stok_koruyucusu_engel_olur(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    pol = V2Politikasi()
    stok = np.full(H, 2, dtype=np.int64)
    # son 28 günde hiç satış yok -> haftalik hız 0 -> stok(2) < 0*6 yanlış -> engellenir
    son_satislar = [np.zeros(H, dtype=np.int64) for _ in range(28)]
    gonderilen = pol.gonderilecek(mini_dunya, 12, stok, son_satislar)
    assert (gonderilen == 0).all()


def test_v2_politikasi_yeterli_hiz_varsa_gonderir(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    pol = V2Politikasi()
    stok = np.full(H, 2, dtype=np.int64)
    # son 28 günde günde 1 satış -> haftalik hız 7 -> stok(2) < 7*6=42 doğru
    son_satislar = [np.ones(H, dtype=np.int64) for _ in range(28)]
    gonderilen = pol.gonderilecek(mini_dunya, 12, stok, son_satislar)
    assert (gonderilen == 2).all()  # hedef(4) - stok(2) = 2


def test_gecmisi_oynat_acilis_gunu_sevk_eder_sonraki_pazartesiye_kadar_bekler(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    talep = np.zeros((365, H), dtype=np.int32)
    gozlenen, durum = gecmisi_oynat(mini_dunya, talep, bit="2025-01-13")
    # 2025-01-01 (gün 0, açılış) hedef=4 her hücreye; 2025-01-06 pazartesi
    # hafta 2 -> (2-1)%2=1 -> sevk yok; bit 2025-01-13'ten önce durur.
    assert durum.toplam_gonderilen == H * 4


def test_gecmisi_oynat_iki_haftada_bir_pazartesi_tekrar_sevk_eder(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    talep = np.zeros((365, H), dtype=np.int32)
    # talep sıfır olduğundan stok hiç düşmez, hedefe zaten ulaşılmıştır;
    # 2025-01-13 (hafta 3, (3-1)%2=0) tekrar sevkiyat günüdür ama eksik=0
    # olduğundan toplam sevkiyat yine açılışla aynı kalmalı.
    gozlenen, durum = gecmisi_oynat(mini_dunya, talep, bit="2025-01-14")
    assert durum.toplam_gonderilen == H * 4


def test_gecmisi_oynat_durum_alanlari(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    talep = np.zeros((365, H), dtype=np.int32)
    gozlenen, durum = gecmisi_oynat(mini_dunya, talep, bit="2025-01-13")
    assert isinstance(durum, Durum)
    assert gozlenen.shape == (365, H)


@pytest.mark.veri
def test_v2_politikasi_v2_sevkiyatini_yaklasik_uretir():
    d = dunya_kur()
    con = kaynak.baglan()
    satis, durum = gecmisi_oynat(d, kaynak.kahin_talep(con, d))
    bit = d.gun("2025-09-01")
    v2 = kaynak.sevkiyat(con, d)[:bit].sum()
    assert abs(durum.toplam_gonderilen / v2 - 1) < 0.01


@pytest.mark.veri
def test_yol_baslangici_yol_0_gercek_veriyi_kullanir():
    d = dunya_kur()
    con = kaynak.baglan()
    talep, gecmis_satis, durum = yol_baslangici(d, 0, con)

    bas_gunu = d.gun(sabitler.OYUN_BAS)
    beklenen_talep = kaynak.kahin_talep(con, d)
    assert np.array_equal(talep, beklenen_talep)

    beklenen_gecmis = kaynak.gozlenen_satis(con, d)
    beklenen_gecmis = beklenen_gecmis.copy()
    beklenen_gecmis[bas_gunu:] = 0
    assert np.array_equal(gecmis_satis, beklenen_gecmis)

    beklenen_stok = kaynak.stok_fotografi(con, d, sabitler.OYUN_BAS)
    assert np.array_equal(durum.stok, beklenen_stok)
    assert len(durum.iade_kuyrugu) == sabitler.IADE_GECIKME


@pytest.mark.veri
def test_yol_baslangici_yol_1_talep_yolu_ve_gecmisi_kullanir():
    d = dunya_kur()
    con = kaynak.baglan()
    talep, gecmis_satis, durum = yol_baslangici(d, 1, con)

    from replenishment.talep_yolu import talep_yolu

    assert np.array_equal(talep, talep_yolu(d, 1))
    assert isinstance(durum, Durum)
    bas_gunu = d.gun(sabitler.OYUN_BAS)
    assert (gecmis_satis[bas_gunu:] == 0).all()
