import numpy as np

from replenishment.tahmin import OZELLIKLER, Tahminci, egitim_seti, ozellik_tablosu

P = {"num_leaves": 15, "n_estimators": 50, "learning_rate": 0.05, "min_child_samples": 5}


def test_egitim_hedefi_karar_gununu_asmaz(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    s = np.ones((365, H), np.int32)
    k = mini_dunya.gun("2025-09-01")
    s[k + 1 :] = 999  # gelecek bozuk
    X, y = egitim_seti(s, mini_dunya, k, mini_dunya.gun("2025-06-02"))
    assert y.max() < 999


def test_sifir_hedefte_negatif_ya_da_nan_yok(mini_dunya):
    H = len(mini_dunya.hucre_urun)
    s = np.zeros((365, H), np.int32)
    t = Tahminci(P, mini_dunya.gun("2025-06-02")).tahmin_et(s, mini_dunya, mini_dunya.gun("2025-09-01"))
    assert (t >= 0).all() and not np.isnan(t).any()


def test_deterministik(mini_dunya):
    rng = np.random.default_rng(1)
    s = rng.poisson(0.5, (365, len(mini_dunya.hucre_urun))).astype(np.int32)
    tc = Tahminci(P, mini_dunya.gun("2025-06-02"))
    k = mini_dunya.gun("2025-09-01")
    assert (tc.tahmin_et(s, mini_dunya, k) == tc.tahmin_et(s, mini_dunya, k)).all()


def test_ozellik_tablosu_oc_basina_bir_satir(mini_dunya):
    s = np.zeros((365, len(mini_dunya.hucre_urun)), np.int32)
    X = ozellik_tablosu(s, mini_dunya, mini_dunya.gun("2025-09-01"))
    assert len(X) == len(mini_dunya.oc_hucre) and list(X.columns) == OZELLIKLER
