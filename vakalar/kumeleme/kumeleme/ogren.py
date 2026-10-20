"""Makine öğrenmesi kümeleri: k-means ve Ward, hakemsiz k seçimi, kararlılık, yorum, öneri.

Kural: bu bir karar modülüdür; yalnız `ozellikler`'in yayımlanan veriden kurduğu mağaza
özelliklerini okur. Gizli gerçeğe (`perakende_veri`, gizli mağaza tablosu) ve ölçüm modüllerine
(hakem, ölçütler) dokunmaz (AST kilidi, `tests/test_sizinti.py`). k, yöntem, aile ve önerilen küme
hakemsiz seçilir (spec §0/5, §4.2): gizli segment hiçbir adımda girdi değildir; hakem yalnız
sonradan ölçer.

**Kümeler** (`kume`). Girdi standartlanmış özellik tablosudur (`ozellikler.standartla`; satır
`magaza_id`). Kümeleme, satırlar ve sütunlar ada göre sıralanmış tabloda yapılır: sonuç girdinin
satır ve sütun sırasından bağımsızdır.

    kmeans  `KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=tohum)` (k-means++, Lloyd),
            tek iş parçacığıyla (`threadpool_limits(1)`: 67 mağazada ~3 kat hızlı, etiketler aynı)
    ward    `AgglomerativeClustering(n_clusters=k, linkage="ward")` (Öklid; tohum kullanılmaz)

**Kanonik etiket** (`kanonik`). Küme numarası 0..k−1, kümelerin en küçük `magaza_id`'lerinin
sırasıyla: küme 0 en küçük kimlikli mağazayı taşır. Aynı bölmeyi veren iki etiketleme kanonik
olarak birebir aynıdır. **Bölme kimliği** (`bolme_kimligi`): kümelerin sıralı mağaza listelerinin
sıralı listesinin SHA-256 özeti; etiket adlarından, numaralarından ve satır sırasından bağımsızdır.

**Siluet** (`siluet`): sklearn `silhouette_score`, Öklid, standartlanmış tabloda. **Dirsek**: k
tablosunun `w` sütunu (küme içi kareler toplamı); raporda basılır, kurala girmez (aşağıda).

**k seçimi** (`k_sec`, kural `k_kurali`). `K_ARALIK`'taki her k için küme kurulur (n − 1'den büyük
k denenmez: siluet tanımsız). Kural:

    1. en küçük kümesi `EN_KUCUK_KUME` (3) mağazadan az olan k elenir (iş kısıtı: üç mağazadan
       küçük bir plan grubu kurulmaz);
    2. kalanlarda siluet en yüksek olan s*;
    3. siluet s* − `SILUET_ESITLIK` (0,01) ya da üstündeki k'lardan **en küçüğü** seçilir
       (siluetteki 0,01'lik fark ayırt edici sayılmaz; az grup planlamada daha kullanışlıdır).

    Uygun k yoksa seçim `None`'dır. Dirsek (küme içi kareler) kurala girmez: k-means/Ward'da
    k ile tekdüze düşer ve dirseğin yeri bir eşiğe bağlıdır (ikinci bir serbest parametre);
    raporda siluetin yanında basılır.

**Kararlılık** (`kararlilik`). Hakemsiz bir ikinci ölçüt: aynı yöntem ve k ile bütün mağazaların
kümesi bir kez kurulur; sonra `KARARLILIK_ORNEK` (50) kez mağazaların `KARARLILIK_ORAN`'ı (%80,
yarım yukarı) iadesiz çekilip yalnız onlarla yeniden kümelenir; her çekilişte iki bölmenin çekilen
mağazalardaki ARI'si (`adjusted_rand_score`) hesaplanır, ortalaması kararlılıktır (1: bölme
alt örneklemeden etkilenmez). Özellikler yeniden kurulmaz ve yeniden standartlanmaz (Ruling R6):
çekiliş yalnız kümeleme adımında mağaza dışarıda bırakır. Çekilişler `default_rng(tohum)`'la.

**Öneri** (`oneri`). Yazıların ana "ML kümesi": aileler {S1, S2} × yöntemler {kmeans, ward} ×
`K_ARALIK` içinden, üç adımda ve hakemsiz. Siluet birincil ölçüttür (k kuralıyla aynı), kararlılık
yalnız siluette ayırt edilemeyen adayları ayırır:

    1. her (aile, yöntem) için k, `k_sec` kuralıyla: en çok dört **aday** (tabloda `secilen`);
       her adayın kararlılığı hesaplanır ve basılır (`kararlilik`);
    2. adaylardan siluet en yüksek olan s*; siluet s* − `SILUET_ESITLIK` ya da üstündekiler
       **siluette eşit** sayılır (tabloda `esit`);
    3. eşitlerden kararlılığı en yüksek olan; kararlılık farkı ≤ `KARARLILIK_ESITLIK` (0,02)
       ise küçük k, o da eşitse aile sırası (S1, S2), o da eşitse yöntem sırası (kmeans, ward).

    Siluet aileler arasında da karşılaştırılır. Gerekçe: iki aile aynı standartlamayla (her blok
    toplam varyans 1) kurulur ve siluet boyuttan değil bölmenin ayrıklığından konuşur; SS25'te
    sütunları bağımsız karıştırılmış boş veride (`bos_siluet`: yapısız, aynı marjinaller) siluet
    S1'de ve S2'de aynı düzeydedir (adaylarda 0,05 dolayı; raporda basılır). Kararlılık birincil ölçüt yapılmaz: küçük k'yı ve tek bir
    güçlü eksende ikiye bölünmeyi kayırır (bölme alt örneklemede bozulmaz ama yapının asıl
    ekseni olmayabilir); 50 çekilişli ortalamanın oynaklığı ~0,01 düzeyindedir (eşitlik payı bu
    yüzden 0,02).

Özellikler bir kez, kapsamın kümelenen (`kumelenir`) mağazalarıyla kurulur; yeni mağazalar
kümelenmez (sonradan `yeni_magaza` atar). `oneri` bütün aday tablosunu `Oneri.tablo`'da döndürür.

**Yorum** (`yorum`). Her kümenin en ayırt edici `n` özelliği: verilen tablonun sütunları
etiketlenen mağazalar üstünde z-skora çevrilir (popülasyon sapması; sabit sütun düşer), kümenin
ortalama z'si |z| büyükten küçüğe (eşitlikte sütun adı) sıralanır. Z-skor yeniden alındığı için
ham ya da standartlanmış (ağırlıklı) tabloda aynı sonucu verir.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from threadpoolctl import threadpool_limits

from kumeleme import ozellikler, sabitler

YONTEMLER = ("kmeans", "ward")
ONERI_AILELERI = ("S1", "S2")
SILUET_ESITLIK = 0.01
KARARLILIK_ORNEK = 50
KARARLILIK_ORAN = 0.80
KARARLILIK_ESITLIK = 0.02
BOS_ORNEK = 10
_EPS = 1e-12

Yontem = Literal["kmeans", "ward"]


# ---------------------------------------------------------------------------
# Kümeler, kanonik etiket, kimlik
# ---------------------------------------------------------------------------


def _sirali(X: pd.DataFrame) -> pd.DataFrame:
    if X.index.has_duplicates or X.columns.has_duplicates:
        raise ValueError("satır ya da sütun adı tekrarlı")
    if X.isna().to_numpy().any():
        raise ValueError("özellik tablosunda NaN var")
    Y = X.sort_index(axis=0).sort_index(axis=1).astype("float64")
    Y.index = Y.index.astype(str)
    Y.index.name = "magaza_id"
    return Y


def kanonik(etiket: pd.Series) -> pd.Series:
    """Etiketleri 0..k−1'e çevirir: kümeler en küçük `magaza_id`'lerinin sırasıyla."""
    if etiket.index.has_duplicates:
        raise ValueError("mağaza kimliği tekrarlı")
    if etiket.isna().any():
        raise ValueError("etikette NaN var")
    ids = etiket.index.astype(str)
    ilk = pd.Series(ids, index=ids).groupby(etiket.to_numpy()).min().sort_values()
    sira = {lab: i for i, lab in enumerate(ilk.index)}
    return pd.Series([sira[v] for v in etiket.to_numpy()], index=pd.Index(ids, name="magaza_id"),
                     dtype="int64", name="kume")


def kume(X_std: pd.DataFrame, yontem: Yontem, k: int, tohum: int = sabitler.TOHUM) -> pd.Series:
    """Mağaza → kanonik küme numarası (0..k−1), `X_std` satır sırasıyla."""
    X = _sirali(X_std)
    if not 1 <= k <= len(X):
        raise ValueError(f"k = {k}, mağaza sayısı {len(X)}")
    if yontem == "kmeans":
        model = KMeans(n_clusters=k, n_init=sabitler.KMEANS_N_INIT, random_state=tohum)
    elif yontem == "ward":
        model = AgglomerativeClustering(n_clusters=k, linkage="ward")
    else:
        raise ValueError(f"bilinmeyen yöntem: {yontem!r} {YONTEMLER}")
    with threadpool_limits(limits=1):     # küçük tabloda hızlı; iş parçacığı sayısından bağımsız
        etiket = kanonik(pd.Series(model.fit(X.to_numpy()).labels_, index=X.index))
    return etiket.reindex(pd.Index(X_std.index.astype(str), name="magaza_id"))


def bolme_kimligi(etiket: pd.Series) -> str:
    """Bölmenin SHA-256 özeti (hex): etiket adlarından ve satır sırasından bağımsız."""
    if etiket.index.has_duplicates:
        raise ValueError("mağaza kimliği tekrarlı")
    if etiket.isna().any():
        raise ValueError("etikette NaN var")
    ids = pd.Series(etiket.index.astype(str), index=etiket.index)
    gruplar = sorted(sorted(g) for _, g in ids.groupby(etiket.to_numpy()))
    return hashlib.sha256(json.dumps(gruplar, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Siluet, k seçimi, kararlılık
# ---------------------------------------------------------------------------


def _hizala(X: pd.DataFrame, etiket: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    ids = etiket.index.astype(str)
    Y = X.copy()
    Y.index = Y.index.astype(str)
    return Y.loc[ids].to_numpy(dtype="float64"), etiket.to_numpy()


def siluet(X: pd.DataFrame, etiket: pd.Series) -> float:
    """Ortalama siluet (Öklid); `X` satırları etiketin mağazalarına hizalanır."""
    A, e = _hizala(X, etiket)
    return float(silhouette_score(A, e, metric="euclidean"))


def _ic_kare(X: pd.DataFrame, etiket: pd.Series) -> float:
    A, e = _hizala(X, etiket)
    return float(sum(((A[e == g] - A[e == g].mean(axis=0)) ** 2).sum() for g in np.unique(e)))


def k_kurali(tablo: pd.DataFrame, en_kucuk: int = sabitler.EN_KUCUK_KUME) -> int | None:
    """k seçim kuralı (modül notu): `k`, `siluet`, `en_kucuk` sütunlu tablodan seçilen k ya da None."""
    u = tablo.loc[tablo["en_kucuk"] >= en_kucuk]
    if u.empty:
        return None
    esik = u["siluet"].max() - SILUET_ESITLIK - _EPS
    return int(u.loc[u["siluet"] >= esik, "k"].min())


_K_SUTUNLARI = ["k", "siluet", "w", "en_kucuk", "boyutlar", "uygun", "secilen", "kimlik"]


def k_sec(X_std: pd.DataFrame, yontem: Yontem, *, k_aralik=sabitler.K_ARALIK,
          en_kucuk: int = sabitler.EN_KUCUK_KUME, tohum: int = sabitler.TOHUM
          ) -> tuple[int | None, pd.DataFrame]:
    """Hakemsiz k (modül notu, `k_kurali`) ve k tablosu.

    Tablo sütunları: `k`, `siluet`, `w` (küme içi kareler; dirsek), `en_kucuk` (en küçük kümenin
    mağaza sayısı), `boyutlar` (küme büyüklükleri, büyükten küçüğe), `uygun` (en küçük ≥
    `en_kucuk`), `secilen`, `kimlik` (`bolme_kimligi`). Uygun k yoksa seçim None."""
    n = len(X_std)
    satir = []
    for k in k_aralik:
        if not 2 <= k <= n - 1:
            continue
        e = kume(X_std, yontem, k, tohum=tohum)
        boy = e.value_counts()
        satir.append({"k": int(k), "siluet": siluet(X_std, e), "w": _ic_kare(X_std, e),
                      "en_kucuk": int(boy.min()), "boyutlar": tuple(sorted(boy.tolist(), reverse=True)),
                      "kimlik": bolme_kimligi(e)})
    tablo = pd.DataFrame(satir, columns=[c for c in _K_SUTUNLARI if c not in ("uygun", "secilen")])
    tablo["uygun"] = tablo["en_kucuk"] >= en_kucuk
    secilen = k_kurali(tablo, en_kucuk) if len(tablo) else None
    tablo["secilen"] = tablo["k"] == secilen
    return secilen, tablo[_K_SUTUNLARI]


def kararlilik(X_std: pd.DataFrame, yontem: Yontem, k: int, *, ornek: int = KARARLILIK_ORNEK,
               oran: float = KARARLILIK_ORAN, tohum: int = sabitler.TOHUM) -> float:
    """Alt örneklemede kararlılık: tam bölme ile %`oran` alt örneklem bölmesinin ortalama ARI'si."""
    X = _sirali(X_std)
    n = len(X)
    m = int(np.floor(oran * n + 0.5))
    if not k < m <= n:
        raise ValueError(f"alt örneklem {m} mağaza, k = {k}, n = {n}")
    tam = kume(X, yontem, k, tohum=tohum).to_numpy()
    rng = np.random.default_rng(tohum)
    ari = []
    for _ in range(ornek):
        sec = np.sort(rng.choice(n, size=m, replace=False))
        alt = kume(X.iloc[sec], yontem, k, tohum=tohum).to_numpy()
        ari.append(adjusted_rand_score(tam[sec], alt))
    return float(np.mean(ari))


