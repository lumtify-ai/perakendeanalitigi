"""Günün fiyatı, talep çekimi, satış, ikame, iade (hücre vektörel, saf
fonksiyonlar).

Rastgelelik (global kısıt): her gün her amaç (`talep`, `indirim`, `iade`,
`beden_ikame`, `ikame`) kendi sayaç üretecinden tam olarak bir `random(C)`
çeker — satış olsun olmasın, politika ne yaparsa yapsın. Bir hücrenin
talebi yalnız (u_talep[d, c], λ, fiyat oranı), işlem indirimi yalnız
(u_indirim[d, c]), iadesi yalnız (u_iade[d, c], gecikmeli satış) ile
belirlenir. İkame çekilişleri (`beden_ikame`, `ikame`) müşteri davranışıdır:
dünyanın tohumuyla çekilir.

Talep (spec §5.2): `oran_talep = max(markdown, kampanya)`; `λ = gerçek
λ(d) × (1 − oran_talep)^(−ε)`; `talep = PoissonTersCDF(u_talep, λ)`. Aynı
tekdüze sayı farklı fiyatta monoton olarak farklı talep verir; iki
markdown politikası aynı müşteri akışını görür. İşlem indirimi (tam
fiyatlı satışta rastgele, v3) yalnız satış sonrası fiyat indirimidir,
λ'ya girmez.
"""

import numpy as np
import pandas as pd

from .. import sabitler
from ..kampanya import fiyat_carpani, gunun_fiyati
from ..rastgele import binom_ters_cdf, poisson_ters_cdf, sayac_uretici

HAT_NORMAL, HAT_OUTLET, HAT_ONLINE = 0, 1, 2


def hat_indisi(hucre_online: np.ndarray, hucre_outlet_akisi: np.ndarray) -> np.ndarray:
    """[C] hücrenin fiyat hattı: 2 online (ONL), 1 outlet akışı hücresi
    (çıkıştan sonra outlet mağazasında satılan Collection), 0 diğerleri
    (outlet mağazasında normal pencereyle satılan Outlet line dahil: kendi
    indirim gününe göre normal markdown'ı izler)."""
    return np.where(
        hucre_online, HAT_ONLINE, np.where(hucre_outlet_akisi, HAT_OUTLET, HAT_NORMAL)
    ).astype(np.intp)


def tekduzeler(d: int, C: int, dunya_tohumu: int, operasyon_tohumu: int) -> dict[str, np.ndarray]:
    """Günün üç tekdüze dizisi, sabit sırayla ve her gün tam birer kez.
    Talep dünyanın tohumuyla (müşteri akışı dünyaya aittir), indirim ve
    iade operasyon tohumuyla çekilir."""
    return {
        "talep": sayac_uretici(d, "talep", dunya_tohumu).random(C),
        "indirim": sayac_uretici(d, "indirim", operasyon_tohumu).random(C),
        "iade": sayac_uretici(d, "iade", operasyon_tohumu).random(C),
    }


def talep_cek(u: np.ndarray, lam: np.ndarray, oran_talep: np.ndarray, eps: np.ndarray) -> np.ndarray:
    """[C] günlük talep: PoissonTersCDF(u, λ × fiyat çarpanı).

    Hız: F(0) = exp(−λ) ≥ u olan hücrelerin talebi 0'dır; ters CDF yalnız
    geri kalanlar için çalışır (sonuç birebir aynı)."""
    lam = np.asarray(lam, dtype=float)
    indirimli = oran_talep > 0
    if indirimli.any():
        lam = lam.copy()
        lam[indirimli] *= fiyat_carpani(oran_talep[indirimli], eps[indirimli])
    talep = np.zeros(len(u), dtype=np.int64)
    aday = np.flatnonzero(u > np.exp(-lam))
    if aday.size:
        talep[aday] = poisson_ters_cdf(u[aday], lam[aday])
    return talep


