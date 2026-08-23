import numpy as np
import pandas as pd

from . import sabitler

# Tip başına (taban metrekare, dağılım genişliği) ve zincirdeki payı
TIP_PROFILI = {
    "AVM": {"taban": 320, "genislik": 90, "pay": 0.48},
    "Cadde": {"taban": 180, "genislik": 60, "pay": 0.36},
    "Outlet": {"taban": 520, "genislik": 140, "pay": 0.16},
}


def magazalari_uret(rng: np.random.Generator) -> pd.DataFrame:
    """Mağaza ana verisini üretir. Tip dağılımı sabit paylara göre kurulur."""
    tipler: list[str] = []
    for tip, profil in TIP_PROFILI.items():
        adet = round(sabitler.MAGAZA_SAYISI * profil["pay"])
        tipler.extend([tip] * adet)
    # Yuvarlama farkını en yaygın tiple kapat
    while len(tipler) < sabitler.MAGAZA_SAYISI:
        tipler.append("AVM")
    tipler = tipler[: sabitler.MAGAZA_SAYISI]

    sehirler = rng.choice(sabitler.SEHIRLER, size=sabitler.MAGAZA_SAYISI)
    metrekareler = [
        int(rng.normal(TIP_PROFILI[t]["taban"], TIP_PROFILI[t]["genislik"]))
        for t in tipler
    ]
    gun_farklari = rng.integers(0, 3650, size=sabitler.MAGAZA_SAYISI)
    acilislar = pd.Timestamp("2015-01-01") + pd.to_timedelta(gun_farklari, unit="D")

    return pd.DataFrame(
        {
            "magaza_id": [f"M{i:03d}" for i in range(1, sabitler.MAGAZA_SAYISI + 1)],
            "ad": [f"{sehir} {tip}" for sehir, tip in zip(sehirler, tipler)],
            "sehir": sehirler,
            "tip": tipler,
            "metrekare": [max(80, m) for m in metrekareler],
            "acilis_tarihi": acilislar,
            "aktif": True,
        }
    )
