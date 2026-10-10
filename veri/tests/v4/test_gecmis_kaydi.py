"""Testler: `simule_et(..., gecmis_kaydi=True)` (RPT v4, Görev 7, Ruling R6).

Motor içi karar anı kestiricisi (vaka: `rpt.anlik.gunluk_gorunumden`) o
dünyanın kendi geçmişini görmelidir. Varsayılan (`False`) motorun bugünkü
davranışıdır: `Gorunum`un geçmiş alanları `None`, çıktılar birebir aynı
(yayımlanan v4 değişmez; tam karşılaştırma `test_talep_tohumu`'nun yavaş
testi). `True` iken `Gorunum` üç geçmiş sunar:

    satis_oncesi_gecmisi  [gün < d, C] ortak günlük tablonun `satis_oncesi`si
    fiyat_gecmisi         fiyat değişim kaydı, gün < d
    stok_fotograflari     pazartesi mağaza fotoğrafları, gün <= d
"""

import numpy as np
import pandas as pd
import pytest

from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar, lumoda_replenishment

GUN_SAYISI = 260  # pencere 181. günde başlar; satış, fiyat ve fotoğraf oluşur


class _Yakala:
    """Lumoda'nın replenishment'ını sarar; her pazartesi görünümü saklar."""

    def __init__(self):
        self.gorunumler = []

    def __call__(self, g):
        self.gorunumler.append(g)
        return lumoda_replenishment(g)


def _esit(a, b, ad: str = "") -> None:
    if isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), obj=ad)
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=ad)
        assert a.dtype == b.dtype, ad
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), ad
        for k in a:
            _esit(a[k], b[k], f"{ad}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), ad
        for i, (x, y) in enumerate(zip(a, b)):
            _esit(x, y, f"{ad}[{i}]")
    else:
        assert a == b, ad


@pytest.fixture(scope="module")
def kayitli(kucuk_dunya):
    y = _Yakala()
    ham = simule_et(kucuk_dunya, Politikalar(replenishment=y), gun_sayisi=GUN_SAYISI,
                    kayit_talep=True, gecmis_kaydi=True)
    return ham, y.gorunumler


def test_varsayilan_gorunumde_gecmis_yok(kucuk_dunya):
    y = _Yakala()
    simule_et(kucuk_dunya, Politikalar(replenishment=y), gun_sayisi=60)
    assert y.gorunumler
    for g in y.gorunumler:
        assert g.satis_oncesi_gecmisi is None
        assert g.fiyat_gecmisi is None
        assert g.stok_fotograflari is None


def test_gecmis_kaydi_ciktilari_degistirmez(kucuk_dunya, kayitli):
    """Kayıt yalnız okur: bütün ham çıktılar kayıtsız koşuyla birebir aynı."""
    ham, _ = kayitli
    ref = simule_et(kucuk_dunya, gun_sayisi=GUN_SAYISI, kayit_talep=True)
    assert len(ref["satis"]) > 0 and len(ref["fiyat"]) > 0 and len(ref["stok"]) > 0
    assert ham.keys() == ref.keys()
    for ad in ref:
        _esit(ham[ad], ref[ad], ad)


def test_gecmis_yalniz_bugunden_once(kayitli):
    _, gorunumler = kayitli
    for g in gorunumler:
        so = g.satis_oncesi_gecmisi
        assert so.shape == g.satis_gecmisi.shape and so.dtype == np.int32
        assert not so.flags.writeable
        assert all(p[0] < g.gun for p in g.fiyat_gecmisi)
        assert all(p[0] <= g.gun for p in g.stok_fotograflari)
        assert g.stok_fotograflari and g.stok_fotograflari[-1][0] == g.gun   # bu sabahın fotoğrafı
        for p in g.fiyat_gecmisi + g.stok_fotograflari:
            assert all(not np.asarray(a).flags.writeable for a in p[1:])


def test_satis_oncesi_ortak_tanimla(kucuk_dunya, kayitli):
    """Fiziksel hücre: satıştan önceki raf (stoklu bayrağı onun > 0'ıdır, satış onu
    aşmaz). ONL: ertesi sabahın depo stoğu + günün net online satışı (ortak
    `stok.gunluk_online`'ın tanımı)."""
    w = kucuk_dunya
    ham, gorunumler = kayitli
    g = gorunumler[-1]
    so = np.asarray(g.satis_oncesi_gecmisi, dtype=np.int64)
    D = g.gun
    onl = np.asarray(w.hucre_online)
    fiz = ~onl
    st = np.asarray(g.stoklu_gecmisi)
    np.testing.assert_array_equal(st[:, fiz], so[:, fiz] > 0)
    assert (np.asarray(g.satis_gecmisi)[:, fiz] <= so[:, fiz]).all()
    assert (so[:, fiz] > 0).any()

    hs = np.asarray(w.hucre_sku)
    onl_c = np.flatnonzero(onl)
    sku_hucre = np.full(len(w.urunler), -1)
    sku_hucre[hs[onl_c]] = onl_c
    depo = np.zeros((D + 1, len(w.urunler)), dtype=np.int64)
    ds = ham["depo_stok"]
    ds = ds[ds["gun"] <= D]
    depo[ds["gun"].to_numpy(), ds["sku"].to_numpy()] = ds["adet"].to_numpy()
    net = np.zeros((D, len(w.urunler)), dtype=np.int64)
    s = ham["satis"]
    s = s[(s["gun"] < D) & onl[s["hucre"].to_numpy()]]
    np.add.at(net, (s["gun"].to_numpy(), hs[s["hucre"].to_numpy()]), s["adet"].to_numpy())
    beklenen = depo[1:D + 1] + net                               # [D, S]
    np.testing.assert_array_equal(so[:, onl_c], beklenen[:, hs[onl_c]])
    assert (so[:, onl_c] > 0).any()


def test_fiyat_ve_fotograf_kayitla_ayni(kayitli):
    ham, gorunumler = kayitli
    g = gorunumler[-1]
    f = ham["fiyat"]
    f = f[f["gun"] < g.gun]
    gun = np.concatenate([np.full(len(p[1]), p[0]) for p in g.fiyat_gecmisi])
    np.testing.assert_array_equal(gun, f["gun"].to_numpy())
    np.testing.assert_array_equal(np.concatenate([p[1] for p in g.fiyat_gecmisi]), f["option"].to_numpy())
    np.testing.assert_array_equal(np.concatenate([p[2] for p in g.fiyat_gecmisi]), f["hat"].to_numpy())
    np.testing.assert_array_equal(np.concatenate([p[3] for p in g.fiyat_gecmisi]), f["oran"].to_numpy())

    s = ham["stok"]
    s = s[s["gun"] <= g.gun]
    gun = np.concatenate([np.full(len(p[1]), p[0]) for p in g.stok_fotograflari])
    np.testing.assert_array_equal(gun, s["gun"].to_numpy())
    for i, ad in ((1, "hucre"), (2, "adet"), (3, "stoklu_gun")):
        np.testing.assert_array_equal(np.concatenate([p[i] for p in g.stok_fotograflari]), s[ad].to_numpy())
