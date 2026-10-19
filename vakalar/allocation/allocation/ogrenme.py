"""Erken talep (sansür düzeltmeli) ve öğrenme tablosu: geçmiş sezonların ilk 6 haftası.

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme
dokunmaz; yayımlanan tablolardan (`kaynak`) ve dünyanın açık alanlarından (`optionlar`,
`urunler`, `magazalar`, `sezon`, `takvim`, `ilk_alim`, hücre dizileri) okur.

**Erken pencere** (spec §0/11). Her (fiziksel mağaza, option) için option'ın o mağazaya ilk
dağıtım varışından (`ilk_varislar`) başlar, `ERKEN_GUN` (42) gün sürer ve sezonun erken
kesiminde (`kaynak.erken_kesim`, dahil) kesilir: pencere `[varış, min(varış + 42, kesim + 1))`.
Kesimden sonra varan hücrenin penceresi boştur. v4'te ilk dağıtım lansman günü ya da
sonrasında varır (yayımlanan veride en geç 17 gün sonra), varış günü bir tanedir.

**Sansür düzeltmesi** (Ruling R3: stoklu gün hızı, ortak Basit değil). SKU hücresi başına,
pencere günü `L`, penceredeki brüt satış `s` ve stoklu gün `f` (`kaynak.gunluk_matrisler`'in
tanımı: satış öncesi raf > 0; tükenen gün stoklu sayılır):

    f >= 3       talep = s / f × L
    f = 1, 2     talep = s           (oran çok az günden: olduğu gibi)
    f = 0        hücre dışarıda      (bilgi yok; satışı `satis`'te görünür)

Option talebi, dışarıda kalmayan SKU'ların toplamıdır. Sonuç satırının `stoklu_gun`'ü en az
bir bedenin stoklu olduğu pencere günü sayısıdır; 0 ise satır kalır, `talep` NaN'dır. Bedeli:
hiç stoklanmayan bedenin talebi option toplamında yoktur (ilk dağıtım bütün bedenleri paketle
gönderdiği için seyrek), tükenen gün tam stoklu sayılır (Basit'in koşullu düzeltmesi yok).

**Öğrenme tablosu** (`ogrenme_tablosu`). Karar gününde kapanmış (`kapanmis_sezonlar`) `LINE`
sezonlarının option'ları; matrisler `bit = karar_gunu` ile kurulur ve tablolar önce bu
option'ların SKU'larına daraltılır (`daralt`; stok kurulumu hücre başına olduğu için o
hücrelerde sonuç aynıdır, testli). Varışlar yalnız karar gününden önce varanlardır.
"""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from allocation import kaynak, sabitler

ERKEN_SUTUNLARI = ("option", "magaza", "satis", "stoklu_gun", "talep")
OZNITELIKLER = ("ust_kategori", "alt_kategori", "fiyat_segmenti", "kalip", "kumas", "renk", "desen",
                "cinsiyet", "dalga", "liste_fiyati", "sezon_kodu")
EN_AZ_STOKLU_GUN = 3        # bundan az stoklu günde satış olduğu gibi alınır
# `urun_id` taşıyan hareket tabloları: öğrenme bunları option kümesine daraltır
HAREKET_TABLOLARI = ("satis", "stok", "sevkiyat", "depo_stok", "siparis")


def _gun0(w) -> pd.Timestamp:
    return pd.Timestamp(w.takvim["tarih"].iloc[0]).normalize()


# ---------------------------------------------------------------------------
# İlk varışlar
# ---------------------------------------------------------------------------


def ilk_varislar(tablolar: Mapping[str, pd.DataFrame], w) -> dict[tuple[int, int], int]:
    """`sevkiyat`'ın `ilk_dagitim` satırlarından (mağaza indisi, option indisi) -> ilk varış
    günü (dünya gün indisi, 0 = `takvim`in ilk günü). Varışı boş satır ve dünyanın evreninde
    olmayan mağaza / ürün düşer; option'ın SKU'ları arasında en erken varış alınır."""
    s = tablolar["sevkiyat"]
    s = s[(s["tip"] == "ilk_dagitim").fillna(False).to_numpy(dtype=bool) & s["varis_tarihi"].notna().to_numpy()]
    m = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(s["hedef"].astype(str))
    sku = pd.Index(w.urunler["urun_id"].astype(str)).get_indexer(s["urun_id"].astype(str))
    var = (m >= 0) & (sku >= 0)
    gun = (pd.to_datetime(s["varis_tarihi"]).dt.normalize() - _gun0(w)).dt.days.to_numpy()
    df = pd.DataFrame({"m": m[var], "o": np.asarray(w.sku_option)[sku[var]], "g": gun[var]})
    ilk = df.groupby(["m", "o"])["g"].min()
    return {(int(mi), int(oi)): int(g) for (mi, oi), g in ilk.items()}


# ---------------------------------------------------------------------------
# Erken talep
# ---------------------------------------------------------------------------


