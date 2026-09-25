import numpy as np
import pandas as pd
import pytest

from perakende_veri import sabitler as v2_sabitler
from perakende_veri.magaza import magazalari_uret
from perakende_veri.v3 import sabitler
from perakende_veri.v3.dunya import dunya_yeniden_kur, talep_matrisi
from perakende_veri.v3.tedarik import moq_yuvarla


@pytest.fixture(scope="module")
def dunya(v3_kosu):
    return v3_kosu["dunya"]


def test_magazalar_v2_ile_ayni(dunya):
    v2 = magazalari_uret(np.random.default_rng(v2_sabitler.TOHUM))
    pd.testing.assert_frame_equal(dunya.magazalar, v2)


def test_dunya_deterministik(dunya):
    ikinci = dunya_yeniden_kur()
    assert np.array_equal(ikinci.gercek_statik, dunya.gercek_statik)
    assert np.array_equal(ikinci.g_gercek, dunya.g_gercek)
    assert np.array_equal(ikinci.ilk_dagitim_hucre, dunya.ilk_dagitim_hucre)
    pd.testing.assert_frame_equal(ikinci.cesit, dunya.cesit)


def test_plan_surprizi_ve_suruklenmeyi_bilmez(dunya):
    d = np.arange(dunya.gun_sayisi)
    oran = np.divide(dunya.g_gercek[d], dunya.g_plan[d], out=np.ones_like(dunya.g_plan[d]),
                     where=dunya.g_plan[d] > 0)
    beklenen = dunya.surpriz[None, :] * dunya.suruklenme[:, d // 7].T
    aktif = dunya.g_plan[d] > 0
    assert np.allclose(oran[aktif], beklenen[aktif])


def test_suruklenme_ar1(dunya):
    x = np.log(dunya.suruklenme)
    rho = np.corrcoef(x[:, 1:].ravel(), x[:, :-1].ravel())[0, 1]
    assert 0.6 < rho < 0.8
    assert 0.08 < x.std() < 0.2


def test_surpriz_line_sigmasiyla(dunya):
    opt = dunya.optionlar
    log_s = np.log(dunya.surpriz)
    coll = log_s[(opt.line == "Collection").to_numpy()]
    nos = log_s[(opt.line == "NOS").to_numpy()]
    assert 0.45 < coll.std() < 0.65
    assert nos.std() < 0.2


def test_sezonluk_urun_yalniz_lansman_ile_cikis_arasinda_aktif(dunya):
    opt = dunya.optionlar
    for o in np.flatnonzero(opt["sezonluk"].to_numpy())[:40]:
        L, X = int(opt.at[o, "lansman_gun"]), int(opt.at[o, "cikis_gun"])
        g = dunya.g_plan[:, o]
        assert (g[: max(L, 0)] == 0).all()
        assert (g[L:X] > 0).all()
        assert (g[X:] == 0).all()


def test_ilk_alim_kurali(dunya):
    opt = dunya.optionlar
    sezonluk = opt["sezonluk"].to_numpy()
    for o in np.flatnonzero(sezonluk):
        beklenen = moq_yuvarla(dunya.plan_sezon[o] / sabitler.HEDEF_TAM_FIYAT_STR, int(opt.at[o, "moq_option"]))
        assert dunya.ilk_alim[o] == beklenen
        sk = dunya.sku_option == o
        assert dunya.ilk_alim_sku[sk].sum() == dunya.ilk_alim[o]
    assert (dunya.ilk_alim[~sezonluk] == 0).all()


def test_ilk_dagitim_yuzde_altmis(dunya):
    magazaya = np.bincount(dunya.hucre_sku, dunya.ilk_dagitim_hucre, minlength=len(dunya.urunler))
    sezonluk_sku = dunya.optionlar["sezonluk"].to_numpy()[dunya.sku_option]
    beklenen = np.rint(sabitler.ILK_DAGITIM_PAYI * dunya.ilk_alim_sku)
    # Çeşitte hiç mağazası olmayan SKU yok; her SKU'nun %60'ı mağazalara
    assert np.array_equal(magazaya[sezonluk_sku], beklenen[sezonluk_sku])
    assert (dunya.ilk_dagitim_hucre[~dunya.optionlar["sezonluk"].to_numpy()[dunya.hucre_option]] == 0).all()


def test_ilk_siparis_tarihleri(dunya):
    opt = dunya.optionlar
    for s in dunya.ilk_siparisler:
        o = s["option"]
        L = int(opt.at[o, "lansman_gun"])
        assert s["siparis_gun"] == L - 7 * int(opt.at[o, "ilk_siparis_hafta"])
        assert s["planlanan_gun"] == L - 7
        assert opt.at[o, "ilk_dagitim_gun"] == max(L, s["gerceklesen_gun"])
    gecikme = np.array([s["gerceklesen_gun"] - s["planlanan_gun"] for s in dunya.ilk_siparisler])
    assert (gecikme > 7).any()      # bazı Uzak Doğu siparişleri lansmanı kaçırır


def test_talep_matrisi_deterministik_ve_aktiflige_bagli(dunya, v3_kosu):
    t = v3_kosu["talep"]
    assert t.shape == (dunya.gun_sayisi, len(dunya.cesit))
    assert np.array_equal(t[:30], talep_matrisi(dunya)[:30])
    opt = dunya.optionlar
    lansman = opt["lansman_gun"].to_numpy()[dunya.hucre_option]
    cikis = opt["cikis_gun"].to_numpy()[dunya.hucre_option]
    gun = np.arange(dunya.gun_sayisi)[:, None]
    pasif = (gun < lansman[None, :]) | (gun >= cikis[None, :])
    assert t[pasif].sum() == 0
