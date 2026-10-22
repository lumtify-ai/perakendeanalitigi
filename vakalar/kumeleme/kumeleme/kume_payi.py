"""Küme payı: İlk Sevkiyat'ın benzer ürün endeksinin (`vakalar/allocation/allocation/benzer.py`) mağaza
yerine **küme** düzeyinde hesaplanmış hâli (spec §4.4). İlk Sevkiyat'ın küme kollarına giden pay sözlüğü
buradan çıkar (`KumeEndeksi.paylar`; allocation `politika.KahinKol`'un `erken_talep`'i).

Kural: bu bir karar modülüdür; `perakende_veri`'yi, gizli gerçeği ve ölçüm modüllerini (`hakem`,
`olcutler`, `oyun`) içe aktarmaz (AST kilidi, `tests/test_sizinti.py`). `allocation` paketini de içe
aktarmaz (vakalar arası bağımlılık tek yönlüdür: allocation'ın koşu dışı `oyun.py`'si bu modülü
çağırır). Bu yüzden girdisi bir DataFrame'dir:

**Öğrenme tablosu** (`tablo`): İlk Sevkiyat `ogrenme.ogrenme_tablosu`'nun satırları (geçmiş
sezonların her (fiziksel mağaza, option) çiftinin sansür düzeltmeli ilk 6 hafta talebi), şu sütunlarla:

    option        geçmiş option'ın kimliği (allocation'da `option_id` dizgesi); `paylar`'da karar
                  verilen option'la karşılaştırılır (aynıysa sızıntı: hata)
    magaza_id     mağaza kimliği (allocation tablosundaki `magaza` indisinin dünyadaki kimliği)
    stoklu_gun    pencerede en az bir bedenin stoklu olduğu gün sayısı (> 0 gözlemdir)
    talep         sansür düzeltmeli erken talep (NaN = gözlem yok)
    sezon_kodu    "SS23", "AW23", … (mevsim süzgeci öneke bakar)
    ust_kategori, alt_kategori, fiyat_segmenti, kalip     hiyerarşinin sütunları (`SUTUNLAR`)

Öteki sütunlar (`satis`, `ilk_alim`, …) okunmaz. Tablo karar gününde kapanmış sezonlardan kurulmuş
olmalıdır (allocation `ogrenme.ogrenme_tablosu` bunu garanti eder); bu modül tarih görmez.

**Göreli hız** (benzer ile aynı). Her geçmiş option `o'` için mağazanın göreli hızı

    g(m, o') = talep(m, o') / ortalama_{m' gözlemli} talep(m', o')

Ortalama o option'da gözlemi olan BÜTÜN mağazalar üstündendir (kümesi olmayan, örneğin sonradan
kapanmış mağaza da normalleşmeye girer, kümenin hızına girmez). Gözlemli mağazalarında hiç satmamış
option bilgi taşımaz, öğrenilmez.

**Kümenin göreli hızı.** `G(c, o') = ortalama_{m ∈ c, gözlemli} g(m, o')` (kümenin o option'da gözlemli
üyesi yoksa tanımsız). Kümede birleştirmek mağaza gürültüsünü azaltır; mağaza düzeyinde az gözlemli
ince düzeyler (alt kategori × fiyat segmenti × kalıp) küme düzeyinde kullanılabilir (hipotez; İlk
Sevkiyat'ta ölçülür).

**Düzey** (`HIYERARSI`, en özelden en genele; son düzey `()` bütün geçmiş Collection'ı). Yeni option
için düzey, yeni option'la o düzeyin bütün sütunlarında eşleşen en az `en_az` geçmiş option'ı olan ilk
düzeydir; hiçbirinde yoksa son düzey (benzer'in kuralı). Kümenin endeksi seçilen düzeyin option'larında
`G`'nin ortalamasıdır; o düzeyde gözlemi olmayan küme bir üst düzeyin değerini alır, hiçbir düzeyde
gözlemi olmayan küme 1'dir (ortalama küme). Hiyerarşi en ince düzeyleri atlanarak verilebilir
(`HIYERARSI[i:]`; kalibrasyonun ızgarası), son düzeyi her zaman `()`'dır.

**Ölçek** (`olcek`). Mağazanın genel göreli hızı `r(m)` = bütün geçmiş (mevsimin) option'larında
`g(m, o')`'nun ortalaması (benzer'in son düzeyindeki endeksi: mağazanın geçmiş Collection talebinin
ortalama mağazaya oranı); ölçek `r(m) ÷ ortalama_{m' ∈ c(m), gözlemli} r(m')`. Geçmişi olmayan (yeni)
mağaza kümesinin **medyan** ölçeğini alır (spec §0/12); kümesinde hiç gözlemli mağaza yoksa 1. "Geçmiş"
mevsim süzgecinden sonradır: yalnız öteki mevsimde satmış mağaza da medyanı alır (`medyan_olcekliler`).

**Pay** (`KumeEndeksi.paylar`): `pay(o, m) = endeks(c(m), o) × ölçek(m)`; her aday mağaza sözlükte bir
anahtardır (`(option_id, magaza_id)`). Kümesi ya da ölçeği olmayan aday hata verir: allocation
`KahinKol` sözlükte olmayan adaya sessizce 0 verir (spec §0/12).

**Mevsim.** `mevsim="SS"` (varsayılan; İlk Sevkiyat Ruling R9) tabloyu yalnız SS sezonlarına daraltır;
`None` süzmez.

**Kimlik.** `KumeEndeksi.kimlik` öğrenilenlerin içerik özetidir (SHA-256; satır sırasından, etiket
Series'inin sırasından ve nesne kimliğinden bağımsız). `sabitle()` özeti bir kez hesaplayıp saklayan
kopya verir.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# allocation `benzer.HIYERARSI` ile aynı biçim ve değer (allocation testi eşitliği sınar)
HIYERARSI = (("alt_kategori", "fiyat_segmenti", "kalip"), ("alt_kategori", "fiyat_segmenti"),
             ("alt_kategori",), ("ust_kategori",), ())
SUTUNLAR = tuple(dict.fromkeys(s for duzey in HIYERARSI for s in duzey))
MEVSIMLER = ("SS", "AW")
GEREKEN = ("option", "magaza_id", "stoklu_gun", "talep", "sezon_kodu") + SUTUNLAR


def _salt(a: np.ndarray, dtype) -> np.ndarray:
    a = np.array(a, dtype=dtype, copy=True)
    a.flags.writeable = False
    return a


def _hiyerarsi(h) -> tuple[tuple[str, ...], ...]:
    h = tuple(tuple(str(s) for s in d) for d in h)
    if not h or h[-1] != ():
        raise ValueError(f"hiyerarşinin son düzeyi genel (()) olmalı: {h}")
    bilinmeyen = sorted({s for d in h for s in d} - set(SUTUNLAR))
    if bilinmeyen:
        raise ValueError(f"hiyerarşide bilinmeyen sütun: {bilinmeyen}")
    return h


def _etiket(etiket: pd.Series | Mapping) -> dict[str, str]:
    e = pd.Series(etiket)
    if e.isna().any():
        raise ValueError("etikette boş değer")
    ids = e.index.astype(str)
    if ids.duplicated().any():
        raise ValueError("etikette mağaza kimliği tekrarlı")
    return {m: str(v) for m, v in sorted(zip(ids, e.to_numpy()))}


def _gozlemler(tablo: pd.DataFrame, mevsim: str | None) -> pd.DataFrame:
    """Gözlem satırları (`stoklu_gun > 0`, talep tanımlı; mevsim süzgeci), (option, magaza_id) sırasıyla."""
    eksik = [s for s in GEREKEN if s not in tablo.columns]
    if eksik:
        raise KeyError(f"öğrenme tablosunda sütun eksik: {eksik}")
    if mevsim is not None and mevsim not in MEVSIMLER:
        raise ValueError(f"mevsim {MEVSIMLER}'den biri olmalı: {mevsim!r}")
    t = tablo[(tablo["stoklu_gun"] > 0).to_numpy() & tablo["talep"].notna().to_numpy()]
    if mevsim is not None:
        t = t[t["sezon_kodu"].astype(str).str.startswith(mevsim).to_numpy()]
    t = t.assign(option=t["option"].astype(str), magaza_id=t["magaza_id"].astype(str))
    t = t.sort_values(["option", "magaza_id"], kind="stable", ignore_index=True)
    if t.duplicated(["option", "magaza_id"]).any():
        raise ValueError("öğrenme tablosu: aynı (option, mağaza) için birden çok gözlem satırı")
    return t


def _goreli(t: pd.DataFrame):
    """(option [K], mağaza [Ms], göreli [K, Ms]); hiç satmamış option düşer. Ortalama satırda mağaza
    sırasıyla (toplama sırası içerikten)."""
    optionlar = np.array(sorted(t["option"].unique()), dtype=object)
    magazalar = np.array(sorted(t["magaza_id"].unique()), dtype=object)
    talep = np.full((len(optionlar), len(magazalar)), np.nan)
    talep[np.searchsorted(optionlar, t["option"].to_numpy()), np.searchsorted(magazalar, t["magaza_id"].to_numpy())] = (
        t["talep"].to_numpy(dtype=np.float64))
    n = (~np.isnan(talep)).sum(axis=1)
    ort = np.nansum(talep, axis=1) / np.maximum(n, 1) if len(optionlar) else np.zeros(0)
    tut = ort > 0
    return optionlar[tut], magazalar, talep[tut] / ort[tut][:, None]


def _ortalama(a: np.ndarray, axis: int) -> np.ndarray:
    """NaN'sız ortalama; hiç değer yoksa NaN (uyarısız)."""
    n = (~np.isnan(a)).sum(axis=axis)
    s = np.nansum(a, axis=axis)
    return np.divide(s, n, out=np.full(s.shape, np.nan), where=n > 0)


