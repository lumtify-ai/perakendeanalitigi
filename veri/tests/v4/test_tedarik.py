"""Testler: Görev 6 tedarikçiler, gizli profil, kalite kontrol, Lumoda seçimi.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §4.1-4.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-6-brief.md
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.tedarik import (
    alis_fiyati_uygula,
    hatali_adet,
    lumoda_tedarikci_secimi,
    teslim_sapmasi,
    tedarikcileri_uret,
)


@pytest.fixture(scope="module")
def t():
    """(tedarikciler, gizli_tedarikci) çifti — tek rng akışı, modül boyu."""
    return tedarikcileri_uret(dunya_akisi())


def test_on_sekiz(t):
    assert len(t[0]) == 18
    assert t[0].mense.value_counts().to_dict() == {"Yerli": 10, "Uzak Doğu": 6, "Yakın": 2}


def test_gizli_profil_yayimlanmaz(t):
    assert not {"hatali_orani", "kapasite_sezon_adet", "maliyet_carpani"} & set(t[0].columns)


def test_uzmanlik_her_alt_kategoriye_iki_tedarikci(t):
    from perakende_veri.v4.sabitler import ALT_KATEGORI_ALAN

    sayim = t[0]["uzmanlik"].value_counts()
    for alan in set(ALT_KATEGORI_ALAN.values()):
        assert sayim.get(alan, 0) >= 2, alan


def test_aksesuarda_yerli_var(t):
    aksesuar = t[0][t[0].uzmanlik == "aksesuar"]
    assert (aksesuar.mense == "Yerli").any()


def test_sapma_yonu(t):
    tedarikciler, gizli = t
    idx = np.arange(len(tedarikciler))
    sapma = teslim_sapmasi(dunya_akisi(), gizli, idx, 300)
    for i, mense in enumerate(tedarikciler["mense"]):
        if mense == "Yerli":
            assert np.all(np.abs(sapma[i]) <= 3), mense
        else:
            maks = 10 if mense == "Yakın" else 21
            assert np.all(sapma[i] >= 0) and np.all(sapma[i] <= maks), mense


def _sahte_optionlar(n, alt_kategoriler, sezon_kodu="AW23"):
    return pd.DataFrame(
        {
            "option_id": [f"O{i}" for i in range(n)],
            "alt_kategori": alt_kategoriler,
            "sezon_kodu": [sezon_kodu] * n,
        }
    )


def test_lumoda_secimi_performansa_kor(t):
    tedarikciler, gizli = t
    optionlar = _sahte_optionlar(
        10, ["Tişört", "Jean", "Mont", "Gömlek", "Kazak", "Çanta", "Etek", "Şort", "Elbise", "Tulum"]
    )
    talep = np.full(10, 100)

    secim1 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli, talep)

    gizli_ters = gizli.copy()
    for kol in ["hatali_orani", "maliyet_carpani", "gecikme_parametre_t", "gecikme_beklenen_gun"]:
        gizli_ters[kol] = gizli_ters[kol].to_numpy()[::-1]
    secim2 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli_ters, talep)

    assert np.array_equal(secim1, secim2)


def test_kapasite_tasmasi(t):
    tedarikciler, gizli = t
    optionlar = _sahte_optionlar(5, ["Tişört"] * 5)
    talep = np.full(5, 100)

    secim = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli, talep)
    assert len(set(secim.tolist())) == 1  # kapasite yeterli: hepsi birincile
    birincil = int(secim[0])

    gizli_dolu = gizli.copy()
    gizli_dolu.loc[birincil, "kapasite_sezon_adet"] = 0
    secim2 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli_dolu, talep)

    assert np.all(secim2 != birincil)
    assert len(set(secim2.tolist())) == 1  # hepsi aynı ikincile taşar


def test_kapasite_zinciri_ucuncu_tedarikciye(t):
    """Birincil ve ikincil sırayla dolunca üçüncü (farklı) bir tedarikçiye taşar."""
    tedarikciler, gizli = t
    optionlar = _sahte_optionlar(3, ["Tişört"] * 3)
    talep = np.full(3, 100)

    secim0 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli, talep)
    assert len(set(secim0.tolist())) == 1
    birincil = int(secim0[0])

    gizli1 = gizli.copy()
    gizli1.loc[birincil, "kapasite_sezon_adet"] = 0
    secim1 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli1, talep)
    assert len(set(secim1.tolist())) == 1
    ikincil = int(secim1[0])
    assert ikincil != birincil

    gizli2 = gizli1.copy()
    gizli2.loc[ikincil, "kapasite_sezon_adet"] = 0
    secim2 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli2, talep)
    assert len(set(secim2.tolist())) == 1
    ucuncu = int(secim2[0])
    assert ucuncu not in (birincil, ikincil)


def test_kapasite_hepsi_dolu_ikincilde_kalir(t):
    """Bütün tedarikçilerin kapasitesi sıfırlanırsa alışılmış ikincilde kalınır (aşım kabul)."""
    tedarikciler, gizli = t
    optionlar = _sahte_optionlar(3, ["Tişört"] * 3)
    talep = np.full(3, 100)

    secim0 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli, talep)
    birincil = int(secim0[0])
    gizli1 = gizli.copy()
    gizli1.loc[birincil, "kapasite_sezon_adet"] = 0
    secim1 = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli1, talep)
    ikincil = int(secim1[0])

    gizli_hepsi_dolu = gizli.copy()
    gizli_hepsi_dolu["kapasite_sezon_adet"] = 0
    secim_final = lumoda_tedarikci_secimi(
        dunya_akisi(), optionlar, tedarikciler, gizli_hepsi_dolu, talep
    )
    assert np.all(secim_final == ikincil)


def test_uzak_dogu_sapma_carpik(t):
    """Uzak Doğu teslim sapması sağa çarpık: ortalama > medyan (Beta(1.3,3.5))."""
    tedarikciler, gizli = t
    idx = np.flatnonzero((tedarikciler["mense"] == "Uzak Doğu").to_numpy())
    idx_genis = np.repeat(idx, 50)
    sapma = teslim_sapmasi(dunya_akisi(), gizli, idx_genis, 500)
    ornekler = sapma.astype(float).flatten()
    assert ornekler.mean() > np.median(ornekler)


def test_devamli_kapasite_siniri_yok(t):
    tedarikciler, gizli = t
    optionlar = _sahte_optionlar(5, ["Tişört"] * 5, sezon_kodu="DEVAMLI")
    talep = np.full(5, 10**9)  # devasa talep — kapasite sınırlı olsaydı taşardı

    secim = lumoda_tedarikci_secimi(dunya_akisi(), optionlar, tedarikciler, gizli, talep)
    assert len(set(secim.tolist())) == 1  # DEVAMLI kapasiteye bakmaz, hep birincil


def test_hatali_orani_yakinsar(t):
    tedarikciler, gizli = t
    idx = np.arange(len(tedarikciler))
    adet = np.full(len(tedarikciler), 2_000_000)

    numune, hatali = hatali_adet(dunya_akisi(), gizli, idx, adet)
    gozlenen = hatali / adet
    gercek = gizli["hatali_orani"].to_numpy()
    assert np.all(np.abs(gozlenen - gercek) / gercek < 0.25)


def test_hatali_adet_numune_formulu(t):
    tedarikciler, gizli = t
    idx = np.zeros(3, dtype=int)
    adet = np.array([10, 1000, 100000])
    numune, hatali = hatali_adet(dunya_akisi(), gizli, idx, adet)
    assert list(numune) == [10, 32 + 1000 // 50, 32 + 100000 // 50]
    assert np.all(hatali <= adet)


def test_uzmanlik_hatali_azaltir(t):
    tedarikciler, gizli = t
    idx = np.zeros(50000, dtype=int)
    adet = np.full(50000, 200)
    rng1 = dunya_akisi()
    _, hatali_uyumsuz = hatali_adet(rng1, gizli, idx, adet, uyum=np.zeros(50000, dtype=bool))
    rng2 = dunya_akisi()
    _, hatali_uyumlu = hatali_adet(rng2, gizli, idx, adet, uyum=np.ones(50000, dtype=bool))
    assert hatali_uyumlu.sum() < hatali_uyumsuz.sum()


def test_alis_fiyati_uygula_saf():
    alis = np.array([100.0, 100.0, 100.0])
    carpan = np.array([1.0, 1.0, 1.0])
    uyum = np.array([False, True, False])
    sonuc = alis_fiyati_uygula(alis, carpan, uyum)
    assert np.allclose(sonuc, [100.0, 93.0, 100.0])
