"""Basit kestiricinin gün karakteri: çarpımsal çarpanlar (spec §4.4).

    karakter = hafta_gunu(kanal, gün) × özel gün × (1 − oran)^(−ε̂_kampanya(üst kategori))
               × yaşam(line, alt kategori, yaş haftası)

Bütün çarpanlar stoklu hücre-günlerden öğrenilir (`durum = stoklu`; hedef
`brut_satis`, iade talep değildir; `tukenen` günler sansürlüdür). `ogren`e
yalnız 2023–2024 verilir. Girdi `ozellikler.ekle` biçimindedir.

Öğrenme sırası ve kurallar (her adım öncekinin çarpanını satıştan çıkarır):

    hafta_gunu   kanal başına; tatil, Black Friday, indirim başlangıcı ve
                 kampanya günleri dışarıda. Hafta × haftanın günü çarpımsal
                 Poisson modeli (iteratif orantılı uydurma): her takvim
                 haftasının kendi düzeyi olur, mevsim ve kampanya dışı günlerin
                 hafta içi dağılımı oranı bozmaz. Yedi günün ortalaması 1.
    esneklik_kampanya
                 fark-içinde-fark. Her kampanya için kapsanan hücrelerin
                 kampanya günlerindeki stoklu günlük satışı ÷ önceki 14 günün
                 stoklu günlük satışı; aynı oran kapsam dışı hücrelerde
                 (kampanyanın hiç dokunmadığı mağazalarda, aynı kanal × üst
                 kategori × line katmanında) — oranların oranı. Satış önce hafta
                 günü çarpanına bölünür. Yalnız markdown'sız satırlar;
                 kapsanan hücrenin kampanya günü o kampanyanın günüdür, ön
                 dönem ve kontrol satırları kampanyasız. İki dönemde de stoklu
                 günü olan hücreler sayılır. ε̂ = ln(oran) / (−ln(1 − kampanya
                 oranı)); üst kategori başına kapsanan hücre-gün ağırlıklı
                 ortalama. `"*"` anahtarı bütün katmanların ortalamasıdır;
                 tahmini olmayan üst kategoride karakter onu kullanır. Kontrolü
                 olmayan kampanya (kapsamı boş: ikinci ürün, Black Friday)
                 katkı vermez.
    ozel_gun     black_friday (BF dönemindeki cuma), black_friday_devami (BF
                 döneminin diğer günleri), tatil, indirim_baslangici; bir gün
                 tek türdür, bu öncelikle (v4 takviminde BF cuması tatildir ama
                 trafiği tatilin tersidir; BF sıçraması yalnız cumadadır). Satış fiyat
                 çarpanına bölünür (fiyat etkisi çıkar), option × kanal × gün
                 düzeyine toplanır; o türdeki her gün aynı option'ın aynı
                 haftagünündeki komşularıyla kıyaslanır: simetrik çiftler
                 (−7, +7) ve (−14, +14), iki ucu da özel ve kampanya günü
                 değilse (doğrusal eğilim götürülür); Σ satış ÷ Σ (stoklu
                 SKU-gün × komşuların SKU-gün hızı). Gözlenmeyen tür sözlükte
                 yoktur (çarpanı 1).
    esneklik_markdown
                 yalnız raporlanır, karakterde yok. Markdown oranının bir
                 pazartesi yükseldiği hücrelerde, iki yandaki 14 gün (önceki
                 iki hafta p0'da, sonraki iki hafta p1'de sabit), kontrol grubu
                 yok. Satış hafta günü ve özel gün çarpanlarına bölünür,
                 kampanya günleri dışarıda. (üst kategori, kanal, pazartesi,
                 p0, p1) başına havuzlanmış oran; ε̂ = ln(oran) /
                 (−ln((1 − p1)/(1 − p0))); üst kategori başına hücre-gün
                 ağırlıklı ortalama. Markdown içsel olduğundan (satmayana
                 indirim gelir) yanlıdır; yazının esneklik tuzağı.
    yasam        line × alt kategori × yaş haftası (yas_gun // 7) başına
                 Σ düzeltilmiş satış ÷ Σ stoklu hücre-gün; düzeltme hafta günü
                 × özel gün × fiyat. 100'den az hücre-günlü hafta komşu
                 haftalardan doldurulur. 0–4. haftaların ortalamasına
                 normalize. Devamlıda (yas_gun −1) 1; öğrenilen son haftadan
                 sonrası son haftanın değeri.
    beden_payi   mağaza × option içinde SKU'ların stoklu-gün satış hızı payı
                 (hız = Σ satış ÷ stoklu gün; bir bedenin az stoklu kalması
                 payını düşürmez). Mağaza × option'da 30'dan az stoklu SKU-gün
                 varsa satır yazılmaz; zincir payı (`magaza_id = "*"`) kullanılır.

Kestiriciler (`talep`) beden payını kendi gözlem havuzundan `beden_payi` ile
yeniden kurar: payı ürüne özgüdür ve 2025'in yeni option'ları 2023–2024'te yok.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Özel gün türleri, öncelik sırasıyla (bir günün tek türü olur). Black Friday
# kampanyası cuma başlar ve birkaç gün sürer; trafik sıçraması yalnız cumadadır
# (v4: cuma ×1,8, sonraki günler ×1,0, fiyat etkisi çıkınca), bu yüzden iki tür:
# `black_friday` (BF dönemindeki cuma) ve `black_friday_devami`. v4 takviminde
# BF cuması `tatil_mi`dir ama trafiği tatilin tersidir: BF tatilden önce gelir.
# Tatil etkisi indirim başlangıcınınkinden güçlüdür.
OZEL_GUNLER = ("black_friday", "black_friday_devami", "tatil", "indirim_baslangici")
_CUMA = 4
ON_GUN = 14           # kampanya ön dönemi ve markdown penceresi (gün)
BEDEN_ESIGI = 30      # mağaza × option payı için en az stoklu SKU-gün
YASAM_ESIGI = 100     # bir yaş haftasında en az stoklu hücre-gün
_KOMSULAR = (7, 14)   # özel günün aynı haftagünündeki komşuları (± gün)
_ESNEKLIK_VARSAYILAN = 0.0


def _bos_yasam() -> pd.DataFrame:
    return pd.DataFrame({"line": pd.Series(dtype=object), "alt_kategori": pd.Series(dtype=object),
                         "yas_hafta": pd.Series(dtype=np.int32),
                         "indeks": pd.Series(dtype=np.float64)})


def _bos_beden() -> pd.DataFrame:
    return pd.DataFrame({k: pd.Series(dtype=object) for k in ("magaza_id", "option_id", "urun_id")}
                        | {"pay": pd.Series(dtype=np.float64)})


@dataclass
class Carpanlar:
    """Öğrenilmiş çarpanlar. Eksik anahtar nötrdür: hafta günü ve özel gün 1,
    esneklik `"*"` (o da yoksa 0), tabloda olmayan yaşam grubu 1."""
    hafta_gunu: dict = field(default_factory=dict)          # (kanal, 0..6) -> çarpan
    ozel_gun: dict = field(default_factory=dict)            # tür -> çarpan
    esneklik_kampanya: dict = field(default_factory=dict)   # ust_kategori -> ε̂ ("*" hepsi)
    esneklik_markdown: dict = field(default_factory=dict)   # ust_kategori -> ε̂ ("*" hepsi)
    yasam: pd.DataFrame = field(default_factory=_bos_yasam)
    beden_payi: pd.DataFrame = field(default_factory=_bos_beden)


# ------------------------------------------------------------------ yardımcı

def gun_sayisi(tarih: pd.Series) -> np.ndarray:
    """Tarih sütunu -> 1970-01-01'den gün sayısı (int32)."""
    return tarih.to_numpy().astype("datetime64[D]").astype(np.int64).astype(np.int32)


