"""Müşteri yaşam döngüsü (spec §4): aylık gizli terk, operasyonel
tetikleyiciler, ev mağazası kapanışı ve 2026 LTV gizli gerçeği.

Terk her takvim ayının 1'inde, hayatta olan müşteriler için çekilir::

    p_k = min(terk_p_k × c_k, TERK_P_UST)
    c_k = 1,5  (d ≤ stoksuz_bitis_gun; stoksuzluk günü + 60)
        × 1,2  (son iade d − 90 .. d aralığında)
        × 1,3  (beden_uyumsuz_sayisi ≥ 2)
        × 2    (ev mağazası kapandı ve geçiş yapmadı)

Terk eden müşteri bir daha gelmez (`hayatta` False, `terk_gun` = d).
Bütün çekilişler verilen `rng` ile, müşteri başına sabit sayıda (K) yapılır:
sonuç yalnız (rng, nüfus durumu) ile belirlenir.

2026 LTV (`ltv_2026`), 2025 sonunda hayatta olanlar için B'nin müşteri
modelinin 2026 simülasyonudur (A'nın satış kısıtı yok, tetik yok): 12 aylık
terk çekilişi (ay başında, önce terk) ve hayatta kalınan her ayda
Poisson(hız/12) ziyaret. Analitik beklenti:

    E[ziyaret] = hız/12 × Σ_{m=1..12} (1 − p)^m
    E[harcama] = E[ziyaret] × sepet_ort × fiyat_ort
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import ClassVar

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..magaza import haversine_km
from . import sabitler as S
from .nufus import Nufus

STOKSUZLUK_GUN = S.STOKSUZLUK_GUN
IADE_GUN = S.IADE_GUN
P_UST = S.TERK_P_UST
GECIS_OLASILIGI = S.EV_GECIS_OLASILIGI
AY_SAYISI = 12
_YOK_GUN = -(10**6)


def ay_basi_mi(d: int) -> bool:
    """Gün d (0 = ISINMA_BASLANGIC) ayın 1'i mi."""
    return (a_sabitler.ISINMA_BASLANGIC + timedelta(days=int(d))).day == 1


# ---------------------------------------------------------------------------
# Tetikleyiciler
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class Tetik:
    """Müşteri başına tetik durumu (uzunluk K, nüfus satır sırası).
    `stoksuz_bitis_gun` stoksuzluk penceresinin son günü (−1 yok);
    `iade_sayisi` toplam iade olayı, `son_iade_gun` sonuncunun günü;
    `beden_uyumsuz_sayisi` beden uyumsuz alım sayısı; `ev_kapandi` ev
    mağazası kapandı ve geçmedi (×2); `ev_gecti` kapanışta en yakın
    mağazaya geçti. Nüfus büyüdükçe `uzat(K)` varsayılan satır ekler
    (`gunluk_terk` ve `ev_kapanisi` kendiliğinden çağırır); sütun
    referansı `uzat`'tan sonra yeniden okunmalıdır."""

    SUTUNLAR: ClassVar[dict[str, tuple[type, int]]] = {
        "stoksuz_bitis_gun": (np.int32, -1),
        "iade_sayisi": (np.int32, 0),
        "son_iade_gun": (np.int32, _YOK_GUN),
        "beden_uyumsuz_sayisi": (np.int32, 0),
        "ev_kapandi": (np.bool_, False),
        "ev_gecti": (np.bool_, False),
    }

    K: int = 0
    stoksuz_bitis_gun: np.ndarray = None
    iade_sayisi: np.ndarray = None
    son_iade_gun: np.ndarray = None
    beden_uyumsuz_sayisi: np.ndarray = None
    ev_kapandi: np.ndarray = None
    ev_gecti: np.ndarray = None
    _tampon: dict = field(default_factory=dict, repr=False)

    @classmethod
    def bos(cls, K: int = 0) -> "Tetik":
        t = cls()
        t._tampon = {ad: np.full(max(int(K), 1), v, dtype=tip) for ad, (tip, v) in cls.SUTUNLAR.items()}
        t.K = int(K)
        t._goster()
        return t

    def _goster(self) -> None:
        for ad in self.SUTUNLAR:
            setattr(self, ad, self._tampon[ad][: self.K])

    def uzat(self, K: int) -> None:
        """K satıra büyüt (yeni satırlar varsayılan; kapasite ikiye katlanır)."""
        K = int(K)
        if K <= self.K:
            return
        kap = len(self._tampon["iade_sayisi"])
        if K > kap:
            while kap < K:
                kap *= 2
            for ad, (tip, v) in self.SUTUNLAR.items():
                yeni = np.full(kap, v, dtype=tip)
                yeni[: self.K] = self._tampon[ad][: self.K]
                self._tampon[ad] = yeni
        self.K = K
        self._goster()

    def stoksuzluk(self, k: np.ndarray, d: int) -> None:
        """Gün d'de stoksuzlukla karşılaşan müşteriler: pencere d + 60'a
        uzar (daha uzun bir pencere kısalmaz)."""
        np.maximum.at(self.stoksuz_bitis_gun, np.asarray(k, dtype=np.int64), d + STOKSUZLUK_GUN)

    def iade(self, k: np.ndarray, d: int) -> None:
        """Gün d'de iade yapan müşteriler (tekrarlı indis = birden çok iade)."""
        k = np.asarray(k, dtype=np.int64)
        np.add.at(self.iade_sayisi, k, 1)
        np.maximum.at(self.son_iade_gun, k, d)

    def beden_uyumsuz(self, k: np.ndarray) -> None:
        """Beden uyumsuz alım (tekrarlı indis = birden çok)."""
        np.add.at(self.beden_uyumsuz_sayisi, np.asarray(k, dtype=np.int64), 1)


