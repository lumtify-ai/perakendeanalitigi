import os
import time
import warnings

import pandas as pd
import pulp

from ..cekirdek.parametreler import Parametreler
from . import greedy
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


def _olurlulugu_dogrula(secilen: pd.DataFrame, kapasite: dict[str, int], p: Parametreler) -> None:
    """Başlangıç planı §6 kısıtlarını sağlamalı; sağlamıyorsa açık hata.

    CBC olursuz bir başlangıcı sessizce yok sayar; o zaman "MIP greedy'den
    kötü olamaz" güvencesi de sessizce kaybolur."""
    if secilen.duplicated(["verici", "option_id"]).any():
        raise RuntimeError("sıcak başlangıç olursuz: bir blok iki hedefe gidiyor")
    yuk = secilen.groupby("alici", observed=True).adet.sum()
    asan = [a for a, adet in yuk.items() if adet > kapasite.get(a, 0)]
    if asan:
        raise RuntimeError(f"sıcak başlangıç olursuz: kapasite aşılıyor ({asan})")
    rota = secilen.groupby(["verici", "alici"], observed=True).adet.sum()
    if (rota < p.min_koli).any():
        raise RuntimeError("sıcak başlangıç olursuz: min_koli altında rota var")


def _sicak_baslangic(
    adaylar: pd.DataFrame, kapasite: dict[str, int], p: Parametreler, x: dict, y: dict
) -> bool:
    """Greedy planını CBC'ye başlangıç çözümü olarak yazar (x, y başlangıç değerleri).

    Greedy'nin min_koli post-filtresinden çıkan plan MIP için olurludur (blok
    tek hedefe, kapasite, açık her rota ≥ K); CBC onu ilk olurlu çözüm alır.
    Sonuç: düğüm ya da süre limitinde duran MIP bile greedy'den kötü olamaz.

    Başlangıç verilmeyen iki durum (False döner):
      - greedy planı boş: boş plan zaten olurlu (amaç 0), söylenecek bir şey yok;
      - (verici, alıcı, option) üçlüsü adaylarda tekil değil: hareketi adaya
        eşlemek belirsiz (üretilen adaylarda olmaz, elle kurulan girdiye karşı).
    """
    h = greedy.cozumle(adaylar, kapasite, p).hareketler
    if len(h) == 0:
        return False
    uclu = list(zip(adaylar.verici, adaylar.alici, adaylar.option_id))
    if len(set(uclu)) != len(uclu):
        return False
    sira = dict(zip(uclu, adaylar.index))
    secilen = {sira[k] for k in zip(h.verici, h.alici, h.option_id)}
    _olurlulugu_dogrula(adaylar.loc[sorted(secilen)], kapasite, p)
    acik = set(zip(h.verici, h.alici))
    for i, degisken in x.items():
        degisken.setInitialValue(1 if i in secilen else 0)
    for r, degisken in y.items():
        degisken.setInitialValue(1 if r in acik else 0)
    return True


def _surucusuz_gecici_dosyalar(cozucu: pulp.PULP_CBC_CMD) -> bool:
    r"""CBC 2.10.3, `-mips` dosya adı `/` ya da `\` ile başlamıyorsa başına `.\`
    ekler: Windows'ta `C:\...` mutlak yolu bozulur, başlangıç sessizce okunmaz.
    Geçici dosya yollarından sürücü harfini atar (`\Users\...`); CBC süreci
    Python'un çalışma dizininin sürücüsünü kullanır, bu yüzden yalnız geçici
    dizin aynı sürücüdeyse yapılır. Yapılamazsa False."""
    surucu = os.path.splitdrive(cozucu.tmpDir)[0]
    if not surucu:
        return True                                  # POSIX: yol zaten / ile başlar
    if surucu.lower() != os.path.splitdrive(os.getcwd())[0].lower():
        return False
    asil = cozucu.create_tmp_files
    cozucu.create_tmp_files = lambda ad, *uzantilar: [
        os.path.splitdrive(f)[1] for f in asil(ad, *uzantilar)
    ]
    return True


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

    Sıcak başlangıç: greedy planı CBC'ye ilk olurlu çözüm olarak verilir
    (`_sicak_baslangic`); hangi sınırda durursa dursun MIP amacı greedy
    amacından düşük olamaz.

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
    sicak = _sicak_baslangic(adaylar, kapasite, p, x, y)
    cozucu = pulp.PULP_CBC_CMD(
        msg=0,
        warmStart=sicak,
        threads=0,
        gapRel=p.mip_bosluk_orani,
        timeLimit=p.mip_zaman_limiti_sn,
        maxNodes=p.mip_dugum_limiti,
    )
    if sicak and not _surucusuz_gecici_dosyalar(cozucu):
        warnings.warn("CBC geçici dizini başka sürücüde: sıcak başlangıç okunamaz, "
                      "MIP greedy'den kötü kalabilir")
    # CBC 2.10.3 `-max` ile verilen başlangıcın amacını ters işaretle kaydeder
    # (başlangıç işe yaramaz). Aynı problemi eksi amaçla en küçükleyerek çözeriz;
    # `kur`un modeli (rapor da onu okur) en büyükleme olarak kalır.
    model.sense = pulp.LpMinimize
    model.objective = -model.objective
    model.solve(cozucu)
    durum = DURUMLAR.get(model.sol_status, "hata")
    if durum == "hata":
        # tam sayı çözüm yok: değişken değerleri (varsa) LP gevşetmesinden, plan değil
        return Plan(bos_hareketler(), durum, time.perf_counter() - baslangic, amac=None)

    secilen = adaylar.loc[[i for i in adaylar.index if x[i].value() and x[i].value() > 0.5]]
    df = secilen[HAREKET_KOLONLARI].reset_index(drop=True) if len(secilen) else bos_hareketler()
    amac = -float(pulp.value(model.objective))      # en küçüklenen eksi amaç
    return Plan(df, durum, time.perf_counter() - baslangic, amac=amac)
