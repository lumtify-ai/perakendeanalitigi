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
yalnız maliyeti artırabilir). Sağlamıyorsa (`yontem = "mip"`):
1. Mağazaya özel kısıtlı tasarım karışık tamsayılı modelle çözülür (`_kisitli_ata`: HiGHS,
   `mip_rel_gap = 0`; mağaza → aday ataması ve beden başına aşım). Bu her K için alt sınırdır;
   K = "magaza"da ya da en çok K desen kullanıyorsa sonuçtur.
2. Değilse K'lı kümelerde dal-sınır (`_kisitli_kume`): her kümenin aşım alt sınırı (her mağaza
   kümenin o bedende en az adetli desenini alsa) ve uyumsuzluk alt sınırı (kısıtsız toplam) ucuzdur;
   kümeler bu sınırlara göre sıralanıp sırayla kısıtlı atamayla çözülür, sınır en iyi değeri geçince
   durulur. Eşit değerlerde bu işlenme sırasında (sınırlar, sonra sözlük sırası) ilk küme kalır;
   küme içi atamanın eşitliklerini çözücü (belirlenimci) bozar. `_MIP_EN_COK` model aşılırsa en iyi
   bulunan döner, `en_iyi_mi = False`. Dönüşümlü arama yolunda yalnız bulunan desenlerle kısıtlı
   atama yapılır (`en_iyi_mi = False`).
Aşım sıfır değilse hiçbir tasarım kısıtı sağlamaz: en küçük toplam aşımlı tasarımlar arasında en
küçük uyumsuzluklu olan döner, `depo_uygun = False`, `depo_asimi` beden başına aşan adet.
`en_iyi_mi` tam aramada ve çözücünün kanıtlı optimumunda doğrudur; dönüşümlü arama mağazaya özel
alt sınıra (Σ_m min_p U) erişirse de doğrudur.

**Belirlenimcilik.** Rastgelelik yalnız dönüşümlü aramada ve tohumludur; aynı girdi aynı çıktıyı
verir; mağaza satırlarının sırası sonucu değiştirmez (mağazalar içeride `magaza_id` sırasıyla
işlenir).
"""

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
_MIP_EN_COK = 20_000            # kısıtlı dal-sınırda en çok küme modeli (aşılırsa en_iyi_mi = False)


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


def _kisitli_ata(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray):
    """Verilen desenlerle (A'nın satırları) depo kısıtlı atama, karışık tamsayılı model (HiGHS,
    `mip_rel_gap = 0`): önce en küçük toplam aşım (adet), sonra o aşımla en küçük uyumsuzluk.
    Döner: (mağaza başına A satır indisi, toplam aşım, uyumsuzluk, kanıtlı optimal mi)."""
    M, n = C.shape
    B = A.shape[1]
    nx, nv = M * n, M * n + B                        # x (m, p) | s (b)
    tek = sparse.hstack([sparse.kron(sparse.eye_array(M), np.ones((1, n))),
                         sparse.csr_array((M, B))])  # her mağaza tek desen
    yuk = np.hstack([np.einsum("m,pb->bmp", w, A).reshape(B, nx), -np.eye(B)])   # Σ w A x − s ≤ cap
    kisit = [LinearConstraint(tek, 1.0, 1.0), LinearConstraint(yuk, -np.inf, cap)]
    tamsayi = np.r_[np.ones(nx), np.zeros(B)]
    sinir = Bounds(np.zeros(nv), np.r_[np.ones(nx), np.full(B, np.inf)])
    secenek = {"mip_rel_gap": 0.0, "presolve": True}
    amac1 = np.r_[np.zeros(nx), np.ones(B)]
    r1 = milp(amac1, integrality=tamsayi, bounds=sinir, constraints=kisit, options=secenek)
    if r1.x is None:
        raise RuntimeError(f"depo modeli çözülemedi: {r1.message}")
    kisit.append(LinearConstraint(amac1[None, :], -np.inf, float(r1.fun) + _DEPO_TOL))
    r2 = milp(np.r_[C.ravel(), np.zeros(B)], integrality=tamsayi, bounds=sinir, constraints=kisit,
              options=secenek)
    if r2.x is None:
        raise RuntimeError(f"depo modeli çözülemedi: {r2.message}")
    secim = np.argmax(r2.x[:nx].reshape(M, n), axis=1)
    return (secim, float(_asim(w, A, secim, cap).sum()), float(C[np.arange(M), secim].sum()),
            bool(r1.status == 0 and r2.status == 0))


def _onde(a: tuple, b: tuple) -> bool:
    """(aşım, uyumsuzluk) çiftinde a, b'den kesin iyi mi (tolerans dışında)."""
    if a[0] < b[0] - _DEPO_TOL:
        return True
    return abs(a[0] - b[0]) <= _DEPO_TOL and a[1] < b[1] - _ESITLIK * max(1.0, abs(b[1]))


