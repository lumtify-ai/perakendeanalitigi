"""v4 CRM (B) hız ölçümü: Görev 5'in günlük eşleştirme algoritmasının
iskeleti TAM ölçekte, bütün günlerde. Kapı: eşleştirme ≤ 12 dk.

    python araclar/v4_crm_hiz.py            # A'yı TAM kurar (~4 dk, ölçüme dahil değil)
    python araclar/v4_crm_hiz.py --gun 60   # yalnız ilk 60 gün (deneme)
    python araclar/v4_crm_hiz.py --butce-dk 60
    python araclar/v4_crm_hiz.py --karsilastir 20   # önce 20 günde yoğun ↔ tip
    python araclar/v4_crm_hiz.py --yogun            # tam koşuda eski yoğun varyant
    python araclar/v4_crm_hiz.py --kucuk            # duman testi (A KUCUK)
    python araclar/v4_crm_hiz.py --ayristir         # gerçek gun_ayristir, gerçek nüfus, bütün günler
    python araclar/v4_crm_hiz.py --ayristir --iade  # + Görev 6 (işlem, iade, boş ziyaret)
    python araclar/v4_crm_hiz.py --dongu            # Görev 7: tam crm_simule_et + ölçümler

İki varyant: `gun_esle_tip` (varsayılan; Görev 5 için seçilen iki aşamalı,
tip düzeyinde, sayım düzeyinde algoritma, docstring'inde; ziyaretçi seçimi
`ziyaretci_sec`: kümülatif ağırlıktan ret örneklemesi, Gumbel-top-k
yedekli) ve `gun_esle_yogun` (ilk ölçüm: birim × fiş yoğun puan matrisi ve
her gün tam Gumbel-top-k, aşağıdaki 3–5. adımlar).

Eşleştirme `--butce-dk`'yı (varsayılan 24 dk = 2 × kapı) aşarsa durur ve
bütün günlerin süresini gün başına beklenen çift sayısıyla (Σ F_m (2 U_m −
F_m)) projekte eder.

Gerçek girdi (`girdi_kur(Olcek.TAM)`: günlük pozitif satış satırları, hücre
→ mağaza/SKU, ürün öznitelikleri, mağaza şehirleri) + sahte nüfus (1,8 M
müşteri: ev mağazası satış hacmiyle orantılı, il, ziyaret hızı gamma,
online payı, hayatta bayrağı, 17 alt kategori + 3 fiyat segmenti tercih
vektörü, beden) + rastgele tamamlayıcılık matrisi. Her gün, bütün
mağazalar birlikte (vektörel):

1. birimleri aç (satır × adet);
2. fiş sayısı F_m = max(1, round(U_m / sepet_hedef_m)) (fiziksel 2,2,
   ONL 1,8; Black Friday ×1,3), fiş boyutları lognormal ağırlıkla en büyük
   kalan, her fiş ≥ 1;
3. ziyaretçi seçimi: Gumbel-top-k (üstel yarış biçimi: E/w'nin en küçük
   k'sı ≡ log w + Gumbel'in en büyük k'sı), uygun = hayatta ∧ (ev mağazası
   m [ağırlık hız] ∨ aynı il [0,15 × hız]); ONL: online_payi > 0 [hız ×
   online_payi]; uygun < F_m ise sahte "yeni müşteri" (ölçümde sayılır);
4. çapa: birim × fiş puanı + Gumbel, her fiş en iyi boş birimini alır,
   çakışmada en yüksek puanlı fiş kazanır, ≤ 5 tur, sonra mağazanın boş
   birimlerinden rastgele;
5. tamamlayıcı: kalan birim × kapasiteli fiş puanı (tercih + beden +
   tamamlayıcılık(fiş sepeti) + Gumbel), her birim en iyi kapasiteli fişe,
   taşanlar sonraki tura (≤ 5 tur), sonra kalan kapasiteye rastgele;
6. birimleri (fiş, SKU) satırlarında birleştir, tutar birim başına.

Süre `time.perf_counter`, tepe bellek süreç tepe çalışma kümesi (Windows
`GetProcessMemoryInfo`; A'nın kurulumu dahil) ve eşleştirme döngüsünün
tracemalloc tepe artışı (numpy dizileri dahil).
"""

import argparse
import ctypes
import sys
import time
import tracemalloc
from collections import defaultdict
from ctypes import wintypes

import numpy as np

from perakende_veri.v4.crm.ayristir import (  # eşleştirme çekirdeği tek kaynak
    asama1, asama2, grup_en_buyuk_kalan, grup_ici_karistir, segment_argmax, segment_ici,
)
from perakende_veri.v4.crm.tercih import A_ALT, N_TIP, STD_BEDEN, tip_kodu, tip_ozellik

N_MUSTERI = 1_800_000
IL_ICI_AGIRLIK = 0.15
SEPET_FIZIKSEL = 2.2
SEPET_ONLINE = 1.8
BF_CARPANI = 1.3
TUR = 5
KAPI_SN = 12 * 60


# ---------------------------------------------------------------------------
# Bellek (Windows)
# ---------------------------------------------------------------------------


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def bellek_gb() -> tuple[float, float]:
    """(şu anki, tepe) çalışma kümesi GB; Windows dışında (nan, nan)."""
    if sys.platform != "win32":
        return float("nan"), float("nan")
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize / 2**30, pmc.PeakWorkingSetSize / 2**30


# ---------------------------------------------------------------------------
# Sahte dünya
# ---------------------------------------------------------------------------


