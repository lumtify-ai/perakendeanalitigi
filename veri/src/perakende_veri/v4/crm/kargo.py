"""Görev 8: online teslim süresi (spec §5 bağlamı; A'da müşteri teslim
süresi yok, B'ye ait). Depo Gebze (`sabitler.GEBZE_DEPO`); il uzaklığı
depodan ilin merkezine (A'nın o ildeki mağazalarının ortalama enlem/boylamı)
büyük çember uzaklığı (`magaza.haversine_km`). İli olmayan (mağazasız) il
B'de yoktur: her il A'nın en az bir fiziksel mağazasından gelir.

Teslim günü = 1 + (mesafe > 300 km) + (mesafe > 800 km); gecikme olasılıkla
0,08 (Black Friday haftasında 0,25 — BF günü dahil sonraki 10 gün: BF'nin
kendisi + izleyen Pazar + 2 gün daha), gecikmede 2–6 gün ek (uniform, dahil).
Çekilişler fiş günü başına tek sayaç akışı (`crm_uretici(d, "kargo")`),
gün içi fiş sayısına göre boyutlanır: sonuç yalnız o günün ONL satış fişi
sayısına bağlıdır (kalibrasyon/koşu uzunluğu diğer günleri etkilemez).

Gizli: `gecikme` bayrağı (yayımlanan tabloya girmez; Görev 13 gizler)."""

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..magaza import haversine_km
from ..takvim import gun_indisi
from .rastgele import crm_uretici

GECIKME_P_NORMAL = 0.08
GECIKME_P_BF = 0.25
BF_PENCERE_GUN = 10          # BF günü dahil, izleyen 10 gün
GECIKME_EK_ALT, GECIKME_EK_UST = 2, 6   # uniform, ikisi de dahil


def _bf_gunleri() -> np.ndarray:
    return np.array([gun_indisi(t) for t in a_sabitler.BLACK_FRIDAY], dtype=np.int64)


def _bf_maskesi(gun: np.ndarray) -> np.ndarray:
    """`gun` (fiş günü) BF penceresinde mi: BF günü dahil sonraki
    `BF_PENCERE_GUN` gün (BF'nin kendisi + izleyen Pazar + 2 gün daha, yani
    BF'den itibaren 10 günlük pencere)."""
    gun = np.asarray(gun)
    maske = np.zeros(len(gun), dtype=bool)
    for b in _bf_gunleri():
        maske |= (gun >= b) & (gun < b + BF_PENCERE_GUN)
    return maske


def il_mesafeleri(girdi, nufus) -> np.ndarray:
    """`[n_il]` Gebze deposundan il merkezine (A'nın o ildeki fiziksel
    mağazalarının ortalama enlem/boylamı) km. İl sırası `nufus.magaza.il_adlari`."""
    mag = girdi.dunya.magazalar
    mb = nufus.magaza
    n_il = len(mb.il_adlari)
    lat = mag["enlem"].to_numpy(dtype=float)
    lon = mag["boylam"].to_numpy(dtype=float)
    fiziksel = mb.il >= 0
    il_f = mb.il[fiziksel]
    sayi = np.bincount(il_f, minlength=n_il).astype(float)
    assert (sayi > 0).all(), "her il en az bir fiziksel mağazadan gelmeli"
    lat_top = np.bincount(il_f, weights=lat[fiziksel], minlength=n_il)
    lon_top = np.bincount(il_f, weights=lon[fiziksel], minlength=n_il)
    merkez_lat, merkez_lon = lat_top / sayi, lon_top / sayi
    depo_lat, depo_lon = a_sabitler.GEBZE_DEPO
    return haversine_km(depo_lat, depo_lon, merkez_lat, merkez_lon)


def teslim_gunu(rng, fis_gun: np.ndarray, il: np.ndarray,
                il_mesafe_km: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(teslim_gun, gecikme)`: temel gün 1 + (mesafe > 300) + (mesafe > 800);
    gecikmede (olasılık BF haftasında 0,25, yoksa 0,08) 2–6 ek gün. `rng`
    tek çekiliş akışı (çağıran fiş günü başına `crm_uretici(d, "kargo")`
    verir); çekilişler her satır için (gecikme dahil olmasa da) aynı sırada
    tüketilir, böylece sonuç yalnız satır sayısına bağlıdır."""
    fis_gun = np.asarray(fis_gun)
    n = len(fis_gun)
    km = il_mesafe_km[np.asarray(il)]
    temel = 1 + (km > 300).astype(np.int64) + (km > 800).astype(np.int64)

    p = np.where(_bf_maskesi(fis_gun), GECIKME_P_BF, GECIKME_P_NORMAL)
    u = rng.random(n)
    gecikme = u < p
    ek_cekilis = rng.integers(GECIKME_EK_ALT, GECIKME_EK_UST + 1, size=n)
    ek = np.where(gecikme, ek_cekilis, 0)

    return temel + ek, gecikme


def kargo_tablosu(crm_ham, girdi) -> pd.DataFrame:
    """ONL satış fişleri için `(fis_id, teslim_gun, gecikme)`. `gecikme`
    gizlidir (Görev 13 yayımlanan tablodan çıkarır); burada teşhis/test
    amaçlı üretilir. Çekiliş gün başına `crm_uretici(d, "kargo")`."""
    fis = crm_ham.tablo("fis")
    mb = crm_ham.nufus.magaza
    onl_satis = (fis["magaza"].to_numpy() == mb.onl) & (fis["tip"].to_numpy() == 0)
    alt = fis.loc[onl_satis]

    if not len(alt):
        return pd.DataFrame({
            "fis_id": np.zeros(0, dtype=np.int64),
            "teslim_gun": np.zeros(0, dtype=np.int64),
            "gecikme": np.zeros(0, dtype=bool),
        })

    gun = alt["gun"].to_numpy(dtype=np.int64)
    fis_id = alt["fis_id"].to_numpy(dtype=np.int64)
    musteri = alt["musteri"].to_numpy(dtype=np.int64)
    il = crm_ham.nufus.il[musteri]
    il_km = il_mesafeleri(girdi, crm_ham.nufus)

    teslim = np.empty(len(alt), dtype=np.int64)
    gecikme = np.empty(len(alt), dtype=bool)
    sira = np.argsort(gun, kind="stable")
    gs = gun[sira]
    sinir = np.flatnonzero(np.diff(gs)) + 1
    for parca in np.split(sira, sinir):
        if not len(parca):
            continue
        d = int(gun[parca[0]])
        rng = crm_uretici(d, "kargo")
        t, g = teslim_gunu(rng, gun[parca], il[parca], il_km)
        teslim[parca] = t
        gecikme[parca] = g

    return pd.DataFrame({"fis_id": fis_id, "teslim_gun": teslim, "gecikme": gecikme})
