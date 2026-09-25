import numpy as np
import pytest

from replenishment.dagitim import KoliKurali
from replenishment.depo import Depo
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.motor import baslangic_durumu
from replenishment.olcutler import hesapla
from replenishment.oyun import OyunAyari, oyna
from replenishment.politika import (
    KuralPolitikasi,
    TahminPolitikasi,
    TahminTabanPolitikasi,
)


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
    # 6 (mağaza, option) çifti: OC0 ve OC3 stoklu, kalan 4 boş. kirik_cift
    # yalnız stoklu çiftler içinde anlamlı; boş rafı "kırık değil" saymak
    # yanıltıcı olduğundan stoklu/boş sayıları ve pay ayrıca raporlanır.
    assert o["stoklu_cift_sayisi"] == 2.0
    assert o["bos_cift_sayisi"] == 4.0
    assert o["kirik_cift_pay_yuzde"] == pytest.approx(50.0)
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


# --- Kural hedefi: safety stock taban, eklenen tampon degil ---------------

def test_kural_hedefi_safety_stock_ile_ongorunun_buyugu(mini_dunya):
    """Hedef = max(ongoru, safety stock); ikisinin toplami DEGIL.

    Safety stock sahada "minimum sergileme"dir: raf hic bosalmasin diye
    konan taban. Ongorunun ustune eklenince hedef gercek talebin belirgin
    ustune cikiyor ve zincir surekli fazla mal tasiyor.
    """
    H = len(mini_dunya.hucre_urun)
    OC = len(mini_dunya.oc_hucre)
    katsayilar = {"Üst Giyim": 1.0, "Alt Giyim": 1.0, "Dış Giyim": 1.0}
    gozlenen = np.zeros((365, H), np.int32)
    karar = mini_dunya.gun("2025-09-01")

    # Ilk OC'nin son 7 gununde 10 adet satis var, safety stock sabit 2:
    # ongoru (10) buyuk, hedef 10 olmali -- 12 degil.
    for hucre in mini_dunya.oc_hucre[0]:
        gozlenen[karar - 3, hucre] = 2
    pol = KuralPolitikasi(GuvenlikStoku("sabit", 2), katsayilar)
    hedef, ongoru = pol.hedef(gozlenen, mini_dunya, karar, np.zeros(H, np.int64))
    assert ongoru[0] == pytest.approx(10.0)
    assert hedef[0] == pytest.approx(10.0)

    # Hic satmayan OC'lerde ongoru 0; taban devreye girer, hedef 2.
    assert ongoru[1] == pytest.approx(0.0)
    assert hedef[1] == pytest.approx(2.0)

    # Ongoru hicbir zaman hedefi asmaz, hedef hicbir zaman toplama esit degil
    assert (hedef >= ongoru).all()
    assert hedef.sum() < (ongoru + 2.0).sum()
    assert len(hedef) == OC


def test_oyna_stoklu_gunlugu_politikaya_gecirir(mini_dunya):
    """Politika stoklu_gunluk argümanını gerçekten alır ve oyunun kendi
    ürettiği bayrakları görür (hepsi True olan başlangıç değil)."""
    gorulen = []

    class _Casus:
        def hedef(self, gozlenen, dunya, karar_gunu, stok, stoklu_gunluk):
            gorulen.append(stoklu_gunluk.copy())
            OC = len(dunya.oc_hucre)
            return np.zeros(OC), np.zeros(OC)

    talep, gecmis, _, ayar, paylar = _kur(mini_dunya)
    H = len(mini_dunya.hucre_urun)
    oyna(mini_dunya, talep, gecmis, baslangic_durumu(np.zeros(H, np.int64), []),
         _Casus(), ayar, paylar)
    assert len(gorulen) == 17
    bas = mini_dunya.gun("2025-09-01")
    # başlangıçta stok yok -> oyunun ilk günleri stoksuz işaretlenmiş olmalı
    assert not gorulen[-1][bas:bas + 3].all()


