"""Kısıtlı dağıtım: önce açık adet, sonra tam koli (spec §3.4–3.5, §0 karar 10).

Kolun hücre isteği (`ihtiyac.bedene_bol`, [C]) gölge defterin stoğuyla
gönderime çevrilir. **Koli açılmaz:** depoda stok ya kapalı kolide ya açık
adettir; kolideki mal mağazaya yalnız tam koli olarak gider.

  0. Maske: `maske_c` dışındaki hücreye hiçbir şey gitmez (`motor_maskesi`:
     motorun sıfırlayacağı hücre; sıfırlanan istek deftere "giriş" diye
     dönerdi).
  1. **Açık aşama.** SKU başına açık stok ve haftalık açık toplama tavanı
     (`tavan`, adet; ∞ = sınırsız) yettiğince, adet adet, önceliğe göre.
  2. **Koli aşaması.** Kalan ihtiyaçta (mağaza, option) başına koli kuralı
     (`koli_uygun`) geçerse ve option'ın kapalı kolisi varsa tam koli,
     önceliğe göre; her koliden sonra kalan ihtiyaç yeniden değerlendirilir.
     **Koli tavana hiç sayılmaz, tavan sonlu olsa da** (Ruling R16; tavan
     haftalık açık toplamanın sınırıdır, v2 anlamı); koli aşamasının sınırı
     yalnız kapalı koli stoğu. Kolinin içerik bedenlerinden birinin hücresi maskeliyse
     o çifte koli gitmez.

Düşüm `dagit` içinde yapılır (`defter.dus_acik`, `defter.dus_koli`).

**Kısıtsız** (`KISITSIZ`, tavan ∞): bütün stok açık gibi davranır (kapalı
kolinin adedi de adet adet gider; defter gerektiği kadar koliyi kendisi açar,
yalnız sayım için); bölmeyi yine `oncelik` yapar. v4'ün tek adet sevkiyatı.

**Öncelik** (her iki aşamada sıra; (mağaza, option) çifti = OC):

    cover     (raf + yolda + giden + ek) / max(öngörü, 0,1) en küçük çift önce;
              ek açıkta 1, kolide koli adedi (v2)
    ihtiyac   en büyük kalan ihtiyaç (çiftin bedenleri toplamı) önce
    esit      en az giden adet önce, eşitlikte cover
    orantili  açıkta: SKU içinde isteğe orantılı en büyük kalan (motorun
              `orantili_kes` aritmetiğiyle aynı), tavan aşılırsa bütün
              hücrelerde aynı kuralla tavana kesilir; kolide: D'Hondt
              (koli aşaması başındaki ihtiyaç / (giden koli + 1) en büyük önce),
              tam koliyle orantılı bölmenin karşılığı

Eşitlikte küçük OC indisi (çiftler `kaynak.harita_kur` sırasında: mağaza,
option artan). Açıkta seçilen çiftin içinde adet, `(giden + 1) / istek`'i en
küçük bedene gider (eşitlikte beden sırası): bedenler isteğe orantılı dolar.
Bir çiftin anahtarı yalnız kendi gönderimiyle değişir; paylaşılan SKU / koli
stoğu çift sıradan çıktığında denetlenir (heap girdisi bayatlamaz).

`motor_maskesi(g)`: motorun replenishment isteğini sıfırlamadığı hücreler
(`perakende_veri/v4/motor/dongu.py`, adım 10), yalnız açık alanlardan.

Bu modül `perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz
(`tests/test_sizinti.py`); dünyanın yalnız açık alanlarını okur (`hucre_*`,
`sku_option`, `optionlar`, `urunler`, `paketler`).
"""

import heapq
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .defter import beden_skulari, koli_icerigi

Oncelik = Literal["cover", "ihtiyac", "esit", "orantili"]
ONCELIKLER = ("cover", "ihtiyac", "esit", "orantili")
ONGORU_TABANI = 0.1        # cover paydası: öngörüsü 0 olan çift sonsuz cover'a gitmesin (v2)


# ---------------------------------------------------------------------------
# Koli kuralı
# ---------------------------------------------------------------------------

