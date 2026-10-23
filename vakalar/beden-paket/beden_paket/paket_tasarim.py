"""Paket tasarımı: K ortak 7'li desen, mağaza → desen ataması, beden başına depo kısıtı.

Kural: bu bir karar modülüdür; yalnız karar anında tahmin edilen mağaza eğrilerinden (`egri`
çıktısı) ve beklenen paket sayısından okur. `perakende_veri`'yi, gizli gerçeği ve ölçüm
modüllerini (hakem, ölçütler) içe aktarmaz (AST kilidi `tests/test_sizinti.py`).

**Adaylar** (`adaylar`). Beş bedenli, toplamı `adet` (ana: `PAKET_ADET` = 7) olan tamsayı
vektörler; `CEKIRDEK_BEDENLER` (2, 3, 4) her pakette en az 1, öteki bedenler en az 0 (spec §4.1:
kırık seti önlemek için). 7'li pakette 70 aday (çekirdek üç adet çıkınca kalan 4 adedin beş
bedene dağılışı, C(8, 4)). Sıra sözlük sırasıdır (0-1-1-1-4 … 4-1-1-1-0); eşitlikler bu sırayla
bozulur.

**Uyumsuzluk ölçüsü** (`uyumsuzluk`; sonuçlar görülmeden seçildi, değişmez). Mağaza m'ye eğrisi
e_m olan ve w_m paket alacak bir mağazaya p deseni gönderildiğinde *beklenen eksik adet*:

    U(p, e_m, w_m) = w_m × Σ_b max(0, a × e_mb − p_b)        (a = Σ_b p_b = 7)

yani mağazanın aynı adetteki talebinin beden payına göre paketin taşımadığı adet (eğri 4. bedende
2,1 adet istiyor, paket 1 taşıyor: 1,1 adet eksik). Gerekçe: birimi adettir ve ağırlığı paket
sayısıdır, bu yüzden mağazalar arasında doğrudan toplanır ("zincirde ilk dağıtımda yanlış bedende
duran adet"); bedenlerin eksik ve fazlası birbirini tuttuğu için (Σ_b (a e_mb − p_b) = 0) aynı
zamanda fazla adettir ve U = w_m × a × L1(p/a, e_m) / 2: L1 ölçüsüyle aynı sıralamayı verir, yani
"eksik adet mi L1 mi" seçimi tasarımı değiştirmez, yalnız birimi adete çevirir. KL gibi
logaritmik ölçüler sıfır adetli bedende (1. ve 5. beden 0 olabilir) tanımsızdır. Toplam
uyumsuzluk Σ_m U(p_{a(m)}, e_m, w_m)'dir.

**Ağırlık** w_m: mağazanın beklenen ilk dağıtım paket sayısı (Lumoda'nın karar günü planı; T4
sağlar). Sıfır ağırlıklı mağaza maliyete ve depo yüküne girmez; yine de seçilen desenlerden
kendi eğrisine (ağırlıksız) en yakın olanı alır.

**Arama** (`tasarla`).
- K ∈ {1, 2, 3, 4}: bütün K'lı aday kümeleri sözlük sırasında taranır; her kümede her mağaza en
  küçük uyumsuzluklu desene atanır (eşitlikte küme içindeki ilk desen), toplamı en küçük küme
  seçilir (eşitlikte, göreli 1e-9 içinde, sözlük sırasında ilk küme). 7'li pakette K = 4'te
  C(70, 4) = 916.895 küme: tam arama, `en_iyi_mi = True`. Küme sayısı `TAM_ARAMA_SINIRI`'nı
  aşarsa (ör. 12'li pakette K = 3) dönüşümlü arama (atama / her grubun en iyi deseni; açgözlü
  başlangıç ve `YENIDEN_BASLAMA` rastgele başlangıç, tohum `TOHUM`), `en_iyi_mi = False`.
- K = "magaza": her mağaza bütün adaylardan kendi en iyi desenini alır (aday kümesinin tamamı).
- Sonuçta yalnız kullanılan desenler kalır (spec §4.1 "en çok K paket tipi"): ayrı eğri sayısı
  K'dan azsa `desenler` K'dan az satırlıdır; desenler sözlük sırasındadır, `atama` bu sıranın
  indisidir.

**Depo kısıtı** (spec §0/11; `depo_payi` verilirse, sert kısıt). Beden b'de mağazalara giden adet
depodaki adedi aşmaz:

    Σ_m w_m × p_{a(m), b} ≤ depo_payi_b × a × Σ_m w_m

yani `depo_payi_b` = depodaki b adedi / ilk dağıtımda giden toplam adet (a × Σ w); toplamı 1'den
büyük olabilir (depoda kalan mal). Hedef sözlükseldir: önce toplam aşım (adet) en aza, sonra o
aşımla uyumsuzluk en aza. Arama önce kısıtsız en iyiyi bulur; o kısıtı sağlıyorsa en iyidir (kısıt
yalnız maliyeti artırabilir). Sağlamıyorsa (`yontem = "mip"`, `_kisitli`):
0. K = 1: her aday doğrudan değerlenir (tek atama), tam.
1. Bir bedende en az adetli desen bile depoyu aşıyorsa (Σw × min_p p_b > depo_b) o bedende fazladan
   her adet aşımı bir artırır, öteki bedenlerdeki aşımı en çok bir azaltır: en küçük aşım yalnız bu
   bedenlerde en az adetli desenlerle kurulur. Aday kümesi bunlara indirilir, o bedenlerin kısıtı
   kalkar, kalan problem aynı yolla çözülür (sağlanamayan depoda dal-sınırın budamamasının çaresi).
   Kalan problemde aşım kalırsa eşitlik ihtimali yüzünden `en_iyi_mi = False`.
2. Mağazaya özel kısıtlı tasarım karışık tamsayılı modelle çözülür (`_kisitli_ata`: HiGHS,
   `mip_rel_gap = 0`; mağaza → aday ataması ve beden başına aşım; bağlayabilen bedenlerde baskılanan
   (mağaza, desen) çiftleri modele girmez; ilk aşamanın LP gevşetmesi aşımı sıfır verirse doğrudan
   "aşım yok" altında çözülür). Bu her K için alt sınırdır; K = "magaza"da ya da en çok K desen
   kullanıyorsa sonuçtur.
3. Değilse K'lı kümelerde dal-sınır (`_kisitli_kume`): her kümenin aşım alt sınırı (her mağaza
   kümenin o bedende en az adetli desenini alsa; 2'nin aşımından küçükse o) ve uyumsuzluk alt sınırı
   (kısıtsız toplam) ucuzdur. Kümeler bu sınırlara göre sıralanır; önce alt sınır aşımına
   inebilecekler tek aşamalı modelle (aşım ≤ alt sınır; inemeyen kanıtla atlanır), hiçbiri inemezse
   bütün kümeler iki aşamalı modelle çözülür; sınır en iyi değeri geçince ya da en iyi değer 2'nin
   alt sınırına eşitlenince durulur. Eşit değerlerde bu işlenme sırasında (sınırlar, sonra sözlük
   sırası) ilk küme kalır; küme içi atamanın eşitliklerini çözücü (belirlenimci) bozar.
   Küme aşım alt sınırı bedenlerin her bölmesi üstünden alınır (parçadaki yük ≥ Σw × kümenin o
   parçada en az adetli deseni; parça aşımları toplanır, bölmelerin en büyüğü). Her geçişin kendi
   `_MIP_EN_COK` model bütçesi vardır; aşılırsa en iyi bulunan döner, `en_iyi_mi = False` (süre
   sınırı yok: tekrarlanabilirliği bozardı). Bütçe seçim yapılamadan biterse güvenli yedek
   (`_yedek`): kısıtsız en iyi küme ya da mağazaya özel tasarımın en ağır K deseni, kısıtlı
   atamayla; hiçbir durumda hata yükselmez.
4. Küme sayısı tam arama sınırını aşarsa (12'li pakette K ≥ 3) kısıtlı dönüşümlü arama
   (`_kisitli_donusumlu`): kümede kısıtlı atama ↔ her grubun, öteki gruplar sabitken (aşım,
   uyumsuzluk) en küçük deseni. Başlangıçlar: kısıtsız dönüşümlü aramanın desenleri, mağazaya özel
   kısıtlı tasarımın en ağır K deseni, K − 1'in kısıtlı tasarımına bir desen eklenmişi ve aday
   havuzundan (mağazaların kısıtsız en iyileri, mağazaya özel desenler) `_KISITLI_BASLAMA` tohumlu
   rastgele K'lı. `en_iyi_mi` yalnız 2'nin alt sınırına erişilirse doğrudur.
5. Kanıtsız her K sonucu K − 1'in kısıtlı sonucuyla kıyaslanır, iyi olan kalır: K'da tekdüze.
Çözücü bir modeli çözemezse (HiGHS "Solve error") ön işlemesiz yeniden denenir; yine çözülemezse o
küme kanıtsız atlanır, `en_iyi_mi = False`; tasarım düşmez. HiGHS'in stdout'a bastıkları susturulur.
Aşım sıfır değilse hiçbir tasarım kısıtı sağlamaz: en küçük toplam aşımlı tasarımlar arasında en
küçük uyumsuzluklu olan döner, `depo_uygun = False`, `depo_asimi` beden başına aşan adet.
`en_iyi_mi` tam aramada ve çözücünün kanıtlı optimumunda doğrudur; dönüşümlü arama mağazaya özel
alt sınıra erişirse de doğrudur. Desenler yalnız ağırlıklı mağazaların kullandıklarından sayılır.

**Belirlenimcilik.** Rastgelelik yalnız dönüşümlü aramada ve tohumludur; aynı girdi aynı çıktıyı
verir; mağaza satırlarının sırası sonucu değiştirmez (mağazalar içeride `magaza_id` sırasıyla
işlenir).
"""

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import chain, combinations, islice
from math import comb
from typing import Literal

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from beden_paket import sabitler

