"""Mağaza ana verisi.

Transfer probleminin ilginçliği mağaza sayısından değil mağazalar
arasındaki farktan gelir: tip, büyüklük ve şehir bir mağazanın talep
profilini de kapasitesini de belirler.
"""

import numpy as np
import pandas as pd

from . import sabitler

# Tip başına taban metrekare, dağılım genişliği, zincirdeki payı ve
# raf yoğunluğu (metrekare başına taşınabilir adet)
TIP_PROFILI = {
    "AVM": {"taban": 320, "genislik": 90, "pay": 0.48, "yogunluk": 9.0},
    "Cadde": {"taban": 180, "genislik": 60, "pay": 0.36, "yogunluk": 8.0},
    "Outlet": {"taban": 520, "genislik": 140, "pay": 0.16, "yogunluk": 12.5},
}


def _tipleri_dagit() -> list[str]:
    """Tipleri sabit paylara göre dağıtır."""
    tipler: list[str] = []
    for tip, profil in TIP_PROFILI.items():
        tipler.extend([tip] * round(sabitler.MAGAZA_SAYISI * profil["pay"]))
    while len(tipler) < sabitler.MAGAZA_SAYISI:
        tipler.append("AVM")
    return tipler[: sabitler.MAGAZA_SAYISI]


def _sehirleri_dagit(rng: np.random.Generator) -> list[str]:
    """Mağazaları şehirlere ağırlıklarına göre dağıtır.

    Rastgele örnekleme yerine en büyük kalan yöntemi kullanılır: 25
    mağazalık bir zincirde örnekleme gürültüsü hedeflenen dağılımı
    bozar (İstanbul payı %30 iken 4 mağazaya düşebilir). Burada bir
    zincir tasarlanıyor, örneklenmiyor.
    """
    hedefler = [a * sabitler.MAGAZA_SAYISI for a in sabitler.SEHIR_AGIRLIKLARI]
    adetler = [int(h) for h in hedefler]

    kalan = sabitler.MAGAZA_SAYISI - sum(adetler)
    kesirler = sorted(
        range(len(hedefler)), key=lambda i: hedefler[i] - adetler[i], reverse=True
    )
    for i in kesirler[:kalan]:
        adetler[i] += 1

    sehirler = [
        sehir
        for sehir, adet in zip(sabitler.SEHIRLER, adetler)
        for _ in range(adet)
    ]
    # Şehir sırası tip sırasıyla örtüşmesin: karıştırılmazsa İstanbul
    # mağazalarının tamamı AVM olur.
    return [sehirler[i] for i in rng.permutation(len(sehirler))]


def _adlari_uret(sehirler: list[str]) -> list[str]:
    """Her mağazaya semt bazlı benzersiz bir ad verir.

    Aynı şehirde birden çok mağaza olduğu için ad şehir değil konum
    belirtir. Semt havuzu tükenirse sıra numarasına düşülür.
    """
    kalan = {sehir: list(semtler) for sehir, semtler in sabitler.SEMTLER.items()}
    sayaclar: dict[str, int] = {}
    adlar = []
    for sehir in sehirler:
        havuz = kalan.get(sehir, [])
        if havuz:
            adlar.append(f"{sehir} {havuz.pop(0)}")
        else:
            sayaclar[sehir] = sayaclar.get(sehir, 1) + 1
            adlar.append(f"{sehir} {sayaclar[sehir]}. Mağaza")
    return adlar


def magazalari_uret(rng: np.random.Generator) -> pd.DataFrame:
    """Mağaza ana verisini üretir."""
    tipler = _tipleri_dagit()

    sehirler = _sehirleri_dagit(rng)

    metrekareler = [
        max(80, int(rng.normal(TIP_PROFILI[t]["taban"], TIP_PROFILI[t]["genislik"])))
        for t in tipler
    ]
    # Kapasite = taşınabilir azami adet; transfer kısıtının girdisidir
    kapasiteler = [
        int(m * TIP_PROFILI[t]["yogunluk"]) for m, t in zip(metrekareler, tipler)
    ]

    gun_farklari = rng.integers(0, 3650, size=sabitler.MAGAZA_SAYISI)
    acilislar = pd.Timestamp("2015-01-01") + pd.to_timedelta(gun_farklari, unit="D")

    return pd.DataFrame(
        {
            "magaza_id": [f"M{i:03d}" for i in range(1, sabitler.MAGAZA_SAYISI + 1)],
            "ad": _adlari_uret(sehirler),
            "sehir": sehirler,
            "tip": tipler,
            "metrekare": metrekareler,
            "kapasite": kapasiteler,
            "acilis_tarihi": acilislar,
            "aktif": True,
        }
    )
