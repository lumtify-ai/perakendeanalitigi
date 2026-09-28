"""B'nin günlük döngüsü (spec §3, §4): bütün günleri gün 0'dan (ısınma
başı) D'ye koşar, sonunda 2026 LTV gizli gerçeğini üretir.

Gün d'nin sırası::

    1. katılış          nufus.katilis_sayisi + ekle (kayıt günü d)
    2. terk             ayın 1'inde yasam.gunluk_terk (önce terk: o gün ölen
                        müşteri o gün gelmez). Katılış terkten önce olduğundan
                        ayın 1'inde katılan müşteri aynı gün terk edebilir
                        (hiç fişi olmadan; aylık olasılıkla, bilinçli)
    3. mağaza olayları  kapanış günü (magaza_olay "kapanis", olay_tarihi)
                        yasam.ev_kapanisi; açılış ve tadilatın B'de ayrı adımı
                        yok (satış yoksa fiş yok; açılış dalgası katılışta)
    4. gun_ayristir     satış fişleri (Görev 5)
    5. islem_indirimi_yerlestir, iade_bagla, bos_ziyaret (Görev 6)
    6. kart okutma      aşağıda

**Kart okutma.** Gün d'nin her satış fişi: fiziksel mağazada müşterinin
`kart_olasiligi`'yla kimlikli (sayaç üreteci `crm_uretici(d, "kart")`,
fiziksel mağaza satış fişi başına bir çekiliş, fiş_id sırasıyla), ONL'de
hep kimlikli (çekiliş yok).
İade fişi: ONL hep; mağazada orijinal satış fişlerinden biri kimlikliyse
kimlikli (fiş (mağaza, müşteri) başına birden çok orijinali toplayabilir).
Müşterinin ilk kimlikli olayında `gorunur_mu` True, `gorunur_gun` = d.
Anonim fişte de gerçek sahip `kayit` `fis.musteri`'de gizli kalır;
yayımlanan müşteri kimliği yalnız kartlı fişte (Görev 13 maskeler). Kart
bayrağı `CrmHam.kart[fis_id]` (fis_id = `fis` tablosunun satır sırası).

**Terk ve iade.** Terk eden müşterinin terk gününden sonra satış fişi ve
boş ziyareti olmaz; A'nın iadesi satışın 7 (ONL 10) gün sonrasında
kesin olarak doğduğundan, terkten hemen önceki alışverişin iadesi terkten
sonra gelebilir (iade fişi, orijinali terkten önce).

**Kapalı mağaza.** Açılış öncesi, kapanış sonrası ve tadilatta A'nın
satışı yok, satış fişi de yok. A kapanıştan (ya da tadilat başından) önceki
satışın iadesini aynı hücreye yazdığından o iade fişi kapalı mağaza-günde
görünür (Görev 6, Review Focus 2); tutarlılık bunu gerektirir.

**2026 LTV.** `fiyat_ort[k]` müşterinin pencere (2023-01-01 – 2025-12-31)
içi satış satırlarında ödenen ortalama birim fiyat (Σ tutar / Σ adet);
satırı olmayan müşteride arketipinin medyanı (arketipte hiç yoksa bütün
medyan). Pencere koşulmamışsa (kısa `gun_sayisi`) bütün koşulan günler.
Rastgelelik `crm_uretici(D, "ltv")`.

Rastgelelik: başlangıç tabanı `default_rng(tohum)`; katılış
`crm_uretici(d, "katilis")`; terk ve kapanış
`crm_alt_ureticiler(d, "terk", ("terk", "kapanis"))`; kart
`crm_uretici(d, "kart")`; ayrıştırma ve Görev 6 kendi akışları. Hepsi
gün sayaçlı: ilk N günün sonucu `gun_sayisi` = N koşusuyla birebir aynıdır.
"""