SUTUNLAR = tuple(f"b{i}" for i in range(1, sabitler.BEDEN_SAYISI + 1))
TAM_ARAMA_SINIRI = 2_000_000    # tam aramada taranacak en çok aday kümesi
YENIDEN_BASLAMA = 64            # dönüşümlü aramada rastgele başlangıç sayısı
_DONUSUM_EN_COK = 100
_ESITLIK = 1e-9                 # göreli eşitlik toleransı (sözlük sırası bozar)
_DEPO_TOL = 1e-6                # adet; depo kısıtı ve aşım toleransı
_PARCA = 16_384                 # tam aramada bir seferde değerlendirilen küme sayısı
_KISITLI_BASLAMA = 32          # kısıtlı dönüşümlü aramada ek rastgele başlangıç
_MIP_EN_COK = 3_000             # kısıtlı dal-sınırda en çok küme modeli (aşılırsa en_iyi_mi = False)


@dataclass(frozen=True)
class Tasarim:
    """Paket tasarımı (modül notu)."""
    desenler: np.ndarray            # [K', 5] tamsayı, K' ≤ K, sözlük sırası, her desen kullanılır
    atama: pd.Series                # magaza_id → `desenler` satır indisi (girdi eğrisinin sırası)
    toplam_uyumsuzluk: float        # Σ_m beklenen eksik adet
    en_iyi_mi: bool                 # kanıtlı en iyi (tam arama ya da optimal MIP)
    yontem: str                     # "tam" | "donusumlu" | "mip"
    depo_uygun: bool | None = None  # depo_payi verilmediyse None
    depo_asimi: np.ndarray | None = None   # [5] depoyu aşan adet (uygunsa sıfır)


