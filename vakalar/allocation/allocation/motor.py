"""Üretecin tek kapısı: v4 dünyası, politika enjeksiyonu, kaydediciler, takvim, kırpma
tablosu, koşu önbelleği, gizli gerçek.

DM vakasının `replenishment/motor.py`'sinin kopyasıdır (spec §0/7, DM R1 emsali; ortak
parçaya çıkarılmaz, RPT ve DM'nin kod özeti ve ızgarası korunur). Farklar: ilk alım oranı
yoktur (dünya `dunya("tam")`, yayımlanan); dört politika yuvası enjekte edilir
(`ilk_dagitim`, `replenishment`, `rpt`, `markdown`); Lumoda'nın ilk dağıtım, RPT ve
markdown kararları her koşuda kaydedilir (Ruling R2, `kaydedici` bayrağı yok); outlet
akışı kaydedilmez; `takvim` ve `kirpma_tablosu` eklenir.

Vakada `perakende_veri`'yi (v4 üreteci) yalnız bu modül içe aktarır. Karar modülleri
(`kaynak`, `ogrenme`, `benzer`, `tahmin`, `paylastir`, `politika`, `kalibrasyon`,
`hikaye_sec`) bu modülü de içe aktarmaz (`tests/test_sizinti.py` kilitler); politika yalnız
`Gorunum`'ü ve dünyanın açık alanlarını okur. Gizli gerçek (`Kosu.gercek`) yalnız ölçüme ve
rapora gider.

    w = dunya()                                       # TAM v4 dünyası (süreç içi önbellek)
    k = kos(benim_kolum, ad="kural", parametreler={...})
    k.tablolar["sevkiyat"], k.gercek, k.kayitlar["rpt"], k.meta
    takvim(k), kirpma_tablosu(k)

KOŞU. `kos` `Politikalar(ilk_dagitim=..., replenishment=..., rpt=..., markdown=...)` ile
(verilmeyen yuva Lumoda) `simule_et(..., kayit_talep=True, talep_tohumu,
operasyon_tohumu)` koşar ve döndürür:

    tablolar  yayımlanan 18 tablonun TEMİZ hâli (`hareket_tablolari`: aynı şema, aynı
              pencere, kirli kayıt yok). Kollar arası farkın yalnız kararlardan gelmesi
              için kirletilmez; yayımlanan biçim `yayimlanan_bicim(tablolar)` (aynı kirli
              kayıtlar).
    gercek    hücre-gün gizli gerçek (`gercek_tablosu`; hakem tanımı)
    kayitlar  yuva adı → DataFrame: Lumoda kaydedicilerinin ve enjekte edilen
              politikaların `kayit_tablosu()`'su (varsa). Önbellekten okunan koşuda
              politika çalışmadığı için yan etkisi buradan gelir
    meta      anahtar bileşenleri, süre, tepe bellek, satır sayıları

KAYDEDİCİLER. Verilmeyen `ilk_dagitim`, `rpt`, `markdown` yuvaları (`KAYDEDILENLER`)
Lumoda'nın politikasını `Kaydedici`yle sarılı alır: sardığını aynen çağırır, aynı nesneyi
döndürür, her çağrıyı `{"gun", "args", "cikti"}` olarak (çıktının kopyası; DM Ruling R3)
canlı `kayit` listesine ekler. Çıktıyı değiştirmez (`test_kaydedici_ciktiyi_degistirmez`,
eşdeğerlik testi). Bu iç kaydediciler hep Lumoda'yı sardığı için anahtara bir şey
eklemezler (kod özetindedirler). Enjekte edilen politika Lumoda kaydedicisinin yerine
geçer; kaydı kendi `kayit_tablosu()`'ndan gelir (vakanın kendisinin sardığı
`Kaydedici(kol)` sardığını `temel` ile anahtara taşır). Enjekte edilen politika `baglan`
taşıyorsa iç kaydediciler ona `baglan({yuva: kaydedici})` ile verilir. Kayıt politikanın
kararıdır, motorun uyguladığı değil: motor ilk dağıtımı aday maskesiyle ve depo stoğuyla
kırpar (`paketleri_sigdir`), sevki lansmandan önceki güne erteleyebilir (kayıttaki `gun`
karar günüdür); farkı `kirpma_tablosu` verir.

TAKVİM. `takvim(kosu)` kayıtlı RPT ve markdown kararlarından `Takvim` kurar (gün → RPT
sözlüğü, gün → [O, 3] markdown oranı); sabit takvim kolları (spec §4.5) bunu `rpt=` ve
`markdown=` yuvalarında yeniden oynatır. Takvim pickle'lanır; kimliği içerikten
(`sabitle()`).

`kos(..., tembel=True)` (önbellek ister) tabloları belleğe almadan `KosuKaydi` döndürür:
tablolar ve gizli gerçek istendikçe diskten, yalnız gereken sütun ve SKU'larla
(`tablo(ad, sutunlar, urunler)`; `Kosu`da da aynı yöntem).

ÖNBELLEK. `onbellek` dizininde (varsayılan `cikti/kosular/`) koşu başına bir alt dizin
`<ad>_<anahtar[:20]>`: tablolar, kayıtlar ve gizli gerçek Parquet, `meta.json` en son.
Dizin önce `.yaziliyor` adıyla yazılır, sonra tek `os.replace` ile yerine konur;
`meta.json`'u olmayan ya da anahtarı tutmayan dizin okunmaz; meta'sı tam ama Parquet'i
eksik/bozuk kayıt silinip yeniden koşulur; bu süreçten eski `.yaziliyor-*` artıkları
silinir. Anahtar (`onbellek_anahtari`): `ad`, `parametreler` (kanonik JSON), enjekte
edilen her yuvanın politika türü (sınıf / fonksiyon tam adı) ve kimliği, iki tohum, ölçek,
gün sayısı, kod özeti (yalnız koşuyu etkileyen kaynaklar: `KOSU_MODULLERI`, onların ortak
paket kapanışı, `perakende_veri/v4/**/*.py`; satır sonları LF), v4 DuckDB dosyasının
parmak izi (ad, boyut, değişiklik zamanı), numpy / pandas / pyarrow / lightgbm /
scikit-learn sürümü.

GEÇMİŞ KAYDI. Enjekte edilen politikalardan biri `gecmis_gerekir = True` taşıyorsa motor
`gecmis_kaydi=True` ile koşar. Kayıt yalnız okur, çıktılar birebir aynıdır; anahtara
girmez.

LUMODA. Karar modülleri üreteci içe aktarmadığı için Lumoda'nın bugünkü kuralları kollara
argüman olarak verilir: `lumoda("ilk_dagitim")` (v4 `lumoda_ilk_dagitim`; kolun `temel`i).

POLİTİKANIN KENDİ KİMLİĞİ. Enjekte edilen politikanın `parametreler()` yöntemi varsa
çıktısı, `temel` (sardığı politika; ör. kolun Lumoda kuralı, kaydedicinin sardığı) varsa
onun türü ve kimliği (özyinelemeli) anahtara kendiliğinden girer (`politika_kimligi`).
Öğrenilmiş nesneler kimliklerini İÇERİKTEN taşır (RPT'nin pickle kimliği dersi):
`sabitle()` ile içerik özeti (takvim dahil); LightGBM modelinin özeti
`booster.model_to_string()`'in SHA-256'sı (pickle baytı değil).

**Politikalar Python nesneleridir; anahtar onları `ad` + `parametreler` + kimlik ile
tanır.** Çağıran, politikanın davranışını değiştiren HER parametreyi (tutma oranı, tavan,
pay kaynağı, eğitim verisinin kaynağı olan koşunun anahtarı, takvimin kimliği, …)
`parametreler`'e ya da politikanın `parametreler()`'ine koymalıdır; aksi halde farklı
davranan iki politika aynı önbellek kaydını okur. Ölçüm sonucu (oyun / yollar /
kalibrasyon) politikaya yalnız `parametreler` üstünden girer. Kod değişikliği özetle, veri
değişikliği parmak iziyle yakalanır. Kod özeti çağrı anındaki dosyalardan alınır: süreç
açıkken değiştirilen kod (yüklenmiş modül eski) yakalanmaz, süreç yeniden başlatılmalıdır.

Koşular sıralıdır: önbellek eşzamanlı yazıma karşı korunmaz (RPT ve DM koşularıyla da aynı
anda koşulmaz). Bir TAM koşu ~4 dk, tepe ~8 GB. `dunya` her ölçek için bir dünya tutar
(süreç içi); `dunya.cache_clear()` belleği bırakır.
"""