def sahte_nufus(rng, magaza_hacmi: np.ndarray, il_m: np.ndarray, onl_m: np.ndarray) -> dict:
    fiz = np.flatnonzero(~onl_m)
    p = magaza_hacmi[fiz] / magaza_hacmi[fiz].sum()
    ev = fiz[rng.choice(len(fiz), N_MUSTERI, p=p)]
    hiz = rng.gamma(2.0, 0.5, N_MUSTERI).astype(np.float32) + 1e-3
    online = np.where(rng.random(N_MUSTERI) < 0.3, 0.0, rng.beta(1.5, 4.0, N_MUSTERI)).astype(np.float32)
    return {
        "ev": ev, "il": il_m[ev], "hiz": hiz, "online": online,
        "hayatta": rng.random(N_MUSTERI) > 0.03,
        "tercih": rng.normal(0, 1, (N_MUSTERI, A_ALT)).astype(np.float32),
        "segment": rng.normal(0, 0.5, (N_MUSTERI, 3)).astype(np.float32),
        "beden": rng.integers(0, 6, N_MUSTERI).astype(np.int8),
    }


def aday_listeleri(nufus: dict, il_m: np.ndarray, onl_m: np.ndarray) -> list[tuple]:
    """Mağaza başına (aday müşteri indisi int32, 1/ağırlık float32, ağırlık
    kümülatifi float64 — ret örneklemesi için; nüfus değişince yeniden)."""
    ev, il, hiz = nufus["ev"], nufus["il"], nufus["hiz"]
    il_sira = np.argsort(il, kind="stable")
    il_sinir = np.searchsorted(il[il_sira], np.arange(il_m.max() + 2))
    listeler = []
    for m in range(len(il_m)):
        if onl_m[m]:
            aday = np.flatnonzero(nufus["online"] > 0)
            w = hiz[aday] * nufus["online"][aday]
        else:
            aday = il_sira[il_sinir[il_m[m]]:il_sinir[il_m[m] + 1]]
            w = hiz[aday] * np.where(ev[aday] == m, 1.0, IL_ICI_AGIRLIK).astype(np.float32)
        listeler.append((aday.astype(np.int32), (1.0 / w).astype(np.float32),
                         np.cumsum(w, dtype=np.float64)))
    return listeler


# ---------------------------------------------------------------------------
# Günlük eşleştirme
# ---------------------------------------------------------------------------


