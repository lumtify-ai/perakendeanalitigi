"""Yeni mağaza ataması: satış görmeden, yalnız statik gözlemlenebilirlerle küme.

Kural: bu bir karar modülüdür; yalnız `kaynak.kapsam`'ın yayımlanan mağaza tablosundan gelen
statik sütunlarını ve verilen küme etiketlerini okur. Gizli gerçeğe (`perakende_veri`, gizli
mağaza tablosu) ve ölçüm modüllerine (hakem, ölçütler) dokunmaz (AST kilidi,
`tests/test_sizinti.py`). Atamanın gizli segmente karşı doğruluğu `olcutler`'de ölçülür.

**Statik özellikler** (`statik_tablo`, `STATIKLER`): bölge, metropol bayrağı, iklim sınıfı (şehirden,
`kaynak.SEHIR_IKLIM`; tabloda olmayan şehir hata verir), tip (AVM, Cadde), log m², enlem. Hepsi
mağaza açılmadan bilinir. Satış, ciro, kapasite ve turistik bayrağı girmez.

**Kodlama** (`_kodla`). Her statik bir bloktur ve bloklar eşit ağırlık alır (her bloğun
kümelenmiş mağazalardaki toplam varyansı 1; `ozellikler.standartla` ile aynı ilke): sayısal sütun
z-skordur; kategorik sütun bire-sıcak kodlanır, merkezlenir ve bloğun toplam varyansının
kareköküne bölünür. İstatistikler (ortalama, sapma, kategoriler) yalnız **kümelenmiş** mağazalardan
alınır, yeni mağazaya aynen uygulanır; kümelenmişlerde görülmemiş kategori bütün sütunlarda 0
(merkezlenmeden önce) kodlanır. Kümelenmişlerde sabit olan blok düşer.

**Atama** (`ata`, `YONTEMLER`):

    knn     en yakın `komsu` (5) kümelenmiş mağazanın çoğunluk kümesi; eşitlikte, eşit oylu
            kümelerden en yakın komşunun kümesi. Komşu sırası uzaklık, eşitlikte `magaza_id`.
            Varsayılan.
    merkez  en yakın küme merkezi: her kümenin kümelenmiş mağazalarının kodlanmış statiklerinin
            ortalaması; Öklid uzaklığı en küçük olan küme (eşitlikte küçük etiket). Karşılaştırma.

    Varsayılanın gerekçesi (hakemsiz ölçüt: bırakbirde mağazanın kendi satış kümesine isabet):
    satış kümeleri statik uzayda dışbükey değildir (SS25'te en büyük küme Anadolu'nun metropol
    dışı mağazalarıyla İstanbul'un bir kısmını birlikte taşır), merkez bu kümeyi ortalamaya çeker;
    komşu yereldir. SS25'te `komsu` = 5 (sonuç görülmeden yazıldı) ile isabet 0,82, merkezle
    0,70. Seçim sonuç görüldükten sonra yapıldı; iki seçenekten biri olduğu için iyimserlik payı
    küçüktür, rapor ikisini de basar.

**Bırakbir ölçümü** (`birakbir`, spec §0/11). Kümelenen her mağaza "yeniymiş gibi": kümeler o
mağaza hariç, aynı özellik tablosundan (`Z`, bir kez kurulur; Ruling R6) aynı kümeleme işleviyle
yeniden kurulur ve mağaza yalnız statikleriyle o kümelere atanır. Mağazanın ne özellik satırı ne
statikleri ne etiketi kendi atamasına girer. Bırakbir kümelerinin etiketleri tam kümelerin
etiket uzayına çevrilir (`_tam_etikete`): bırakbir kümeleri tam kümelerle ortak üye sayısını en
çoklayan birebir eşlemeyle (Macar yöntemi; `olcutler.kararlilik`'in önyüklemesiyle aynı) eşlenir.
Birebirdir: iki bırakbir kümesi aynı tam kümeye çevrilmez (çoğunluk çevirisi bölünen bir kümenin
iki parçasını aynı etikete toplardı). `ayni_bolme`: bırakbir bölmesi tam
bölmenin o mağaza çıkarılmış hâliyle aynı mı (`ogren.bolme_kimligi`).
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from kumeleme import kaynak, ogren

STATIKLER = ("bolge", "metropol", "iklim", "tip", "log_m2", "enlem")
KATEGORIK = ("bolge", "metropol", "iklim", "tip")
SAYISAL = ("log_m2", "enlem")
YONTEMLER = ("knn", "merkez")
KOMSU = 5
_EPS = 1e-12


def statik_tablo(magazalar: pd.DataFrame) -> pd.DataFrame:
    """`magaza_id` dizinli statik özellik tablosu (`STATIKLER` sütunları), girdi satır sırasıyla.

    Girdi: `kaynak.kapsam` satırları (`magaza_id, sehir, bolge, tip, metrekare, enlem, metropol`)."""
    m = magazalar.reset_index(drop=True)
    sehir = m["sehir"].astype(str)
    bilinmeyen = sorted(set(sehir) - set(kaynak.SEHIR_IKLIM))
    if bilinmeyen:
        raise KeyError(f"şehir → iklim tablosunda yok: {bilinmeyen}")
    if (pd.to_numeric(m["metrekare"]) <= 0).any():
        raise ValueError("metrekare pozitif olmalı")
    S = pd.DataFrame({
        "bolge": m["bolge"].astype(str).to_numpy(),
        "metropol": m["metropol"].astype(bool).to_numpy(),
        "iklim": sehir.map(kaynak.SEHIR_IKLIM).to_numpy(),
        "tip": m["tip"].astype(str).to_numpy(),
        "log_m2": np.log(pd.to_numeric(m["metrekare"]).to_numpy(dtype="float64")),
        "enlem": pd.to_numeric(m["enlem"]).to_numpy(dtype="float64"),
    }, index=pd.Index(m["magaza_id"].astype(str).to_numpy(), name="magaza_id"))
    if S.index.has_duplicates:
        raise ValueError("mağaza kimliği tekrarlı")
    return S


def _kodla(ref: pd.DataFrame, S: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Kümelenmiş (`ref`) ve atanacak (`S`) mağazaların kodlanmış statikleri (modül notu)."""
    A, B = [], []
    for s in STATIKLER:
        if s in SAYISAL:
            mu, sd = ref[s].mean(), ref[s].std(ddof=0)
            if sd <= _EPS:
                continue
            A.append(((ref[s] - mu) / sd).to_numpy()[:, None])
            B.append(((S[s] - mu) / sd).to_numpy()[:, None])
        else:
            kat = sorted(ref[s].astype(str).unique())
            if len(kat) < 2:
                continue
            Ra = np.column_stack([(ref[s].astype(str) == c).to_numpy(dtype="float64") for c in kat])
            Sa = np.column_stack([(S[s].astype(str) == c).to_numpy(dtype="float64") for c in kat])
            mu = Ra.mean(axis=0)
            olcek = np.sqrt(Ra.var(axis=0).sum())
            A.append((Ra - mu) / olcek)
            B.append((Sa - mu) / olcek)
    if not A:
        raise ValueError("kümelenmiş mağazalarda değişen statik özellik yok")
    return np.hstack(A), np.hstack(B)


