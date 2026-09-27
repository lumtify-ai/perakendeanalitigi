"""Testler: Görev 5 ürün evreni, öznitelikler, fiyat, paket.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-5-brief.md

Controller kararı: hacim sınırı brief'teki 1.620-1.780 değil 1.820-1.920
(AW22 de üretilir, bkz. task-5-brief üstü mesaj / task-5-report.md).
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.rastgele import dunya_akisi
from perakende_veri.v4.urun import (
    AKSESUAR,
    GECERLI_KUMAS,
    KATEGORILER,
    YALNIZ_KADIN,
    liste_fiyati,
    paketleri_uret,
    urunleri_uret,
)


@pytest.fixture(scope="module")
def uo():
    """Küçük ölçekte (hızlı) urunler, optionlar çifti."""
    return urunleri_uret(dunya_akisi(), Olcek.KUCUK)


@pytest.fixture(scope="module")
def u(uo):
    return uo[0]


def test_hiyerarsi_tutarli(u):
    # her option tek model, tek renk
    assert (u.groupby("option_id")["model_kodu"].nunique() == 1).all()
    assert (u.groupby("option_id")["renk"].nunique() == 1).all()
    # her model tek alt kategori
    assert (u.groupby("model_kodu")["alt_kategori"].nunique() == 1).all()
    # ust_kategori KATEGORILER'e uyar
    alt_to_ust = {alt: ust for ust, altlar in KATEGORILER.items() for alt in altlar}
    assert (u["ust_kategori"] == u["alt_kategori"].map(alt_to_ust)).all()


def test_yalniz_kadin(u):
    assert (u[u.alt_kategori.isin(YALNIZ_KADIN)].cinsiyet == "Kadın").all()


def test_aksesuar_tek_beden(u):
    assert (u[u.ust_kategori == "Aksesuar"].beden == "STD").all()


def test_kumas_gecerli(u):
    for alt_kategori, grup in u.groupby("alt_kategori"):
        gecerli = GECERLI_KUMAS[alt_kategori]
        assert grup.kumas.isin(gecerli).all(), alt_kategori


def test_hacim_tam():
    urunler, optionlar = urunleri_uret(dunya_akisi(), Olcek.TAM)
    sezonlu = optionlar[optionlar.sezon_kodu != "DEVAMLI"]
    for kod, grup in sezonlu.groupby("sezon_kodu"):
        assert (grup.line == "Collection").sum() == 210, kod
        assert (grup.line == "Outlet").sum() == 40, kod

    devamli = optionlar[optionlar.sezon_kodu == "DEVAMLI"]
    assert (devamli.line == "Basic").sum() == 80
    assert (devamli.line == "NOS").sum() == 40

    assert 1_820 <= len(optionlar) <= 1_920


def test_fiyat_bicimi(u):
    assert np.allclose((u.liste_fiyati + 0.01) % 10, 0)
    assert (u.liste_fiyati > u.alis_fiyati * 2).all()


def test_paket_toplami():
    p = paketleri_uret()
    assert p.groupby("paket_id").adet.sum().min() >= 6


def test_mont_yaz_yok(u):
    assert not (
        (u.alt_kategori == "Mont")
        & u.sezon_kodu.str.startswith("SS")
        & (u.line == "Collection")
    ).any()


def test_sort_kis_yok(u):
    assert not (
        (u.alt_kategori == "Şort")
        & u.sezon_kodu.str.startswith("AW")
        & (u.line == "Collection")
    ).any()


def test_liste_fiyati_saf():
    alis = np.array([100.0, 200.0, 50.0])
    segment = np.array(["giris", "orta", "premium"])
    sonuc = liste_fiyati(alis, segment)
    assert np.allclose((sonuc + 0.01) % 10, 0)
    assert (sonuc > alis * 2).all()


def test_tedarikci_bos(u):
    assert u["tedarikci_id"].isna().all()


def test_detay_alani(u):
    aksesuar = u[u.ust_kategori == "Aksesuar"]
    assert aksesuar.detay.isna().all()
    diger = u[u.ust_kategori != "Aksesuar"]
    assert diger.detay_alani.notna().all()