def gun_esle_yogun(satirlar, hm, hs, sku, nufus, adaylar, onl_m, T, bf: bool, rng, sure: dict) -> dict:
    """Bir günün pozitif satışını fişlere böler; sayaçları döner."""
    M = len(onl_m)
    t = time.perf_counter()

    # 1) Birimler, mağazaya göre sıralı
    hucre = satirlar[:, 0].astype(np.int64)
    adet = satirlar[:, 1].astype(np.int64)
    birim_hucre = np.repeat(hucre, adet)
    birim_m = hm[birim_hucre]
    sira = np.argsort(birim_m, kind="stable")
    birim_hucre, birim_m = birim_hucre[sira], birim_m[sira]
    birim_s = hs[birim_hucre]
    b_alt, b_seg, b_bed, b_aks = sku["alt"][birim_s], sku["seg"][birim_s], sku["beden"][birim_s], sku["aks"][birim_s]
    U_m = np.bincount(birim_m, minlength=M)
    u_bas = np.cumsum(U_m) - U_m
    Ut = len(birim_hucre)

    # 2) Fiş sayısı ve boyutları
    hedef = np.where(onl_m, SEPET_ONLINE, SEPET_FIZIKSEL) * (BF_CARPANI if bf else 1.0)
    F_m = np.where(U_m > 0, np.maximum(1, np.rint(U_m / hedef)), 0).astype(np.int64)
    F_m = np.minimum(F_m, U_m)
    fis_m = np.repeat(np.arange(M), F_m)
    f_bas = np.cumsum(F_m) - F_m
    F = len(fis_m)
    boyut = 1 + grup_en_buyuk_kalan(rng.lognormal(0.0, 0.9, F), fis_m, U_m - F_m)
    sure["1-2 birim/fis"] += time.perf_counter() - t
    t = time.perf_counter()

    # 3) Ziyaretçi: Gumbel-top-k (üstel yarış) mağaza başına
    musteri = np.empty(F, dtype=np.int64)
    yeni = 0
    hayatta = nufus["hayatta"]
    for m in np.flatnonzero(F_m > 0):
        aday, ters_w = adaylar[m][:2]
        anahtar = rng.standard_exponential(len(aday), dtype=np.float32) * ters_w
        anahtar[~hayatta[aday]] = np.inf
        k = int(F_m[m])
        k_al = min(k, len(aday))
        sec = np.argpartition(anahtar, k_al - 1)[:k_al] if k_al > 0 else np.zeros(0, np.int64)
        sec = aday[sec[np.isfinite(anahtar[sec])]]   # ölü aday seçilmez
        k_al = len(sec)
        if k_al < k:   # nüfus yetmez: yeni müşteri (Görev 5'te nufus.ekle)
            yeni += k - k_al
            sec = np.r_[sec, np.full(k - k_al, -1)]
        musteri[f_bas[m]:f_bas[m] + k] = sec
    sure["3 ziyaretci"] += time.perf_counter() - t
    t = time.perf_counter()

    # Fiş başına küçük tercih tabloları (yeni müşteri: sıfır tercih)
    var = musteri >= 0
    mk = np.maximum(musteri, 0)
    f_tercih = np.where(var[:, None], nufus["tercih"][mk], 0).astype(np.float32)
    f_seg = np.where(var[:, None], nufus["segment"][mk], 0).astype(np.float32)
    f_bed = nufus["beden"][mk]

    def puan(pf, pu):
        uyum = (b_aks[pu] | (b_bed[pu] == f_bed[pf])).astype(np.float32)
        return f_tercih[pf, b_alt[pu]] + f_seg[pf, b_seg[pu]] + 1.5 * uyum

    # 4) Çapa: fiş-ana çiftler (fiş f × mağazasının birimleri)
    cift_len = U_m[fis_m]
    pf, ic = segment_ici(cift_len)
    pu = u_bas[fis_m][pf] + ic
    skor = puan(pf, pu) + rng.gumbel(size=len(pf)).astype(np.float32)
    sure["4a capa puan"] += time.perf_counter() - t
    t = time.perf_counter()
    alinan = np.zeros(Ut, dtype=bool)
    capa = np.full(F, -1, dtype=np.int64)
    acik = np.ones(F, dtype=bool)
    for _ in range(TUR):
        maskeli = np.where(alinan[pu] | ~acik[pf], -np.inf, skor).astype(np.float32)
        yer, enb = segment_argmax(maskeli, cift_len)
        aday_f = np.flatnonzero(acik & np.isfinite(enb))
        if not len(aday_f):
            break
        secilen_u = pu[yer[aday_f]]
        s = enb[aday_f]
        o = np.lexsort((-s, secilen_u))
        kazan = o[np.r_[True, secilen_u[o][1:] != secilen_u[o][:-1]]]
        capa[aday_f[kazan]] = secilen_u[kazan]
        alinan[secilen_u[kazan]] = True
        acik[aday_f[kazan]] = False
        if not acik.any():
            break
    kalan_f = np.flatnonzero(acik)
    if len(kalan_f):   # rastgele: mağazanın boş birimleri
        bos = np.flatnonzero(~alinan)
        bos = bos[grup_ici_karistir(birim_m[bos], rng)]
        bm = birim_m[bos]
        bos_bas = np.searchsorted(bm, np.arange(M))
        fm = fis_m[kalan_f]
        rutbe = np.arange(len(fm)) - np.searchsorted(fm, fm)
        u = bos[bos_bas[fm] + rutbe]
        capa[kalan_f] = u
        alinan[u] = True
    del skor, maskeli, pf, pu, ic
    sure["4b capa tur"] += time.perf_counter() - t
    t = time.perf_counter()

    # 5) Tamamlayıcı: birim-ana çiftler (kalan birim × mağazasının fişleri)
    fis_birim = np.full(Ut, -1, dtype=np.int64)
    fis_birim[capa] = np.arange(F)
    sepet = np.zeros((F, A_ALT), dtype=np.float32)
    np.add.at(sepet, (np.arange(F), b_alt[capa]), 1.0)
    kap = boyut - 1
    kalan_u = np.flatnonzero(~alinan)
    cift_len2 = F_m[birim_m[kalan_u]]
    pk, ic2 = segment_ici(cift_len2)
    pu2 = kalan_u[pk]
    pf2 = f_bas[birim_m[pu2]] + ic2
    taban = puan(pf2, pu2) + rng.gumbel(size=len(pk)).astype(np.float32)
    sure["5a tamam puan"] += time.perf_counter() - t
    t = time.perf_counter()
    bekleyen = np.ones(len(kalan_u), dtype=bool)
    for _ in range(TUR if len(kalan_u) else 0):
        tamam = sepet @ T                                  # [F, A] tamamlayıcılık
        skor2 = taban + tamam[pf2, b_alt[pu2]]
        skor2[(kap[pf2] <= 0) | ~bekleyen[pk]] = -np.inf
        yer, enb = segment_argmax(skor2, cift_len2)
        aktif = np.flatnonzero(bekleyen & np.isfinite(enb))
        if not len(aktif):
            break
        hedef_f = pf2[yer[aktif]]
        s = enb[aktif]
        o = np.lexsort((-s, hedef_f))
        hf = hedef_f[o]
        rutbe = np.arange(len(o)) - np.searchsorted(hf, hf)
        kabul = o[rutbe < kap[hf]]
        u = kalan_u[aktif[kabul]]
        f = hedef_f[kabul]
        fis_birim[u] = f
        np.add.at(sepet, (f, b_alt[u]), 1.0)
        kap -= np.bincount(f, minlength=F)
        bekleyen[aktif[kabul]] = False
        if not bekleyen.any():
            break
    kalan = kalan_u[bekleyen]
    if len(kalan):   # kalan kapasiteye rastgele (mağaza içinde Σ kap = kalan birim)
        yuva = np.repeat(np.arange(F), np.maximum(kap, 0))
        yuva = yuva[grup_ici_karistir(fis_m[yuva], rng)]
        km = birim_m[kalan]
        o = np.argsort(km, kind="stable")
        fis_birim[kalan[o]] = yuva
    del taban, skor2, pk, pu2, pf2, ic2
    sure["5b tamam tur"] += time.perf_counter() - t
    t = time.perf_counter()

    # 6) (fiş, SKU) satırları
    assert (fis_birim >= 0).all()
    anahtar = fis_birim * (len(sku["alt"]) + 1) + birim_s
    satir_anahtar, satir_adet = np.unique(anahtar, return_counts=True)
    sure["6 birlestir"] += time.perf_counter() - t
    return {"birim": Ut, "fis": F, "satir": len(satir_anahtar), "yeni": yeni,
            "cift": int(cift_len.sum() + cift_len2.sum()),
            "tur_disi_capa": len(kalan_f), "tur_disi_tamam": len(kalan)}




# ---------------------------------------------------------------------------
# İki aşamalı, tip düzeyinde eşleştirme (Görev 5 için seçilen algoritma)
# ---------------------------------------------------------------------------


def _gumbel_top_k(aday, ters_w, hayatta, k, rng) -> np.ndarray:
    """Gumbel-top-k (üstel yarış: E/w'nin en küçük k'sı); ölüler dışarıda.
    k'dan az hayatta aday varsa hepsi."""
    anahtar = rng.standard_exponential(len(aday), dtype=np.float32) * ters_w
    anahtar[~hayatta[aday]] = np.inf
    k_al = min(k, len(aday))
    if k_al == 0:
        return aday[:0].astype(np.int64)
    sec = np.argpartition(anahtar, k_al - 1)[:k_al]
    return aday[sec[np.isfinite(anahtar[sec])]].astype(np.int64)


RET_SINIRI = 4   # çekiliş sayısı > RET_SINIRI × k + 64 ise Gumbel-top-k'ya düş


