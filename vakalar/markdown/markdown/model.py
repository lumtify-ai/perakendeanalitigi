"""Option başına haftalık dinamik program (spec §3.3).

Karar modülüdür: yalnız numpy ve `sabitler`; gizli gerçeğe ve ölçüm tarafına dokunmaz (AST kilidi).
Talep (`d`), satılabilir stok payları (`w`) ve fiyat çarpanları (`carpan`) dışarıdan dizi olarak gelir.

**Dinamik.** Haftalar t = 0..T-1 (karar pazartesisinden çıkışa). Durum (t, k, X): t. haftanın başında
yürürlükteki basamak k ve kalan stok X. X, 0'dan X0'a `kova` noktalı düzgün ızgarada tutulur; ara
değerlerde değer fonksiyonu doğrusal enterpole edilir. Karar k' >= k ve `izinli[t, k']`; izinli bir
k' >= k yoksa k' = k (kalınır: oran geri alınmaz, kural dışı basamak zorlanmaz).

    σ_t(k', X) = min(X, Σ_n min(X · w_n, d_t,n · carpan[t, k']))
    ödül       = σ · liste · (1 − etkin_oran[t, k']) · (1 − iade)
    V_T(k, X)  = kalinti · liste · X

Satış akışkandır (beklenen değer, rassal değil): X' = X − σ. Eşitlikte sığ basamak seçilir (derine
inmek için değerin göreli 1e-12'den fazla büyük olması gerekir); sonuç belirlenimcidir.

**Yol.** `Cozum.kademe`, X0 ve k0'dan başlayan beklenen (akışkan) yoldur. Yol boyunca karar her
haftanın karar-değeri (`Q`) eğrilerinden o haftanın gerçek X'inde enterpolasyonla yeniden seçilir
(ızgaraya yuvarlanmaz); ciro, satış ve kalan bu yoldan hesaplanır.
"""

from dataclasses import dataclass

import numpy as np

from .sabitler import KADEMELER, STOK_KOVA

_ESIT = 1e-12      # eşitlik sayılan göreli fark
_ORAN_PAYI = 1e-9  # merdivenle karşılaştırmada kayan nokta payı


@dataclass(frozen=True)
class Cozum:
    kademe: np.ndarray          # [T] int: beklenen yolda hafta başına basamak
    beklenen_satis: np.ndarray  # [T] beklenen yolda haftalık satış (adet)
    beklenen_ciro: float        # yolun toplam ödülü + kalıntı değeri (TL)
    beklenen_kalan: float       # çıkıştaki kalan stok X_T (adet)


def merdiven_indisi(oran: float) -> int:
    """KADEMELER'de `oran`ın üstündeki ya da eşit en yakın basamağın indisi; %70'in üstü %70."""
    for i, k in enumerate(KADEMELER):
        if oran <= k + _ORAN_PAYI:
            return i
    return len(KADEMELER) - 1


def haftalik_satis(X: np.ndarray, d: np.ndarray, w: np.ndarray, m: float) -> np.ndarray:
    """Bir haftada `σ = Σ_n min(X · w_n, d_n · m)`; dönüş [B] (X'in her değeri için).

    X: kova değerleri [B]; d: o haftanın hücre taban talebi [N]; w: satılabilir stok payı [N];
    m: fiyat çarpanı (kampanya dahil)."""
    X = np.asarray(X, float)
    return np.minimum(X[:, None] * w[None, :], (d * m)[None, :]).sum(axis=1)