_GEREKEN = {"yok": (), "kisitsiz": (), "A": ("alfa", "beta"), "B": ("gamma",),
            "C": ("alfa", "beta", "gamma")}


@dataclass(frozen=True)
class KoliKurali:
    """Kalan ihtiyaç `n` (çiftin bedenleri) ve koli içeriği `içerik` için
    (koli adedi = Σ içerik; standart 7, aksesuar 6):

        A          Σn ≥ α × koli adedi ve her bedende (içerik − n) < β
        B          Σ min(içerik, n) / koli adedi ≥ γ
        C          A ve B
        yok        hiç koli gitmez (yalnız açık toplama, tavanla)
        kisitsiz   koli zorunluluğu yok: bütün stok açık gibi (tavan ∞)
    """

    ad: str
    alfa: float | None = None
    beta: int | None = None
    gamma: float | None = None

    def __post_init__(self):
        if self.ad not in _GEREKEN:
            raise ValueError(f"bilinmeyen koli kuralı: {self.ad!r}")
        eksik = [a for a in _GEREKEN[self.ad] if getattr(self, a) is None]
        if eksik:
            raise ValueError(f"koli kuralı {self.ad} için eksik parametre: {eksik}")


def _yok() -> KoliKurali:
    return KoliKurali("yok")


def _a(alfa: float = 0.6, beta: int = 2) -> KoliKurali:
    return KoliKurali("A", alfa=alfa, beta=beta)


def _b(gamma: float = 0.6) -> KoliKurali:
    return KoliKurali("B", gamma=gamma)


def _c(alfa: float = 0.6, beta: int = 2, gamma: float = 0.6) -> KoliKurali:
    return KoliKurali("C", alfa=alfa, beta=beta, gamma=gamma)


# Kurucular (varsayılanlar v2'nin: α = 0,6, β = 2, γ = 0,6); kalibrasyon ızgarası üzerine yazar
KOLI_KURALLARI = {"yok": _yok, "A": _a, "B": _b, "C": _c}
KISITSIZ = KoliKurali("kisitsiz")


def _uygun(n: np.ndarray, icerik: np.ndarray, kural: KoliKurali) -> np.ndarray:
    """bool[k]: `n`, `icerik` [k, B] satır satır `koli_uygun`."""
    if kural.ad in ("yok", "kisitsiz"):
        return np.zeros(len(n), dtype=bool)
    adet = icerik.sum(axis=1)
    sonuc = np.ones(len(n), dtype=bool)
    if kural.ad in ("A", "C"):
        sonuc &= n.sum(axis=1) >= kural.alfa * adet
        sonuc &= (icerik - n).max(axis=1, initial=-1) < kural.beta
    if kural.ad in ("B", "C"):
        sonuc &= np.minimum(icerik, n).sum(axis=1) / np.maximum(adet, 1) >= kural.gamma
    return sonuc & (adet > 0)


def koli_uygun(n_beden: np.ndarray, icerik: np.ndarray, kural: KoliKurali) -> bool:
    """Kalan ihtiyaç `n_beden` [B] için koli kuralı geçer mi (`icerik` [B] kolinin
    beden adetleri, aynı sırada; koli adedi `icerik.sum()`)."""
    n = np.asarray(n_beden, dtype=np.int64).reshape(1, -1)
    ic = np.asarray(icerik, dtype=np.int64).reshape(1, -1)
    if n.shape != ic.shape:
        raise ValueError(f"n_beden {n.shape[1]} beden, içerik {ic.shape[1]}")
    return bool(_uygun(n, ic, kural)[0])


# ---------------------------------------------------------------------------
# Dünyadan indisler
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _Dizinler:
    hucre_sku: np.ndarray      # [C]
    hucre_oc: np.ndarray       # [C] (harita_kur sırası)
    hucre_sutun: np.ndarray    # [C] hücrenin option içindeki beden sütunu
    sku_option: np.ndarray     # [S]
    oc_option: np.ndarray      # [OC]
    oc_hucre: np.ndarray       # [OC, B] sütunun hücresi; yok −1
    icerik: np.ndarray         # [O, B] koli içeriği (beden_skulari sütunlarıyla)
    koli_adedi: np.ndarray     # [O]
    icerik_sku: np.ndarray     # [S]


