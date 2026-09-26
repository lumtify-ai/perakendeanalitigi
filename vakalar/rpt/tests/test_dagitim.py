import numpy as np
import pytest

from rpt import dagitim, egri


def test_hiz_hedefi_son_stoklu_gunler():
    # İki hücre, 10 gün. Hücre 0: ilk 6 gün stoklu, günde 2 satar, sonra boş.
    # Hücre 1: hiç stoklu değil. Eğri düz (β = 1/7).
    S = np.zeros((10, 2))
    F = np.zeros((10, 2), dtype=bool)
    S[:6, 0], F[:6, 0] = 2, True
    beta = np.full(10, 1 / 7)
    hedef, var = dagitim.hiz_hedefi(S, F, beta, beta_ileri=28 / 7)
    # seviye = 12 / (6/7) = 14 ⇒ günlük 2 ⇒ 28 günde 56. Son 7 gün satış 0
    # olsa da hız sıfır görünmez (bugünkü kapının tersine).
    assert hedef[0] == pytest.approx(56)
    assert var.tolist() == [True, False]


def test_hiz_hedefi_pencere_en_son_stoklu_gunler():
    S = np.zeros((40, 1))
    F = np.ones((40, 1), dtype=bool)
    S[:10, 0] = 10    # eski yüksek satış
    S[10:, 0] = 1     # son 30 gün günde 1
    beta = np.full(40, 1 / 7)
    hedef, _ = dagitim.hiz_hedefi(S, F, beta, beta_ileri=4, pencere=28)
    assert hedef[0] == pytest.approx(28)   # yalnız son 28 stoklu gün


def test_hiz_hedefi_egriyle_tasir():
    # Geçmişte eğri ağırlığı 2, ileride 1: hız yarıya iner
    S = np.full((7, 1), 4.0)
    F = np.ones((7, 1), dtype=bool)
    hedef, _ = dagitim.hiz_hedefi(S, F, np.full(7, 2.0), beta_ileri=28 * 1.0)
    assert hedef[0] == pytest.approx(2 * 28)


def test_gunluk_agirlik():
    e = egri.Egri(paylar={(1,): np.array([0.7, 0.3])}, grup=("dalga",), yontem="x", hedef="cikis",
                  sezonlar=())
    b = dagitim.gunluk_agirlik(e, 1, 20)
    assert b[:7].sum() == pytest.approx(0.7) and b[7:14].sum() == pytest.approx(0.3)
    assert b[14:].sum() == 0
