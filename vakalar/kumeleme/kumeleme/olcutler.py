"""Ölçütler: hakemli (ARI, AMI, çapraz tablo, saflık, yeni mağaza doğruluğu) ve hakemsiz kararlılık.

Bu bir **ölçüm** modülüdür (spec §4.3): gizli segment buraya argüman olarak gelir (`hakem.
gizli_segment`), karar modülleri bu modülü içe aktarmaz (AST kilidi, `tests/test_sizinti.py`).
Hakemli ölçütler kümeleri sonradan ölçer, hiçbir seçime girmez.

**Hakemli.** `ari_ami`: sklearn `adjusted_rand_score` ve `adjusted_mutual_info_score` (aritmetik
ortalama), etiketin mağazalarında (gizli tabloda olmayan mağaza hata verir). `capraz`: küme ×
segment mağaza sayıları. `saflik`: segment başına, segmentin en çok düştüğü küme (`kume`), segmentin
o kümedeki payı (`pay`) ve o kümenin bu segmentten olan payı (`kume_payi`); eşitlikte küçük küme.
`toplam_saflik`: her kümenin çoğunluk segmentindeki mağazaların toplam payı (klasik saflık).

**Kararlılık** (`kararlilik`, hakemsiz). İki parça:

    yıllar arası    aynı kümeleme işleviyle (`fn_kume`) her dönemin (`DONEMLER`) yalnız kendi
                    penceresinden kurulan özelliklerle bulunan bölmeler; dönem çiftleri arası ARI.
                    Dönem = (pencere sonu günü, hafta): `ozellikler.pencere` kuralıyla pencere,
                    günün haftasının pazartesisinde biten son `hafta` tamamlanmış hafta. Varsayılan:
                    "2023" = 2024-01-01'de biten 52 hafta (2023-01-02 … 2023-12-31; veri
                    2023-01-01 pazar başlar, o tek gün dışarıda); "2024" = SS25 karar gününde
                    biten 52 hafta (2024-02-05 … 2025-02-02). İki pencere örtüşmez. Karşılaştırma,
                    kümelenen mağazalardan **her** dönemin penceresinde en az `en_az_hafta` (26)
                    satışlı haftası olanlarla yapılır (ötekiler `disarida`; özellikler her dönem
                    bu ortak mağaza kümesiyle kurulur).
    önyükleme       karar günü özellik tablosu (kümelenen mağazalar, `OZELLIK_HAFTA`) bir kez kurulur
                    ve standartlanır (Ruling R6); `ornek` (50) kez mağazalar iadeli çekilir
                    (tekrar eden mağaza aynı satırın kopyasıdır), çekiliş `fn_kume` ile kümelenir,
                    çekiliş bölmesinin kümeleri tam bölmenin kümeleriyle ortak mağaza sayısını en
                    çoklayan birebir eşleşmeyle (Macar yöntemi) eşlenir. Çekilişe giren mağaza,
                    eşlenmiş kümesi tam bölmedeki kümesi değilse **değişmiş** sayılır;
                    `degisme` = değiştiği çekiliş / girdiği çekiliş. `onyukleme_ari`: çekilişe
                    giren (tekil) mağazalarda iki bölmenin ortalama ARI'si. Çekilişler
                    `default_rng(tohum)`'la.

Etiket adları hiçbir ölçüte girmez: aynı bölmenin etiketleri değiştirilmiş hâli ARI 1, değişme 0.

**Yeni mağaza doğruluğu** (`birakbir_dogruluk`). `yeni_magaza.birakbir` tablosuna `gizli`
eklenir. Küme doğruluğu: `atanan == gercek_kume`. Segment doğruluğu: atanan kümenin, mağazanın
kendisi hariç tam bölmedeki üyelerinin çoğunluk segmenti mağazanın gizli segmentiyse doğru
(`atanan_segment`; eşitlikte alfabetik ilk segment). Karşılaştırma için aynı kural mağazanın kendi
satış kümesiyle (`kume_segment`: kümeleme mağazanın satışını görseydi segmenti ne kadar bilirdi)
ve iki taban: herkese en büyük küme (`taban_kume`), herkese en sık segment (`taban_segment`; ikisi
de mağazanın kendisi hariç sayılır). Özet: hepsi, metropol, metropol dışı.
"""

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