def gunun_birim_fiyati(liste: np.ndarray, md: np.ndarray, kamp: np.ndarray, u_indirim: np.ndarray):
    """(birim [C], uygulanan oran [C]): `kampanya.gunun_fiyati`; işlem
    indirimi u_indirim < ISLEM_INDIRIM_OLASILIGI ve oran 0 iken."""
    return gunun_fiyati(liste, md, kamp, u_indirim < sabitler.ISLEM_INDIRIM_OLASILIGI)


def satis_yap(talep: np.ndarray, stok: np.ndarray, depo: np.ndarray, onl: np.ndarray, hucre_sku: np.ndarray) -> np.ndarray:
    """[C] satılan: fiziksel hücre rafından `min(talep, stok)`; ONL hücresi
    depodan `min(talep, depo[sku])` (ONL'de SKU başına tek hücre)."""
    kullanilabilir = np.where(onl, depo[hucre_sku], stok)
    return np.minimum(talep, kullanilabilir)


def iade_cek(u: np.ndarray, n: np.ndarray, p: np.ndarray) -> np.ndarray:
    """[C] iade adedi: Binomial(n, p)'nin ters CDF'i (yalnız n > 0)."""
    iade = np.zeros(len(n), dtype=np.int64)
    aday = np.flatnonzero(n > 0)
    if aday.size:
        iade[aday] = binom_ters_cdf(u[aday], n[aday], p[aday])
    return iade


# ---------------------------------------------------------------------------
# İkame (spec §5.4)
# ---------------------------------------------------------------------------


def _grup_en_buyuk_kalan(x: np.ndarray, grup: np.ndarray, hedef: np.ndarray) -> np.ndarray:
    """Grup içinde en büyük kalan: her eleman ⌊x⌋ alır, grubun `hedef`ine
    kalan adetler kesri en büyük (eşitlikte küçük indis) elemanlara birer
    birer verilir; kesri 0 olan eleman artık almaz. `grup` yoğun indis."""
    taban = np.floor(x + 1e-9).astype(np.int64)
    kalan = np.asarray(hedef, dtype=np.int64) - np.bincount(grup, taban, minlength=len(hedef)).astype(np.int64)
    kesir = x - taban
    sira = np.lexsort((np.arange(len(x)), -kesir, grup))
    g_sirali = grup[sira]
    rutbe = np.arange(len(sira)) - np.searchsorted(g_sirali, g_sirali, side="left")
    ver = (kesir[sira] > 1e-9) & (rutbe < np.maximum(kalan, 0)[g_sirali])
    taban[sira[ver]] += 1
    return taban