import ast
import copy
import dataclasses
import functools
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import shutil
import sys
import time
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import perakende_veri.v4 as _v4_paketi
from perakende_analitik import kaynak as ortak
from perakende_veri.v4 import sabitler as v4_sabitler
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.dunya import akislar, dunya_kur
from perakende_veri.v4.kirlet import kirlet
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar, lumoda_politikalari

TOHUM = v4_sabitler.TOHUM
PAKET_ADI = "allocation"
PAKET_KOKU = Path(__file__).resolve().parent                    # vakalar/allocation/allocation
KOSU_DIZINI = PAKET_KOKU.parent / "cikti" / "kosular"
VERI_YOLU = ortak.VARSAYILAN_YOL
OLCEKLER = {"tam": Olcek.TAM, "kucuk": Olcek.KUCUK}

# Kod özetine giren kaynaklar (yalnız koşuyu etkileyenler):
#   allocation  KOSU_MODULLERI (henüz olmayan dosya atlanır). Ölçüm, anlatı ve
#          kalibrasyon (KOSU_DISI; vaka kökü rapor*.py, testler) koşuyu değiştirmez: bir
#          ölçümün sonucu politikaya girerse (ör. kalibrasyonun seçtiği değer) o sonuç
#          `parametreler`'e girer. allocation/'daki her modül iki listeden birindedir
#          (tests/test_motor.py).
#   ortak  perakende_analitik'te ORTAK_TOHUM + vaka kaynaklarının içe aktardığı ortak
#          modüllerin içe aktarma kapanışı (AST; hakem gibi ulaşılmayan modüller girmez)
#   v4     perakende_veri/v4/**/*.py
KOSU_MODULLERI = ("motor", "sabitler", "kaynak", "ogrenme", "benzer", "tahmin", "paylastir", "politika")
KOSU_DISI = ("olcutler", "oyun", "yollar", "hikaye_sec", "senaryolar", "kalibrasyon")
ORTAK_TOHUM = ("kaynak", "stok", "ozellikler", "carpanlar", "talep", "hazirlik")
KOD_KOKLERI = {
    PAKET_ADI: PAKET_KOKU,
    "ortak": Path(ortak.__file__).resolve().parent,                 # perakende_analitik/
    "v4": Path(_v4_paketi.__file__).resolve().parent,
}
ORTAK_PAKET = "perakende_analitik"

# Enjekte edilebilen politika yuvaları (`Politikalar` alan adları; `kos`un argümanları)
YUVALAR = ("ilk_dagitim", "replenishment", "rpt", "markdown")
# Verilmediğinde Lumoda'nın kaydedicilerle sarılan kararları (Ruling R2: her koşuda)
KAYDEDILENLER = ("ilk_dagitim", "rpt", "markdown")
HAT_SAYISI = 3   # markdown çıktısı [O, 3]: normal / outlet / online hattı

GERCEK_SUTUNLARI = ("talep", "kendi_satis", "karsilanmayan", "ikameye_giden", "kalici_kayip")
_AD_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


# ---------------------------------------------------------------------------
# Dünya, Lumoda, kaydedici
# ---------------------------------------------------------------------------


@functools.cache
def _dunya(olcek: str):
    return dunya_kur(OLCEKLER[olcek])


def dunya(olcek: str = "tam"):
    """v4 dünyası (`dunya_kur`, varsayılan tohum, yayımlanan dünya; süreç içi önbellek,
    TAM ~20 sn)."""
    if olcek not in OLCEKLER:
        raise ValueError(f"ölçek {sorted(OLCEKLER)}'den biri olmalı: {olcek!r}")
    return _dunya(olcek)


dunya.cache_clear = _dunya.cache_clear


def lumoda(ad: str):
    """Lumoda'nın v4 politikası (`Politikalar` alan adı: "ilk_dagitim", "rpt", "markdown", …)."""
    p = lumoda_politikalari()
    if ad not in p:
        raise ValueError(f"Lumoda politikası {sorted(p)}'den biri olmalı: {ad!r}")
    return p[ad]


def _kopya(x):
    """Kayda giren kopya: numpy skaleri Python sayısına, gerisi derin kopya."""
    if isinstance(x, np.generic):
        return x.item()
    return copy.deepcopy(x)


def _skaler(x) -> bool:
    return isinstance(x, (bool, int, float, np.generic))


def _sozluk_sutunlari(c: dict) -> dict[str, np.ndarray]:
    """RPT biçimi {option: adet | SKU dizisi} → `indis`, `alt`, `deger` (anahtar sırasıyla;
    skaler değerde `alt` = −1, dizide dizinin sırası; dizinin sıfır öğeleri de girer)."""
    indis, alt, deger = [], [], []
    for k, v in c.items():
        if np.ndim(v) == 0:
            indis.append(int(k))
            alt.append(-1)
            deger.append(_kopya(v))
        else:
            v = np.asarray(v).ravel().tolist()
            indis += [int(k)] * len(v)
            alt += range(len(v))
            deger += v
    return {"indis": np.asarray(indis, dtype=np.int64), "alt": np.asarray(alt, dtype=np.int64),
            "deger": np.asarray(deger)}


