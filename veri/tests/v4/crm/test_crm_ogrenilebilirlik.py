"""Görev 15: B'nin öğrenilebilirliği (spec §8), TAM, yayımlanan B tohumu.

Her ölçüt iki parçadır: **öğrenen** yalnız yayımlanan tabloları okur (B'nin
altı tablosu + A'nın yayımlanan `urun` tablosu); **gizli gerçek**
(`crm_gizli_gercek`) yalnız puanlamada kullanılır (ve terk/LTV'de çapraz
doğrulamalı modelin eğitim hedefi olarak — öğrenenin özellikleri yine
yalnız yayımlanan tablolardan). Bütün rastgelelik sabit `random_state`.

Ortak tanımlar: "kartlı satış fişi" = `fis_tipi == "satis"` ve `musteri_id`
dolu (mağaza ya da online); "satış satırı" = kartlı satış fişinin `adet > 0`
satırı; gün sayıları tarih farkıdır.

segmentasyon
    Pencerede ≥ 3 kartlı satış fişi olan müşteriler. Özellikler: RFM (2025
    sonu; R = 2025-12-31 − son fiş günü, F = fiş sayısı, M = Σ fiş tutarı;
    üçü de log1p — çarpık dağılım), 17 alt kategori adet payı, indirimli
    satır payı (`indirim_tutari > 0`), online fiş payı. Standardize,
    `KMeans(7, n_init=20, random_state=0)`; gizli arketipe ARI, bant
    (kontrolcü kararı, Görev 5c) ≥ 0,08 — spec'in 0,3–0,7'si ulaşılamaz:
    gözlenen kategori payları A'nın sabit mağaza-gün satışıyla ve müşteri
    başına ~7–10 birimle sınırlı; gizli parametre tavanı 0,94, TAM
    0,092–0,095. İkincil satırlar: RFM log'suz; brief'in özellikleri + fiş
    başına ortalama adet + ortalama ödenen birim fiyat. Tanı satırları
    (öğrenen değil, gizli parametreler yalnız yorum için): aynı müşterilerde
    gizli tercih/parametrelerle k-means ARI tavanı; indirim duyarlılığı ile
    gözlenen indirimli satır payının korelasyonu.

terk
    2025-06-30'a kadar en az bir kartlı satış fişi olan müşteriler; o güne
    kadarki veriden RFM (log1p), kartlı iade fişi sayısı, son 6 ay
    (2025-01-01 – 06-30) kartlı satış fişi sayısı. Hedef gizli
    `ltv_2026.geri_gelecek_2026`. Standardize + `LogisticRegression`,
    `StratifiedKFold(5, shuffle, random_state=0)`, kat dışı olasılıkla
    AUC; bant 0,70–0,85.

LTV
    Aynı müşteriler: 2025 kartlı satış tutarı × (1 − model terk olasılığı)
    (= kat dışı P(geri gelir)); gizli `gerceklesen_harcama_2026` ile
    Spearman, bant 0,4–0,7. İkincil satır: gizli `beklenen_harcama_2026`.

öneri
    Option düzeyi (A'nın `urun.option_id`). Kartlı ve ≥ 2 kartlı satış
    fişli müşterilerin son fişi (en büyük `fis_id`; fiş kimlikleri tarih ve
    saate göre sıralı) test, öncekiler eğitim. Eğitim: müşteri × option
    ikili matrisi X; birlikte alım C = XᵀX (köşegen 0, kosinüs
    normalizasyonu C_ij / √(n_i n_j)). Skor = müşterinin eğitim option'ları
    üzerinden C satırları toplamı; müşterinin zaten aldığı option'lar
    öneriden ve test kümesinden çıkarılır (popülerlik tabanında da aynı
    kural); popülerlik = eğitim satış adedine göre ilk 10 (zaten alınanlar
    atlanarak). Test kümesi boş kalan müşteri atılır; değerlendirme sabit
    örneklemde (en çok 200.000 müşteri, `default_rng(0)`). recall@10 =
    isabet / test option sayısı, müşteri ortalaması. Kabul: öneri ≥ 1,2 ×
    popülerlik.

sıralama
    `online_liste_gunluk`, yalnız `kategori:` listeleri (arama listelerinde
    gizli enjekte hücreler var), ≥ 200 gösterimli option'lar. (i) saf TO =
    Σ tıklama / Σ gösterim; (ii) bakılma eğrisi θ̂_s = sıra s'nin ortalama
    TO'su / sıra 1'inki, IPS TO = Σ tıklama / Σ (gösterim × θ̂_sıra). Gizli
    ilgi: `tiklama_modeli.ilgi_gunluk` (gün × option, arketip karışımıyla
    ağırlıklı günlük ilgi), option başına gösterim ağırlıklı ortalama.
    Kabul: Spearman(ii) − Spearman(i) ≥ 0,1. İkincil: Görev 9'un PBM MLE
    kestirimi ve arketip ağırlıklı (sezon) ilgiyle aynı fark.

yorum konuları
    TF-IDF (kelime 1–2 gram + karakter 3–5 gram `char_wb`, `min_df=2`,
    `sublinear_tf`) + one-vs-rest `LogisticRegression`; etiket gizli
    `yorum_etiket.konular` (çoklu etiket, 7 konu); makro F1 (eşik 0,5).
    Birincil bölme (kontrolcü kararı): metin grubuna göre — yayımlanan
    metinden ürünün rengi ve beden etiketi (A'nın `urun` tablosu) yer
    tutucuya geri çevrilip küçük harfe indirgenir, aynı kalıp aynı grup;
    `GroupShuffleSplit(test_size=0,2, random_state=0)`. Bant (kontrolcü
    kararı) ≥ 0,60; spec'in 0,85 üst sınırı kalktı (kütüphane konuları
    açıkça söyler; üst sınırı aşma README / spec §11 notu).
    İkincil satır: brief'in müşteri bazlı %80/%20 bölmesi (aynı kalıp hem
    eğitimde hem testte; ezberle şişer).

Çok tohumlu koşu: `araclar/v4_crm_cok_tohum.py` (aynı yardımcılar).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from .test_crm_kalibrasyon import _aralik, _no

PENCERE_SON = np.datetime64("2025-12-31", "D")
TERK_KESIM = np.datetime64("2025-06-30", "D")
SON_6_AY = np.datetime64("2025-01-01", "D")
YIL_2025 = np.datetime64("2025-01-01", "D")

SEGMENT_EN_AZ_FIS = 3
SEGMENT_K = 7
ONERI_K = 10
ONERI_ORNEK = 200_000
ONERI_KAT = 1.2
SIRALAMA_EN_AZ_GOSTERIM = 200
SIRALAMA_PBM_TUR = 100

# (anahtar, spec §8 satırı, bant metni, geçer mi)
OGRENILEBILIRLIK = [
    # Kontrolcü kararı (Görev 5c): spec'in 0,3–0,7 bandı yerine ≥ 0,08 —
    # gözlenen kategori payları A'nın sabit mağaza-gün satışı ve müşteri başına
    # ~7–10 birimle sınırlı; gizli parametre tavanı 0,94, TAM 0,092–0,095.
    ("seg_ari", "Segmentasyon: k-means ARI", "≥ 0,08 (karar)", lambda x: x >= 0.08),
    ("terk_auc", "Terk: lojistik AUC (5 kat)", "0,70–0,85", _aralik(0.70, 0.85)),
    ("ltv_spearman", "LTV: Spearman (gerçekleşen 2026)", "0,4–0,7", _aralik(0.4, 0.7)),
    ("oneri_oran", "Öneri: recall@10 / popülerlik", "≥ 1,2", lambda x: x >= ONERI_KAT),
    ("siralama_kazanc", "Sıralama: Spearman (IPS − saf)", "≥ 0,1", lambda x: x >= 0.1),
    # Kontrolcü kararı (Görev 15): spec'in 0,60–0,85 bandının üst sınırı
    # kaldırıldı — kütüphane her etiketli konuyu metinde açıkça söyler, yüksek
    # F1 tasarım sonucu (TAM 4242/1/2: 0,95–0,97); README / spec §11'e not.
    ("yorum_f1", "Yorum konuları: makro F1 (metin grubu)", "≥ 0,60 (karar)", lambda x: x >= 0.60),
]

# İkincil / bilgi satırları
OGRENILEBILIRLIK_IZLEME = [
    ("seg_n", "Segmentasyon müşteri sayısı", "(bilgi)", None),
    ("seg_ari_logsuz", "Segmentasyon ARI, RFM log'suz", "(bilgi)", None),
    ("seg_ari_genis", "Segmentasyon ARI, + sepet ve birim fiyat", "(bilgi)", None),
    ("seg_ari_gizli_tavan", "Tanı: ARI, gizli parametrelerle k-means", "(bilgi)", None),
    ("seg_indirim_kor", "Tanı: kor(indirim duyarlılığı, indirimli satır payı)", "(bilgi)", None),
    ("terk_n", "Terk müşteri sayısı", "(bilgi)", None),
    ("terk_taban", "Terk: 2026'da gelen payı", "(bilgi)", None),
    ("ltv_spearman_beklenen", "LTV: Spearman (beklenen 2026)", "(bilgi)", None),
    ("oneri_n", "Öneri değerlendirilen müşteri", "(bilgi)", None),
    ("oneri_recall", "Öneri recall@10", "(bilgi)", None),
    ("oneri_pop_recall", "Popülerlik recall@10", "(bilgi)", None),
    ("siralama_n", "Sıralama option sayısı", "(bilgi)", None),
    ("siralama_saf", "Sıralama Spearman saf", "(bilgi)", None),
    ("siralama_ips", "Sıralama Spearman IPS", "(bilgi)", None),
    ("siralama_pbm_kazanc", "Sıralama PBM MLE − saf", "(bilgi)", None),
    ("siralama_kazanc_arketip", "Sıralama IPS − saf (arketip ağırlıklı ilgi)", "(bilgi)", None),
    ("yorum_n", "Yorum sayısı (öğrenme)", "(bilgi)", None),
    ("yorum_grup", "Metin grubu sayısı", "(bilgi)", None),
    ("yorum_grup_saflik", "Grup başına tek kütüphane metni payı", "(bilgi)", None),
    ("yorum_f1_musteri", "Yorum makro F1, müşteri bölmesi", "(bilgi)", None),
]


# ---------------------------------------------------------------------------
# Ortak hazırlık
# ---------------------------------------------------------------------------


def _gun(tarih: pd.Series) -> np.ndarray:
    return tarih.to_numpy().astype("datetime64[D]")


def _urun_kodu(seri: pd.Series, urun_idler: np.ndarray) -> np.ndarray:
    ix = pd.Index(urun_idler)
    if isinstance(seri.dtype, pd.CategoricalDtype):
        kod = ix.get_indexer(seri.cat.categories.astype(str))[seri.cat.codes.to_numpy()]
    else:
        kod = ix.get_indexer(seri.astype(str).to_numpy())
    assert (kod >= 0).all()
    return kod


class _Fisler:
    """Yayımlanan `fis` / `fis_satir`'ın öğrenenin kullandığı sayısal görünümü."""

    def __init__(self, t: dict, urun: pd.DataFrame):
        f = t["fis"]
        assert (_no(f["fis_id"]) == np.arange(len(f))).all()
        self.mus = _no(f["musteri_id"])
        self.K = int(self.mus.max()) + 1
        self.gun = _gun(f["tarih"])
        self.satis = (f["fis_tipi"] == "satis").to_numpy()
        self.online = (f["kanal"] == "online").to_numpy()
        self.tutar = f["tutar"].to_numpy(dtype=np.float64)
        self.kart = self.mus >= 0
        self.ks = self.satis & self.kart                      # kartlı satış fişi

        fs = t["fis_satir"]
        self.s_fis = _no(fs["fis_id"])
        u = _urun_kodu(fs["urun_id"], urun["urun_id"].to_numpy().astype(str))
        alt_kod, self.alt_ad = pd.factorize(urun["alt_kategori"], sort=True)
        opt_kod, self.opt_ad = pd.factorize(urun["option_id"], sort=True)
        self.s_alt = alt_kod[u]
        self.s_opt = opt_kod[u]
        self.s_adet = fs["adet"].to_numpy(dtype=np.int64)
        self.s_indirimli = fs["indirim_tutari"].to_numpy(dtype=np.float64) > 0
        self.s_tutar = fs["tutar"].to_numpy(dtype=np.float64)
        self.s_ks = self.ks[self.s_fis] & (self.s_adet > 0)   # kartlı satış satırı


