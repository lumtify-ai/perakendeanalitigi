"""v4 hız ölçümü: iskelet operasyonların gerçek ölçekte süresini ve tepe
belleğini ölçer. Görev 1 kapısı: iskelet ≤ 4 dk ise devam.

Henüz gerçek dünya/talep modülleri yok (sonraki görevler kuracak); burada
motorun günlük döngüsünde tekrarlanacak vektörel iş yükünün sentetik bir
benzeri kurulur: gün başına λ hesaplama (3 dizi çarpımı), sayaç
üreticiyle 4×`random(C)` çekilişi, Poisson ters CDF, `np.minimum` (stok
kırpma), 3.500 grupta `np.bincount` ile ikame payı ve int16 geçmiş
yazımı. C=260.000 hücre, D=1.277 gün (spec penceresi + ısınma + uzatma
mertebesinde sentetik büyüklükler).
"""

import time
import tracemalloc

import numpy as np

from perakende_veri.v4.rastgele import poisson_ters_cdf, sayac_uretici

C = 260_000
D = 1_277
GRUP_SAYISI = 3_500


def calistir() -> tuple[float, int]:
    """Sentetik günlük döngüyü koşar, (süre_sn, tepe_bellek_byte) döner."""
    rng_dunya = np.random.default_rng(2026)
    statik = rng_dunya.uniform(0.1, 5.0, C)
    g_carpan_a = rng_dunya.uniform(0.5, 1.5, C)
    g_carpan_b = rng_dunya.uniform(0.5, 1.5, C)
    gruplar = rng_dunya.integers(0, GRUP_SAYISI, C)
    stok = rng_dunya.integers(0, 50, C).astype(np.int64)

    gecmis = np.zeros((D, C), dtype=np.int16)

    tracemalloc.start()
    baslangic = time.perf_counter()

    for d in range(D):
        lam = statik * g_carpan_a * g_carpan_b

        u_talep = sayac_uretici(d, "talep").random(C)
        u_iade = sayac_uretici(d, "iade").random(C)
        u_indirim = sayac_uretici(d, "indirim").random(C)
        u_ikame = sayac_uretici(d, "ikame").random(C)

        talep = poisson_ters_cdf(u_talep, lam)
        satis = np.minimum(talep, stok)

        # 3.500 grupta (option/tedarikçi mertebesi) ikame payı: bincount
        # ile grup toplamı, sonra hücreye geri yayılır.
        grup_toplami = np.bincount(gruplar, weights=satis, minlength=GRUP_SAYISI)
        ikame_payi = grup_toplami[gruplar]

        # iade ve indirim akışları da motorun günlük sabit çekiliş
        # sayısını taklit etmek için tüketilir (sonuç geçmişe etkimez).
        _ = (u_iade > 0.9).sum()
        _ = (u_indirim > 0.8).sum() + ikame_payi.sum() + (u_ikame > 0.99).sum()

        gecmis[d] = satis.astype(np.int16)

    sure = time.perf_counter() - baslangic
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return sure, tepe


def main() -> None:
    sure, tepe = calistir()
    print(f"süre: {sure:.1f} sn")
    print(f"tepe bellek: {tepe / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
