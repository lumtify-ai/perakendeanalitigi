import numpy as np

from perakende_veri.v4.rastgele import binom_ters_cdf, poisson_ters_cdf, sayac_uretici


def test_sayac_uretici_gunden_bagimsiz():
    a = sayac_uretici(500, "talep").random(10)
    sayac_uretici(3, "talep").random(10**6)          # başka gün tüketimi
    assert np.array_equal(a, sayac_uretici(500, "talep").random(10))
    assert not np.array_equal(a, sayac_uretici(500, "iade").random(10))


def test_poisson_ters_cdf_dagilimi():
    rng = np.random.default_rng(0); u = rng.random(200_000)
    for lam in (0.05, 1.3, 12.0):
        k = poisson_ters_cdf(u, np.full(u.size, lam))
        assert abs(k.mean() - lam) < 0.02 * max(lam, 1)
        assert abs(k.var() - lam) < 0.05 * max(lam, 1)


def test_poisson_monoton_lambda():
    u = np.random.default_rng(1).random(50_000)
    lam = np.random.default_rng(2).gamma(1.0, 2.0, 50_000)
    assert (poisson_ters_cdf(u, lam * 1.3) >= poisson_ters_cdf(u, lam)).all()


def test_poisson_sifir_lambda_sifir():
    assert (poisson_ters_cdf(np.array([0.0, 0.999999]), np.zeros(2)) == 0).all()


def test_binom_dizi_p():
    u = np.random.default_rng(3).random(100_000); n = np.full(u.size, 10)
    k = binom_ters_cdf(u, n, np.full(u.size, 0.3))
    assert abs(k.mean() - 3.0) < 0.03 and (k <= n).all()
