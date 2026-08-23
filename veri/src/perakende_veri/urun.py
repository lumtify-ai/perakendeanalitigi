import numpy as np
import pandas as pd

from . import sabitler

KOLEKSIYONLAR = ["2025-İlkbahar/Yaz", "2025-Sonbahar/Kış"]

# Alt kategori başına taban alış fiyatı (TL)
TABAN_FIYAT = {
    "Tişört": 120, "Gömlek": 260, "Kazak": 340, "Sweatshirt": 300,
    "Pantolon": 380, "Jean": 420, "Etek": 290, "Şort": 190,
    "Mont": 900, "Ceket": 720, "Trençkot": 850,
}


def urunleri_uret(rng: np.random.Generator) -> pd.DataFrame:
    """Model × renk × beden kırılımında SKU listesi üretir.

    Fiyat model düzeyinde belirlenir; beden ve renk fiyatı değiştirmez.
    """
    alt_kategoriler = [
        (kategori, alt)
        for kategori, altlar in sabitler.KATEGORILER.items()
        for alt in altlar
    ]

    modeller = []
    for i in range(1, sabitler.MODEL_SAYISI + 1):
        kategori, alt = alt_kategoriler[rng.integers(len(alt_kategoriler))]
        alis = TABAN_FIYAT[alt] * float(rng.uniform(0.85, 1.15))
        modeller.append(
            {
                "model_kodu": f"MDL{i:03d}",
                "kategori": kategori,
                "alt_kategori": alt,
                "koleksiyon": KOLEKSIYONLAR[int(rng.integers(2))],
                "alis_fiyati": round(alis, 2),
                "liste_fiyati": round(alis * 2.6, 2),
            }
        )

    satirlar = []
    sayac = 0
    for model in modeller:
        for renk in sabitler.RENKLER:
            for beden in sabitler.BEDENLER:
                sayac += 1
                satirlar.append(
                    {
                        "urun_id": f"U{sayac:04d}",
                        "model_kodu": model["model_kodu"],
                        "ad": f"{model['alt_kategori']} {model['model_kodu']} {renk}",
                        "kategori": model["kategori"],
                        "alt_kategori": model["alt_kategori"],
                        "marka": sabitler.MARKA,
                        "koleksiyon": model["koleksiyon"],
                        "beden": beden,
                        "renk": renk,
                        "alis_fiyati": model["alis_fiyati"],
                        "liste_fiyati": model["liste_fiyati"],
                    }
                )

    return pd.DataFrame(satirlar)
