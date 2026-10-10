"""Üretecin tek kapısı: v4 dünyası, politika enjeksiyonu, koşu önbelleği,
gizli gerçek.

Vakada `perakende_veri`'yi (v4 üreteci) yalnız bu modül içe aktarır.
Karar modülleri (`kaynak`, `egri`, `sansur`, `aday`, `miktar`, `dagitim`,
`politika`, `hikaye`, …) bu modülü de içe aktarmaz (`tests/test_sizinti.py`
kilitler); onlara yalnız `politika_gorunumu`'nün döndürdüğü veri geçirilir.
Gizli gerçek (`Kosu.gercek`) yalnız `olcutler`, `kahin` ve rapora gider.

    w   = dunya()                                   # TAM v4 dünyası (süreç içi önbellek)
    pb  = politika_gorunumu(w)                      # Lumoda'nın gördüğü sabitler
    k   = kos(rpt=benim_rpt, ad="oneri", parametreler={...})
    k.tablolar["satis"], k.gercek, k.meta

KOŞU. `kos` `Politikalar(rpt=..., replenishment=...)` ile (verilmeyen alan
Lumoda) `simule_et(..., kayit_talep=True, talep_tohumu, operasyon_tohumu)`
koşar ve döndürür:

    tablolar  yayımlanan 18 tablonun TEMİZ hâli (`hareket_tablolari`: aynı
              şema, aynı pencere, kirli kayıt yok). Kollar arası farkın
              yalnız kararlardan gelmesi için kirletilmez; yayımlanan
              biçim `yayimlanan_bicim(tablolar)` (aynı kirli kayıtlar).
    gercek    hücre-gün gizli gerçek (`gercek_tablosu`; hakem tanımı)
    kayitlar  enjekte edilen politikanın `kayit_tablosu()` DataFrame'i
              (varsa): önbellekten okunan koşuda politika çalışmadığı
              için yan etkisi buradan gelir
    meta      anahtar bileşenleri, süre, tepe bellek, satır sayıları

ÖNBELLEK. `onbellek` dizininde (varsayılan `cikti/kosular/`) koşu başına
bir alt dizin `<ad>_<anahtar[:20]>`: tablolar ve gizli gerçek Parquet,
`meta.json` en son. Dizin önce `.yaziliyor` adıyla yazılır, sonra tek
`os.replace` ile yerine konur; `meta.json`'u olmayan ya da anahtarı tutmayan
dizin okunmaz; meta'sı tam ama Parquet'i eksik/bozuk kayıt silinip yeniden
koşulur; bu süreçten eski `.yaziliyor-*` artıkları silinir. Anahtar
(`onbellek_anahtari`): `ad`, `parametreler` (kanonik JSON), politika türleri
(sınıf / fonksiyon tam adı), iki tohum, ölçek, gün sayısı, kod özeti (yalnız
koşuyu etkileyen kaynaklar: `KOSU_MODULLERI`, onların ortak paket kapanışı,
`perakende_veri/v4/**/*.py`; satır sonları LF), v4 DuckDB dosyasının parmak
izi (ad, boyut, değişiklik zamanı), numpy / pandas / pyarrow / lightgbm /
scikit-learn sürümü.

GEÇMİŞ KAYDI. Politikalardan biri `gecmis_gerekir = True` taşıyorsa (motor içi
karar anı kestiricisi, `politika.Oneri`) motor `gecmis_kaydi=True` ile koşar
(Ruling R6: `Gorunum` satış öncesi stok, fiyat ve fotoğraf geçmişini taşır).
Kayıt yalnız okur, çıktılar birebir aynıdır (veri testi); anahtara girmez.

LUMODA. Karar modülleri üreteci içe aktarmadığı için Lumoda'nın bugünkü kuralları
kollara ve dağıtım kurallarına argüman olarak verilir: `lumoda("rpt")`,
`lumoda("replenishment")` (v4 `LumodaRPT`, `lumoda_replenishment`).

POLİTİKANIN KENDİ KİMLİĞİ. Enjekte edilen her politikanın `parametreler()`
yöntemi varsa çıktısı, `temel` (sardığı politika; ör. kolun Lumoda kuralı,
dağıtım kuralının bugünkü replenishment'ı) varsa onun türü ve kimliği
(özyinelemeli) anahtara kendiliğinden girer (`politika_kimligi`; içerikte
`politikalar`, yalnız boş değilse: Lumoda'nın varsayılan koşusunun anahtarı
değişmez). Kollar (`politika.KOLLAR`, `kahin.Kahin`) ve dağıtım kuralları
(`dagitim.KURALLAR`) öğrenilmiş verinin özetini `parametreler()`'de taşır.

**Politikalar Python nesneleridir; anahtar onları `ad` + `parametreler`
ile tanır.** Çağıran, politikanın davranışını değiştiren HER parametreyi
(eşik, model türü, dağıtım kuralı, öğrenmenin dayandığı sezonlar, eğitim
verisinin kaynağı olan koşunun anahtarı, …) `parametreler`'e koymalıdır;
aksi halde farklı davranan iki politika aynı önbellek kaydını okur. Kod
değişikliği özetle, veri değişikliği parmak iziyle yakalanır; politikaya
elle verilen veri (ör. eğitilmiş model) yakalanmaz: onu belirleyen
parametreler anahtara girmelidir. Kod özeti çağrı anındaki dosyalardan
alınır: süreç açıkken değiştirilen kod (yüklenmiş modül eski) yakalanmaz,
süreç yeniden başlatılmalıdır.

Koşular sıralıdır: önbellek eşzamanlı yazıma karşı korunmaz (aynı anahtarı
iki süreç yazarsa ikincisi birincinin dizinini bulur ve onu okur). Bir TAM
koşu ~4 dk, ~6 GB.
"""

