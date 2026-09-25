"""v3 ürün master'ı.

v2'nin hiyerarşisi (model > option > SKU), beden setleri ve fiyat
konumlandırması aynen içe aktarılır. v3'te değişen, ürünün ÖMRÜDÜR:
Collection ve Outlet bir sezonda doğar (dalga tarihi) ve sezonun
çıkışında raftan kalkar; Basic ve NOS pencere boyunca devamlıdır.

Model kodları: MDL001–MDL032 devamlı (22 Basic + 10 NOS), MDL033'ten
itibaren sezonlar sırayla (AW23, SS24, AW24, SS25, AW25), her sezonda
36 Collection + 6 Outlet; sezon içinde dalga 1, 2, 3 sırasıyla.
"""

import numpy as np
import pandas as pd

from .. import sabitler as v2_sabitler
from ..urun import LINE_FIYAT_CARPANI, TABAN_FIYAT, _cinsiyet_sec
from . import sabitler
from .tedarik import tedarikci_sec

_ALT_TO_UST = {
    alt: ust for ust, altlar in v2_sabitler.KATEGORILER.items() for alt in altlar
}


def _alt_kategori_sec(rng: np.random.Generator, agirliklar: dict[str, float]) -> str:
    adlar = list(agirliklar)
    p = np.array([agirliklar[a] for a in adlar], dtype=float)
    return adlar[rng.choice(len(adlar), p=p / p.sum())]


def _model(
    rng: np.random.Generator,
    sira: int,
    line: str,
    agirlik_anahtari: str,
    renk_sayisi: int,
    renk_havuzu: list[str],
    tedarikciler: pd.DataFrame,
    sezon_kodu: str,
    dalga,
    lansman,
    cikis,
) -> dict:
    alt_kategori = _alt_kategori_sec(rng, sabitler.ALT_KATEGORI_AGIRLIK[agirlik_anahtari])
    ust_kategori = _ALT_TO_UST[alt_kategori]
    cinsiyet = _cinsiyet_sec(rng, alt_kategori)
    kesim = str(rng.choice(v2_sabitler.KESIMLER[alt_kategori]))
    alis = TABAN_FIYAT[alt_kategori] * LINE_FIYAT_CARPANI[line] * float(rng.uniform(0.9, 1.1))
    beden_seti, bedenler = v2_sabitler.BEDEN_SETLERI[(cinsiyet, ust_kategori)]
    secilen = rng.choice(len(renk_havuzu), size=renk_sayisi, replace=False)
    renkler = [renk_havuzu[i] for i in sorted(secilen)]
    return {
        "model_kodu": f"MDL{sira:03d}",
        "model_adi": f"{kesim} {alt_kategori}",
        "cinsiyet": cinsiyet,
        "ust_kategori": ust_kategori,
        "alt_kategori": alt_kategori,
        "line": line,
        "beden_seti": beden_seti,
        "bedenler": bedenler,
        "renkler": renkler,
        "alis_fiyati": round(alis, 2),
        "liste_fiyati": round(alis * 2.6, 2),
        "sezon_kodu": sezon_kodu,
        "dalga": dalga,
        "lansman_tarihi": lansman,
        "cikis_tarihi": cikis,
        "tedarikci_id": tedarikci_sec(rng, alt_kategori, tedarikciler),
    }


def modelleri_uret(rng: np.random.Generator, tedarikciler: pd.DataFrame) -> list[dict]:
    """242 modelin tasarım kararları, sabit sırayla (tohum sırası buna bağlı)."""
    tum_renkler = list(sabitler.RENKLER)
    modeller: list[dict] = []
    sira = 1

    for line, adet, renk in (
        ("Basic", sabitler.BASIC_MODEL, sabitler.BASIC_RENK),
        ("NOS", sabitler.NOS_MODEL, sabitler.NOS_RENK),
    ):
        for _ in range(adet):
            modeller.append(
                _model(rng, sira, line, line, renk, sabitler.DEVAMLI_RENK_HAVUZU,
                       tedarikciler, sabitler.DEVAMLI, None, None, None)
            )
            sira += 1

    alt, ust = sabitler.SEZON_RENK_ARALIGI
    for kod, s in sabitler.SEZONLAR.items():
        tip = kod[:2]   # "AW" | "SS"
        cikis = pd.Timestamp(s["cikis"])
        for line, adet in (
            ("Collection", sabitler.SEZON_COLLECTION_MODEL),
            ("Outlet", sabitler.SEZON_OUTLET_MODEL),
        ):
            dalga_basina = adet // sabitler.DALGA_SAYISI
            for i in range(adet):
                dalga = i // dalga_basina + 1
                modeller.append(
                    _model(rng, sira, line, tip, int(rng.integers(alt, ust + 1)),
                           tum_renkler, tedarikciler, kod, dalga,
                           pd.Timestamp(s["dalgalar"][dalga - 1]), cikis)
                )
                sira += 1
    return modeller


def urunleri_uret(rng: np.random.Generator, tedarikciler: pd.DataFrame) -> pd.DataFrame:
    """Model × renk × beden kırılımında SKU master'ı."""
    satirlar = []
    for model in modelleri_uret(rng, tedarikciler):
        for renk in model["renkler"]:
            renk_kodu = sabitler.RENKLER[renk]
            option_id = f"{model['model_kodu']}-{renk_kodu}"
            for beden_sira, beden in enumerate(model["bedenler"], start=1):
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
                        "marka": v2_sabitler.MARKA,
                        "cinsiyet": model["cinsiyet"],
                        "ust_kategori": model["ust_kategori"],
                        "alt_kategori": model["alt_kategori"],
                        "line": model["line"],
                        "renk": renk,
                        "renk_kodu": renk_kodu,
                        "beden_seti": model["beden_seti"],
                        "beden": beden,
                        "beden_sira": beden_sira,
                        "alis_fiyati": model["alis_fiyati"],
                        "liste_fiyati": model["liste_fiyati"],
                        "sezon_kodu": model["sezon_kodu"],
                        "dalga": model["dalga"],
                        "lansman_tarihi": model["lansman_tarihi"],
                        "cikis_tarihi": model["cikis_tarihi"],
                        "tedarikci_id": model["tedarikci_id"],
                    }
                )
    df = pd.DataFrame(satirlar)
    df["dalga"] = df["dalga"].astype("Int64")
    df["lansman_tarihi"] = pd.to_datetime(df["lansman_tarihi"])
    df["cikis_tarihi"] = pd.to_datetime(df["cikis_tarihi"])
    return df
