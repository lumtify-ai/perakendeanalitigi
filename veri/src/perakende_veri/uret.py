"""Veri setini uçtan uca üretir: python -m perakende_veri.uret"""

import sys

import numpy as np

from . import sabitler
from .disa_aktar import yaz
from .magaza import magazalari_uret
from .simulasyon import simule_et
from .takvim import takvim_uret
from .urun import urunleri_uret


def tablolari_uret() -> dict:
    """Yedi tabloyu tek bir tohumdan üretir.

    Tohum tek bir yerde kurulur ve modüller onu sırayla tüketir; sıra
    değişirse veri de değişir. Tekrar üretilebilirlik buna bağlıdır.
    """
    rng = np.random.default_rng(sabitler.TOHUM)

    magazalar = magazalari_uret(rng)
    urunler = urunleri_uret(rng)
    takvim = takvim_uret()
    hareketler = simule_et(rng, magazalar, urunler, takvim)

    return {
        "magaza": magazalar,
        "urun": urunler,
        "takvim": takvim,
        **hareketler,
    }


def main() -> None:
    # Windows konsolu cp1252; Türkçe tablo adları olmasa da güvenceye alalım
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tablolar = tablolari_uret()
    yaz(tablolar, sabitler.CIKTI_DIZINI)

    for ad, df in tablolar.items():
        print(f"{ad:12s} {len(df):>10,} satır")
    print(f"\nÇıktı: {sabitler.CIKTI_DIZINI}")


if __name__ == "__main__":
    main()