import ast
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
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import perakende_veri.v4 as _v4_paketi
from perakende_analitik import kaynak as ortak
from perakende_veri.v4 import sabitler
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.dunya import akislar, dunya_kur
from perakende_veri.v4.kirlet import kirlet
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar, lumoda_politikalari

from .bilgi import PolitikaBilgisi

TOHUM = sabitler.TOHUM
PAKET_KOKU = Path(__file__).resolve().parent                    # vakalar/rpt/rpt
KOSU_DIZINI = PAKET_KOKU.parent / "cikti" / "kosular"
VERI_YOLU = ortak.VARSAYILAN_YOL
OLCEKLER = {"tam": Olcek.TAM, "kucuk": Olcek.KUCUK}

# Kod özetine giren kaynaklar (yalnız koşuyu etkileyenler; Ruling R3):
#   rpt    KOSU_MODULLERI (henüz olmayan dosya atlanır). Ölçüm ve anlatı
#          (KOSU_DISI: olcutler, hikaye*, yollar, hazirla; vaka kökü rapor*.py, testler)
#          koşuyu değiştirmez: bir ölçümün sonucu politikaya girerse (ör. SS24'te
#          seçilen dağıtım kuralı) o sonuç `parametreler`'e girer. rpt/'deki her
#          modül iki listeden birindedir (tests/test_motor.py).
#   ortak  perakende_analitik'te ORTAK_TOHUM + rpt kaynaklarının içe aktardığı
#          ortak modüllerin içe aktarma kapanışı (AST; hakem gibi ulaşılmayan
#          modüller girmez)
#   v4     perakende_veri/v4/**/*.py
KOSU_MODULLERI = (
    "motor", "bilgi", "politika", "dagitim", "kahin", "aday", "miktar", "sansur", "egri",
    "kaynak", "anlik", "oyun",
)
KOSU_DISI = ("olcutler", "hikaye", "hikaye_sec", "yollar", "hazirla")
ORTAK_TOHUM = ("kaynak", "stok", "ozellikler", "carpanlar", "talep", "hazirlik")
KOD_KOKLERI = {
    "rpt": PAKET_KOKU,
    "ortak": Path(ortak.__file__).resolve().parent,                 # perakende_analitik/
    "v4": Path(_v4_paketi.__file__).resolve().parent,
}
ORTAK_PAKET = "perakende_analitik"

GERCEK_SUTUNLARI = ("talep", "kendi_satis", "karsilanmayan", "ikameye_giden", "kalici_kayip")
_AD_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


# ---------------------------------------------------------------------------
# Dünya ve politikanın gördüğü
# ---------------------------------------------------------------------------


@functools.cache
def dunya(olcek: str = "tam"):
    """v4 dünyası (`dunya_kur`, varsayılan tohum; süreç içi önbellek, TAM ~20 sn)."""
    return dunya_kur(OLCEKLER[olcek])


def lumoda(ad: str):
    """Lumoda'nın v4 politikası (`Politikalar` alan adı: "rpt", "replenishment", …)."""
    p = lumoda_politikalari()
    if ad not in p:
        raise ValueError(f"Lumoda politikası {sorted(p)}'den biri olmalı: {ad!r}")
    return p[ad]


