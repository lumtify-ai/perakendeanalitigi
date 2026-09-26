"""Ne kadar RPT: üç miktar kuralı.

    banu        ilk alımın %50'si, en az MOQ (v3'teki Lumoda kuralı)
    frr         Fisher–Rajaram–Raman (2001) perakendecisinin kuralı:
                Q2 = ((1 − ω) · x_k / k_k − Q1)⁺ — çıplak satış, çıplak eğri.
                ω iade oranı. Q2 MOQ'nun yarısından küçükse sipariş yok,
                değilse en az MOQ (FRR'de MOQ yok; bizim eklememiz).
    newsvendor  gelişten sonra kalan talebin dağılımı üstünde beklenen kârı
                en büyükleyen miktar (aşağıda).

NEWSVENDOR. Karar pazartesisi h, tedarik süresi L, geliş a = h + L.
Sezon talebi kestirimi d katmanıdır (Faz A): Ŝ = D_h / k_h, tam fiyat
penceresi için indirim eğrisiyle, indirim dönemi için çıkış eğrisiyle.
Belirsizlik çarpımsaldır: S = Ŝ · exp(ε), ε ~ N(μ_h, σ_h); μ ve σ yalnız
oyun sezonundan önce kapanmış sezonlardaki kestirim hatasından
(log(gerçek / kestirim)) öğrenilir (`kalibrasyon`). Dağılım 200 sabit
kantil noktasıyla temsil edilir (deterministik).

    B    = geliş öncesi talep = S_cx · (k_cx(a) − k_cx(h))
    C0   = gelişte elde kalacak stok = (envanter pozisyonu − B)⁺
           envanter pozisyonu = depo + mağaza stoğu + açık siparişler
    Xtf  = gelişten indirime tam fiyat talebi = S_io · (1 − k_io(a))
    Xind = indirim dönemi talebi (gelişten sonra) = S_cx · (1 − k_cx(max(a, W)))
    Q'nun tam fiyat satışı  tf  = min(Q, (Xtf − C0)⁺)
    indirimli satışı        ind = min(Q − tf, (Xind − (C0 − Xtf)⁺)⁺)
    kâr = p · tf + p_ind · ind − c · Q      (çıkışta kalan 0 değerli)

Az alma maliyeti Cu = p − c (tam fiyat marjı), fazla alma maliyeti
Co = c − p_ind (indirimde satılırsa) ya da c (hiç satılmazsa); formül bu iki
maliyeti senaryolar üstünden kendisi tartar. p_ind, option'ın indirim
dönemindeki planlı fiyatının plan talebiyle ağırlıklı ortalamasıdır (plan
ve indirim takvimi önceden bilinir).

MOQ KAPISI. En iyi Q MOQ'dan küçükse MOQ'nun beklenen kârı pozitifse MOQ,
değilse sipariş yok. Ayrıca MOQ'nun yarısını tam fiyattan satması
beklenmeyen sipariş verilmez: aday modelinin etiketi ve olcutler'in "yanlış
alarm" tanımı aynı eşiktir (tutarlılık).

Bilinen sadeleştirmeler: mağazalar arası dağılım (sıkışan stok) ve iade
yok sayılır; teslim sapması yok sayılır (planlanan geliş).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from perakende_veri.v3 import sabitler as v3s
from perakende_veri.v3.tedarik import moq_yuvarla
from scipy.stats import norm

from . import egri, kaynak, sansur

KANTIL = 200
_Z = norm.ppf((np.arange(KANTIL) + 0.5) / KANTIL)
ADIM = v3s.YUVARLAMA_ADET
IADE_ORANI = v3s.IADE_ORANI
KALIBRASYON_HAFTALARI = (2, 3, 4, 5, 6)


def banu(ilk_alim: float, moq: int, oran: float = v3s.RPT_MIKTAR_ORANI) -> int:
    return moq_yuvarla(oran * ilk_alim, moq)


def frr(x: float, k: float, ilk_alim: float, moq: int, omega: float = IADE_ORANI) -> int:
    if k <= 0:
        return 0
    q2 = max((1 - omega) * x / k - ilk_alim, 0.0)
    return moq_yuvarla(q2, moq) if q2 >= moq / 2 else 0


def indirim_fiyatlari(dunya) -> np.ndarray:
    """[O] indirim dönemi beklenen fiyatı (plan talebiyle ağırlıklı)."""
    opt = dunya.optionlar
    O = len(opt)
    D = dunya.gun_sayisi + 200
    g = dunya.g_plan[:D]
    oran = dunya.indirim_orani[:D]
    gun = np.arange(len(g))[:, None]
    ind = (gun >= opt["indirim_gun"].to_numpy()[None, :]) & (gun < opt["cikis_gun"].to_numpy()[None, :])
    w = np.where(ind, g, 0.0)
    ort = np.divide((w * (1 - oran)).sum(0), w.sum(0), out=np.full(O, 0.5), where=w.sum(0) > 0)
    return opt["liste_fiyati"].to_numpy() * ort


@dataclass(frozen=True)
class Belirsizlik:
    mu: dict      # h → ortalama log(gerçek / kestirim)
    sigma: dict   # h → std
    n: dict
    sezonlar: tuple

    def al(self, h: float):
        hs = sorted(self.mu)
        k = min(hs, key=lambda x: abs(x - h))
        return self.mu[k], self.sigma[k]


def kalibrasyon(t: dict, opt_t: pd.DataFrame, oyun_sezonu: str, hh: pd.DataFrame | None = None,
                egriler: dict | None = None) -> Belirsizlik:
    """Oyun sezonundan önceki tam sezonlarda d katmanının log hatası.

    Geçmiş sezon P'nin kestirimi, P'nin kendi oyun eğrisiyle (P'den önceki
    sezonlardan) yapılır; P'nin öncesi yoksa (SS24) oyun sezonunun eğrisi
    kullanılır — örneklem içi, σ'yı biraz iyimser yapar (README).
    `hh` tablolar oyun başlangıcına kırpılmadan kurulmuş olabilir: yalnız
    geçmiş sezonların satırları okunur, hepsi oyun başlamadan kapanmıştır.
    """
    gecmis = egri.gecmis_sezonlar(t, oyun_sezonu)
    bas = kaynak.sezon_baslangici(t, oyun_sezonu)
    kirpik = kaynak.tarihten_once(t, bas)
    if hh is None:
        hh = kaynak.hucre_hafta(kirpik, opt_t, gecmis)
    egriler = egriler or {}

    def _egri(sezon, yontem):
        anahtar = (sezon, yontem)
        if anahtar not in egriler:
            egriler[anahtar] = egri.oyun_egrisi(t, opt_t, sezon, yontem)
        return egriler[anahtar]

    parca = []
    for P in gecmis:
        kaynak_sezon = P if egri.gecmis_sezonlar(t, P) else oyun_sezonu
        o = opt_t[(opt_t["sezon_kodu"] == P) & (opt_t["line"] == "Collection")]
        h_ = hh[hh["option_id"].isin(o["option_id"])]
        g = sansur.gercek_talep(h_)
        for h in KALIBRASYON_HAFTALARI:
            k = sansur.kestir(h_, o, h, _egri(kaynak_sezon, "ham"), _egri(kaynak_sezon, "duzeltilmis"))
            k = k.merge(g, on="option_id")
            k = k[(k["d"] > 0) & (k["gercek_io"] > 0)]
            parca.append(pd.DataFrame({"h": h, "r": np.log(k["gercek_io"] / k["d"])}))
    r = pd.concat(parca)
    ozet = r.groupby("h")["r"].agg(["mean", "std", "size"])
    return Belirsizlik(mu=ozet["mean"].to_dict(), sigma=ozet["std"].to_dict(),
                       n=ozet["size"].to_dict(), sezonlar=gecmis)


def senaryolar(D, h, L, W, egri_io, egri_cx, dalga, mu, sigma):
    """Senaryo başına (B, Xtf, Xind) dizileri."""
    k_io, k_cx = egri_io.k((dalga,), h), egri_cx.k((dalga,), h)
    m = np.exp(mu + sigma * _Z)
    S_io = D / max(k_io, 1e-6) * m
    S_cx = D / max(k_cx, 1e-6) * m
    a = h + L
    B = S_cx * (egri_cx.k((dalga,), a) - k_cx)
    Xtf = S_io * (1 - egri_io.k((dalga,), a))
    Xind = S_cx * (1 - egri_cx.k((dalga,), max(a, W)))
    return B, Xtf, Xind


def kar_egrisi(Q: np.ndarray, B, Xtf, Xind, ip, p, p_ind, c):
    """Q ızgarası için beklenen (tam fiyat satış, indirimli satış, kâr)."""
    C0 = np.maximum(ip - B, 0.0)
    C1 = np.maximum(C0 - Xtf, 0.0)
    ihtiyac_tf = np.maximum(Xtf - C0, 0.0)[None, :]
    ihtiyac_ind = np.maximum(Xind - C1, 0.0)[None, :]
    Qm = Q[:, None].astype(float)
    tf = np.minimum(Qm, ihtiyac_tf)
    ind = np.minimum(Qm - tf, ihtiyac_ind)
    kar = p * tf + p_ind * ind - c * Qm
    return tf.mean(1), ind.mean(1), kar.mean(1)


def newsvendor(D, h, L, W, egri_io, egri_cx, dalga, ip, p, c, p_ind, mu, sigma, moq,
               ust: float | None = None) -> dict:
    """Beklenen kârı en büyük RPT miktarı (MOQ kapılı). Sözlük döndürür."""
    B, Xtf, Xind = senaryolar(D, h, L, W, egri_io, egri_cx, dalga, mu, sigma)
    ust = ust if ust is not None else max(np.percentile(Xtf + Xind, 99), moq) + ADIM
    Q = np.arange(0, int(ust) + ADIM, ADIM)
    tf, ind, kar = kar_egrisi(Q, B, Xtf, Xind, ip, p, p_ind, c)
    i = int(np.argmax(kar))
    q = int(Q[i])
    if 0 < q < moq:
        j = int(np.searchsorted(Q, moq))
        q = moq if j < len(Q) and kar[j] > 0 else 0
    if q > 0:
        j = int(np.searchsorted(Q, q))
        if tf[j] < moq / 2:
            q = 0
    j = int(np.searchsorted(Q, q))
    return {"q": q, "q_serbest": int(Q[i]), "beklenen_tf": float(tf[j]), "beklenen_ind": float(ind[j]),
            "beklenen_kar": float(kar[j]), "ip": float(ip), "Xtf": float(np.mean(Xtf)),
            "Xind": float(np.mean(Xind)), "B": float(np.mean(B))}