def adaylar(adet: int = sabitler.PAKET_ADET) -> np.ndarray:
    """Toplamı `adet` olan, çekirdek bedenleri ≥ 1, öteki bedenleri ≥ 0 bütün desenler [n, 5],
    sözlük sırasında."""
    B = sabitler.BEDEN_SAYISI
    cekirdek = np.zeros(B, dtype=np.int64)
    cekirdek[[b - 1 for b in sabitler.CEKIRDEK_BEDENLER]] = 1
    kalan = adet - int(cekirdek.sum())
    if kalan < 0:
        raise ValueError(f"{adet} adetlik pakete çekirdek bedenler sığmaz")
    satirlar = []
    for cubuk in combinations(range(kalan + B - 1), B - 1):     # yıldız ve çubuk
        sinir = (-1,) + cubuk + (kalan + B - 1,)
        satirlar.append(tuple(sinir[i + 1] - sinir[i] - 1 for i in range(B)))
    return np.array(sorted(satirlar), dtype=np.int64) + cekirdek


def desen_adi(desen) -> str:
    return "-".join(str(int(x)) for x in desen)


def _eksik(E: np.ndarray, A: np.ndarray) -> np.ndarray:
    """[M, n] paket başına beklenen eksik adet (12 ondalığa yuvarlı: eşitlikler sayısal gürültüyle
    bozulmasın)."""
    a = A.sum(axis=1)[None, :, None]
    return np.round(np.maximum(0.0, a * E[:, None, :] - A[None, :, :]).sum(axis=2), 12)


def uyumsuzluk(paket, egri_satiri, agirlik: float = 1.0) -> float:
    """Beklenen eksik adet: ağırlık × Σ_b max(0, a × eğri_b − paket_b), a = paket adedi (modül
    notu)."""
    p = np.asarray(paket, dtype="float64")
    e = np.asarray(egri_satiri, dtype="float64")
    return float(agirlik * np.round(np.maximum(0.0, p.sum() * e - p).sum(), 12))


def en_yakin_desen(egri_satiri, adet: int = sabitler.PAKET_ADET) -> np.ndarray:
    """Tek eğriye en küçük uyumsuzluklu desen (eşitlikte sözlük sırasında ilk)."""
    A = adaylar(adet)
    return A[int(np.argmin(_eksik(np.asarray(egri_satiri, float)[None, :], A)[0]))]


def _esit_ya_da_kucuk(x: float, y: float) -> bool:
    return x <= y + _ESITLIK * max(1.0, abs(y))


def _kumeler(C: np.ndarray, K: int):
    """K'lı bütün aday kümeleri sözlük sırasında, parça parça: (küme [c, K], kısıtsız toplam [c])."""
    CT = C.T
    it = combinations(range(C.shape[1]), K)
    while True:
        blok = np.fromiter(chain.from_iterable(islice(it, _PARCA)), dtype=np.int64)
        if blok.size == 0:
            return
        blok = blok.reshape(-1, K)
        yield blok, CT[blok].min(axis=1).sum(axis=1)


def _tam(C: np.ndarray, K: int) -> np.ndarray:
    """K'lı bütün aday kümelerinin tam taraması (sözlük sırası); en iyi küme [K]."""
    en_iyi, secilen = np.inf, None
    for blok, toplam in _kumeler(C, K):
        enk = toplam.min()
        if secilen is None or not _esit_ya_da_kucuk(en_iyi, enk):
            i = int(np.flatnonzero(toplam <= enk + _ESITLIK * max(1.0, abs(enk)))[0])
            en_iyi, secilen = float(toplam[i]), blok[i]
    return secilen


