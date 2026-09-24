"""Dağıtım motoru: koli kuralları, cover önceliği, açık kapasite.

Depodan mağazalara sevkiyat iki fazda kurulur: önce kapalı koli (bütün
5 bedeni birden taşıyan `sabitler.KOLI` demeti), sonra açık (beden bazlı,
tek tek) adet. Her iki faz da aynı öncelik mantığını kullanan bir `heapq`
ile ilerler: en öncelikli aday sevk edilir, adaylığı yeniden değerlendirilir,
hâlâ uygunsa yeni anahtarla geri itilir. Bir öğe heap'te dururken paylaşılan
kısıt (mağaza kalan kapasitesi) başka bir sevkiyatla değişmiş olabileceğinden,
her pop'ta adaylık yeniden doğrulanır — artık uygun değilse sessizce atılır
(bayat giriş).

`kural.ad == "C"`, A ve B kurallarının aynı anda sağlanmasıdır (plan
§Task 6, madde 5: "C = seçilen A ve B birlikte").
"""

import heapq
from dataclasses import dataclass

import numpy as np

from . import sabitler
from .depo import Depo
from .dunya import Dunya

_KOLI = np.array(sabitler.KOLI, dtype=np.int64)


@dataclass(frozen=True)
class KoliKurali:
    ad: str                 # "A" | "B" | "C" | "yok"
    alfa: float = 0.6       # A: Σn ≥ alfa × 8
    beta: int = 2           # A: her bedende (koli − n) < beta
    gama: float = 0.6       # B: Σ min(koli, n) / 8 ≥ gama


def koli_uygun(n: np.ndarray, kural: KoliKurali) -> bool:
    """n: int[5], beden_sira 1..5 sırasında o (mağaza, option) ihtiyacı."""
    n = np.asarray(n)

    def _a() -> bool:
        return bool(n.sum() >= kural.alfa * sabitler.KOLI_ADET) and bool(
            (_KOLI - n).max() < kural.beta
        )

    def _b() -> bool:
        return bool(np.minimum(_KOLI, n).sum() / sabitler.KOLI_ADET >= kural.gama)

    if kural.ad == "yok":
        return False
    if kural.ad == "A":
        return _a()
    if kural.ad == "B":
        return _b()
    if kural.ad == "C":
        return _a() and _b()
    raise ValueError(f"Bilinmeyen koli kuralı: {kural.ad}")


@dataclass
class Sevk:
    gelen: np.ndarray       # int64[H]  hücre başına gönderilen
    koli_sayisi: int
    acik_adet: int


def _kalan_kapasite(dunya: Dunya, stok: np.ndarray) -> np.ndarray:
    """int[M]: mağaza kapasitesi eksi mağaza stok toplamı, 0'ın altına inmez."""
    hucre_mag = np.searchsorted(dunya.magazalar, dunya.hucre_magaza)
    magaza_stok = np.zeros(len(dunya.magazalar), dtype=np.int64)
    np.add.at(magaza_stok, hucre_mag, stok)
    return np.maximum(dunya.kapasite - magaza_stok, 0)


def dagit(
    ihtiyac: np.ndarray,
    ongoru: np.ndarray,
    stok: np.ndarray,
    depo: Depo,
    dunya: Dunya,
    kural: KoliKurali,
    acik_kapasite: int,
    oncelik: str = "cover",
) -> Sevk:
    OC = dunya.oc_hucre.shape[0]
    H = len(dunya.hucre_magaza)

    n = np.array(ihtiyac, dtype=np.int64, copy=True)
    gelen = np.zeros(H, dtype=np.int64)
    kalan_kap = _kalan_kapasite(dunya, stok)

    oc_hucre = dunya.oc_hucre
    oc_opt = dunya.oc_opt
    oc_mag = dunya.oc_mag
    oc_magaza = dunya.oc_magaza
    oc_option = dunya.oc_option

    def _oc_deger(oc: int) -> tuple[float, float]:
        """(stok_oc, gelen_oc): OC'nin 5 bedeninin toplamı."""
        hucreler = oc_hucre[oc]
        return float(stok[hucreler].sum()), float(gelen[hucreler].sum())

    def _cover(oc: int, ek: int) -> float:
        stok_oc, gelen_oc = _oc_deger(oc)
        return (stok_oc + gelen_oc + ek) / max(float(ongoru[oc]), 0.1)

    def _anahtar_oc(oc: int, ek: int) -> tuple:
        if oncelik == "cover":
            birincil = _cover(oc, ek)
        elif oncelik == "ihtiyac":
            birincil = -float(n[oc].sum())
        elif oncelik == "esit":
            _, gelen_oc = _oc_deger(oc)
            birincil = gelen_oc
        else:
            raise ValueError(f"Bilinmeyen öncelik: {oncelik}")
        if oncelik == "esit":
            return (birincil, _cover(oc, ek), oc_magaza[oc], oc_option[oc])
        return (birincil, oc_magaza[oc], oc_option[oc])

    koli_sayisi = 0
    acik_adet = 0

    # --- Koli fazı -----------------------------------------------------
    if kural.ad != "yok":

        def koli_uygun_mu(oc: int) -> bool:
            return (
                koli_uygun(n[oc], kural)
                and depo.koli[oc_opt[oc]] > 0
                and kalan_kap[oc_mag[oc]] >= sabitler.KOLI_ADET
            )

        heap: list[tuple[tuple, int]] = []
        for oc in range(OC):
            if koli_uygun_mu(oc):
                heapq.heappush(heap, (_anahtar_oc(oc, sabitler.KOLI_ADET), oc))

        while heap:
            _anahtar, oc = heapq.heappop(heap)
            if not koli_uygun_mu(oc):
                continue  # bayat giriş: paylaşılan kısıt değişti
            hucreler = oc_hucre[oc]
            gelen[hucreler] += _KOLI
            n[oc] = np.maximum(n[oc] - _KOLI, 0)
            depo.koli[oc_opt[oc]] -= 1
            kalan_kap[oc_mag[oc]] -= sabitler.KOLI_ADET
            koli_sayisi += 1
            if koli_uygun_mu(oc):
                heapq.heappush(heap, (_anahtar_oc(oc, sabitler.KOLI_ADET), oc))

    # --- Açık fazı -------------------------------------------------------
    def acik_uygun_mu(oc: int, beden: int) -> bool:
        return (
            n[oc, beden] > 0
            and depo.acik[oc_opt[oc], beden] > 0
            and kalan_kap[oc_mag[oc]] >= 1
        )

    def _anahtar_acik(oc: int, beden: int) -> tuple:
        return _anahtar_oc(oc, 1) + (beden,)

    heap2: list[tuple[tuple, int, int]] = []
    for oc in range(OC):
        for beden in range(5):
            if acik_uygun_mu(oc, beden):
                heapq.heappush(heap2, (_anahtar_acik(oc, beden), oc, beden))

    while heap2 and acik_adet < acik_kapasite:
        _anahtar, oc, beden = heapq.heappop(heap2)
        if not acik_uygun_mu(oc, beden):
            continue
        hucre = oc_hucre[oc, beden]
        gelen[hucre] += 1
        n[oc, beden] -= 1
        depo.acik[oc_opt[oc], beden] -= 1
        kalan_kap[oc_mag[oc]] -= 1
        acik_adet += 1
        if acik_uygun_mu(oc, beden):
            heapq.heappush(heap2, (_anahtar_acik(oc, beden), oc, beden))

    return Sevk(gelen=gelen, koli_sayisi=koli_sayisi, acik_adet=acik_adet)
