"""Görev 8: online teslim süresi (kargo)."""

import numpy as np
import pytest

from perakende_veri.v4 import sabitler as a_sabitler
from perakende_veri.v4.crm.kargo import (
    GECIKME_P_BF,
    GECIKME_P_NORMAL,
    il_mesafeleri,
    kargo_tablosu,
    teslim_gunu,
)
from perakende_veri.v4.crm.rastgele import crm_uretici
from perakende_veri.v4.takvim import gun_indisi

BF_GUN = gun_indisi(a_sabitler.BLACK_FRIDAY[1])   # 2023 BF, KUCUK penceresinde
NORMAL_GUN = BF_GUN - 60


def test_teslim_en_az_bir_gun():
    rng = np.random.default_rng(0)
    n = 2000
    il_mesafe_km = np.array([10.0, 500.0, 1200.0])
    il = np.random.default_rng(1).integers(0, 3, size=n)
    teslim, gecikme = teslim_gunu(rng, np.zeros(n, dtype=np.int64), il, il_mesafe_km)
    assert teslim.min() >= 1
    assert teslim.dtype.kind in "iu"
    assert gecikme.dtype == bool


def test_temel_gun_mesafe_esiklerine_gore():
    rng = np.random.default_rng(0)
    il_mesafe_km = np.array([10.0, 500.0, 1200.0])
    il = np.array([0, 1, 2])
    gun = np.full(3, NORMAL_GUN, dtype=np.int64)
    # gecikme çekilişini etkisiz kılmak için büyük örnekle ayrıca test
    # edildiğinden burada yalnız temel günü (rng sabit, düşük olasılık) kontrol
    # etmek için tekrar tekrar çekip en sık görülen (gecikmesiz) değere bakıyoruz
    temeller = []
    for tohum in range(50):
        t, g = teslim_gunu(np.random.default_rng(tohum), gun, il, il_mesafe_km)
        temeller.append(np.where(g, np.nan, t))
    temeller = np.array(temeller)
    beklenen = np.array([1, 2, 3])
    for i in range(3):
        gecikmesiz = temeller[:, i][~np.isnan(temeller[:, i])]
        assert (gecikmesiz == beklenen[i]).all()


def test_bf_haftasinda_gecikme_orani_iki_kattan_fazla():
    n = 40_000
    il_mesafe_km = np.array([10.0])
    il = np.zeros(n, dtype=np.int64)

    rng_normal = crm_uretici(NORMAL_GUN, "kargo")
    _, g_normal = teslim_gunu(rng_normal, np.full(n, NORMAL_GUN), il, il_mesafe_km)

    rng_bf = crm_uretici(BF_GUN, "kargo")
    _, g_bf = teslim_gunu(rng_bf, np.full(n, BF_GUN), il, il_mesafe_km)

    oran_normal = g_normal.mean()
    oran_bf = g_bf.mean()
    assert oran_normal == pytest.approx(GECIKME_P_NORMAL, abs=0.01)
    assert oran_bf == pytest.approx(GECIKME_P_BF, abs=0.01)
    assert oran_bf > 2 * oran_normal


def test_bf_penceresi_bf_gunune_kadar_ve_sonrasinda():
    # BF gününün hemen öncesi (pencere dışı) normal oranda, BF + 9 (pencere
    # içi son gün) BF oranında olmalı.
    n = 20_000
    il_mesafe_km = np.array([10.0])
    il = np.zeros(n, dtype=np.int64)

    onceki_gun = BF_GUN - 1
    rng_once = crm_uretici(onceki_gun, "kargo")
    _, g_once = teslim_gunu(rng_once, np.full(n, onceki_gun), il, il_mesafe_km)
    assert g_once.mean() == pytest.approx(GECIKME_P_NORMAL, abs=0.01)

    son_gun = BF_GUN + 9
    rng_son = crm_uretici(son_gun, "kargo")
    _, g_son = teslim_gunu(rng_son, np.full(n, son_gun), il, il_mesafe_km)
    assert g_son.mean() == pytest.approx(GECIKME_P_BF, abs=0.02)

    disari_gun = BF_GUN + 10
    rng_disari = crm_uretici(disari_gun, "kargo")
    _, g_disari = teslim_gunu(rng_disari, np.full(n, disari_gun), il, il_mesafe_km)
    assert g_disari.mean() == pytest.approx(GECIKME_P_NORMAL, abs=0.01)


def test_gecikme_ek_gun_araligi():
    n = 40_000
    il_mesafe_km = np.array([10.0])
    il = np.zeros(n, dtype=np.int64)
    rng = crm_uretici(BF_GUN, "kargo")
    teslim, gecikme = teslim_gunu(rng, np.full(n, BF_GUN), il, il_mesafe_km)
    ek = teslim[gecikme] - 1   # bu mesafede temel gün 1
    assert ek.min() >= 2
    assert ek.max() <= 6
    assert len(set(ek.tolist())) == 5  # 2,3,4,5,6 hepsi görülmeli


def test_determinizm_ayni_gun_ayni_sonuc():
    n = 500
    il_mesafe_km = np.array([10.0, 900.0])
    il = np.arange(n) % 2
    gun = np.full(n, NORMAL_GUN, dtype=np.int64)

    t1, g1 = teslim_gunu(crm_uretici(NORMAL_GUN, "kargo"), gun, il, il_mesafe_km)
    t2, g2 = teslim_gunu(crm_uretici(NORMAL_GUN, "kargo"), gun, il, il_mesafe_km)
    assert (t1 == t2).all()
    assert (g1 == g2).all()


def test_il_mesafeleri_kucuk_girdi(kucuk_girdi):
    from perakende_veri.v4.crm.nufus import magaza_bilgisi, nufus_baslat

    mb = magaza_bilgisi(kucuk_girdi)
    nufus = nufus_baslat(np.random.default_rng(0), kucuk_girdi)
    mesafeler = il_mesafeleri(kucuk_girdi, nufus)
    assert len(mesafeler) == len(mb.il_adlari)
    assert (mesafeler >= 0).all()
    assert np.isfinite(mesafeler).all()


def test_kargo_tablosu_onl_satis_fisleriyle_eslesir(kucuk_girdi, kucuk_crm):
    fis = kucuk_crm.tablo("fis")
    mb = kucuk_crm.nufus.magaza
    beklenen = fis[(fis["magaza"] == mb.onl) & (fis["tip"] == 0)]

    df = kargo_tablosu(kucuk_crm, kucuk_girdi)

    assert len(df) == len(beklenen)
    assert set(df["fis_id"]) == set(beklenen["fis_id"])
    assert (df["teslim_gun"] >= 1).all()
    assert df["gecikme"].dtype == bool
