import numpy as np
import pytest

from rpt import egri, miktar


def _duz(n=10):
    return egri.Egri(paylar={(1,): np.full(n, 1.0 / n)}, grup=("dalga",), yontem="x", hedef="x", sezonlar=())


def test_banu_ve_frr():
    assert miktar.banu(2080, 300) == 1040
    assert miktar.banu(400, 300) == 300
    # (1 − 0,06) · 1000 / 0,25 − 2000 = 1760
    assert miktar.frr(1000, 0.25, 2000, 300) == 1760
    assert miktar.frr(1000, 0.5, 2000, 300) == 0         # tahmin ilk alımın altında
    assert miktar.frr(560, 0.25, 2000, 300) == 0          # 105 < MOQ/2
    assert miktar.frr(600, 0.25, 2000, 300) == 300        # 256 ≥ MOQ/2 → en az MOQ


def test_newsvendor_belirsizlik_yokken_eksigi_alir():
    # Düz eğri (10 hafta), h=2'de D=200 ⇒ sezon 1000; L=2 ⇒ geliş h=4.
    # Geliş öncesi talep 200, elde 100 ⇒ gelişte 0 stok; gelişten sonra tam
    # fiyat talep 600. İndirim dönemi yok (çıkış eğrisi = indirim eğrisi).
    e = _duz()
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q"] == 600
    assert nv["beklenen_tf"] == pytest.approx(600, abs=1)
    assert nv["beklenen_kar"] == pytest.approx(600 * 60, rel=1e-3)


def test_newsvendor_moq_kapisi():
    e = _duz()
    # Eksik yalnız 100 adet, MOQ 300: tam fiyattan MOQ/2 satamaz ⇒ sipariş yok
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=700, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q_serbest"] == 100
    assert nv["q"] == 0
    # Eksik 200: MOQ'nun beklenen kârı 200·100 − 300·40 = 8.000 > 0 ve 200 ≥ 150 ⇒ MOQ
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=600, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q"] == 300


def test_newsvendor_belirsizlikte_kritik_orana_gore():
    e = _duz()
    ucuz = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=10, p_ind=0, mu=0, sigma=0.4, moq=10)
    pahali = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=90, p_ind=0, mu=0, sigma=0.4, moq=10)
    assert ucuz["q"] > 600 > pahali["q"]


def test_kar_egrisi_elle():
    Q = np.array([0, 10, 20])
    tf, ind, kar = miktar.kar_egrisi(Q, np.array([5.0]), np.array([12.0]), np.array([4.0]),
                                     ip=5, p=10, p_ind=5, c=4)
    # C0 = 0 ⇒ tam fiyat ihtiyacı 12, indirim 4
    assert tf.tolist() == [0, 10, 12]
    assert ind.tolist() == [0, 0, 4]
    assert kar.tolist() == [0, 100 - 40, 120 + 20 - 80]


@pytest.mark.veri
def test_kalibrasyon_gelecegi_gormez(veri):
    from rpt import kaynak

    t, opt = veri["t"], veri["opt"]
    a = miktar.kalibrasyon(t, opt, "SS25")
    bas = kaynak.sezon_baslangici(t, "SS25")
    bozuk = dict(t)
    df = t["kayip_satis"].copy()
    df.loc[df["tarih"] >= bas, "kayip_adet"] *= 9
    bozuk["kayip_satis"] = df
    df = t["satis"].copy()
    df.loc[df["tarih"] >= bas, "adet"] *= 3
    bozuk["satis"] = df
    b = miktar.kalibrasyon(bozuk, opt, "SS25")
    assert a.mu == pytest.approx(b.mu) and a.sigma == pytest.approx(b.sigma)
    assert a.sezonlar == ("SS24", "AW24")
