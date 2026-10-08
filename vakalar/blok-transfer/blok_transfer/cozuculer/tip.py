from dataclasses import dataclass

import pandas as pd

HAREKET_KOLONLARI = ["verici", "alici", "option_id", "adet", "w"]


@dataclass
class Plan:
    hareketler: pd.DataFrame       # HAREKET_KOLONLARI
    # 'optimal'  MIP: CBC `mip_bosluk_orani` toleransı içinde durdu; kanıtlı optimum DEĞİL
    # 'limit'    MIP: düğüm ya da süre sınırında olurlu çözümle durdu (boşluk `sinir`den)
    # 'sezgisel' açgözlü: çözücü optimumluk iddia etmez
    # 'hata'     çözüm yok
    durum: str
    sure_sn: float
    sayaclar: dict[str, int] | None = None   # yalnız greedy doldurur; rapor.py okur
    amac: float | None = None      # Σw − rota sabiti × açık rota; durum 'hata'yken None
    sinir: float | None = None     # MIP: CBC'nin son üst sınırı (TL); greedy ya da okunamazsa None


def bos_hareketler() -> pd.DataFrame:
    return pd.DataFrame(columns=HAREKET_KOLONLARI)