@dataclass(frozen=True, eq=False)
class KumeEndeksi:
    """Öğrenilen küme düzeyi benzer ürün bilgisi (salt okunur). K geçmiş option, C küme.

    en_az      düzey eşiği (en az bu kadar benzer geçmiş option)
    hiyerarsi  kullanılan düzeyler (en özelden en genele; son düzey `()`)
    option     [K] geçmiş option kimliği (artan)
    oznitelik  sütun (`SUTUNLAR`) -> [K] str
    kumeler    [C] küme adı (str, artan)
    goreli     [K, C] kümenin göreli hızı; NaN = kümenin o option'da gözlemli üyesi yok
    etiket     mağaza kimliği -> küme adı (statik atanmış yeni mağazalar dahil)

    `eq=False`: eşitlik nesne kimliğinden; içerik eşitliği `kimlik` ile."""

    en_az: int
    hiyerarsi: tuple
    option: np.ndarray
    oznitelik: Mapping[str, np.ndarray]
    kumeler: tuple
    goreli: np.ndarray
    etiket: Mapping[str, str]
    _kimlik: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "en_az", int(self.en_az))
        object.__setattr__(self, "hiyerarsi", _hiyerarsi(self.hiyerarsi))
        object.__setattr__(self, "option", _salt(np.asarray(self.option).astype(str), str))
        object.__setattr__(self, "oznitelik", {s: _salt(np.asarray(self.oznitelik[s]).astype(str), str)
                                               for s in SUTUNLAR})
        object.__setattr__(self, "kumeler", tuple(str(c) for c in self.kumeler))
        object.__setattr__(self, "goreli", _salt(self.goreli, np.float64))
        object.__setattr__(self, "etiket", dict(sorted((str(m), str(c)) for m, c in self.etiket.items())))
        K = len(self.option)
        if self.goreli.shape != (K, len(self.kumeler)):
            raise ValueError("KumeEndeksi: dizi boyutları tutarsız")
        if any(len(v) != K for v in self.oznitelik.values()):
            raise ValueError("KumeEndeksi: öznitelik uzunluğu K değil")
        if not set(self.etiket.values()) <= set(self.kumeler):
            raise ValueError("KumeEndeksi: etiketteki küme kümeler listesinde yok")

    # --- kimlik --------------------------------------------------------------

    def _ozet(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps({"en_az": self.en_az, "hiyerarsi": self.hiyerarsi, "boyut": list(self.goreli.shape),
                             "option": self.option.tolist(), "kumeler": list(self.kumeler),
                             "etiket": sorted(self.etiket.items()),
                             "oznitelik": {s: self.oznitelik[s].tolist() for s in SUTUNLAR}},
                            ensure_ascii=False).encode("utf-8"))
        a = np.where(np.isnan(self.goreli), np.nan, self.goreli)          # tek NaN biçimi
        h.update(b"\0goreli\0" + np.ascontiguousarray(a, dtype="<f8").tobytes())
        return h.hexdigest()

    @property
    def kimlik(self) -> str:
        """İçerik özeti (SHA-256 hex): sabitlenmişse saklanan, değilse hesaplanan."""
        return self._kimlik if self._kimlik is not None else self._ozet()

    def sabitle(self) -> "KumeEndeksi":
        """Kimliği bir kez hesaplayıp saklayan kopya (zaten sabitse kendisi)."""
        if self._kimlik is not None:
            return self
        e = KumeEndeksi(en_az=self.en_az, hiyerarsi=self.hiyerarsi, option=self.option, oznitelik=self.oznitelik,
                        kumeler=self.kumeler, goreli=self.goreli, etiket=self.etiket)
        object.__setattr__(e, "_kimlik", e._ozet())
        return e

    # --- sorgu ---------------------------------------------------------------

    def _eslesmeler(self, satir: Mapping) -> list[np.ndarray]:
        out = []
        for duzey in self.hiyerarsi:
            e = np.ones(len(self.option), dtype=bool)
            for s in duzey:
                e &= self.oznitelik[s] == str(satir[s])
            out.append(e)
        return out

    def _duzey(self, eslesme: list[np.ndarray]) -> int:
        return next((i for i, e in enumerate(eslesme) if e.sum() >= self.en_az), len(self.hiyerarsi) - 1)

    def kume_endeksi(self, satir: Mapping) -> tuple[np.ndarray, int]:
        """Yeni option için `(endeks [C], düzey)` (modül notu); düzey `hiyerarsi` indisi."""
        eslesme = self._eslesmeler(satir)
        secilen = self._duzey(eslesme)
        endeks = np.full(len(self.kumeler), np.nan)
        for e in eslesme[secilen:]:
            kalan = np.isnan(endeks)
            if not kalan.any():
                break
            endeks[kalan] = _ortalama(self.goreli[e][:, kalan], axis=0)
        return np.where(np.isnan(endeks), 1.0, endeks), secilen

    def _satirlar(self, optionlar: pd.DataFrame) -> pd.DataFrame:
        eksik = [s for s in ("option_id",) + SUTUNLAR if s not in optionlar.columns]
        if eksik:
            raise ValueError(f"yeni option tablosunda öznitelik eksik: {eksik}")
        o = optionlar.assign(option_id=optionlar["option_id"].astype(str))
        if o["option_id"].duplicated().any():
            raise ValueError("yeni option tablosunda option_id tekrarlı")
        sizan = sorted(set(o["option_id"]) & set(self.option.tolist()))
        if sizan:
            raise ValueError(f"karar verilen option öğrenme tablosunda (karar sonrası bilgi): {sizan[:5]}")
        return o.set_index("option_id")

    def duzeyler(self, optionlar: pd.DataFrame) -> dict[str, int]:
        """option_id -> seçilen düzey (`hiyerarsi` indisi)."""
        o = self._satirlar(optionlar)
        return {oid: self._duzey(self._eslesmeler(r)) for oid, r in o.iterrows()}

    def paylar(self, optionlar: pd.DataFrame, adaylar: Mapping[str, Sequence[str]],
               olcek: Mapping[str, float]) -> dict[tuple[str, str], float]:
        """`(option_id, magaza_id) -> pay` (modül notu), `adaylar`ın her çifti için.

        optionlar  yeni option'lar: `option_id` + `SUTUNLAR` (allocation
                   `ogrenme.option_oznitelikleri` + `option_id`)
        adaylar    option_id -> aday mağaza kimlikleri (her biri `etiket`te olmalı)
        olcek      magaza_id -> ölçek (`olcek(...)`; her aday için)"""
        o = self._satirlar(optionlar)
        konum = {c: i for i, c in enumerate(self.kumeler)}
        sonuc: dict[tuple[str, str], float] = {}
        for oid, magazalar in adaylar.items():
            oid = str(oid)
            if oid not in o.index:
                raise KeyError(f"adayı verilen option yeni option tablosunda yok: {oid}")
            endeks, _ = self.kume_endeksi(o.loc[oid])
            for m in magazalar:
                m = str(m)
                if m not in self.etiket:
                    raise ValueError(f"{oid}: aday {m}'in kümesi yok (küme payı her adayı kapsamalı)")
                if m not in olcek:
                    raise ValueError(f"{oid}: aday {m}'in ölçeği yok")
                v = float(endeks[konum[self.etiket[m]]] * float(olcek[m]))
                if not np.isfinite(v) or v < 0:
                    raise ValueError(f"({oid}, {m}): pay sonlu ve eksi olmayan olmalı: {v}")
                sonuc[(oid, m)] = v
        return sonuc


