"""Günlük ayrıştırma, satış (spec §3 adım 1–3): gün d'nin pozitif satışını
fişlere, fişleri müşterilere dağıtır. İade, işlem indirimi yerleşimi ve boş
ziyaret `iade.py`'dedir (Görev 6).

**Akış** (bütün mağazalar birlikte; birimler hiç açılmaz, sayımla çalışılır):

1. Satış satırı = (mağaza, SKU) hattı, `c` adet. Grup = (mağaza, tip, ürün
   cinsiyeti, indirimli); tip `tercih.tip_kodu` (alt kategori × fiyat
   segmenti × beden sırası; aksesuar STD; 306 tip), ürün cinsiyeti
   `tercih.urun_cinsiyet` (Kadın, Erkek, Unisex; Görev 5b), indirimli = A
   satırının `indirim_tutari > 0` (markdown, kampanya ya da işlem; A'da
   hücre-gün başına tek durum; Görev 5c).
2. Fiş sayısı `F_m = max(1, round(U_m / sepet_hedef_m), ⌈U_m / 8⌉)`
   (mağaza 2,2, ONL 1,8; Black Friday günlerinde hedef ×1,3), `F_m ≤ U_m`.
3. Ziyaretçi: `ziyaretci.ziyaretci_sec` (artımlı aday yapısı, ağırlıkla
   ardışık örnekleme; eksikse yeni müşteri), mağaza başına kadın ziyaretçi
   kotasıyla (`kadin_hedefi`: günün o mağazadaki Kadın / (Kadın + Erkek)
   birim payı + `KADIN_HEDIYE_DUZELTME`, rastgele yuvarlama; Görev 5b).
4. Fiş boyutu: her fiş ≥ 1; ek `U_m − F_m` adet ağırlık `(sepet_ort − 1) ×
   Gamma(1, 1)` (üstel, çarpık; müşterinin sepetine bağlı) ile en büyük kalanla
   dağıtılır, 8'i aşan fazla kapasitesi olan fişlere yeniden dağıtılır.
5. **Aşama 1, grup düzeyinde kesin** (`asama1`): puan birimde yalnız gruba
   bağlı (`tercih.tip_puani`: alt kategori, fiyat segmenti, beden uyumu; +
   `tercih.cinsiyet_terimi`: müşteri × ürün cinsiyeti; +
   `tercih.indirim_terimi`: `INDIRIM_AGIRLIGI` × müşterinin indirim
   duyarlılığı, grup indirimliyse; Görev 5c); aynı gruptaki n boş
   birimin Gumbel-max'ı = grup puanı + log n + tek Gumbel. Tip puanı [F ×
   306] cinsiyetsiz hesaplanır, cinsiyet terimi çift başına bir tablo
   okuması (Görev 5b: cinsiyet tipe katılsaydı tip puanı matrisi üç kat
   büyürdü; grup anahtarına katmak aşama 2'yi cinsiyet-saf bırakır).
   İndirim durumu da aynı yolla anahtardadır (tip puanı değişmez; çift
   başına bir çarpım).
   - Çapa: açık fiş × mağazasının grupları, puan + log(kalan) + Gumbel; her
     fiş en iyi grubunu ister, çakışmada grubun kalanı kadar en yüksek fiş
     kazanır; 2.–5. turlar yalnız açık fişler, sonra mağazanın boş
     birimlerinden rastgele.
   - Tamamlayıcı: bekleyen birimin en iyi fişi = grubun kapasiteli fişler
     üzerindeki softmax(puan + tamamlayıcılık(fiş sepeti))'ından kategorik
     çekiliş (Gumbel-max'a eşdeğer), kazanan değeri lse + Gumbel. Dalga:
     bir turda fiş başına en çok `TAMAMLAYICI_DALGA` (1) birim, en yüksek
     değerli istek kabul edilir, diğerleri sonraki tura; böylece sonraki
     birimler sepete yeni girenlerle tamamlayıcılığı görür (hepsi aynı
     turda yerleşseydi yalnız çapayı görürdü). `TAMAMLAYICI_TUR` (8)
     dalga turunun sonuncusu ve ardından `TAMAMLAYICI_ARTIK_TUR` (4) artık
     tur yalnız fiş kapasitesiyle sınırlı; artık turlarda fiş seçimine
     log(kalan kapasite) eklenir (birim kapasite yuvaları üzerinden
     Gumbel-max gibi). Rastgele yerleşim yalnız son çare. Her tur yalnız bekleyen birimler × kapasiteli fişler; sepet
     ve tamamlayıcılık her turda güncel. Tamamlayıcılık = sepet sayımı @
     `tamamlayici_matris()` (= `tercih.tamamlayicilik`).
   - Turlar arasında Gumbel yeniden çekilir (birim başına sabit Gumbel'li
     yoğun sürümden farkı yalnız taşan birim/fişlerin koşullu dağılımında;
     Görev 1 raporu).
6. **Aşama 2, tip içinde SKU** (`asama2`): (fiş, grup) başına k birim
   grubun hatlarından kategorik çekilir, logit = `tercih.sku_ek_puani`
   (kalıp, desen, indirim duyarlılığı × SKU-gün oranı — grup indirim
   durumunda saf olduğundan indirimli grupta derinlik tercihi olarak kalır)
   + tekrar alım bonusu
   (müşterinin son 8 option'ında: +0,8, Basic/NOS +1,2) + log(kalan c).
   Hatta kalandan fazla istek düşerse değeri (lse + Gumbel) en yüksek
   istekler kazanır; ≤ 5 tur, sonra grup içinde rastgele.
7. (fiş, hat) satırları; tutar ve indirim_tutari A'nın satır tutarından
   adetle orantılı, kuruş düzeyinde en büyük kalanla (toplam kuruşu
   kuruşuna A). A'da işlem indirimi hücre-gün başına ya hep ya hiç
   olduğundan (Görev 1) birim fiyat satır içinde tektir; `islem_adet`
   Görev 6'nın yer tutucusudur (0).
8. Fiş saati (dakika): mağaza hafta içi 19:00, hafta sonu 15:30 tepeli;
   ONL 24 saat, 21:00 tepeli.
9. Tekrar alım tamponu güncellenir.

Durum (`AyristirDurum`: ürün dizileri, aday yapısı, tekrar tamponu)
`kayit.durum`'da yaşar, ilk çağrıda kurulur. Rastgelelik:
`crm_uretici(d, "ziyaret")` ziyaretçi + yeni müşteri; `"atama"` akışının
adım başına alt akışları (`crm_alt_ureticiler`: boyut, asama1, asama2,
saat) — bir adımın kalibrasyonu diğerlerinin çekilişlerini kaydırmaz.
"""