def _donusumlu(C: np.ndarray, K: int, tohum: int) -> np.ndarray:
    """Dönüşümlü arama (atama ↔ grubun en iyi deseni), açgözlü + rastgele başlangıçlar."""
    n = C.shape[1]
    rng = np.random.default_rng(tohum)
    acgozlu: list[int] = []
    for _ in range(K):
        taban = C[:, acgozlu].min(axis=1) if acgozlu else np.full(C.shape[0], np.inf)
        acgozlu.append(int(np.argmin(np.minimum(taban[:, None], C).sum(axis=0))))
    baslangiclar = [np.array(acgozlu)] + [rng.choice(n, K, replace=False) for _ in range(YENIDEN_BASLAMA)]
    en_iyi, secilen = np.inf, None
    for S in baslangiclar:
        S = np.sort(S)
        for _ in range(_DONUSUM_EN_COK):
            grup = np.argmin(C[:, S], axis=1)
            yeni = S.copy()
            for g in range(len(S)):
                uye = grup == g
                if uye.any():
                    yeni[g] = int(np.argmin(C[uye].sum(axis=0)))
            yeni = np.unique(yeni)
            if np.array_equal(yeni, S):
                break
            S = yeni
        toplam = float(C[:, S].min(axis=1).sum())
        if secilen is None or toplam < en_iyi - _ESITLIK * max(1.0, abs(en_iyi)) or (
                _esit_ya_da_kucuk(toplam, en_iyi) and tuple(S) < tuple(secilen)):
            en_iyi, secilen = toplam, S
    return secilen


def _asim(w: np.ndarray, A: np.ndarray, secim: np.ndarray, cap: np.ndarray) -> np.ndarray:
    """[5] depoyu aşan adet (tolerans içi sıfır)."""
    a = np.maximum(0.0, w @ A[secim] - cap)
    a[a <= _DEPO_TOL] = 0.0
    return a


@contextmanager
def _sessiz():
    """HiGHS'in C düzeyinde stdout'a (dosya tanıtıcısı 1) bastığı satırları susturur."""
    try:
        sys.stdout.flush()
        eski = os.dup(1)
    except (OSError, ValueError, AttributeError):
        eski = None
    if eski is None:
        yield
        return
    bos = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(bos, 1)
        yield
    finally:
        os.dup2(eski, 1)
        os.close(bos)
        os.close(eski)


def _coz(amac, tamsayi, sinir, kisit):
    """`milp` (HiGHS, `mip_rel_gap = 0`); çözücü hatasında ön işlemesiz yeniden. Döner (sonuç | None,
    durum): "optimal", "uygunsuz" (kanıtlı), "kanitsiz" (çözüm var, optimallik kanıtı yok), "hata"."""
    yedek = None
    for on_isleme in (True, False):
        with _sessiz():
            r = milp(amac, integrality=tamsayi, bounds=sinir, constraints=kisit,
                     options={"mip_rel_gap": 0.0, "presolve": on_isleme})
        if r.status == 0 and r.x is not None:
            return r, "optimal"
        if r.status == 2:
            return None, "uygunsuz"
        if r.x is not None and yedek is None:
            yedek = r
    return (yedek, "kanitsiz") if yedek is not None else (None, "hata")


def _baskilanmayan(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray) -> list[np.ndarray]:
    """Mağaza başına baskılanmayan adaylar. q, p'yi baskılar ⇔ q'nun uyumsuzluğu ≤ ve bağlayabilecek
    her bedende (Σw × en çok adet > depo) adedi ≤ (hepsinde eşitse küçük indis). Baskılanan deseni
    alan mağaza baskılayana geçince ne aşım ne uyumsuzluk artar: model yalnız baskılanmayan
    (mağaza, desen) çiftleriyle kurulur ve yine tamdır."""
    n = C.shape[1]
    bag = w.sum() * A.max(axis=0) > cap + _DEPO_TOL
    Ab = A[:, bag]
    az = (Ab[:, None, :] <= Ab[None, :, :]).all(axis=2)          # [q, p]: q her bağlayan bedende ≤ p
    ayni = (Ab[:, None, :] == Ab[None, :, :]).all(axis=2)
    once = np.arange(n)[:, None] < np.arange(n)[None, :]
    sonuc = []
    for c in C:
        ucuz, esit = c[:, None] <= c[None, :], c[:, None] == c[None, :]
        bask = (az & ucuz & ~(ayni & esit)) | (ayni & esit & once)
        sonuc.append(np.flatnonzero(~bask.any(axis=0)))
    return sonuc