def ogren(tablo: pd.DataFrame, etiket: pd.Series | Mapping, en_az: int, hiyerarsi=HIYERARSI, *,
          mevsim: str | None = "SS") -> KumeEndeksi:
    """Öğrenme tablosundan (modül notundaki sütunlar) ve mağaza → küme etiketinden `KumeEndeksi`.

    `etiket` küme payının kapsayacağı bütün mağazaları taşır (yeni mağazalar statik atamalarıyla);
    etiketi olmayan mağazanın gözlemi yalnız option ortalamasına (göreli hızın paydasına) girer."""
    if int(en_az) < 1:
        raise ValueError(f"en_az >= 1 olmalı: {en_az}")
    h = _hiyerarsi(hiyerarsi)
    et = _etiket(etiket)
    t = _gozlemler(tablo, mevsim)
    optionlar, magazalar, g = _goreli(t)
    kumeler = tuple(sorted(set(et.values())))
    G = np.full((len(optionlar), len(kumeler)), np.nan)
    uye = np.array([et.get(m) for m in magazalar], dtype=object)
    for j, c in enumerate(kumeler):
        sut = uye == c
        if sut.any() and len(optionlar):
            G[:, j] = _ortalama(g[:, sut], axis=1)
    ilk = t.drop_duplicates("option").set_index("option").reindex(optionlar)
    return KumeEndeksi(en_az=int(en_az), hiyerarsi=h, option=optionlar,
                       oznitelik={s: ilk[s].astype(str).to_numpy() for s in SUTUNLAR}, kumeler=kumeler,
                       goreli=G, etiket=et)