from kumeleme import ozellikler, sabitler

DONEMLER: dict[str, tuple[pd.Timestamp, int]] = {
    "2023": (pd.Timestamp("2024-01-01"), 52),
    "2024": (sabitler.KARAR_GUNU, 52),
}
ONYUKLEME_ORNEK = 50


def _ortak(etiket: pd.Series, gercek: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    e = etiket.copy()
    e.index = e.index.astype(str)
    g = gercek.copy()
    g.index = g.index.astype(str)
    if e.index.has_duplicates or g.index.has_duplicates:
        raise ValueError("mağaza kimliği tekrarlı")
    eksik = sorted(set(e.index) - set(g.index))
    if eksik:
        raise KeyError(f"gerçek etikette olmayan mağaza: {eksik}")
    return e.to_numpy(), g.loc[e.index].to_numpy()


def ari_ami(etiket: pd.Series, gercek: pd.Series) -> tuple[float, float]:
    """(ARI, AMI): `etiket`in mağazalarında, `gercek`e (gizli segment) karşı."""
    e, g = _ortak(etiket, gercek)
    return float(adjusted_rand_score(g, e)), float(adjusted_mutual_info_score(g, e))


def capraz(etiket: pd.Series, gercek: pd.Series) -> pd.DataFrame:
    """Küme (satır) × gerçek segment (sütun) mağaza sayıları."""
    e, g = _ortak(etiket, gercek)
    return pd.crosstab(pd.Series(e, name="kume"), pd.Series(g, name="segment"))


def saflik(etiket: pd.Series, gercek: pd.Series) -> pd.DataFrame:
    """Segment başına: `n`, en çok düştüğü `kume`, o kümedeki `pay`ı, kümenin segment payı (`kume_payi`)."""
    t = capraz(etiket, gercek)
    satir = []
    for s in t.columns:
        c = t[s]
        g = c.index[int(np.argmax(c.to_numpy()))]
        satir.append({"segment": s, "n": int(c.sum()), "kume": g, "pay": c[g] / c.sum(),
                      "kume_payi": c[g] / t.loc[g].sum()})
    return pd.DataFrame(satir).set_index("segment")


def toplam_saflik(etiket: pd.Series, gercek: pd.Series) -> float:
    """Klasik saflık: Σ_küme (çoğunluk segmentinin mağaza sayısı) / n."""
    t = capraz(etiket, gercek)
    return float(t.max(axis=1).sum() / t.to_numpy().sum())


# ---------------------------------------------------------------------------
# Kararlılık
# ---------------------------------------------------------------------------


def _satisli_hafta(tablolar, ids: list[str], bas: pd.Timestamp, bit: pd.Timestamp) -> pd.Series:
    """Mağaza → `[bas, bit)` içinde brüt (pozitif adetli) satışı olan pazartesi-pazar hafta sayısı."""
    if isinstance(tablolar, Mapping):
        s = tablolar["satis"]
        s = s.loc[(s["adet"] > 0) & (s["tarih"] >= bas) & (s["tarih"] < bit), ["tarih", "magaza_id"]]
        gun = pd.to_datetime(s["tarih"]).dt.normalize()
        h = pd.DataFrame({"m": s["magaza_id"].astype(str).to_numpy(),
                          "h": (gun - pd.to_timedelta(gun.dt.weekday, unit="D")).to_numpy()})
        sayi = h.drop_duplicates().groupby("m").size()
    else:
        df = tablolar.execute(
            "select magaza_id::varchar as m, count(distinct date_trunc('week', tarih)) as n from satis "
            "where adet > 0 and tarih >= ? and tarih < ? group by 1",
            [bas.to_pydatetime(), bit.to_pydatetime()]).df()
        sayi = df.set_index("m")["n"]
    return sayi.reindex(ids).fillna(0).astype("int64")


def _eslesik_degisen(cekilis: np.ndarray, tam: np.ndarray) -> np.ndarray:
    """Çekiliş kümeleri tam kümelere birebir (ortak üye sayısını en çoklayan) eşlenir; eşlenmiş
    kümesi tam kümesinden farklı (ya da eşlenmemiş kümede) olan mağaza True."""
    c_ad, c = np.unique(cekilis, return_inverse=True)
    t_ad, t = np.unique(tam, return_inverse=True)
    ortak = np.zeros((len(c_ad), len(t_ad)), dtype=np.int64)
    np.add.at(ortak, (c, t), 1)
    sat, sut = linear_sum_assignment(-ortak)
    hedef = np.full(len(c_ad), -1)
    hedef[sat] = sut
    return hedef[c] != t


def kararlilik(fn_kume: Callable[[pd.DataFrame], pd.Series], tablolar, kapsam: pd.DataFrame,
               urunler: pd.DataFrame | None, donemler: Mapping[str, tuple] = DONEMLER, *, aile: str,
               karar_gunu=sabitler.KARAR_GUNU, ozellik: pd.DataFrame | None = None,
               en_az_hafta: int = sabitler.GECMIS_HAFTA_ESIGI, ornek: int = ONYUKLEME_ORNEK,
               tohum: int = sabitler.TOHUM) -> dict:
    """Yıllar arası ARI ve önyüklemede mağaza başına küme değişme sıklığı (modül notu).

    fn_kume     standartlanmış özellik tablosu → küme etiketi (örn. `partial(ogren.kume,
                yontem="ward", k=5)`)
    tablolar    `ozellikler.ozellik_tablosu` girdisi (bağlantı ya da `satis`, `stok`, `magaza`)
    kapsam      `kaynak.kapsam` (kümelenen mağazalar kullanılır)
    donemler    dönem adı → (pencere sonu günü, hafta)
    aile        özellik ailesi (`ozellikler.AILELER`)
    ozellik     verilirse karar günü ham özellik tablosu (kümelenen mağazalar; önyükleme için,
                yeniden kurulmaz)

    Dönüş: `donem` (dönem × bas, bit, hafta, magaza), `satisli_hafta` (mağaza × dönem),
    `disarida` (yıllar arası karşılaştırmaya girmeyen mağazalar), `etiketler` (dönem → bölme),
    `ari` ((dönem, dönem) → ARI), `degisme` (mağaza → sıklık), `gorulme` (mağaza → çekiliş
    sayısı), `degisme_ort`, `onyukleme_ari`."""
    ids = sorted(kapsam.loc[kapsam["kumelenir"].astype(bool), "magaza_id"].astype(str))

    # yıllar arası
    pencereler = {d: ozellikler.pencere(gun, hafta) for d, (gun, hafta) in donemler.items()}
    hafta = pd.DataFrame({d: _satisli_hafta(tablolar, ids, *p) for d, p in pencereler.items()})
    hafta.index.name = "magaza_id"
    yeterli = (hafta >= en_az_hafta).all(axis=1)
    ortak = list(hafta.index[yeterli])
    etiketler = {}
    for d, (gun, h) in donemler.items():
        X = ozellikler.ozellik_tablosu(tablolar, ortak, urunler, gun, aile, hafta=h)
        etiketler[d] = fn_kume(ozellikler.standartla(X, aile)).reindex(ortak)
    adlar = list(donemler)
    ari = {(a, b): float(adjusted_rand_score(etiketler[a].to_numpy(), etiketler[b].to_numpy()))
           for i, a in enumerate(adlar) for b in adlar[i + 1:]}
    donem = pd.DataFrame([{"donem": d, "bas": p[0], "bit": p[1], "hafta": donemler[d][1],
                           "magaza": len(ortak)} for d, p in pencereler.items()]).set_index("donem")

    # önyükleme
    X = ozellik if ozellik is not None else ozellikler.ozellik_tablosu(tablolar, ids, urunler,
                                                                        karar_gunu, aile)
    if sorted(X.index.astype(str)) != ids:
        raise ValueError("özellik tablosunun mağazaları kapsamın kümelenenleri değil")
    Z = ozellikler.standartla(X, aile)
    Z.index = Z.index.astype(str)
    Z = Z.loc[ids]
    tam = fn_kume(Z).reindex(ids).to_numpy()
    rng = np.random.default_rng(tohum)
    degis = np.zeros(len(ids), dtype=np.int64)
    gor = np.zeros(len(ids), dtype=np.int64)
    aris = []
    for _ in range(ornek):
        cek = np.sort(rng.integers(0, len(ids), size=len(ids)))
        ad, sira = [], {}
        for j in cek:
            sira[j] = sira.get(j, -1) + 1
            ad.append(ids[j] if sira[j] == 0 else f"{ids[j]}#{sira[j]}")
        B = pd.DataFrame(Z.to_numpy()[cek], index=pd.Index(ad, name="magaza_id"), columns=Z.columns)
        e = fn_kume(B)
        tekil = np.unique(cek)
        ce = e.loc[[ids[j] for j in tekil]].to_numpy()
        degis[tekil] += _eslesik_degisen(ce, tam[tekil])
        gor[tekil] += 1
        aris.append(adjusted_rand_score(tam[tekil], ce))
    sik = pd.Series(np.where(gor > 0, degis / np.maximum(gor, 1), np.nan), index=pd.Index(ids, name="magaza_id"),
                    name="degisme")
    return {"donem": donem, "satisli_hafta": hafta, "disarida": list(hafta.index[~yeterli]),
            "etiketler": etiketler, "ari": ari, "degisme": sik,
            "gorulme": pd.Series(gor, index=sik.index, name="gorulme"),
            "degisme_ort": float(sik.mean()), "onyukleme_ari": float(np.mean(aris))}


# ---------------------------------------------------------------------------
# Yeni mağaza doğruluğu
# ---------------------------------------------------------------------------


def _cogunluk(degerler: pd.Series):
    if degerler.empty:
        return None
    say = degerler.value_counts()
    return sorted(say.index[say == say.max()])[0]


def birakbir_dogruluk(tablo: pd.DataFrame, gizli: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`yeni_magaza.birakbir` tablosu + gizli segment → (mağaza tablosu, özet) (modül notu)."""
    t = tablo.copy()
    t["magaza_id"] = t["magaza_id"].astype(str)
    _, g = _ortak(t.set_index("magaza_id")["gercek_kume"], gizli)
    t["gizli"] = g
    kume = t.set_index("magaza_id")["gercek_kume"]
    seg = t.set_index("magaza_id")["gizli"]

    def kume_cogunlugu(m, c):
        uye = kume.index[(kume == c) & (kume.index != m)]
        return _cogunluk(seg.loc[uye])

    t["atanan_segment"] = [kume_cogunlugu(m, c) for m, c in zip(t["magaza_id"], t["atanan"])]
    t["kume_segment"] = [kume_cogunlugu(m, c) for m, c in zip(t["magaza_id"], t["gercek_kume"])]
    t["dogru_kume"] = t["atanan"] == t["gercek_kume"]
    t["dogru_segment"] = t["atanan_segment"] == t["gizli"]
    t["kume_dogru_segment"] = t["kume_segment"] == t["gizli"]
    t["taban_kume"] = [t["gercek_kume"].iloc[i] == _cogunluk(t["gercek_kume"].drop(t.index[i]))
                       for i in range(len(t))]
    t["taban_segment"] = [t["gizli"].iloc[i] == _cogunluk(t["gizli"].drop(t.index[i]))
                          for i in range(len(t))]

    olcut = ["dogru_kume", "dogru_segment", "kume_dogru_segment", "taban_kume", "taban_segment"]
    gruplar = {"hepsi": t, "metropol": t[t["metropol"]], "metropol_disi": t[~t["metropol"]]}
    ozet = pd.DataFrame([{"grup": ad, "n": len(d), **{o: float(d[o].mean()) if len(d) else np.nan
                                                       for o in olcut}}
                         for ad, d in gruplar.items()]).set_index("grup")
    return t, ozet