def _kur(w) -> _Dizinler:
    """Hücre / çift / SKU / koli indisleri (her çağrıda; yalnız açık alanlar)."""
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    ho = np.asarray(w.hucre_option, dtype=np.int64)
    hs = np.asarray(w.hucre_sku, dtype=np.int64)
    so = np.asarray(w.sku_option, dtype=np.int64)
    O, S, C = len(w.optionlar), len(so), len(hs)
    cift, oc = np.unique(hm * O + ho, return_inverse=True)
    oc = oc.reshape(-1).astype(np.int64)
    skular = beden_skulari(w)
    icerik, koli_adedi = koli_icerigi(w)
    sku_sutun = np.full(S, -1, dtype=np.int64)
    var = skular >= 0
    sku_sutun[skular[var]] = np.nonzero(var)[1]
    sutun = sku_sutun[hs]
    oc_hucre = np.full((len(cift), skular.shape[1]), -1, dtype=np.int64)
    oc_hucre[oc, sutun] = np.arange(C)
    if (oc_hucre >= 0).sum() != C:
        raise ValueError("aynı (mağaza, SKU) için birden çok hücre")
    icerik_sku = np.zeros(S, dtype=np.int64)
    icerik_sku[skular[var]] = icerik[var]
    return _Dizinler(hucre_sku=hs, hucre_oc=oc, hucre_sutun=sutun, sku_option=so,
                     oc_option=(cift % O).astype(np.int64), oc_hucre=oc_hucre,
                     icerik=icerik, koli_adedi=koli_adedi, icerik_sku=icerik_sku)


# ---------------------------------------------------------------------------
# Dağıtım
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Sevk:
    """`dagit`'in sonucu.

    hucre_adet      int64[C] hücre başına gönderilen (açık + koli)
    acik_adet       açık aşamada toplanan adet (kısıtsızda bütün gönderim)
    koli_sayisi     gönderilen tam koli
    koli_adet       kolilerle giden adet
    tavan_dolulugu  açık adet / ⌊tavan⌋ (açık aşama en çok ⌊tavan⌋ adet
                    toplar; bağlayan kesirli tavanda 1,0). Tavan ∞ ise ya da
                    ⌊tavan⌋ = 0 ise (o zaman açık adet de 0) 0. Kolideki adet
                    sayılmaz.
    """

    hucre_adet: np.ndarray
    acik_adet: int
    koli_sayisi: int
    koli_adet: int
    tavan_dolulugu: float


def _dizi(x, n: int, ad: str, dtype) -> np.ndarray:
    a = np.asarray(x)
    if a.shape != (n,):
        raise ValueError(f"{ad}: boy {a.shape}, beklenen ({n},)")
    return a.astype(dtype)


def _en_buyuk_kalan(istek: np.ndarray, grup: np.ndarray, kapasite: np.ndarray) -> np.ndarray:
    """Grubun toplam isteği kapasiteyi aşıyorsa isteğe orantılı keser: her
    öğe ⌊istek × kapasite / toplam⌋, artan adetler kesri en büyük öğelere
    (eşitlikte küçük indis). Motorun `orantili_kes` aritmetiği (v3)."""
    G = len(kapasite)
    toplam = np.bincount(grup, istek, minlength=G).astype(np.int64)
    kisitli = toplam > kapasite
    if not kisitli.any():
        return istek.astype(np.int64)
    oran = np.where(kisitli, kapasite / np.maximum(toplam, 1), 1.0)
    hedef = istek * oran[grup]
    taban = np.where(kisitli[grup], np.floor(hedef + 1e-9), istek).astype(np.int64)
    taban = np.minimum(taban, istek)
    kalan = kapasite - np.bincount(grup, taban, minlength=G).astype(np.int64)
    kesir = np.where(kisitli[grup] & (istek > taban), hedef - taban, -1.0)
    sira = np.lexsort((np.arange(len(istek)), -kesir, grup))
    grup_sirali = grup[sira]
    rutbe = np.arange(len(sira)) - np.searchsorted(grup_sirali, grup_sirali, side="left")
    ver = (kesir[sira] > 0) & (rutbe < np.maximum(kalan, 0)[grup_sirali])
    sonuc = taban.copy()
    sonuc[sira[ver]] += 1
    return sonuc