def terk_carpani(tetik: Tetik, d: int) -> np.ndarray:
    """[K] gün d'nin tetik çarpanı (çarpılır)."""
    c = np.where(tetik.stoksuz_bitis_gun >= d, S.STOKSUZLUK_CARPANI, 1.0)
    c *= np.where(d - tetik.son_iade_gun <= IADE_GUN, S.IADE_CARPANI, 1.0)
    c *= np.where(tetik.beden_uyumsuz_sayisi >= S.BEDEN_UYUMSUZ_ESIGI, S.BEDEN_UYUMSUZ_CARPANI, 1.0)
    c *= np.where(tetik.ev_kapandi, S.EV_KAPANIS_CARPANI, 1.0)
    return c


def terk_olasiligi(nufus: Nufus, tetik: Tetik, d: int) -> np.ndarray:
    """[K] gün d'nin aylık terk olasılığı: terk_p × çarpan, en çok 0,95."""
    tetik.uzat(nufus.K)
    return np.minimum(nufus.terk_p * terk_carpani(tetik, d), P_UST)


def gunluk_terk(rng_gun, nufus: Nufus, tetik: Tetik, d: int, ay_basi: bool) -> np.ndarray:
    """Gün d'nin terk çekilişi (yalnız ay başında; değilse çekiliş yok).
    Yeni terk edenlerin [K] maskesini döndürür; `nufus.hayatta` ve
    `terk_gun`'a yazar."""
    tetik.uzat(nufus.K)
    if not ay_basi:
        return np.zeros(nufus.K, dtype=bool)
    p = terk_olasiligi(nufus, tetik, d)
    u = rng_gun.random(nufus.K)
    terk = nufus.hayatta & (u < p)
    nufus.hayatta[terk] = False
    nufus.terk_gun[terk] = d
    return terk