def bos_siluet(X: pd.DataFrame, aile: str, yontem: Yontem, k: int, *, ornek: int = BOS_ORNEK,
               tohum: int = sabitler.TOHUM) -> float:
    """Yapısız karşılaştırma: ham özellik tablosunun her sütunu mağazalar arasında bağımsız
    karıştırılır (marjinaller aynı, ortak yapı yok), `standartla(…, aile)` ile standartlanır, aynı
    yöntem ve k ile kümelenir; `ornek` karıştırmanın ortalama siluetidir. Aileler arasında siluetin
    karşılaştırılabilirliğinin hakemsiz denetimi (modül notu, Öneri)."""
    rng = np.random.default_rng(tohum)
    X = X.sort_index(axis=0).sort_index(axis=1)
    s = []
    for _ in range(ornek):
        N = pd.DataFrame({c: rng.permutation(X[c].to_numpy()) for c in X.columns}, index=X.index)
        Z = ozellikler.standartla(N, aile)
        s.append(siluet(Z, kume(Z, yontem, k, tohum=tohum)))
    return float(np.mean(s))


# ---------------------------------------------------------------------------
# Yorum
# ---------------------------------------------------------------------------


def _ad(v):
    return v.item() if isinstance(v, np.generic) else v


def yorum(X: pd.DataFrame, etiket: pd.Series, n: int = 3) -> dict:
    """Küme → [(özellik, ortalama z), …]: kümenin en ayırt edici `n` özelliği (modül notu)."""
    A = X.copy()
    A.index = A.index.astype(str)
    A = A.loc[etiket.index.astype(str)].astype("float64")
    sd = A.std(axis=0, ddof=0)
    A = A.loc[:, sd > _EPS]
    Z = (A - A.mean(axis=0)) / sd[A.columns]
    ort = Z.groupby(etiket.to_numpy()).mean()
    sonuc = {}
    for g in sorted(ort.index):
        r = ort.loc[g]
        sira = sorted(r.index, key=lambda c: (-round(abs(float(r[c])), 12), str(c)))[:n]
        sonuc[_ad(g)] = [(str(c), float(r[c])) for c in sira]
    return sonuc


