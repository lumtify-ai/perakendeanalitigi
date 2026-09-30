"""Günlük ayrıştırma, satış dışı (spec §3.4–3.5, §4): işlem indirimi
yerleşimi, iade bağlama, gizli kaybın boş ziyaretlere yazılması.

Günlük sıra (Görev 7'nin döngüsü): `gun_ayristir` → `islem_indirimi_yerlestir`
→ `iade_bagla` → `bos_ziyaret`. Her biri yalnız gün d'nin kayıtlarını ekler
ya da düzeltir; `islem_indirimi_yerlestir` sıradan bağımsızdır (iade
satırlarını da doğru işaretler).

**İşlem indirimi.** A'da işlem indirimi hücre-gün başına tek çekiliştir:
satırın bütün birimleri ya indirimli ya değil (`k ∈ {0, adet}`, Görev 1).
Fiş satırı durumu A satırından alır (`islem_adet` = adet ya da 0; iade
satırında adetle aynı işaretli). Tutar Görev 5'te A satırının birim
fiyatından zaten kuruşu kuruşuna paylaştırılmıştır. **Spec sapması:**
spec §3.4'ün "işlem indirimli birimler kartlı müşterilere daha olası"
(sadakat indirimi) eğilimi uygulanmaz — satır içinde tek fiyat olduğundan
birimleri kartlıya kaydırmak A'nın tutarını bozar (denetleyici kararı).

**İade.** A'da (motor 16. adım) gün d'nin iadesi aynı hücrenin d − 7 (ONL
d − 10) satışından doğar, Binom(n, p) ≤ n; o günün birim fiyatıyla (işlem
dahil). B her iade birimini o hücre-günün B satış satırlarından birinin bir
birimine bağlar: iade satırı başına, satış satırlarının birimleri arasından
ağırlıklı yerine koymadan (Efraimidis–Spirakis: anahtar log(u) / w, en
büyük a), ağırlık `1 + IADE_BEDEN_AGIRLIK × (satır beden uyumsuz)`; satır
başına iade satılan adedi aşamaz. İadeler (müşteri, mağaza, gün) başına tek
iade fişinde (`tip` 1), satır `orijinal_satir` = orijinal `satir_id`;
A'nın iade tutarı ve indirimi birim başına en büyük kalanla (kuruşu
kuruşuna). İade fişinin mağazası **orijinal mağazadır**: A'da kapanmış
mağazanın iadesi depoya gider (`iade_depoya`), ama `satis` satırı ve B'nin
kaydı mağazanın hücresindedir — bağ kurulur, fiş kapanmış mağazada görünür
(Review Focus 2). Tetik: iade fişi başına `iade(k, d)`; iade edilen beden
uyumsuz satır başına `beden_uyumsuz(k)`. `beden_uyumsuz_adet` ve
`islem_adet` iade satırında adetle aynı işaretlidir (negatif).

**Boş ziyaret.** Gün d, mağaza m'nin gizli kaybının (A, ısınma dahil) her
birimi Binom(1, `BOS_FISLI_PAY`) ile ya o gün m'de satış fişi olan bir
müşteriye ("almak istediği bir şey eksikti") ya da fişsiz bir boş
ziyaretçiye yazılır (o gün fişli müşteri yoksa hepsi fişsiz). Fişsiz
ziyaretçiler Görev 5'in aday yapısından (`Adaylar.sec`, ziyaret ağırlığı)
mağaza başına `max(1, round(birim / sepet hedefi))` kişi çekilir, o gün m'de
fişi olanlar atılır; aday yoksa yeni müşteri eklenir. Her iki havuzda birim
sahibi, birimin tipine tercih (`tercih.tip_puani` + müşteri × ürün
cinsiyeti terimi, Görev 5b) softmax'ıyla çekilir (yalnız havuz × mağazanın
kayıp (tip, cinsiyet) grupları). Hepsine `stoksuzluk(k, d)`.
Satırlar `kayit` `bos_ziyaret` (gun, magaza, musteri, sku, adet; gizli).

Rastgelelik: `crm_alt_ureticiler(d, "iade", ADIMLAR)`.
"""

import time

import numpy as np