# --- Tahmin + taban: politika ayni, ongoru kaynagi farkli ----------------

def test_tahmin_taban_politikasi_ongoruyu_tabanla_birlestirir(mini_dunya):
    """Kural politikasiyla AYNI hedef kurali, yalniz ongoru LightGBM'den.

    Boylece iki kol arasindaki fark politikadan degil, ongorunun
    isabetinden gelir -- karsilastirmanin anlamli olmasi buna bagli.
    """
    H = len(mini_dunya.hucre_urun)
    OC = len(mini_dunya.oc_hucre)
    gozlenen = np.zeros((365, H), np.int32)
    karar = mini_dunya.gun("2025-09-01")

    # Sahte tahminci her OC icin 3.0 doner; sabit taban 5 -> hedef 5
    pol = TahminTabanPolitikasi(_SahteTahminci(), GuvenlikStoku("sabit", 5))
    hedef, ongoru = pol.hedef(gozlenen, mini_dunya, karar, np.zeros(H, np.int64), None)
    assert (ongoru == 3.0).all()
    assert (hedef == 5.0).all()
    assert len(hedef) == OC

    # Taban 1 olunca ongoru buyuk kalir -> hedef 3
    pol2 = TahminTabanPolitikasi(_SahteTahminci(), GuvenlikStoku("sabit", 1))
    hedef2, _ = pol2.hedef(gozlenen, mini_dunya, karar, np.zeros(H, np.int64), None)
    assert (hedef2 == 3.0).all()


# --- Line kirilimi: NOS ile Collection ayni sekilde davranmaz --------------

def test_line_kirilimi_bulunabilirligi_line_basina_ayirir(mini_dunya):
    """Her line icin talep, satis, bulunabilirlik ve donem sonu stok.

    Iddia ("NOS neredeyse hic stoksuz kalmaz, Collection kalir") ancak bu
    kirilimla olculebilir; toplam rakam iki line'i birbirine karistirir.
    """
    from replenishment.olcutler import line_kirilimi

    H = len(mini_dunya.hucre_urun)
    bas = mini_dunya.gun("2025-09-01")
    durum = baslangic_durumu(np.zeros(H, np.int64), [])
    talep = np.zeros((365, H), np.int32)

    # A = Collection, B = NOS (mini_dunya fikstürü boyle kuruyor)
    a_hucre = mini_dunya.oc_hucre[0]          # M1-A
    b_hucre = mini_dunya.oc_hucre[1]          # M1-B
    talep[bas, a_hucre[2]] = 4                 # Collection: talep var, stok yok
    talep[bas, b_hucre[2]] = 4                 # NOS: talep var, stok var
    durum.stoklu_gunluk[bas, a_hucre[2]] = False
    durum.stoklu_gunluk[bas, b_hucre[2]] = True
    durum.stok[b_hucre[2]] = 10

    gozlenen = np.zeros((365, H), np.int32)
    gozlenen[bas, b_hucre[2]] = 4              # NOS stoklu: talebin tamami satildi
    gozlenen[bas, a_hucre[2]] = 0              # Collection stoksuz: hic satis yok
    k = line_kirilimi(durum, mini_dunya, talep, gozlenen, bas, mini_dunya.gun("2025-12-31"))
    assert k["Collection"]["talep_adet"] == 4.0
    assert k["NOS"]["talep_adet"] == 4.0
    assert k["Collection"]["bulunabilirlik"] == 0.0
    assert k["NOS"]["bulunabilirlik"] == 100.0
    assert k["NOS"]["satis_adet"] == 4.0
    assert k["Collection"]["satis_adet"] == 0.0
    assert k["Collection"]["kayip_orani"] == 100.0
    assert k["NOS"]["kayip_orani"] == 0.0
    assert k["NOS"]["magaza_stok_son"] == 10.0
    assert k["Collection"]["magaza_stok_son"] == 0.0
    # Talebin hic olmadigi line'lar NaN degil sifir doner
    for line, deger in k.items():
        assert not any(np.isnan(v) for v in deger.values()), line