def _bos_erken() -> pd.DataFrame:
    return pd.DataFrame({"option": np.array([], np.int64), "magaza": np.array([], np.int64),
                         "satis": np.array([], np.int64), "stoklu_gun": np.array([], np.int64),
                         "talep": np.array([], np.float64)})


def erken_talep(satis: np.ndarray, stoklu: np.ndarray, harita: kaynak.Harita, w,
                optionlar: np.ndarray, ilk_varis: Mapping[tuple[int, int], int]) -> pd.DataFrame:
    """`optionlar`ın her (fiziksel mağaza, option) çiftinin erken penceresi (modül notu).

    satis, stoklu  `kaynak.gunluk_matrisler`'in `[gün, C]` matrisleri (gün 0 = `takvim`
                   başı); boş olmayan her pencereyi kapsamalı, yoksa `ValueError`
    ilk_varis      (m, o) -> varış günü (`ilk_varislar`); çifti olmayan mağaza aday değildir

    Dönüş: `ERKEN_SUTUNLARI`; `option`, `magaza` indis; `option`, `magaza` sırasıyla."""
    optionlar = np.asarray(optionlar, dtype=np.int64)
    O = len(harita.option_line)
    secili = np.zeros(O, dtype=bool)
    secili[optionlar] = True
    ciftler = sorted((int(m), int(o)) for (m, o) in ilk_varis
                     if secili[o] and harita.magaza_fiziksel[m])
    if not ciftler:
        return _bos_erken()
    cm = np.array([m for m, _ in ciftler], dtype=np.int64)
    co = np.array([o for _, o in ciftler], dtype=np.int64)
    bas = np.array([ilk_varis[c] for c in ciftler], dtype=np.int64)
    if (bas < 0).any():
        raise ValueError("ilk varış dünya takviminden önce")
    gun0 = _gun0(w)
    kesim = {sz: (kaynak.erken_kesim(w, sz) - gun0).days for sz in np.unique(harita.option_sezon[co])}
    son = np.minimum(bas + sabitler.ERKEN_GUN, np.array([kesim[sz] for sz in harita.option_sezon[co]]) + 1)
    son = np.maximum(son, bas)
    pencere = son - bas
    n = satis.shape[0]
    if ((pencere > 0) & (son > n)).any():
        raise ValueError(f"matrisler ({n} gün) erken pencereleri kapsamıyor (en geç {int(son.max())})")

    # hücreler -> çift (sıralı anahtar: m × O + o)
    anahtar = cm * O + co
    hucre = np.flatnonzero(secili[harita.hucre_option] & harita.magaza_fiziksel[harita.hucre_magaza])
    hk = harita.hucre_magaza[hucre] * O + harita.hucre_option[hucre]
    j = np.searchsorted(anahtar, hk)
    var = j < len(anahtar)
    var[var] = anahtar[j[var]] == hk[var]
    hucre, j = hucre[var], j[var]

    # pencere günleri [k, ERKEN_GUN]
    gunler = bas[j][:, None] + np.arange(sabitler.ERKEN_GUN)
    icinde = gunler < son[j][:, None]
    gunler = np.where(icinde, gunler, 0)
    if n == 0:
        icinde[:] = False
        s = np.zeros(icinde.shape, dtype=np.int64)
        f = icinde.copy()
    else:
        s = np.where(icinde, satis[gunler, hucre[:, None]], 0).astype(np.int64)
        f = icinde & stoklu[gunler, hucre[:, None]]

    sku_satis = s.sum(axis=1)
    sku_stoklu = f.sum(axis=1)
    L = pencere[j]
    oran = np.divide(sku_satis * L, sku_stoklu, out=np.zeros(len(j)), where=sku_stoklu > 0)
    sku_talep = np.where(sku_stoklu >= EN_AZ_STOKLU_GUN, oran, sku_satis.astype(np.float64))
    giren = sku_stoklu > 0

    P = len(ciftler)
    toplam_satis = np.bincount(j, weights=sku_satis, minlength=P).astype(np.int64)
    toplam_talep = np.bincount(j[giren], weights=sku_talep[giren], minlength=P)
    gun_stoklu = np.zeros((P, sabitler.ERKEN_GUN), dtype=np.int64)
    np.add.at(gun_stoklu, j, f)
    stoklu_gun = (gun_stoklu > 0).sum(axis=1).astype(np.int64)
    talep = np.where(stoklu_gun > 0, toplam_talep, np.nan)

    df = pd.DataFrame({"option": co, "magaza": cm, "satis": toplam_satis, "stoklu_gun": stoklu_gun,
                       "talep": talep})
    return df.sort_values(["option", "magaza"], ignore_index=True)


# ---------------------------------------------------------------------------
# Öğrenme tablosu
# ---------------------------------------------------------------------------


