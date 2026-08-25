import time

import pandas as pd
import pulp

from ..cekirdek.parametreler import Parametreler
from .tip import HAREKET_KOLONLARI, Plan, bos_hareketler


def cozumle(adaylar: pd.DataFrame, kapasite: dict[str, int], p: Parametreler) -> Plan:
    """Spec §6 formülasyonu: x blok kararı, y rota açılışı."""
    baslangic = time.perf_counter()
    if len(adaylar) == 0:
        return Plan(bos_hareketler(), "optimal", time.perf_counter() - baslangic)

    model = pulp.LpProblem("blok_transfer", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in adaylar.index}
    rotalar = sorted(set(zip(adaylar.verici, adaylar.alici)))
    y = {r: pulp.LpVariable(f"y_{r[0]}_{r[1]}", cat="Binary") for r in rotalar}

    model += (
        pulp.lpSum(adaylar.loc[i, "w"] * x[i] for i in adaylar.index)
        - p.rota_sabiti_tl * pulp.lpSum(y.values())
    )

    for (verici, option), grup in adaylar.groupby(["verici", "option_id"]):
        model += pulp.lpSum(x[i] for i in grup.index) <= 1          # blok tek hedefe

    for alici, grup in adaylar.groupby("alici"):
        model += (
            pulp.lpSum(int(adaylar.loc[i, "adet"]) * x[i] for i in grup.index)
            <= kapasite.get(alici, 0)
        )

    for r, grup in adaylar.groupby(["verici", "alici"]):
        for i in grup.index:
            model += x[i] <= y[r]                                    # rota açılmadan taşıma yok
        model += (
            pulp.lpSum(int(adaylar.loc[i, "adet"]) * x[i] for i in grup.index)
            >= p.min_koli * y[r]                                     # açık rota koliyi doldurur
        )

    sonuc = model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=p.mip_zaman_limiti_sn))
    if sonuc == pulp.LpStatusOptimal:
        durum = "optimal"
    elif sonuc == pulp.LpStatusNotSolved:
        durum = "limit"
    else:
        durum = "hata"

    secilen = adaylar.loc[[i for i in adaylar.index if x[i].value() and x[i].value() > 0.5]]
    df = secilen[HAREKET_KOLONLARI].reset_index(drop=True) if len(secilen) else bos_hareketler()
    return Plan(df, durum, time.perf_counter() - baslangic)