def _ret_ornekle(aday, kum, hayatta, k, rng) -> np.ndarray | None:
    """Ardışık yerine koymadan örnekleme: kümülatif ağırlıktan yerine koyarak
    çek, tekrarı ve ölüyü reddet, ilk k farklı hayattaki aday. Dağılım
    Gumbel-top-k ile aynı (ikisi de ağırlıkla ardışık örneklemedir; ölüleri
    reddetmek hayattakilere koşullamaktır). Çekiliş sınırı aşılırsa None."""
    toplam = kum[-1]
    akis = np.zeros(0, dtype=np.int64)
    cekilen = 0
    parti = int(k * 1.25) + 16
    while True:
        yeni = np.searchsorted(kum, rng.random(parti) * toplam, side="right")
        yeni = np.minimum(yeni, len(kum) - 1)
        cekilen += parti
        akis = np.concatenate([akis, yeni[hayatta[aday[yeni]]]])
        _, ilk = np.unique(akis, return_index=True)
        if len(ilk) >= k:
            return aday[akis[np.sort(ilk)[:k]]].astype(np.int64)
        if cekilen > RET_SINIRI * k + 64:
            return None
        parti = max(2 * (k - len(ilk)), 16)


def ziyaretci_sec(F_m, f_bas, F, nufus, adaylar, rng, sayac: dict) -> tuple[np.ndarray, int]:
    """Mağaza başına F_m ziyaretçi: ret örneklemesi (O(k log n)); k adayların
    yarısını aşarsa ya da ret sınırı aşılırsa Gumbel-top-k. Yetmezse −1
    (yeni müşteri, Görev 5'te `nufus.ekle`)."""
    musteri = np.empty(F, dtype=np.int64)
    yeni = 0
    hayatta = nufus["hayatta"]
    for m in np.flatnonzero(F_m > 0):
        aday, ters_w, kum = adaylar[m]
        k = int(F_m[m])
        sec = _ret_ornekle(aday, kum, hayatta, k, rng) if 2 * k <= len(aday) else None
        if sec is None:
            sayac["gumbel_yedek"] += 1
            sec = _gumbel_top_k(aday, ters_w, hayatta, k, rng)
        if len(sec) < k:
            yeni += k - len(sec)
            sec = np.r_[sec, np.full(k - len(sec), -1)]
        musteri[f_bas[m]:f_bas[m] + k] = sec
    return musteri, yeni


def gun_esle_tip(satirlar, hm, hs, sku, nufus, adaylar, onl_m, T, bf: bool, rng, sure: dict) -> dict:
    """İki aşamalı, sayım düzeyinde eşleştirme; çekirdek
    `perakende_veri.v4.crm.ayristir.asama1/asama2` (Görev 5'in kullandığı
    kodun aynısı), puanlar bu betiğin sahte nüfusundan. Tip = `tercih.tip_kodu`
    (306 tip)."""
    M = len(onl_m)
    t = time.perf_counter()
    hucre = satirlar[:, 0].astype(np.int64)
    h_s = hs[hucre]
    anahtar = hm[hucre] * N_TIP + sku["tip"][h_s]
    sira = np.argsort(anahtar, kind="stable")
    h_s, anahtar = h_s[sira], anahtar[sira]
    h_c = satirlar[sira, 1].astype(np.int64)
    h_oran = satirlar[sira, 2].astype(np.float32)
    gk, g_bas_h, L_g = np.unique(anahtar, return_index=True, return_counts=True)
    h_g = np.repeat(np.arange(len(gk)), L_g)
    n_g = np.add.reduceat(h_c, g_bas_h)
    g_m, g_tip = gk // N_TIP, gk % N_TIP
    alt_t, seg_t, bed_t = tip_ozellik()
    g_alt, g_seg, g_bed = alt_t[g_tip], seg_t[g_tip], bed_t[g_tip]
    g_aks = g_bed == STD_BEDEN
    U_m = np.bincount(g_m, n_g, minlength=M).astype(np.int64)
    Ut = int(n_g.sum())

    hedef = np.where(onl_m, SEPET_ONLINE, SEPET_FIZIKSEL) * (BF_CARPANI if bf else 1.0)
    F_m = np.where(U_m > 0, np.maximum(1, np.rint(U_m / hedef)), 0).astype(np.int64)
    F_m = np.minimum(F_m, U_m)
    fis_m = np.repeat(np.arange(M), F_m)
    f_bas = np.cumsum(F_m) - F_m
    F = len(fis_m)
    boyut = 1 + grup_en_buyuk_kalan(rng.lognormal(0.0, 0.9, F), fis_m, U_m - F_m)
    sure["1-2 birim/fis"] += time.perf_counter() - t
    t = time.perf_counter()

    sayac = defaultdict(int)
    musteri, yeni = ziyaretci_sec(F_m, f_bas, F, nufus, adaylar, rng, sayac)
    sure["3 ziyaretci"] += time.perf_counter() - t
    t = time.perf_counter()

    var = musteri >= 0
    mk = np.maximum(musteri, 0)
    f_tercih = np.where(var[:, None], nufus["tercih"][mk], 0).astype(np.float32)
    f_seg = np.where(var[:, None], nufus["segment"][mk], 0).astype(np.float32)
    f_bed = nufus["beden"][mk]

    def puan_tip(pf, pg):
        uyum = (g_aks[pg] | (g_bed[pg] == f_bed[pf])).astype(np.float32)
        return f_tercih[pf, g_alt[pg]] + f_seg[pf, g_seg[pg]] + 1.5 * uyum

    af, ag = asama1(fis_m, boyut, g_m, g_alt, n_g, M, puan_tip, T, rng, sayac)
    assert len(af) == Ut
    sure["4-5 asama1 (tip)"] += time.perf_counter() - t
    t = time.perf_counter()

    def logit(f, h):
        c = musteri[f]
        cm = np.maximum(c, 0)
        s = h_s[h]
        return np.where(c >= 0, nufus["kalip"][cm, sku["kalip"][s]] + nufus["desen"][cm, sku["desen"][s]]
                        + nufus["duyarlilik"][cm] * h_oran[h], 0.0)

    pf_, ph_, pn_ = asama2(af, ag, F, g_bas_h, L_g, n_g, h_c, h_g, logit, rng, sayac)
    sure["6 asama2 (SKU)"] += time.perf_counter() - t
    t = time.perf_counter()

    H = len(h_s)
    satir_k, ters = np.unique(pf_ * H + ph_, return_inverse=True)
    assert (np.bincount(pf_, pn_, minlength=F) == boyut).all()
    assert (np.bincount(ph_, pn_, minlength=H) == h_c).all()
    sure["7 birlestir"] += time.perf_counter() - t
    return {"birim": Ut, "fis": F, "satir": len(satir_k), "yeni": yeni,
            "cift": sayac["cift_capa"] + sayac["cift_tamam"] + sayac["cift_asama2"],
            "cift_capa": sayac["cift_capa"], "cift_tamam": sayac["cift_tamam"],
            "cift_asama2": sayac["cift_asama2"],
            "tur_disi_capa": sayac["tur_disi_capa"], "tur_disi_tamam": sayac["tur_disi_tamam"],
            "tur_disi_sku": sayac["tur_disi_sku"], "gumbel_yedek": sayac["gumbel_yedek"]}


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------