def _rfm(F: _Fisler, maske: np.ndarray, referans) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`maske`li fişlerden müşteri başına (R gün, F, M); fişsiz müşteride R = −1."""
    m = F.mus[maske]
    sayi = np.bincount(m, minlength=F.K).astype(float)
    tutar = np.bincount(m, F.tutar[maske], minlength=F.K)
    son = np.full(F.K, np.datetime64("NaT", "D"))
    g = F.gun[maske]
    o = np.lexsort((g, m))
    son_ix = np.flatnonzero(np.r_[m[o][1:] != m[o][:-1], True])
    son[m[o][son_ix]] = g[o][son_ix]
    r = np.where(sayi > 0, (np.datetime64(referans, "D") - son).astype("timedelta64[D]").astype(float), -1.0)
    return r, sayi, tutar


def _gizli_mus_no(seri: pd.Series, K: int) -> tuple[np.ndarray, np.ndarray]:
    """Gizli tablodaki `musteri_id` (NA'lı) → (satır maskesi, müşteri no)."""
    dolu = seri.notna().to_numpy()
    no = _no(seri[dolu].astype("string[pyarrow]"))
    ok = no < K
    idx = np.flatnonzero(dolu)[ok]
    return idx, no[ok]


# ---------------------------------------------------------------------------
# Segmentasyon
# ---------------------------------------------------------------------------


def segmentasyon(F: _Fisler, gizli: dict) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score
    from sklearn.preprocessing import StandardScaler

    r, f, m = _rfm(F, F.ks, PENCERE_SON)
    sec = np.flatnonzero(f >= SEGMENT_EN_AZ_FIS)
    pos = np.full(F.K, -1)
    pos[sec] = np.arange(len(sec))

    sm = F.s_ks.copy()
    sm[sm] = pos[F.mus[F.s_fis[sm]]] >= 0
    p = pos[F.mus[F.s_fis[sm]]]
    A = len(F.alt_ad)
    kat = np.bincount(p * A + F.s_alt[sm], F.s_adet[sm], minlength=len(sec) * A).reshape(len(sec), A)
    kat = kat / kat.sum(axis=1, keepdims=True)
    ind = np.bincount(p, F.s_indirimli[sm], minlength=len(sec)) / np.bincount(p, minlength=len(sec))
    onl = (np.bincount(F.mus[F.ks & F.online], minlength=F.K) / np.maximum(f, 1))[sec]

    arketip = gizli["musteri_gizli"][["musteri_id", "arketip"]]
    idx, no = _gizli_mus_no(arketip["musteri_id"], F.K)
    hedef = np.full(F.K, -1)
    hedef[no] = arketip["arketip"].cat.codes.to_numpy()[idx] if isinstance(
        arketip["arketip"].dtype, pd.CategoricalDtype) else pd.factorize(arketip["arketip"])[0][idx]
    y = hedef[sec]
    assert (y >= 0).all()

    def ari(rfm):
        X = np.column_stack([rfm, kat, ind, onl])
        X = StandardScaler().fit_transform(X)
        km = KMeans(SEGMENT_K, n_init=20, random_state=0).fit(X)
        return float(adjusted_rand_score(y, km.labels_))

    rfm = np.column_stack([r[sec], f[sec], m[sec]])
    o = {"seg_n": len(sec), "seg_ari": ari(np.log1p(rfm)), "seg_ari_logsuz": ari(rfm)}
    # İkincil: brief'in özellikleri + fiş başına ortalama adet + ortalama
    # ödenen birim fiyat (ikisi de log; yayımlanan tablolardan)
    birim = np.bincount(p, F.s_adet[sm], minlength=len(sec)).astype(float)
    fiyat = np.bincount(p, F.s_tutar[sm], minlength=len(sec)) / birim
    sepet = birim / f[sec]
    X = np.column_stack([np.log1p(rfm), kat, ind, onl, np.log(sepet), np.log(np.maximum(fiyat, 1.0))])
    X = StandardScaler().fit_transform(X)
    o["seg_ari_genis"] = float(adjusted_rand_score(y, KMeans(SEGMENT_K, n_init=20, random_state=0).fit(X).labels_))

    # Tanı (öğrenen değil; gizli parametreler yalnız ölçüt yorumu için):
    # aynı müşterilerde gizli tercih/parametrelerle k-means ARI tavanı ve
    # indirim duyarlılığının gözlenen indirimli satır payıyla korelasyonu.
    mg = gizli["musteri_gizli"]
    satir = np.full(F.K, -1)
    satir[no] = idx
    mg = mg.iloc[satir[sec]]
    sut = ([c for c in mg.columns if c.startswith(("tercih_kat_", "fiyat_segment_egilim_"))]
           + ["ziyaret_hizi", "online_payi", "indirim_duyarlilik", "sepet_ort", "kart_olasiligi", "terk_p"])
    Xg = StandardScaler().fit_transform(mg[sut].to_numpy(dtype=float))
    o["seg_ari_gizli_tavan"] = float(adjusted_rand_score(
        y, KMeans(SEGMENT_K, n_init=20, random_state=0).fit(Xg).labels_))
    o["seg_indirim_kor"] = float(np.corrcoef(mg["indirim_duyarlilik"].to_numpy(dtype=float), ind)[0, 1])
    return o


# ---------------------------------------------------------------------------
# Terk ve LTV
# ---------------------------------------------------------------------------


def terk_ltv(F: _Fisler, gizli: dict) -> dict:
    from scipy.stats import spearmanr
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    once = F.gun <= TERK_KESIM
    r, f, m = _rfm(F, F.ks & once, TERK_KESIM)
    sec = np.flatnonzero(f > 0)
    iade = np.bincount(F.mus[F.kart & ~F.satis & once], minlength=F.K)
    son6 = np.bincount(F.mus[F.ks & once & (F.gun >= SON_6_AY)], minlength=F.K)
    X = np.column_stack([np.log1p(r[sec]), np.log1p(f[sec]), np.log1p(m[sec]), iade[sec], son6[sec]])

    ltv = gizli["ltv_2026"]
    idx, no = _gizli_mus_no(ltv["musteri_id"], F.K)
    gel = np.zeros(F.K, dtype=bool)
    gel[no] = ltv["geri_gelecek_2026"].to_numpy(dtype=bool)[idx]
    har = np.zeros(F.K)
    har[no] = ltv["gerceklesen_harcama_2026"].to_numpy(dtype=float)[idx]
    bek = np.zeros(F.K)
    bek[no] = ltv["beklenen_harcama_2026"].to_numpy(dtype=float)[idx]
    y = gel[sec]

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    kat = StratifiedKFold(5, shuffle=True, random_state=0)
    p = cross_val_predict(model, X, y, cv=kat, method="predict_proba")[:, 1]

    yil = F.ks & (F.gun >= YIL_2025)
    h2025 = np.bincount(F.mus[yil], F.tutar[yil], minlength=F.K)[sec]
    tahmin = h2025 * p                     # = 2025 harcaması × (1 − terk olasılığı)
    return {
        "terk_n": len(sec),
        "terk_taban": float(y.mean()),
        "terk_auc": float(roc_auc_score(y, p)),
        "ltv_spearman": float(spearmanr(tahmin, har[sec]).statistic),
        "ltv_spearman_beklenen": float(spearmanr(tahmin, bek[sec]).statistic),
    }


# ---------------------------------------------------------------------------
# Öneri
# ---------------------------------------------------------------------------


def oneri(F: _Fisler) -> dict:
    from scipy import sparse

    fis_ix = np.flatnonzero(F.ks)
    n_fis = np.bincount(F.mus[fis_ix], minlength=F.K)
    son_fis = np.full(F.K, -1)
    np.maximum.at(son_fis, F.mus[fis_ix], fis_ix)

    sm = F.s_ks
    s_mus = F.mus[F.s_fis[sm]]
    s_fis = F.s_fis[sm]
    s_opt = F.s_opt[sm]
    s_adet = F.s_adet[sm]
    uygun = n_fis[s_mus] >= 2
    test = uygun & (s_fis == son_fis[s_mus])
    egit = uygun & ~test
    O = len(F.opt_ad)

    X = sparse.csr_matrix((np.ones(egit.sum(), dtype=np.float32), (s_mus[egit], s_opt[egit])), shape=(F.K, O))
    X.data[:] = 1.0
    X.sum_duplicates()
    X.data[:] = 1.0
    T = sparse.csr_matrix((np.ones(test.sum(), dtype=np.float32), (s_mus[test], s_opt[test])), shape=(F.K, O))
    T.sum_duplicates()
    T.data[:] = 1.0
    T = T - T.multiply(X)                   # zaten alınanlar testten çıkar
    T.eliminate_zeros()

    C = (X.T @ X).toarray().astype(np.float32)
    np.fill_diagonal(C, 0.0)
    d = np.sqrt(np.asarray(X.sum(axis=0)).ravel()).astype(np.float32)
    d[d == 0] = 1.0
    C /= d[:, None]
    C /= d[None, :]

    pop = np.bincount(s_opt[egit], s_adet[egit], minlength=O)
    pop_sira = np.argsort(-pop, kind="stable")[:500]

    n_test = np.asarray(T.sum(axis=1)).ravel()
    aday = np.flatnonzero(n_test > 0)
    rng = np.random.default_rng(0)
    if len(aday) > ONERI_ORNEK:
        aday = np.sort(rng.choice(aday, ONERI_ORNEK, replace=False))

    rec_top, pop_top = 0.0, 0.0
    PARCA = 20_000
    for b in range(0, len(aday), PARCA):
        c = aday[b:b + PARCA]
        Xc = X[c]
        Tc = T[c].toarray() > 0
        Hc = Xc.toarray() > 0
        S = np.asarray(Xc @ C)
        S[Hc] = -np.inf
        top = np.argpartition(-S, ONERI_K, axis=1)[:, :ONERI_K]
        isabet = np.take_along_axis(Tc, top, axis=1).sum(axis=1)
        rec_top += float((isabet / Tc.sum(axis=1)).sum())
        # popülerlik: zaten alınanları atlayarak ilk 10
        hp = Hc[:, pop_sira]
        sec = (~hp) & (np.cumsum(~hp, axis=1) <= ONERI_K)
        pisabet = (Tc[:, pop_sira] & sec).sum(axis=1)
        pop_top += float((pisabet / Tc.sum(axis=1)).sum())
    n = len(aday)
    rec, prec = rec_top / n, pop_top / n
    return {"oneri_n": n, "oneri_recall": rec, "oneri_pop_recall": prec, "oneri_oran": rec / prec}


# ---------------------------------------------------------------------------
# Sıralama
# ---------------------------------------------------------------------------


def siralama(t: dict, gizli: dict) -> dict:
    from scipy.stats import spearmanr

    gl = t["online_liste_gunluk"]
    gl = gl[gl["liste"].astype(str).str.startswith("kategori:").to_numpy()]
    opt = gl["option_id"].astype(str)
    n_o = gl.groupby(opt.to_numpy())["gosterim"].sum()
    secili = n_o.index[n_o >= SIRALAMA_EN_AZ_GOSTERIM]
    tut = opt.isin(secili).to_numpy()
    gl, opt = gl[tut], opt[tut]
    o_kod, o_ad = pd.factorize(opt.to_numpy())
    s_kod = gl["sira"].to_numpy().astype(np.int64) - 1
    n = gl["gosterim"].to_numpy(dtype=float)
    c = gl["tiklama"].to_numpy(dtype=float)
    O, P = len(o_ad), int(s_kod.max()) + 1

    saf = np.bincount(o_kod, c, O) / np.bincount(o_kod, n, O)
    # (ii) sıra başına ortalama TO'dan bakılma eğrisi, IPS
    to_sira = np.bincount(s_kod, c, P) / np.maximum(np.bincount(s_kod, n, P), 1e-12)
    theta = to_sira / to_sira[0]
    ips = np.bincount(o_kod, c, O) / np.bincount(o_kod, n * theta[s_kod], O)
    # PBM (Görev 9; ikincil)
    th = np.ones(P)
    for _ in range(SIRALAMA_PBM_TUR):
        gamma = np.bincount(o_kod, c, O) / np.maximum(np.bincount(o_kod, n * th[s_kod], O), 1e-12)
        th = np.bincount(s_kod, c, P) / np.maximum(np.bincount(s_kod, n * gamma[o_kod], P), 1e-12)
        th /= th[0]

    # gizli: günlük ilgi, gösterim ağırlıklı
    tm = gizli["tiklama_modeli"]
    ig = tm["ilgi_gunluk"]
    ig = pd.DataFrame({"tarih": ig["tarih"].to_numpy(), "option_id": ig["option_id"].astype(str).to_numpy(),
                       "ilgi": ig["ilgi"].to_numpy()})
    b = pd.DataFrame({"tarih": gl["tarih"].to_numpy(), "option_id": opt.to_numpy()}).merge(
        ig, on=["tarih", "option_id"], how="left")
    assert b["ilgi"].notna().all()
    gercek = np.bincount(o_kod, b["ilgi"].to_numpy() * n, O) / np.bincount(o_kod, n, O)

    # ikincil gizli: sezon ilgisinin pencere ortalaması arketip ağırlığıyla
    il = tm["ilgi"]
    w = tm["arketip_agirligi"].groupby("arketip")["agirlik"].mean()
    il = il.assign(w=il["arketip"].map(w).to_numpy(dtype=float))
    il = il.assign(wi=il["ilgi"] * il["w"])
    g2 = il.groupby(il["option_id"].astype(str)).agg(wi=("wi", "sum"), w=("w", "sum"))
    gercek2 = (g2["wi"] / g2["w"]).reindex(o_ad).to_numpy()

    def rho(x, g):
        return float(spearmanr(x, g).statistic)

    r_saf, r_ips, r_pbm = rho(saf, gercek), rho(ips, gercek), rho(gamma, gercek)
    return {
        "siralama_n": O, "siralama_saf": r_saf, "siralama_ips": r_ips, "siralama_kazanc": r_ips - r_saf,
        "siralama_pbm_kazanc": r_pbm - r_saf,
        "siralama_kazanc_arketip": rho(ips, gercek2) - rho(saf, gercek2),
    }


# ---------------------------------------------------------------------------
# Yorum konuları
# ---------------------------------------------------------------------------


def _turkce_kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def metin_grubu(yorum: pd.DataFrame, urun: pd.DataFrame) -> np.ndarray:
    """Yayımlanan metinden ürünün rengi ve beden etiketi yer tutucuya geri
    çevrilir, küçük harf; aynı kalıp → aynı grup kodu."""
    u = urun.set_index(urun["urun_id"].astype(str))
    uid = yorum["urun_id"].astype(str).to_numpy()
    renk = u["renk"].reindex(uid).astype(str).to_numpy()
    beden = u["beden"].reindex(uid).astype(str).to_numpy()
    out = []
    for m, r, b in zip(yorum["metin"].astype(str).to_numpy(), renk, beden):
        m = _turkce_kucuk(m)
        m = re.sub(r"(?<!\w)" + re.escape(_turkce_kucuk(r)) + r"(?!\w)", "{renk}", m)
        if b and b != "STD":
            m = re.sub(r"(?<!\w)" + re.escape(_turkce_kucuk(b)) + r"(?!\w)", "{beden}", m)
        out.append(m)
    return pd.factorize(np.asarray(out, dtype=object))[0]


def _konu_f1(metin: np.ndarray, Y: np.ndarray, egit: np.ndarray, test: np.ndarray) -> float:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.pipeline import make_pipeline, make_union

    vek = make_union(
        TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True),
    )
    model = make_pipeline(vek, OneVsRestClassifier(LogisticRegression(max_iter=1000)))
    model.fit(metin[egit], Y[egit])
    return float(f1_score(Y[test], model.predict(metin[test]), average="macro", zero_division=0))


