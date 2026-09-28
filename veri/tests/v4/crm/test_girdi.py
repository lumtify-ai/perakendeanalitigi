"""Görev 1: B'nin A'dan okuduğu girdi görünümü."""

import hashlib

import numpy as np
import pandas as pd

from perakende_veri.v4.tablolar import pencere


def _satis_ozeti(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def _yigin(parcalar: list[np.ndarray], genislik: int) -> np.ndarray:
    dolu = [p for p in parcalar if len(p)]
    return np.concatenate(dolu) if dolu else np.empty((0, genislik))


def test_gunluk_toplam_temiz_satisa_esit(kucuk_girdi):
    from perakende_veri.v4.crm import girdi as G
    from perakende_veri.v4.uret import yayimla

    g = kucuk_girdi
    bas, son = pencere()
    temiz = yayimla(g.dunya, g.ham, kirli=False)["satis"]
    ham = g.ham["satis"]
    isinma = ham[ham["gun"].to_numpy() < bas]

    assert len(g.satis_gun) == len(g.iade_gun) == len(g.kayip_gun) == g.D
    sat = _yigin(g.satis_gun, len(G.SUTUNLAR))
    iad = _yigin(g.iade_gun, len(G.SUTUNLAR))
    assert (sat[:, G.ADET] > 0).all() and (iad[:, G.ADET] < 0).all()
    assert len(sat) + len(iad) == len(temiz) + len(isinma)

    for kolon, i in (("adet", G.ADET), ("tutar", G.TUTAR), ("indirim_tutari", G.INDIRIM)):
        beklenen = temiz[kolon].sum() + isinma[kolon].sum()
        assert abs(sat[:, i].sum() + iad[:, i].sum() - beklenen) < 0.5, kolon

    # Gün gün: pencere günlerinde yayımlanan temiz satışın adet ve tutarı
    gun = (temiz["tarih"].to_numpy().astype("datetime64[D]")
           - np.datetime64("2022-07-04", "D")).astype(np.int64)
    adet_gun = np.bincount(gun, temiz["adet"].to_numpy(), minlength=g.D)
    tutar_gun = np.bincount(gun, temiz["tutar"].to_numpy(), minlength=g.D)
    for d in range(bas, min(son, g.D - 1) + 1):
        a = g.satis_gun[d][:, G.ADET].sum() + g.iade_gun[d][:, G.ADET].sum()
        t = g.satis_gun[d][:, G.TUTAR].sum() + g.iade_gun[d][:, G.TUTAR].sum()
        assert a == adet_gun[d], d
        assert abs(t - tutar_gun[d]) < 0.01 * (len(g.satis_gun[d]) + len(g.iade_gun[d]) + 1), d


def test_islem_adet_tutari_kurar(kucuk_girdi):
    from perakende_veri.v4.crm import girdi as G

    g = kucuk_girdi
    liste_s = g.dunya.urunler["liste_fiyati"].to_numpy(dtype=float)
    hs = np.asarray(g.dunya.hucre_sku)
    satir_sayisi = 0
    for parca in (*g.satis_gun, *g.iade_gun):
        if not len(parca):
            continue
        liste = liste_s[hs[parca[:, G.H].astype(np.int64)]]
        adet, k, oran = parca[:, G.ADET], parca[:, G.ISLEM], parca[:, G.ORAN]
        kurulan = liste * (adet - 0.3 * k) * (1 - oran)
        assert np.abs(kurulan - parca[:, G.TUTAR]).max() <= 0.01
        # k, adetle aynı işarette ve |k| ≤ |adet|; yalnız oran 0 satırlarda
        assert (np.abs(k) <= np.abs(adet)).all() and (k * adet >= 0).all()
        assert (k[oran > 0] == 0).all()
        # Global dizi ile satır sütunu tutarlı
        assert (g.islem_adet[parca[:, G.SATIR].astype(np.int64)] == k).all()
        satir_sayisi += len(parca)
    assert satir_sayisi == len(g.islem_adet)
    # İşlem indirimi A'da tam fiyatlı hücre-günlerin ~%8'inde
    sat = np.concatenate([p for p in g.satis_gun if len(p)])
    tam = sat[sat[:, G.ORAN] == 0]
    pay = (tam[:, G.ISLEM] > 0).mean()
    assert 0.05 < pay < 0.11, pay


def test_kayip_isinma_dahil(kucuk_girdi):
    bas, _ = pencere()
    assert sum(len(x) for x in kucuk_girdi.kayip_gun[:bas]) > 0
    toplam = sum(int(x[:, 1].sum()) for x in kucuk_girdi.kayip_gun if len(x))
    assert toplam == int(kucuk_girdi.ham["gizli_kayip"]["adet"].sum())


def test_a_degismedi(kucuk_girdi):
    """B modülleri import edilip girdi kurulduktan sonra A'nın temiz satışı,
    B'den bağımsız taze bir A kurulumununkiyle birebir aynı."""
    import perakende_veri.v4.crm.girdi  # noqa: F401
    from perakende_veri.v4.magaza import Olcek
    from perakende_veri.v4.uret import tablolari_uret, yayimla

    _, dunya, ham = tablolari_uret(Olcek.KUCUK, donus_ham=True)
    taze = _satis_ozeti(yayimla(dunya, ham, kirli=False)["satis"])
    sonra = _satis_ozeti(yayimla(kucuk_girdi.dunya, kucuk_girdi.ham, kirli=False)["satis"])
    assert taze == sonra