import hashlib
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..takvim import gun_indisi
from . import sabitler as S
from .ayristir import Kayit, gun_ayristir
from .iade import bos_ziyaret, iade_bagla, islem_indirimi_yerlestir
from .girdi import Girdi
from .nufus import Nufus, katilis_sayisi, nufus_baslat
from .rastgele import crm_alt_ureticiler, crm_uretici
from .yasam import Tetik, ay_basi_mi, ev_kapanisi, gunluk_terk, ltv_2026

TERK_ADIMLARI = ("terk", "kapanis")   # yeni adım SONA
GECIKME_MAGAZA = a_sabitler.IADE_GECIKME_MAGAZA
GECIKME_ONLINE = a_sabitler.IADE_GECIKME_ONLINE


@dataclass(eq=False)
class CrmHam:
    """B'nin ham sonucu. `kayit` fiş, fiş satırı ve boş ziyaret parçaları
    (`tablo(ad)` DataFrame; `fis`'e `kart` sütunu eklenir); `kart` [fiş]
    kimlikli mi (fis_id indisli); `ltv` 2026 LTV gizli gerçeği;
    `fiyat_ort` [K] LTV'nin birim fiyatı; `D` koşulan gün sayısı; `sure`
    adım süreleri (sn)."""

    nufus: Nufus
    tetik: Tetik
    kayit: Kayit
    kart: np.ndarray
    ltv: pd.DataFrame
    fiyat_ort: np.ndarray
    D: int
    tohum: int
    sure: dict

    def tablo(self, ad: str) -> pd.DataFrame:
        df = self.kayit.tablo(ad)
        if ad == "fis":
            assert (df["fis_id"].to_numpy() == np.arange(len(df))).all()
            df["kart"] = self.kart
        return df


class _KartTampon:
    """fis_id indisli, büyüyen kart bayrağı."""

    def __init__(self):
        self.a = np.zeros(1 << 16, dtype=bool)
        self.n = 0

    def ekle(self, fis_id: np.ndarray, deger: np.ndarray) -> None:
        if not len(fis_id):
            return
        assert fis_id[0] == self.n and (np.diff(fis_id) == 1).all()
        son = self.n + len(fis_id)
        if son > len(self.a):
            kap = len(self.a)
            while kap < son:
                kap *= 2
            yeni = np.zeros(kap, dtype=bool)
            yeni[: self.n] = self.a[: self.n]
            self.a = yeni
        self.a[self.n:son] = deger
        self.n = son

    @property
    def dizi(self) -> np.ndarray:
        return self.a[: self.n].copy()


def _birlestir(parcalar: list[dict], sutunlar) -> dict:
    return {k: np.concatenate([p[k] for p in parcalar]) if parcalar else np.zeros(0, dtype=np.int64)
            for k in sutunlar}