def _yogun_cift(satirlar, hm, onl_m, bf: bool) -> float:
    """Yoğun varyantın gün çift sayısı Σ F_m (2 U_m − F_m)."""
    M = len(onl_m)
    U = np.bincount(hm[satirlar[:, 0].astype(np.int64)], satirlar[:, 1], minlength=M)
    h = np.where(onl_m, SEPET_ONLINE, SEPET_FIZIKSEL) * (BF_CARPANI if bf else 1.0)
    F = np.minimum(np.where(U > 0, np.maximum(1, np.rint(U / h)), 0), U)
    return float((F * (2 * U - F)).sum())


def _gunleri_kos(esle, gunler, gun_listesi, baglam, bf_gun, rng, butce_sn=np.inf):
    """(süre, işlenen günler, adım süreleri, toplam sayaçlar, gün en çok çift)."""
    sure = defaultdict(float)
    toplam = defaultdict(int)
    en_cok = 0
    islenen = []
    t = time.perf_counter()
    for d in gun_listesi:
        if time.perf_counter() - t > butce_sn:
            break
        islenen.append(d)
        if not len(gunler[d]):
            continue
        s = esle(gunler[d], *baglam, d in bf_gun, rng, sure)
        for k, v in s.items():
            toplam[k] += v
        en_cok = max(en_cok, s["cift"])
        if d % 100 == 0 and len(gun_listesi) > 100:
            print(f"  gün {d}: {time.perf_counter() - t:.0f} sn, {bellek_gb()[0]:.2f} GB", flush=True)
    return time.perf_counter() - t, islenen, sure, toplam, en_cok