def _kisitli_ata(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, asim_ust: float | None = None):
    """Verilen desenlerle (A'nın satırları) depo kısıtlı atama, karışık tamsayılı model: önce en
    küçük toplam aşım (adet), sonra o aşımla en küçük uyumsuzluk. `asim_ust` verilirse ilk aşama
    atlanır, aşım ≤ `asim_ust` altında uyumsuzluk en aza indirilir. Döner (mağaza başına A satır
    indisi | None, toplam aşım, uyumsuzluk, durum) — durum `_coz`'unki."""
    M = C.shape[0]
    B = A.shape[1]
    ciftler = _baskilanmayan(C, w, A, cap)
    mi = np.concatenate([np.full(len(c), m) for m, c in enumerate(ciftler)])
    pi = np.concatenate(ciftler)
    nx, nv = len(mi), len(mi) + B                    # x (mağaza, desen çifti) | s (b)
    tek = sparse.csr_array((np.ones(nx), (mi, np.arange(nx))), shape=(M, nv))      # her mağaza tek desen
    yuk = np.hstack([w[mi][None, :] * A[pi].T, -np.eye(B)])                        # Σ w A x − s ≤ cap
    kisit = [LinearConstraint(tek, 1.0, 1.0), LinearConstraint(yuk, -np.inf, cap)]
    tamsayi = np.r_[np.ones(nx), np.zeros(B)]
    sinir = Bounds(np.zeros(nv), np.r_[np.ones(nx), np.full(B, np.inf)])
    amac1 = np.r_[np.zeros(nx), np.ones(B)]
    amac2 = np.r_[C[mi, pi], np.zeros(B)]

    def sonuc(r, durum):
        x = r.x[:nx]
        o = np.lexsort((-x, mi))
        ilk = np.r_[True, mi[o][1:] != mi[o][:-1]]
        secim = np.empty(M, dtype=np.int64)
        secim[mi[o][ilk]] = pi[o][ilk]
        return secim, float(_asim(w, A, secim, cap).sum()), float(C[np.arange(M), secim].sum()), durum

    kesin = True
    if asim_ust is None:
        # ilk aşamanın LP gevşetmesi aşımı sıfır veriyorsa doğrudan "aşım yok" altında çöz (sık
        # durum; ilk aşamanın tamsayı modeli pahalı olabilir); olmazsa tamsayı ilk aşama
        r0, _ = _coz(amac1, np.zeros(nv), sinir, kisit)
        if r0 is not None and float(r0.fun) <= _DEPO_TOL:
            ek = LinearConstraint(amac1[None, :], -np.inf, _DEPO_TOL)
            r2, d2 = _coz(amac2, tamsayi, sinir, kisit + [ek])
            if r2 is not None:
                return sonuc(r2, "optimal" if d2 == "optimal" else "kanitsiz")
        r1, d1 = _coz(amac1, tamsayi, sinir, kisit)
        if r1 is None:                               # aşım değişkenleriyle model her zaman uygundur
            return None, np.inf, np.inf, "hata"
        asim_ust, kesin = float(r1.fun) + _DEPO_TOL, d1 == "optimal"
    kisit.append(LinearConstraint(amac1[None, :], -np.inf, asim_ust))
    r2, d2 = _coz(amac2, tamsayi, sinir, kisit)
    if r2 is None:
        return None, np.inf, np.inf, d2
    return sonuc(r2, "optimal" if kesin and d2 == "optimal" else "kanitsiz")


def _onde(a: tuple, b: tuple) -> bool:
    """(aşım, uyumsuzluk) çiftinde a, b'den kesin iyi mi (tolerans dışında)."""
    if a[0] < b[0] - _DEPO_TOL:
        return True
    return abs(a[0] - b[0]) <= _DEPO_TOL and a[1] < b[1] - _ESITLIK * max(1.0, abs(b[1]))


def _deger(C, w, A, secim, cap) -> tuple:
    return float(_asim(w, A, secim, cap).sum()), float(C[np.arange(len(w)), secim].sum())


def _ozel(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray):
    """Mağazaya özel kısıtlı tasarım ve her K için geçerli alt sınır (aşım, uyumsuzluk). Model
    kanıtlı çözülemezse alt sınır ucuz sınırdır: aşım ≥ Σ_b max(0, Σw × min_p A_pb − cap_b),
    uyumsuzluk ≥ Σ_m min_p U. Döner (atama | None, alt sınır, kanıtlı mı)."""
    secim, a, m, durum = _kisitli_ata(C, w, A, cap)
    if durum == "optimal":
        return secim, (a, m), True
    ucuz = (float(np.maximum(0.0, w.sum() * A.min(axis=0) - cap).sum()), float(C.min(axis=1).sum()))
    return secim, ucuz, False


def _yedek(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, kumeler) -> np.ndarray:
    """Arama seçim yapamadığında güvenli tasarım: verilen her aday kümesinde kısıtlı atama (çözücü
    çözemezse kısıtsız atama); (aşım, uyumsuzluk) en küçük olan. Hiçbir zaman None dönmez."""
    en_iyi, secilen = None, None
    for S in kumeler:
        S = np.unique(np.asarray(S, dtype=np.int64))
        if S.size == 0:
            continue
        y = _kisitli_ata(C[:, S], w, A[S], cap)[0]
        secim = S[y] if y is not None else S[np.argmin(C[:, S], axis=1)]
        deger = _deger(C, w, A, secim, cap)
        if secilen is None or _onde(deger, en_iyi):
            en_iyi, secilen = deger, secim
    return secilen


def _en_agir(secim: np.ndarray, w: np.ndarray, K: int, n: int) -> np.ndarray:
    """Atamada toplam ağırlığı en büyük K desen (eşitlikte küçük indis)."""
    poz = w > 0
    agir = np.bincount(secim[poz], weights=w[poz], minlength=n)
    return np.array([int(p) for p in np.lexsort((np.arange(n), -agir)) if agir[p] > 0][:K], dtype=np.int64)