def _kisitli_kume(C: np.ndarray, w: np.ndarray, A: np.ndarray, cap: np.ndarray, K: int,
                  alt_sinir: tuple):
    """K'lı kümeler üzerinde depo kısıtlı tam arama (dal-sınır). Her kümenin iki alt sınırı ucuz:
    aşım ≥ Σ_b max(0, Σw × min_{p∈S} A_pb − cap_b), uyumsuzluk ≥ kısıtsız toplam. Kümeler bu
    sınırlara (sonra sözlük sırasına) göre sıralanır; kısıtsız ataması uygun olan kümenin değeri
    kısıtsız toplamıdır, öteki kümelerde `_kisitli_ata` çözülür. Sınır en iyi değeri geçince ya da en
    iyi değer `alt_sinir`'a (mağazaya özel kısıtlı tasarım: her K için alt sınır) eşitlenince durur.
    Eşit değerlerde bu işlenme sırasında ilk küme. Döner: (mağaza başına aday indisi, en iyi mi)."""
    W = w.sum()
    anahtar, kumeler = [], []
    for blok, toplam in _kumeler(C, K):
        sl = np.maximum(0.0, W * A[blok].min(axis=1) - cap).sum(axis=1)
        anahtar.append(np.c_[np.round(sl, 9), np.round(toplam, 9)])
        kumeler.append(blok)
    anahtar, kumeler = np.vstack(anahtar), np.vstack(kumeler)
    sira = np.lexsort((np.arange(len(kumeler)), anahtar[:, 1], anahtar[:, 0]))
    en_iyi, secim, kanit, cozulen = (np.inf, np.inf), None, True, 0
    for i in sira:
        sl, alt_t = anahtar[i]
        if sl > en_iyi[0] + _DEPO_TOL or (sl >= en_iyi[0] - _DEPO_TOL
                                         and alt_t > en_iyi[1] + _ESITLIK * max(1.0, abs(en_iyi[1]))):
            break
        if secim is not None and not _onde(alt_sinir, en_iyi):
            break                                   # alt sınıra erişildi: daha iyisi yok
        S = kumeler[i]
        yerel = np.argmin(C[:, S], axis=1)
        if not _asim(w, A, S[yerel], cap).any():
            deger, kesin = (0.0, float(C[np.arange(len(w)), S[yerel]].sum())), True
        else:
            if cozulen >= _MIP_EN_COK:
                kanit = False
                break
            yerel, asim, mal, kesin = _kisitli_ata(C[:, S], w, A[S], cap)
            deger, cozulen = (asim, mal), cozulen + 1
        if secim is None or _onde(deger, en_iyi):
            en_iyi, secim = deger, S[yerel]
        kanit = kanit and kesin
    return secim, kanit


def tasarla(egri: pd.DataFrame, agirlik: pd.Series, K: int | Literal["magaza"],
            depo_payi=None, *, adet: int = sabitler.PAKET_ADET, tohum: int = sabitler.TOHUM) -> Tasarim:
    """Mağaza eğrilerine (`egri`, satır `magaza_id`, sütun b1..b5, satırlar bire toplanır) K ortak
    desen ve atama; `depo_payi` [5] verilirse beden başına depo kısıtı (modül notu)."""
    if K != "magaza" and not (isinstance(K, (int, np.integer)) and K >= 1):
        raise ValueError(f"K pozitif tamsayı ya da 'magaza' olmalı: {K!r}")
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
    # atama anahtarı: sıfır ağırlıklı mağaza maliyete girmez, kendi eğrisine en yakın deseni alır
    Ca = np.where(w[:, None] > 0, C, D)

    kume_k = None if K == "magaza" else min(int(K), n)
    if kume_k is None:
        kume, en_iyi, yontem = np.arange(n), True, "tam"
    elif comb(n, kume_k) <= TAM_ARAMA_SINIRI:
        kume, en_iyi, yontem = _tam(C, kume_k), True, "tam"
    else:
        kume, en_iyi, yontem = _donusumlu(C, kume_k, tohum), False, "donusumlu"
    secim = kume[np.argmin(Ca[:, kume], axis=1)]
    toplam = float(C[np.arange(len(w)), secim].sum())
    if not en_iyi and _esit_ya_da_kucuk(toplam, float(C.min(axis=1).sum())):
        en_iyi = True                                    # mağazaya özel alt sınıra erişti
    yontem_k = yontem

    depo_uygun = depo_asimi = None
    if depo_payi is not None:
        cap = depo_payi * adet * w.sum()
        if _asim(w, A, secim, cap).any():
            yontem = "mip"
            ozel, asim, mal, ozel_kesin = _kisitli_ata(C, w, A, cap)   # mağazaya özel: alt sınır
            if kume_k is None or len(np.unique(ozel)) <= kume_k:
                secim, en_iyi = ozel, ozel_kesin
            elif yontem_k == "tam":
                secim, kesin = _kisitli_kume(C, w, A, cap, kume_k, (asim, mal))
                en_iyi = kesin and ozel_kesin
            else:                                        # dönüşümlü aramanın desenleriyle
                yerel = _kisitli_ata(C[:, kume], w, A[kume], cap)[0]
                secim, en_iyi = kume[yerel], False
            kullanilan = np.unique(secim)
            sifir = w == 0
            if sifir.any():
                secim[sifir] = kullanilan[np.argmin(D[np.ix_(sifir, kullanilan)], axis=1)]
        depo_asimi = _asim(w, A, secim, cap)
        depo_uygun = not depo_asimi.any()

    kullanilan = np.unique(secim)                    # aday indisleri sözlük sırasında
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
