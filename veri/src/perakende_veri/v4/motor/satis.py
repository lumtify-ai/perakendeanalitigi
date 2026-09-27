"""Günün fiyatı, talep çekimi, satış, iade (hücre vektörel, saf fonksiyonlar).

Rastgelelik (global kısıt): her gün her amaç (`talep`, `indirim`, `iade`)
kendi sayaç üretecinden tam olarak bir `random(C)` çeker — satış olsun
olmasın, politika ne yaparsa yapsın. Bir hücrenin talebi yalnız
(u_talep[d, c], λ, fiyat oranı), işlem indirimi yalnız (u_indirim[d, c]),
iadesi yalnız (u_iade[d, c], gecikmeli satış) ile belirlenir.

Talep (spec §5.2): `oran_talep = max(markdown, kampanya)`; `λ = gerçek
λ(d) × (1 − oran_talep)^(−ε)`; `talep = PoissonTersCDF(u_talep, λ)`. Aynı
tekdüze sayı farklı fiyatta monoton olarak farklı talep verir; iki
markdown politikası aynı müşteri akışını görür. İşlem indirimi (tam
fiyatlı satışta rastgele, v3) yalnız satış sonrası fiyat indirimidir,
λ'ya girmez.
"""

import numpy as np

from .. import sabitler
from ..kampanya import fiyat_carpani, gunun_fiyati
from ..rastgele import binom_ters_cdf, poisson_ters_cdf, sayac_uretici

HAT_NORMAL, HAT_OUTLET, HAT_ONLINE = 0, 1, 2


def hat_indisi(magazalar, hucre_magaza: np.ndarray) -> np.ndarray:
    """[C] hücrenin fiyat hattı: 0 normal, 1 outlet mağazası, 2 online."""
    tip = magazalar["tip"].to_numpy()
    hat_m = np.where(tip == "Online", HAT_ONLINE, np.where(tip == "Outlet", HAT_OUTLET, HAT_NORMAL))
    return hat_m[hucre_magaza].astype(np.intp)


def tekduzeler(d: int, C: int, dunya_tohumu: int, operasyon_tohumu: int) -> dict[str, np.ndarray]:
    """Günün üç tekdüze dizisi, sabit sırayla ve her gün tam birer kez.
    Talep dünyanın tohumuyla (müşteri akışı dünyaya aittir), indirim ve
    iade operasyon tohumuyla çekilir."""
    return {
        "talep": sayac_uretici(d, "talep", dunya_tohumu).random(C),
        "indirim": sayac_uretici(d, "indirim", operasyon_tohumu).random(C),
        "iade": sayac_uretici(d, "iade", operasyon_tohumu).random(C),
    }


def talep_cek(u: np.ndarray, lam: np.ndarray, oran_talep: np.ndarray, eps: np.ndarray) -> np.ndarray:
    """[C] günlük talep: PoissonTersCDF(u, λ × fiyat çarpanı).

    Hız: F(0) = exp(−λ) ≥ u olan hücrelerin talebi 0'dır; ters CDF yalnız
    geri kalanlar için çalışır (sonuç birebir aynı)."""
    lam = np.asarray(lam, dtype=float)
    indirimli = oran_talep > 0
    if indirimli.any():
        lam = lam.copy()
        lam[indirimli] *= fiyat_carpani(oran_talep[indirimli], eps[indirimli])
    talep = np.zeros(len(u), dtype=np.int64)
    aday = np.flatnonzero(u > np.exp(-lam))
    if aday.size:
        talep[aday] = poisson_ters_cdf(u[aday], lam[aday])
    return talep


def gunun_birim_fiyati(liste: np.ndarray, md: np.ndarray, kamp: np.ndarray, u_indirim: np.ndarray):
    """(birim [C], uygulanan oran [C]): `kampanya.gunun_fiyati`; işlem
    indirimi u_indirim < ISLEM_INDIRIM_OLASILIGI ve oran 0 iken."""
    return gunun_fiyati(liste, md, kamp, u_indirim < sabitler.ISLEM_INDIRIM_OLASILIGI)


def satis_yap(talep: np.ndarray, stok: np.ndarray, depo: np.ndarray, onl: np.ndarray, hucre_sku: np.ndarray) -> np.ndarray:
    """[C] satılan: fiziksel hücre rafından `min(talep, stok)`; ONL hücresi
    depodan `min(talep, depo[sku])` (ONL'de SKU başına tek hücre)."""
    kullanilabilir = np.where(onl, depo[hucre_sku], stok)
    return np.minimum(talep, kullanilabilir)


def iade_cek(u: np.ndarray, n: np.ndarray, p: np.ndarray) -> np.ndarray:
    """[C] iade adedi: Binomial(n, p)'nin ters CDF'i (yalnız n > 0)."""
    iade = np.zeros(len(n), dtype=np.int64)
    aday = np.flatnonzero(n > 0)
    if aday.size:
        iade[aday] = binom_ters_cdf(u[aday], n[aday], p[aday])
    return iade
