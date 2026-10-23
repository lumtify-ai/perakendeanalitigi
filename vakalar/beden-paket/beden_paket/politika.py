"""Paket politikası: dünya kopyasına eklenen paket satırları, mağazanın desenine göre paket seçimi
ve Lumoda'nın giden paket sayısını gönderen ilk dağıtım (spec §0/5–7, §0/11, §0/14, §4.2).

    df, harita = paket_ekle(w.paketler, desenler)          # koşucu: dataclasses.replace(w, paketler=df)
    PaketSecimi(atama, harita, desenler=..., optionlar=...)  # motorun paket_secimi(g, o) -> [M] indis
    GidenIlkDagitim(ns, temel, optionlar)                   # motorun ilk_dagitim(g, o) -> [M] paket

Kural: karar modülüdür. `perakende_veri`'yi, hakemi ve ölçüm modüllerini içe aktarmaz (AST kilidi,
`tests/test_sizinti.py`). Politikalar `(g, o)` alan düz çağrılabilirlerdir ve yalnız `g.dunya`'nın
açık alanlarını okur (`magazalar.magaza_id`, `optionlar.option_id`, `optionlar.beden_seti`).
Motorun `Politikalar`'ı ve Lumoda'nın kuralı (`temel`) koşucuda (`kosucu`) kurulur.

**Paket indisi.** Motor paket içeriğini koşu başında bir kez `paket_tablosu(w.paketler)` ile okur:
indis `paket_id`'nin tabloda ilk görülme sırasıdır (`sevkiyat.paket_id` kategorileri de bu sırayla
kurulur), bir beden setinin standart paketi o setin tablodaki ilk paketidir (`setdefault`).
`paket_indisleri` bu kuralın kopyasıdır (v4'ü içe aktarmamak için; test v4'le birebir sınar).
`paket_ekle` yeni satırları standart paketlerin **ardına** ekler: standart indisler değişmez,
Lumoda'nın kuralları (`lumoda_paket_secimi`, `lumoda_ilk_dagitim`'in paket adedi) kopyada da
standart paketi görür.

**Desenler.** `desenler` [K, 5] tamsayı: beden sırası 1..5 adetleri (7'li ya da 12'li; aynı
kopyada birlikte durabilir). Her beş bedenli beden setine (standart paketi beden sırası 1..5
taşıyan set; aksesuarın tek bedenli 6'lısı değil) her desen için bir paket eklenir, beş satır
(sıfır adetli beden de satırdır; motor sıfır adedi göndermez). Kimlik `PKD{d:02d}-{standart
paket_id}` (d desenin satır indisi; K > 100'de basamak genişler): set ve desen indisinden kararlı.
Desen içeriği bütün setlerde aynıdır (spec §0/14: mağazanın deseni bütün option'larda aynı).

`harita`: (beden_seti, d) → paket indisi; (beden_seti, `STANDART`) her set için standart paket.

**Paket seçimi** (`PaketSecimi`). Option `optionlar`'da (oyun option'ları) ve seti desen almışsa
mağaza `atama[magaza_id]` deseninin o setteki paketini alır; atama dışı mağaza, oyun dışı option
ve beş bedenli olmayan set standart paketi alır. Atamasız seçim Lumoda'nın seçimidir (doğrulama
kolu).

**İlk dağıtım** (`GidenIlkDagitim`). Oyun option'ında [M] = `ns[(option_id, magaza_id)]` (yoksa 0):
Lumoda'nın aynı option'da mağazaya **giden** paket sayısı (motor sonrası; spec §0/11). Oyun dışı
option'da `temel(g, o)` aynen (Lumoda'nın kuralı). Paket tasarımı depo kısıtına uyduğu için motor
bu kollarda kırpmaz; kırparsa kırpma koşucunun ölçütünde görünür.

Kimlik (`parametreler()`, önbellek anahtarına girer): JSON-kanonik listeler. `PaketSecimi`
desenleri, atamayı, haritayı ve option kümesini taşır; `GidenIlkDagitim` ns'in içerik özetini
(SHA-256), toplamını ve option kümesini.
"""

import hashlib
import json
from collections.abc import Mapping

import numpy as np
import pandas as pd

from beden_paket import sabitler