def _ikame_yapisi(dunya) -> dict:
    """Dünya başına bir kez kurulan ikame yapısı (dünyanın önbelleğinde):
    komşu beden hücreleri (aynı mağaza, aynı option, beden sırası ±1; yoksa
    −1), (mağaza, alt kategori, fiyat segmenti) grubu, grup × option alt
    grubu ve alt kategorinin ikame payı."""
    onbellek = dunya._onbellek
    if "ikame" in onbellek:
        return onbellek["ikame"]
    hm = np.asarray(dunya.hucre_magaza, dtype=np.int64)
    hs = np.asarray(dunya.hucre_sku, dtype=np.int64)
    ho = np.asarray(dunya.hucre_option, dtype=np.int64)
    S = len(dunya.urunler)
    sira = dunya.urunler["beden_sira"].to_numpy().astype(np.int64)
    sku_option = np.asarray(dunya.sku_option, dtype=np.int64)
    K = int(sira.max()) + 2

    # (option, beden sırası) → SKU; (mağaza, SKU) → hücre
    os_anahtar = sku_option * K + sira
    os_sira = np.argsort(os_anahtar, kind="stable")
    os_sirali = os_anahtar[os_sira]
    hc_anahtar = hm * S + hs
    hc_sira = np.argsort(hc_anahtar, kind="stable")
    hc_sirali = hc_anahtar[hc_sira]

    def ara(sirali, sirasi, k):
        i = np.minimum(np.searchsorted(sirali, k), len(sirali) - 1)
        return np.where(sirali[i] == k, sirasi[i], -1)

    def komsu(adim: int) -> np.ndarray:
        s2 = ara(os_sirali, os_sira, sku_option[hs] * K + sira[hs] + adim)
        c2 = ara(hc_sirali, hc_sira, hm * S + np.maximum(s2, 0))
        return np.where(s2 >= 0, c2, -1)

    opt = dunya.optionlar
    ak = opt["alt_kategori"].to_numpy()
    anahtar = np.stack([
        hm,
        pd.factorize(ak)[0][ho],
        pd.factorize(opt["fiyat_segmenti"].to_numpy())[0][ho],
    ])
    _, grup = np.unique(anahtar, axis=1, return_inverse=True)
    grup = grup.ravel().astype(np.int64)
    _, alt_grup = np.unique(np.stack([grup, ho]), axis=1, return_inverse=True)
    alt_grup = alt_grup.ravel().astype(np.int64)
    alt_grup_grubu = np.zeros(int(alt_grup.max()) + 1, dtype=np.int64)
    alt_grup_grubu[alt_grup] = grup
    yapi = {
        "buyuk": komsu(+1), "kucuk": komsu(-1),
        "grup": grup, "grup_sayisi": int(grup.max()) + 1,
        "alt_grup": alt_grup, "alt_grup_grubu": alt_grup_grubu,
        "pay": pd.Series(ak).map(sabitler.IKAME_PAYI).to_numpy(dtype=float)[ho],
    }
    assert not np.isnan(yapi["pay"]).any(), "IKAME_PAYI eksik alt kategori"
    onbellek["ikame"] = yapi
    return yapi