def _gun_tarihi(gun) -> np.ndarray:
    bas = np.datetime64(sabitler.ISINMA_BASLANGIC, "D")
    return (bas + np.asarray(gun, dtype=np.int64).astype("timedelta64[D]")).astype("datetime64[ns]")


def politika_gorunumu(w) -> PolitikaBilgisi:
    """Bkz. `PolitikaBilgisi`. Sezon planı politikanın erişimcisi
    `ileri_plan_option`'dan; haftalık kanal ayrımı onun topladığı plan
    özetinden (`plan_ozeti.gunluk`, gün × kanal × option)."""
    opt = w.optionlar.reset_index(drop=True)
    gunluk = np.asarray(w.plan_ozeti.gunluk)                     # [N, 2, O]
    N, _, O = gunluk.shape
    kum = np.concatenate([np.zeros((1, 2, O)), np.cumsum(gunluk, axis=0)])   # [N+1, 2, O]

    lansman = opt["lansman_gun"].to_numpy(dtype=np.int64)
    indirim = opt["indirim_gun"].to_numpy(dtype=np.int64)
    cikis = opt["cikis_gun"].to_numpy(dtype=np.int64)
    sezonluk = opt["sezonluk"].to_numpy(dtype=bool)
    plan_sezon = np.zeros(O)
    plan_cikis = np.zeros(O)
    for i in np.flatnonzero(sezonluk):   # politikanın erişimcisiyle (ilk alımın hesabıyla aynı)
        plan_sezon[i] = w.ileri_plan_option(int(lansman[i]), int(indirim[i] - lansman[i]))[i]
        plan_cikis[i] = w.ileri_plan_option(int(lansman[i]), int(cikis[i] - lansman[i]))[i]

    ted = w.tedarikciler[["tedarikci_id", "ad", "ulke", "mense", "ilk_siparis_hafta",
                          "rpt_hafta", "moq_option", "uzmanlik"]].rename(columns={"ad": "tedarikci_adi"})
    alanlar = ["option_id", "model_kodu", "marka", "cinsiyet", "ust_kategori", "alt_kategori",
               "line", "sezon_kodu", "dalga", "fiyat_segmenti", "alis_fiyati", "liste_fiyati",
               "lansman_tarihi", "cikis_tarihi", "tedarikci_id", "sezonluk"]
    o = opt[alanlar].copy()
    o["indirim_baslangic"] = np.where(sezonluk, _gun_tarihi(np.where(sezonluk, indirim, 0)),
                                      np.datetime64("NaT", "ns"))
    o["plan_sezon"] = plan_sezon
    o["plan_cikis"] = plan_cikis
    o["ilk_alim"] = np.asarray(w.ilk_alim, dtype=np.int64)
    o = o.merge(ted, on="tedarikci_id", how="left", validate="many_to_one")
    assert o["rpt_hafta"].notna().all() and list(o["option_id"]) == list(opt["option_id"])

    parca = []
    for i in np.flatnonzero(sezonluk):
        n_hafta = int(-(-(cikis[i] - lansman[i]) // 7))
        bas = lansman[i] + 7 * np.arange(n_hafta)
        p = kum[np.clip(np.minimum(bas + 7, cikis[i]), 0, N), :, i] - kum[np.clip(bas, 0, N), :, i]
        parca.append(pd.DataFrame({
            "option_id": opt.at[i, "option_id"], "h": np.arange(n_hafta),
            "plan_magaza": p[:, 0], "plan_online": p[:, 1], "plan": p.sum(axis=1),
        }))
    plan_hafta = pd.concat(parca, ignore_index=True) if parca else pd.DataFrame(
        columns=["option_id", "h", "plan_magaza", "plan_online", "plan"])
    return PolitikaBilgisi(
        optionlar=o, plan_hafta=plan_hafta,
        plan_tablolari={k: v.copy() for k, v in w.plan_tablolari.items()},
    )


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


def ortak_kapanisi(rpt_dosyalari, ortak_koku: Path, tohum=ORTAK_TOHUM) -> list[str]:
    """`tohum` + rpt dosyalarının içe aktardığı ortak modüllerden başlayıp
    ortak paket içi içe aktarmalarla ulaşılan modüller (sıralı)."""
    ortak_koku = Path(ortak_koku)
    var = {y.stem for y in ortak_koku.glob("*.py")}
    sira = {m for m in tohum if m in var}
    for y in rpt_dosyalari:
        sira |= _paket_modulleri(ice_aktarimlar(y, "rpt"), ORTAK_PAKET, ortak_koku)
    gorulen: set[str] = set()
    while sira:
        m = sira.pop()
        gorulen.add(m)
        yeni = _paket_modulleri(ice_aktarimlar(ortak_koku / f"{m}.py", ORTAK_PAKET), ORTAK_PAKET, ortak_koku)
        sira |= yeni - gorulen
    return sorted(gorulen)


def kod_dosyalari() -> dict[str, Path]:
    """Kod özetine giren dosyalar: `<önek>/<göreli yol>` → yol (bkz. KOSU_MODULLERI)."""
    rpt_koku, ortak_koku, v4_koku = (Path(KOD_KOKLERI[a]) for a in ("rpt", "ortak", "v4"))
    rpt = [rpt_koku / f"{m}.py" for m in KOSU_MODULLERI if (rpt_koku / f"{m}.py").is_file()]
    dosyalar = {f"rpt/{y.name}": y for y in rpt}
    for m in ortak_kapanisi(rpt, ortak_koku):
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
    `politikalar`: kanca → `politika_kimligi` (boşsa içeriğe girmez)."""
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


@dataclass
class Kosu:
    """Bir koşunun sonucu (bkz. modül belgesi)."""

    tablolar: dict
    gercek: pd.DataFrame
    meta: dict
    kayitlar: dict = field(default_factory=dict)
    onbellekten: bool = False


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
    rpt=None,
    replenishment=None,
    *,
    talep_tohumu: int | None = None,
    operasyon_tohumu: int = TOHUM,
    ad: str,
    parametreler: dict,
    onbellek: Path | None = KOSU_DIZINI,
    olcek: str = "tam",
    gun_sayisi: int | None = None,
    gecmis_kaydi: bool | None = None,
) -> Kosu:
    """v4 motorunu verilen RPT / replenishment politikasıyla koşar (verilmeyen
    Lumoda); önbellekte varsa koşmadan okur. `onbellek=None` önbelleği
    kapatır. `parametreler` politikanın davranışını belirleyen HER şeyi
    taşımalıdır (modül belgesi). `olcek`, `gun_sayisi` testler içindir.
    `gecmis_kaydi` None ise politikaların `gecmis_gerekir`inden (çıktıyı
    değiştirmez, anahtara girmez)."""
    if not _AD_DESENI.match(ad):
        raise ValueError(f"koşu adı dosya adına uygun olmalı: {ad!r}")
    if olcek not in OLCEKLER:
        raise ValueError(f"ölçek {sorted(OLCEKLER)}'den biri olmalı: {olcek!r}")
    politikalar = {"rpt": rpt, "replenishment": replenishment}
    turler = {a: _tur_adi(p) for a, p in politikalar.items() if p is not None}
    kimlikler = {a: k for a, p in politikalar.items() if p is not None and (k := politika_kimligi(p))}
    icerik = anahtar_icerigi(ad=ad, parametreler=parametreler, talep_tohumu=talep_tohumu,
                             operasyon_tohumu=operasyon_tohumu, olcek=olcek, gun_sayisi=gun_sayisi,
                             turler=turler, politikalar=kimlikler)
    anahtar = _ozet(icerik)
    if onbellek is not None:
        _artiklari_sil(onbellek)
        k = _oku(_dizin(onbellek, ad, anahtar), anahtar)
        if k is not None:
            return k

    t0 = time.perf_counter()
    w = dunya(olcek)
    pol = Politikalar(**{a: p for a, p in politikalar.items() if p is not None})
    if gecmis_kaydi is None:
        gecmis_kaydi = any(getattr(p, "gecmis_gerekir", False) for p in politikalar.values())
    ham = simule_et(w, pol, gun_sayisi=gun_sayisi, operasyon_tohumu=operasyon_tohumu,
                    kayit_talep=True, talep_tohumu=talep_tohumu, gecmis_kaydi=bool(gecmis_kaydi))
    t1 = time.perf_counter()
    gercek = gercek_tablosu(w, ham)
    del ham["talep"]
    tablolar = v4_tablolar.hareket_tablolari(w, ham)
    del ham
    kayitlar = {}
    for a, p in politikalar.items():
        f = getattr(p, "kayit_tablosu", None)
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
    `yayimla`'yla eşitliği test edilir). Lumoda + varsayılan tohumlarla
    koşunun bu biçimi yayımlanan v4'tür."""
    w = dunya(olcek)
    return kirlet(akislar(w.tohum)["kirli"], dict(tablolar), w)
