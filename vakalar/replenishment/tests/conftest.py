"""Ortak test yapılandırması.

Bu paketin testleri kendi fikstürlerini taşır (`test_kaynak.py` içindeki
`ortam`); burada yalnızca `pythonpath` ile paket bulunabilirliği sağlanır
(bkz. `pyproject.toml`).

`mini_dunya`: gerçek v2 verisine ihtiyaç duymayan, elle kurulmuş küçük bir
`Dunya`. 3 mağaza (M1, M2, M3) × 2 option (A: Collection, B: NOS) × 5 beden
= 30 hücre. Her hücrenin günlük plan talebi sabit 0.1 (hem plan hem
beklenen); mağaza kapasitesi 1000. Takvim (tarihler/tatil/sezon) gerçek
2025 takvimidir (`perakende_veri.takvim.takvim_uret`), böylece `gun()` ve
sezon aramaları üretim koduyla aynı davranır. Depo ve motor testleri bu
fikstürü paylaşır.
"""

import numpy as np
import pytest
from perakende_veri import takvim, talep

from replenishment.dunya import Dunya

MAGAZALAR = np.array(["M1", "M2", "M3"])
OPTIONLAR = np.array(["A", "B"])
BEDEN_SIRALARI = (1, 2, 3, 4, 5)

# OC (mağaza, option) sırası dunya_kur'daki gibi (magaza_id, option_id)
# artan sırayla: (M1,A),(M1,B),(M2,A),(M2,B),(M3,A),(M3,B).
OC_MAGAZA = np.array(["M1", "M1", "M2", "M2", "M3", "M3"])
OC_OPTION = np.array(["A", "B", "A", "B", "A", "B"])
OC_LINE = np.array(["Collection", "NOS", "Collection", "NOS", "Collection", "NOS"])
OC_MAGAZA_TIPI = np.array(["AVM", "AVM", "Cadde", "Cadde", "Outlet", "Outlet"])
OC_KATEGORI = np.array(["Üst Giyim"] * 6)


@pytest.fixture
def mini_dunya() -> Dunya:
    hucre_magaza = []
    hucre_urun = []
    for magaza in MAGAZALAR:
        for option in OPTIONLAR:
            for beden in BEDEN_SIRALARI:
                hucre_magaza.append(magaza)
                hucre_urun.append(f"{option}-{beden}")
    hucre_magaza = np.array(hucre_magaza)
    hucre_urun = np.array(hucre_urun)
    H = len(hucre_magaza)
    assert H == 30

    oc_hucre = np.arange(H, dtype=np.int64).reshape(6, 5)
    oc_opt = np.searchsorted(OPTIONLAR, OC_OPTION).astype(np.int64)
    oc_mag = np.searchsorted(MAGAZALAR, OC_MAGAZA).astype(np.int64)

    kapasite = np.full(len(MAGAZALAR), 1000, dtype=np.int64)

    takvim_df = takvim.takvim_uret()
    tarihler = takvim_df["tarih"].to_numpy().astype("datetime64[D]")
    tatil = takvim_df["tatil_mi"].to_numpy(dtype=bool)
    sezon = takvim_df["sezon"].to_numpy().astype(str)

    plan_deger = np.full(H, 0.1, dtype=float)
    sezon_adlari = np.unique(sezon)
    plan = {s: plan_deger.copy() for s in sezon_adlari}
    beklenen = {s: plan_deger.copy() for s in sezon_adlari}

    zincir_payi = talep.beden_dagilimi()
    zincir_beden_payi = np.array([zincir_payi[k] for k in range(1, 6)], dtype=float)

    return Dunya(
        tarihler=tarihler,
        tatil=tatil,
        hucre_magaza=hucre_magaza,
        hucre_urun=hucre_urun,
        oc_hucre=oc_hucre,
        oc_magaza=OC_MAGAZA,
        oc_option=OC_OPTION,
        oc_line=OC_LINE,
        oc_kategori=OC_KATEGORI,
        oc_magaza_tipi=OC_MAGAZA_TIPI,
        optionlar=OPTIONLAR,
        oc_opt=oc_opt,
        magazalar=MAGAZALAR,
        oc_mag=oc_mag,
        kapasite=kapasite,
        plan=plan,
        beklenen=beklenen,
        sezon=sezon,
        zincir_beden_payi=zincir_beden_payi,
    )


# mini_dunya_10: 10 mağaza (M01..M10, kapasite 1000) × tek option X
# (Collection) × 5 beden = 50 hücre. Dağıtım (Task 6) testleri için.

MAGAZALAR_10 = np.array([f"M{i:02d}" for i in range(1, 11)])
OC_MAGAZA_10 = MAGAZALAR_10
OC_OPTION_10 = np.array(["X"] * 10)
OC_LINE_10 = np.array(["Collection"] * 10)
OC_MAGAZA_TIPI_10 = np.array(["AVM"] * 10)
OC_KATEGORI_10 = np.array(["Üst Giyim"] * 10)


@pytest.fixture
def mini_dunya_10() -> Dunya:
    hucre_magaza = []
    hucre_urun = []
    for magaza in MAGAZALAR_10:
        for beden in BEDEN_SIRALARI:
            hucre_magaza.append(magaza)
            hucre_urun.append(f"X-{beden}")
    hucre_magaza = np.array(hucre_magaza)
    hucre_urun = np.array(hucre_urun)
    H = len(hucre_magaza)
    assert H == 50

    oc_hucre = np.arange(H, dtype=np.int64).reshape(10, 5)
    oc_opt = np.zeros(10, dtype=np.int64)
    oc_mag = np.arange(10, dtype=np.int64)

    kapasite = np.full(len(MAGAZALAR_10), 1000, dtype=np.int64)

    takvim_df = takvim.takvim_uret()
    tarihler = takvim_df["tarih"].to_numpy().astype("datetime64[D]")
    tatil = takvim_df["tatil_mi"].to_numpy(dtype=bool)
    sezon = takvim_df["sezon"].to_numpy().astype(str)

    plan_deger = np.full(H, 0.1, dtype=float)
    sezon_adlari = np.unique(sezon)
    plan = {s: plan_deger.copy() for s in sezon_adlari}
    beklenen = {s: plan_deger.copy() for s in sezon_adlari}

    zincir_payi = talep.beden_dagilimi()
    zincir_beden_payi = np.array([zincir_payi[k] for k in range(1, 6)], dtype=float)

    return Dunya(
        tarihler=tarihler,
        tatil=tatil,
        hucre_magaza=hucre_magaza,
        hucre_urun=hucre_urun,
        oc_hucre=oc_hucre,
        oc_magaza=OC_MAGAZA_10,
        oc_option=OC_OPTION_10,
        oc_line=OC_LINE_10,
        oc_kategori=OC_KATEGORI_10,
        oc_magaza_tipi=OC_MAGAZA_TIPI_10,
        optionlar=np.array(["X"]),
        oc_opt=oc_opt,
        magazalar=MAGAZALAR_10,
        oc_mag=oc_mag,
        kapasite=kapasite,
        plan=plan,
        beklenen=beklenen,
        sezon=sezon,
        zincir_beden_payi=zincir_beden_payi,
    )