def _olcek(tablo: pd.DataFrame, etiket, mevsim: str | None) -> tuple[dict[str, float], list[str]]:
    """(magaza_id -> ölçek, kümesinin medyan ölçeğini alan mağazalar); modül notu."""
    et = _etiket(etiket)
    t = _gozlemler(tablo, mevsim)
    _, magazalar, g = _goreli(t)
    r = dict(zip(magazalar.tolist(), _ortalama(g, axis=0))) if len(magazalar) else {}
    r = {m: v for m, v in r.items() if m in et and np.isfinite(v)}
    sonuc: dict[str, float] = {}
    for c in sorted(set(et.values())):
        uyeler = [m for m, k in et.items() if k == c]
        gozlemli = [m for m in uyeler if m in r]
        ort = float(np.mean([r[m] for m in gozlemli])) if gozlemli else 0.0
        oran = {m: r[m] / ort for m in gozlemli} if ort > 0 else {m: 1.0 for m in gozlemli}
        medyan = float(np.median(list(oran.values()))) if oran else 1.0
        for m in uyeler:
            sonuc[m] = float(oran.get(m, medyan))
    return dict(sorted(sonuc.items())), sorted(m for m in et if m not in r)


def olcek(tablo: pd.DataFrame, etiket: pd.Series | Mapping, *, mevsim: str | None = "SS") -> dict[str, float]:
    """magaza_id -> ölçek (modül notu), `etiket`in her mağazası için: gözlemli mağazada genel göreli hızının
    kümesinin gözlemli üyelerinin ortalamasına oranı, gözlemsiz (yeni) mağazada kümesinin medyan ölçeği,
    kümesinde gözlemli mağaza yoksa 1."""
    return _olcek(tablo, etiket, mevsim)[0]


def medyan_olcekliler(tablo: pd.DataFrame, etiket: pd.Series | Mapping, *, mevsim: str | None = "SS") -> list[str]:
    """Ölçeği kümesinin medyanından gelen mağazalar (artan): mevsim süzgecinden sonra gözlemi olmayanlar (yeni
    mağaza; yalnız öteki mevsimde geçmişi olan mağaza da)."""
    return _olcek(tablo, etiket, mevsim)[1]