def ata(statik_yeni: pd.DataFrame, statik_kumelenmis: pd.DataFrame, etiket: pd.Series, *,
        yontem: str = "knn", komsu: int = KOMSU) -> pd.Series:
    """Yeni mağaza → küme etiketi (`etiket`in değerlerinden), `statik_yeni` satır sırasıyla.

    statik_yeni, statik_kumelenmis   `kaynak.kapsam` satırları (statikler `statik_tablo`'yla
                                     türetilir; başka sütunlar okunmaz)
    etiket                           kümelenmiş mağaza → küme (`magaza_id` dizinli); kümelenmiş
                                     tablonun bütün mağazalarını kapsamalı"""
    if yontem not in YONTEMLER:
        raise ValueError(f"bilinmeyen yöntem: {yontem!r} {YONTEMLER}")
    yeni = statik_tablo(statik_yeni)
    ref = statik_tablo(statik_kumelenmis).sort_index()
    if set(yeni.index) & set(ref.index):
        raise ValueError(f"atanacak mağaza kümelenmişler arasında: {sorted(set(yeni.index) & set(ref.index))}")
    e = etiket.copy()
    e.index = e.index.astype(str)
    eksik = sorted(set(ref.index) - set(e.index))
    if eksik:
        raise ValueError(f"etiketi olmayan kümelenmiş mağaza: {eksik}")
    e = e.loc[ref.index].to_numpy()
    A, B = _kodla(ref, yeni)

    kumeler = np.array(sorted(pd.unique(e)))
    if yontem == "merkez":
        merkez = np.vstack([A[e == g].mean(axis=0) for g in kumeler])
        d = ((B[:, None, :] - merkez[None, :, :]) ** 2).sum(axis=2)
        sonuc = [kumeler[int(np.argmin(np.round(r, 12)))] for r in d]       # eşitlikte küçük etiket
    else:
        d = ((B[:, None, :] - A[None, :, :]) ** 2).sum(axis=2)
        sonuc = []
        for r in d:
            sira = np.lexsort((ref.index.to_numpy(), np.round(r, 12)))[:komsu]
            oy = pd.Series(e[sira]).value_counts()
            enler = set(oy.index[oy == oy.max()])
            sonuc.append(next(e[j] for j in sira if e[j] in enler))
    return pd.Series(sonuc, index=yeni.index, name="kume")