from .. import sabitler as a_sabitler
from . import sabitler as S
from .ayristir import N_TC, AyristirDurum, fis_saati, grup_en_buyuk_kalan, segment_kategorik
from .girdi import ADET, H, INDIRIM, ISLEM, KAMPANYA, SATIR, TUTAR
from .rastgele import crm_alt_ureticiler
from .tercih import URUN_CINSIYET_SAYISI, tip_puani

ADIMLAR = ("iade", "iade_saat", "bos_bol", "bos_yeni", "bos_ata")   # yeni adım SONA
GECIKME_MAGAZA = a_sabitler.IADE_GECIKME_MAGAZA
GECIKME_ONLINE = a_sabitler.IADE_GECIKME_ONLINE


def _durum(girdi, nufus, kayit, d: int) -> AyristirDurum:
    if kayit.durum is None:
        kayit.durum = AyristirDurum(girdi, nufus, d)
    return kayit.durum


def _birlestir(parcalar: list[dict], sutunlar) -> dict:
    return {k: np.concatenate([p[k] for p in parcalar]) if parcalar else np.zeros(0) for k in sutunlar}


# ---------------------------------------------------------------------------
# İşlem indirimi
# ---------------------------------------------------------------------------


def islem_indirimi_yerlestir(d: int, girdi, nufus, kayit) -> None:
    """Gün d'nin bütün fiş satırlarında `islem_adet` = adet (A satırı işlem
    indirimliyse) ya da 0; A satırı başına toplam A'nın k'sına eşit olduğunu
    doğrular. Tutar/indirim Görev 5'te kesin paylaştırılmıştır (modül
    docstring'i; kartlı eğilimi uygulanmaz). `nufus` arayüz için."""
    t = time.perf_counter()
    k_a = girdi.islem_adet
    for p in kayit.gun_parcalari("fis_satir", d):
        a = p["a_satir"]
        p["islem_adet"][:] = np.where(k_a[a] != 0, p["adet"], 0)
        au, ters = np.unique(a, return_inverse=True)
        top = np.bincount(ters.ravel(), p["islem_adet"].astype(np.int64), minlength=len(au))
        assert (top == k_a[au]).all(), f"gün {d}: işlem adedi A satırıyla tutmuyor"
    kayit.sure["8 islem"] += time.perf_counter() - t


# ---------------------------------------------------------------------------
# İade
# ---------------------------------------------------------------------------


