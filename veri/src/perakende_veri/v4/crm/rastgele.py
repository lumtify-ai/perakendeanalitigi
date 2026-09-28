"""B'nin sayaç üreteci (A'nın `v4.rastgele.sayac_uretici` kalıbı).

`SeedSequence(tohum, spawn_key=(AMACLAR[amac], d))`: gün ve amaç sabitken
üreteç, önceki günlerde ya da başka amaçlarda ne kadar tüketildiğinden
bağımsızdır. Tohum varsayılanı `CRM_TOHUM`; A'nın akışlarıyla (tohum 2026)
karışmaz.
"""

import numpy as np

from .sabitler import CRM_TOHUM

AMACLAR: dict[str, int] = {
    "katilis": 1,
    "ziyaret": 2,
    "atama": 3,
    "iade": 4,
    "kart": 5,
    "terk": 6,
    "online": 7,
    "yorum": 8,
    "kargo": 9,
    "ltv": 10,
}


def crm_uretici(d: int, amac: str, tohum: int = CRM_TOHUM) -> np.random.Generator:
    """d günü, `amac` çekilişi için B'nin sayaç üreteci."""
    return np.random.default_rng(np.random.SeedSequence(tohum, spawn_key=(AMACLAR[amac], int(d))))


def crm_alt_ureticiler(d: int, amac: str, adimlar: tuple[str, ...],
                       tohum: int = CRM_TOHUM) -> dict[str, np.random.Generator]:
    """(d, amac) akışının adım başına alt akışları: `SeedSequence(tohum,
    spawn_key=(amac, d, i))`, i = adımın `adimlar` içindeki sırası. Bir
    adımın çekiliş sayısı değişince (kalibrasyon) diğer adımların akışı
    kaymaz. Yeni adım listenin SONUNA eklenmelidir."""
    return {
        ad: np.random.default_rng(np.random.SeedSequence(tohum, spawn_key=(AMACLAR[amac], int(d), i)))
        for i, ad in enumerate(adimlar)
    }