def _acik_orantili(istek, z: _Dizinler, stok, tavan_adet) -> np.ndarray:
    x = _en_buyuk_kalan(istek, z.hucre_sku, stok)
    if tavan_adet is not None and x.sum() > tavan_adet:
        x = _en_buyuk_kalan(x, np.zeros(len(x), dtype=np.int64), np.array([tavan_adet]))
        assert x.sum() <= tavan_adet, "orantılı kesim tavanı aştı"
    return x


def _acik_sirayla(istek, z: _Dizinler, stok, tavan_adet, oncelik, eldeki_oc, f) -> np.ndarray:
    """Açık aşama, adet adet (heap; bkz. modül belgesi)."""
    C = len(istek)
    sonuc = np.zeros(C, dtype=np.int64)
    aday = np.flatnonzero((istek > 0) & (stok[z.hucre_sku] > 0))
    if aday.size == 0 or tavan_adet == 0:
        return sonuc
    # Çiftin istekli hücreleri (beden sırasıyla); ihtiyaç toplamı bütün istekli hücrelerden
    istekli = np.flatnonzero(istek > 0)
    istekli = istekli[np.lexsort((z.hucre_sutun[istekli], z.hucre_oc[istekli]))]
    oc_ist = z.hucre_oc[istekli]
    aktif = np.unique(z.hucre_oc[aday])
    bas = np.searchsorted(oc_ist, aktif, side="left")
    bit = np.searchsorted(oc_ist, aktif, side="right")
    R = np.bincount(z.hucre_oc[istekli], istek[istekli], minlength=len(f))

    istek_l = istek.tolist()
    sku_l = z.hucre_sku.tolist()
    stok_l = stok.astype(np.int64).tolist()
    giden_l = [0] * C
    istekli_l = istekli.tolist()
    E = {int(oc): float(eldeki_oc[oc]) for oc in aktif}
    F = {int(oc): float(f[oc]) for oc in aktif}
    G = dict.fromkeys(E, 0)
    Rd = {int(oc): int(R[oc]) for oc in aktif}
    hucreler = {int(oc): istekli_l[b:e] for oc, b, e in zip(aktif.tolist(), bas.tolist(), bit.tolist())}

    if oncelik == "cover":
        def anahtar(oc):
            return ((E[oc] + G[oc] + 1) / F[oc], oc)
    elif oncelik == "ihtiyac":
        def anahtar(oc):
            return (-Rd[oc], oc)
    else:  # esit
        def anahtar(oc):
            return (G[oc], (E[oc] + G[oc] + 1) / F[oc], oc)

    sinir = math.inf if tavan_adet is None else tavan_adet
    toplam = 0
    heap = [anahtar(oc) for oc in E]
    heapq.heapify(heap)
    while heap and toplam < sinir:
        oc = heapq.heappop(heap)[-1]
        hh = hucreler[oc]
        while True:
            sec = -1
            for c in hh:
                if giden_l[c] < istek_l[c] and stok_l[sku_l[c]] > 0:
                    if sec < 0 or (giden_l[c] + 1) * istek_l[sec] < (giden_l[sec] + 1) * istek_l[c]:
                        sec = c
            if sec < 0:
                break                                   # çiftin gidecek bedeni kalmadı
            giden_l[sec] += 1
            stok_l[sku_l[sec]] -= 1
            G[oc] += 1
            Rd[oc] -= 1
            toplam += 1
            if toplam >= sinir:
                break
            k = anahtar(oc)
            if heap and k > heap[0]:
                heapq.heappush(heap, k)
                break
    sonuc[:] = giden_l
    return sonuc