def kart_okut(d: int, nufus: Nufus, kayit: Kayit, kart: _KartTampon, onl: int) -> None:
    """Gün d'nin fişlerine kart bayrağı (modül docstring'i); `gorunur_*`."""
    fis = _birlestir(kayit.gun_parcalari("fis", d), ("fis_id", "magaza", "musteri", "tip"))
    if not len(fis["fis_id"]):
        return
    fid = fis["fis_id"].astype(np.int64)
    sira = np.argsort(fid, kind="stable")
    fid = fid[sira]
    mag = fis["magaza"][sira].astype(np.int64)
    mus = fis["musteri"][sira].astype(np.int64)
    tip = fis["tip"][sira]
    deger = np.zeros(len(fid), dtype=bool)

    satis = tip == 0
    deger[satis & (mag == onl)] = True
    fs = satis & (mag != onl)
    u = crm_uretici(d, "kart", kayit.tohum).random(int(fs.sum()))
    deger[fs] = u < nufus.kart_olasiligi[mus[fs]]

    iade = tip == 1
    deger[iade & (mag == onl)] = True
    im = iade & (mag != onl)
    if im.any():
        sat = _birlestir(kayit.gun_parcalari("fis_satir", d), ("fis_id", "orijinal_satir", "adet"))
        r = sat["adet"] < 0
        r_fis = sat["fis_id"][r].astype(np.int64)
        r_orj = sat["orijinal_satir"][r].astype(np.int64)
        orj_parca = []
        for g in sorted({d - GECIKME_MAGAZA, d - GECIKME_ONLINE}):
            if g >= 0:
                orj_parca += kayit.gun_parcalari("fis_satir", g)
        orj = _birlestir(orj_parca, ("satir_id", "fis_id"))
        o = np.argsort(orj["satir_id"], kind="stable")
        sid, ofis = orj["satir_id"][o], orj["fis_id"][o].astype(np.int64)
        p = np.minimum(np.searchsorted(sid, r_orj), max(len(sid) - 1, 0))
        assert len(sid) and (sid[p] == r_orj).all(), f"gün {d}: iadenin orijinal satırı bulunamadı"
        # orijinal fişler bu günden önce: kart bayrağı tamponda
        k_orj = kart.a[ofis[p]].astype(np.int64)
        pos = np.searchsorted(fid, r_fis)
        var = np.zeros(len(fid), dtype=np.int64)
        np.maximum.at(var, pos, k_orj)
        deger[im] = var[im] > 0

    kart.ekle(fid, deger)
    kimlikli = np.unique(mus[deger])
    yeni = kimlikli[~nufus.gorunur_mu[kimlikli]]
    nufus.gorunur_mu[yeni] = True
    nufus.gorunur_gun[yeni] = d


def _kapanislar(girdi: Girdi, M_idx: dict) -> dict[int, list[int]]:
    """gün → o gün kapanan mağaza indisleri (A'nın `magaza_olay`'ı)."""
    out: dict[int, list[int]] = {}
    for r in girdi.dunya.magaza_olay.itertuples():
        if r.olay == "kapanis":
            out.setdefault(gun_indisi(r.olay_tarihi), []).append(M_idx[r.magaza_id])
    return {g: sorted(v) for g, v in out.items()}


def fiyat_ortalamasi(nufus: Nufus, kayit: Kayit, D: int) -> np.ndarray:
    """[K] ödenen ortalama birim fiyat (modül docstring'i); hepsi sonlu."""
    from ..tablolar import pencere

    K = nufus.K
    bas, son = pencere()
    gunler = range(max(bas, 0), min(son + 1, D))
    if not any(kayit.gun_parcalari("fis_satir", d) for d in gunler):
        gunler = range(D)
    tutar = np.zeros(K)
    adet = np.zeros(K)
    for d in gunler:
        fis = _birlestir(kayit.gun_parcalari("fis", d), ("fis_id", "musteri"))
        if not len(fis["fis_id"]):
            continue
        o = np.argsort(fis["fis_id"])
        fid, mus = fis["fis_id"][o], fis["musteri"][o].astype(np.int64)
        for p in kayit.gun_parcalari("fis_satir", d):
            s = p["adet"] > 0
            if not s.any():
                continue
            k = mus[np.searchsorted(fid, p["fis_id"][s])]
            tutar += np.bincount(k, p["tutar"][s], minlength=K)
            adet += np.bincount(k, p["adet"][s].astype(float), minlength=K)
    var = adet > 0
    assert var.any(), "hiç satış satırı yok"
    f = np.full(K, np.nan)
    f[var] = tutar[var] / adet[var]
    genel = float(np.median(f[var]))
    for a in range(len(S.ARKETIPLER)):
        s = nufus.arketip == a
        v = s & var
        f[s & ~var] = float(np.median(f[v])) if v.any() else genel
    assert np.isfinite(f).all() and (f > 0).all()
    return f