def _tam_etikete(e: pd.Series, tam: pd.Series) -> dict:
    """Bırakbir etiketi → tam bölme etiketi (modül notu): ortak üye sayısını en çoklayan birebir
    eşleme (Macar); sütunlar tam bölmenin bütün kümeleri (dışarıdaki mağazanın tek başına kümesi
    dahil). Eşlenemeyen bırakbir kümesi (tam bölmeden çok küme) üyelerinin çoğunluğunu alır."""
    e_ad = np.array(sorted(pd.unique(e.to_numpy())))
    t_ad = np.array(sorted(pd.unique(tam.to_numpy())))
    ortak = (pd.crosstab(e.to_numpy(), tam.loc[e.index].to_numpy())
             .reindex(index=e_ad, columns=t_ad, fill_value=0).to_numpy())
    sat, sut = linear_sum_assignment(-ortak)
    harita = {e_ad[i]: t_ad[j] for i, j in zip(sat, sut)}
    for i, g in enumerate(e_ad):
        if g not in harita:
            harita[g] = t_ad[int(np.argmax(ortak[i]))]
    return harita


def birakbir(statik: pd.DataFrame, Z: pd.DataFrame, fn_kume: Callable[[pd.DataFrame], pd.Series], *,
             yontem: str = "knn", komsu: int = KOMSU) -> pd.DataFrame:
    """Kümelenen her mağaza için bırakbir ataması (modül notu), `magaza_id` sırasıyla.

    statik      kümelenen mağazaların `kaynak.kapsam` satırları
    Z           aynı mağazaların standartlanmış özellik tablosu (bir kez kurulur; Ruling R6)
    fn_kume     özellik tablosu → küme etiketi (örn. `partial(ogren.kume, yontem="ward", k=5)`)

    Sütunlar: `magaza_id`, `gercek_kume` (tam bölmede, kendi satışıyla), `atanan` (bırakbir
    ataması, tam bölmenin etiket uzayında), `metropol`, `ayni_bolme`."""
    Z = Z.copy()
    Z.index = Z.index.astype(str)
    st = statik.assign(magaza_id=statik["magaza_id"].astype(str)).set_index("magaza_id", drop=False)
    ids = sorted(Z.index)
    if sorted(st.index) != ids:
        raise ValueError("statik tablonun mağazaları özellik tablosununkiler değil")
    tam = fn_kume(Z).copy()
    tam.index = tam.index.astype(str)
    satir = []
    for m in ids:
        digerleri = [i for i in ids if i != m]
        e = fn_kume(Z.loc[digerleri]).copy()
        e.index = e.index.astype(str)
        harita = _tam_etikete(e, tam)
        a = ata(st.loc[[m]], st.loc[digerleri], e, yontem=yontem, komsu=komsu).iloc[0]
        satir.append({"magaza_id": m, "gercek_kume": tam[m], "atanan": harita[a],
                      "metropol": bool(st.at[m, "metropol"]),
                      "ayni_bolme": ogren.bolme_kimligi(e) == ogren.bolme_kimligi(tam.loc[digerleri])})
    return pd.DataFrame(satir, columns=["magaza_id", "gercek_kume", "atanan", "metropol", "ayni_bolme"])
