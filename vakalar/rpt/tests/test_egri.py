import numpy as np
import pandas as pd
import pytest
from conftest import sentetik_gunluk
from perakende_analitik.carpanlar import Carpanlar

from rpt import egri, hazirla, kaynak

NOTR = Carpanlar()
GECMIS = pd.Timestamp("2024-02-12")     # SS24
OYUN = pd.Timestamp("2024-05-13")       # sentetik "AW24": SS24 indiriminden sonra, çıkışından önce


@pytest.fixture(scope="module")
def sentetik():
    """SS24 option'ı (geçmiş, 14 hafta: indirim 12. hafta) + AW24 option'ı (oyun)."""
    g, opt, b = sentetik_gunluk([("P1", "SS24", GECMIS, 14, 1), ("G1", "AW24", OYUN, 8, 1)],
                                magaza_sayisi=60)
    return g, opt, b


def test_basit_duzeltmesi_sansuru_duzeltir(sentetik):
    """Sansürlü satışın eğrisi öne yığılır; Basit kaybıyla düzeltilmiş eğri gerçeğe yakın."""
    g, opt, b = sentetik
    egriler = egri.oyun_egrileri(g, opt, "AW24", NOTR)
    ham, duz = egriler[("ham", "indirim")], egriler[("duzeltilmis", "indirim")]
    H = 12
    k_gercek = np.cumsum(b[:H] / b[:H].sum())
    k_ham, k_duz = ham.birikimli((1,))[1:], duz.birikimli((1,))[1:]
    assert len(k_duz) == H
    assert k_ham[3] > k_gercek[3] + 0.03
    assert np.abs(k_duz - k_gercek).max() < 0.03
    assert np.abs(k_duz - k_gercek).max() < np.abs(k_ham - k_gercek).max() / 2
    # yalnız geçmiş sezon
    assert duz.sezonlar == ("SS23", "AW23", "SS24")


def test_oyun_egrisi_gelecegi_gormez(sentetik):
    """Oyunun ilk lansman sabahından sonraki satırlar (oyun sezonu dahil) eğriyi değiştirmez."""
    g, opt, _ = sentetik
    a = egri.oyun_egrileri(g, opt, "AW24", NOTR)
    bozuk = g.copy()
    sonra = bozuk["tarih"] >= OYUN
    bozuk.loc[sonra, "brut_satis"] = bozuk.loc[sonra, "brut_satis"] * 5 + 1
    bozuk.loc[sonra, "durum"] = "bos"
    b = egri.oyun_egrileri(bozuk, opt, "AW24", NOTR)
    for anahtar in a:
        assert a[anahtar].paylar.keys() == b[anahtar].paylar.keys()
        for k in a[anahtar].paylar:
            np.testing.assert_allclose(a[anahtar].paylar[k], b[anahtar].paylar[k])
    # çıkış eğrisi oyun başlangıcında kırpılır: SS24'ün son haftası (13.) görünmez
    assert len(a[("duzeltilmis", "cikis")].paylar[(1,)]) == 13


def test_gercek_yontemi_yalniz_argumanla(sentetik):
    g, opt, b = sentetik
    with pytest.raises(ValueError):
        egri.egri_ogren(g, opt, ["SS24"], "gercek")
    with pytest.raises(ValueError):
        egri.oyun_egrisi(g, opt, "AW24", NOTR, "gercek")
    gercek = g[["tarih", "option_id"]].assign(talep=g["gercek_talep"])
    e = egri.egri_ogren(None, opt, ["SS24"], "gercek", gercek=gercek)
    H = 12
    np.testing.assert_allclose(e.birikimli((1,))[1:], np.cumsum(b[:H] / b[:H].sum()), atol=0.02)


def test_gecmis_sezonlar_egri():
    assert egri.gecmis_sezonlar("AW24") == ("SS23", "AW23", "SS24")
    assert egri.gecmis_sezonlar("SS25") == ("SS23", "AW23", "SS24", "AW24")


def test_egri_k_ara_deger_ve_kalan():
    e = egri.Egri(paylar={(1,): np.array([0.1, 0.2, 0.3, 0.4])}, grup=("dalga",), yontem="x",
                  hedef="indirim", sezonlar=("SS24",))
    assert e.k((1,), 0) == 0.0
    assert e.k(1, 2) == pytest.approx(0.3)
    assert e.k((1,), 2.5) == pytest.approx(0.45)
    assert e.k((1,), 10) == pytest.approx(1.0)
    assert e.kalan((1,), 3) == pytest.approx(0.4)
    yedekli = egri.Egri(paylar={("Üst", 1): np.array([0.5, 0.5])}, grup=("ust_kategori", "dalga"),
                        yontem="x", hedef="indirim", sezonlar=(), yedek=e)
    assert yedekli.k(("Alt", 1), 2) == pytest.approx(0.3)   # grup yok → dalga eğrisi


@pytest.mark.veri
def test_gercek_egriler_monoton_ve_bire_varir(veri):
    """AW24 oyun eğrileri gerçek v4'te (SS23, AW23, SS24; t0 = 2024-08-19)."""
    con = kaynak.baglan()
    try:
        try:
            yol = hazirla.gunluk_yolu(con=con)
        except RuntimeError as e:
            pytest.skip(str(e))
        opt = veri["opt"]
        t0 = egri.oyun_baslangici(opt, "AW24")
        havuz = egri.gecmis_havuzu(opt, egri.gecmis_sezonlar("AW24"))
        gunluk = hazirla.havuz_gunlugu(yol, con, havuz, t0)
        egriler = egri.oyun_egrileri(gunluk, opt, "AW24", hazirla.carpanlar(con, yol, t0))
    finally:
        con.close()
    for (yontem, hedef), e in egriler.items():
        assert e.sezonlar == ("SS23", "AW23", "SS24")
        assert set(e.paylar) == {(1,), (2,), (3,)}
        for anahtar in e.paylar:
            k = e.birikimli(anahtar)
            assert (np.diff(k) >= -1e-12).all()
            assert k[-1] == pytest.approx(1.0)
    # düzeltilmiş eğri ham eğriden geç biter (sansür erken haftaları şişirir)
    ham, duz = egriler[("ham", "indirim")], egriler[("duzeltilmis", "indirim")]
    assert duz.k((1,), 4) < ham.k((1,), 4)