def ikame(stok_sonrasi: np.ndarray, kayip: np.ndarray, dunya, d: int, lam: np.ndarray | None = None):
    """Stoksuzluğun karşılanmamış talebini ikameye çevirir; tek tur.

    `stok_sonrasi` [C] bugünkü birincil satıştan sonra hücrenin satabileceği
    stok (fiziksel: raf; ONL: depo[sku]); `kayip` [C] birincil satışın
    karşılayamadığı talep; `lam` [C] bugünün gerçek λ'sı (verilmezse
    `dunya.lam.gun(d)`), alıcı ağırlığıdır (çekicilik × beden payı zaten
    içindedir; penceresi kapalı ya da mağazası kapalı hücrede 0 → alıcı
    olamaz).

    1. Beden ikamesi: `n = Binom(kayip, BEDEN_IKAME_ORANI)` (sayaç
       "beden_ikame"); aynı mağaza ve option'da önce bir büyük, sonra bir
       küçük beden (beden sırası ±1) stoğundan satılır.
    2. Kategori ikamesi: `n2 = Binom(kayip − beden ikamesiyle satılan,
       IKAME_PAYI[alt kategori])` (sayaç "ikame"). Grup = (mağaza, alt
       kategori, fiyat segmenti). Her kaynak option'ın n2'si grubun stoğu
       olan (> 0), λ'sı olan, **başka option'lardaki** hücrelerine λ
       ağırlığıyla bölünür; grup toplamı en büyük kalanla tam sayıya
       çevrilir ve alıcının stoğuyla kesilir. Sığmayan kaybolur (tek tur:
       yeniden dağıtılmaz). Kurtarılan adet grubun kaynak hücrelerine n2
       payıyla (en büyük kalan) yazılır.

    Döner: (`ikame_satis` [C] alıcı hücrenin ikameyle sattığı adet,
    `gizli_kayip` [C] kaynak hücrenin kalıcı kaybı). Σ ikame_satis +
    Σ gizli_kayip = Σ kayip; ikame_satis ≤ stok_sonrasi. Her gün iki
    sayaçtan tam birer `random(C)` çekilir (politikadan bağımsız).
    """
    C = len(kayip)
    kayip = np.asarray(kayip, dtype=np.int64)
    u1 = sayac_uretici(d, "beden_ikame", dunya.tohum).random(C)
    u2 = sayac_uretici(d, "ikame", dunya.tohum).random(C)
    satis = np.zeros(C, dtype=np.int64)
    kurtarilan = np.zeros(C, dtype=np.int64)
    kaynak = np.flatnonzero(kayip > 0)
    if kaynak.size == 0:
        return satis, kayip.copy()
    y = _ikame_yapisi(dunya)
    if lam is None:
        lam = dunya.lam.gun(d)
    stok = np.asarray(stok_sonrasi, dtype=np.int64).copy()

    # (1) Beden ikamesi: her geçişte bir alıcının en çok bir kaynağı var
    # (büyük geçişte sıra−1 komşusu, küçükte sıra+1 komşusu): çakışma yok.
    n = binom_ters_cdf(u1[kaynak], kayip[kaynak], sabitler.BEDEN_IKAME_ORANI)
    for yon in ("buyuk", "kucuk"):
        r = y[yon][kaynak]
        m = (n > 0) & (r >= 0)
        if not m.any():
            continue
        rr = r[m]
        a = np.where(lam[rr] > 0, np.minimum(n[m], stok[rr]), 0)
        stok[rr] -= a
        satis[rr] += a
        n[m] -= a
        kurtarilan[kaynak[m]] += a

    # (2) Kategori ikamesi
    kalan = kayip[kaynak] - kurtarilan[kaynak]
    n2 = np.zeros(C, dtype=np.int64)
    n2[kaynak] = binom_ters_cdf(u2[kaynak], kalan, y["pay"][kaynak])
    if n2.sum() == 0:
        return satis, kayip - kurtarilan
    grup, alt, G = y["grup"], y["alt_grup"], y["grup_sayisi"]
    ag = y["alt_grup_grubu"]
    A = len(ag)
    alici = (stok > 0) & (lam > 0)
    W_g = np.bincount(grup[alici], lam[alici], minlength=G)
    W_a = np.bincount(alt[alici], lam[alici], minlength=A)
    N_a = np.bincount(alt, n2, minlength=A).astype(np.int64)
    payda = W_g[ag] - W_a                                  # başka option'ların ağırlığı
    gecerli = (N_a > 0) & (payda > 1e-9 * W_g[ag]) & (payda > 0)
    oran_a = np.zeros(A)
    oran_a[gecerli] = N_a[gecerli] / payda[gecerli]
    A_g = np.bincount(ag, oran_a, minlength=G)
    T_g = np.bincount(ag, np.where(gecerli, N_a, 0), minlength=G).astype(np.int64)
    ai = np.flatnonzero(alici & (T_g[grup] > 0))
    if ai.size == 0:
        return satis, kayip - kurtarilan
    x = lam[ai] * np.maximum(A_g[grup[ai]] - oran_a[alt[ai]], 0.0)
    gi, gy = np.unique(grup[ai], return_inverse=True)
    a = np.minimum(_grup_en_buyuk_kalan(x, gy.ravel(), T_g[gi]), stok[ai])
    satis[ai] += a
    S_g = np.bincount(grup[ai], a, minlength=G).astype(np.int64)
    # Kurtarılanı kaynaklara n2 payıyla dağıt (yalnız alıcısı olan alt gruplar)
    k = np.flatnonzero((n2 > 0) & gecerli[alt] & (S_g[grup] > 0))
    if k.size:
        gi, gy = np.unique(grup[k], return_inverse=True)
        pay = n2[k] * S_g[grup[k]] / T_g[grup[k]]
        kurtarilan[k] += _grup_en_buyuk_kalan(pay, gy.ravel(), S_g[gi])
    return satis, kayip - kurtarilan