import time
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

from .. import sabitler as a_sabitler
from ..takvim import gun_indisi
from . import sabitler as S
from .girdi import ADET, H, INDIRIM, KAMPANYA, ORAN, SATIR, TUTAR
from .rastgele import crm_alt_ureticiler, crm_uretici
from .tercih import (
    BEDEN_YONU, N_TIP, URUN_CINSIYET_SAYISI, cinsiyet_ceza_tablosu, indirim_terimi, sku_ek_puani_cift,
    sku_kodlari, tamamlayici_matris, tip_kodu, tip_ozellik, tip_puani, urun_cinsiyet,
)
from .ziyaretci import Adaylar, ziyaretci_sec

TUR = S.ESLESTIRME_TUR
ATAMA_ADIMLARI = ("boyut", "asama1", "asama2", "saat")   # yeni adım SONA
TAMAM_TUR = S.TAMAMLAYICI_TUR
ARTIK_TUR = S.TAMAMLAYICI_ARTIK_TUR
DALGA = S.TAMAMLAYICI_DALGA
A_ALT = len(S.ALT_KATEGORILER)
#: Ziyaretçi cinsiyet kotası açık mı (Görev 5b). YALNIZ ÖLÇÜM içindir
#: (kotasız karşılaştırma, araclar/v4_crm_hiz.py --kotasiz); üretim hep True.
ZIYARETCI_KOTASI = True
N_TC = N_TIP * URUN_CINSIYET_SAYISI      # tip × ürün cinsiyeti (boş ziyaret grubu, iade.py)
N_TCI = N_TC * 2                         # aşama 1 grup anahtarının mağaza-içi kısmı: × indirimli (Görev 5c)


# ---------------------------------------------------------------------------
# Vektörel yardımcılar
# ---------------------------------------------------------------------------


