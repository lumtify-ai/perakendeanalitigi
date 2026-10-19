"""Kollar: motora enjekte edilen ilk dağıtım kolları, `hiz` replenishment'ı ve sabit takvim
yeniden oynatıcıları (spec §0/9, §0/10, §0/14, §3.3, §3.5).

    kol = BenzerKol(lumoda("ilk_dagitim"), harita, Ayar(tutma=0.15), endeks=endeks)
    k = kos(kol, ad="benzer", parametreler={...})
    kirpma_tablosu(k)            # oyun option'larında boş olmalı (kollar U'ya sığar)

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme
dokunmaz (`tests/test_sizinti.py`); yalnız `Gorunum`'ü ve dünyanın açık alanlarını okur.
Lumoda'nın kuralları (`temel`) ve öğrenilmiş nesneler (endeks, tahminci, takvim, ölçülmüş
erken talep) dışarıdan verilir.

**İlk dağıtım kolları** (`IlkDagitimKolu(temel, harita, ayar)`; motorun `ilk_dagitim(g, o) ->
[M] paket` yuvası). Option `Ayar.sezon`un `LINE` option'ı değilse kol `temel(g, o)`'yu aynen
döndürür (Lumoda'ya devreder). Öyleyse:

    aday    = paylastir.aday_maskesi(g, o)              Lumoda'nın aday kümesi
    U       = paylastir.ust_sinir(g, o)                 gönderilebilir üst sınır (paket)
    toplam  = ⌊U × (1 − t)⌋                             t: `Ayar.tutma` (belirsizlikte option'ın)
    pay, tavan = kolun `_pay`'ı;  paylastir(toplam, pay, aday, tavan, en_az_gosterim)

Aday mağazalarda hiç pozitif pay yoksa (ör. ölçülmüş talep her yerde 0) pay eşittir (Lumoda'nın
geri düşüşü; kayıtta `geri_dusus`). Kolların gönderdiği toplam `U`'yu aşmaz; motorun kırpması
(`paketleri_sigdir`) bu yüzden kollarda devreye girmez (`motor.kirpma_tablosu`, test).

    lumoda_tut   pay = Lumoda'nın paketleri. t = 0 ve U ≥ Lumoda'nın toplamıysa Lumoda'nın
                 çıktısı AYNEN (mağaza mağaza); değilse Lumoda'nın paketleri ⌊U(1−t)⌋'ya en büyük
                 kalanla ölçeklenir. Lumoda'nın kuralıdır: tavan ve en az gösterim yok
                 (`Ayar.tavan` ve `Ayar.en_az_gosterim` bu kolda etkisiz)
    esit         pay = aday 1 (saf "herkese eşit"); tavan yok (spec §0/14)
    benzer       pay = benzer ürün endeksi (`benzer.Endeks`); tavan = mutlak öngörü
    tahmin       pay = LightGBM erken talep tahmini (`tahmin.Tahminci`); tavan = tahmin
    kahin        pay = ölçülmüş erken birincil talep (`erken_talep[(option_id, magaza_id)]`,
                 başka bir koşunun ölçümü; spec §3.3/5, Ruling R4); tavan yok
    belirsizlik  pay ve tavan taban koldan; t option başına (`t_o[option_id]`, Görev 7)

Kapsama tavanı (`Ayar.tavan`, yalnız benzer ve tahmin): mağazaya en çok
⌈öngörülen erken talep × `TAVAN_KAPSAMA` ÷ paket adedi⌉ paket, en az 1; öngörüsü olmayan
mağaza (benzer: hiçbir adayın geçmişi yok, mutlak öngörü NaN) tavansızdır (`TAVANSIZ`).
Kolların etkin ayarı (etkisiz alanlar kapalı yazılır) `parametreler()`'e girer.

**Kayıt** (`kayit_tablosu()`, motor `kayitlar["ilk_dagitim"]`). `motor.Kaydedici` biçimi
(`gun`, `arg0` = option, `indis` = mağaza, `deger` = paket; `kirpma_tablosu` bunu okur) ve
karar başına sütunlar: `kol` (kendi kararı mı), `U`, `toplam`, `t`, `duzey` (benzerin
hiyerarşi düzeyi; yoksa −1), `tavanda` (tavan uygulanmış ve paketi tavanına eşit mağaza
sayısı; tavan olmasa da o kadar alacak mağazayı da sayar, "tavanı bağlayan"dan geniştir),
`geri_dusus`. Kendi kararında her aday mağaza bir satırdır (paket 0 da); aday mağazası hiç
olmayan kendi kararı tek bir nöbetçi satırdır (`indis = −1`, `deger = 0`, karar sütunları dolu;
`motor.kirpma_tablosu` `indis < 0` satırlarını atar). Lumoda'ya devredilen kararda yalnız paket
alan mağazalar (`kol = False`, karar sütunları −1 / NaN).

**Her koşuya bir kol nesnesi.** Kayıt nesne kurulurken boştur. Motor `baglan`'ı yalnız
Lumoda kaydedicisi kalan koşularda çağırır (kayıt orada da sıfırlanır); ilk dağıtım, RPT ve
markdown'ın üçü de enjekte edilen (sabit takvimli) koşuda çağırmaz. Bu yüzden nesne yeniden
kullanılmamalıdır: ikinci koşuda gün geri gittiği için `RuntimeError` verir.

**`hiz` replenishment'ı** (`HizReplenishment(temel, harita, sezon)`, spec §3.5). `sezon`un `LINE`
hücrelerinde, ilk dağıtımı bitmiş (`ilk_dagitim_gun < gün`), fiziksel (ONL ve outlet akışı
değil), bugün açık mağazada:

    hız   = son `HIZ_GECMIS_GUN` günün satışı ÷ o günlerin stoklu gün sayısı (sansür düzeltmeli)
    istek = max(⌈hız × HIZ_HEDEF_GUN⌉ − stok − yolda, 0)

Pencerede hiç stoklu gün yoksa (hücre iki haftadır boş; hız bilinmiyor) hız, option'ın ilk
dağıtımından bu yana stoklu günlerden alınır (Ruling R16); hiç stoklu günü olmayan hücre
istemez. Oyun hücrelerinin ötekileri 0 (motor zaten sıfırlar); öteki hücreler `temel(g)`.

**Sabit takvim** (`TakvimRPT`, `TakvimMarkdown`; spec §0/10). `takvim` `motor.takvim(kosu)`'dur.
`optionlar`da kaydedilen kararı yeniden oynatır, ötekilerde `temel`in kararı:

    TakvimRPT       günün kaydı (`takvim.rpt_gunu`: sıfır adet ve SKU dizisi korunur); o gün
                    kayıt yoksa bu option'lara RPT yok
    TakvimMarkdown  günün kaydedilen [O, 3] oranı (`takvim.markdown_gunu`). Takvim yalnız sıfır
                    olmayan oran taşıyan günleri saklar ve çağrı günleri politikadan
                    bağımsızdır (pazartesi + sezon indirim günleri): kaydı olmayan çağrı günü
                    kaynak koşuda bütün oranların 0 olduğu gündür, bu option'lar 0 alır
                    (= o günün kaydedilen oranı; markdown oranı hiç sığlaşmadığı için "son
                    kaydedilen oran"la aynı)
"""

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pandas as pd