def _a_satis_satiri(girdi, g: int, hucre: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gün g'nin A satış satırlarında hücrelerin (SATIR, ADET)'i."""
    s = girdi.satis_gun[g]
    hc = s[:, H].astype(np.int64)
    o = np.argsort(hc, kind="stable")
    p = np.minimum(np.searchsorted(hc[o], hucre), max(len(hc) - 1, 0))
    assert len(hc) and (hc[o][p] == hucre).all(), f"gün {g}: iadenin satış satırı yok"
    satir = o[p]
    return s[satir, SATIR].astype(np.int64), s[satir, ADET].astype(np.int64)


def _satis_satirlari(kayit, g: int, a_satirlar: np.ndarray) -> dict:
    """Gün g'nin B satış satırlarından A satırı `a_satirlar` içinde olanlar,
    fişin müşterisi ve mağazasıyla."""
    sat = _birlestir(kayit.gun_parcalari("fis_satir", g),
                     ("satir_id", "fis_id", "sku", "adet", "beden_uyumsuz_adet", "a_satir"))
    fis = _birlestir(kayit.gun_parcalari("fis", g), ("fis_id", "musteri", "magaza"))
    sec = (sat["adet"] > 0) & np.isin(sat["a_satir"], a_satirlar)
    sat = {k: v[sec] for k, v in sat.items()}
    assert (np.diff(fis["fis_id"]) > 0).all()
    i = np.searchsorted(fis["fis_id"], sat["fis_id"])
    assert (fis["fis_id"][i] == sat["fis_id"]).all()
    sat["musteri"] = fis["musteri"][i]
    sat["magaza"] = fis["magaza"][i]
    return sat


def iade_bagla(d: int, girdi, nufus, tetik, kayit) -> None:
    """Gün d'nin A iadelerini orijinal B satış satırlarına bağlar, iade
    fişleri ve satırları ekler, tetikleri günceller (modül docstring'i).
    Orijinal gün (d − 7 / ONL d − 10) daha önce ayrıştırılmış olmalıdır."""
    r = girdi.iade_gun[d]
    if not len(r):
        return
    t = time.perf_counter()
    du = _durum(girdi, nufus, kayit, d)
    akis = crm_alt_ureticiler(d, "iade", ADIMLAR, kayit.tohum)
    R = len(r)
    c = r[:, H].astype(np.int64)
    a = -r[:, ADET].astype(np.int64)
    assert (a > 0).all()
    onl_r = du.hm[c] == du.onl
    s_gun = d - np.where(onl_r, GECIKME_ONLINE, GECIKME_MAGAZA)
    assert (s_gun >= 0).all()

    # A'nın satış satırı ve B adayları
    sa = np.empty(R, dtype=np.int64)
    s_adet = np.empty(R, dtype=np.int64)
    aday = []
    for g in np.unique(s_gun):
        sel = s_gun == g
        sa[sel], s_adet[sel] = _a_satis_satiri(girdi, int(g), c[sel])
        aday.append(_satis_satirlari(kayit, int(g), sa[sel]))
    assert (a <= s_adet).all(), f"gün {d}: iade satıştan fazla"
    ad = {k: np.concatenate([x[k] for x in aday]) for k in aday[0]}
    o_sa = np.argsort(sa)
    grp = o_sa[np.searchsorted(sa[o_sa], ad["a_satir"])]    # adayın iade satırı
    assert (np.bincount(grp, ad["adet"], minlength=R) == s_adet).all(), f"gün {d}: satış satırları eksik"

    # Birim düzeyinde ağırlıklı, yerine koymadan (ES anahtarı)
    Lc = len(grp)
    u_l = np.repeat(np.arange(Lc), ad["adet"].astype(np.int64))
    w = 1.0 + S.IADE_BEDEN_AGIRLIK * (ad["beden_uyumsuz_adet"][u_l] > 0)
    anahtar = np.log(akis["iade"].random(len(u_l))) / w
    gr = grp[u_l]
    o = np.lexsort((-anahtar, gr))
    go = gr[o]
    rutbe = np.arange(len(o)) - np.searchsorted(go, go)
    n_l = np.bincount(u_l[o[rutbe < a[go]]], minlength=Lc)
    assert (np.bincount(grp, n_l, minlength=R) == a).all()

    # İade satırları, (mağaza, müşteri) başına fiş
    lk = np.flatnonzero(n_l > 0)
    n = n_l[lk].astype(np.int64)
    row = grp[lk]
    mus = ad["musteri"][lk].astype(np.int64)
    mag = ad["magaza"][lk].astype(np.int64)
    assert (mag == du.hm[c[row]]).all() and (ad["sku"][lk] == du.hs[c[row]]).all()
    sira = np.lexsort((row, mus, mag))
    lk, n, row, mus, mag = lk[sira], n[sira], row[sira], mus[sira], mag[sira]
    fis_anahtar = mag * (nufus.K + 1) + mus
    yeni_fis = np.r_[True, fis_anahtar[1:] != fis_anahtar[:-1]]
    f_l = np.cumsum(yeni_fis) - 1
    F = int(yeni_fis.sum())
    L = len(lk)
    satir_no = np.arange(L) - np.flatnonzero(yeni_fis)[f_l] + 1
    kurus = -np.rint(r[:, TUTAR] * 100).astype(np.int64)
    ind_kurus = -np.rint(r[:, INDIRIM] * 100).astype(np.int64)
    assert (kurus >= 0).all() and (ind_kurus >= 0).all()
    l_tutar = -grup_en_buyuk_kalan(n.astype(float), row, kurus) / 100.0
    l_indirim = -grup_en_buyuk_kalan(n.astype(float), row, ind_kurus) / 100.0
    uyumsuz = ad["beden_uyumsuz_adet"][lk] > 0

    fis_id = kayit.fis_sayisi + np.arange(F, dtype=np.int64)
    f_mag, f_mus = mag[yeni_fis], mus[yeni_fis]
    kayit.ekle("fis", d, {
        "fis_id": fis_id, "gun": np.full(F, d), "magaza": f_mag, "musteri": f_mus,
        "kanal": (f_mag == du.onl).astype(np.int8), "tip": np.ones(F, dtype=np.int8),
        "saat": fis_saati(akis["iade_saat"], d, f_mag == du.onl),
    })
    kayit.ekle("fis_satir", d, {
        "satir_id": kayit.satir_sayisi + np.arange(L, dtype=np.int64), "fis_id": fis_id[f_l],
        "satir_no": satir_no, "sku": ad["sku"][lk], "adet": -n, "tutar": l_tutar, "indirim_tutari": l_indirim,
        "kampanya_id": r[row, KAMPANYA].astype(np.int64),
        "islem_adet": np.where(r[row, ISLEM] != 0, -n, 0),
        "beden_uyumsuz_adet": np.where(uyumsuz, -n, 0), "orijinal_satir": ad["satir_id"][lk],
        "a_satir": r[row, SATIR].astype(np.int64),
    })
    kayit.fis_sayisi += F
    kayit.satir_sayisi += L
    kayit.sayac["iade_birim"] += int(a.sum())
    kayit.sayac["iade_fis"] += F
    kayit.sayac["iade_satir"] += L

    tetik.uzat(nufus.K)
    tetik.iade(f_mus, d)
    tetik.beden_uyumsuz(mus[uyumsuz])
    kayit.sure["9 iade"] += time.perf_counter() - t


# ---------------------------------------------------------------------------
# Boş ziyaret
# ---------------------------------------------------------------------------


def _birimleri_ata(nufus, havuz_k, havuz_m, b_m, b_tc, b_n, tc_ceza, rng):
    """Mağaza içi havuzdan (havuz_m'ye göre sıralı) birim sahibi: (m, tip,
    ürün cinsiyeti) grubunun her birimi havuzun softmax(tip_puani +
    cinsiyet terimi)'nden bağımsız çekilir. `b_*` birim satırları (mağaza,
    tip × `URUN_CINSIYET_SAYISI` + ürün cinsiyeti, adet); `tc_ceza`
    `AyristirDurum.tc_ceza`. Satır sırasıyla birim başına müşteri [Σ b_n]
    döner (satır içi birimler bitişik)."""
    anahtar = b_m * N_TC + b_tc
    sira = np.argsort(anahtar, kind="stable")
    gk, g_ters = np.unique(anahtar, return_inverse=True)
    g_ters = g_ters.ravel()
    g_n = np.bincount(g_ters, b_n, minlength=len(gk)).astype(np.int64)
    g_m, g_tc = gk // N_TC, gk % N_TC
    h_bas = np.searchsorted(havuz_m, np.arange(nufus.magaza.M))
    h_son = np.searchsorted(havuz_m, np.arange(nufus.magaza.M), side="right")
    logit, aday, uz = [], [], []
    for m in np.unique(g_m):
        k_m = havuz_k[h_bas[m]:h_son[m]]
        assert len(k_m), m
        tc_m = g_tc[g_m == m]
        P = (tip_puani(nufus, k_m, tc_m // URUN_CINSIYET_SAYISI)                  # [nk, nt]
             + tc_ceza[tc_m][:, nufus.cinsiyet[k_m].astype(np.int64)].T)
        logit.append(P.T.ravel())
        aday.append(np.tile(k_m, len(tc_m)))
        uz.append(np.full(len(tc_m), len(k_m)))
    pos, _ = segment_kategorik(np.concatenate(logit), np.concatenate(uz), g_n, rng)
    cekilen = np.concatenate(aday)[pos]        # grup sırasıyla, grup içinde g_n
    # birimleri (grup sırasıyla açılmış) çekilişlerle eşle; çekilişler iid
    birim_satir = np.repeat(sira, b_n[sira])
    sonuc = np.empty(int(b_n.sum()), dtype=np.int64)
    b_bas = np.cumsum(b_n) - b_n
    ic = np.arange(len(birim_satir)) - np.repeat(np.cumsum(b_n[sira]) - b_n[sira], b_n[sira])
    sonuc[b_bas[birim_satir] + ic] = cekilen
    return sonuc


def bos_ziyaret(d: int, girdi, nufus, tetik, kayit) -> None:
    """Gün d'nin gizli kaybını müşterilere yazar (modül docstring'i):
    `kayit` `bos_ziyaret` satırları ve `tetik.stoksuzluk`. Gün d'nin satış
    fişleri (`gun_ayristir`) önceden eklenmiş olmalıdır."""
    kay = girdi.kayip_gun[d]
    if not len(kay):
        return
    t = time.perf_counter()
    du = _durum(girdi, nufus, kayit, d)
    akis = crm_alt_ureticiler(d, "iade", ADIMLAR, kayit.tohum)
    M = du.M
    c = kay[:, 0].astype(np.int64)
    b_n = kay[:, 1].astype(np.int64)
    b_m = du.hm[c]
    b_s = du.hs[c]
    b_tc = du.sku_tip[b_s] * URUN_CINSIYET_SAYISI + du.sku_cins[b_s]

    # Fişli havuz: gün d, satış fişi olan (mağaza, müşteri)
    fis = _birlestir(kayit.gun_parcalari("fis", d), ("magaza", "musteri", "tip"))
    sf = fis["tip"] == 0
    fk = np.unique(fis["magaza"][sf].astype(np.int64) * (nufus.K + 1) + fis["musteri"][sf])
    fisli_m, fisli_k = fk // (nufus.K + 1), fk % (nufus.K + 1)
    fisli_say = np.bincount(fisli_m, minlength=M)

    n_fisli = akis["bos_bol"].binomial(b_n, S.BOS_FISLI_PAY)
    n_fisli[fisli_say[b_m] == 0] = 0
    n_yeni = b_n - n_fisli

    # Fişsiz ziyaretçi havuzu
    rng_y = akis["bos_yeni"]
    yeni_m_n = np.bincount(b_m, n_yeni, minlength=M).astype(np.int64)
    hedef = np.where(np.arange(M) == du.onl, S.SEPET_HEDEF_ONLINE, S.SEPET_HEDEF_MAGAZA)
    yk, ym = [], []
    for m in np.flatnonzero(yeni_m_n > 0):
        v = int(min(max(1, np.rint(yeni_m_n[m] / hedef[m])), yeni_m_n[m]))
        sec = du.adaylar.sec(nufus, int(m), v, rng_y, kayit.sayac)
        sec = sec[~np.isin(sec, fisli_k[fisli_m == m])]
        if not len(sec):
            sec = nufus.ekle(rng_y, v, ev_magaza=np.full(v, m), kayit_gun=d)
            kayit.sayac["bos_yeni_musteri"] += v
        yk.append(np.sort(sec))
        ym.append(np.full(len(sec), m))

    satirlar = []
    rng_a = akis["bos_ata"]
    for n_yol, h_k, h_m in ((n_fisli, fisli_k, fisli_m),
                            (n_yeni, np.concatenate(yk) if yk else np.zeros(0, np.int64),
                             np.concatenate(ym) if ym else np.zeros(0, np.int64))):
        v = n_yol > 0
        if not v.any():
            continue
        k_birim = _birimleri_ata(nufus, h_k.astype(np.int64), h_m.astype(np.int64),
                                 b_m[v], b_tc[v], n_yol[v], du.tc_ceza, rng_a)
        idx = np.repeat(np.flatnonzero(v), n_yol[v])
        satirlar.append((b_m[idx], k_birim, b_s[idx]))
    m_u = np.concatenate([x[0] for x in satirlar])
    k_u = np.concatenate([x[1] for x in satirlar])
    s_u = np.concatenate([x[2] for x in satirlar])
    Sn = len(du.sku_tip)
    uk, say = np.unique((m_u * (nufus.K + 1) + k_u) * Sn + s_u, return_counts=True)
    mk, sku = uk // Sn, uk % Sn
    kayit.ekle("bos_ziyaret", d, {
        "gun": np.full(len(uk), d), "magaza": mk // (nufus.K + 1), "musteri": mk % (nufus.K + 1),
        "sku": sku, "adet": say,
    })
    assert say.sum() == b_n.sum()
    kayit.sayac["bos_birim"] += int(b_n.sum())
    kayit.sayac["bos_fisli_birim"] += int(n_fisli.sum())

    tetik.uzat(nufus.K)
    tetik.stoksuzluk(np.unique(k_u), d)
    kayit.sure["10 bos ziyaret"] += time.perf_counter() - t