def segment_ici(uzunluk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Segment uzunluklarından (segment no, segment içi sıra) düz dizileri."""
    uzunluk = np.asarray(uzunluk, dtype=np.int64)
    seg = np.repeat(np.arange(len(uzunluk)), uzunluk)
    bas = np.cumsum(uzunluk) - uzunluk
    return seg, np.arange(len(seg)) - bas[seg]


def segment_argmax(deger: np.ndarray, uzunluk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bitişik segmentlerde (uzunluk > 0) en büyük değerin konumu ve değeri."""
    bas = np.cumsum(uzunluk) - uzunluk
    enb = np.maximum.reduceat(deger, bas)
    esit = np.flatnonzero(deger == np.repeat(enb, uzunluk))
    seg = np.searchsorted(bas, esit, side="right") - 1
    ilk = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
    return esit[ilk], enb


def segment_kategorik(logit: np.ndarray, uzunluk: np.ndarray, tekrar: np.ndarray, rng):
    """Bitişik segmentlerin her birinde softmax(logit)'ten `tekrar[s]`
    bağımsız çekiliş: (seçilen konumlar [Σ tekrar], segment lse). Gumbel-max
    ile aynı dağılım: argmax_i(logit_i + G_i) ~ softmax, en büyük değer
    ~ lse + Gumbel (argmax'tan bağımsız). Logitler sonlu olmalı."""
    uzunluk = np.asarray(uzunluk, dtype=np.int64)
    bas = np.cumsum(uzunluk) - uzunluk
    mx = np.maximum.reduceat(logit, bas).astype(np.float64)
    w = np.exp(logit.astype(np.float64) - np.repeat(mx, uzunluk))
    C = np.cumsum(w)
    toplam = np.add.reduceat(w, bas)
    alt = C[bas + uzunluk - 1] - toplam
    seg = np.repeat(np.arange(len(uzunluk)), tekrar)
    x = alt[seg] + rng.random(len(seg)) * toplam[seg]
    pos = np.clip(np.searchsorted(C, x, side="right"), bas[seg], bas[seg] + uzunluk[seg] - 1)
    return pos, mx + np.log(toplam)


def gumbel32(rng, n: int) -> np.ndarray:
    """[n] standart Gumbel, float32 (−log(−log U), U float32; U = 0 en küçük
    pozitif float32'ye kırpılır). Çift başına float64 `rng.gumbel`'den ~3
    kat ucuz; puanlar zaten float32."""
    u = rng.random(n, dtype=np.float32)
    np.maximum(u, np.finfo(np.float32).tiny, out=u)
    np.log(u, out=u)
    np.negative(u, out=u)
    np.log(u, out=u)
    np.negative(u, out=u)
    return u


def grup_en_buyuk_kalan(agirlik: np.ndarray, grup: np.ndarray, hedef: np.ndarray) -> np.ndarray:
    """Grup içinde `hedef[g]` (tam sayı) ağırlıkla orantılı tam sayılara
    böler (en büyük kalan). Toplam ağırlığı 0 olan grubun hedefi 0 olmalı."""
    hedef = np.asarray(hedef, dtype=np.int64)
    top = np.bincount(grup, agirlik, minlength=len(hedef))
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.where(top[grup] > 0, agirlik / top[grup], 0.0) * hedef[grup]
    taban = np.floor(x).astype(np.int64)
    kalan = hedef - np.bincount(grup, taban, minlength=len(hedef))
    sira = np.lexsort((-(x - taban), grup))
    g = grup[sira]
    rutbe = np.arange(len(sira)) - np.searchsorted(g, g, side="left")
    taban[sira[rutbe < kalan[g]]] += 1
    return taban


def grup_ici_karistir(grup: np.ndarray, rng) -> np.ndarray:
    """Gruba göre sıralı, grup içinde rastgele permütasyon indisi."""
    return np.lexsort((rng.random(len(grup)), grup))


def grup_ici_es(sol_grup: np.ndarray, sag_grup: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """İki çoklu kümeyi grup içinde rastgele eşler (grup başına sayılar
    eşit olmalı): (sol sıra, sağ sıra) — sol[a[i]] ile sag[b[i]] eş."""
    a = np.argsort(sol_grup, kind="stable")
    b = grup_ici_karistir(sag_grup, rng)
    assert (sol_grup[a] == sag_grup[b]).all()
    return a, b


# ---------------------------------------------------------------------------
# Fiş sayısı ve boyutu
# ---------------------------------------------------------------------------


def fis_sayisi(U_m: np.ndarray, onl_m: np.ndarray, bf: bool) -> np.ndarray:
    """[M] F_m = max(1, round(U_m / hedef), ⌈U_m / 8⌉), en çok U_m; satışsız 0."""
    U_m = np.asarray(U_m, dtype=np.int64)
    hedef = np.where(onl_m, S.SEPET_HEDEF_ONLINE, S.SEPET_HEDEF_MAGAZA) * (S.SEPET_BF_CARPANI if bf else 1.0)
    F = np.maximum(np.maximum(1, np.rint(U_m / hedef)), np.ceil(U_m / S.FIS_EN_COK))
    return np.where(U_m > 0, np.minimum(F, U_m), 0).astype(np.int64)


def fis_boyutlari(rng, fis_m: np.ndarray, U_m: np.ndarray, sepet_f: np.ndarray) -> np.ndarray:
    """[F] fiş boyutu (1–8), mağaza içinde toplam U_m. Ek adet ağırlığı
    (sepet_ort − 1) × Gamma(FIS_EK_SEKIL, 1/FIS_EK_SEKIL); 8'i aşan fazla
    kapasitesi olan fişlere aynı ağırlıkla yeniden dağıtılır."""
    M = len(U_m)
    F_m = np.bincount(fis_m, minlength=M)
    w = np.maximum(np.asarray(sepet_f, dtype=float) - 1.0, 0.05)
    w = w * rng.gamma(S.FIS_EK_SEKIL, 1.0 / S.FIS_EK_SEKIL, len(fis_m))
    boyut = 1 + grup_en_buyuk_kalan(w, fis_m, np.asarray(U_m) - F_m)
    for _ in range(64):
        fazla = boyut - S.FIS_EN_COK
        if (fazla <= 0).all():
            break
        tasan = np.bincount(fis_m, np.maximum(fazla, 0), minlength=M).astype(np.int64)
        boyut = np.minimum(boyut, S.FIS_EN_COK)
        boyut += grup_en_buyuk_kalan(np.where(boyut < S.FIS_EN_COK, w, 0.0), fis_m, tasan)
    assert (boyut >= 1).all() and (boyut <= S.FIS_EN_COK).all()
    assert (np.bincount(fis_m, boyut, minlength=M) == U_m).all()
    return boyut


def kadin_hedefi(F_m: np.ndarray, kadin_m: np.ndarray, erkek_m: np.ndarray, varsayilan: np.ndarray,
                 rng) -> np.ndarray:
    """[M] mağaza-gün kadın ziyaretçi kotası: `F_m × q_m` rastgele
    yuvarlanmış (beklentisi kesin), q_m = kadın / (kadın + erkek) birim +
    `KADIN_HEDIYE_DUZELTME` ([0, 1]); cinsiyeti belli birim yoksa
    `varsayilan` (nüfusun mağaza kadın payı)."""
    F_m = np.asarray(F_m, dtype=np.int64)
    top = kadin_m + erkek_m
    with np.errstate(invalid="ignore", divide="ignore"):
        q = np.where(top > 0, kadin_m / top + S.KADIN_HEDIYE_DUZELTME, varsayilan)
    x = F_m * np.clip(q, 0.0, 1.0)
    return np.minimum(np.floor(x + rng.random(len(F_m))), F_m).astype(np.int64)


# ---------------------------------------------------------------------------
# Eşleştirme çekirdeği (iki aşama)
# ---------------------------------------------------------------------------


def asama1(fis_m, boyut, g_m, g_alt, n_g, M: int, puan, T, rng, sayac,
           g_ust=None, g_ind=None, w_f=None) -> tuple[np.ndarray, np.ndarray]:
    """Tip düzeyinde çapa + tamamlayıcı (modül docstring'i, adım 5). Gruplar
    (mağaza, tip, …) sırasıyla bitişik; `T` [17, 17] log-tamamlayıcılık.
    Birim başına (fiş, grup) atamaları döner (uzunluk Σ n_g).

    **Üst grup** (Görev 5c): `g_ust[g]` grubun üst grubu (aynı mağaza,
    bitişik, en çok iki alt grup), `g_ind[g]` ∈ {0, 1} alt grup terimi
    göstergesi, `w_f[f]` fişin alt grup terimi; grup puanı = `puan(pf, ps)`
    (fiş × üst grup, float32) + `g_ind × w_f`. Çiftler fiş × üst grup
    düzeyinde kurulur (indirim durumu çift sayısını büyütmez) ve kesindir:
    çapada üst grubun iki alt grubunun Gumbel-max'ı = puan + log(k₀ +
    k₁·e^w) + tek Gumbel, alt grup P(1) = k₁e^w / (k₀ + k₁e^w) ile seçilir
    (en büyük değer seçimden bağımsız, düz sürümle aynı ortak dağılım);
    tamamlayıcıda üst grubun taban logiti bir kez hesaplanır, her alt grubun
    birimleri kendi logitiyle (taban + g_ind × w_f) çekilir. Verilmezse her
    grup kendi üst grubudur (Görev 5b davranışı)."""
    F = len(fis_m)
    Gn = len(n_g)
    if g_ust is None:
        g_ust, g_ind, w_f = np.arange(Gn), np.zeros(Gn, dtype=np.int64), np.zeros(F)
    g_ust = np.asarray(g_ust, dtype=np.int64)
    g_ind = np.asarray(g_ind, dtype=np.int64)
    w_f = np.asarray(w_f, dtype=np.float64)
    Sn = int(g_ust[-1]) + 1 if Gn else 0
    assert (np.diff(g_ust) >= 0).all() and (np.diff(g_ust) <= 1).all()
    s_g = np.full((Sn, 2), -1, dtype=np.int64)          # üst grup → alt grup (indirim 0 / 1)
    s_g[g_ust, g_ind] = np.arange(Gn)
    assert (np.bincount(g_ust, minlength=Sn) == (s_g >= 0).sum(axis=1)).all()
    s_ilk = np.flatnonzero(np.r_[True, np.diff(g_ust) > 0]) if Gn else np.zeros(0, np.int64)
    s_m, s_alt = g_m[s_ilk], g_alt[s_ilk]                # üst grubun mağazası, alt kategorisi
    S_m = np.bincount(s_m, minlength=M)
    sm_bas = np.cumsum(S_m) - S_m
    ew_f = np.exp(w_f).astype(np.float32)
    var0, var1 = s_g[:, 0] >= 0, s_g[:, 1] >= 0
    g0, g1 = np.maximum(s_g[:, 0], 0), np.maximum(s_g[:, 1], 0)

    def alt_kalan(kalan_g):
        """[S] üst grup başına (indirimsiz, indirimli) kalan, float32."""
        return (np.where(var0, kalan_g[g0], 0).astype(np.float32),
                np.where(var1, kalan_g[g1], 0).astype(np.float32))

    # Çapa
    kalan_g = n_g.astype(np.int64).copy()
    capa_g = np.full(F, -1, dtype=np.int64)
    acik = np.arange(F)
    for _ in range(TUR):
        if not len(acik):
            break
        uz = S_m[fis_m[acik]]
        pi, ic = segment_ici(uz)
        pf = acik[pi]
        ps = sm_bas[fis_m[pf]] + ic
        sayac["cift_capa"] += len(pf)
        k0_s, k1_s = alt_kalan(kalan_g)
        k0 = k0_s[ps]
        k1 = k1_s[ps] * ew_f[pf]
        with np.errstate(divide="ignore"):
            skor = puan(pf, ps) + np.log(k0 + k1)
        skor += gumbel32(rng, len(pf))
        yer, enb = segment_argmax(skor, uz)
        t0, t1 = k0[yer], k1[yer]
        with np.errstate(invalid="ignore"):
            bir = rng.random(len(yer)) * (t0 + t1) < t1
        g_sec = s_g[ps[yer], bir.astype(np.int64)]
        g_sec = np.where(g_sec >= 0, g_sec, s_g[ps[yer]].max(axis=1))   # tükenmiş üst grup (kabul edilmez)
        o = np.lexsort((-enb, g_sec))
        gs = g_sec[o]
        rutbe = np.arange(len(o)) - np.searchsorted(gs, gs)
        kabul = o[rutbe < kalan_g[gs]]
        capa_g[acik[kabul]] = g_sec[kabul]
        kalan_g -= np.bincount(g_sec[kabul], minlength=Gn)
        kalsin = np.ones(len(acik), dtype=bool)
        kalsin[kabul] = False
        acik = acik[kalsin]
    sayac["tur_disi_capa"] += len(acik)
    if len(acik):   # mağazanın boş birimlerinden rastgele
        yuva = np.repeat(np.arange(Gn), kalan_g)
        yuva = yuva[grup_ici_karistir(g_m[yuva], rng)]
        y_bas = np.searchsorted(g_m[yuva], np.arange(M))
        fm = fis_m[acik]
        rutbe = np.arange(len(fm)) - np.searchsorted(fm, fm)
        g_sec = yuva[y_bas[fm] + rutbe]
        capa_g[acik] = g_sec
        kalan_g -= np.bincount(g_sec, minlength=Gn)

    # Tamamlayıcı
    kap = boyut - 1
    sepet = np.zeros((F, A_ALT), dtype=np.float32)
    np.add.at(sepet, (np.arange(F), g_alt[capa_g]), 1.0)
    atama_f, atama_g = [np.arange(F)], [capa_g]
    bekleyen = kalan_g
    w32 = w_f.astype(np.float32)
    for tur in range(TAMAM_TUR + ARTIK_TUR):
        artik = tur >= TAMAM_TUR
        gw = np.flatnonzero(bekleyen > 0)
        if not len(gw):
            break
        sw = np.unique(g_ust[gw])
        fo = np.flatnonzero(kap > 0)
        Fo_m = np.bincount(fis_m[fo], minlength=M)
        fo_bas = np.cumsum(Fo_m) - Fo_m
        uz = Fo_m[s_m[sw]]
        assert (uz > 0).all()
        pi, ic = segment_ici(uz)
        ps = sw[pi]
        pf = fo[fo_bas[s_m[ps]] + ic]
        sayac["cift_tamam"] += len(pf)
        tamam = sepet @ T
        taban = puan(pf, ps) + tamam[pf, s_alt[ps]]
        if artik:
            taban = taban + np.log(kap[pf]).astype(np.float32)
        hf_l, hg_l, dg_l = [], [], []
        for b in (0, 1):
            gb = s_g[sw, b]
            adet = np.where(gb >= 0, bekleyen[np.maximum(gb, 0)], 0)
            var = adet > 0
            if not var.any():
                continue
            maske = np.repeat(var, uz)
            logit = taban[maske] + w32[pf[maske]] if b else taban[maske]
            pos, lse = segment_kategorik(logit, uz[var], adet[var], rng)
            hf_l.append(pf[maske][pos])
            hg_l.append(np.repeat(gb[var], adet[var]))
            dg_l.append(np.repeat(lse, adet[var]) + rng.gumbel(size=len(pos)))
        hedef_f, hedef_g, deger = np.concatenate(hf_l), np.concatenate(hg_l), np.concatenate(dg_l)
        o = np.lexsort((-deger, hedef_f))
        hf = hedef_f[o]
        rutbe = np.arange(len(o)) - np.searchsorted(hf, hf)
        sinir = kap[hf] if tur >= TAMAM_TUR - 1 else np.minimum(kap[hf], DALGA)
        kabul = o[rutbe < sinir]
        f_k, g_k = hedef_f[kabul], hedef_g[kabul]
        atama_f.append(f_k)
        atama_g.append(g_k)
        np.add.at(sepet, (f_k, g_alt[g_k]), 1.0)
        kap -= np.bincount(f_k, minlength=F)
        bekleyen = bekleyen - np.bincount(g_k, minlength=Gn)
    n_disi = int(bekleyen.sum())
    sayac["tur_disi_tamam"] += n_disi
    if n_disi:   # kalan kapasiteye rastgele (mağaza içinde Σ kap = bekleyen)
        g_rest = np.repeat(np.arange(Gn), bekleyen)
        yuva = np.repeat(np.arange(F), np.maximum(kap, 0))
        a, b = grup_ici_es(g_m[g_rest], fis_m[yuva], rng)
        atama_f.append(yuva[b])
        atama_g.append(g_rest[a])
    return np.concatenate(atama_f), np.concatenate(atama_g)


def asama2(af, ag, F: int, g_bas_h, L_g, n_g, h_c, h_g, logit, rng, sayac):
    """Tip içinde SKU (modül docstring'i, adım 6). `af, ag` birim başına
    (fiş, grup); hatlar gruba göre bitişik (`g_bas_h`, `L_g`), `h_c` hat
    adedi. `logit(f, h)` fiş f'nin müşterisi × hat h'nin SKU'su log-puanı
    (log(kalan) hariç). (fiş, hat, adet) parçaları döner."""
    uk, k_a = np.unique(ag * F + af, return_counts=True)
    a_g, a_f = uk // F, uk % F
    A = len(uk)
    Hn = len(h_c)
    parca_f, parca_h, parca_n = [], [], []
    c_kalan = h_c.astype(np.int64).copy()
    ihtiyac = k_a.copy()
    # Seçimsiz: grubun tek hattı var ya da grubun hepsi tek fişte
    tek_hat = L_g[a_g] == 1
    if tek_hat.any():
        parca_f.append(a_f[tek_hat])
        parca_h.append(g_bas_h[a_g[tek_hat]])
        parca_n.append(k_a[tek_hat])
    tum = (k_a == n_g[a_g]) & ~tek_hat
    if tum.any():
        ti, tc = segment_ici(L_g[a_g[tum]])
        hh = g_bas_h[a_g[tum]][ti] + tc
        parca_f.append(a_f[tum][ti])
        parca_h.append(hh)
        parca_n.append(h_c[hh])
    secimsiz = tek_hat | tum
    ihtiyac[secimsiz] = 0
    if secimsiz.any():
        c_kalan -= np.bincount(np.concatenate(parca_h), np.concatenate(parca_n), minlength=Hn).astype(np.int64)
    for _ in range(TUR):
        aktif = np.flatnonzero(ihtiyac > 0)
        if not len(aktif):
            break
        pi, ic = segment_ici(L_g[a_g[aktif]])
        pa = aktif[pi]
        ph = g_bas_h[a_g[pa]] + ic
        sayac["cift_asama2"] += len(pa)
        with np.errstate(divide="ignore"):
            lg = logit(a_f[pa], ph) + np.log(c_kalan[ph])
        # tükenmiş hat: çok küçük ama sonlu (segment_kategorik sonlu ister)
        lg = np.where(np.isfinite(lg), lg, -1e30)
        pos, lse = segment_kategorik(lg, L_g[a_g[aktif]], ihtiyac[aktif], rng)
        istek_a = np.repeat(aktif, ihtiyac[aktif])
        istek_h = ph[pos]
        deger = np.repeat(lse, ihtiyac[aktif]) + rng.gumbel(size=len(pos))
        deger[c_kalan[istek_h] <= 0] = -np.inf
        o = np.lexsort((-deger, istek_h))
        ho = istek_h[o]
        rutbe = np.arange(len(o)) - np.searchsorted(ho, ho)
        kabul = o[(rutbe < c_kalan[ho]) & np.isfinite(deger[o])]
        ka, kh = istek_a[kabul], istek_h[kabul]
        ck, cn = np.unique(ka * Hn + kh, return_counts=True)
        parca_f.append(a_f[ck // Hn])
        parca_h.append(ck % Hn)
        parca_n.append(cn)
        ihtiyac -= np.bincount(ka, minlength=A)
        c_kalan -= np.bincount(kh, minlength=Hn)
    n_disi = int(ihtiyac.sum())
    sayac["tur_disi_sku"] += n_disi
    if n_disi:   # grup içinde rastgele
        ra = np.repeat(np.arange(A), ihtiyac)
        rh = np.repeat(np.arange(Hn), c_kalan)
        a, b = grup_ici_es(a_g[ra], h_g[rh], rng)
        parca_f.append(a_f[ra[a]])
        parca_h.append(rh[b])
        parca_n.append(np.ones(len(a), dtype=np.int64))
    return np.concatenate(parca_f), np.concatenate(parca_h), np.concatenate(parca_n).astype(np.int64)


# ---------------------------------------------------------------------------
# Kayıt tamponları
# ---------------------------------------------------------------------------


class Kayit:
    """B'nin ham kayıtları: gün gün eklenen sütun parçaları. `tablo(ad)`
    DataFrame'e çevirir (`ad` None ise üçü birden, sözlük).

    - `fis`: fis_id, gun, magaza, musteri (gerçek sahip, gizli), kanal
      (0 mağaza, 1 online), tip (0 satış, 1 iade), saat (gün içi dakika).
    - `fis_satir`: satir_id (bütün kayıttaki sıra), fis_id, satir_no
      (fiş içinde 1'den), sku, adet, tutar, indirim_tutari, kampanya_id
      (−1 yok), islem_adet (`iade.islem_indirimi_yerlestir` doldurur),
      beden_uyumsuz_adet (iade satırında islem_adet ve beden_uyumsuz_adet
      adetle aynı işaretli, negatif),
      orijinal_satir (iade satırının satir_id'si; satışta −1), a_satir
      (A'nın `ham["satis"]` satır konumu).
    - `bos_ziyaret` (Görev 6): gun, magaza, musteri, sku, adet.

    `durum` günlük ayrıştırmanın kalıcı durumudur (`AyristirDurum`, ilk
    `gun_ayristir` çağrısında kurulur); `sayac` sayaçlar, `sure` adım
    süreleri (profil)."""

    SEMA: dict[str, dict[str, type]] = {
        "fis": {"fis_id": np.int64, "gun": np.int16, "magaza": np.int16, "musteri": np.int64,
                "kanal": np.int8, "tip": np.int8, "saat": np.int16},
        "fis_satir": {"satir_id": np.int64, "fis_id": np.int64, "satir_no": np.int16, "sku": np.int32,
                      "adet": np.int16, "tutar": np.float64, "indirim_tutari": np.float64,
                      "kampanya_id": np.int32, "islem_adet": np.int16, "beden_uyumsuz_adet": np.int16,
                      "orijinal_satir": np.int64, "a_satir": np.int64},
        "bos_ziyaret": {"gun": np.int16, "magaza": np.int16, "musteri": np.int64, "sku": np.int32,
                        "adet": np.int16},
    }

    def __init__(self, tohum: int = S.CRM_TOHUM):
        self.tohum = tohum
        self._parca: dict[str, list[dict]] = {ad: [] for ad in self.SEMA}
        self._gun: dict[str, dict[int, list[int]]] = {ad: {} for ad in self.SEMA}
        self.fis_sayisi = 0
        self.satir_sayisi = 0
        self.durum = None
        self.sayac: dict[str, int] = defaultdict(int)
        self.sure: dict[str, float] = defaultdict(float)   # adım süreleri (sn)

    def ekle(self, ad: str, gun: int, sutunlar: dict) -> dict:
        """Gün `gun`'ün bir parçasını ekler (sütunlar şemaya dönüştürülür);
        eklenen parçayı döndürür (diziler yazılabilir, Görev 6 düzeltir)."""
        sema = self.SEMA[ad]
        assert set(sutunlar) == set(sema), (ad, set(sutunlar) ^ set(sema))
        parca = {k: np.asarray(sutunlar[k]).astype(t, copy=False) for k, t in sema.items()}
        n = {len(v) for v in parca.values()}
        assert len(n) == 1, ad
        self._parca[ad].append(parca)
        self._gun[ad].setdefault(int(gun), []).append(len(self._parca[ad]) - 1)
        return parca

    def gun_parcalari(self, ad: str, gun: int) -> list[dict]:
        return [self._parca[ad][i] for i in self._gun[ad].get(int(gun), [])]

    def tablo(self, ad: str | None = None):
        if ad is None:
            return {a: self.tablo(a) for a in self.SEMA}
        parcalar = self._parca[ad]
        if not parcalar:
            return pd.DataFrame({k: np.zeros(0, dtype=t) for k, t in self.SEMA[ad].items()})
        return pd.DataFrame({k: np.concatenate([p[k] for p in parcalar]) for k in self.SEMA[ad]})


# ---------------------------------------------------------------------------
# Kalıcı durum
# ---------------------------------------------------------------------------


def black_friday_gunleri(dunya) -> set[int]:
    k = dunya.kampanya
    gunler: set[int] = set()
    for r in k[k["tip"] == "black_friday"].itertuples():
        gunler.update(range(gun_indisi(r.baslangic), gun_indisi(r.bitis) + 1))
    return gunler


class AyristirDurum:
    """Günlük ayrıştırmanın günler arası durumu: ürün/hücre dizileri (salt
    okunur), Black Friday günleri, ziyaretçi aday yapısı ve tekrar alım
    tamponu (müşteri başına son `TEKRAR_TAMPON` option, halka; −1 boş)."""

    def __init__(self, girdi, nufus, d: int):
        w = girdi.dunya
        u = w.urunler
        self.M = nufus.magaza.M
        self.onl = nufus.magaza.onl
        self.onl_m = np.arange(self.M) == self.onl
        self.hm = np.asarray(w.hucre_magaza, dtype=np.int64)
        self.hs = np.asarray(w.hucre_sku, dtype=np.int64)
        self.sku_tip = tip_kodu(u)
        self.tip_alt = tip_ozellik()[0]
        self.sku_alt = self.tip_alt[self.sku_tip]
        self.sku_yon = BEDEN_YONU[self.sku_alt]
        self.sku_cins = urun_cinsiyet(u)
        # [N_TC, 2 müşteri cinsiyeti] cinsiyet log-terimi (aksesuar tipte yarım ceza)
        tc = np.arange(N_TC)
        aks = (BEDEN_YONU[self.tip_alt[tc // URUN_CINSIYET_SAYISI]] < 0).astype(np.int64)
        self.tc_ceza = cinsiyet_ceza_tablosu()[aks, :, tc % URUN_CINSIYET_SAYISI].astype(np.float32)
        self.sku_beden = u["beden_sira"].to_numpy(dtype=np.int64)
        self.kodlar = sku_kodlari(u)
        self.sku_option = np.asarray(w.sku_option, dtype=np.int64)
        self.option_devamli = w.optionlar["line"].isin(["Basic", "NOS"]).to_numpy()
        self.bf = black_friday_gunleri(w)
        self.T = tamamlayici_matris().astype(np.float32)
        self.adaylar = Adaylar(nufus, d)
        kap = max(nufus.K, 1024)
        self.tekrar = np.full((kap, S.TEKRAR_TAMPON), -1, dtype=np.int32)
        self.tekrar_ptr = np.zeros(kap, dtype=np.int8)

    def tekrar_buyut(self, K: int) -> None:
        kap = len(self.tekrar)
        if K <= kap:
            return
        while kap < K:
            kap *= 2
        t = np.full((kap, S.TEKRAR_TAMPON), -1, dtype=np.int32)
        t[: len(self.tekrar)] = self.tekrar
        p = np.zeros(kap, dtype=np.int8)
        p[: len(self.tekrar_ptr)] = self.tekrar_ptr
        self.tekrar, self.tekrar_ptr = t, p

    def tekrar_bonusu(self, k: np.ndarray, o: np.ndarray) -> np.ndarray:
        """[n] müşteri k'nin tamponunda option o varsa log-bonus."""
        var = (self.tekrar[k] == o[:, None]).any(axis=1)
        return np.where(var, np.where(self.option_devamli[o], S.TEKRAR_BONUS_DEVAMLI, S.TEKRAR_BONUS), 0.0)

    def tekrar_ekle(self, k: np.ndarray, o: np.ndarray) -> None:
        """Günün alımlarını (müşteri, option; tekrarlı çift bir kez) halkaya
        yazar; bir müşterinin günde 8'den fazla option'ı varsa son 8'i."""
        if not len(k):
            return
        O = int(self.option_devamli.shape[0])
        ck = np.unique(k.astype(np.int64) * O + o)
        k, o = ck // O, ck % O
        ku, bas, say = np.unique(k, return_index=True, return_counts=True)
        grup = np.repeat(np.arange(len(ku)), say)
        r = np.arange(len(k)) - bas[grup]
        atla = np.maximum(say - S.TEKRAR_TAMPON, 0)[grup]
        tut = r >= atla
        k, o, r = k[tut], o[tut], (r - atla)[tut]
        pos = (self.tekrar_ptr[k].astype(np.int64) + r) % S.TEKRAR_TAMPON
        self.tekrar[k, pos] = o
        self.tekrar_ptr[ku] = (self.tekrar_ptr[ku] + np.minimum(say, S.TEKRAR_TAMPON)) % S.TEKRAR_TAMPON


# ---------------------------------------------------------------------------
# Saat
# ---------------------------------------------------------------------------


def fis_saati(rng, d: int, onl_f: np.ndarray) -> np.ndarray:
    """[F] gün içi dakika: mağaza (10:00–22:00) hafta içi / hafta sonu tepeli
    karışım; ONL 24 saat, akşam tepeli."""
    n = len(onl_f)
    hafta_sonu = (a_sabitler.ISINMA_BASLANGIC + timedelta(days=int(d))).weekday() >= 5
    tepe, sigma, pay = S.SAAT_HAFTA_SONU if hafta_sonu else S.SAAT_HAFTA_ICI
    a, b = S.SAAT_ACILIS, S.SAAT_KAPANIS
    u_tepe, z, u_duz = rng.random(n), rng.standard_normal(n), rng.random(n)
    mag = np.where(u_tepe < pay, tepe + sigma * z, a + (b - a) * u_duz)
    mag = np.where((mag < a) | (mag >= b), a + (b - a) * u_duz, mag)
    ot, os_, op = S.SAAT_ONLINE
    onl = np.where(u_tepe < op, np.mod(ot + os_ * z, 24.0), 24.0 * u_duz)
    saat = np.where(onl_f, onl, mag)
    return np.minimum(np.floor(saat * 60.0), 24 * 60 - 1).astype(np.int16)


# ---------------------------------------------------------------------------
# Gün
# ---------------------------------------------------------------------------


def gun_ayristir(d: int, girdi, nufus, tetik, kayit: Kayit) -> None:
    """Gün d'nin pozitif satışını fişlere dağıtır, `kayit`'a fiş ve fiş
    satırı ekler (modül docstring'i). Uygun müşteri yetmeyen mağazada yeni
    müşteri eklenir (`nufus` büyür). `tetik` bu adımda değişmez (beden
    uyumsuzluğu tetiği iadede, Görev 6). Aday yapısı satışsız günde de
    güncellenir (aynı günün `bos_ziyaret`'i güncel adaylardan seçer)."""
    sure = kayit.sure
    t = time.perf_counter()

    def adim(ad):
        nonlocal t
        simdi = time.perf_counter()
        sure[ad] += simdi - t
        t = simdi

    if kayit.durum is None:
        kayit.durum = AyristirDurum(girdi, nufus, d)
    du = kayit.durum
    sayac = kayit.sayac
    du.adaylar.guncelle(nufus, d)
    adim("0 aday yapisi")
    s = girdi.satis_gun[d]
    if not len(s):
        return
    rng_z = crm_uretici(d, "ziyaret", kayit.tohum)
    akis = crm_alt_ureticiler(d, "atama", ATAMA_ADIMLARI, kayit.tohum)
    M = du.M

    # 1) Hatlar ve (mağaza, tip) grupları
    hucre = s[:, H].astype(np.int64)
    sku_h = du.hs[hucre]
    indirimli = (s[:, INDIRIM] > 0).astype(np.int64)     # A satırı indirimli (hücre-gün başına tek durum)
    anahtar = (du.hm[hucre] * N_TCI + (du.sku_tip[sku_h] * URUN_CINSIYET_SAYISI + du.sku_cins[sku_h]) * 2
               + indirimli)
    sira = np.argsort(anahtar, kind="stable")
    s, hucre, anahtar = s[sira], hucre[sira], anahtar[sira]
    h_s = du.hs[hucre]
    h_c = s[:, ADET].astype(np.int64)
    h_oran = s[:, ORAN]
    Hn = len(h_c)
    gk, g_bas_h, L_g = np.unique(anahtar, return_index=True, return_counts=True)
    h_g = np.repeat(np.arange(len(gk)), L_g)
    n_g = np.add.reduceat(h_c, g_bas_h)
    g_m, g_tci = gk // N_TCI, gk % N_TCI
    g_tc, g_ind = g_tci // 2, g_tci % 2
    g_tip = g_tc // URUN_CINSIYET_SAYISI
    g_alt = du.tip_alt[g_tip]
    # üst grup (mağaza, tip, ürün cinsiyeti): aşama 1 çiftleri bu düzeyde (Görev 5c)
    s_ilk = np.flatnonzero(np.r_[True, np.diff(gk // 2) > 0])
    g_ust = np.repeat(np.arange(len(s_ilk)), np.diff(np.r_[s_ilk, len(gk)]))
    s_tc = g_tc[s_ilk]
    s_tip = s_tc // URUN_CINSIYET_SAYISI
    U_m = np.bincount(g_m, n_g, minlength=M).astype(np.int64)

    # 2–4) Fiş sayısı, ziyaretçi, boyut
    F_m = fis_sayisi(U_m, du.onl_m, d in du.bf)
    fis_m = np.repeat(np.arange(M), F_m)
    F = len(fis_m)
    adim("1 hat/grup")
    kotalar = None
    if ZIYARETCI_KOTASI:
        h_cins = du.sku_cins[h_s]
        kotalar = kadin_hedefi(F_m, np.bincount(g_m[h_g], h_c * (h_cins == 0), minlength=M),
                               np.bincount(g_m[h_g], h_c * (h_cins == 1), minlength=M),
                               nufus.magaza.kadin_payi, rng_z)
    musteri = ziyaretci_sec(du.adaylar, nufus, d, F_m, rng_z, sayac, kadin_hedef=kotalar)
    adim("3 ziyaretci")
    du.tekrar_buyut(nufus.K)
    boyut = fis_boyutlari(akis["boyut"], fis_m, U_m, nufus.sepet_ort[musteri])

    adim("4 boyut")

    # 5) Aşama 1
    P = tip_puani(nufus, musteri, np.arange(N_TIP)).astype(np.float32)   # [F, N_TIP]
    adim("5a tip puani")
    # cinsiyet terimi: üst grup × müşteri cinsiyeti düz tablosu
    s_ceza = du.tc_ceza[s_tc].ravel()                                     # [S × 2]
    m_cins = nufus.cinsiyet[musteri].astype(np.int64)
    # indirim terimi: alt grup indirimliyse müşterinin INDIRIM_AGIRLIGI × duyarlılığı (Görev 5c)
    m_ind = indirim_terimi(nufus.indirim_duyarlilik[musteri], True)

    P_duz = P.ravel()

    def puan(pf, ps):
        return P_duz[pf * N_TIP + s_tip[ps]] + s_ceza[ps * 2 + m_cins[pf]]

    af, ag = asama1(fis_m, boyut, g_m, g_alt, n_g, M, puan, du.T, akis["asama1"], sayac,
                    g_ust=g_ust, g_ind=g_ind, w_f=m_ind)
    assert len(af) == U_m.sum()
    del P
    adim("5b asama1")

    # 6) Aşama 2
    def logit(f, h):
        k = musteri[f]
        sku = h_s[h]
        return (sku_ek_puani_cift(nufus, k, sku, h_oran[h], du.kodlar)
                + du.tekrar_bonusu(k, du.sku_option[sku]))

    pf, ph, pn = asama2(af, ag, F, g_bas_h, L_g, n_g, h_c, h_g, logit, akis["asama2"], sayac)

    adim("6 asama2")

    # 7) (fiş, hat) satırları
    uk, ters = np.unique(pf * Hn + ph, return_inverse=True)
    l_adet = np.bincount(ters.ravel(), pn).astype(np.int64)
    l_f, l_h = uk // Hn, uk % Hn
    assert (np.bincount(l_f, l_adet, minlength=F) == boyut).all()
    assert (np.bincount(l_h, l_adet, minlength=Hn) == h_c).all()
    assert l_adet.min() > 0
    L = len(uk)
    l_bas = np.searchsorted(l_f, np.arange(F))
    satir_no = np.arange(L) - l_bas[l_f] + 1
    kurus = np.rint(s[:, TUTAR] * 100).astype(np.int64)
    ind_kurus = np.rint(s[:, INDIRIM] * 100).astype(np.int64)
    l_tutar = grup_en_buyuk_kalan(l_adet.astype(float), l_h, kurus) / 100.0
    l_indirim = grup_en_buyuk_kalan(l_adet.astype(float), l_h, ind_kurus) / 100.0
    l_sku = h_s[l_h]
    l_k = musteri[l_f]
    yon = du.sku_yon[l_sku]
    m_beden = np.where(yon == 1, nufus.beden_alt[l_k], nufus.beden_ust[l_k]).astype(np.int64)
    uyumsuz = (yon >= 0) & (np.abs(du.sku_beden[l_sku] - m_beden) >= 1)

    fis_id = kayit.fis_sayisi + np.arange(F, dtype=np.int64)
    kayit.ekle("fis", d, {
        "fis_id": fis_id, "gun": np.full(F, d), "magaza": fis_m, "musteri": musteri,
        "kanal": (fis_m == du.onl).astype(np.int8), "tip": np.zeros(F, dtype=np.int8),
        "saat": fis_saati(akis["saat"], d, fis_m == du.onl),
    })
    kayit.ekle("fis_satir", d, {
        "satir_id": kayit.satir_sayisi + np.arange(L, dtype=np.int64), "fis_id": fis_id[l_f],
        "satir_no": satir_no, "sku": l_sku, "adet": l_adet, "tutar": l_tutar, "indirim_tutari": l_indirim,
        "kampanya_id": s[l_h, KAMPANYA].astype(np.int64), "islem_adet": np.zeros(L, dtype=np.int16),
        "beden_uyumsuz_adet": np.where(uyumsuz, l_adet, 0), "orijinal_satir": np.full(L, -1),
        "a_satir": s[l_h, SATIR].astype(np.int64),
    })
    kayit.fis_sayisi += F
    kayit.satir_sayisi += L
    sayac["birim"] += int(U_m.sum())
    sayac["fis"] += F
    sayac["satir"] += L

    # 9) Tekrar alım tamponu
    du.tekrar_ekle(l_k, du.sku_option[l_sku])
    adim("7 kayit+tekrar")