class Kaydedici:
    """Bir politikayı sarar: aynen çağırır, aynı nesneyi döndürür, her çağrıyı kaydeder
    (çıktıyı değiştirmez).

    `kayit` (canlı liste; DM Ruling R3): her çağrı için `{"gun": g.gun, "args": (g
    dışındaki argümanların kopyaları), "cikti": çıktının kopyası}`. Örnekler:
    `ilk_dagitim` → `args=(o,)`, `cikti` [M] paket sayısı; `rpt` → `args=()`, `cikti`
    {option: adet}; `markdown` → `args=()`, `cikti` [O, 3] oran; `replenishment` →
    `args=()`, `cikti` [C] istek. Kopya: motor ya da politika dönen nesneyi sonradan
    değiştirse de kayıt değişmez.

    `temel` sarılan politikadır: `politika_kimligi` onun türünü ve kimliğini anahtara
    taşır (kaydedici kimliksiz bir kabuktur). `gecmis_gerekir` ve `baglan` sarılana geçer.
    Sarılanın kendi `kayit_tablosu`'nu gölgeler.
    """

    def __init__(self, temel):
        self.temel = temel
        self.kayit: list[dict] = []

    def __call__(self, g, *args):
        cikti = self.temel(g, *args)
        self.kayit.append({"gun": int(g.gun), "args": tuple(_kopya(a) for a in args),
                           "cikti": _kopya(cikti)})
        return cikti

    @property
    def gecmis_gerekir(self) -> bool:
        return bool(getattr(self.temel, "gecmis_gerekir", False))

    def baglan(self, kaydediciler: dict) -> None:
        f = getattr(self.temel, "baglan", None)
        if callable(f):
            f(kaydediciler)

    def kayit_tablosu(self) -> pd.DataFrame:
        """Uzun biçim (tamsayı sütunlar int64): `gun`, skaler argümanlar (`arg0`, `arg1`,
        …; dizi argüman tabloda yer almaz), sonra çıktının satırları:

            1-B dizi              `indis`, `deger` (sıfırdan farklı öğeler; ilk dağıtım:
                                  indis = mağaza, deger = paket; replenishment: indis =
                                  hücre, deger = istek adedi)
            2-B dizi              `indis`, `sutun`, `deger` (sıfırdan farklı öğeler;
                                  markdown: indis = option, sutun = hat, deger = oran)
            sözlük                `indis`, `deger` (RPT: indis = option, deger = adet);
                                  bir değer SKU dizisiyse `alt` sütunu da (dizinin sırası,
                                  skaler değerde −1)
            dizi alanlı dataclass alan adları (`Transferler`: `kaynak, hedef, sku,
                                  adet`), satır başına

        Satır vermeyen çağrı (boş sözlük, sıfır dizi) tabloda yer almaz (`kayit`ta
        kalır). Kayıt yoksa yalnız `gun` sütunlu boş tablo."""
        parcalar = []
        for e in self.kayit:
            argler = {f"arg{i}": a for i, a in enumerate(e["args"]) if _skaler(a)}
            c = e["cikti"]
            if isinstance(c, np.ndarray) and c.ndim == 1:
                i = np.flatnonzero(c)
                sutunlar = {"indis": i, "deger": c[i]}
            elif isinstance(c, np.ndarray) and c.ndim == 2:
                i, j = np.nonzero(c)
                sutunlar = {"indis": i, "sutun": j, "deger": c[i, j]}
            elif isinstance(c, dict):
                sutunlar = _sozluk_sutunlari(c)
            elif dataclasses.is_dataclass(c) and not isinstance(c, type):
                sutunlar = {f.name: np.asarray(getattr(c, f.name)) for f in dataclasses.fields(c)}
            else:
                raise TypeError(f"kayıt tablosuna dönmeyen çıktı türü: {type(c).__name__}")
            n = len(next(iter(sutunlar.values()))) if sutunlar else 0
            if n == 0:
                continue
            parcalar.append(pd.DataFrame(
                {"gun": np.full(n, e["gun"]), **{a: np.full(n, v) for a, v in argler.items()},
                 **sutunlar}))
        if not parcalar:
            return pd.DataFrame({"gun": np.zeros(0, dtype=np.int64)})
        df = pd.concat(parcalar, ignore_index=True)
        if "alt" in df.columns and (df["alt"] == -1).all():
            df = df.drop(columns="alt")
        return df.astype({s: np.int64 for s in df.columns if pd.api.types.is_integer_dtype(df[s])})


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def _anahtarli(df: pd.DataFrame, C: int, pozitif: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """(gun, hucre, adet) → (artan tekil `gun*C + hucre`, adet toplamı);
    `pozitif` iade (negatif) satırlarını atar."""
    gun = df["gun"].to_numpy(dtype=np.int64)
    hucre = df["hucre"].to_numpy(dtype=np.int64)
    adet = df["adet"].to_numpy(dtype=np.int64)
    if pozitif:
        m = adet > 0
        gun, hucre, adet = gun[m], hucre[m], adet[m]
    anahtar = gun * C + hucre
    if len(anahtar) > 1 and not np.all(anahtar[1:] > anahtar[:-1]):
        anahtar, ters = np.unique(anahtar, return_inverse=True)
        adet = np.bincount(ters, weights=adet, minlength=len(anahtar)).astype(np.int64)
    return anahtar, adet


def _bul(sirali: np.ndarray, aranan: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`aranan`ın `sirali`daki konumu ve bulundu maskesi."""
    if not len(sirali):
        return np.zeros(len(aranan), dtype=np.int64), np.zeros(len(aranan), dtype=bool)
    i = np.minimum(np.searchsorted(sirali, aranan), len(sirali) - 1)
    return i, sirali[i] == aranan


def gercek_tablosu(w, ham: dict) -> pd.DataFrame:
    """Hücre-gün gizli gerçek: `tarih, magaza_id, urun_id` + `talep,
    kendi_satis, karsilanmayan, ikameye_giden, kalici_kayip` (int32).

    Satırlar: pencerede (2023-01-01 – 2025-12-31) talebi olan her hücre-gün;
    (tarih, magaza_id, urun_id) sıralı. Tanımlar hakemle aynı
    (`perakende_analitik.hakem.karsilanmayan_tablosu`; onun tablosu bunun
    `karsilanmayan > 0` alt kümesidir):

        kendi_satis    = ham `satis`'in pozitif satırı − alınan ikame
        karsilanmayan  = talep − kendi_satis
        kalici_kayip   = `gizli_kayip` (ikameden sonra, kaynak hücrede)
        ikameye_giden  = karsilanmayan − kalici_kayip

    Hücreye başka hücreden gelen ikame satışı (talebi olmayan hücre-günde
    de olabilir) = pozitif satış − kendi_satis; `satis`'te zaten vardır.
    Kimlik tutmazsa (kendi satış talebi aşar, kalıcı kayıp karşılanmayanı
    aşar ya da talepsiz hücre-günde) `RuntimeError`."""
    talep = np.asarray(ham["talep"])
    D, C = talep.shape
    bas, son = v4_tablolar.pencere()
    son = min(son, D - 1)
    talep_duz = talep.reshape(-1)

    s_anahtar, kendi = _anahtarli(ham["satis"], C, pozitif=True)
    i_anahtar, ikame = _anahtarli(ham["ikame_satis"], C)
    if len(i_anahtar):
        sira, var = _bul(s_anahtar, i_anahtar)
        if not var.all():
            raise RuntimeError("gercek: satışsız hücre-günde alınan ikame var")
        kendi[sira] -= ikame
    asan = (kendi > talep_duz[s_anahtar]) | (kendi < 0)
    if asan.any():
        raise RuntimeError(f"gercek: kendi_satis talebi aşıyor ya da negatif: {int(asan.sum())} hücre-gün")

    if bas > son:
        anahtar = np.zeros(0, dtype=np.int64)
    else:
        anahtar = np.flatnonzero(talep_duz[bas * C:(son + 1) * C] > 0) + bas * C
    t = talep_duz[anahtar].astype(np.int32)
    sira, var = _bul(s_anahtar, anahtar)
    k = np.where(var, kendi[sira] if len(kendi) else 0, 0).astype(np.int32)
    del sira, var
    kars = t - k

    g_anahtar, g_adet = _anahtarli(ham["gizli_kayip"], C)
    pen = (g_anahtar >= bas * C) & (g_anahtar < (son + 1) * C)
    g_anahtar, g_adet = g_anahtar[pen], g_adet[pen]
    kalici = np.zeros(len(anahtar), dtype=np.int32)
    sira, var = _bul(anahtar, g_anahtar)
    if not var.all():
        raise RuntimeError(f"gercek: kalici_kayip talepsiz hücre-günde: {int((~var).sum())}")
    kalici[sira] = g_adet
    if (kalici > kars).any():
        raise RuntimeError(f"gercek: kalici_kayip karsilanmayani aşıyor: {int((kalici > kars).sum())}")

    gun, hucre = anahtar // C, anahtar % C
    # Sıra: gün, sonra (magaza_id, urun_id) sözlük sırası (yayımlanan tablolar gibi)
    m = w.magazalar["magaza_id"].to_numpy().astype(str)[np.asarray(w.hucre_magaza)]
    u = w.urunler["urun_id"].to_numpy().astype(str)[np.asarray(w.hucre_sku)]
    rutbe = np.empty(C, dtype=np.int64)
    rutbe[np.lexsort((u, m))] = np.arange(C)
    p = np.argsort(gun * C + rutbe[hucre], kind="stable")
    ham_df = pd.DataFrame({
        "gun": gun[p], "hucre": hucre[p], "talep": t[p], "kendi_satis": k[p],
        "karsilanmayan": kars[p], "ikameye_giden": (kars - kalici)[p], "kalici_kayip": kalici[p],
    })
    df = v4_tablolar.hucre_tablosu(w, ham_df).reset_index(drop=True)
    for s in GERCEK_SUTUNLARI:
        df[s] = df[s].astype(np.int32)
    return df


# ---------------------------------------------------------------------------
# Önbellek anahtarı
# ---------------------------------------------------------------------------


def _kanonik(x):
    """JSON'a birebir dönen değer (numpy sayıları ve dizileri listeye);
    başka her tür `TypeError`: anahtar yalnız tanımlı biçimden kurulur."""
    if isinstance(x, dict):
        if not all(isinstance(k, str) for k in x):
            raise TypeError(f"parametre anahtarları str olmalı: {list(x)}")
        return {k: _kanonik(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_kanonik(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_kanonik(v) for v in x.tolist()]
    if isinstance(x, np.generic):
        return _kanonik(x.item())
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        if not np.isfinite(x):
            raise TypeError(f"sonlu olmayan parametre: {x}")
        return x
    raise TypeError(f"önbellek anahtarına girmeyen parametre türü: {type(x).__name__} ({x!r})")


def ice_aktarimlar(yol: Path, paket_adi: str) -> set[str]:
    """Dosyanın içe aktardığı tam modül adları (AST; fonksiyon içi dahil;
    göreli adlar `paket_adi` altına; `from m import a` hem `m` hem `m.a`)."""
    agac = ast.parse(Path(yol).read_text(encoding="utf-8"), filename=str(yol))
    adlar: set[str] = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            taban = ".".join([paket_adi] + ([d.module] if d.module else [])) if d.level else (d.module or "")
            adlar.add(taban)
            adlar |= {f"{taban}.{a.name}" for a in d.names}
    return adlar


def _paket_modulleri(adlar: set[str], paket_adi: str, kok: Path) -> set[str]:
    """`adlar` içinde `paket_adi.X` biçimindeki, `kok/X.py`'si olan X'ler."""
    on = paket_adi + "."
    return {a[len(on):].split(".")[0] for a in adlar if a.startswith(on)} & {
        y.stem for y in Path(kok).glob("*.py")}


def ortak_kapanisi(vaka_dosyalari, ortak_koku: Path, tohum=ORTAK_TOHUM) -> list[str]:
    """`tohum` + vaka dosyalarının içe aktardığı ortak modüllerden başlayıp
    ortak paket içi içe aktarmalarla ulaşılan modüller (sıralı)."""
    ortak_koku = Path(ortak_koku)
    var = {y.stem for y in ortak_koku.glob("*.py")}
    sira = {m for m in tohum if m in var}
    for y in vaka_dosyalari:
        sira |= _paket_modulleri(ice_aktarimlar(y, PAKET_ADI), ORTAK_PAKET, ortak_koku)
    gorulen: set[str] = set()
    while sira:
        m = sira.pop()
        gorulen.add(m)
        yeni = _paket_modulleri(ice_aktarimlar(ortak_koku / f"{m}.py", ORTAK_PAKET), ORTAK_PAKET, ortak_koku)
        sira |= yeni - gorulen
    return sorted(gorulen)


def kod_dosyalari() -> dict[str, Path]:
    """Kod özetine giren dosyalar: `<önek>/<göreli yol>` → yol (bkz. KOSU_MODULLERI)."""
    vaka_koku, ortak_koku, v4_koku = (Path(KOD_KOKLERI[a]) for a in (PAKET_ADI, "ortak", "v4"))
    vaka = [vaka_koku / f"{m}.py" for m in KOSU_MODULLERI if (vaka_koku / f"{m}.py").is_file()]
    dosyalar = {f"{PAKET_ADI}/{y.name}": y for y in vaka}
    for m in ortak_kapanisi(vaka, ortak_koku):
        dosyalar[f"ortak/{m}.py"] = ortak_koku / f"{m}.py"
    for y in v4_koku.glob("**/*.py"):
        if y.is_file() and "__pycache__" not in y.parts:
            dosyalar[f"v4/{y.relative_to(v4_koku).as_posix()}"] = y
    return dict(sorted(dosyalar.items()))


def _surum(paket: str) -> str | None:
    try:
        return importlib.metadata.version(paket)
    except importlib.metadata.PackageNotFoundError:
        return None


def kod_ozeti() -> str:
    """`kod_dosyalari`'nın göreli yol + içerik sha256'sı (satır sonları LF)."""
    ozet = hashlib.sha256()
    for ad, yol in kod_dosyalari().items():
        ozet.update(ad.encode("utf-8") + b"\0")
        ozet.update(yol.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return ozet.hexdigest()


def veri_parmak_izi() -> list:
    """v4 DuckDB dosyasının kimliği: ad, boyut, değişiklik zamanı (yoksa "yok")."""
    yol = Path(VERI_YOLU)
    if not yol.exists():
        return ["yok", yol.name]
    d = yol.stat()
    return [yol.name, d.st_size, d.st_mtime_ns]


def _tur_adi(p) -> str:
    """Politikanın türü: fonksiyonsa kendi tam adı, nesneyse sınıfınınki."""
    if inspect.isfunction(p) or inspect.ismethod(p) or inspect.isbuiltin(p):
        return f"{p.__module__}.{p.__qualname__}"
    return f"{type(p).__module__}.{type(p).__qualname__}"


POLITIKA_DERINLIGI = 5


def politika_kimligi(p, derinlik: int = POLITIKA_DERINLIGI) -> dict:
    """Politikanın kendi beyan ettiği kimliği: `parametreler()` çıktısı ve sardığı
    `temel` politikanın türü + kimliği (özyinelemeli). Beyanı olmayan politika `{}`."""
    k = {}
    f = getattr(p, "parametreler", None)
    if callable(f):
        k["parametreler"] = f()
    t = getattr(p, "temel", None)
    if t is not None:
        if derinlik <= 0:
            raise ValueError("politika_kimligi: `temel` zinciri çok derin")
        k["temel"] = {"tur": _tur_adi(t), **politika_kimligi(t, derinlik - 1)}
    return k


def anahtar_icerigi(
    *, ad: str, parametreler: dict, talep_tohumu: int | None, operasyon_tohumu: int,
    olcek: str, gun_sayisi: int | None, turler: dict, politikalar: dict | None = None,
) -> dict:
    """Koşuyu belirleyen her şey (bkz. modül belgesi); `meta`'ya da yazılır.
    `turler`: enjekte edilen yuva → politika türü; `politikalar`: yuva →
    `politika_kimligi` (boşsa içeriğe girmez)."""
    ek = {"politikalar": _kanonik(politikalar)} if politikalar else {}
    return {
        "ad": ad,
        "parametreler": _kanonik(parametreler),
        "turler": _kanonik(turler),
        **ek,
        "talep_tohumu": None if talep_tohumu is None else int(talep_tohumu),
        "operasyon_tohumu": int(operasyon_tohumu),
        "olcek": olcek,
        "gun_sayisi": None if gun_sayisi is None else int(gun_sayisi),
        "kod": kod_ozeti(),
        "veri": veri_parmak_izi(),
        "surumler": {p: _surum(p) for p in ("numpy", "pandas", "pyarrow", "lightgbm", "scikit-learn")},
    }


def _ozet(icerik: dict) -> str:
    metin = json.dumps(icerik, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def onbellek_anahtari(**alanlar) -> str:
    """`anahtar_icerigi`'nin sha256'sı (kanonik JSON)."""
    return _ozet(anahtar_icerigi(**alanlar))


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------


def _sec(df: pd.DataFrame, sutunlar, urunler) -> pd.DataFrame:
    if urunler is not None:
        df = df[df["urun_id"].astype(str).isin(set(map(str, urunler)))]
    if sutunlar is not None:
        df = df[list(sutunlar)]
    return df.reset_index(drop=True)


@dataclass
class Kosu:
    """Bir koşunun sonucu (bkz. modül belgesi)."""

    tablolar: dict
    gercek: pd.DataFrame
    meta: dict
    kayitlar: dict = field(default_factory=dict)
    onbellekten: bool = False

    def tablo(self, ad: str, sutunlar=None, urunler=None) -> pd.DataFrame:
        """Tablo `ad` (ya da "gercek"), yalnız `sutunlar`, yalnız `urun_id ∈ urunler`."""
        return _sec(self.gercek if ad == "gercek" else self.tablolar[ad], sutunlar, urunler)


class _TembelTablolar(Mapping):
    """`KosuKaydi.tablolar`: her erişimde tabloyu Parquet'ten okur (bellekte tutmaz)."""

    def __init__(self, kayit: "KosuKaydi"):
        self._k = kayit

    def __getitem__(self, ad):
        if ad not in self._k.meta["tablolar"]:
            raise KeyError(ad)
        return self._k.tablo(ad)

    def __iter__(self):
        return iter(self._k.meta["tablolar"])

    def __len__(self):
        return len(self._k.meta["tablolar"])


@dataclass
class KosuKaydi:
    """Önbellekteki bir koşu, tembel (`kos(..., tembel=True)`): `meta` ve
    `kayitlar` bellekte; tablolar ve gizli gerçek istendikçe diskten okunur
    (`tablo(ad, sutunlar, urunler)` yalnız gereken sütun ve SKU'ları okur). Bir TAM
    koşunun tabloları belleğe ~birkaç GB'tır; ızgara bunları aynı anda tutamaz.
    `yukle()` tam `Kosu`. Parquet'in bütünlüğü okunurken sınanır (tembel kayıt
    yalnız dosyaların varlığını sınar)."""

    dizin: Path
    meta: dict
    kayitlar: dict = field(default_factory=dict)
    onbellekten: bool = True

    def _yol(self, ad: str) -> Path:
        return self.dizin / ("gercek.parquet" if ad == "gercek" else f"tablo_{ad}.parquet")

    def tablo(self, ad: str, sutunlar=None, urunler=None) -> pd.DataFrame:
        """Tablo `ad` (ya da "gercek"), yalnız `sutunlar`, yalnız `urun_id ∈ urunler`
        (Parquet süzgeciyle; bütün tablo belleğe gelmez)."""
        if ad != "gercek" and ad not in self.meta["tablolar"]:
            raise KeyError(ad)
        suzgec = [("urun_id", "in", sorted(set(map(str, urunler))))] if urunler is not None else None
        df = pd.read_parquet(self._yol(ad), columns=None if sutunlar is None else list(sutunlar),
                             filters=suzgec)
        return df.reset_index(drop=True)

    @property
    def tablolar(self) -> Mapping:
        return _TembelTablolar(self)

    @property
    def gercek(self) -> pd.DataFrame:
        return self.tablo("gercek")

    def yukle(self) -> Kosu:
        return Kosu(tablolar={a: self.tablo(a) for a in self.meta["tablolar"]}, gercek=self.gercek,
                    meta=self.meta, kayitlar=dict(self.kayitlar), onbellekten=self.onbellekten)


def _tepe_bellek_gb() -> float | None:
    """Sürecin tepe çalışma kümesi (GB): Windows'ta `GetProcessMemoryInfo`,
    başka yerde `ru_maxrss`."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _Sayac(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (a, ctypes.c_size_t) for a in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

            s = _Sayac()
            s.cb = ctypes.sizeof(s)
            bilgi = ctypes.WinDLL("psapi").GetProcessMemoryInfo
            bilgi.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Sayac), wintypes.DWORD]
            # -1: GetCurrentProcess sözde tanıtıcısı (64 bit HANDLE olarak geçmeli)
            if not bilgi(wintypes.HANDLE(-1), ctypes.byref(s), s.cb):
                return None
            return round(s.PeakWorkingSetSize / 2**30, 2)
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 2)
    except Exception:  # noqa: BLE001 — yalnız bilgi amaçlı
        return None


def _dizin(onbellek: Path, ad: str, anahtar: str) -> Path:
    return Path(onbellek) / f"{ad}_{anahtar[:20]}"


def _oku(dizin: Path, anahtar: str) -> Kosu | None:
    meta_yolu = dizin / "meta.json"
    if not meta_yolu.exists():
        return None
    meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
    if meta.get("anahtar") != anahtar:
        return None
    try:
        tablolar = {ad: pd.read_parquet(dizin / f"tablo_{ad}.parquet") for ad in meta["tablolar"]}
        kayitlar = {ad: pd.read_parquet(dizin / f"kayit_{ad}.parquet") for ad in meta["kayitlar"]}
        gercek = pd.read_parquet(dizin / "gercek.parquet")
    except Exception as e:  # noqa: BLE001 — eksik ya da bozuk Parquet: kayıt silinir, yeniden koşulur
        warnings.warn(f"bozuk koşu kaydı siliniyor ({type(e).__name__}): {dizin}", stacklevel=3)
        shutil.rmtree(dizin, ignore_errors=True)
        return None
    return Kosu(tablolar=tablolar, gercek=gercek, meta=meta, kayitlar=kayitlar, onbellekten=True)


def _oku_tembel(dizin: Path, anahtar: str) -> KosuKaydi | None:
    """`_oku`'nun tembel hâli: meta ve anahtar tutmalı, bütün Parquet dosyaları
    bulunmalı (eksikse kayıt silinir, yeniden koşulur); yalnız kayıtlar okunur."""
    meta_yolu = dizin / "meta.json"
    if not meta_yolu.exists():
        return None
    meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
    if meta.get("anahtar") != anahtar:
        return None
    dosyalar = ([dizin / f"tablo_{a}.parquet" for a in meta["tablolar"]]
                + [dizin / f"kayit_{a}.parquet" for a in meta["kayitlar"]] + [dizin / "gercek.parquet"])
    try:
        if not all(d.is_file() for d in dosyalar):
            raise FileNotFoundError("eksik Parquet")
        kayitlar = {ad: pd.read_parquet(dizin / f"kayit_{ad}.parquet") for ad in meta["kayitlar"]}
    except Exception as e:  # noqa: BLE001 — eksik ya da bozuk: kayıt silinir, yeniden koşulur
        warnings.warn(f"eksik ya da bozuk koşu kaydı siliniyor ({type(e).__name__}): {dizin}",
                      stacklevel=3)
        shutil.rmtree(dizin, ignore_errors=True)
        return None
    return KosuKaydi(dizin=dizin, meta=meta, kayitlar=kayitlar, onbellekten=True)


_SUREC_BASI = time.time()


def _artiklari_sil(onbellek: Path) -> None:
    """Bu süreçten önce başlamış (yarıda kalmış) `.yaziliyor-*` dizinlerini siler."""
    for d in Path(onbellek).glob("*.yaziliyor-*"):
        try:
            if d.is_dir() and d.stat().st_mtime < _SUREC_BASI:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _yaz(dizin: Path, kosu: Kosu) -> None:
    """Geçici dizine yazar (`meta.json` en son), sonra tek `os.replace`."""
    dizin.parent.mkdir(parents=True, exist_ok=True)
    gecici = dizin.with_name(dizin.name + f".yaziliyor-{os.getpid()}")
    shutil.rmtree(gecici, ignore_errors=True)
    gecici.mkdir()
    for ad, df in kosu.tablolar.items():
        df.to_parquet(gecici / f"tablo_{ad}.parquet", index=False, compression="zstd")
    for ad, df in kosu.kayitlar.items():
        df.to_parquet(gecici / f"kayit_{ad}.parquet", index=False, compression="zstd")
    kosu.gercek.to_parquet(gecici / "gercek.parquet", index=False, compression="zstd")
    (gecici / "meta.json").write_text(
        json.dumps(kosu.meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if dizin.exists():                       # yarım (meta'sız) ya da bayat kayıt
        shutil.rmtree(dizin)
    os.replace(gecici, dizin)


def _gidis_donus(kosu: Kosu) -> Kosu:
    """Parquet gidiş-dönüşü bellekte: önbellekli ve önbelleksiz koşu aynı
    türleri döndürsün."""
    import io

    def gd(df):
        tampon = io.BytesIO()
        df.to_parquet(tampon, index=False)
        tampon.seek(0)
        return pd.read_parquet(tampon)

    return Kosu(tablolar={a: gd(d) for a, d in kosu.tablolar.items()}, gercek=gd(kosu.gercek),
                meta=kosu.meta, kayitlar={a: gd(d) for a, d in kosu.kayitlar.items()})


def kos(
    ilk_dagitim=None,
    *,
    replenishment=None,
    rpt=None,
    markdown=None,
    talep_tohumu: int | None = None,
    operasyon_tohumu: int = TOHUM,
    ad: str,
    parametreler: dict,
    onbellek: Path | None = KOSU_DIZINI,
    olcek: str = "tam",
    gun_sayisi: int | None = None,
    gecmis_kaydi: bool | None = None,
    tembel: bool = False,
) -> Kosu | KosuKaydi:
    """v4 motorunu verilen politikalarla (verilmeyen yuva Lumoda) yayımlanan dünyada
    koşar; önbellekte varsa koşmadan okur. `onbellek=None` önbelleği kapatır.
    `parametreler` politikanın davranışını belirleyen HER şeyi taşımalıdır (modül
    belgesi). `olcek`, `gun_sayisi` testler içindir. Verilmeyen `ilk_dagitim`, `rpt`,
    `markdown` Lumoda'nın kaydedicili kararlarıdır; enjekte edilen politika `baglan`
    taşıyorsa bu kaydediciler ona verilir. `gecmis_kaydi` None ise enjekte edilen
    politikaların `gecmis_gerekir`inden (çıktıyı değiştirmez, anahtara girmez). `tembel`
    (önbellek ister): tabloları belleğe almadan `KosuKaydi` döndürür (anahtara girmez)."""
    if not _AD_DESENI.match(ad):
        raise ValueError(f"koşu adı dosya adına uygun olmalı: {ad!r}")
    if tembel and onbellek is None:
        raise ValueError("tembel koşu kaydı önbellek ister (onbellek=None verildi)")
    if olcek not in OLCEKLER:
        raise ValueError(f"ölçek {sorted(OLCEKLER)}'den biri olmalı: {olcek!r}")
    verilen = {a: p for a, p in zip(YUVALAR, (ilk_dagitim, replenishment, rpt, markdown))
               if p is not None}
    turler = {a: _tur_adi(p) for a, p in verilen.items()}
    kimlikler = {a: k for a, p in verilen.items() if (k := politika_kimligi(p))}
    icerik = anahtar_icerigi(ad=ad, parametreler=parametreler, talep_tohumu=talep_tohumu,
                             operasyon_tohumu=operasyon_tohumu, olcek=olcek, gun_sayisi=gun_sayisi,
                             turler=turler, politikalar=kimlikler)
    anahtar = _ozet(icerik)
    if onbellek is not None:
        _artiklari_sil(onbellek)
        k = (_oku_tembel if tembel else _oku)(_dizin(onbellek, ad, anahtar), anahtar)
        if k is not None:
            return k

    t0 = time.perf_counter()
    w = dunya(olcek)
    kaydediciler = {a: Kaydedici(lumoda(a)) for a in KAYDEDILENLER if a not in verilen}
    for p in verilen.values():
        baglan = getattr(p, "baglan", None)
        if kaydediciler and callable(baglan):
            baglan(dict(kaydediciler))
    if gecmis_kaydi is None:
        gecmis_kaydi = any(getattr(p, "gecmis_gerekir", False) for p in verilen.values())
    politikalar = {**kaydediciler, **verilen}
    ham = simule_et(w, Politikalar(**politikalar), gun_sayisi=gun_sayisi,
                    operasyon_tohumu=operasyon_tohumu, kayit_talep=True,
                    talep_tohumu=talep_tohumu, gecmis_kaydi=bool(gecmis_kaydi))
    t1 = time.perf_counter()
    gercek = gercek_tablosu(w, ham)
    del ham["talep"]
    tablolar = v4_tablolar.hareket_tablolari(w, ham)
    del ham
    kayitlar = {}
    for a in YUVALAR:
        f = getattr(politikalar.get(a), "kayit_tablosu", None)
        if callable(f):
            kayitlar[a] = pd.DataFrame(f()).reset_index(drop=True)
    meta = {
        "anahtar": anahtar,
        **icerik,
        "motor_sn": round(t1 - t0, 1),
        "sure_sn": round(time.perf_counter() - t0, 1),
        "tepe_bellek_gb": _tepe_bellek_gb(),
        "tablolar": sorted(tablolar),
        "kayitlar": sorted(kayitlar),
        "satir_sayilari": {a: len(d) for a, d in sorted(tablolar.items())} | {"gercek": len(gercek)},
        "gercek_toplamlari": {s: int(gercek[s].to_numpy().sum(dtype=np.int64)) for s in GERCEK_SUTUNLARI},
    }
    kosu = Kosu(tablolar=tablolar, gercek=gercek, meta=meta, kayitlar=kayitlar)
    if onbellek is None:
        return _gidis_donus(kosu)
    dizin = _dizin(onbellek, ad, anahtar)
    _yaz(dizin, kosu)
    del kosu, tablolar, gercek
    if tembel:
        k = _oku_tembel(dizin, anahtar)
        if k is None:
            raise RuntimeError(f"koşu yazıldı ama okunamadı: {dizin}")
        k.onbellekten = False
        return k
    return _oku_zorunlu(dizin, anahtar)


def _oku_zorunlu(dizin: Path, anahtar: str) -> Kosu:
    """Yeni yazılan koşuyu okur (dönen koşu önbellekten okunanla aynı türlerde)."""
    k = _oku(dizin, anahtar)
    if k is None:
        raise RuntimeError(f"koşu yazıldı ama okunamadı: {dizin}")
    k.onbellekten = False
    return k


def yayimlanan_bicim(tablolar: dict, olcek: str) -> dict:
    """Temiz tablolara yayımlamadaki kirli kayıtları ekler: `uret.yayimla`'nın
    `kirlet` adımı (aynı `kirli` akışı, aynı dünya; `yayimla` ham çıktı
    aldığı için çağrılamaz, adım aynen tekrarlanır ve KÜÇÜK dünyada
    `yayimla`'yla eşitliği test edilir). Lumoda + varsayılan tohumlarla koşunun
    bu biçimi yayımlanan v4'tür."""
    w = dunya(olcek)
    return kirlet(akislar(w.tohum)["kirli"], dict(tablolar), w)


# ---------------------------------------------------------------------------
# Takvim (sabit takvim kolları) ve kırpma tablosu
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Takvim:
    """Bir koşunun RPT ve markdown kararları, gün gün (`takvim(kosu)`).

        rpt            gün → {option indisi: adet (int) | SKU adetleri (int64 dizisi)}
                       (yalnız en az bir RPT verilen günler)
        markdown       gün → [option_sayisi, 3] oran (normal / outlet / online hattı;
                       yalnız sıfırdan farklı bir oran taşıyan günler)
        option_sayisi  O

    Kayıtta olmayan gün boş sözlük / sıfır matristir (`rpt_gunu`, `markdown_gunu`;
    politika o gün çağrıldıysa kararı buydu). Pickle'lanır. Kimlik İÇERİKTEN: `kimlik`
    içerik özeti (SHA-256; sözlük sırası ve pickle baytı girmez), `sabitle()` onu bir kez
    hesaplayıp saklayan kopya. Yeniden oynatan politika kimliği `parametreler()`ine koyar."""

    rpt: dict
    markdown: dict
    option_sayisi: int
    _kimlik: str | None = None

    def __post_init__(self):
        for gun, m in self.markdown.items():
            if np.shape(m) != (self.option_sayisi, HAT_SAYISI):
                raise ValueError(f"markdown[{gun}] [{self.option_sayisi}, {HAT_SAYISI}] olmalı: "
                                 f"{np.shape(m)}")

    def rpt_gunu(self, gun: int) -> dict:
        """Günün RPT kararı (kopya; kayıtsız gün `{}`)."""
        return {o: (v.copy() if isinstance(v, np.ndarray) else v)
                for o, v in self.rpt.get(int(gun), {}).items()}

    def markdown_gunu(self, gun: int) -> np.ndarray:
        """Günün [O, 3] markdown oranı (kopya; kayıtsız gün sıfır)."""
        m = self.markdown.get(int(gun))
        return np.zeros((self.option_sayisi, HAT_SAYISI)) if m is None else np.array(m, dtype=float)

    def _ozet(self) -> str:
        h = hashlib.sha256()
        rpt = sorted((int(g), sorted((int(o), np.asarray(v).tolist()) for o, v in d.items()))
                     for g, d in self.rpt.items())
        h.update(json.dumps({"O": int(self.option_sayisi), "rpt": rpt}).encode("utf-8"))
        for g in sorted(self.markdown):
            h.update(b"\0" + str(int(g)).encode("ascii") + b"\0")
            h.update(np.ascontiguousarray(self.markdown[g], dtype="<f8").tobytes())
        return h.hexdigest()

    @property
    def kimlik(self) -> str:
        """İçerik özeti (SHA-256 hex): sabitlenmişse saklanan, değilse hesaplanan."""
        return self._kimlik if self._kimlik is not None else self._ozet()

    def sabitle(self) -> "Takvim":
        """Kimliği bir kez hesaplayıp saklayan kopya (zaten sabitse kendisi)."""
        if self._kimlik is not None:
            return self
        return dataclasses.replace(self, _kimlik=self._ozet())


def _kayit(kosu, ad: str) -> pd.DataFrame:
    if ad not in kosu.kayitlar:
        raise KeyError(f"koşuda `{ad}` kaydı yok (kayıtlar: {sorted(kosu.kayitlar)}); Lumoda'nın "
                       f"kaydedicili kararı ya da `kayit_tablosu()` taşıyan politika gerekir")
    return kosu.kayitlar[ad]


def takvim(kosu, w=None) -> Takvim:
    """Koşunun kayıtlı RPT ve markdown kararlarından `Takvim` (`kosu`: `Kosu` ya da
    `KosuKaydi`; `w` verilmezse koşunun ölçeğindeki dünya, yalnız option sayısı için).
    Kayıtlar `Kaydedici.kayit_tablosu` biçimindedir (Lumoda kaydedicisi ya da
    `Kaydedici(politika)`)."""
    w = dunya(kosu.meta["olcek"]) if w is None else w
    O = len(w.optionlar)
    r = _kayit(kosu, "rpt")
    rpt: dict[int, dict] = {}
    if len(r):
        alt = r["alt"].to_numpy() if "alt" in r.columns else np.full(len(r), -1)
        for (gun, o), parca in r.assign(_alt=alt).groupby(["gun", "indis"], sort=True):
            if len(parca) == 1 and int(parca["_alt"].iloc[0]) < 0:
                v = int(parca["deger"].iloc[0])
            else:
                v = parca.sort_values("_alt")["deger"].to_numpy(dtype=np.int64)
            rpt.setdefault(int(gun), {})[int(o)] = v
    m = _kayit(kosu, "markdown")
    markdown: dict[int, np.ndarray] = {}
    if len(m):
        for gun, parca in m.groupby("gun", sort=True):
            a = np.zeros((O, HAT_SAYISI))
            a[parca["indis"].to_numpy(), parca["sutun"].to_numpy()] = parca["deger"].to_numpy(dtype=float)
            markdown[int(gun)] = a
    return Takvim(rpt=rpt, markdown=markdown, option_sayisi=O)


KIRPMA_SUTUNLARI = ["option_id", "magaza_id", "istenen_paket", "giden_paket"]


def _istenen(kayit: pd.DataFrame, w, kiyas_o: np.ndarray) -> pd.DataFrame:
    k = kayit[np.isin(kayit["arg0"].to_numpy(), kiyas_o)]
    t = pd.DataFrame({"option_id": w.optionlar["option_id"].to_numpy().astype(str)[k["arg0"].to_numpy()],
                      "magaza_id": w.magazalar["magaza_id"].to_numpy().astype(str)[k["indis"].to_numpy()],
                      "istenen_paket": k["deger"].to_numpy(dtype=np.int64)})
    return t.groupby(["option_id", "magaza_id"], as_index=False)["istenen_paket"].sum()


def _giden(kosu, w, kiyas: set) -> pd.DataFrame:
    """`sevkiyat`'ın ilk dağıtım satırlarından (option, mağaza) başına paket sayısı."""
    s = kosu.tablo("sevkiyat", sutunlar=["tarih", "hedef", "urun_id", "adet", "tip", "paket_id"])
    s = s[s["tip"].astype(str) == "ilk_dagitim"]
    u = w.urunler.set_index(w.urunler["urun_id"].astype(str))
    urun = s["urun_id"].astype(str)
    s = pd.DataFrame({
        "tarih": s["tarih"].to_numpy(),
        "option_id": urun.map(u["option_id"].astype(str)).to_numpy(),
        "magaza_id": s["hedef"].astype(str).to_numpy(),
        "paket_id": s["paket_id"].astype(str).to_numpy(),
        "beden_sira": urun.map(u["beden_sira"]).to_numpy(dtype=np.int64),
        "adet": s["adet"].to_numpy(dtype=np.int64),
    })
    s = s[s["option_id"].isin(kiyas)]
    p = kosu.tablo("paket", sutunlar=["paket_id", "beden_sira", "adet"])
    p = pd.DataFrame({"paket_id": p["paket_id"].astype(str).to_numpy(),
                      "beden_sira": p["beden_sira"].to_numpy(dtype=np.int64),
                      "icerik": p["adet"].to_numpy(dtype=np.int64)})
    s = s.merge(p, on=["paket_id", "beden_sira"], how="left")
    ic = s["icerik"].fillna(0).to_numpy(dtype=np.int64)
    if (ic <= 0).any() or (s["adet"].to_numpy() % np.maximum(ic, 1) != 0).any():
        raise RuntimeError("ilk dağıtım sevki paket içeriğinin katı değil "
                           "(paket ↔ sevkiyat tutmuyor)")
    s["paket"] = s["adet"].to_numpy() // ic
    sevk = s.groupby(["option_id", "magaza_id", "tarih"])["paket"].agg(["min", "max"])
    if (sevk["min"] != sevk["max"]).any():
        raise RuntimeError("ilk dağıtım sevkinin bedenleri farklı paket sayısı veriyor: "
                           f"{int((sevk['min'] != sevk['max']).sum())} sevk")
    return sevk["min"].groupby(level=["option_id", "magaza_id"]).sum().rename("giden_paket").reset_index()


def kirpma_tablosu(kosu, w=None) -> pd.DataFrame:
    """İlk dağıtım kaydındaki paket kararı ↔ motorun gönderdiği (`sevkiyat`, tip
    `ilk_dagitim`): `option_id, magaza_id, istenen_paket, giden_paket` (paketler int64),
    yalnız ikisinin farklı olduğu (option, mağaza) satırları, (option_id, magaza_id) sıralı.

    Motor paketleri aday maskesiyle (varışta kapalı, kapanış kararlı mağaza) ve depodaki
    SKU'lara sığdırarak (`paketleri_sigdir`) kırpar; sevki sonraki günlere erteleyebilir.
    Giden paket sayısı = sevk edilen beden adedi ÷ paketin (`paket_id`, `paket` tablosu)
    o bedendeki içeriği; bir sevkin bedenleri aynı sayıyı vermezse `RuntimeError`. Kıyas
    yalnız sevkleri bütünüyle tabloda olan option'larda yapılır: karar günü pencere
    başında ya da sonra (pencere öncesi sevk yayımlanmaz) ve max(lansman, karar günü)
    pencerenin ve koşunun son gününde ya da önce (sevk bundan geç olmaz). `kosu`: `Kosu`
    ya da `KosuKaydi`; `w` verilmezse koşunun ölçeğindeki dünya."""
    w = dunya(kosu.meta["olcek"]) if w is None else w
    kayit = _kayit(kosu, "ilk_dagitim")
    tarih = pd.DatetimeIndex(pd.to_datetime(w.takvim["tarih"]))
    D = min(int(kosu.meta.get("gun_sayisi") or w.gun_sayisi), len(tarih))
    bas, son = pd.Timestamp(v4_sabitler.BASLANGIC), min(pd.Timestamp(v4_sabitler.BITIS), tarih[D - 1])
    if len(kayit):
        karar = kayit.groupby("arg0")["gun"].agg(["min", "max"])
        o = karar.index.to_numpy(dtype=np.int64)
        lansman = pd.DatetimeIndex(pd.to_datetime(w.optionlar["lansman_tarihi"]))[o]
        tam = (tarih[karar["min"].to_numpy()] >= bas) & (
            np.maximum(lansman, tarih[karar["max"].to_numpy()]) <= son)
        kiyas_o = o[np.asarray(tam)]
    else:
        kiyas_o = np.zeros(0, dtype=np.int64)
    istenen = _istenen(kayit, w, kiyas_o) if len(kayit) else pd.DataFrame(
        {"option_id": [], "magaza_id": [], "istenen_paket": []})
    giden = _giden(kosu, w, set(w.optionlar["option_id"].to_numpy().astype(str)[kiyas_o]))
    t = istenen.merge(giden, on=["option_id", "magaza_id"], how="outer")
    t[["istenen_paket", "giden_paket"]] = t[["istenen_paket", "giden_paket"]].fillna(0)
    t = t[t["istenen_paket"] != t["giden_paket"]]
    t = t.astype({"option_id": str, "magaza_id": str, "istenen_paket": np.int64, "giden_paket": np.int64})
    return t.sort_values(["option_id", "magaza_id"])[KIRPMA_SUTUNLARI].reset_index(drop=True)
