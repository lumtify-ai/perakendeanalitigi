import numpy as np
import pandas as pd

from .parametreler import Parametreler


def agirliklandir(adaylar: pd.DataFrame, p: Parametreler, deger: str = "ciro") -> pd.DataFrame:
    """Aday başına net değer `w` (spec §4, §3.6).

    deger  "ciro": adet başına değer = fiyat
           "kar":  adet başına değer = fiyat − alis
    Taşıma maliyeti iki durumda da aynıdır (adet × adet_maliyeti_tl)."""
    if deger == "ciro":
        birim = adaylar.fiyat
    elif deger == "kar":
        birim = adaylar.fiyat - adaylar.alis
    else:
        raise ValueError(f"deger 'ciro' ya da 'kar' olmalı, verilen: {deger!r}")
    df = adaylar.copy()
    H = p.ufuk_hafta
    df["kazanc"] = np.minimum(df.adet, df.hiz_alici * H) * birim
    df["kayip"] = np.minimum(df.adet, df.hiz_verici * H) * birim
    df["tasima"] = p.adet_maliyeti_tl * df.adet
    df["w"] = df.kazanc - df.kayip - df.tasima
    return df