def calistir(gun_sayisi: int | None = None, butce_sn: float = 2 * KAPI_SN,
             yogun: bool = False, karsilastir: int = 0, kucuk: bool = False) -> None:
    from perakende_veri.v4.crm.girdi import ADET, ORAN, H, girdi_kur
    from perakende_veri.v4.magaza import Olcek

    t0 = time.perf_counter()
    g = girdi_kur(Olcek.KUCUK if kucuk else Olcek.TAM)
    t_girdi = time.perf_counter() - t0
    print(f"girdi_kur(TAM): {t_girdi:.1f} sn, bellek {bellek_gb()[0]:.2f} GB (tepe {bellek_gb()[1]:.2f})", flush=True)
    w = g.dunya
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    hs = np.asarray(w.hucre_sku, dtype=np.int64)
    u = w.urunler

    def kod(s):
        return u[s].astype("category").cat.codes.to_numpy().astype(np.int64)

    tip = tip_kodu(u)
    alt_t, seg_t, bed_t = tip_ozellik()
    sku = {"alt": alt_t[tip], "seg": seg_t[tip], "beden": bed_t[tip].astype(np.int8),
           "aks": bed_t[tip] == STD_BEDEN, "kalip": kod("kalip"), "desen": kod("desen"), "tip": tip}
    onl_m = (w.magazalar["tip"] == "Online").to_numpy()
    il_m = w.magazalar["sehir"].astype("category").cat.codes.to_numpy().astype(np.int64)
    M = len(onl_m)
    gunler = [x[:, [H, ADET, ORAN]] for x in g.satis_gun]
    hacim = np.zeros(M)
    for x in gunler:
        if len(x):
            hacim += np.bincount(hm[x[:, 0].astype(np.int64)], x[:, 1], minlength=M)
    kamp = w.kampanya
    bf_gun = set()
    bas0 = np.datetime64("2022-07-04", "D")
    for r in kamp[kamp["tip"] == "black_friday"].itertuples():
        a = int((np.datetime64(r.baslangic, "D") - bas0).astype(int))
        b = int((np.datetime64(r.bitis, "D") - bas0).astype(int))
        bf_gun.update(range(a, b + 1))
    D = g.D if gun_sayisi is None else gun_sayisi
    del g

    rng = np.random.default_rng(4242)
    tracemalloc.start()
    t1 = time.perf_counter()
    nufus = sahte_nufus(rng, hacim, il_m, onl_m)
    nufus["kalip"] = rng.normal(0, 0.7, (N_MUSTERI, sku["kalip"].max() + 1)).astype(np.float32)
    nufus["desen"] = rng.normal(0, 0.7, (N_MUSTERI, sku["desen"].max() + 1)).astype(np.float32)
    nufus["duyarlilik"] = rng.gamma(2.0, 1.0, N_MUSTERI).astype(np.float32)
    adaylar = aday_listeleri(nufus, il_m, onl_m)
    T = rng.normal(0, 0.3, (A_ALT, A_ALT)).astype(np.float32)
    T = (T + T.T) / 2
    t_nufus = time.perf_counter() - t1
    print(f"sahte nüfus + aday listeleri: {t_nufus:.1f} sn, "
          f"aday toplamı {sum(len(a[0]) for a in adaylar):,}", flush=True)
    baglam = (hm, hs, sku, nufus, adaylar, onl_m, T)
    yogun_cift = np.array([_yogun_cift(x, hm, onl_m, d in bf_gun) if len(x) else 0.0
                           for d, x in enumerate(gunler[:D])])

    if karsilastir:
        dolu = [d for d in range(D) if len(gunler[d])]
        ornek = [dolu[i] for i in np.linspace(0, len(dolu) - 1, karsilastir).astype(int)]
        print(f"\nKarşılaştırma, {len(ornek)} eşit aralıklı gün:", flush=True)
        for ad, esle in (("yogun", gun_esle_yogun), ("tip", gun_esle_tip)):
            sn, _, sure, top, _ = _gunleri_kos(esle, gunler, ornek, baglam, bf_gun, np.random.default_rng(1))
            print(f"  {ad:5s}: {sn:7.1f} sn ({sn / len(ornek):.2f} sn/gün), çift/gün "
                  f"{top['cift'] / len(ornek):,.0f}; {D} güne oranla ~{sn / len(ornek) * D / 60:.1f} dk", flush=True)
            print("         " + ", ".join(f"{k} {v:.1f}" for k, v in sure.items()), flush=True)

    ad = "yogun" if yogun else "tip"
    print(f"\nTam koşu ({ad}), {D} gün:", flush=True)
    t_esle, islenen, sure, toplam, en_cok = _gunleri_kos(
        gun_esle_yogun if yogun else gun_esle_tip, gunler, list(range(D)), baglam, bf_gun, rng, butce_sn)
    son = len(islenen)
    if son < D:
        oran = yogun_cift.sum() / max(yogun_cift[:son].sum(), 1.0)
        print(f"\nBÜTÇE AŞILDI: {butce_sn / 60:.0f} dk'da {son}/{D} gün; projeksiyon "
              f"{t_esle * oran / 60:.0f} dk (yoğun çift sayısıyla orantılı)")
    _, tepe_tm = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _, tepe = bellek_gb()

    print(f"\nGün: {son}; birim {toplam['birim']:,}, fiş {toplam['fis']:,}, fiş satırı {toplam['satir']:,}, "
          f"yeni müşteri {toplam['yeni']:,}")
    yc = yogun_cift[:son].sum()
    print(f"Çift/gün: {toplam['cift'] / son:,.0f} (çapa {toplam['cift_capa'] / son:,.0f}, tamamlayıcı "
          f"{toplam['cift_tamam'] / son:,.0f}, aşama 2 {toplam['cift_asama2'] / son:,.0f}); yoğun "
          f"{yc / son:,.0f} → azalma {yc / max(toplam['cift'], 1):.1f}×; gün en çok {en_cok:,}")
    print(f"Ziyaretçi Gumbel-top-k yedeğine düşen mağaza-gün: {toplam['gumbel_yedek']:,}")
    print(f"Tur dışı (rastgele): çapa fişi {toplam['tur_disi_capa']:,}, tamamlayıcı birim "
          f"{toplam['tur_disi_tamam']:,}, aşama 2 birim {toplam['tur_disi_sku']:,}")
    print(f"Sahte nüfus {t_nufus:.1f} sn; eşleştirme {t_esle:.1f} sn ({t_esle / 60:.2f} dk)")
    for k, v in sure.items():
        print(f"  {k:16s} {v:7.1f} sn  %{100 * v / max(t_esle, 1e-9):4.1f}")
    print(f"Tepe bellek: süreç {tepe:.2f} GB (A kurulumu dahil), eşleştirme tracemalloc tepe "
          f"{tepe_tm / 2**30:.2f} GB")
    kapi = son == D and (t_esle + t_nufus) <= KAPI_SN
    print(f"Kapı (≤ {KAPI_SN // 60} dk, nüfus + eşleştirme): {'GEÇTİ' if kapi else 'AŞTI'}")


