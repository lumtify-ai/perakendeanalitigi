"""v4 rastgelelik çekirdeği: akışlar, sayaç üreteci, Poisson/Binom ters CDF.

Rastgelelik iki türden gelir (bkz. global kısıtlar):

    dunya   `default_rng(TOHUM)`                         tek akış, dünya kurulumu
    sayaç   `SeedSequence(TOHUM, spawn_key=(AMAC, d))`    gün + amaç başına ayrı üreteç

Sayaç tabanlı akışların temel özelliği: d günü ve amaç sabitken üretecin
verdiği sayılar önceki günlerde ne kadar tüketildiğinden bağımsızdır (başka
bir günün akışını ne kadar tüketirseniz tüketin, bu günün akışı değişmez).
Hiçbir çekiliş politikaya bağlı sayıda tüketilmez: motor her gün her amaç
için sabit sayıda çekiliş yapar.

Ters CDF örneklemesi tek tip tekdüze sayıdan (`u`) tamsayı dağılım değeri
üretir; Poisson ve Binom için kapalı biçim yoktur, kümülatif olasılık
yinelemeli çarpımla (pmf zinciri) hesaplanır. Vektöreldir: `u`, `lam`/`n`/`p`
dizi olabilir; döngü yalnız k (sayım) üzerindedir, hücre başına değil.
"""

import numpy as np

from .sabitler import TOHUM

# Amaç anahtarları: SeedSequence spawn_key'in ilk bileşeni. Gün (d) ikinci
# bileşendir. Aynı (amac, d) çifti her zaman aynı üreteci verir.
AMACLAR: dict[str, int] = {
    "talep": 1,
    "iade": 2,
    "indirim": 3,
    "ikame": 4,
    "beden_ikame": 5,
    "elle": 6,
    "kalite": 7,
}

# Poisson ters CDF'te kayan nokta kuyruğu hiç kapanmayabilir (pmf, cdf'yi
# 1.0'a makine hassasiyetinde yaklaştırıp sıfıra yuvarlanabilir); bu sınırdan
# sonra kalan hücreler o ana kadarki k değerinde bırakılır.
POISSON_MAKS_YINELEME = 200


def sayac_uretici(d: int, amac: str, tohum: int = TOHUM) -> np.random.Generator:
    """d günü, `amac` çekilişi için sayaç üreteci.

    `SeedSequence(tohum, spawn_key=(AMACLAR[amac], d))`: gün ve amaç
    sabitken üreteç önceki günlerde veya başka amaçlarda ne kadar
    tüketildiğinden bağımsızdır.
    """
    return np.random.default_rng(
        np.random.SeedSequence(tohum, spawn_key=(AMACLAR[amac], d))
    )


def sayac_uretici_option(d: int, amac: str, o: int, tohum: int = TOHUM) -> np.random.Generator:
    """d günü, o option'ı, `amac` çekilişi için sayaç üreteci.

    `SeedSequence(tohum, spawn_key=(AMACLAR[amac], d, o))`: bir option'ın
    çekilişi, aynı gün başka option'lar için kaç üreteç açıldığından (ör.
    bir politikanın kaç sipariş verdiğinden) bağımsızdır. Motor RPT ve
    sürekli teslimlerin kalite kontrolünü bununla çeker ("kalite").
    """
    return np.random.default_rng(
        np.random.SeedSequence(tohum, spawn_key=(AMACLAR[amac], d, o))
    )


def dunya_akisi(tohum: int = TOHUM) -> np.random.Generator:
    """Dünya kurulumu için tek akış: `default_rng(tohum)`."""
    return np.random.default_rng(tohum)


def poisson_ters_cdf(u: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """Poisson(lam)'ın ters dağılım fonksiyonu: en küçük k, F(k) ≥ u.

    Hücre başına kendi tekdüze sayısıyla çekilir. pmf(0) = exp(-lam) ile
    başlar, her adımda pmf *= lam / (k+1) ile bir sonraki terime geçilir;
    u, kümülatif olasılığı aşan hücrelerde k bir artar. Tek hücre için
    döngü yok: döngü yalnız k üzerinde, bütün hücreler vektörel işlenir.
    """
    u = np.asarray(u, dtype=float)
    lam = np.asarray(lam, dtype=float)
    lam = np.broadcast_to(lam, u.shape).astype(float)
    k = np.zeros(u.shape, dtype=np.int64)
    pmf = np.exp(-lam)
    cdf = pmf.copy()
    for j in range(POISSON_MAKS_YINELEME):
        asan = u > cdf
        if not asan.any():
            break
        k += asan
        pmf = pmf * lam / (j + 1)
        cdf = cdf + pmf
    return k


def binom_ters_cdf(u: np.ndarray, n: np.ndarray, p: float | np.ndarray) -> np.ndarray:
    """Binomial(n, p)'nin ters dağılım fonksiyonu: en küçük k, F(k) ≥ u.

    v3'ün algoritmasıyla aynıdır (bkz. `perakende_veri.v3.dunya.binom_ters_cdf`);
    burada `p` de dizi olabilir (hücre başına farklı olasılık). Kesin
    (olasılıklar yinelemeli çarpımla), bağımlılık yok; n küçük olduğu için
    döngü kısa. Sonuç [0, n] aralığına kırpılır (yuvarlama F(n)'yi 1'in
    hemen altında bırakabilir).
    """
    n = np.asarray(n, dtype=np.int64)
    u = np.asarray(u, dtype=float)
    p = np.broadcast_to(np.asarray(p, dtype=float), n.shape).astype(float)
    k = np.zeros(n.shape, dtype=np.int64)
    if n.size == 0 or n.max() <= 0:
        return k
    pmf = (1.0 - p) ** n
    cdf = pmf.copy()
    oran = p / (1.0 - p)
    for j in range(int(n.max())):
        asan = u > cdf
        if not asan.any():
            break
        k += asan
        pmf = pmf * np.maximum(n - j, 0) / (j + 1) * oran
        cdf = cdf + pmf
    return np.minimum(k, n)