def crm_simule_et(girdi: Girdi, tohum: int = S.CRM_TOHUM, gun_sayisi: int | None = None,
                  ilerleme=None) -> CrmHam:
    """Gün 0'dan D'ye (ya da `gun_sayisi`) B'nin bütün günlük döngüsü
    (modül docstring'i), sonunda 2026 LTV. `ilerleme(d, nufus, kayit)`
    verilirse her günün sonunda çağrılır (ölçüm araçları için; süreye
    sayılmaz)."""
    D = girdi.D if gun_sayisi is None else int(gun_sayisi)
    assert 0 < D <= girdi.D
    sure: dict = {}

    def olc(ad, t0):
        simdi = time.perf_counter()
        sure[ad] = sure.get(ad, 0.0) + simdi - t0
        return simdi

    t = time.perf_counter()
    nufus = nufus_baslat(np.random.default_rng(tohum), girdi)
    tetik = Tetik.bos(nufus.K)
    kayit = Kayit(tohum)
    kart = _KartTampon()
    mb = nufus.magaza
    M_idx = {mid: i for i, mid in enumerate(girdi.dunya.magazalar["magaza_id"])}
    kapanis = _kapanislar(girdi, M_idx)
    t = olc("a nufus_baslat", t)

    for d in range(D):
        rng = crm_uretici(d, "katilis", tohum)
        n = katilis_sayisi(rng, girdi, nufus, d)
        if n.sum():
            nufus.ekle(rng, int(n.sum()), np.repeat(np.arange(len(n)), n), kayit_gun=d)
        t = olc("b katilis", t)

        ay_basi = ay_basi_mi(d)
        if ay_basi or d in kapanis:
            akis = crm_alt_ureticiler(d, "terk", TERK_ADIMLARI, tohum)
            gunluk_terk(akis["terk"], nufus, tetik, d, ay_basi)
            t = olc("c terk", t)
            for m in kapanis.get(d, []):
                ev_kapanisi(akis["kapanis"], nufus, tetik, girdi, m, d)
            t = olc("d magaza olayi", t)

        t0 = t
        gun_ayristir(d, girdi, nufus, tetik, kayit)
        islem_indirimi_yerlestir(d, girdi, nufus, kayit)
        iade_bagla(d, girdi, nufus, tetik, kayit)
        bos_ziyaret(d, girdi, nufus, tetik, kayit)
        t = time.perf_counter()
        sure["e ayristir+gorev6"] = sure.get("e ayristir+gorev6", 0.0) + t - t0

        kart_okut(d, nufus, kayit, kart, mb.onl)
        t = olc("f kart", t)
        if ilerleme is not None:
            ilerleme(d, nufus, kayit)
            t = time.perf_counter()

    tetik.uzat(nufus.K)
    fiyat = fiyat_ortalamasi(nufus, kayit, D)
    t = olc("g fiyat_ort", t)
    ltv = ltv_2026(crm_uretici(D, "ltv", tohum), nufus, tetik, fiyat)
    olc("h ltv", t)
    for ad, v in kayit.sure.items():
        sure[f"  {ad}"] = v
    return CrmHam(nufus=nufus, tetik=tetik, kayit=kayit, kart=kart.dizi, ltv=ltv, fiyat_ort=fiyat,
                  D=D, tohum=tohum, sure=sure)


def crm_ozeti(ham: CrmHam) -> str:
    """Bütün ham sonucun sha256'sı (determinizm denetimi): fiş (kart
    dahil), fiş satırı, boş ziyaret, nüfus ve tetik sütunları, LTV."""
    h = hashlib.sha256()

    def ekle(ad, a):
        a = np.ascontiguousarray(np.asarray(a))
        h.update(f"{ad}:{a.dtype}:{a.shape}".encode())
        h.update(a.tobytes())

    for ad in ("fis", "fis_satir", "bos_ziyaret"):
        df = ham.tablo(ad)
        for c in df.columns:
            ekle(f"{ad}.{c}", df[c].to_numpy())
    for c in Nufus.SUTUNLAR:
        ekle(f"nufus.{c}", getattr(ham.nufus, c))
    for c in Tetik.SUTUNLAR:
        ekle(f"tetik.{c}", getattr(ham.tetik, c))
    for c in ham.ltv.columns:
        ekle(f"ltv.{c}", ham.ltv[c].to_numpy())
    return h.hexdigest()
