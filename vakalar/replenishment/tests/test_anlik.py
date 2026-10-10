"""`replenishment.anlik`: karar anı Basit öngörüsü motorun `Gorunum`'ü üstünde.

KÜÇÜK dünyada geçmiş kaydıyla bir Lumoda koşusu (oyun başına dek ~5 sn): oyunun ilk
pazartesisi `t`'nin ve iki hafta sonrasının görünümü yakalanır. Sonrakinin geçmiş
dizileri `t`'nin gerçek geleceğini taşır; `t`'nin görünümü onlarla uzatılınca
(ve gelecek satırlar ayrıca bozulunca) öngörü değişmemelidir.
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest
from perakende_analitik.carpanlar import Carpanlar

from replenishment import anlik, kaynak, motor
from replenishment.sabitler import OYUN_BAS


class _Bitti(Exception):
    pass


class _Yakala:
    gecmis_gerekir = True

    def __init__(self, gunler, temel):
        self.gunler, self.temel, self.g = set(gunler), temel, {}

    def __call__(self, g):
        if g.gun in self.gunler:
            self.g[g.gun] = g
            if len(self.g) == len(self.gunler):
                raise _Bitti
        return self.temel(g)


@pytest.fixture(scope="module")
def kosu():
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.politika import Politikalar

    w = motor.dunya("kucuk")
    t0 = pd.Timestamp(w.takvim["tarih"].iloc[0])
    t = int((pd.Timestamp(OYUN_BAS) - t0).days)
    y = _Yakala((t, t + 14), motor.lumoda("replenishment"))
    with pytest.raises(_Bitti):
        simule_et(w, Politikalar(replenishment=y), kayit_talep=False, gecmis_kaydi=True)
    return w, kaynak.harita_kur(w), y.g[t], y.g[t + 14]


def test_anlik_gelecegi_gormez(kosu):
    """`t`'nin görünümü gerçek gelecekle (iki hafta satış, stok, fiyat kaydı,
    fotoğraflar) uzatılınca ve gelecek satırlar bozulunca öngörü birebir aynı."""
    w, h, g, sonra = kosu
    t = g.gun
    o = anlik.karar_ani_ongoru(g, Carpanlar(), h)
    uzun = dataclasses.replace(
        g, satis_gecmisi=sonra.satis_gecmisi, stoklu_gecmisi=sonra.stoklu_gecmisi,
        satis_oncesi_gecmisi=sonra.satis_oncesi_gecmisi, fiyat_gecmisi=sonra.fiyat_gecmisi,
        stok_fotograflari=sonra.stok_fotograflari)
    assert len(uzun.satis_gecmisi) == t + 14
    assert any(p[0] > t for p in uzun.stok_fotograflari)
    assert np.array_equal(o, anlik.karar_ani_ongoru(uzun, Carpanlar(), h))

    bozuk = dataclasses.replace(
        uzun, satis_gecmisi=np.concatenate([g.satis_gecmisi, np.full_like(sonra.satis_gecmisi[t:], 99)]),
        stoklu_gecmisi=np.concatenate([g.stoklu_gecmisi, ~sonra.stoklu_gecmisi[t:]]),
        satis_oncesi_gecmisi=np.concatenate([g.satis_oncesi_gecmisi,
                                             np.zeros_like(sonra.satis_oncesi_gecmisi[t:])]))
    assert np.array_equal(o, anlik.karar_ani_ongoru(bozuk, Carpanlar(), h))


def test_ongoru_brut_artı_kayip(kosu):
    """Öngörü = son 7 günün fiziksel brüt satışı + Basit kaybı (≥ 0, sonlu); online
    OC 0; kayıp gerçekten eklenir (oyun başında stoksuz hücre-günler var)."""
    w, h, g, _ = kosu
    t = g.gun
    o = anlik.karar_ani_ongoru(g, Carpanlar(), h)
    S = np.asarray(g.satis_gecmisi)
    brut = np.bincount(h.oc, weights=np.where(h.hucre_online, 0, S[t - 7:t].sum(0)), minlength=len(h.oc_magaza))
    assert o.shape == (len(h.oc_magaza),) and np.isfinite(o).all()
    assert (o[h.oc_online] == 0).all()
    assert (o >= brut - 1e-9).all() and o.sum() > brut.sum()


def test_kayip_yalniz_son_haftadan_ve_stoksuz_gunden(kosu):
    """Kayıp tablosu `[t−28, t)` satırlarıdır; stoklu satırın kaybı 0; öngörüye yalnız
    `[t−7, t−1]` girer."""
    w, h, g, _ = kosu
    kurucu = anlik.GunlukKurucu(w)
    t = g.gun
    bas = t - anlik.PENCERE_GUN
    S, F = np.asarray(g.satis_gecmisi), np.asarray(g.stoklu_gecmisi)
    aktif = ~h.hucre_online & ((S[bas:t] > 0).any(0) | F[bas:t].any(0))
    gunluk = kurucu(g, np.unique(h.hucre_option[aktif]), bas)
    tarih = pd.Timestamp(g.tarih)
    assert gunluk["tarih"].min() >= tarih - pd.Timedelta(days=anlik.PENCERE_GUN)
    assert gunluk["tarih"].max() < tarih
    assert not h.hucre_online[gunluk["hucre"]].any()
    k = anlik.karar_ani_kaybi(gunluk, tarih, Carpanlar())
    durum = gunluk.set_index(["hucre", "tarih"])["durum"]
    stoklu = (durum.reindex(pd.MultiIndex.from_frame(k[["hucre", "tarih"]])) == "stoklu").to_numpy()
    assert (k["kayip"].to_numpy()[stoklu] == 0).all() and (k["kayip"] >= 0).all()
    son = k[k["tarih"] >= tarih - pd.Timedelta(days=7)]
    S7 = np.where(h.hucre_online, 0, S[t - 7:t].sum(0))
    beklenen = np.bincount(h.oc, weights=S7, minlength=len(h.oc_magaza)) + np.bincount(
        h.oc[son["hucre"]], weights=son["kayip"], minlength=len(h.oc_magaza))
    assert np.allclose(anlik.karar_ani_ongoru(g, Carpanlar(), h, kurucu=kurucu), beklenen)


def test_gecmis_kaydi_ister(kosu):
    w, h, g, _ = kosu
    with pytest.raises(ValueError, match="gecmis_kaydi=True"):
        anlik.karar_ani_ongoru(dataclasses.replace(g, satis_oncesi_gecmisi=None), Carpanlar(), h)
