"""Kollar (spec §3.4–3.5): her kol motorun `markdown(g) -> [O, 3]` yuvasıdır (normal / outlet / online).

Karar modülüdür: `perakende_veri`'yi, hakemi, simülasyonu ve ölçütleri içe aktarmaz; dünyanın gizli
alanlarını okumaz (AST kilidi, `tests/test_sizinti.py`). Kahinin gerçek girdileri (`KahinGirdisi`)
yapıcı argümanı olarak dizi hâlinde gelir; onları gizli gerçekten ölçen `hakem`'dir.

**Sarmalayıcı** (`Sarmalayici`, bütün kolların tabanı). Her çağrıda önce `temel(g)` (Lumoda'nın
markdown'ı) çağrılır: test dışı option'ların her sütunu ve test option'larının outlet sütunu onundur.
Test option'larının normal ve online sütunu ise baştan kolun kendi iç durumudur (`oran`; başta 0):
Lumoda'nın oranı oraya hiç düşmez, kol bu yüzden kendi oran geçmişini tam bilir (`oran_gecmisi`,
Ruling R12). Oran geri alınmaz (yeni oran = max(eski, karar)) ve merdivene üstten sığdırılır
(`merdivene`). Sıra:

1. **Taban** (`taban` > 0 ise; her çağrıda, pazartesi olmasa da): `indirim_gun ≤ gün < cikis_gun` olan
   option'ın oranı en az `taban`. Motor sezon indirimini takvim olayı sayar ve politikayı pazartesi
   olmayan indirim gününde de çağırır; o çağrıda yalnız bu taban uygulanır.
2. **Karar** (yalnız pazartesi): penceredeki (`pencere günü ≤ gün < cikis_gun`) test option'ları için
   `karar(g, oo, oran) -> (yeni_oran [n], ek | None)`; `ek` kayıt sütunlarını (`tahmini_satis`,
   `satilabilir`, `beklenen_kalan`; [n] diziler) taşır. Pencere `kaynak.karar_penceresi`: serbest =
   `max(indirim − 56, lansman + 42)`'nin pazartesisi (R9), takvim = `indirim_gun` (yuvarlamasız).

Kayıt (`kayit_tablosu`): her (pazartesi, penceredeki test option'ı) bir satır; `option` dünya option
indisi, `oran` o haftanın kararı (taban ve sığlaşmazlık uygulanmış). Bir kol nesnesi tek koşu içindir:
gün geriye giderse `ValueError`.

**Kollar.**

- `Tekduze(temel, test_idx, oran)`: takvim penceresi, taban = `oran`; karar oranı değiştirmez.
- `Kural(temel, test_idx, alfa)`: serbest pencere. Kapsama = satılabilir stok (fiziksel raf + yolda +
  option'ın SKU'larının depo stoğu + açık siparişlerin adedi) ÷ son `HIZ_GUN` günün stoklu gün hızı
  (bugünkü fiyatta gerçekleşen: hücre başına stoklu günlerin satışı ÷ stoklu gün sayısı, option'ın
  hücreleri üstünde toplam; ONL dahil, outlet akışı hariç). Kapsama ÷ kalan gün (`cikis − gün`) > α ise
  bir kademe derinleşir (ilk indirim de böyle başlar; haftada en fazla bir), değilse yerinde (Ruling R6:
  tek eşik). Hız 0 ve stok varsa kapsama sonsuzdur; stok 0 ise derinleşmez. Kayıt: tahmini satış =
  `min(X, hız × kalan gün)` (kuralın kendi bakışı: bugünkü hızla).
- `Optimizasyon(temel, test_idx, ogrenilen, kip, eps)`: her pazartesi penceredeki her option için
  ufuk = karar gününden `cikis_gun`'e (hariç), 7 günlük haftalar (son hafta eksik olabilir; talebi o
  haftanın günlerinin toplamıdır). `Tahminci` (ε̂ tablosu `eps`'e göre `eps_kampanya` ya da
  `eps_markdown`; kolun oran geçmişiyle) taban talebi, satılabilir stoğu, çarpanı ve etkin oranı (k = 0'da
  beklenen işlem indirimi, R11) ve iade payını verir; kalıntı `Ogrenilen.kalinti`; `model.coz`un ilk
  haftasının basamağı uygulanır. Kip (spec §3.4): `serbest` serbest pencere, tabansız; `takvim` pencere
  indirim günü, taban %30; `erken_yok` pencere indirim günü, tabansız; `taban` serbest pencere, indirim
  gününden %30. Tabanlı kipte ilk günü indirim gününden önce olmayan haftalarda yalnız ≥ taban basamaklar
  izinlidir (`izinli`); indirim gününü içine alan haftayı taban, indirim günü çağrısında kendisi uygular.
- `Kahin(temel, test_idx, ogrenilen, girdi)`: `Optimizasyon(kip="serbest", eps="kampanya")`'nın gerçek
  girdili hâli (spec §0/12). Taban talep girdinin `taban[gün, hücre]`'sinden (fiyat çarpanından önceki
  beklenen günlük talep), esneklik girdinin hücre ε'si: DP'nin hafta × basamak fiyat çarpanı hücre-gün
  çarpanlarının `(1 − max(r, kampanya))^(−ε_hücre)` gerçek taban talep ağırlıklı ortalamasıdır
  (`Tahminci.carpan`'a [N] ε; kampanya oranları gibi). ε'ler önce ortalanmaz: çarpan ε'de dışbükey
  olduğu için ortalama ε'nin çarpanı derin basamakta talep artışını eksik okurdu. Satılabilir stok,
  kampanya, iade, kalıntı ve işlem
  indirimi `Optimizasyon`'daki gibi (açık bilgi ve öğrenilenler; gerçek talep yalnız depo payını belirler).

`parametreler()` koşu önbelleği anahtarına giren JSON-kanonik sözlüktür: davranışı değiştiren her şey
(kol, pencere, taban, kip, ε kaynağı, α, tekdüze oran, `Ogrenilen.kimlik()`, kahin girdisi kimliği, test
option'ları, stok kovası).
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from markdown import kaynak, model, sabitler
from markdown.ogrenme import Ogrenilen
from markdown.sabitler import HIZ_GUN, KADEMELER, STOK_KOVA, TAKVIM_TABANI
from markdown.tahmin import Tahminci

KAYIT_SUTUNLARI = ("gun", "option", "oran", "tahmini_satis", "satilabilir", "beklenen_kalan")
_EK_SUTUNLAR = KAYIT_SUTUNLARI[3:]
KIPLER = ("serbest", "takvim", "erken_yok", "taban")
_KIP_PENCERE = {"serbest": "serbest", "takvim": "takvim", "erken_yok": "takvim", "taban": "serbest"}
_KIP_TABAN = {"serbest": 0.0, "takvim": TAKVIM_TABANI, "erken_yok": 0.0, "taban": TAKVIM_TABANI}
EPS_KAYNAKLARI = ("kampanya", "markdown")
_K = np.asarray(KADEMELER, dtype=float)
_HAFTA_GUNU_0 = pd.Timestamp(sabitler.GUN_SIFIRI).weekday()
_PAY = 1e-9

Karar = Callable[[object, np.ndarray, np.ndarray], tuple[np.ndarray, dict | None]]


def merdivene(oran) -> np.ndarray:
    """Her oranı merdivenin üstündeki ya da eşit en yakın basamağına sığdırır (%70'in üstü %70)."""
    oran = np.asarray(oran, dtype=float)
    return _K[np.minimum(np.searchsorted(_K, oran - _PAY, side="left"), len(_K) - 1)]


def pazartesi_mi(gun: int) -> bool:
    return (int(gun) + _HAFTA_GUNU_0) % 7 == 0


def izinli(ufuk: np.ndarray, indirim_gun: int, taban: float) -> np.ndarray:
    """[T, K] DP izin maskesi: ilk günü `indirim_gun`'den önce olmayan haftalarda yalnız ≥ `taban`
    basamaklar (taban 0'sa hepsi)."""
    bas = np.asarray(ufuk, dtype=np.int64)[::7]
    maske = np.ones((len(bas), len(_K)), dtype=bool)
    if taban > 0:
        maske[bas >= indirim_gun] = _K >= taban - _PAY
    return maske


# ---------------------------------------------------------------------------
# Sarmalayıcı
# ---------------------------------------------------------------------------


class Sarmalayici:
    """Bütün kolların tabanı (modül docstring'i). `karar` verilmezse alt sınıfın `_karar`'ı."""

    ad = "sarmalayici"

    def __init__(self, temel, test_idx, karar: Karar | None = None, *,
                 pencere: Literal["serbest", "takvim"] = "serbest", taban: float = 0.0):
        if pencere not in kaynak.KOL_TIPLERI:
            raise ValueError(f"pencere {kaynak.KOL_TIPLERI}'den biri olmalı: {pencere!r}")
        self.temel = temel
        self.test_idx = np.unique(np.asarray(test_idx, dtype=np.int64))
        self.karar = karar if karar is not None else self._karar
        self.pencere = pencere
        self.taban = float(taban)
        self.oran = np.zeros(len(self.test_idx))
        self._konum = {int(o): i for i, o in enumerate(self.test_idx)}
        self._gecmis: list[list[tuple[int, float]]] = [[] for _ in self.test_idx]
        self._kayit: list[pd.DataFrame] = []
        self._son_gun: int | None = None
        self._dunya_id = None
        self._hucre_dunya = None

    def _karar(self, g, oo: np.ndarray, oran: np.ndarray) -> tuple[np.ndarray, dict | None]:
        return oran, None

    # ------------------------------------------------------------- çağrı

    def _hazirla(self, w) -> None:
        if self._dunya_id == id(w):
            return
        opt = w.optionlar
        self._pencere = kaynak.karar_penceresi(opt, self.test_idx, self.pencere)
        self._indirim = opt["indirim_gun"].to_numpy(dtype=np.int64)[self.test_idx]
        self._cikis = opt["cikis_gun"].to_numpy(dtype=np.int64)[self.test_idx]
        self._liste = opt["liste_fiyati"].to_numpy(dtype=float)[self.test_idx]
        self._dunya_id = id(w)

    def __call__(self, g) -> np.ndarray:
        d = int(g.gun)
        if self._son_gun is not None and d < self._son_gun:
            raise ValueError(f"gün geri gitti ({self._son_gun} -> {d}): her koşu için yeni kol kurun")
        self._son_gun = d
        yeni = np.array(self.temel(g), dtype=float, copy=True)
        self._hazirla(g.dunya)
        oran = self.oran.copy()
        if self.taban > 0:
            tb = (d >= self._indirim) & (d < self._cikis)
            oran = np.where(tb, np.maximum(oran, merdivene(self.taban)), oran)
        if pazartesi_mi(d):
            i = np.flatnonzero((d >= self._pencere) & (d < self._cikis))
            if len(i):
                karar, ek = self.karar(g, self.test_idx[i], oran[i].copy())
                oran[i] = np.maximum(oran[i], merdivene(karar))
                self._kaydet(d, i, oran[i], ek)
        for j in np.flatnonzero(oran != self.oran):
            self._gecmis[j].append((d, float(oran[j])))
        self.oran = oran
        yeni[self.test_idx, 0] = oran
        yeni[self.test_idx, 2] = oran
        return yeni

    def _kaydet(self, d: int, i: np.ndarray, oran: np.ndarray, ek: dict | None) -> None:
        satir = {"gun": np.full(len(i), d, dtype=np.int64), "option": self.test_idx[i].copy(),
                 "oran": oran.astype(float)}
        for s in _EK_SUTUNLAR:
            satir[s] = np.full(len(i), np.nan) if ek is None else np.asarray(ek[s], dtype=float)
        self._kayit.append(pd.DataFrame(satir))

    # ------------------------------------------------------------- çıktılar

    def oran_gecmisi(self, o: int) -> tuple[np.ndarray, np.ndarray]:
        """Test option'ı `o`'nun (dünya indisi) normal/online oran değişimleri: (günler, oranlar); oran
        o günden itibaren geçerli, ilk değişimden önce 0 (Ruling R12; `Tahminci(oran_gecmisi=)`)."""
        k = self._gecmis[self._konum[int(o)]]
        return (np.array([a for a, _ in k], dtype=np.int64), np.array([b for _, b in k], dtype=float))

    def kayit_tablosu(self) -> pd.DataFrame:
        if not self._kayit:
            bos = {s: pd.Series(dtype=np.int64 if s in ("gun", "option") else float) for s in KAYIT_SUTUNLARI}
            return pd.DataFrame(bos)
        return pd.concat(self._kayit, ignore_index=True)[list(KAYIT_SUTUNLARI)]

    def parametreler(self) -> dict:
        return {"kol": self.ad, "pencere": self.pencere, "taban": float(self.taban),
                "test_optionlari": [int(o) for o in self.test_idx]}

    # ------------------------------------------------------------- yardımcılar

    def _hucre_yapisi(self, w):
        """Test option'larının hücreleri (outlet akışı hariç; ONL dahil): (hücre [n], option konumu [n],
        online [n]) ve SKU'ları (sku [m], option konumu [m]); dünya başına bir kez."""
        if self._hucre_dunya == id(w):
            return self._hucre_onbellek
        ho = np.asarray(w.hucre_option, dtype=np.int64)
        c = np.flatnonzero(np.isin(ho, self.test_idx) & ~np.asarray(w.hucre_outlet_akisi, dtype=bool))
        konum = np.searchsorted(self.test_idx, ho[c])
        so = np.asarray(w.sku_option, dtype=np.int64)
        s = np.flatnonzero(np.isin(so, self.test_idx))
        self._hucre_onbellek = (c, konum, np.asarray(w.hucre_online, dtype=bool)[c], s,
                                np.searchsorted(self.test_idx, so[s]))
        self._hucre_dunya = id(w)
        return self._hucre_onbellek


# ---------------------------------------------------------------------------
# Tekdüze ve kural
# ---------------------------------------------------------------------------


class Tekduze(Sarmalayici):
    """Herkese aynı oran, indirim gününden çıkışa (düz indirim taban çizgisi)."""

    ad = "tekduze"

    def __init__(self, temel, test_idx, oran: float):
        if not np.isclose(_K, oran).any() or oran <= 0:
            raise ValueError(f"tekdüze oran merdivenin sıfırdan büyük bir basamağı olmalı: {oran}")
        super().__init__(temel, test_idx, pencere="takvim", taban=float(oran))

    def _karar(self, g, oo, oran):
        n = len(oo)
        return oran, {"tahmini_satis": np.full(n, np.nan), "satilabilir": _satilabilir(self, g)[
            np.searchsorted(self.test_idx, oo)], "beklenen_kalan": np.full(n, np.nan)}

    def parametreler(self) -> dict:
        return {**super().parametreler(), "oran": float(self.taban)}


def _satilabilir(kol: Sarmalayici, g) -> np.ndarray:
    """[len(test_idx)] fiziksel raf + yolda + SKU depo stoğu + açık sipariş adedi."""
    c, konum, online, s, s_konum = kol._hucre_yapisi(g.dunya)
    n = len(kol.test_idx)
    raf = np.where(online, 0.0, np.maximum(np.asarray(g.magaza_stok, float)[c], 0)
                   + np.maximum(np.asarray(g.yolda, float)[c], 0))
    X = np.bincount(konum, raf, minlength=n)
    X += np.bincount(s_konum, np.maximum(np.asarray(g.depo, float)[s], 0), minlength=n)
    for sip in g.acik_siparisler:
        j = kol._konum.get(int(sip["option"]))
        if j is not None:
            X[j] += float(np.sum(sip["adetler"]))
    return X


class Kural(Sarmalayici):
    """Kapsama kuralı (modül docstring'i; spec §3.4, 3. yazı)."""

    ad = "kural"

    def __init__(self, temel, test_idx, alfa: float):
        if not alfa > 0:
            raise ValueError(f"alfa pozitif olmalı: {alfa}")
        super().__init__(temel, test_idx, pencere="serbest")
        self.alfa = float(alfa)

    def hiz(self, g) -> np.ndarray:
        """[len(test_idx)] günlük stoklu gün hızı (son `HIZ_GUN` gün, bugünkü fiyatta)."""
        c, konum, _on, _s, _sk = self._hucre_yapisi(g.dunya)
        d = int(g.gun)
        bas = max(0, d - HIZ_GUN)
        st = np.asarray(g.stoklu_gecmisi[bas:d, c], dtype=bool)
        satis = np.where(st, np.asarray(g.satis_gecmisi[bas:d, c], dtype=float), 0.0).sum(0)
        gun = st.sum(0)
        r = np.divide(satis, gun, out=np.zeros(len(c)), where=gun > 0)
        return np.bincount(konum, r, minlength=len(self.test_idx))

    def _karar(self, g, oo, oran):
        j = np.searchsorted(self.test_idx, oo)
        X = _satilabilir(self, g)[j]
        v = self.hiz(g)[j]
        kalan = (self._cikis[j] - int(g.gun)).astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            kapsama = np.where(v > 0, X / v, np.where(X > 0, np.inf, 0.0))
        derin = kapsama > self.alfa * kalan
        sonraki = _K[np.minimum(np.searchsorted(_K, oran + _PAY, side="left"), len(_K) - 1)]
        tahmini = np.minimum(X, v * kalan)
        return np.where(derin, sonraki, oran), {"tahmini_satis": tahmini, "satilabilir": X,
                                                "beklenen_kalan": X - tahmini}

    def parametreler(self) -> dict:
        return {**super().parametreler(), "alfa": self.alfa, "hiz_gun": HIZ_GUN}


# ---------------------------------------------------------------------------
# Optimizasyon ve kahin
# ---------------------------------------------------------------------------


class Optimizasyon(Sarmalayici):
    """Tahmin + haftalık DP + kayan ufuk (modül docstring'i; spec §3.2–3.4)."""

    ad = "optimizasyon"

    def __init__(self, temel, test_idx, ogrenilen: Ogrenilen,
                 kip: Literal["serbest", "takvim", "erken_yok", "taban"],
                 eps: Literal["kampanya", "markdown"]):
        if kip not in KIPLER:
            raise ValueError(f"kip {KIPLER}'den biri olmalı: {kip!r}")
        if eps not in EPS_KAYNAKLARI:
            raise ValueError(f"eps {EPS_KAYNAKLARI}'den biri olmalı: {eps!r}")
        super().__init__(temel, test_idx, pencere=_KIP_PENCERE[kip], taban=_KIP_TABAN[kip])
        self.ogrenilen = ogrenilen
        self.kip = kip
        self.eps = eps
        tablo = ogrenilen.eps_kampanya if eps == "kampanya" else ogrenilen.eps_markdown
        self.tahminci = Tahminci(ogrenilen, self.test_idx, eps=tablo, oran_gecmisi=self.oran_gecmisi)

    def _talep(self, g, o: int, ufuk: np.ndarray):
        """(hücreler [N], d [T, N], ε (tek sayı ya da [N]), hücre-gün ağırlığı [U, N] ya da None)."""
        hucre, d = self.tahminci.taban(g, o, ufuk)
        return hucre, d, self.tahminci.option_eps(g, o), None

    def _karar(self, g, oo, oran):
        t = self.tahminci
        n = len(oo)
        yeni = oran.copy()
        ek = {s: np.zeros(n) for s in _EK_SUTUNLAR}
        gun = int(g.gun)
        for i, o in enumerate(oo):
            j = self._konum[int(o)]
            ufuk = np.arange(gun, self._cikis[j])
            hucre, d, eps, agirlik = self._talep(g, int(o), ufuk)
            X0, pay = t.satilabilir(g, int(o), hucre, d)
            ek["satilabilir"][i] = X0
            if X0 <= 0:
                continue
            carpan, etkin = t.carpan(g, int(o), ufuk, eps, agirlik=agirlik)
            z = model.coz(d, pay, X0, float(self._liste[j]), carpan, etkin,
                          model.merdiven_indisi(float(oran[i])),
                          izinli(ufuk, int(self._indirim[j]), self.taban),
                          t.iade_payi(g, int(o), hucre, d), float(self.ogrenilen.kalinti))
            yeni[i] = _K[z.kademe[0]]
            ek["tahmini_satis"][i] = float(z.beklenen_satis.sum())
            ek["beklenen_kalan"][i] = z.beklenen_kalan
        return yeni, ek

    def parametreler(self) -> dict:
        return {**super().parametreler(), "kip": self.kip, "eps": self.eps,
                "ogrenilen": self.ogrenilen.kimlik(), "kova": STOK_KOVA}


@dataclass(frozen=True, eq=False)
class KahinGirdisi:
    """Kahinin gerçek girdileri (`hakem` gizli gerçekten ölçer; politika yalnız bu dizileri görür).

    hucre [C] int64: dünya hücre indisleri (test option'larının hücreleri); gunler [U] int64: artan gün
    indisleri (ufuk günleri); taban [U, C]: hücre-gün beklenen taban talep (fiyat çarpanından önce);
    eps [C]: hücre esnekliği. Diziler kopyalanır ve salt okunur yapılır."""

    hucre: np.ndarray
    gunler: np.ndarray
    taban: np.ndarray
    eps: np.ndarray

    def __post_init__(self):
        diziler = {"hucre": np.asarray(self.hucre, dtype=np.int64),
                   "gunler": np.asarray(self.gunler, dtype=np.int64),
                   "taban": np.asarray(self.taban, dtype=float), "eps": np.asarray(self.eps, dtype=float)}
        C, U = len(diziler["hucre"]), len(diziler["gunler"])
        if diziler["hucre"].ndim != 1 or diziler["gunler"].ndim != 1 or diziler["taban"].shape != (U, C) \
                or diziler["eps"].shape != (C,):
            raise ValueError(f"KahinGirdisi boyutları tutarsız: hucre {diziler['hucre'].shape}, gunler "
                             f"{diziler['gunler'].shape}, taban {diziler['taban'].shape}, eps "
                             f"{diziler['eps'].shape}")
        if len(np.unique(diziler["hucre"])) != C or (np.diff(diziler["gunler"]) <= 0).any():
            raise ValueError("KahinGirdisi: hücreler tekil, günler artan olmalı")
        for ad, x in diziler.items():
            x = x.copy()
            x.flags.writeable = False
            object.__setattr__(self, ad, x)
        sira = np.argsort(diziler["hucre"], kind="stable")
        object.__setattr__(self, "_sira", sira)
        object.__setattr__(self, "_sirali", diziler["hucre"][sira])

    def kimlik(self) -> str:
        """İçerik özeti (sha256, ilk 16 hane): dizilerin türü, boyu ve baytları."""
        h = hashlib.sha256()
        for ad in ("hucre", "gunler", "taban", "eps"):
            x = np.ascontiguousarray(getattr(self, ad))
            h.update(f"{ad}:{x.dtype.str}:{x.shape}\0".encode())
            h.update(x.tobytes())
        return h.hexdigest()[:16]

    def sutunlar(self, hucre: np.ndarray) -> np.ndarray:
        """Dünya hücrelerinin `taban`/`eps` sütun indisleri; eksik hücre `ValueError`."""
        i = np.minimum(np.searchsorted(self._sirali, hucre), len(self._sirali) - 1)
        if len(self._sirali) == 0 or (self._sirali[i] != hucre).any():
            raise ValueError("kahin girdisinde option'ın bazı hücreleri yok")
        return self._sira[i]

    def satirlar(self, gunler: np.ndarray) -> np.ndarray:
        """Günlerin `taban` satır indisleri; eksik gün `ValueError`."""
        i = np.minimum(np.searchsorted(self.gunler, gunler), max(len(self.gunler) - 1, 0))
        if len(self.gunler) == 0 or (self.gunler[i] != gunler).any():
            raise ValueError("kahin girdisinde ufkun bazı günleri yok")
        return i


class Kahin(Optimizasyon):
    """`Optimizasyon(kip="serbest", eps="kampanya")`'nın gerçek talep ve esneklikli hâli (modül
    docstring'i; spec §0/12)."""

    ad = "kahin"

    def __init__(self, temel, test_idx, ogrenilen: Ogrenilen, girdi: KahinGirdisi):
        super().__init__(temel, test_idx, ogrenilen, kip="serbest", eps="kampanya")
        self.girdi = girdi

    def _talep(self, g, o: int, ufuk: np.ndarray):
        hucre = self.tahminci.hucreler(g, o)
        gunluk = self.girdi.taban[np.ix_(self.girdi.satirlar(ufuk), self.girdi.sutunlar(hucre))]
        eps = self.girdi.eps[self.girdi.sutunlar(hucre)]          # [N] hücre ε'si (ortalanmaz)
        d = np.add.reduceat(gunluk, np.arange(0, len(ufuk), 7), axis=0) if len(ufuk) else gunluk[:0]
        return hucre, d, eps, gunluk

    def parametreler(self) -> dict:
        return {**super().parametreler(), "kahin_girdisi": self.girdi.kimlik()}