def ev_kapanisi(rng, nufus: Nufus, tetik: Tetik, girdi, m: int, d: int) -> np.ndarray:
    """Fiziksel mağaza m gün d'de kapanır: hayatta olan ev müşterileri,
    aynı ilde d'de açık başka fiziksel mağaza varsa en yakınına (mağaza
    koordinatları, haversine) 0,6 olasılıkla geçer (`ev_magaza` değişir,
    `ev_gecti`). Geçmeyenler (ilde açık mağaza yoksa hepsi): online payı ×2
    (en çok 1), `ev_kapandi` True (terk ×2). Geçenlerin indislerini
    döndürür."""
    tetik.uzat(nufus.K)
    mb = nufus.magaza
    assert m != mb.onl, "ONL kapanmaz"
    ev = np.flatnonzero(nufus.hayatta & (nufus.ev_magaza == m))
    tum = np.arange(mb.M)
    acik = (tum != mb.onl) & (tum != m) & (mb.acilis_gun <= d) & (mb.kapanis_gun > d)
    aday = acik & (mb.il == mb.il[m])
    u = rng.random(len(ev))
    if aday.any():
        mag = girdi.dunya.magazalar
        lat, lon = mag["enlem"].to_numpy(dtype=float), mag["boylam"].to_numpy(dtype=float)
        uzak = np.where(aday, haversine_km(lat[m], lon[m], lat, lon), np.inf)
        hedef = int(np.argmin(uzak))
        gec = u < GECIS_OLASILIGI
    else:
        hedef = -1
        gec = np.zeros(len(ev), dtype=bool)
    gecen, kalan = ev[gec], ev[~gec]
    if len(gecen):
        nufus.ev_magaza[gecen] = hedef
        tetik.ev_gecti[gecen] = True
    nufus.online_payi[kalan] = np.minimum(nufus.online_payi[kalan] * S.EV_KAPANIS_ONLINE_CARPANI, 1.0)
    nufus.ev_degisti()
    tetik.ev_kapandi[kalan] = True
    return gecen


# ---------------------------------------------------------------------------
# 2026 LTV (gizli gerçek)
# ---------------------------------------------------------------------------


def ltv_2026(rng, nufus: Nufus, tetik: Tetik, fiyat_ort: np.ndarray) -> pd.DataFrame:
    """2025 sonu nüfusundan 2026 LTV gizli gerçeği (müşteri başına bir satır,
    `musteri_id` = k). `fiyat_ort` [K]: müşterinin pencere içi ortalama
    ödenen birim fiyatı (B'nin fişlerinden; Görev 7). Tetikler 2026'ya
    taşınmaz (`tetik` yalnız arayüz tutarlılığı için).

    Sütunlar: `hayatta_olasiligi` (2025 sonu hayatta 1, değilse 0),
    `hayatta_kalma_2026` (analitik, 12 ayın (1 − p)^m ortalaması),
    `beklenen_ziyaret_2026`, `beklenen_harcama_2026` (analitik),
    `gerceklesen_ziyaret_2026`, `gerceklesen_harcama_2026` (tek çekiliş;
    ziyaret başına sepet_ort × fiyat_ort), `geri_gelecek_2026`
    (gerçekleşen ziyaret > 0), `terk_ay_2026` (1–12; 0 = 2026'da terk yok
    ya da zaten ölü). Ölü müşterilerde bütün değerler 0 / False."""
    K = nufus.K
    tetik.uzat(K)
    fiyat_ort = np.asarray(fiyat_ort, dtype=float)
    assert fiyat_ort.shape == (K,), f"fiyat_ort uzunluğu {fiyat_ort.shape} ≠ {K}"
    h = nufus.hayatta.copy()
    p = np.where(h, nufus.terk_p, 0.0)
    hiz_ay = np.where(h, nufus.ziyaret_hizi, 0.0) / AY_SAYISI
    birim = np.where(h, nufus.sepet_ort * fiyat_ort, 0.0)

    q = 1.0 - p
    sag_top = np.zeros(K)
    qm = np.ones(K)
    for _ in range(AY_SAYISI):
        qm = qm * q
        sag_top += qm
    hayatta_kalma = np.where(h, sag_top / AY_SAYISI, 0.0)
    beklenen_ziyaret = hiz_ay * sag_top

    canli = h.copy()
    ziyaret = np.zeros(K, dtype=np.int64)
    terk_ay = np.zeros(K, dtype=np.int8)
    for ay in range(1, AY_SAYISI + 1):
        u = rng.random(K)
        olur = canli & (u < p)
        canli &= ~olur
        terk_ay[olur] = ay
        ziyaret += rng.poisson(np.where(canli, hiz_ay, 0.0))

    return pd.DataFrame({
        "musteri_id": np.arange(K, dtype=np.int64),
        "hayatta_olasiligi": h.astype(float),
        "hayatta_kalma_2026": hayatta_kalma,
        "beklenen_ziyaret_2026": beklenen_ziyaret,
        "beklenen_harcama_2026": beklenen_ziyaret * birim,
        "gerceklesen_ziyaret_2026": ziyaret,
        "gerceklesen_harcama_2026": ziyaret * birim,
        "geri_gelecek_2026": ziyaret > 0,
        "terk_ay_2026": terk_ay,
    })