def kodlar(seri: pd.Series) -> tuple[np.ndarray, pd.Index]:
    """(satır -> kategori kodu (int32, boş -1), kategoriler).

    Kodlardan anahtar kurarken önce int64'e çevrilmeli (taşma)."""
    if isinstance(seri.dtype, pd.CategoricalDtype):
        return seri.cat.codes.to_numpy().astype(np.int32), seri.cat.categories
    kod, kategoriler = pd.factorize(seri, use_na_sentinel=True)
    return kod.astype(np.int32), pd.Index(kategoriler)


def yalniz_stoklu(df: pd.DataFrame) -> pd.DataFrame:
    """`durum` sütunu varsa yalnız stoklu satırlar (hepsi stokluysa kopyasız)."""
    if "durum" not in df.columns:
        return df
    stoklu = (df["durum"] == "stoklu").to_numpy()
    return df if stoklu.all() else df[stoklu]


def ozel_turleri(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Satır başına tek özel tür (`OZEL_GUNLER` önceliğiyle): tür -> bool dizi.

    Okunan sütunlar: black_friday, hafta_gunu, tatil, indirim_baslangici."""
    bf = df["black_friday"].to_numpy(bool)
    cuma = df["hafta_gunu"].to_numpy() == _CUMA
    ham = {"black_friday": bf & cuma, "black_friday_devami": bf & ~cuma,
           "tatil": df["tatil"].to_numpy(bool), "indirim_baslangici": df["indirim_baslangici"].to_numpy(bool)}
    sonuc, alindi = {}, np.zeros(len(df), dtype=bool)
    for ad in OZEL_GUNLER:
        sonuc[ad] = ham[ad] & ~alindi
        alindi |= sonuc[ad]
    return sonuc


def _sozlukten(kod: np.ndarray, kategoriler: pd.Index, sozluk: dict, varsayilan: float) -> np.ndarray:
    """Kategori kodlarını sözlük değerine çevirir (döngü kategoriler üzerinde)."""
    tablo = np.array([float(sozluk.get(str(k), varsayilan)) for k in kategoriler] + [varsayilan])
    return tablo[np.where(kod >= 0, kod, len(kategoriler))]


def _fiyat_carpani(oran: np.ndarray, eps: np.ndarray) -> np.ndarray:
    """(1 − oran)^(−ε)."""
    return np.exp(-eps * np.log1p(-np.clip(oran, 0.0, 0.99)))


def _gruplu_toplam(anahtar: np.ndarray, *degerler: np.ndarray):
    """Anahtar (>= 0) başına toplamlar: (benzersiz anahtarlar sıralı, toplam dizileri...).

    Anahtar aralığı küçükse yoğun `bincount` (sıralama yok, ek bellek az)."""
    if len(anahtar) == 0:
        return (anahtar.astype(np.int64), *[np.zeros(0) for _ in degerler])
    ust = int(anahtar.max()) + 1
    if ust <= 4 * len(anahtar) + 10_000_000:
        sayi = np.bincount(anahtar, minlength=ust)
        var = np.flatnonzero(sayi)
        return (var.astype(np.int64),
                *[np.bincount(anahtar, weights=v, minlength=ust)[var] for v in degerler])
    benzersiz, ters = np.unique(anahtar, return_inverse=True)
    return (benzersiz, *[np.bincount(ters, weights=v, minlength=len(benzersiz)) for v in degerler])


# --------------------------------------------------------------- hafta günü

def _hafta_gunu(kanal: np.ndarray, pazartesi: np.ndarray, hg: np.ndarray, s: np.ndarray,
                nkanal: int) -> np.ndarray:
    """[kanal, 0..6] çarpan tablosu: satış ~ hafta düzeyi × gün çarpanı (IPF)."""
    tablo = np.ones((nkanal, 7))
    if len(s) == 0:
        return tablo
    p0 = int(pazartesi.min())
    nh = int((pazartesi.max() - p0) // 7) + 1
    i = (kanal * nh + (pazartesi - p0) // 7) * 7 + hg
    S = np.bincount(i, weights=s, minlength=nkanal * nh * 7).reshape(nkanal, nh, 7)
    N = np.bincount(i, minlength=nkanal * nh * 7).reshape(nkanal, nh, 7).astype(np.float64)
    f = np.ones((nkanal, 7))
    with np.errstate(divide="ignore", invalid="ignore"):
        for _ in range(200):
            payda = (N * f[:, None, :]).sum(2)
            w = np.where(payda > 0, S.sum(2) / payda, 0.0)
            payda = (N * w[:, :, None]).sum(1)
            yeni = np.where(payda > 0, S.sum(1) / payda, np.nan)
            yeni = yeni / np.nanmean(yeni, axis=1, keepdims=True)
            yakin = np.allclose(np.nan_to_num(yeni, nan=1.0), np.nan_to_num(f, nan=1.0),
                                rtol=0, atol=1e-10)
            f = yeni
            if yakin:
                break
    f = np.where(np.isfinite(f) & (f > 0), f, 1.0)
    return f / f.mean(axis=1, keepdims=True)


# ------------------------------------------------------ kampanya esnekliği

def _agirlikli(kayit: list[tuple[str, float, float]]) -> dict[str, float]:
    """[(üst kategori, ε̂, ağırlık)] -> üst kategori başına ve "*" ağırlıklı ortalama."""
    if not kayit:
        return {}
    d = pd.DataFrame(kayit, columns=["ust", "eps", "w"])
    d["we"] = d["eps"] * d["w"]
    g = d.groupby("ust")[["we", "w"]].sum()
    sonuc = {str(k): float(v) for k, v in (g["we"] / g["w"]).items()}
    sonuc["*"] = float(d["we"].sum() / d["w"].sum())
    return sonuc


def _donem_toplamlari(hucre: np.ndarray, grup: np.ndarray, katman: np.ndarray,
                      sonra: np.ndarray, s: np.ndarray) -> pd.DataFrame:
    """Hücre başına iki dönemin (önce/sonra) satış ve gün sayısı; yalnız iki dönemde de
    stoklu günü olan hücreler; (grup, katman) başına toplam."""
    d = pd.DataFrame({"h": hucre, "g": grup, "k": katman, "sonra": sonra,
                      "s": s.astype(np.float64), "n": 1.0})
    c = d.groupby(["h", "g", "k", "sonra"], sort=False)[["s", "n"]].sum().unstack("sonra")
    c = c.dropna()
    c.columns = [f"{a}_{'sonra' if b else 'once'}" for a, b in c.columns]
    for k in ("s_once", "n_once", "s_sonra", "n_sonra"):
        if k not in c.columns:
            c[k] = 0.0
    return c.groupby(level=["g", "k"]).sum()


def _esneklik_kampanya(gun, hucre, magaza, katman, katman_ust, s_h, kamp, kid, md,
                       ustler: pd.Index) -> dict[str, float]:
    sira = np.argsort(gun, kind="stable")
    gs = gun[sira]
    kayit = []
    for c in np.unique(kid[kid >= 0]):
        ic = np.flatnonzero(kid == c)
        gunler = np.unique(gun[ic])
        bas, bit = int(gunler[0]), int(gunler[-1])
        oran = float(kamp[ic].max())
        if not 0 < oran < 1:
            continue
        p = sira[np.searchsorted(gs, bas - ON_GUN, "left"):np.searchsorted(gs, bit, "right")]
        g = gun[p]
        once = g < bas
        kampanya_gunu = ~once & np.isin(g, gunler)
        temiz = md[p] <= 0
        kampsiz = kamp[p] <= 0
        tedavi = np.isin(hucre[p], np.unique(hucre[ic]))
        kontrol = ~tedavi & ~np.isin(magaza[p], np.unique(magaza[ic]))
        sec = temiz & ((tedavi & ((once & kampsiz) | (kampanya_gunu & (kid[p] == c))))
                       | (kontrol & kampsiz & (once | kampanya_gunu)))
        p, once = p[sec], once[sec]
        if len(p) == 0:
            continue
        t = _donem_toplamlari(hucre[p], np.where(tedavi[sec], 0, 1), katman[p], ~once, s_h[p])
        if 0 not in t.index.get_level_values("g") or 1 not in t.index.get_level_values("g"):
            continue
        tr, ct = t.xs(0, level="g"), t.xs(1, level="g")
        ortak = tr.index.intersection(ct.index)
        tr, ct = tr.loc[ortak], ct.loc[ortak]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = ((tr["s_sonra"] / tr["n_sonra"]) / (tr["s_once"] / tr["n_once"])
                 / ((ct["s_sonra"] / ct["n_sonra"]) / (ct["s_once"] / ct["n_once"])))
        x = -np.log(1.0 - oran)
        for k, rr in r.items():
            if np.isfinite(rr) and rr > 0 and katman_ust[k] >= 0:
                kayit.append((str(ustler[katman_ust[k]]), float(np.log(rr) / x),
                              float(tr.at[k, "n_sonra"])))
    return _agirlikli(kayit)


# ------------------------------------------------------ markdown esnekliği

def _esneklik_markdown(hucre, pazartesi, s_adj, md, kamp, kanal, ust,
                       ustler: pd.Index) -> dict[str, float]:
    if len(hucre) == 0:
        return {}
    p0 = int(pazartesi.min())
    nh = int((pazartesi.max() - p0) // 7) + 1
    # hücre-hafta tablosu: markdown en küçük / en büyük, kampanyasız satış ve gün
    anahtar = hucre.astype(np.int64) * nh + (pazartesi - p0) // 7
    sira = np.argsort(anahtar, kind="stable")
    a = anahtar[sira]
    del anahtar
    bas = np.flatnonzero(np.r_[True, a[1:] != a[:-1]])
    a = a[bas]
    mds = md[sira]
    md_min, md_max = np.minimum.reduceat(mds, bas), np.maximum.reduceat(mds, bas)
    del mds
    kampsiz = kamp[sira] <= 0
    S = np.add.reduceat(np.where(kampsiz, s_adj[sira], 0.0), bas)
    N = np.add.reduceat(kampsiz.astype(np.float64), bas)
    del kampsiz, sira
    h, w = a // nh, a % nh
    hk = np.zeros(int(hucre.max()) + 1, dtype=np.int32)   # hücrenin kanalı / üst kategorisi
    hu = np.zeros(int(hucre.max()) + 1, dtype=np.int32)
    hk[hucre], hu[hucre] = kanal, ust
    sabit = md_min == md_max
    n = len(a)
    i = np.arange(2, n - 1)
    if len(i) == 0:
        return {}

    def ayni(j, fark):
        return (h[j] == h[i]) & (w[i] - w[j] == fark)

    adim = (ayni(i - 1, 1) & ayni(i - 2, 2) & ayni(i + 1, -1)
            & sabit[i] & sabit[i - 1] & sabit[i - 2] & sabit[i + 1]
            & (md_min[i] > md_min[i - 1]) & (md_min[i - 1] == md_min[i - 2])
            & (md_min[i + 1] == md_min[i]))
    i = i[adim]
    on_s, on_n = S[i - 2] + S[i - 1], N[i - 2] + N[i - 1]
    son_s, son_n = S[i] + S[i + 1], N[i] + N[i + 1]
    ok = (on_n > 0) & (son_n > 0)
    i, on_s, on_n, son_s, son_n = i[ok], on_s[ok], on_n[ok], son_s[ok], son_n[ok]
    g = pd.DataFrame({"ust": hu[h[i]], "kanal": hk[h[i]], "w": w[i],
                      "p0": np.round(md_min[i - 1].astype(np.float64), 4),
                      "p1": np.round(md_min[i].astype(np.float64), 4),
                      "on_s": on_s, "on_n": on_n, "son_s": son_s, "son_n": son_n})
    g = g.groupby(["ust", "kanal", "w", "p0", "p1"])[["on_s", "on_n", "son_s", "son_n"]].sum()
    kayit = []
    for (u, _, _, q0, q1), r in g.iterrows():
        if u < 0 or r["on_s"] <= 0 or r["son_s"] <= 0:
            continue
        oran = (r["son_s"] / r["son_n"]) / (r["on_s"] / r["on_n"])
        x = -np.log((1 - q1) / (1 - q0))
        kayit.append((str(ustler[int(u)]), float(np.log(oran) / x), float(r["son_n"])))
    return _agirlikli(kayit)


# ------------------------------------------------------------------ özel gün

def _ozel_gun(opt, kanal, nkanal, gun, a, bayrak: dict, kampli) -> dict[str, float]:
    if len(gun) == 0:
        return {}
    g0 = int(gun.min()) - 20
    ng = int(gun.max()) - g0 + 21
    anahtar = (opt.astype(np.int64) * nkanal + kanal) * ng + (gun - g0)
    K, A, N, kamp, *tur = _gruplu_toplam(anahtar, a, np.ones(len(a)), kampli,
                                         *bayrak.values())
    del anahtar
    tur = dict(zip(bayrak, [t > 0 for t in tur]))
    ozel = np.zeros(len(K), dtype=bool)
    for t in tur.values():
        ozel |= t
    gecerli = ~ozel & (kamp <= 0)

    def komsu(o):
        j = np.minimum(np.searchsorted(K, K + o), len(K) - 1)
        return j, (K[j] == K + o) & gecerli[j]

    # simetrik çiftler (−7, +7), (−14, +14): iki ucu da geçerliyse sayılır, doğrusal
    # eğilim (mevsim, yaşam) kendini götürür
    kA, kN = np.zeros(len(K)), np.zeros(len(K))
    for o in _KOMSULAR:
        (j1, b1), (j2, b2) = komsu(-o), komsu(o)
        cift = b1 & b2
        kA += np.where(cift, A[j1] + A[j2], 0.0)
        kN += np.where(cift, N[j1] + N[j2], 0.0)
    sonuc = {}
    for ad, t in tur.items():
        yalniz = t & (kN > 0)
        for diger, td in tur.items():
            if diger != ad:
                yalniz &= ~td
        beklenen = (N[yalniz] * kA[yalniz] / kN[yalniz]).sum()
        if beklenen > 0:
            sonuc[ad] = float(A[yalniz].sum() / beklenen)
    return sonuc


# --------------------------------------------------------------------- yaşam

def _yasam(line, lines: pd.Index, alt, altlar: pd.Index, yas, a) -> pd.DataFrame:
    m = (yas >= 0) & (line >= 0) & (alt >= 0)
    if not m.any():
        return _bos_yasam()
    yh = (yas[m] // 7).astype(np.int64)
    nw = int(yh.max()) + 1
    na = len(altlar)
    i = (line[m] * na + alt[m]) * nw + yh
    boy = len(lines) * na * nw
    S = np.bincount(i, weights=a[m], minlength=boy).reshape(len(lines), na, nw)
    N = np.bincount(i, minlength=boy).reshape(len(lines), na, nw)
    parcalar = []
    for li, ai in zip(*np.nonzero(N.sum(2))):
        n = N[li, ai]
        son = int(np.flatnonzero(n)[-1]) + 1
        n, s = n[:son], S[li, ai, :son]
        esik = YASAM_ESIGI if (n >= YASAM_ESIGI).any() else 1
        with np.errstate(divide="ignore", invalid="ignore"):
            idx = pd.Series(np.where(n >= esik, s / n, np.nan))
        idx = idx.interpolate(limit_area="inside").ffill().bfill()
        taban = idx.iloc[:5].mean()
        if not np.isfinite(taban) or taban <= 0:
            continue
        idx = (idx / taban).clip(lower=1e-3)
        parcalar.append(pd.DataFrame({"line": str(lines[li]), "alt_kategori": str(altlar[ai]),
                                      "yas_hafta": np.arange(son, dtype=np.int32),
                                      "indeks": idx.to_numpy()}))
    return pd.concat(parcalar, ignore_index=True) if parcalar else _bos_yasam()


def _yasam_carpani(df: pd.DataFrame, yasam: pd.DataFrame) -> np.ndarray:
    n = len(df)
    if yasam.empty or n == 0:
        return np.ones(n)
    yas = df["yas_gun"].to_numpy().astype(np.int64)
    line, lines = kodlar(df["line"])
    alt, altlar = kodlar(df["alt_kategori"])
    gruplar = yasam[["line", "alt_kategori"]].drop_duplicates().reset_index(drop=True)
    harita = np.full((len(lines) + 1, len(altlar) + 1), -1, dtype=np.int64)
    li = pd.Index(lines.astype(str)).get_indexer(gruplar["line"].astype(str))
    ai = pd.Index(altlar.astype(str)).get_indexer(gruplar["alt_kategori"].astype(str))
    var = (li >= 0) & (ai >= 0)
    harita[li[var], ai[var]] = np.flatnonzero(var)
    grup = harita[np.where(line >= 0, line, len(lines)), np.where(alt >= 0, alt, len(altlar))]

    # yoğun tablo: [grup, yaş haftası]; son satır "grup yok" (1)
    gk = pd.MultiIndex.from_frame(gruplar).get_indexer(
        pd.MultiIndex.from_frame(yasam[["line", "alt_kategori"]]))
    yh = yasam["yas_hafta"].to_numpy().astype(np.int64)
    nw = int(yh.max()) + 1
    M = np.full((len(gruplar) + 1, nw), np.nan)
    M[gk, yh] = yasam["indeks"].to_numpy()
    son = np.zeros(len(gruplar) + 1, dtype=np.int64)     # grubun öğrenilen son haftası
    np.maximum.at(son, gk, yh)
    M = pd.DataFrame(M).ffill(axis=1).bfill(axis=1).to_numpy()
    M[-1] = 1.0
    hafta = np.clip(yas // 7, 0, son[grup])
    return np.where((yas >= 0) & (grup >= 0), M[grup, hafta], 1.0)


# ---------------------------------------------------------------- beden payı

def beden_payi_kod(m, u, o, s, nu: int, esik: int = BEDEN_ESIGI):
    """Kod düzeyinde beden payı.

    Döner: (mağaza anahtarları `m*nu+u` sıralı, mağaza payları, zincir payı
    `nu` boyunda (NaN: SKU havuzda yok), option başına SKU sayısı (boy o.max()+1))."""
    anahtar, S, N = _gruplu_toplam(m.astype(np.int64) * nu + u, s, np.ones(len(s)))
    mm, uu = anahtar // nu, anahtar % nu
    opt_u = np.full(nu, -1, dtype=np.int64)
    opt_u[u] = o
    oo = opt_u[uu]
    hiz = S / N
    _, ters = np.unique(mm * (int(oo.max()) + 1 if len(oo) else 1) + oo, return_inverse=True)
    toplam_n = np.bincount(ters, weights=N)[ters]
    toplam_hiz = np.bincount(ters, weights=hiz)[ters]
    tut = (toplam_n >= esik) & (toplam_hiz > 0)
    m_anahtar, m_pay = anahtar[tut], hiz[tut] / toplam_hiz[tut]

    zS = np.bincount(u, weights=s, minlength=nu)
    zN = np.bincount(u, minlength=nu).astype(np.float64)
    var = zN > 0
    zhiz = np.where(var, zS / np.where(var, zN, 1.0), 0.0)
    no = int(o.max()) + 1 if len(o) else 0
    o_u = np.where(opt_u >= 0, opt_u, no)
    ohiz = np.bincount(o_u[var], weights=zhiz[var], minlength=no + 1)
    osayi = np.bincount(o_u[var], minlength=no + 1).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        z_pay = np.where(ohiz[o_u] > 0, zhiz / ohiz[o_u], 1.0 / osayi[o_u])
    z_pay = np.where(var, z_pay, np.nan)
    return m_anahtar, m_pay, z_pay, osayi[:no]


def _beden_tablosu(m, u, o, s, magazalar, urunler, opsiyonlar, esik) -> pd.DataFrame:
    nu = len(urunler)
    m_anahtar, m_pay, z_pay, _ = beden_payi_kod(m, u, o, s, nu, esik)
    opt_u = np.full(nu, -1, dtype=np.int64)
    opt_u[u] = o
    zu = np.flatnonzero(np.isfinite(z_pay))
    magaza = np.concatenate([np.asarray(magazalar.astype(str), dtype=object)[m_anahtar // nu],
                             np.full(len(zu), "*", dtype=object)])
    urun = np.concatenate([m_anahtar % nu, zu])
    return pd.DataFrame({
        "magaza_id": magaza,
        "option_id": np.asarray(opsiyonlar.astype(str), dtype=object)[opt_u[urun]],
        "urun_id": np.asarray(urunler.astype(str), dtype=object)[urun],
        "pay": np.concatenate([m_pay, z_pay[zu]]),
    })


def beden_payi(stoklu: pd.DataFrame, esik: int = BEDEN_ESIGI) -> pd.DataFrame:
    """`magaza_id, option_id, urun_id, pay`; zincir payı `magaza_id = "*"`."""
    df = yalniz_stoklu(stoklu)
    if len(df) == 0:
        return _bos_beden()
    m, magazalar = kodlar(df["magaza_id"])
    u, urunler = kodlar(df["urun_id"])
    o, opsiyonlar = kodlar(df["option_id"])
    return _beden_tablosu(m, u, o, df["brut_satis"].to_numpy(np.float64), magazalar, urunler,
                          opsiyonlar, esik)


# ----------------------------------------------------------------- arayüz

def ogren(stoklu: pd.DataFrame) -> Carpanlar:
    """Stoklu hücre-günlerden (`ozellikler.ekle` biçimi) bütün çarpanlar.

    `durum` sütunu varsa yalnız `stoklu` satırlar kullanılır. Tarih süzülmez:
    çağıran yalnız 2023–2024'ü verir. Bellek: satır başına dar türler (int8–32,
    float32, girdi sütunlarının kopyasız görünümleri); ara diziler iş bitince
    bırakılır."""
    df = yalniz_stoklu(stoklu)
    gun = gun_sayisi(df["tarih"])
    hg = df["hafta_gunu"].to_numpy().astype(np.int8)
    pazartesi = gun - hg
    s = df["brut_satis"].to_numpy().astype(np.float32)
    kanal, kanallar = kodlar(df["kanal"])
    nkanal = len(kanallar)
    bayrak = ozel_turleri(df)
    kamp = df["kampanya_orani"].to_numpy()
    md = df["markdown_orani"].to_numpy()

    # 1. hafta günü
    normal = (kamp <= 0) & (kanal >= 0)
    for b in bayrak.values():
        normal &= ~b
    hf_tablo = _hafta_gunu(kanal[normal], pazartesi[normal], hg[normal], s[normal], nkanal)
    del normal
    hafta_gunu = {(str(kanallar[i]), g): float(hf_tablo[i, g])
                  for i in range(nkanal) for g in range(7)}
    hf = np.vstack([hf_tablo, np.ones((1, 7))]).astype(np.float32)[
        np.where(kanal >= 0, kanal, nkanal), hg]

    # 2. kampanya esnekliği (fark-içinde-fark)
    m, magazalar = kodlar(df["magaza_id"])
    u, urunler = kodlar(df["urun_id"])
    hucre = m.astype(np.int64) * len(urunler) + u
    if len(hucre) and hucre.max() < 2**31:
        hucre = hucre.astype(np.int32)
    ust, ustler = kodlar(df["ust_kategori"])
    line, lines = kodlar(df["line"])
    # katman = kanal × üst kategori × line (kodlar +1: boş değer 0)
    nu1, nl1 = len(ustler) + 1, len(lines) + 1
    katman_kod, katman = np.unique(((kanal.astype(np.int64) + 1) * nu1 + ust + 1) * nl1 + line + 1,
                                   return_inverse=True)
    katman = katman.astype(np.int32)
    katman_ust = (katman_kod // nl1) % nu1 - 1
    kid, _ = kodlar(df["kampanya_id"])
    eps_k = _esneklik_kampanya(gun, hucre, m, katman, katman_ust, s / hf, kamp, kid, md, ustler)
    del katman, kid
    eps = _sozlukten(ust, ustler, eps_k, eps_k.get("*", _ESNEKLIK_VARSAYILAN)).astype(np.float32)
    fiyat = _fiyat_carpani(df["oran"].to_numpy(), eps).astype(np.float32)
    del eps

    # 3. özel gün
    o, opsiyonlar = kodlar(df["option_id"])
    ok = (o >= 0) & (kanal >= 0)
    ozel_gun = _ozel_gun(o[ok], kanal[ok], nkanal, gun[ok], (s / fiyat)[ok],
                         {ad: v[ok] for ad, v in bayrak.items()}, (kamp > 0)[ok])
    del ok
    oz = np.ones(len(df), dtype=np.float32)
    for ad, f in ozel_gun.items():
        oz[bayrak[ad]] *= np.float32(f)
    del bayrak
    hf *= oz          # artık hafta günü × özel gün
    del oz

    # 4. markdown esnekliği (yalnız rapor)
    eps_m = _esneklik_markdown(hucre, pazartesi, s / hf, md, kamp, kanal, ust, ustler)
    del hucre, pazartesi

    # 5. yaşam
    alt, altlar = kodlar(df["alt_kategori"])
    hf *= fiyat       # artık bütün karakter (yaşam hariç)
    del fiyat
    yasam = _yasam(line, lines, alt, altlar, df["yas_gun"].to_numpy(), s / hf)
    del hf, alt, line

    # 6. beden payı
    bp = _beden_tablosu(m, u, o, s, magazalar, urunler, opsiyonlar, BEDEN_ESIGI)
    return Carpanlar(hafta_gunu=hafta_gunu, ozel_gun=ozel_gun, esneklik_kampanya=eps_k,
                     esneklik_markdown=eps_m, yasam=yasam, beden_payi=bp)


def karakter(df: pd.DataFrame, c: Carpanlar) -> pd.Series:
    """Hafta günü × özel gün × (1 − oran)^(−ε̂_kampanya) × yaşam (devamlıda 1).

    Okunan sütunlar: kanal, hafta_gunu, tatil, black_friday, indirim_baslangici,
    oran, ust_kategori, line, alt_kategori, yas_gun. float64, `df`nin indeksiyle."""
    n = len(df)
    if n == 0:
        return pd.Series(np.ones(0), index=df.index, name="karakter")
    kanal, kanallar = kodlar(df["kanal"])
    tablo = np.array([[float(c.hafta_gunu.get((str(k), g), 1.0)) for g in range(7)]
                      for k in kanallar] + [[1.0] * 7])
    hg = df["hafta_gunu"].to_numpy().astype(np.int64)
    k = tablo[np.where(kanal >= 0, kanal, len(kanallar)), hg]
    for ad, bayrak in ozel_turleri(df).items():
        f = float(c.ozel_gun.get(ad, 1.0))
        if f != 1.0:
            k = np.where(bayrak, k * f, k)
    ust, ustler = kodlar(df["ust_kategori"])
    eps = _sozlukten(ust, ustler, c.esneklik_kampanya,
                     c.esneklik_kampanya.get("*", _ESNEKLIK_VARSAYILAN))
    k = k * _fiyat_carpani(df["oran"].to_numpy(np.float64), eps)
    k = k * _yasam_carpani(df, c.yasam)
    return pd.Series(k, index=df.index, name="karakter")
