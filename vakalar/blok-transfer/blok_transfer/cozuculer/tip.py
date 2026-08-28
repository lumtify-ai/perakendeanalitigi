from dataclasses import dataclass

import pandas as pd

HAREKET_KOLONLARI = ["verici", "alici", "option_id", "adet", "w"]


@dataclass
class Plan:
    hareketler: pd.DataFrame       # HAREKET_KOLONLARI
    durum: str                     # 'optimal' | 'limit' | 'hata'
    sure_sn: float
    sayaclar: dict[str, int] | None = None   # yalnız greedy doldurur; rapor.py okur


def bos_hareketler() -> pd.DataFrame:
    return pd.DataFrame(columns=HAREKET_KOLONLARI)