STANDART = -1                   # harita: (beden_seti, STANDART) → setin standart paketi
ONEK = "PKD"                    # eklenen paketlerin kimlik öneki (yayımlananlar PKT..)
SUTUNLAR = ("paket_id", "beden_seti", "beden_sira", "adet")


def _ozet(nesne) -> str:
    return hashlib.sha256(json.dumps(nesne, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def desen_dizisi(desenler) -> np.ndarray:
    """[K, 5] int64; beşli olmayan, negatif ya da boş desen `ValueError`."""
    a = np.asarray(desenler)
    if a.size == 0:
        return np.zeros((0, sabitler.BEDEN_SAYISI), dtype=np.int64)
    if a.ndim != 2 or a.shape[1] != sabitler.BEDEN_SAYISI:
        raise ValueError(f"desenler [K, {sabitler.BEDEN_SAYISI}] olmalı: {a.shape}")
    if not np.issubdtype(a.dtype, np.integer) and not np.array_equal(a, np.round(a)):
        raise ValueError("desenler tamsayı olmalı")
    a = a.astype(np.int64)
    if (a < 0).any() or (a.sum(axis=1) <= 0).any():
        raise ValueError("desen adetleri negatif olamaz, desen boş olamaz")
    return a


def paket_indisleri(paketler: pd.DataFrame) -> tuple[np.ndarray, dict[str, int]]:
    """(`paket_idleri` [P] ilk görülme sırasıyla, beden seti → standart paket indisi): motorun
    `paket_tablosu` kuralı (modül notu)."""
    ids = paketler["paket_id"].drop_duplicates().to_numpy()
    idx = {p: i for i, p in enumerate(ids)}
    standart: dict[str, int] = {}
    for bs, pid in zip(paketler["beden_seti"], paketler["paket_id"]):
        standart.setdefault(bs, idx[pid])
    return ids, standart


def _bes_bedenli_setler(paketler: pd.DataFrame, ids, standart: dict) -> list[str]:
    """Standart paketi beden sırası 1..5'i taşıyan setler (tablodaki sırayla)."""
    beklenen = set(range(1, sabitler.BEDEN_SAYISI + 1))
    sonuc = []
    for bs, i in standart.items():
        sira = set(paketler.loc[paketler["paket_id"] == ids[i], "beden_sira"].astype(int))
        if sira == beklenen:
            sonuc.append(bs)
    return sonuc


def paket_ekle(paketler: pd.DataFrame, desenler) -> tuple[pd.DataFrame, dict[tuple, int]]:
    """Her beş bedenli sete desen başına bir paket, standart paketlerin ardına (modül notu).
    Dönüş: (yeni tablo; sütunları ve türleri `paketler`'inkiyle aynı, ilk satırlar aynen;
    `harita`). Tablo zaten eklenmiş paket taşıyorsa `ValueError`."""
    if tuple(paketler.columns) != SUTUNLAR:
        raise ValueError(f"paket sütunları {SUTUNLAR} olmalı: {tuple(paketler.columns)}")
    if paketler["paket_id"].astype(str).str.startswith(ONEK).any():
        raise ValueError(f"tabloda zaten {ONEK} paketleri var (paket_ekle iki kez çağrılmış)")
    D = desen_dizisi(desenler)
    ids, standart = paket_indisleri(paketler)
    genislik = max(2, len(str(max(len(D) - 1, 0))))
    satirlar = []
    yeni_id = {}
    for bs in _bes_bedenli_setler(paketler, ids, standart):
        for d, desen in enumerate(D):
            pid = f"{ONEK}{d:0{genislik}d}-{ids[standart[bs]]}"
            yeni_id[(bs, d)] = pid
            satirlar += [(pid, bs, b, int(a)) for b, a in enumerate(desen, start=1)]
    yeni = pd.DataFrame(satirlar, columns=list(SUTUNLAR))
    df = pd.concat([paketler, yeni], ignore_index=True).astype(paketler.dtypes.to_dict())
    ids2, standart2 = paket_indisleri(df)
    if standart2 != standart:                     # ekleme sonrası standart değişmemeli
        raise RuntimeError("paket_ekle: standart paket indisleri değişti")
    konum = {p: i for i, p in enumerate(ids2)}
    harita = {(bs, STANDART): i for bs, i in standart.items()}
    harita |= {k: konum[pid] for k, pid in yeni_id.items()}
    return df, harita


def _sozluk(atama) -> dict[str, int]:
    if isinstance(atama, pd.Series):
        atama = atama.to_dict()
    return {str(m): int(d) for m, d in dict(atama or {}).items()}


def _harita(harita: Mapping) -> dict[tuple, int]:
    return {(str(bs), int(d)): int(i) for (bs, d), i in harita.items()}


class PaketSecimi:
    """Motorun `paket_secimi(g, o) -> [M]` yuvası (modül notu).

    atama      magaza_id → desen indisi (`desenler` satırı; pd.Series ya da sözlük)
    harita     `paket_ekle`'nin haritası
    desenler   [K, 5] (kimlik ve denetim için; içerik dünya kopyasındadır)
    optionlar  desenin uygulandığı option_id'ler (oyun option'ları)"""

    def __init__(self, atama, harita: Mapping, *, desenler, optionlar):
        self.atama = _sozluk(atama)
        self.harita = _harita(harita)
        self.desenler = desen_dizisi(desenler)
        self.optionlar = frozenset(str(o) for o in np.asarray(list(optionlar), dtype=object))
        K = len(self.desenler)
        kotu = {m: d for m, d in self.atama.items() if not 0 <= d < K}
        if kotu:
            raise ValueError(f"atamada desen indisi [0, {K}) dışında: {dict(list(kotu.items())[:5])}")
        setler = {bs for bs, d in self.harita if d != STANDART}
        eksik = [(bs, d) for bs in setler for d in range(K) if (bs, d) not in self.harita]
        if eksik:
            raise ValueError(f"haritada desen paketi eksik: {eksik[:5]}")

    def __call__(self, g, o: int) -> np.ndarray:
        w = g.dunya
        bs = str(w.optionlar.at[o, "beden_seti"])
        std = self.harita[(bs, STANDART)]
        M = len(w.magazalar)
        if (str(w.optionlar.at[o, "option_id"]) not in self.optionlar or not self.atama
                or (bs, 0) not in self.harita):
            return np.full(M, std, dtype=np.int64)
        d = w.magazalar["magaza_id"].astype(str).map(self.atama).fillna(STANDART).to_numpy(dtype=np.int64)
        return np.array([std if x == STANDART else self.harita[(bs, int(x))] for x in d], dtype=np.int64)

    def parametreler(self) -> dict:
        return {"desenler": self.desenler.tolist(),
                "atama": sorted([m, d] for m, d in self.atama.items()),
                "harita": sorted([bs, d, i] for (bs, d), i in self.harita.items()),
                "optionlar": sorted(self.optionlar)}


class GidenIlkDagitim:
    """Motorun `ilk_dagitim(g, o) -> [M]` yuvası: oyun option'ında Lumoda'nın giden paket sayısı,
    ötekinde `temel` (modül notu).

    ns         (option_id, magaza_id) → paket (≥ 0); oyun dışı option'ların satırları yok sayılır
    temel      Lumoda'nın ilk dağıtım kuralı (koşucudan; bu modül v4'ü içe aktarmaz)
    optionlar  ns'in uygulandığı option_id'ler"""

    def __init__(self, ns: Mapping, temel, optionlar):
        self.temel = temel
        self.optionlar = frozenset(str(o) for o in np.asarray(list(optionlar), dtype=object))
        tablo: dict[str, dict[str, int]] = {}
        for (o, m), n in ns.items():
            n = int(n)
            if n < 0:
                raise ValueError(f"ns negatif olamaz: {(o, m)} → {n}")
            if str(o) in self.optionlar and n > 0:
                tablo.setdefault(str(o), {})[str(m)] = n
        self._ns = tablo

    def __call__(self, g, o: int) -> np.ndarray:
        w = g.dunya
        oid = str(w.optionlar.at[o, "option_id"])
        if oid not in self.optionlar:
            return self.temel(g, o)
        d = self._ns.get(oid, {})
        return w.magazalar["magaza_id"].astype(str).map(d).fillna(0).to_numpy(dtype=np.int64)

    def parametreler(self) -> dict:
        satir = sorted([o, m, n] for o, d in self._ns.items() for m, n in d.items())
        return {"ns_ozeti": _ozet(satir), "satir": len(satir), "toplam": int(sum(s[2] for s in satir)),
                "optionlar": sorted(self.optionlar)}
