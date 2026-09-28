"""v4 CRM (B) hız ölçümü: Görev 5'in günlük eşleştirme algoritmasının
iskeleti TAM ölçekte, bütün günlerde. Kapı: eşleştirme ≤ 12 dk.

    python araclar/v4_crm_hiz.py            # A'yı TAM kurar (~4 dk, ölçüme dahil değil)
    python araclar/v4_crm_hiz.py --gun 60   # yalnız ilk 60 gün (deneme)
    python araclar/v4_crm_hiz.py --butce-dk 60

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
from ctypes import wintypes

import numpy as np

N_MUSTERI = 1_800_000
IL_ICI_AGIRLIK = 0.15
SEPET_FIZIKSEL = 2.2
SEPET_ONLINE = 1.8
BF_CARPANI = 1.3
TUR = 5
KAPI_SN = 12 * 60
A_ALT = 17


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


def grup_en_buyuk_kalan(agirlik: np.ndarray, grup: np.ndarray, hedef: np.ndarray) -> np.ndarray:
    """Grup içinde `hedef[g]` adedi ağırlıkla orantılı tam sayılara böler."""
    top = np.bincount(grup, agirlik, minlength=len(hedef))
    x = agirlik / top[grup] * hedef[grup]
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


def aday_listeleri(nufus: dict, il_m: np.ndarray, onl_m: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Mağaza başına (aday müşteri indisi int32, 1/ağırlık float32)."""
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
        listeler.append((aday.astype(np.int32), (1.0 / w).astype(np.float32)))
    return listeler


# ---------------------------------------------------------------------------
# Günlük eşleştirme
# ---------------------------------------------------------------------------


def gun_esle(satirlar, hm, hs, sku, nufus, adaylar, onl_m, T, bf: bool, rng, sure: dict) -> dict:
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
        aday, ters_w = adaylar[m]
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


