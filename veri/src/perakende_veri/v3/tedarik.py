"""Tedarik: tedarikçiler, tedarik süreleri, MOQ, teslim sapması.

v2'de üretici bir etiketti; hiçbir şeyi belirlemiyordu. v3'te tedarikçi
kararın kısıtıdır: ilk siparişin ne kadar önce verileceğini, RPT'nin kaç
haftada geleceğini ve en az kaç adet sipariş verilebileceğini o belirler.
"""

import math

import numpy as np
import pandas as pd

from . import sabitler


def tedarikcileri_uret(rng: np.random.Generator) -> pd.DataFrame:
    """8 tedarikçi: 5 yerli (v2'nin üretici adları), 3 Uzak Doğu (kurgusal).

    Süreler aralık içinden tedarikçi başına bir kez çekilir; tedarikçinin
    kendi sabit süresidir. Gerçekleşen teslim bunun etrafında sapar.
    """
    tanimlar = [(ad, "Türkiye", "Yerli") for ad in sabitler.YERLI_TEDARIKCILER] + [
        (ad, ulke, "Uzak Doğu") for ad, ulke in sabitler.UZAK_DOGU_TEDARIKCILER
    ]
    satirlar = []
    for sira, (ad, ulke, mense) in enumerate(tanimlar, start=1):
        m = sabitler.MENSE[mense]
        satirlar.append(
            {
                "tedarikci_id": f"T{sira:02d}",
                "ad": ad,
                "ulke": ulke,
                "mense": mense,
                "ilk_siparis_hafta": int(rng.integers(m["ilk"][0], m["ilk"][1] + 1)),
                "rpt_hafta": int(rng.integers(m["rpt"][0], m["rpt"][1] + 1)),
                "moq_option": m["moq"],
            }
        )
    return pd.DataFrame(satirlar)


def tedarikci_sec(
    rng: np.random.Generator, alt_kategori: str, tedarikciler: pd.DataFrame
) -> str:
    """Alt kategoriye göre menşe, menşe içinde eşit olasılıkla tedarikçi."""
    uzak = rng.random() < sabitler.UZAK_DOGU_OLASILIGI[alt_kategori]
    havuz = tedarikciler.loc[
        tedarikciler["mense"] == ("Uzak Doğu" if uzak else "Yerli"), "tedarikci_id"
    ].to_numpy()
    return str(havuz[rng.integers(len(havuz))])


def teslim_sapmasi(rng: np.random.Generator, mense: str, boyut) -> np.ndarray:
    """Gerçekleşen − planlanan teslim (gün).

    Yerli: −3…+3 eşit olasılıklı. Uzak Doğu: 0…+21, sağa çarpık (beta):
    gemi erken gelmez, çoğu zaman birkaç gün, bazen üç hafta gecikir.
    """
    if mense == "Yerli":
        return rng.integers(
            -sabitler.YERLI_SAPMA_GUN, sabitler.YERLI_SAPMA_GUN + 1, size=boyut
        )
    a, b = sabitler.UZAK_DOGU_SAPMA_BETA
    return np.rint(sabitler.UZAK_DOGU_SAPMA_GUN * rng.beta(a, b, size=boyut)).astype(
        np.int64
    )


def moq_yuvarla(miktar: float, moq: int) -> int:
    """Sipariş miktarı: en az MOQ, üstü 10'un katına yukarı yuvarlanır.

    "MOQ'ya yuvarlama" MOQ'nun katına yuvarlama değildir: MOQ bir alt
    sınırdır. 700 adetlik ihtiyaç 1.200'e değil 700'e gider.
    """
    y = sabitler.YUVARLAMA_ADET
    return int(max(moq, math.ceil(miktar / y - 1e-9) * y))


def en_buyuk_kalan(toplam: int, paylar: np.ndarray) -> np.ndarray:
    """`toplam` adedi paylara göre tam sayılara böler (en büyük kalan).

    Eşitlikte önce gelen indis kazanır; sonuç deterministiktir.
    """
    paylar = np.asarray(paylar, dtype=float)
    if toplam <= 0 or paylar.sum() <= 0:
        return np.zeros(len(paylar), dtype=np.int64)
    hedef = toplam * paylar / paylar.sum()
    tam = np.floor(hedef).astype(np.int64)
    kalan = int(toplam - tam.sum())
    if kalan > 0:
        sira = np.lexsort((np.arange(len(paylar)), -(hedef - tam)))
        tam[sira[:kalan]] += 1
    return tam
