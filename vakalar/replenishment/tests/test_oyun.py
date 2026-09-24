import numpy as np
import pytest

from replenishment.dagitim import KoliKurali
from replenishment.depo import Depo
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.motor import baslangic_durumu
from replenishment.olcutler import hesapla
from replenishment.oyun import OyunAyari, oyna
from replenishment.politika import KuralPolitikasi, TahminPolitikasi


def _kur(mini_dunya, talep_carpani=1):
    H = len(mini_dunya.hucre_urun)
    talep = np.zeros((365, H), np.int32); talep[243:] = talep_carpani
    gecmis = np.zeros((365, H), np.int32); gecmis[200:243] = 1
    pol = KuralPolitikasi(GuvenlikStoku("sabit", 2), {"Üst Giyim": 1.0, "Alt Giyim": 1.0, "Dış Giyim": 1.0})
    ayar = OyunAyari(0.8, KoliKurali("A"), acik_kapasite=50)
    paylar = np.full((len(mini_dunya.oc_hucre), 5), 0.2)
    return talep, gecmis, pol, ayar, paylar


def test_korunum_satis_ve_kayip_adedi_talebe_esit(mini_dunya):
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya)
    s = oyna(mini_dunya, talep, gecmis, baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), []),
             pol, ayar, paylar)
    o = s.olcutler
    assert o["satis_adet"] + o["kayip_adet"] == pytest.approx(o["talep_adet"])


def test_sizinti_yok_gelecek_talep_karari_degistirmez(mini_dunya):
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya)
    bas = lambda: baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), [])
    s1 = oyna(mini_dunya, talep, gecmis, bas(), pol, ayar, paylar)
    talep2 = talep.copy(); talep2[mini_dunya.gun("2025-09-02"):] *= 5
    s2 = oyna(mini_dunya, talep2, gecmis, bas(), pol, ayar, paylar)
    # ilk karar (1 Eylül gecesi) yalnız geçmişi görür: iki oyunda aynı
    assert s1.haftalik[0] == s2.haftalik[0]


def test_deterministik(mini_dunya):
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya)
    bas = lambda: baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), [])
    assert oyna(mini_dunya, talep, gecmis, bas(), pol, ayar, paylar).olcutler == \
           oyna(mini_dunya, talep, gecmis, bas(), pol, ayar, paylar).olcutler


def test_on_yedi_karar(mini_dunya):
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya)
    s = oyna(mini_dunya, talep, gecmis, baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), []),
             pol, ayar, paylar)
    assert len(s.haftalik) == 17


def test_talep_sifirken_kayipsiz(mini_dunya):
    # Hiç talep olmayan bir dünyada kayıp ve satış sıfır, oran sıfır olmalı (NaN yok).
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya, talep_carpani=0)
    s = oyna(mini_dunya, talep, gecmis, baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), []),
             pol, ayar, paylar)
    o = s.olcutler
    assert o["talep_adet"] == 0
    assert o["satis_adet"] == 0
    assert o["kayip_adet"] == 0
    assert o["kayip_orani"] == 0.0
    assert o["bulunabilirlik"] == 0.0
    assert not any(np.isnan(v) for v in o.values())


def test_kirik_cift_ve_beden_sapmasi_dogrudan(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    durum = baslangic_durumu(np.zeros(H, np.int64), [])
    # OC0 (M1,A): beden 1,2,4,5 dolu, beden 3 (idx 2) boş -> stoklu ve kırık çift.
    durum.stok[mini_dunya.oc_hucre[0]] = [5, 5, 0, 5, 5]
    # OC3 (M2,B): tam dolu, kırık değil.
    durum.stok[mini_dunya.oc_hucre[3]] = [2, 2, 2, 2, 2]
    durum.talepli_gun = 10
    durum.stoklu_talepli_gun = 7

    depo = Depo(koli=np.zeros(2, np.int64), acik=np.zeros((2, 5), np.int64))
    gozlenen = np.zeros((365, H), np.int32)
    talep = np.zeros((365, H), np.int32)
    ayar = OyunAyari(0.8, KoliKurali("A"), acik_kapasite=50)

    o = hesapla(durum, mini_dunya, depo, [], talep, gozlenen, baslangic_stok=0.0, ayar=ayar)

    assert o["kirik_cift"] == 1.0
    assert o["bulunabilirlik"] == pytest.approx(70.0)
    assert o["magaza_stok_son"] == 5 * 4 + 2 * 5

    from replenishment.ihtiyac import magaza_beden_paylari
    bas_gunu = mini_dunya.gun(ayar.bas)
    paylar = magaza_beden_paylari(gozlenen, mini_dunya, bas_gunu)
    p0 = np.array([5, 5, 0, 5, 5], dtype=float) / 20.0
    p3 = np.array([2, 2, 2, 2, 2], dtype=float) / 10.0
    tvd0 = 0.5 * np.abs(p0 - paylar[0]).sum()
    tvd3 = 0.5 * np.abs(p3 - paylar[3]).sum()
    beklenen = round(float((tvd0 + tvd3) / 2 * 100), 1)
    assert o["beden_sapmasi"] == pytest.approx(beklenen)


class _SahteTahminci:
    """Task 8'in gerçek `Tahminci.tahmin_et(self, satis, dunya, karar_gunu)`
    imzasını taklit eder (bkz. task-8-brief.md) — `stok` argümanı yok.
    `TahminPolitikasi.hedef` bu imzadan sapıp `stok` geçirirse bu test
    TypeError ile başarısız olur."""

    def tahmin_et(self, satis, dunya, karar_gunu):
        OC = dunya.oc_hucre.shape[0]
        return np.full(OC, 3.0)


def test_tahmin_politikasi_ucuncu_taraf_imzayla_cagirir(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    gozlenen = np.zeros((365, H), np.int32)
    pol = TahminPolitikasi(_SahteTahminci())
    hedef, ongoru = pol.hedef(gozlenen, mini_dunya, 300, np.zeros(H, np.int64))
    assert (hedef == 3.0).all()
    assert (ongoru == 3.0).all()


def test_olcutler_anahtarlari_tam(mini_dunya):
    talep, gecmis, pol, ayar, paylar = _kur(mini_dunya)
    s = oyna(mini_dunya, talep, gecmis, baslangic_durumu(np.zeros(len(mini_dunya.hucre_urun), np.int64), []),
             pol, ayar, paylar)
    beklenen_anahtarlar = {
        "talep_adet", "satis_adet", "kayip_adet", "kayip_orani", "bulunabilirlik",
        "satisa_donme_gun", "satilmayan_gonderilen", "gonderilen_adet",
        "koli_sayisi", "acik_adet", "toplama_maliyeti_tl", "acik_doluluk",
        "magaza_stok_son", "depo_kalan", "kirik_cift", "beden_sapmasi", "str",
    }
    assert beklenen_anahtarlar <= set(s.olcutler.keys())
    for k, v in s.olcutler.items():
        assert isinstance(v, float), f"{k} float değil: {type(v)}"
