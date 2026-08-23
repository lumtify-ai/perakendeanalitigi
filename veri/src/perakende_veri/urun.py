"""Ürün master'ı.

Moda perakendesinde ürün hiyerarşisi yalnızca bir sınıflandırma değil,
kararın kendisidir: transfer, ikmal ve sevkiyat algoritmalarının hepsi
kapsamını bu ağaç üzerinden tanımlar. Tablo bu yüzden bilinçli olarak
geniş ve düz tutulur; normalize edilmez.

    cinsiyet > üst kategori > alt kategori > line > model > option > SKU

Üç kimlik düzeyi vardır ve karıştırılmamalıdır:

    model   MDL001            ürün kodu + adı; fiyat bu düzeyde belirlenir
    option  MDL001-SYH        model × renk; Blok Transfer'in karar birimi
    SKU     MDL001-SYH-M      option × beden; en alt stok birimi

Beden tek bir ölçek değildir: üst giyim harfle, alt giyim numarayla
gider, kadın ve erkek numaraları ayrıdır. Bu yüzden her ürün bir **beden
setine** aittir ve analiz beden etiketine değil setteki sıraya bakar.
"""

import numpy as np
import pandas as pd

from . import sabitler

# Alt kategori başına taban alış fiyatı (TL)
TABAN_FIYAT = {
    "Tişört": 120, "Gömlek": 260, "Kazak": 340, "Sweatshirt": 300,
    "Pantolon": 380, "Jean": 420, "Etek": 290, "Şort": 190,
    "Mont": 900, "Ceket": 720, "Trençkot": 850,
}

# Line ürünün ticari rolüdür ve fiyat konumlandırmasını da etkiler
LINE_FIYAT_CARPANI = {"Basic": 0.85, "Collection": 1.15, "NOS": 0.90, "Outlet": 0.70}

# Etek yalnızca kadın kategorisinde bulunur
YALNIZ_KADIN = {"Etek"}


def _cinsiyet_sec(rng: np.random.Generator, alt_kategori: str) -> str:
    if alt_kategori in YALNIZ_KADIN:
        return "Kadın"
    return str(rng.choice(sabitler.CINSIYETLER, p=sabitler.CINSIYET_PAYLARI))


def _modelleri_uret(rng: np.random.Generator) -> list[dict]:
    """Model düzeyindeki tasarım kararlarını üretir."""
    alt_kategoriler = [
        (ust, alt)
        for ust, altlar in sabitler.KATEGORILER.items()
        for alt in altlar
    ]

    modeller = []
    for sira in range(1, sabitler.MODEL_SAYISI + 1):
        ust_kategori, alt_kategori = alt_kategoriler[rng.integers(len(alt_kategoriler))]
        cinsiyet = _cinsiyet_sec(rng, alt_kategori)
        line = str(rng.choice(sabitler.LINELER, p=sabitler.LINE_PAYLARI))
        kesim = str(rng.choice(sabitler.KESIMLER[alt_kategori]))

        alis = (
            TABAN_FIYAT[alt_kategori]
            * LINE_FIYAT_CARPANI[line]
            * float(rng.uniform(0.9, 1.1))
        )
        beden_seti, bedenler = sabitler.BEDEN_SETLERI[(cinsiyet, ust_kategori)]

        modeller.append(
            {
                "model_kodu": f"MDL{sira:03d}",
                "model_adi": f"{kesim} {alt_kategori}",
                "cinsiyet": cinsiyet,
                "ust_kategori": ust_kategori,
                "alt_kategori": alt_kategori,
                "line": line,
                "uretici": str(rng.choice(sabitler.URETICILER)),
                "beden_seti": beden_seti,
                "bedenler": bedenler,
                "alis_fiyati": round(alis, 2),
                "liste_fiyati": round(alis * 2.6, 2),
            }
        )
    return modeller


def urunleri_uret(rng: np.random.Generator) -> pd.DataFrame:
    """Model × renk × beden kırılımında SKU master'ı üretir."""
    satirlar = []

    for model in _modelleri_uret(rng):
        for renk, renk_kodu in sabitler.RENKLER.items():
            option_id = f"{model['model_kodu']}-{renk_kodu}"
            for sira, beden in enumerate(model["bedenler"], start=1):
                satirlar.append(
                    {
                        "urun_id": f"{option_id}-{beden}",
                        "option_id": option_id,
                        "model_kodu": model["model_kodu"],
                        "model_adi": model["model_adi"],
                        "ad": (
                            f"{model['cinsiyet']} {model['line']} "
                            f"{model['model_adi']} {renk} {beden}"
                        ),
                        "marka": sabitler.MARKA,
                        "cinsiyet": model["cinsiyet"],
                        "ust_kategori": model["ust_kategori"],
                        "alt_kategori": model["alt_kategori"],
                        "line": model["line"],
                        "uretici": model["uretici"],
                        "renk": renk,
                        "renk_kodu": renk_kodu,
                        "beden_seti": model["beden_seti"],
                        "beden": beden,
                        "beden_sira": sira,
                        "alis_fiyati": model["alis_fiyati"],
                        "liste_fiyati": model["liste_fiyati"],
                    }
                )

    return pd.DataFrame(satirlar)