# ---------------------------------------------------------------------------
# Öneri
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Oneri:
    """Önerilen tek ML kümesi ve bütün aday tablosu.

    tablo   aile × yöntem × k satırları: `k_sec` sütunları (`secilen`: o aile ve yöntemin adayı),
            ayrıca `aile`, `yontem`, `kararlilik` (yalnız adaylarda; diğerleri NaN), `esit`
            (siluette en iyiye eşit aday), `oneri`."""
    aile: str
    yontem: str
    k: int
    etiket: pd.Series
    kimlik: str
    tablo: pd.DataFrame


def oneri_kurali(adaylar: pd.DataFrame) -> tuple[int, pd.Series]:
    """Öneri kuralının 2. ve 3. adımı (modül notu): `aile`, `yontem`, `k`, `siluet`, `kararlilik`
    sütunlu aday tablosundan seçilen satırın konumu ve siluette eşit adayların maskesi."""
    a = adaylar.reset_index(drop=True)
    esit = a["siluet"] >= a["siluet"].max() - SILUET_ESITLIK - _EPS
    e = a.loc[esit]
    e = e.loc[e["kararlilik"] >= e["kararlilik"].max() - KARARLILIK_ESITLIK - _EPS]
    sira = sorted(e.index, key=lambda i: (int(e.at[i, "k"]), ONERI_AILELERI.index(e.at[i, "aile"]),
                                          YONTEMLER.index(e.at[i, "yontem"])))
    return int(sira[0]), esit