def _koli_asamasi(kalan, maske, z: _Dizinler, kapali, kural, oncelik, eldeki_oc, f,
                  giden_oc) -> np.ndarray:
    """[OC] çift başına gönderilen tam koli (bkz. modül belgesi)."""
    OC = len(z.oc_option)
    koli = np.zeros(OC, dtype=np.int64)
    var = z.oc_hucre >= 0
    hucre = np.maximum(z.oc_hucre, 0)
    ic = z.icerik[z.oc_option]
    # Kolinin her içerik bedeninin hücresi var ve maskede
    tamam = (~(ic > 0) | (var & maske[hucre])).all(axis=1)
    n = np.where(var, kalan[hucre], 0)
    aday = np.flatnonzero(tamam & (kapali[z.oc_option] > 0) & (n.sum(axis=1) > 0))
    if aday.size == 0:
        return koli
    aday = aday[_uygun(n[aday], ic[aday], kural)]
    if aday.size == 0:
        return koli
    n_bas = n.sum(axis=1)
    ka = z.koli_adedi[z.oc_option]
    G = giden_oc.astype(float)

    def anahtar(oc):
        if oncelik == "cover":
            return ((eldeki_oc[oc] + G[oc] + ka[oc]) / f[oc], oc)
        if oncelik == "ihtiyac":
            return (-int(n[oc].sum()), oc)
        if oncelik == "esit":
            return (G[oc], (eldeki_oc[oc] + G[oc] + ka[oc]) / f[oc], oc)
        return (-n_bas[oc] / (koli[oc] + 1), oc)        # orantılı: D'Hondt

    heap = [anahtar(int(oc)) for oc in aday]
    heapq.heapify(heap)
    while heap:
        oc = heapq.heappop(heap)[-1]
        o = z.oc_option[oc]
        if kapali[o] == 0:
            continue                                    # option'ın kolisi bitti
        kapali[o] -= 1
        koli[oc] += 1
        G[oc] += ka[oc]
        n[oc] = np.maximum(n[oc] - ic[oc], 0)
        if kapali[o] > 0 and _uygun(n[oc:oc + 1], ic[oc:oc + 1], kural)[0]:
            heapq.heappush(heap, anahtar(oc))
    return koli


