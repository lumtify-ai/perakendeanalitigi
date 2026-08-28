import time

import pandas as pd

from ..cekirdek.parametreler import Parametreler
from .tip import HAREKET_KOLONLARI, Plan, bos_hareketler


def cozumle(adaylar: pd.DataFrame, kapasite: dict[str, int], p: Parametreler) -> Plan:
    """Skor sıralı açgözlü atama. Rota sabit maliyetini modelleyemez;
    min_koli'yi kaba bir rota post-filtresiyle uygular (spec §5)."""
    baslangic = time.perf_counter()
    kalan = dict(kapasite)
    verilen: set[tuple[str, str]] = set()
    secilen: list[dict] = []
    sayac = {"pozitif": 0, "blok": 0, "kapasite": 0, "secilen": 0}

    sirali = adaylar.sort_values(
        by=["w", "verici", "alici", "option_id"],
        ascending=[False, True, True, True],
    )
    for satir in sirali.itertuples(index=False):
        if satir.w <= 0:
            break                                   # kalanların hepsi daha kötü
        sayac["pozitif"] += 1
        if (satir.verici, satir.option_id) in verilen:
            sayac["blok"] += 1
            continue                                # blok tek hedefe
        if kalan.get(satir.alici, 0) < satir.adet:
            sayac["kapasite"] += 1
            continue                                # alıcı kapasitesi
        verilen.add((satir.verici, satir.option_id))
        kalan[satir.alici] -= satir.adet
        sayac["secilen"] += 1
        secilen.append({k: getattr(satir, k) for k in HAREKET_KOLONLARI})

    df = pd.DataFrame(secilen, columns=HAREKET_KOLONLARI) if secilen else bos_hareketler()
    if len(df):
        rota_adet = df.groupby(["verici", "alici"]).adet.transform("sum")
        df = df[rota_adet >= p.min_koli].reset_index(drop=True)
    sayac["min_koli_kesilen"] = sayac["secilen"] - len(df)
    return Plan(
        hareketler=df,
        durum="optimal",
        sure_sn=time.perf_counter() - baslangic,
        sayaclar=sayac,
    )