def ayristir_kos(gun_sayisi: int | None = None, kucuk: bool = False, iade: bool = False) -> None:
    """Gerçek Görev 5 ayrıştırması (`crm.ayristir.gun_ayristir`) bütün
    günlerde, en küçük sürücüyle: gerçek başlangıç nüfusu, her gün katılış
    (`nufus.katilis_sayisi` + `ekle`), terk yok. `iade` ise Görev 6 adımları
    da (işlem, iade bağlama, boş ziyaret; süreleri ayrıca). Kapı:
    `gun_ayristir` toplamı ≤ 12 dk."""
    from perakende_veri.v4.crm.ayristir import Kayit, gun_ayristir
    from perakende_veri.v4.crm.iade import bos_ziyaret, iade_bagla, islem_indirimi_yerlestir
    from perakende_veri.v4.crm.girdi import girdi_kur
    from perakende_veri.v4.crm.nufus import katilis_sayisi, nufus_baslat
    from perakende_veri.v4.crm.rastgele import crm_uretici
    from perakende_veri.v4.crm.sabitler import CRM_TOHUM
    from perakende_veri.v4.crm.yasam import Tetik
    from perakende_veri.v4.magaza import Olcek

    t0 = time.perf_counter()
    g = girdi_kur(Olcek.KUCUK if kucuk else Olcek.TAM)
    print(f"girdi_kur: {time.perf_counter() - t0:.1f} sn, bellek {bellek_gb()[0]:.2f} GB", flush=True)
    t0 = time.perf_counter()
    nufus = nufus_baslat(np.random.default_rng(CRM_TOHUM), g)
    t_nufus = time.perf_counter() - t0
    print(f"nufus_baslat: {t_nufus:.1f} sn, K = {nufus.K:,}", flush=True)
    tetik = Tetik.bos(nufus.K)
    kayit = Kayit()
    D = g.D if gun_sayisi is None else gun_sayisi
    t_kat = t_esle = t_iade = 0.0
    t_bas = time.perf_counter()
    for d in range(D):
        t = time.perf_counter()
        rng = crm_uretici(d, "katilis")
        n = katilis_sayisi(rng, g, nufus, d)
        if n.sum():
            nufus.ekle(rng, int(n.sum()), np.repeat(np.arange(len(n)), n), kayit_gun=d)
        t2 = time.perf_counter()
        t_kat += t2 - t
        gun_ayristir(d, g, nufus, tetik, kayit)
        t3 = time.perf_counter()
        t_esle += t3 - t2
        if iade:
            islem_indirimi_yerlestir(d, g, nufus, kayit)
            iade_bagla(d, g, nufus, tetik, kayit)
            bos_ziyaret(d, g, nufus, tetik, kayit)
            t_iade += time.perf_counter() - t3
        if d % 100 == 0:
            print(f"  gün {d}: ayrıştırma {t_esle:.0f} sn, Görev 6 {t_iade:.0f} sn, K {nufus.K:,}, bellek {bellek_gb()[0]:.2f} GB",
                  flush=True)
    t_top = time.perf_counter() - t_bas
    _, tepe = bellek_gb()
    sy = kayit.sayac
    print(f"\nGün {D}: birim {sy['birim']:,}, fiş {sy['fis']:,}, fiş satırı {sy['satir']:,}, "
          f"yeni (eksik) müşteri {sy['yeni']:,}, son K {nufus.K:,}")
    print(f"Çift/gün: çapa {sy['cift_capa'] / D:,.0f}, tamamlayıcı {sy['cift_tamam'] / D:,.0f}, "
          f"aşama 2 {sy['cift_asama2'] / D:,.0f}")
    print(f"Tur dışı: çapa fişi {sy['tur_disi_capa']:,}, tamamlayıcı birim {sy['tur_disi_tamam']:,} "
          f"(%{100 * sy['tur_disi_tamam'] / max(sy['birim'], 1):.2f}), aşama 2 birim {sy['tur_disi_sku']:,}; "
          f"ziyaretçi Gumbel yedeği {sy['gumbel_yedek']:,} mağaza-gün; aday yapısı kuruluşu "
          f"{kayit.durum.adaylar.kurulus_sayisi}")
    print(f"gun_ayristir toplamı {t_esle:.1f} sn ({t_esle / 60:.2f} dk); katılış {t_kat:.1f} sn; "
          f"döngü {t_top:.1f} sn; nufus_baslat {t_nufus:.1f} sn")
    for k, v in sorted(kayit.sure.items()):
        print(f"  {k:16s} {v:7.1f} sn  %{100 * v / max(t_esle, 1e-9):4.1f}")
    if iade:
        print(f"Görev 6 toplamı {t_iade:.1f} sn ({t_iade / 60:.2f} dk); ayrıştırma + Görev 6 "
              f"{(t_esle + t_iade) / 60:.2f} dk; iade birimi {sy['iade_birim']:,}, iade fişi {sy['iade_fis']:,}, "
              f"boş ziyaret birimi {sy['bos_birim']:,} (fişli {sy['bos_fisli_birim']:,}), "
              f"boş ziyaret için yeni müşteri {sy['bos_yeni_musteri']:,}")
    print(f"Tepe bellek (süreç, A dahil): {tepe:.2f} GB")
    print(f"Kapı (gun_ayristir ≤ {KAPI_SN // 60} dk): {'GEÇTİ' if t_esle <= KAPI_SN else 'AŞTI'}")


def dongu_ozeti(ham, girdi) -> None:
    """Görev 7 ölçümleri (kalibrasyon değil): yıllara göre nüfus, katılış,
    terk; görünür/kartlı pay; mağazada kart okutma payı; sepet; kartlı
    müşteri başına yıllık ziyaret."""
    import pandas as pd

    from perakende_veri.v4 import sabitler as a_sabitler
    from perakende_veri.v4.crm.nufus import SEGMENT_ADLARI
    from perakende_veri.v4.takvim import gun_indisi

    nuf = ham.nufus
    onl = nuf.magaza.onl
    kg, tg = nuf.kayit_gun.astype(np.int64), nuf.terk_gun.astype(np.int64)
    print(f"\nBaşlangıç tabanı (kayit_gun < 0): {(kg < 0).sum():,}; son K {nuf.K:,}; "
          f"son hayatta {nuf.hayatta.sum():,}")
    print("yıl   | yıl sonu hayatta | katılış   | terk      | yıl sonu görünür (hayatta)")
    for yil in (2022, 2023, 2024, 2025):
        b = max(gun_indisi(f"{yil}-01-01"), 0)
        s = min(gun_indisi(f"{yil}-12-31"), ham.D - 1)
        canli = (kg <= s) & ((tg < 0) | (tg > s))
        gor = canli & (nuf.gorunur_gun >= 0) & (nuf.gorunur_gun <= s)
        print(f"{yil}  | {canli.sum():>16,} | {((kg >= b) & (kg <= s)).sum():>9,} | "
              f"{((tg >= b) & (tg <= s)).sum():>9,} | {gor.sum():>10,} (%{100 * gor.sum() / canli.sum():.1f})")
    print(f"Hiç görünür olmuş: {nuf.gorunur_mu.sum():,} / {nuf.K:,} (%{100 * nuf.gorunur_mu.mean():.1f})")

    fis = ham.tablo("fis")
    g = fis["gun"].to_numpy(np.int64)
    m = fis["magaza"].to_numpy(np.int64)
    tip = fis["tip"].to_numpy()
    kart = fis["kart"].to_numpy()
    mus = fis["musteri"].to_numpy(np.int64)
    fiz_s = (m != onl) & (tip == 0)
    print(f"\nFiş {len(fis):,} (satış {int((tip == 0).sum()):,}, iade {int((tip == 1).sum()):,}); "
          f"mağaza satış fişinde kart payı %{100 * kart[fiz_s].mean():.1f}; iade fişinde (mağaza) "
          f"%{100 * kart[(m != onl) & (tip == 1)].mean():.1f}")
    seg = nuf.magaza.segment[m]
    for i, ad in enumerate(SEGMENT_ADLARI):
        s = fiz_s & (seg == i)
        if s.any():
            print(f"  segment {ad:12s} kart %{100 * kart[s].mean():.1f}  ({int(s.sum()):,} fiş)")
    sat = ham.kayit.tablo("fis_satir")[["fis_id", "adet"]]
    sat = sat[sat["adet"] > 0]
    boy = np.bincount(sat["fis_id"].to_numpy(np.int64), sat["adet"].to_numpy(np.int64), minlength=len(fis))
    print(f"Sepet (adet/fiş): mağaza {boy[fiz_s].mean():.2f}, ONL {boy[(m == onl) & (tip == 0)].mean():.2f}")
    del sat
    print("yıl   | kartlı satış fişi | kartlı müşteri | yıllık ziyaret/kartlı müşteri (mağaza+ONL)")
    for yil in (2023, 2024, 2025):
        b, s = gun_indisi(f"{yil}-01-01"), gun_indisi(f"{yil}-12-31")
        sec = (tip == 0) & kart & (g >= b) & (g <= s)
        n_k = len(np.unique(mus[sec]))
        print(f"{yil}  | {int(sec.sum()):>17,} | {n_k:>14,} | {sec.sum() / max(n_k, 1):.2f}")
    bz = ham.kayit.sayac
    print(f"İade birimi {bz['iade_birim']:,}; boş ziyaret birimi {bz['bos_birim']:,}; "
          f"yeni (eksik) müşteri {bz['yeni']:,}; boş ziyaret yeni müşteri {bz['bos_yeni_musteri']:,}")
    print(f"LTV: hayatta {int(ham.ltv['hayatta_olasiligi'].sum()):,}, geri gelecek "
          f"%{100 * ham.ltv['geri_gelecek_2026'].mean():.1f} (tümü), fiyat_ort medyan {np.median(ham.fiyat_ort):.1f}")