def _kolileri_ac(defter, z: _Dizinler, sku_adet: np.ndarray) -> None:
    """Kısıtsız: açık stoğu yetmeyen SKU için option'ın kolisi gerektiği kadar
    defterde açılır (içerik açığa geçer); yalnız sayım."""
    ic = z.icerik_sku
    kisa = np.maximum(sku_adet - defter.acik, 0)
    if (kisa[ic == 0] > 0).any():
        raise AssertionError("kolide olmayan SKU'da açık stoktan fazla gönderim")
    gerek = -(-kisa // np.maximum(ic, 1))
    koli = np.zeros(len(z.koli_adedi), dtype=np.int64)
    np.maximum.at(koli, z.sku_option, gerek)
    defter.dus_koli(koli)
    defter.acik += koli[z.sku_option] * ic        # yerinde (dus_koli gibi): defterin dizisi değişmez


def dagit(
    istek_c: np.ndarray,
    defter,
    w,
    *,
    kural: KoliKurali,
    tavan: float,
    oncelik: Oncelik,
    ongoru_oc: np.ndarray,
    eldeki_c: np.ndarray,
    maske_c: np.ndarray,
) -> Sevk:
    """Hücre isteğini gölge defterin stoğuyla gönderime çevirir ve defterden düşer.

    istek_c    [C] kolun hücre isteği (negatif 0 sayılır)
    defter     `GolgeDefter` (kapalı koli ve açık adet; burada düşülür)
    w          dünya (yalnız açık alanlar)
    kural      `KoliKurali` (`KOLI_KURALLARI[...]()` ya da `KISITSIZ`)
    tavan      haftalık açık toplama tavanı, adet (∞ = yok; kısıtsızda ∞ olmalı)
    oncelik    "cover" | "ihtiyac" | "esit" | "orantili"
    ongoru_oc  [OC] çiftin öngörüsü (`harita_kur` sırası; cover paydası)
    eldeki_c   [C] raf + yolda (cover payı)
    maske_c    [C] bool; dışına hiçbir şey gitmez (`motor_maskesi`)
    """
    z = _kur(w)                       # TAM dünyada ~0,03 sn: önbelleğe gerek yok
    C, OC, S = len(z.hucre_sku), len(z.oc_option), len(z.sku_option)
    if oncelik not in ONCELIKLER:
        raise ValueError(f"bilinmeyen öncelik: {oncelik!r}")
    tavan = float(tavan)
    if math.isnan(tavan) or tavan < 0:
        raise ValueError(f"tavan ≥ 0 olmalı: {tavan}")
    kisitsiz = kural.ad == "kisitsiz"
    if kisitsiz and math.isfinite(tavan):
        raise ValueError("kısıtsız dağıtımda tavan ∞ olmalı")
    maske = _dizi(maske_c, C, "maske_c", bool)
    istek = np.where(maske, np.maximum(_dizi(istek_c, C, "istek_c", np.int64), 0), 0)
    f = np.maximum(_dizi(ongoru_oc, OC, "ongoru_oc", float), ONGORU_TABANI)
    eldeki_oc = np.bincount(z.hucre_oc, _dizi(eldeki_c, C, "eldeki_c", float), minlength=OC)
    if np.isnan(f).any() or np.isnan(eldeki_oc).any():
        raise ValueError("öngörü ya da eldeki stokta NaN")

    # 1) Açık aşama
    stok = defter.acik + (defter.kapali_adet() if kisitsiz else 0)
    tavan_adet = int(math.floor(tavan)) if math.isfinite(tavan) else None
    if oncelik == "orantili":
        acik = _acik_orantili(istek, z, stok, tavan_adet)
    else:
        acik = _acik_sirayla(istek, z, stok, tavan_adet, oncelik, eldeki_oc, f)
    acik_sku = np.bincount(z.hucre_sku, acik, minlength=S).astype(np.int64)
    if kisitsiz:
        _kolileri_ac(defter, z, acik_sku)
    defter.dus_acik(acik_sku)

    # 2) Koli aşaması
    koli_hucre = np.zeros(C, dtype=np.int64)
    koli = np.zeros(OC, dtype=np.int64)
    if kural.ad in ("A", "B", "C"):
        giden_oc = np.bincount(z.hucre_oc, acik, minlength=OC)
        koli = _koli_asamasi(istek - acik, maske, z, defter.kapali.copy(), kural, oncelik,
                             eldeki_oc, f, giden_oc)
        var = (z.oc_hucre >= 0) & (koli > 0)[:, None]
        adet = koli[:, None] * z.icerik[z.oc_option]
        np.add.at(koli_hucre, z.oc_hucre[var], adet[var])
        defter.dus_koli(np.bincount(z.oc_option, koli, minlength=len(z.koli_adedi)).astype(np.int64))

    acik_adet = int(acik.sum())
    return Sevk(
        hucre_adet=acik + koli_hucre,
        acik_adet=acik_adet,
        koli_sayisi=int(koli.sum()),
        koli_adet=int(koli_hucre.sum()),
        tavan_dolulugu=acik_adet / tavan_adet if tavan_adet else 0.0,
    )


# ---------------------------------------------------------------------------
# Motorun sıfırlama maskesi
# ---------------------------------------------------------------------------


def motor_maskesi(g) -> np.ndarray:
    """bool[C]: motorun replenishment isteğini sıfırlamadığı hücreler (v4
    `dongu.py` adım 10): option'ın ilk dağıtımı bugünden önce bitti
    (`ilk_dagitim_gun < gun`), option çıkmadı (`gun < cikis_gun`), hücre
    fiziksel ve outlet akışında değil, mağaza bugün açık."""
    w = g.dunya
    d = int(g.gun)
    ho = np.asarray(w.hucre_option)
    hm = np.asarray(w.hucre_magaza)
    cikis = w.optionlar["cikis_gun"].to_numpy()
    return (
        (np.asarray(g.ilk_dagitim_gun)[ho] < d) & (d < cikis[ho])
        & ~np.asarray(w.hucre_online, dtype=bool) & ~np.asarray(w.hucre_outlet_akisi, dtype=bool)
        & np.asarray(g.acik_magaza, dtype=bool)[hm]
    )
