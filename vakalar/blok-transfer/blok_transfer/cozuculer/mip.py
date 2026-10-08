import time

import pandas as pd
import pulp

from ..cekirdek.parametreler import Parametreler
from .tip import HAREKET_KOLONLARI, Plan, bos_hareketler


def kur(
    adaylar: pd.DataFrame, kapasite: dict[str, int], p: Parametreler
) -> tuple[pulp.LpProblem, dict, dict]:
    """Spec §6 formülasyonunu kurar; çözmez.

    Ayrı durmasının sebebi: `rapor.py` değişken/kısıt sayısını ve LP
    boşluğunu bu modelden okur. Formülasyon iki yerde yazılırsa yazıdaki
    sayı ile çözülen model sessizce ayrışır.
    """
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

    return model, x, y


# PuLP'nin `solve()` dönüşü (LpStatus) süre ya da düğüm sınırında olurlu
# çözümle duran CBC için de LpStatusOptimal'dir: "optimal" kanıt demek
# değildir. Kanıtı çözüm durumu (`sol_status`) taşır.
DURUMLAR = {
    pulp.LpSolutionOptimal: "optimal",          # boşluk toleransı içinde (bkz. cozumle)
    pulp.LpSolutionIntegerFeasible: "limit",    # emniyet sınırında durdu, olurlu en iyi çözüm
}


def cozumle(adaylar: pd.DataFrame, kapasite: dict[str, int], p: Parametreler) -> Plan:
    """Spec §6 formülasyonu: x blok kararı, y rota açılışı.

    Sonlanma göreli boşlukla (`gapRel = p.mip_bosluk_orani`): CBC, bulduğu
    çözümün amacı ile kalan ağacın üst sınırı arasındaki fark bu oranın
    altına inince durur. Durumların anlamı:

        "optimal"  CBC boşluk toleransı içinde durdu. Kanıtlı optimum DEĞİL;
                   kanıtlanan, çözümün optimuma en fazla `mip_bosluk_orani`
                   kadar uzak olduğu ("optimuma en fazla %x uzak").
        "limit"    emniyet sınırlarından biri (düğüm ya da süre) boşluğa
                   inmeden durdurdu; olurlu en iyi çözüm, boşluk garantisi yok.
        "hata"     tam sayı çözüm yok; plan boş.

    Seri arama: aynı girdi aynı planı verir. Düğüm limiti ve süre limiti
    yalnız emniyet; düğüm sınırı süreden önce bağlar ki emniyete takılan
    hücre de makinenin hızından bağımsız aynı planı versin.

    `threads=0` bilerek: CBC'de 0 seri dal-sınır demektir; `threads=1` ise
    paralel kod yolunu tek işçiyle açar. PuLP'nin taşıdığı CBC 2.10.3'te o
    yol aynı girdide kimi koşuda takılıyor, kimi koşuda çöküyor (ölçüm:
    Görev 5 raporu). `None` da seri olur ama 0 niyeti açık yazar.
    """
    baslangic = time.perf_counter()
    if len(adaylar) == 0:
        return Plan(bos_hareketler(), "optimal", time.perf_counter() - baslangic, amac=0.0)

    model, x, y = kur(adaylar, kapasite, p)
    model.solve(pulp.PULP_CBC_CMD(
        msg=0,
        threads=0,
        gapRel=p.mip_bosluk_orani,
        timeLimit=p.mip_zaman_limiti_sn,
        maxNodes=p.mip_dugum_limiti,
    ))
    durum = DURUMLAR.get(model.sol_status, "hata")
    if durum == "hata":
        # tam sayı çözüm yok: değişken değerleri (varsa) LP gevşetmesinden, plan değil
        return Plan(bos_hareketler(), durum, time.perf_counter() - baslangic, amac=None)

    secilen = adaylar.loc[[i for i in adaylar.index if x[i].value() and x[i].value() > 0.5]]
    df = secilen[HAREKET_KOLONLARI].reset_index(drop=True) if len(secilen) else bos_hareketler()
    amac = float(pulp.value(model.objective))
    return Plan(df, durum, time.perf_counter() - baslangic, amac=amac)
