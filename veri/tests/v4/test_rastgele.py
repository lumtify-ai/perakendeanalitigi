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


def _poisson_ters_cdf_eski(u, lam):
    """Son incelemeden önceki `poisson_ters_cdf` (200 yinelemede kırpar,
    exp(−λ) büyük λ'da sıfıra yuvarlanır); λ < 150'de yenisiyle bit bit
    aynı olmalı."""
    u = np.asarray(u, dtype=float)
    lam = np.broadcast_to(np.asarray(lam, dtype=float), u.shape).astype(float)
    k = np.zeros(u.shape, dtype=np.int64)
    pmf = np.exp(-lam)
    cdf = pmf.copy()
    for j in range(200):
        asan = u > cdf
        if not asan.any():
            break
        k += asan
        pmf = pmf * lam / (j + 1)
        cdf = cdf + pmf
    return k


def test_poisson_kucuk_lambda_eskisiyle_bit_bit_ayni():
    rng = np.random.default_rng(11)
    n = 1_000_000
    u = rng.random(n)
    # Motorun gerçek dağılımına benzer karışım: çoğu küçük, kuyruk 150'ye dek.
    lam = np.concatenate([rng.gamma(0.6, 0.5, n // 2), rng.uniform(0.0, 150.0, n - n // 2)])
    lam = np.minimum(lam, np.nextafter(150.0, 0.0))
    rng.shuffle(lam)
    np.testing.assert_array_equal(poisson_ters_cdf(u, lam), _poisson_ters_cdf_eski(u, lam))
    # Sıfır λ ve tek hücre de aynı
    np.testing.assert_array_equal(poisson_ters_cdf(u[:10], np.zeros(10)), _poisson_ters_cdf_eski(u[:10], np.zeros(10)))


def test_poisson_buyuk_lambda_kesin():
    # İnceleme bulgusu: eski sürüm 200'de kırpıyor, exp(−800) sıfır.
    np.testing.assert_array_equal(
        poisson_ters_cdf(np.full(4, 0.5), np.array([150.0, 250.0, 800.0, 1062.0])),
        [150, 250, 800, 1062],
    )
    rng = np.random.default_rng(5)
    u = rng.random(200_000)
    for lam in (250.0, 1000.0):
        k = poisson_ters_cdf(u, np.full(u.size, lam))
        assert abs(k.mean() - lam) < 0.01 * lam, (lam, k.mean())
        assert abs(k.var() - lam) < 0.05 * lam, (lam, k.var())
    # λ'da monoton, eşiğin (150) iki yanında da
    lam = rng.uniform(100.0, 1200.0, u.size)
    assert (poisson_ters_cdf(u, lam * 1.05) >= poisson_ters_cdf(u, lam)).all()
    kk = poisson_ters_cdf(u[:1000], np.linspace(140.0, 160.0, 1000))
    kk2 = poisson_ters_cdf(u[:1000], np.linspace(140.0, 160.0, 1000) + 0.5)
    assert (kk2 >= kk).all()


def test_binom_p_bir_olamaz():
    import pytest

    with pytest.raises(AssertionError):
        binom_ters_cdf(np.array([0.5]), np.array([3]), 1.0)
