import numpy as np
import pandas as pd

from .parametreler import Parametreler


def agirliklandir(adaylar: pd.DataFrame, p: Parametreler) -> pd.DataFrame:
    df = adaylar.copy()
    H = p.ufuk_hafta
    df["kazanc"] = np.minimum(df.adet, df.hiz_alici * H) * df.fiyat
    df["kayip"] = np.minimum(df.adet, df.hiz_verici * H) * df.fiyat
    df["tasima"] = p.adet_maliyeti_tl * df.adet
    df["w"] = df.kazanc - df.kayip - df.tasima
    return df