def _bolmeler(B: int) -> tuple[np.ndarray, np.ndarray]:
    """Beden kümesinin boş olmayan alt kümeleri [31, B] (0/1) ve bütün bölmeleri [52, 31] (her
    bölme hangi alt kümelerden oluşur)."""
    alt = np.array([[(t >> b) & 1 for b in range(B)] for t in range(1, 2 ** B)], dtype=np.int64)

    def bol(kalan):
        if not kalan:
            yield []
            return
        ilk, geri = kalan[0], kalan[1:]
        for r in range(len(geri) + 1):
            for es in combinations(geri, r):
                parca = (ilk, *es)
                for devam in bol([x for x in geri if x not in es]):
                    yield [parca, *devam]

    bolme = []
    for b_ in bol(list(range(B))):
        satir = np.zeros(len(alt), dtype=np.int64)
        for parca in b_:
            satir[sum(1 << x for x in parca) - 1] = 1
        bolme.append(satir)
    return alt, np.array(bolme)


def _kisitli_kume(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, K: int, alt_sinir: tuple,
                  yedekler=()):
    """K'lı kümeler üzerinde depo kısıtlı tam arama (dal-sınır; modül notu). Her geçişin kendi model
    bütçesi (`_MIP_EN_COK`) vardır; bütçe biter de hiçbir küme seçilemezse `_yedek` ile `yedekler`
    (ve kısıtsız en iyi küme) arasından güvenli tasarım döner, kanıtsız. Döner (mağaza başına aday
    indisi, en iyi mi)."""
    W = w.sum()
    s_alt = alt_sinir[0]                            # K'dan bağımsız aşım alt sınırı
    anahtar, kumeler = [], []
    # kümenin aşım alt sınırı: bedenlerin her bölmesi için Σ_parça max(0, Σw × min_{p∈S} p(parça) −
    # depo(parça)) (parçadaki yük en az bu kadar); bölmelerin en büyüğü, s_alt'tan küçükse s_alt
    alt_kume, bolme = _bolmeler(A.shape[1])
    A_alt = A @ alt_kume.T                                          # [n, 31]
    cap_alt = np.where(alt_kume == 1, cap[None, :], 0.0).sum(axis=1)  # [31] (sonsuz depo güvenli)
    for blok, toplam in _kumeler(C, K):
        g = np.maximum(0.0, W * A_alt[blok].min(axis=1) - cap_alt)      # [c, 31]
        sl = np.maximum((g @ bolme.T).max(axis=1), s_alt)
        anahtar.append(np.c_[np.round(sl, 9), np.round(toplam, 9)])
        kumeler.append(blok)
    anahtar, kumeler = np.vstack(anahtar), np.vstack(kumeler)
    sira = np.lexsort((np.arange(len(kumeler)), anahtar[:, 1], anahtar[:, 0]))
    d = {"en_iyi": (np.inf, np.inf), "secim": None, "kanit": True, "model": 0}

    def gecis(sira_, hedef):
        d["model"] = 0                              # her geçişin kendi bütçesi
        for i in sira_:
            sl, alt_t = anahtar[i]
            e = d["en_iyi"]
            esik = e[1] + _ESITLIK * max(1.0, abs(e[1]))
            if sl > e[0] + _DEPO_TOL or (sl >= e[0] - _DEPO_TOL and alt_t > esik):
                return
            if d["secim"] is not None and not _onde(alt_sinir, e):
                return                              # alt sınıra erişildi: daha iyisi yok
            S = kumeler[i]
            yerel = np.argmin(C[:, S], axis=1)
            deger = _deger(C, w, A, S[yerel], cap)
            kesin = True
            if deger[0] > s_alt + _DEPO_TOL:        # kısıtsız atama alt sınıra inmiyor: model
                if d["model"] >= _MIP_EN_COK:
                    d["kanit"] = False
                    return
                d["model"] += 1
                y, a, m, durum = _kisitli_ata(C[:, S], w, A[S], cap, hedef)
                if durum == "uygunsuz":             # küme hedef aşıma inemez (kanıtlı): atla
                    continue
                if y is None:
                    d["kanit"] = False
                    continue
                yerel, deger, kesin = y, (a, m), durum == "optimal"
            if d["secim"] is None or _onde(deger, e):
                d["en_iyi"], d["secim"] = deger, S[yerel]
            d["kanit"] = d["kanit"] and kesin

    # 1. geçiş: aşımı alt sınıra inebilecek kümeler, tek aşamalı model (aşım ≤ alt sınır)
    gecis(sira[anahtar[sira, 0] <= s_alt + _DEPO_TOL], s_alt + _DEPO_TOL)
    if d["secim"] is None or d["en_iyi"][0] > s_alt + _DEPO_TOL:
        # hiçbir K'lı küme alt sınıra inemedi: bütün kümeler, iki aşamalı model
        onceki = d["secim"]
        d["en_iyi"], d["secim"] = (np.inf, np.inf), None
        gecis(sira, None)
        if d["secim"] is None and onceki is not None:
            d["secim"], d["kanit"] = onceki, False
    if d["secim"] is None:                          # bütçe bitti, seçim yok: güvenli yedek
        return _yedek(C, w, A, cap, [kumeler[sira[0]], *yedekler]), False
    return d["secim"], d["kanit"]