def yorum_konulari(t: dict, gizli: dict, urun: pd.DataFrame) -> dict:
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.preprocessing import MultiLabelBinarizer

    y = t["yorum"]
    e = gizli["yorum_etiket"]
    e = e.set_index(e["yorum_id"].astype(str)).reindex(y["yorum_id"].astype(str).to_numpy())
    assert e["konular"].notna().all()
    Y = MultiLabelBinarizer().fit_transform(e["konular"].astype(str).str.split(","))
    assert Y.shape[1] == 7
    metin = y["metin"].astype(str).to_numpy()
    grup = metin_grubu(y, urun)
    kut = e["kutuphane_id"].to_numpy()
    saflik = float((pd.Series(kut).groupby(grup).nunique() == 1).mean())

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
    egit, test = next(gss.split(metin, groups=grup))
    f1 = _konu_f1(metin, Y, egit, test)
    mus = pd.factorize(y["musteri_id"].astype(str))[0]
    egit2, test2 = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0).split(metin, groups=mus))
    f1_m = _konu_f1(metin, Y, egit2, test2)
    return {"yorum_n": len(y), "yorum_grup": int(grup.max() + 1), "yorum_grup_saflik": saflik,
            "yorum_f1": f1, "yorum_f1_musteri": f1_m}


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------