from allocation import ogrenme, sabitler, tahmin
from allocation.paylastir import TAVANSIZ, aday_maskesi, paket_adedi, paylastir, ust_sinir

KOLLAR = {"lumoda_tut", "esit", "benzer", "tahmin", "kahin", "belirsizlik"}
KAYIT_SUTUNLARI = ["gun", "arg0", "indis", "deger", "kol", "U", "toplam", "t", "duzey",
                   "tavanda", "geri_dusus"]
_BASAMAK = 9    # kayan nokta gürültüsünü eleyen yuvarlama (⌊U(1−t)⌋, ⌈öngörü ÷ paket⌉)


def _taban(x) -> np.ndarray:
    return np.floor(np.round(np.asarray(x, dtype=float), _BASAMAK)).astype(np.int64)


def _tavan(x) -> np.ndarray:
    return np.ceil(np.round(np.asarray(x, dtype=float), _BASAMAK)).astype(np.int64)


def _ozet(nesne) -> str:
    return hashlib.sha256(json.dumps(nesne, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Ayar:
    """İlk dağıtım kolunun ayarı (`parametreler()`'e girer).

    sezon           kolun karar verdiği sezon (`LINE` option'ları); öteki option'lar Lumoda
    tutma           depoda tutulan pay t ∈ [0, 1): gönderilen ⌊U × (1 − t)⌋ paket
    tavan           kapsama tavanı (yalnız benzer ve tahmin kollarında etkin)
    en_az_gosterim  pay alan aday mağazaya en az 1 paket ya da hiç (`paylastir`; lumoda_tut'ta
                    etkisiz)"""

    sezon: str = sabitler.OYUN_SEZONU
    tutma: float = 0.0
    tavan: bool = True
    en_az_gosterim: bool = True

    def __post_init__(self):
        t = float(self.tutma)
        if not 0.0 <= t < 1.0:
            raise ValueError(f"tutma [0, 1) aralığında olmalı: {self.tutma}")
        object.__setattr__(self, "tutma", t)


# ---------------------------------------------------------------------------
# İlk dağıtım kolları
# ---------------------------------------------------------------------------


class IlkDagitimKolu:
    """Ortak iskelet (modül notu). Alt sınıf `_pay(g, o, aday) -> (pay [M], tavan [M] | None,
    düzey)` verir; `tavan` paket sayısıdır (`TAVANSIZ` = o mağazada yok)."""

    ad = ""
    TAVANLI = False         # kapsama tavanı bu kolda etkinleşebilir mi (Ayar.tavan ile)
    EN_AZ = True            # en az gösterim bu kolda etkinleşebilir mi (Ayar.en_az_gosterim ile)

    def __init__(self, temel, harita, ayar: Ayar | None = None):
        self.temel = temel
        self.harita = harita
        self.ayar = Ayar() if ayar is None else ayar
        self._kayit: list[dict] = []        # her koşuya yeni nesne (modül notu)

    # --- motor arayüzü ------------------------------------------------------
    def baglan(self, kaydediciler: dict) -> None:
        """Motor koşu başında (Lumoda kaydedicisi kalan koşularda) çağırır: kayıt sıfırlanır."""
        self._kayit = []

    def kendi_mi(self, o: int) -> bool:
        """Option'ın kararı bu kolda mı (`Ayar.sezon`un `LINE` option'ı)?"""
        return (str(self.harita.option_sezon[o]) == self.ayar.sezon
                and str(self.harita.option_line[o]) == sabitler.LINE)

    @property
    def tavan_etkin(self) -> bool:
        return self.TAVANLI and self.ayar.tavan

    @property
    def en_az_etkin(self) -> bool:
        return self.EN_AZ and self.ayar.en_az_gosterim

    def etkin_ayar(self) -> dict:
        """Kolun gerçekten uyguladığı ayar (etkisiz alanlar kapalı)."""
        return {**dataclasses.asdict(self.ayar), "tavan": self.tavan_etkin,
                "en_az_gosterim": self.en_az_etkin}

    def parametreler(self) -> dict:
        return {"kol": self.ad, "ayar": self.etkin_ayar()}

    def sabitle(self) -> "IlkDagitimKolu":
        """Kimliği içerikten sabit kol (öğrenilmiş girdiler kurulurken sabitlenir): kendisi."""
        return self

    def __call__(self, g, o) -> np.ndarray:
        o = int(o)
        if self._kayit and int(g.gun) < self._kayit[-1]["gun"]:
            raise RuntimeError(f"{type(self).__name__}: gün geri gitti ({self._kayit[-1]['gun']} → {g.gun}); "
                               "kol nesnesi ikinci koşuda kullanılıyor, her koşuya yeni nesne verin")
        if not self.kendi_mi(o):
            cikti = np.asarray(self.temel(g, o), dtype=np.int64)
            self._kayit.append({"gun": int(g.gun), "o": o, "paket": cikti.copy(), "kol": False})
            return cikti
        aday = aday_maskesi(g, o, self.harita)
        U = ust_sinir(g, o, self.harita)
        t = self._tutma(g, o)
        toplam = int(_taban(U * (1.0 - t)))
        paket, tavan, duzey, geri = self._karar(g, o, aday, U, t, toplam)
        paket = np.asarray(paket, dtype=np.int64)
        if tavan is None:
            baglayan = 0
        else:
            baglayan = int((aday & (tavan < TAVANSIZ) & (paket > 0) & (paket >= tavan)).sum())
        self._kayit.append({"gun": int(g.gun), "o": o, "paket": paket.copy(), "kol": True, "aday": aday.copy(),
                            "U": int(U), "toplam": toplam, "t": float(t), "duzey": int(duzey),
                            "tavanda": baglayan, "geri_dusus": bool(geri)})
        return paket

    # --- alt sınıfların kancaları -------------------------------------------
    def _tutma(self, g, o: int) -> float:
        return self.ayar.tutma

    def _pay(self, g, o: int, aday: np.ndarray):
        raise NotImplementedError

    def _karar(self, g, o: int, aday: np.ndarray, U: int, t: float, toplam: int):
        """(paket [M], uygulanan tavan [M] | None, düzey, eşit geri düşüş mü)."""
        pay, tavan, duzey = self._pay(g, o, aday)
        pay = np.where(aday, np.asarray(pay, dtype=float), 0.0)
        geri = bool(aday.any() and not (pay > 0).any())
        if geri:
            pay = aday.astype(float)
        tavan = np.asarray(tavan, dtype=np.int64) if (self.tavan_etkin and tavan is not None) else None
        paket = paylastir(toplam, pay, aday, tavan_paket=tavan, en_az_gosterim=self.en_az_etkin)
        return paket, tavan, duzey, geri

    def _kapsama_tavani(self, g, o: int, ongoru: np.ndarray) -> np.ndarray:
        """[M] paket: ⌈öngörü × TAVAN_KAPSAMA ÷ paket adedi⌉, en az 1; NaN öngörü `TAVANSIZ`."""
        ongoru = np.asarray(ongoru, dtype=float)
        var = np.isfinite(ongoru)
        tavan = np.full(len(ongoru), TAVANSIZ, dtype=np.int64)
        pk = paket_adedi(g.dunya, o)
        tavan[var] = np.maximum(_tavan(np.maximum(ongoru[var], 0.0) * sabitler.TAVAN_KAPSAMA / pk), 1)
        return tavan

    # --- kayıt ---------------------------------------------------------------
    def kayit_tablosu(self) -> pd.DataFrame:
        """Modül notundaki biçim; kayıt yoksa sütunları olan boş tablo."""
        parcalar = []
        for e in self._kayit:
            p = e["paket"]
            if e["kol"]:
                m = np.flatnonzero(e["aday"] | (p != 0))
                if not len(m):
                    m = np.array([-1])               # nöbetçi: aday yok, karar özeti kalsın
                ek = {s: e[s] for s in ("U", "toplam", "t", "duzey", "tavanda", "geri_dusus")}
            else:
                m = np.flatnonzero(p)
                ek = {"U": -1, "toplam": -1, "t": np.nan, "duzey": -1, "tavanda": -1, "geri_dusus": False}
            if not len(m):
                continue
            n = len(m)
            parcalar.append(pd.DataFrame({
                "gun": np.full(n, e["gun"], dtype=np.int64), "arg0": np.full(n, e["o"], dtype=np.int64),
                "indis": m.astype(np.int64), "deger": np.where(m >= 0, p[m], 0).astype(np.int64),
                "kol": np.full(n, e["kol"]),
                **{s: np.full(n, v) for s, v in ek.items()}}))
        if not parcalar:
            return pd.DataFrame({s: pd.Series(dtype=t) for s, t in zip(
                KAYIT_SUTUNLARI, ["int64"] * 4 + ["bool", "int64", "int64", "float64", "int64", "int64", "bool"])})
        df = pd.concat(parcalar, ignore_index=True)[KAYIT_SUTUNLARI]
        return df.astype({"U": np.int64, "toplam": np.int64, "t": np.float64, "duzey": np.int64,
                          "tavanda": np.int64, "kol": bool, "geri_dusus": bool})


class LumodaTutKol(IlkDagitimKolu):
    """Lumoda'nın plan payı, t kadarı depoda tutularak (modül notu)."""

    ad = "lumoda_tut"
    TAVANLI = False
    EN_AZ = False

    def _karar(self, g, o, aday, U, t, toplam):
        lum = np.asarray(self.temel(g, o), dtype=np.int64)
        if t == 0.0 and U >= int(lum.sum()):
            return lum.copy(), None, -1, False
        pay = np.where(aday, np.maximum(lum, 0), 0).astype(float)
        geri = bool(aday.any() and not (pay > 0).any())
        if geri:
            pay = aday.astype(float)
        return paylastir(toplam, pay, aday, en_az_gosterim=False), None, -1, geri


class EsitKol(IlkDagitimKolu):
    """Aday mağazalara eşit pay; tavan yok (spec §0/14)."""

    ad = "esit"
    TAVANLI = False

    def _pay(self, g, o, aday):
        return aday.astype(float), None, -1


def _oznitelik(w, o: int) -> pd.DataFrame:
    """Option'ın açık öznitelikleri + ilk alımı (tek satır)."""
    return ogrenme.option_oznitelikleri(w, np.array([o]))


class BenzerKol(IlkDagitimKolu):
    """Benzer ürün endeksi payı; tavan mutlak öngörüden (`benzer.Endeks.endeks`)."""

    ad = "benzer"
    TAVANLI = True

    def __init__(self, temel, harita, ayar: Ayar | None = None, *, endeks):
        super().__init__(temel, harita, ayar)
        self.endeks = endeks.sabitle()

    def parametreler(self) -> dict:
        return {**super().parametreler(), "endeks": self.endeks.kimlik}

    def _pay(self, g, o, aday):
        endeks, duzey, mutlak = self.endeks.endeks(_oznitelik(g.dunya, o).iloc[0], aday)
        return endeks, self._kapsama_tavani(g, o, np.where(aday, mutlak, 0.0)), duzey


class TahminKol(IlkDagitimKolu):
    """LightGBM erken talep tahmini payı; tavan tahminden (`tahmin.Tahminci`)."""

    ad = "tahmin"
    TAVANLI = True

    def __init__(self, temel, harita, ayar: Ayar | None = None, *, tahminci):
        super().__init__(temel, harita, ayar)
        self.tahminci = tahminci.sabitle()

    def parametreler(self) -> dict:
        return {**super().parametreler(), "tahminci": self.tahminci.kimlik}

    def _pay(self, g, o, aday):
        w = g.dunya
        ongoru = np.zeros(len(aday))
        m = np.flatnonzero(aday)
        if m.size:
            satirlar = _oznitelik(w, o).iloc[np.zeros(m.size, dtype=np.int64)].reset_index(drop=True)
            satirlar["magaza"] = m
            X = tahmin.ozellikler(satirlar, w.magazalar, self.tahminci.gecmis_karisim)
            ongoru[m] = self.tahminci.tahmin(X)
        return ongoru, self._kapsama_tavani(g, o, ongoru), -1


class KahinKol(IlkDagitimKolu):
    """Ölçülmüş erken birincil talep payı; tavan yok (spec §3.3/5; Ruling R4)."""

    ad = "kahin"
    TAVANLI = False

    def __init__(self, temel, harita, ayar: Ayar | None = None, *,
                 erken_talep: Mapping[tuple[str, str], float]):
        super().__init__(temel, harita, ayar)
        talep: dict[str, dict[str, float]] = {}
        for (oid, mid), v in erken_talep.items():
            v = float(v)
            if not np.isfinite(v) or v < 0:
                raise ValueError(f"erken_talep[({oid!r}, {mid!r})] sonlu ve eksi olmayan olmalı: {v}")
            talep.setdefault(str(oid), {})[str(mid)] = v
        self.erken_talep = MappingProxyType({o: MappingProxyType(d) for o, d in talep.items()})
        self._kimlik = _ozet(sorted([o, m, v] for o, d in talep.items() for m, v in d.items()))

    def parametreler(self) -> dict:
        return {**super().parametreler(), "erken_talep": self._kimlik}

    def _pay(self, g, o, aday):
        w = g.dunya
        d = self.erken_talep.get(str(w.optionlar["option_id"].iloc[o]), {})
        mag = w.magazalar["magaza_id"].astype(str).to_numpy()
        return np.array([d.get(m, 0.0) for m in mag]), None, -1


class BelirsizlikKol(IlkDagitimKolu):
    """Pay ve tavan taban koldan, tutma oranı option başına (`t_o[option_id]`, Görev 7).

    `t_o` kolun karar verdiği her option'ı kapsamalı (yoksa `KeyError`); değerler [0, 1).
    Etkin ayar tabanınkidir (`Ayar.tutma` yerine `t_o`)."""

    ad = "belirsizlik"

    def __init__(self, taban: IlkDagitimKolu, t_o: Mapping[str, float]):
        if isinstance(taban, BelirsizlikKol):
            raise TypeError("belirsizlik kolunun tabanı belirsizlik olamaz")
        super().__init__(taban.temel, taban.harita, taban.ayar)
        self.taban = taban
        self.TAVANLI, self.EN_AZ = taban.TAVANLI, taban.EN_AZ
        t = {}
        for oid, v in t_o.items():
            v = float(v)
            if not 0.0 <= v < 1.0:
                raise ValueError(f"t_o[{oid!r}] [0, 1) aralığında olmalı: {v}")
            t[str(oid)] = v
        self.t_o = MappingProxyType(t)

    def parametreler(self) -> dict:
        # t_o tabanın `Ayar.tutma`'sını geçersiz kılar: iki yerde de yok sayılır (aynı davranan
        # iki kol aynı anahtarı alsın)
        ayar = {**self.etkin_ayar(), "tutma": None}
        taban = self.taban.parametreler()
        taban = {**taban, "ayar": {**taban["ayar"], "tutma": None}}
        return {"kol": self.ad, "ayar": ayar, "taban": {"tur": type(self.taban).__qualname__, **taban},
                "t_o": sorted([o, v] for o, v in self.t_o.items())}

    def _tutma(self, g, o):
        oid = str(g.dunya.optionlar["option_id"].iloc[o])
        if oid not in self.t_o:
            raise KeyError(f"belirsizlik: {oid} için t_o yok")
        return self.t_o[oid]

    def _karar(self, g, o, aday, U, t, toplam):
        return self.taban._karar(g, o, aday, U, t, toplam)


# ---------------------------------------------------------------------------
# hiz replenishment'ı
# ---------------------------------------------------------------------------


class HizReplenishment:
    """Oyun sezonu `LINE` hücrelerinde stoklu gün hızıyla hedef; ötekilerde `temel` (modül notu)."""

    def __init__(self, temel, harita, sezon: str = sabitler.OYUN_SEZONU):
        self.temel = temel
        self.harita = harita
        self.sezon = str(sezon)
        oyun_o = (harita.option_sezon == self.sezon) & (harita.option_line == sabitler.LINE)
        self._oyun_hucre = oyun_o[harita.hucre_option]          # ONL dahil (o hücreler 0)

    def parametreler(self) -> dict:
        return {"sezon": self.sezon, "gecmis_gun": sabitler.HIZ_GECMIS_GUN,
                "hedef_gun": sabitler.HIZ_HEDEF_GUN}

    def hucreler(self, g) -> np.ndarray:
        """[C] bool: bugün hızla istenen hücreler (oyun hücresi, fiziksel, açık, ilk dağıtımı bitmiş)."""
        h = self.harita
        return (self._oyun_hucre & ~h.hucre_online & ~np.asarray(g.dunya.hucre_outlet_akisi, dtype=bool)
                & np.asarray(g.acik_magaza, dtype=bool)[h.hucre_magaza]
                & (np.asarray(g.ilk_dagitim_gun)[h.hucre_option] < int(g.gun)))

    def hiz(self, g, c: np.ndarray) -> np.ndarray:
        """[len(c)] stoklu gün hızı (adet/gün) son `HIZ_GECMIS_GUN` günden; pencerede stoklu gün
        yoksa option'ın ilk dağıtımından bu yana (Ruling R16); hiç yoksa 0."""
        d = int(g.gun)
        bas = max(d - sabitler.HIZ_GECMIS_GUN, 0)
        satis = np.asarray(g.satis_gecmisi[bas:d][:, c], dtype=np.int64).sum(axis=0)
        stoklu = np.asarray(g.stoklu_gecmisi[bas:d][:, c]).sum(axis=0)
        bos = np.flatnonzero(stoklu == 0)
        if bos.size:
            cb = c[bos]
            ilk = np.asarray(g.ilk_dagitim_gun)[self.harita.hucre_option[cb]]
            d0 = int(max(min(int(ilk.min()), d), 0))
            # ilk dağıtım varışından önceki günler stoksuz ve satışsızdır: ortak başlangıç yeter
            satis[bos] = np.asarray(g.satis_gecmisi[d0:d][:, cb], dtype=np.int64).sum(axis=0)
            stoklu[bos] = np.asarray(g.stoklu_gecmisi[d0:d][:, cb]).sum(axis=0)
        return np.divide(satis, stoklu, out=np.zeros(len(c)), where=stoklu > 0)

    def __call__(self, g) -> np.ndarray:
        istek = np.array(self.temel(g), dtype=np.int64, copy=True)
        istek[self._oyun_hucre] = 0
        c = np.flatnonzero(self.hucreler(g))
        if c.size:
            hedef = _tavan(self.hiz(g, c) * sabitler.HIZ_HEDEF_GUN)
            eldeki = np.asarray(g.magaza_stok, dtype=np.int64)[c] + np.asarray(g.yolda, dtype=np.int64)[c]
            istek[c] = np.maximum(hedef - eldeki, 0)
        return istek


# ---------------------------------------------------------------------------
# Sabit takvim
# ---------------------------------------------------------------------------


class _Takvimli:
    def __init__(self, temel, takvim, optionlar):
        self.temel = temel
        self.takvim = takvim.sabitle()
        self.optionlar = np.unique(np.asarray(optionlar, dtype=np.int64))
        self._kume = frozenset(self.optionlar.tolist())

    def parametreler(self) -> dict:
        return {"takvim": self.takvim.kimlik, "optionlar": self.optionlar.tolist()}


class TakvimRPT(_Takvimli):
    """`optionlar`da kaydedilen RPT kararı, ötekilerde `temel(g)` (modül notu)."""

    def __call__(self, g) -> dict:
        cikti = {o: v for o, v in dict(self.temel(g)).items() if int(o) not in self._kume}
        cikti.update({o: v for o, v in self.takvim.rpt_gunu(g.gun).items() if int(o) in self._kume})
        return cikti


class TakvimMarkdown(_Takvimli):
    """`optionlar`da günün kaydedilen markdown oranı, ötekilerde `temel(g)` (modül notu)."""

    def __call__(self, g) -> np.ndarray:
        cikti = np.array(self.temel(g), dtype=float, copy=True)
        cikti[self.optionlar] = self.takvim.markdown_gunu(g.gun)[self.optionlar]
        return cikti