def _kisitli_donusumlu(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, baslangiclar):
    """Depo kısıtlı dönüşümlü arama: kümede kısıtlı atama (`_kisitli_ata`) ↔ her grubun, öteki
    gruplar sabitken (aşım, uyumsuzluk) en küçük deseni. Her adım değeri artırmaz. Döner en iyi
    atama (aday indisi)."""
    n = C.shape[1]
    en_iyi, secilen = None, None

    def aday(secim):
        nonlocal en_iyi, secilen
        deger = _deger(C, w, A, secim, cap)
        if secilen is None or _onde(deger, en_iyi) or (
                not _onde(en_iyi, deger) and tuple(np.unique(secim)) < tuple(np.unique(secilen))):
            en_iyi, secilen = deger, secim.copy()

    for S0 in baslangiclar:
        S = np.unique(S0)
        for _ in range(_DONUSUM_EN_COK):
            y = _kisitli_ata(C[:, S], w, A[S], cap)[0]
            if y is None:
                break
            sec = S[y]
            aday(sec)
            yuk = w @ A[sec]
            for g in np.unique(sec):
                uye = sec == g
                Wg = w[uye].sum()
                if Wg == 0:
                    continue
                taban = yuk - Wg * A[g]
                asim = np.maximum(0.0, taban[None, :] + Wg * A - cap[None, :])
                asim[asim <= _DEPO_TOL] = 0.0
                p = int(np.lexsort((np.arange(n), np.round(C[uye].sum(axis=0), 9),
                                    np.round(asim.sum(axis=1), 6)))[0])
                sec[uye] = p
                yuk = taban + Wg * A[p]
            aday(sec)
            yeni = np.unique(sec)
            if np.array_equal(yeni, S):
                break
            S = yeni
    return secilen


def _kisitli(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, K: int | None,
             tohum: int, ozel=None) -> tuple[np.ndarray, bool]:
    """Depo kısıtlı tasarım (modül notu). `ozel`: aynı problemin önceden çözülmüş `_ozel`'i
    (K − 1 özyinelemesinde yeniden çözülmesin). Döner (atama, en iyi mi)."""
    K = None if K is None else min(K, C.shape[1])
    W, en_az = w.sum(), A.min(axis=0)
    if K == 1:                                       # tek desen: her aday doğrudan değerlenir
        asim = np.maximum(0.0, W * A - cap[None, :])
        asim[asim <= _DEPO_TOL] = 0.0
        anahtar = (np.arange(len(A)), np.round(C.sum(axis=0), 9), np.round(asim.sum(axis=1), 6))
        p = int(np.lexsort(anahtar)[0])
        return np.full(len(w), p), True
    asiri = W * en_az - cap > _DEPO_TOL
    if asiri.any():
        # Bu bedenlerde her desen depoyu aşar; fazladan her adet aşımı bir artırır, öteki bedenlerde
        # en çok bir azaltır: en küçük aşım yalnız bu bedenlerde en az adetli desenlerle (R) kurulur.
        R = np.flatnonzero((A[:, asiri] == en_az[asiri]).all(axis=1))
        cap_R = np.where(asiri, np.inf, cap)
        yerel, kesin = _kisitli(C[:, R], w, A[R], cap_R, K, tohum)
        # R dışı bir desen ancak öteki bedenlerdeki aşımı aynı miktar azaltırsa eşit kalır: alt
        # problemde aşım yoksa bu imkânsızdır, varsa en iyilik iddia edilmez
        return R[yerel], kesin and not _asim(w, A[R], yerel, cap_R).any()
    if ozel is None:
        ozel = _ozel(C, w, A, cap)
    y, alt, ozel_kesin = ozel
    poz = w > 0
    if y is not None and ozel_kesin and (K is None or len(np.unique(y[poz])) <= K):
        return y, True
    if K is None:
        return (y if y is not None else np.argmin(C, axis=1)), False
    n = C.shape[1]
    agir = _en_agir(y, w, n, n) if y is not None else np.array([], dtype=np.int64)
    yedekler = [agir[:K]] if agir.size else []
    onceki = None                                    # K − 1'in kısıtlı tasarımı (gerekirse)
    if comb(n, K) <= TAM_ARAMA_SINIRI:
        secim, kesin = _kisitli_kume(C, w, A, cap, K, alt, yedekler)
    else:
        kisitsiz = _donusumlu(C, K, tohum)
        baslangiclar = [kisitsiz, *yedekler]
        if K > 1:                                    # K − 1'in kısıtlı tasarımı + bir desen: tekdüzelik
            onceki = _kisitli(C, w, A, cap, K - 1, tohum, ozel)[0]
            o = np.unique(onceki[poz])
            ek = [p for p in list(agir) + list(kisitsiz) if p not in set(o)]
            baslangiclar.append(np.r_[o, ek[:1]].astype(np.int64))
        # ucuz çoklu başlangıç: aday havuzundan (mağazaların kısıtsız en iyileri, mağazaya özel
        # kısıtlı desenler) tohumlu rastgele K'lılar
        havuz = np.unique(np.r_[np.argmin(C[poz], axis=1), agir]).astype(np.int64)
        if havuz.size > K:
            rng = np.random.default_rng(tohum)
            baslangiclar += [rng.choice(havuz, K, replace=False) for _ in range(_KISITLI_BASLAMA)]
        secim = _kisitli_donusumlu(C, w, A, cap, baslangiclar)
        if secim is None:                            # hiçbir başlangıçta model çözülemedi
            secim = _yedek(C, w, A, cap, baslangiclar)
        kesin = ozel_kesin and not _onde(alt, _deger(C, w, A, secim, cap))
    if not kesin and K > 1:                          # kanıtsız sonuç K − 1'inkinden kötü olamaz
        if onceki is None:
            onceki = _kisitli(C, w, A, cap, K - 1, tohum, ozel)[0]
        if _onde(_deger(C, w, A, onceki, cap), _deger(C, w, A, secim, cap)):
            secim = onceki
    return secim, kesin


