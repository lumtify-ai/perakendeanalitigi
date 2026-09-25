import numpy as np
import pandas as pd
import pytest

from rpt import egri, kaynak


def _sentetik(tohum=3, C=60, H=12):
    """Bilinen şekil b_h; seviyesi yüksek hücreler 3. haftadan sonra stoksuz
    kalır (satış sansürlenir). Döner: hh benzeri tablo, opt, gerçek pay."""
    rng = np.random.default_rng(tohum)
    h = np.arange(H)
    b = (h + 1) * np.exp(-h / 4.0)
    a = rng.lognormal(0, 0.6, C)
    satir = []
    for c in range(C):
        for w in range(H):
            lam = a[c] * b[w]
            talep = rng.poisson(lam * 7)
            # Yüksek seviyeli hücreler (üst çeyrek) 3. haftadan sonra 1 gün stoklu
            st = 1 if (a[c] > np.quantile(a, 0.75) and w >= 3) else 7
            satis = rng.poisson(lam * st)
            satir.append({"magaza_id": f"M{c}", "urun_id": "U", "option_id": "O", "h": w,
                          "satis": satis, "kayip": max(talep - satis, 0), "stoklu_gun": st,
                          "acik_gun": 7, "ilk_dagitim": 1})
    hh = pd.DataFrame(satir)
    hh["satis_io"], hh["kayip_io"], hh["acik_io"] = hh["satis"], hh["kayip"], hh["acik_gun"]
    opt = pd.DataFrame({"option_id": ["O"], "sezon_kodu": ["SS24"], "line": ["Collection"],
                        "dalga": [1], "ust_kategori": ["Üst"]})
    return hh, opt, b / b.sum()


def test_ipf_sansuru_duzeltir():
    hh, opt, gercek_pay = _sentetik()
    duz = egri.egri_ogren(hh, opt, ["SS24"], "duzeltilmis")
    ham = egri.egri_ogren(hh, opt, ["SS24"], "ham")
    k_gercek = np.cumsum(gercek_pay)
    k_duz = duz.birikimli((1,))[1:]
    k_ham = ham.birikimli((1,))[1:]
    # Çıplak eğri sansür yüzünden öne yığılır; düzeltilmiş gerçeğe yakındır
    assert k_ham[3] > k_gercek[3] + 0.03
    assert np.abs(k_duz - k_gercek).max() < 0.03
    assert np.abs(k_duz - k_gercek).max() < np.abs(k_ham - k_gercek).max() / 2


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
    t, opt = veri["t"], veri["opt"]
    for sezon in kaynak.OYUN_SEZONLARI:
        for yontem in ("ham", "duzeltilmis"):
            for hedef in ("indirim", "cikis"):
                e = egri.oyun_egrisi(t, opt, sezon, yontem, hedef=hedef)
                for anahtar in e.paylar:
                    k = e.birikimli(anahtar)
                    assert (np.diff(k) >= -1e-12).all()
                    assert k[-1] == pytest.approx(1.0)
                    assert k[0] == 0.0


@pytest.mark.veri
def test_gecmis_sezonlar(veri):
    t = veri["t"]
    assert egri.gecmis_sezonlar(t, "AW24") == ("SS24",)
    assert egri.gecmis_sezonlar(t, "SS25") == ("SS24", "AW24")


@pytest.mark.veri
def test_sizinti_kalkani_egri_gelecegi_gormez(veri):
    """Oyun sezonunun eğrisi, oyun başladıktan sonraki veri bozulsa da aynı."""
    t, opt = veri["t"], veri["opt"]
    for sezon in kaynak.OYUN_SEZONLARI:
        bas = kaynak.sezon_baslangici(t, sezon)
        bozuk = dict(t)
        for ad, kolon in (("satis", "adet"), ("kayip_satis", "kayip_adet")):
            df = t[ad].copy()
            sonra = df["tarih"] >= bas
            df.loc[sonra, kolon] = df.loc[sonra, kolon] * 5
            bozuk[ad] = df
        st = t["stok"].copy()
        st.loc[st["tarih"] > bas, "stoklu_gun"] = 0
        bozuk["stok"] = st
        for yontem in ("ham", "duzeltilmis"):
            a = egri.oyun_egrisi(t, opt, sezon, yontem)
            b = egri.oyun_egrisi(bozuk, opt, sezon, yontem)
            assert a.paylar.keys() == b.paylar.keys()
            for k in a.paylar:
                np.testing.assert_allclose(a.paylar[k], b.paylar[k])
            # ve yalnız geçmiş sezonları kullanır
            assert sezon not in a.sezonlar