def _satis_egrileri(X: np.ndarray, d: np.ndarray, w: np.ndarray, m: np.ndarray) -> np.ndarray:
    """`haftalik_satis`in her çarpan m için aynı değeri, O(K · B · log N): [K, B] (stokla sınırlı).

    Hücre n, X · w_n >= d_n · m iken talep sınırlıdır, yani X / m >= r_n = d_n / w_n. r_n çarpandan
    bağımsızdır: hücreleri bir kez r_n'ye göre sıralayıp birikimli toplamlarla her (m, X) için
    `m · Σ_{r_n <= X/m} d_n + X · Σ_{r_n > X/m} w_n` hesaplanır. Stok payı 0 olan hücre hiç satmaz."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(w > 0, d / w, np.inf)
    sira = np.argsort(r, kind="stable")
    r = r[sira]
    toplam_d = np.concatenate(([0.0], np.cumsum(d[sira])))
    toplam_w = np.concatenate(([0.0], np.cumsum(w[sira])))
    n = np.searchsorted(r, X[None, :] / m[:, None], side="right")     # talep sınırlı hücre sayısı
    sigma = m[:, None] * toplam_d[n] + X[None, :] * (toplam_w[-1] - toplam_w[n])
    return np.minimum(sigma, X[None, :])


def _satis_egrileri_hepsi(X: np.ndarray, d: np.ndarray, w: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Her hafta için `_satis_egrileri(X, d[t], w, m[t])`, toplu: [T, K, B] (aynı aritmetik).

    Satış eğrileri değer fonksiyonuna bağlı değildir; geri adımdan önce bir kez hesaplanır."""
    T = d.shape[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(w[None, :] > 0, d / w[None, :], np.inf)
    sira = np.argsort(r, axis=1, kind="stable")
    r = np.take_along_axis(r, sira, axis=1)
    sifir = np.zeros((T, 1))
    toplam_d = np.concatenate((sifir, np.cumsum(np.take_along_axis(d, sira, axis=1), axis=1)), axis=1)
    toplam_w = np.concatenate((sifir, np.cumsum(w[sira], axis=1)), axis=1)
    y = X[None, None, :] / m[:, :, None]                                        # [T, K, B]
    n = np.stack([np.searchsorted(r[t], y[t], side="right") for t in range(T)])  # talep sınırlı hücre
    satir = np.arange(T)[:, None, None]
    sigma = (m[:, :, None] * toplam_d[satir, n]
             + X[None, None, :] * (toplam_w[:, -1][:, None, None] - toplam_w[satir, n]))
    return np.minimum(sigma, X[None, None, :])


def _sec(Q: np.ndarray, aday: np.ndarray):
    """Her satır için adaylar arasından en büyük Q; eşitlikte sığ basamak.

    Q: [K, B] her basamağın karar değeri; aday: [R, K] bool, satır başına izinli basamaklar (her satırda
    en az bir True). Dönüş (seçilen değer [R, B], seçilen basamak [R, B]). Seçilen, en büyük değerin
    göreli `_ESIT` içindeki en sığ adaydır: derine inmek için değerin bundan fazla büyük olması gerekir."""
    maske = np.where(aday[:, :, None], Q[None], -np.inf)          # [R, K, B]
    en_buyuk = maske.max(axis=1, keepdims=True)
    yakin = maske >= en_buyuk - _ESIT * np.abs(en_buyuk)
    indis = yakin.argmax(axis=1)                                  # ilk True = en sığ
    R, _K, B = maske.shape
    return maske[np.arange(R)[:, None], indis, np.arange(B)[None, :]], indis


def _sec_tek(q: np.ndarray, aday: np.ndarray) -> int:
    """`_sec`in tek satır, tek stok noktası hâli (aynı kural): q [K], aday [K] -> basamak."""
    v = np.where(aday, q, -np.inf)
    en_buyuk = v.max()
    return int(np.argmax(v >= en_buyuk - _ESIT * abs(en_buyuk)))


def _interp_satirlar(x: float, xp: np.ndarray, F: np.ndarray) -> np.ndarray:
    """F'nin her satırı için `np.interp(x, xp, F[k])` (aynı formül ve uç kuralları), tek aramayla."""
    if x >= xp[-1]:
        return F[:, -1].copy()
    if x < xp[0]:
        return F[:, 0].copy()
    j = int(np.searchsorted(xp, x, side="right")) - 1
    if xp[j] == x:
        return F[:, j].copy()
    egim = (F[:, j + 1] - F[:, j]) / (xp[j + 1] - xp[j])
    return egim * (x - xp[j]) + F[:, j]


def _adaylar(izinli: np.ndarray) -> np.ndarray:
    """[T, K(k), K(k')] bool: k'dan derin, izinli basamaklar; hiçbiri yoksa k'nın kendisi (kalınır)."""
    K = izinli.shape[1]
    aday = izinli[:, None, :] & np.triu(np.ones((K, K), bool))[None]
    aday |= ~aday.any(axis=2)[:, :, None] & np.eye(K, dtype=bool)[None]
    return aday


def coz(d: np.ndarray, w: np.ndarray, X0: float, liste: float, carpan: np.ndarray,
        etkin_oran: np.ndarray, k0: int, izinli: np.ndarray, iade: float, kalinti: float,
        kova: int = STOK_KOVA) -> Cozum:
    """Haftalık dinamik programı çöz ve beklenen yolu döndür (modül docstring'ine bak).

    d: [T, N] hafta × hücre taban talebi; w: [N] satılabilir stok payı; X0: karar anındaki satılabilir
    stok; liste: liste fiyatı; carpan, etkin_oran, izinli: [T, K] hafta × basamak fiyat çarpanı
    (kampanya dahil), etkin oran ve izin maskesi; k0: yürürlükteki basamak; iade: iade payı;
    kalinti: çıkıştan sonra kalan birimin liste fiyatına oranla değeri; kova: stok ızgarası noktası."""
    d = np.asarray(d, float)
    w = np.asarray(w, float)
    carpan = np.asarray(carpan, float)
    etkin_oran = np.asarray(etkin_oran, float)
    izinli = np.asarray(izinli, bool)
    T, K = carpan.shape
    if d.shape[0] != T or etkin_oran.shape != (T, K) or izinli.shape != (T, K) or w.shape != d.shape[1:]:
        raise ValueError(f"boyutlar tutarsız: d {d.shape}, w {w.shape}, carpan {carpan.shape}, "
                         f"etkin_oran {etkin_oran.shape}, izinli {izinli.shape}")
    if not 0 <= k0 < K:
        raise ValueError(f"k0 = {k0} merdiven dışında (K = {K})")
    if kova < 2:
        raise ValueError("kova en az 2 olmalı")

    X0 = float(X0)
    # X0 = 0 iken ızgara bozulmasın diye ölçek 1; bütün X'ler zaten 0 kalır.
    izgara = np.linspace(0.0, X0 if X0 > 0 else 1.0, kova)
    birim = liste * (1.0 - iade)
    odul_orani = birim * (1.0 - etkin_oran)                        # [T, K] birim satış başına TL

    aday = _adaylar(izinli)
    V = np.tile(kalinti * liste * izgara, (K, 1))                  # V_T(k, ·) basamaktan bağımsız
    adim = izgara[-1] / (kova - 1)
    sat = np.arange(K)[:, None]
    Q = np.empty((T, K, kova))
    sigmalar = _satis_egrileri_hepsi(izgara, d, w, carpan) if T else np.zeros((0, K, kova))
    for t in range(T - 1, -1, -1):
        sigma = sigmalar[t]                                        # [K, B]
        kalan = np.minimum(np.maximum(izgara[None, :] - sigma, 0.0), izgara[-1]) / adim
        i = np.minimum(kalan.astype(int), kova - 2)                # doğrusal enterpolasyon, kova içi
        f = kalan - i
        Q[t] = sigma * odul_orani[t][:, None] + V[sat, i] * (1.0 - f) + V[sat, i + 1] * f
        V = _sec(Q[t], aday[t])[0]

    # Beklenen (akışkan) yol: her hafta Q eğrileri gerçek X'te enterpole edilerek yeniden seçilir.
    kademe = np.zeros(T, dtype=int)
    satis = np.zeros(T)
    X, k, ciro = X0, k0, 0.0
    for t in range(T):
        k = _sec_tek(_interp_satirlar(X, izgara, Q[t]), aday[t, k])
        sigma = min(X, float(haftalik_satis(np.array([X]), d[t], w, carpan[t, k])[0]))
        kademe[t], satis[t] = k, sigma
        ciro += sigma * odul_orani[t, k]
        X = max(X - sigma, 0.0)
    ciro += kalinti * liste * X
    return Cozum(kademe=kademe, beklenen_satis=satis, beklenen_ciro=float(ciro), beklenen_kalan=float(X))