def tasarla(egri: pd.DataFrame, agirlik: pd.Series, K: int | Literal["magaza"],
            depo_payi=None, *, adet: int = sabitler.PAKET_ADET, tohum: int = sabitler.TOHUM) -> Tasarim:
    """Mağaza eğrilerine (`egri`, satır `magaza_id`, sütun b1..b5, satırlar bire toplanır) K ortak
    desen ve atama; `depo_payi` [5] verilirse beden başına depo kısıtı (modül notu). Yinelenen
    `magaza_id` hatadır."""
    if K != "magaza" and not (isinstance(K, (int, np.integer)) and K >= 1):
        raise ValueError(f"K pozitif tamsayı ya da 'magaza' olmalı: {K!r}")
    if not egri.index.is_unique or not agirlik.index.is_unique:
        raise ValueError("magaza_id yinelenmemeli (eğri ve ağırlık)")
    sira = sorted(egri.index)
    E = egri.loc[sira, list(SUTUNLAR)].to_numpy(dtype="float64")
    if np.isnan(E).any() or not np.allclose(E.sum(axis=1), 1.0, atol=1e-6) or (E < 0).any():
        raise ValueError("eğri satırları negatif olmayan ve bire toplanan paylar olmalı")
    eksik = set(sira) - set(agirlik.index)
    if eksik:
        raise ValueError(f"ağırlığı olmayan mağaza: {sorted(eksik)[:5]}")
    w = agirlik.loc[sira].to_numpy(dtype="float64")
    if np.isnan(w).any() or (w < 0).any():
        raise ValueError("ağırlıklar negatif olmayan sayılar olmalı")
    if depo_payi is not None:
        depo_payi = np.asarray(depo_payi, dtype="float64")
        if depo_payi.shape != (len(SUTUNLAR),) or (depo_payi < 0).any() or np.isnan(depo_payi).any():
            raise ValueError("depo_payi beş negatif olmayan sayı olmalı")

    A = adaylar(adet)
    n = len(A)
    D = _eksik(E, A)
    C = w[:, None] * D
    poz = w > 0

    kume_k = None if K == "magaza" else min(int(K), n)
    if kume_k is None:
        kume, en_iyi, yontem = np.arange(n), True, "tam"
    elif comb(n, kume_k) <= TAM_ARAMA_SINIRI:
        kume, en_iyi, yontem = _tam(C, kume_k), True, "tam"
    else:
        kume, en_iyi, yontem = _donusumlu(C, kume_k, tohum), False, "donusumlu"
    secim = kume[np.argmin(C[:, kume], axis=1)]
    if not en_iyi and _esit_ya_da_kucuk(float(C[np.arange(len(w)), secim].sum()), float(C.min(axis=1).sum())):
        en_iyi = True                                    # mağazaya özel alt sınıra erişti

    depo_uygun = depo_asimi = None
    if depo_payi is not None:
        cap = depo_payi * adet * w.sum()
        if _asim(w, A, secim, cap).any():
            yontem = "mip"
            secim, en_iyi = _kisitli(C, w, A, cap, kume_k, tohum)
        depo_asimi = _asim(w, A, secim, cap)
        depo_uygun = not depo_asimi.any()

    # desen sayımı ağırlıklı mağazalardan; sıfır ağırlıklı mağaza (maliyete ve depoya girmez)
    # kullanılan desenlerden kendi eğrisine en yakınını alır
    kullanilan = np.unique(secim[poz]) if poz.any() else np.unique(secim)
    if (~poz).any():
        secim = secim.copy()
        secim[~poz] = kullanilan[np.argmin(D[np.ix_(~poz, kullanilan)], axis=1)]
    atama = pd.Series(np.searchsorted(kullanilan, secim), index=pd.Index(sira, name="magaza_id"),
                      name="desen").reindex(egri.index)
    atama.index.name = "magaza_id"
    return Tasarim(desenler=A[kullanilan].copy(), atama=atama,
                   toplam_uyumsuzluk=float(C[np.arange(len(sira)), secim].sum()),
                   en_iyi_mi=en_iyi, yontem=yontem, depo_uygun=depo_uygun, depo_asimi=depo_asimi)


def desen_profil_capraz(tasarim: Tasarim, profil: pd.Series) -> pd.DataFrame:
    """Profil × desen mağaza sayısı (rapor için; sütunlar `desenler` sırasında, `1-2-2-1-1`)."""
    adlar = [desen_adi(d) for d in tasarim.desenler]
    desen = pd.Categorical([adlar[i] for i in tasarim.atama], categories=adlar)
    return pd.crosstab(pd.Series(profil.reindex(tasarim.atama.index).to_numpy(), name="profil"),
                       pd.Series(desen, name="desen"), dropna=False)