_ONERI_SUTUNLARI = ["aile", "yontem", "k", "siluet", "w", "en_kucuk", "boyutlar", "uygun", "secilen",
                    "kararlilik", "esit", "oneri", "kimlik"]


def oneri(tablolar, kapsam: pd.DataFrame, urunler: pd.DataFrame | None, karar_gunu, *,
          ozellik: Mapping[str, pd.DataFrame] | None = None, k_aralik=sabitler.K_ARALIK,
          en_kucuk: int = sabitler.EN_KUCUK_KUME, ornek: int = KARARLILIK_ORNEK,
          tohum: int = sabitler.TOHUM) -> Oneri:
    """Önerilen ML kümesi (modül notu, üç adım), kapsamın kümelenen mağazalarında.

    tablolar    `ozellikler.ozellik_tablosu`'nun girdisi (bağlantı ya da DataFrame'ler)
    ozellik     verilirse aile → ham özellik tablosu (S1, S2; satırlar kümelenen mağazalar);
                o zaman `tablolar` ve `urunler` okunmaz."""
    ids = sorted(kapsam.loc[kapsam["kumelenir"].astype(bool), "magaza_id"].astype(str))
    parca, aday = [], []
    for aile in ONERI_AILELERI:
        if ozellik is not None:
            X = ozellik[aile]
            if sorted(X.index.astype(str)) != ids:
                raise ValueError(f"{aile}: özellik tablosunun mağazaları kapsamın kümelenenleri değil")
        else:
            X = ozellikler.ozellik_tablosu(tablolar, ids, urunler, karar_gunu, aile)
        Z = ozellikler.standartla(X, aile)
        for yontem in YONTEMLER:
            k, t = k_sec(Z, yontem, k_aralik=k_aralik, en_kucuk=en_kucuk, tohum=tohum)
            parca.append(t.assign(aile=aile, yontem=yontem))
            if k is not None:
                aday.append({"aile": aile, "yontem": yontem, "k": k, "Z": Z,
                             "siluet": float(t.loc[t["secilen"], "siluet"].iloc[0]),
                             "kararlilik": kararlilik(Z, yontem, k, ornek=ornek, tohum=tohum)})
    if not aday:
        raise ValueError("hiçbir aile ve yöntemde en küçük küme sınırını sağlayan k yok")
    secim, esit = oneri_kurali(pd.DataFrame([{c: a[c] for c in ("aile", "yontem", "k", "siluet",
                                                                 "kararlilik")} for a in aday]))
    o = aday[secim]

    tablo = pd.concat(parca, ignore_index=True)
    tablo["kararlilik"] = np.nan
    tablo["esit"] = False
    for i, a in enumerate(aday):
        sat = (tablo["aile"] == a["aile"]) & (tablo["yontem"] == a["yontem"]) & (tablo["k"] == a["k"])
        tablo.loc[sat, "kararlilik"] = a["kararlilik"]
        tablo.loc[sat, "esit"] = bool(esit[i])
    tablo["oneri"] = ((tablo["aile"] == o["aile"]) & (tablo["yontem"] == o["yontem"])
                      & (tablo["k"] == o["k"]))
    etiket = kume(o["Z"], o["yontem"], o["k"], tohum=tohum).sort_index()
    return Oneri(aile=o["aile"], yontem=o["yontem"], k=int(o["k"]), etiket=etiket,
                 kimlik=bolme_kimligi(etiket), tablo=tablo[_ONERI_SUTUNLARI])