def calistir(gun_sayisi: int | None = None, butce_sn: float = 2 * KAPI_SN) -> None:
    from perakende_veri.v4.crm.girdi import ADET, H, girdi_kur
    from perakende_veri.v4.magaza import Olcek

    t0 = time.perf_counter()
    g = girdi_kur(Olcek.TAM)
    t_girdi = time.perf_counter() - t0
    print(f"girdi_kur(TAM): {t_girdi:.1f} sn, bellek {bellek_gb()[0]:.2f} GB (tepe {bellek_gb()[1]:.2f})", flush=True)
    w = g.dunya
    hm = np.asarray(w.hucre_magaza, dtype=np.int64)
    hs = np.asarray(w.hucre_sku, dtype=np.int64)
    u = w.urunler
    sku = {
        "alt": u["alt_kategori"].astype("category").cat.codes.to_numpy().astype(np.int64),
        "seg": u["fiyat_segmenti"].astype("category").cat.codes.to_numpy().astype(np.int64),
        "beden": u["beden_sira"].to_numpy().astype(np.int8),
        "aks": (u["ust_kategori"] == "Aksesuar").to_numpy(),
    }
    assert sku["alt"].max() < A_ALT
    onl_m = (w.magazalar["tip"] == "Online").to_numpy()
    il_m = w.magazalar["sehir"].astype("category").cat.codes.to_numpy().astype(np.int64)
    M = len(onl_m)
    gunler = [x[:, [H, ADET]] for x in g.satis_gun]
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
    del g   # A'nın nesneleri artık gerekmez (gün dizileri görünüm olarak yaşar)

    rng = np.random.default_rng(4242)
    tracemalloc.start()
    t1 = time.perf_counter()
    nufus = sahte_nufus(rng, hacim, il_m, onl_m)
    adaylar = aday_listeleri(nufus, il_m, onl_m)
    T = rng.normal(0, 0.3, (A_ALT, A_ALT)).astype(np.float32)
    T = (T + T.T) / 2
    t_nufus = time.perf_counter() - t1
    print(f"sahte nüfus + aday listeleri: {t_nufus:.1f} sn, "
          f"aday toplamı {sum(len(a) for a, _ in adaylar):,}", flush=True)

    sure = {k: 0.0 for k in ("1-2 birim/fis", "3 ziyaretci", "4a capa puan", "4b capa tur",
                              "5a tamam puan", "5b tamam tur", "6 birlestir")}
    toplam = {"birim": 0, "fis": 0, "satir": 0, "yeni": 0, "cift": 0, "tur_disi_capa": 0, "tur_disi_tamam": 0}
    en_cok_cift = 0
    # Gün başına beklenen çift sayısı (çapa + tamamlayıcı ≈ Σ F_m (2 U_m − F_m)):
    # bütçe aşılırsa kalan süre bununla projekte edilir.
    beklenen_cift = np.zeros(D)
    for d in range(D):
        if len(gunler[d]):
            U = np.bincount(hm[gunler[d][:, 0].astype(np.int64)], gunler[d][:, 1], minlength=M)
            h = np.where(onl_m, SEPET_ONLINE, SEPET_FIZIKSEL) * (BF_CARPANI if d in bf_gun else 1.0)
            F = np.where(U > 0, np.maximum(1, np.rint(U / h)), 0)
            beklenen_cift[d] = (F * (2 * U - F)).sum()
    t2 = time.perf_counter()
    son_gun = D
    for d in range(D):
        if time.perf_counter() - t2 > butce_sn:
            son_gun = d
            break
        if not len(gunler[d]):
            continue
        s = gun_esle(gunler[d], hm, hs, sku, nufus, adaylar, onl_m, T, d in bf_gun, rng, sure)
        for k in toplam:
            toplam[k] += s[k]
        en_cok_cift = max(en_cok_cift, s["cift"])
        if d % 100 == 0:
            print(f"  gün {d}: {time.perf_counter() - t2:.0f} sn, {bellek_gb()[0]:.2f} GB", flush=True)
    t_esle = time.perf_counter() - t2
    if son_gun < D:
        oran = beklenen_cift.sum() / max(beklenen_cift[:son_gun].sum(), 1.0)
        print(f"\nBÜTÇE AŞILDI: {butce_sn / 60:.0f} dk'da {son_gun}/{D} gün "
              f"(çiftlerin %{100 / oran:.1f}'i); bütün günler için projeksiyon "
              f"{t_esle * oran / 60:.0f} dk (çift sayısıyla orantılı)")
    D = son_gun
    _, tepe_tm = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    simdi, tepe = bellek_gb()

    print(f"\nGün: {D}; birim {toplam['birim']:,}, fiş {toplam['fis']:,}, fiş satırı {toplam['satir']:,}, "
          f"yeni müşteri {toplam['yeni']:,}")
    print(f"Çift (puanlanan birim×fiş) toplam {toplam['cift']:,}, gün en çok {en_cok_cift:,}")
    print(f"Tur dışı (rastgele): çapa fişi {toplam['tur_disi_capa']:,}, tamamlayıcı birim {toplam['tur_disi_tamam']:,}")
    print(f"Sahte nüfus {t_nufus:.1f} sn; eşleştirme {t_esle:.1f} sn ({t_esle / 60:.2f} dk)")
    for k, v in sure.items():
        print(f"  {k:16s} {v:7.1f} sn  %{100 * v / max(t_esle, 1e-9):4.1f}")
    print(f"Tepe bellek: süreç {tepe:.2f} GB (A kurulumu dahil), eşleştirme tracemalloc tepe "
          f"{tepe_tm / 2**30:.2f} GB")
    kapi = (t_esle + t_nufus) <= KAPI_SN
    print(f"Kapı (≤ {KAPI_SN // 60} dk, nüfus + eşleştirme): {'GEÇTİ' if kapi else 'AŞTI'}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=None)
    ap.add_argument("--butce-dk", type=float, default=2 * KAPI_SN / 60,
                    help="eşleştirme bu süreyi aşarsa durur ve projekte eder")
    a = ap.parse_args()
    calistir(a.gun, a.butce_dk * 60)
