"""Ürün master'ı.

Moda perakendesinde ürün hiyerarşisi yalnızca bir sınıflandırma değil,
kararın kendisidir: transfer, ikmal ve sevkiyat algoritmalarının hepsi
kapsamını bu ağaç üzerinden tanımlar. Bu yüzden tablo bilinçli olarak
geniş ve düz tutulur (klasik bir DimProduct gibi), normalize edilmez.

Üç kimlik düzeyi vardır ve karıştırılmamalıdır:

    model   → tasarım (MDL001)              — fiyat bu düzeyde belirlenir
    option  → model × renk (OPT0001)        — Blok Transfer'in karar birimi
    SKU     → option × beden (U0001)        — en alt stok birimi
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

# Etek yalnızca kadın, diğerlerinde kısıt yok
YALNIZ_KADIN = {"Etek"}


def _cinsiyet_sec(rng: np.random.Generator, alt_kategori: str) -> str:
    if alt_kategori in YALNIZ_KADIN:
        return "Kadın"
    return str(rng.choice(sabitler.CINSIYETLER, p=sabitler.CINSIYET_PAYLARI))


def _modelleri_uret(rng: np.random.Generator) -> list[dict]:
    """Model düzeyindeki tasarım kararlarını üretir."""
    alt_kategoriler = [
        (ana, alt)
        for ana, altlar in sabitler.KATEGORILER.items()
        for alt in altlar
    ]
    sezon_kodlari = list(sabitler.SEZON_GRUPLARI)

    modeller = []
    for i in range(1, sabitler.MODEL_SAYISI + 1):
        ana_kategori, alt_kategori = alt_kategoriler[rng.integers(len(alt_kategoriler))]
        line = str(rng.choice(sabitler.LINELER))
        devamli = rng.random() < sabitler.LINE_DEVAMLI_OLASILIGI[line]
        sezon_grup = sezon_kodlari[int(rng.integers(len(sezon_kodlari)))]
        alis = TABAN_FIYAT[alt_kategori] * float(rng.uniform(0.85, 1.15))

        modeller.append(
            {
                "model_kodu": f"MDL{i:03d}",
                "cinsiyet": _cinsiyet_sec(rng, alt_kategori),
                "ana_kategori": ana_kategori,
                "alt_kategori": alt_kategori,
                "line": line,
                "mevsimsellik": "Devamlı" if devamli else "Sezonluk",
                "uretici": str(rng.choice(sabitler.URETICILER)),
                "sezon_grup": sezon_grup,
                "koleksiyon": sabitler.SEZON_GRUPLARI[sezon_grup],
                "alis_fiyati": round(alis, 2),
                "liste_fiyati": round(alis * 2.6, 2),
            }
        )
    return modeller


def urunleri_uret(rng: np.random.Generator) -> pd.DataFrame:
    """Model × renk × beden kırılımında SKU master'ı üretir.

    Fiyat model düzeyinde belirlenir; beden ve renk fiyatı değiştirmez.
    """
    beden_sirasi = {beden: i for i, beden in enumerate(sabitler.BEDENLER, start=1)}

    satirlar = []
    sku_sayaci = 0
    option_sayaci = 0

    for model in _modelleri_uret(rng):
        for renk in sabitler.RENKLER:
            option_sayaci += 1
            option_id = f"OPT{option_sayaci:04d}"
            for beden in sabitler.BEDENLER:
                sku_sayaci += 1
                satirlar.append(
                    {
                        "urun_id": f"U{sku_sayaci:04d}",
                        "option_id": option_id,
                        "model_kodu": model["model_kodu"],
                        # Perakendede ürün adı stil kodunu taşır; aynı ad iki farklı
                        # modele düşerse rapor okunamaz hale gelir.
                        "ad": (
                            f"{model['cinsiyet']} {model['alt_kategori']} "
                            f"{model['line']} {renk} ({model['model_kodu']})"
                        ),
                        "marka": sabitler.MARKA,
                        "cinsiyet": model["cinsiyet"],
                        "ana_kategori": model["ana_kategori"],
                        "alt_kategori": model["alt_kategori"],
                        "line": model["line"],
                        "mevsimsellik": model["mevsimsellik"],
                        "uretici": model["uretici"],
                        "sezon_grup": model["sezon_grup"],
                        "koleksiyon": model["koleksiyon"],
                        "renk": renk,
                        "beden": beden,
                        "beden_sira": beden_sirasi[beden],
                        "alis_fiyati": model["alis_fiyati"],
                        "liste_fiyati": model["liste_fiyati"],
                    }
                )

    return pd.DataFrame(satirlar)