def kapanmis_sezonlar(w, tablolar: Mapping[str, pd.DataFrame], karar_gunu: pd.Timestamp) -> list[str]:
    """Karar gününde kapanmış ve yayımlanan veriye bütünüyle giren sezonlar (lansman sırasıyla).

    Ortak `hazirlik.kapanmis_sezonlar`'ın tanımı, dünyanın `sezon` alanından: dalgaların en geç
    çıkışı `< karar_gunu` (çıkışı tam karar günü olan temkinle kapanmamış) ve en erken lansmanı
    `>=` stok fotoğraflarının ilk günü (pencerenin başında yarım kalan sezon, v4'te AW22, girmez)."""
    ilk = tablolar["stok"]["tarih"].min()
    if pd.isna(ilk):
        return []
    s = w.sezon.assign(sezon_kodu=w.sezon["sezon_kodu"].astype(str)).groupby("sezon_kodu").agg(
        lansman=("lansman_tarihi", "min"), cikis=("cikis_tarihi", "max")).sort_values("lansman")
    karar = pd.Timestamp(karar_gunu).normalize()
    tut = (s["cikis"] < karar) & (s["lansman"] >= pd.Timestamp(ilk).normalize())
    return s.index[tut.to_numpy()].tolist()


def daralt(tablolar: Mapping[str, pd.DataFrame], w, optionlar: np.ndarray) -> dict[str, pd.DataFrame]:
    """Hareket tablolarını (`HAREKET_TABLOLARI`) `optionlar`ın SKU'larına daraltır; öteki
    tablolar olduğu gibi. Stok kurulumu hücre başına olduğu için daraltılan option'ların
    hücrelerinde `gunluk_matrisler` aynıdır; öteki hücreler boş kalır."""
    sku = np.isin(np.asarray(w.sku_option), np.asarray(optionlar, dtype=np.int64))
    urunler = pd.Index(w.urunler["urun_id"].astype(str).to_numpy()[sku])
    dar = dict(tablolar)
    for ad in HAREKET_TABLOLARI:
        if ad in dar:
            t = dar[ad]
            # kategorik sütunda (DuckDB ENUM) `isin` kategorilere bakar; dizgeye çevirmek
            # milyonlarca satırda yavaş
            dar[ad] = t[t["urun_id"].isin(urunler).to_numpy(dtype=bool)].reset_index(drop=True)
    return dar


def option_oznitelikleri(w, optionlar: np.ndarray) -> pd.DataFrame:
    """`optionlar`ın açık öznitelikleri (`OZNITELIKLER`) + `ilk_alim`; satır sırası
    `optionlar`ınki, indeks 0..n-1. Metin sütunları `str`, `dalga` int (sürekli mal 0)."""
    optionlar = np.asarray(optionlar, dtype=np.int64)
    o = w.optionlar.iloc[optionlar].reset_index(drop=True)
    df = pd.DataFrame(index=pd.RangeIndex(len(optionlar)))
    for s in OZNITELIKLER:
        if s == "dalga":
            df[s] = o[s].fillna(0).to_numpy().astype(np.int64)
        elif s == "liste_fiyati":
            df[s] = o[s].to_numpy(dtype=np.float64)
        else:
            df[s] = o[s].astype(str).to_numpy()
    df["ilk_alim"] = np.asarray(w.ilk_alim)[optionlar]
    return df


def ogrenme_tablosu(tablolar: Mapping[str, pd.DataFrame], w, karar_gunu: pd.Timestamp) -> pd.DataFrame:
    """Karar gününde kapanmış `LINE` sezonlarının erken talebi + option öznitelikleri.

    Sütunlar: `ERKEN_SUTUNLARI`, `OZNITELIKLER`, `ilk_alim`; `option`, `magaza` sırasıyla.
    Yalnız karar gününden önceki bilgi: matrisler `bit = karar_gunu`, varışlar `< karar_gunu`.
    `tablolar` bütün tablolar olmalı (`gunluk_matrisler` karar gününden sonraki pazartesi
    fotoğrafını ister; kapanmış sezonların penceresi zaten çok önce biter). Bir TAM çağrı tek
    `gunluk_matrisler` çağrısıdır: öğrenme işi başına bir kez çağırın."""
    karar = pd.Timestamp(karar_gunu).normalize()
    sezonlar = kapanmis_sezonlar(w, tablolar, karar)
    o = w.optionlar
    secili = np.flatnonzero((o["line"].astype(str) == sabitler.LINE).to_numpy()
                            & o["sezon_kodu"].astype(str).isin(sezonlar).to_numpy()).astype(np.int64)
    if secili.size == 0:
        et = _bos_erken()
    else:
        dar = daralt(tablolar, w, secili)
        satis, stoklu = kaynak.gunluk_matrisler(dar, w, karar)
        sev = dar["sevkiyat"]
        varis = ilk_varislar({"sevkiyat": sev[(sev["varis_tarihi"] < karar).fillna(False).to_numpy(dtype=bool)]}, w)
        et = erken_talep(satis, stoklu, kaynak.harita_kur(w), w, secili, varis)
        del satis, stoklu
    oz = option_oznitelikleri(w, et["option"].to_numpy())
    return pd.concat([et, oz], axis=1)