def dongu_kos(gun_sayisi: int | None = None, kucuk: bool = False) -> None:
    """Görev 7: gerçek `crm_simule_et` (katılış, terk, olay, ayrıştırma,
    Görev 6, kart, LTV); A bir kez kurulur, ölçüme dahil değil. Bütçe: B
    toplamı ≤ 20 dk."""
    from perakende_veri.v4.crm.dongu import crm_simule_et
    from perakende_veri.v4.crm.girdi import girdi_kur
    from perakende_veri.v4.magaza import Olcek

    t0 = time.perf_counter()
    g = girdi_kur(Olcek.KUCUK if kucuk else Olcek.TAM)
    a_sure = time.perf_counter() - t0
    simdi, tepe_a = bellek_gb()
    print(f"girdi_kur: {a_sure:.1f} sn, bellek {simdi:.2f} GB (tepe {tepe_a:.2f} GB)", flush=True)
    iz = {"tepe": 0.0}
    t_bas = time.perf_counter()

    def ilerleme(d, nufus, kayit):
        if d % 25 == 0 or d == g.D - 1:
            c = bellek_gb()[0]
            iz["tepe"] = max(iz["tepe"], c)
            if d % 100 == 0:
                print(f"  gün {d}: {time.perf_counter() - t_bas:.0f} sn, K {nufus.K:,}, hayatta "
                      f"{int(nufus.hayatta.sum()):,}, bellek {c:.2f} GB", flush=True)

    ham = crm_simule_et(g, gun_sayisi=gun_sayisi, ilerleme=ilerleme)
    t_b = time.perf_counter() - t_bas
    print(f"\nB toplamı (crm_simule_et): {t_b:.1f} sn ({t_b / 60:.2f} dk); bütçe 20 dk: "
          f"{'GEÇTİ' if t_b <= 20 * 60 else 'AŞTI'}")
    for k, v in ham.sure.items():
        print(f"  {k:22s} {v:7.1f} sn  %{100 * v / t_b:4.1f}")
    print(f"Bellek: B sırasında örneklenen en yüksek çalışma kümesi {iz['tepe']:.2f} GB; süreç tepesi "
          f"{bellek_gb()[1]:.2f} GB (A kurulumu tepesi {tepe_a:.2f} GB)", flush=True)
    dongu_ozeti(ham, g)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=None)
    ap.add_argument("--butce-dk", type=float, default=2 * KAPI_SN / 60,
                    help="eşleştirme bu süreyi aşarsa durur ve projekte eder")
    ap.add_argument("--yogun", action="store_true", help="tam koşuda eski yoğun (birim × fiş) varyant")
    ap.add_argument("--karsilastir", type=int, default=0,
                    help="önce N eşit aralıklı günde yoğun ve tip varyantlarını karşılaştır")
    ap.add_argument("--kucuk", action="store_true", help="duman testi: A KUCUK ölçekte")
    ap.add_argument("--ayristir", action="store_true",
                    help="gerçek Görev 5 gun_ayristir'i gerçek nüfusla bütün günlerde ölç")
    ap.add_argument("--iade", action="store_true",
                    help="--ayristir ile: Görev 6 adımlarını (işlem, iade, boş ziyaret) da ölç")
    ap.add_argument("--dongu", action="store_true",
                    help="Görev 7: tam crm_simule_et (bütçe B ≤ 20 dk) ve nüfus/kart ölçümleri")
    a = ap.parse_args()
    if a.dongu:
        dongu_kos(a.gun, a.kucuk)
    elif a.ayristir:
        ayristir_kos(a.gun, a.kucuk, a.iade)
    else:
        calistir(a.gun, a.butce_dk * 60, a.yogun, a.karsilastir, a.kucuk)