def ogrenilebilirlik_olcutleri(tablolar: dict, gizli: dict, urun: pd.DataFrame, sure: dict | None = None) -> dict:
    """Bir B koşusunun öğrenilebilirlik ölçütleri (birincil + ikincil).
    `urun`: A'nın yayımlanan ürün tablosu."""
    import time

    o: dict = {}
    sure = {} if sure is None else sure
    t = time.perf_counter()
    F = _Fisler(tablolar, urun)
    sure["hazirlik"] = time.perf_counter() - t
    for ad, fn in (("segmentasyon", lambda: segmentasyon(F, gizli)), ("terk_ltv", lambda: terk_ltv(F, gizli)),
                   ("oneri", lambda: oneri(F)), ("siralama", lambda: siralama(tablolar, gizli)),
                   ("yorum", lambda: yorum_konulari(tablolar, gizli, urun))):
        t = time.perf_counter()
        o.update(fn())
        sure[ad] = time.perf_counter() - t
    o["ogrenme_sn"] = {k: round(v, 1) for k, v in sure.items()}
    return o


# ---------------------------------------------------------------------------
# Testler (TAM, CRM_TOHUM)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.yavas


@pytest.fixture(scope="module")
def ogrenme(tam_crm):
    o = ogrenilebilirlik_olcutleri(tam_crm["tablolar"], tam_crm["gizli"], tam_crm["girdi"].dunya.urunler)
    print("\nB öğrenilebilirliği (TAM, CRM_TOHUM):")
    for anahtar, satir, bant, _ in OGRENILEBILIRLIK + OGRENILEBILIRLIK_IZLEME:
        print(f"  {satir:44s} {o[anahtar]!s:>22.22} {bant}")
    print(f"  süreler {o['ogrenme_sn']}")
    return o


@pytest.mark.parametrize("anahtar", [b[0] for b in OGRENILEBILIRLIK])
def test_ogrenilebilirlik(ogrenme, anahtar):
    _, satir, bant, gecer = next(b for b in OGRENILEBILIRLIK if b[0] == anahtar)
    assert gecer(ogrenme[anahtar]), f"{satir}: {ogrenme[anahtar]:.4f} (bant {bant})"
