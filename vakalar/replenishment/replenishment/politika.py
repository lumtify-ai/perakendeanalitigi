"""Kollar (v4): motorun `replenishment(Gorunum) -> [C]` çağrılabilirleri ve koşu
sonrası denetim (spec §3.4, §4.1).

    kol = KOLLAR["kural"](lumoda("replenishment"), Ayar(tavan=2860))
    k = kos(kol, ad="kural", parametreler={})        # motor kolu kaydedicilere bağlar
    sevkiyatla_karsilastir(k)                         # boş olmalı

**Pencere.** `Ayar.pencere` (`[bas, bit]`, iki ucu dahil; varsayılan oyun penceresi)
dışında kol sardığı Lumoda kuralını (`temel`) aynen döndürür: pencereden önce koşu
Lumoda koşusuyla birebirdir, pencereden sonra Lumoda geri döner (devralma yok).
Pencerenin ilk pazartesisi kol koşunun kendi geçmişinden hazırlanır ve gölge
defter depoyu böler (`GolgeDefter.baslat`); sonraki her pazartesi defter son
pazartesiden bu yana akışları uzlaştırır (`uzlastir`, kaydedicilerin canlı
kayıtlarıyla). Ardından her pazartesi:

    hedef [OC] → bedene_bol (raf + yolda düşülür) → istek [C]
    → dagit(..., maske_c=motor_maskesi(g), eldeki_c=raf + yolda) → gönderim [C]

Online çiftin hedefi ve online hücrenin isteği 0 (R14; motor maskesi de dışarıda
bırakır). Gönderim gölge defterin stoğunu aşmaz ve defter depoyla aynıdır: SKU
başına gönderim ≤ `g.depo` her pazartesi denetlenir, motorun orantılı kesimi
devreye girmez (`test_kisitli_kolda_motor_kesmez`).

**Bağlantı.** Motor (`kos`) kaydedicileri (`ilk_dagitim`, `outlet_akisi`) koşu
başında `baglan` ile verir; kol durumunu orada sıfırlar (aynı nesne ikinci koşuda
baştan başlar). Bağlanmamış kol pencereye girerse `RuntimeError` (motor
`kaydedici=False` ile koşmuş demektir; defter brüt akışları göremez).

**Kollar** (`KOLLAR`; hepsi `(temel, ayar=None, **ek)`):

    lumoda        Lumoda'nın hücre isteği (`temel(g)`: kendi 28 günlük hedefinden raf ve
                  yolda düşülmüş eksik) doğrudan istektir; hedef [OC] kurulmaz, kayıtta
                  `hedef_adet` YOKTUR (Lumoda'nın isteği `istek_adet`'tedir). Kısıtlıysa
                  `dagit`'ten hep `orantili` öncelikle geçer (Ayar.oncelik yerine). Kısıtsızsa
                  (`Ayar.kisitsiz`) isteği aynen motora verir: motorun orantılı
                  kesimi böler (eşdeğerlik koşusunun kuralı; defter tutulmaz, kayıt
                  maskeli istektir ve sevkiyattan farklı olabilir)
    kural         hedef = max(öngörü, güvenlik stoku); öngörü `kural_ongorusu`
                  (son 7 gün × hafta katsayısı, satış ÷ stoklu gün ile sansür
                  düzeltmeli), güvenlik stoku `guvenlik_stoku` (ros ailesi de stoklu
                  günle)
    kural_basit   kural; öngörü karar anı Basit'inin ham 7 günü
                  (`anlik.karar_ani_ongoru`, R18) × `oc_hafta_katsayisi`.
                  `gecmis_gerekir = True`; `carpanlar` çağırandan
    tahmin        hedef = LightGBM öngörüsü (çıplak; `tahminci` çağırandan)
    tahmin_taban  hedef = max(LightGBM, güvenlik stoku)

Hiç stok görmemiş çiftin kural öngörüsü 0'dır, hedefi güvenlik stoku (R13; geri
düşüş yok). Cover önceliğinin paydası kolun öngörüsüdür (hedef değil; Lumoda'da 0,
orantılı öncelik onu kullanmaz).

**Bir kez hesaplananlar** (pencerenin ilk pazartesisi, koşunun kendi `Gorunum`
geçmişinden): özel gün katsayıları (`ozel_gun_katsayilari`) ve mağaza beden payları
(`magaza_beden_paylari`), yayımlanan tabloların ilk gününden (`CEVRIMDISI_BAS`,
2023-01-01; çevrimdışı öğrenmeyle aynı başlangıç) pencere başına dek. Koşunun
girdilerinden türedikleri için anahtara ayrıca girmezler. Dışarıdan verilenler
(`Ayar`, tahmincinin içerik kimliği, çarpanların içerik özeti) `parametreler()`'e
girer (motor anahtarı).

**Kayıt** (`kayit_tablosu() -> DataFrame`, motor `kayitlar["replenishment"]`'a
yazar): uzun biçim, sütunlar `gun, tarih, kalem, hucre, magaza_id, urun_id, deger`.
`kalem == "istek"` satırları hücre başına gönderim (`deger` adet); öteki kalemler
pazartesi başına bir satır (`hucre = -1`): `pazartesi`, `hedef_adet` (hedef [OC]
toplamı, raf ve yolda düşülmeden; lumoda kolunda yok), `istek_adet` (bedene bölünmüş
eksik, maskeden önce),
`maske_disi_adet`, `gonderilen_adet`, `karsilanmayan_adet`, `acik_adet`,
`koli_sayisi`, `koli_adet`, `tavan`, `tavan_dolulugu`, `defter_kapali_adet`,
`defter_acik_adet` (gönderimden sonra) ve defterin uzlaştırma kalemleri `uzl_*`
(`Uzlastirma` alanları). Plandaki `list[dict]` yerine DataFrame: TAM koşuda ~10⁶
istek satırı sözlük olarak GB'larca bellek ister. `istek_tablosu`, `hafta_tablosu`
koşudan (önbellekten de) okur; `sevkiyatla_karsilastir` kaydı `sevkiyat`'ın
`replenishment` satırlarıyla karşılaştırır (fark satırları; kısıtlı kolda boş).

**Başlangıç havuzu denetimi.** Pencere başı `d0`'da ya da önce kararlaştırılıp
lansmanı `d0`'dan sonra olan bir ilk dağıtım kaydı defterin ilk dağıtım havuzunu
şişirirdi (sevk `d0`'dan önce çıkmış olabilir; T4 notu). Yayımlanan dünyada oyun
ve kalibrasyon başında olamaz; kol yine de `baslat`'ta denetler (`AssertionError`).

Bu modül `perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz
(`tests/test_sizinti.py`); `Gorunum`'ü ve dünyanın açık alanlarını okur.
"""

import copy
import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from . import anlik, kaynak
from .dagitim import KISITSIZ, KOLI_KURALLARI, ONCELIKLER, KoliKurali, Oncelik, dagit, motor_maskesi
from .defter import GolgeDefter, Uzlastirma
from .ihtiyac import (
    GuvenlikStoku,
    bedene_bol,
    guvenlik_stoku,
    kural_ongorusu,
    magaza_beden_paylari,
    oc_hafta_katsayisi,
    ozel_gun_katsayilari,
)
from .sabitler import ACIK_PAYI, OYUN_BAS, OYUN_BIT
from .tahmin import CEVRIMDISI_BAS, Tahminci, gorunum_oznitelik, gorunum_ozellikleri

KAYIT_SUTUNLARI = ("gun", "tarih", "kalem", "hucre", "magaza_id", "urun_id", "deger")
_UZL_ALANLARI = tuple(f.name for f in dataclasses.fields(Uzlastirma) if f.name != "gun")


# ---------------------------------------------------------------------------
# Ayar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ayar:
    """Kolun kısıt ve pencere ayarı (hepsi `parametreler()`'e girer).

    koli     koli kuralı: `KOLI_KURALLARI` adı (varsayılan parametreleriyle) ya da
             `KoliKurali` (kalibrasyonun seçtiği parametreler)
    tavan    haftalık açık toplama tavanı, adet (∞ = yok); kalibrasyonun referans
             tavanı ve katları çağırandan
    oncelik  "cover" | "ihtiyac" | "esit" | "orantili" (`dagit`)
    kisitsiz tavan ∞ ve koli zorunluluğu yok (`KISITSIZ`); tavan sonluysa ValueError
    gs       güvenlik stoku ailesi ve değeri (`kural`, `kural_basit`, `tahmin_taban`)
    pencere  kolun etkin olduğu `[bas, bit]` (iki ucu dahil); dışında Lumoda

    Varsayılan koli ("A") ve güvenlik stoku (istatistik) v2'nin seçimidir; Görev 9'un
    kalibrasyonu gelene dek yer tutucudur, oyun ve kalibrasyon değerleri açıkça verir.
    """

    koli: str | KoliKurali = "A"
    tavan: float = math.inf
    oncelik: Oncelik = "cover"
    kisitsiz: bool = False
    gs: GuvenlikStoku = field(default_factory=lambda: GuvenlikStoku("istatistik"))
    pencere: tuple[date, date] = (OYUN_BAS, OYUN_BIT)

    def __post_init__(self):
        if not isinstance(self.koli, KoliKurali) and self.koli not in KOLI_KURALLARI:
            raise ValueError(f"koli kuralı {sorted(KOLI_KURALLARI)}'den biri ya da KoliKurali olmalı: {self.koli!r}")
        if self.oncelik not in ONCELIKLER:
            raise ValueError(f"bilinmeyen öncelik: {self.oncelik!r}")
        t = float(self.tavan)
        if math.isnan(t) or t < 0:
            raise ValueError(f"tavan ≥ 0 olmalı: {self.tavan}")
        if self.kisitsiz and math.isfinite(t):
            raise ValueError("kısıtsız kolda tavan ∞ olmalı")
        if isinstance(self.koli, KoliKurali) and self.koli.ad == "kisitsiz" and not self.kisitsiz:
            raise ValueError("koli=KoliKurali('kisitsiz') yalnız kisitsiz=True ile (Ayar.kisitsiz kullanın)")
        bas, bit = self.pencere
        if not bas <= bit:
            raise ValueError(f"pencere başı sonundan sonra: {self.pencere}")

    def kural(self) -> KoliKurali:
        """`dagit`'e giden koli kuralı (kısıtsızda `KISITSIZ`)."""
        if self.kisitsiz:
            return KISITSIZ
        return self.koli if isinstance(self.koli, KoliKurali) else KOLI_KURALLARI[self.koli]()

    def sozluk(self) -> dict:
        """Kanonik JSON'a dönen biçim (motor anahtarı; ∞ "inf")."""
        k = self.kural()
        return {
            "koli": {"ad": k.ad, "alfa": k.alfa, "beta": k.beta, "gamma": k.gamma},
            "tavan": "inf" if math.isinf(self.tavan) else float(self.tavan),
            "oncelik": self.oncelik,
            "kisitsiz": bool(self.kisitsiz),
            "gs": {"aile": self.gs.aile, "deger": float(self.gs.deger)},
            "pencere": [self.pencere[0].isoformat(), self.pencere[1].isoformat()],
        }


def carpan_ozeti(carpanlar) -> str:
    """Çarpanların (`perakende_analitik.carpanlar.Carpanlar`) içerik özeti (SHA-256):
    sözlük alanları sıralı anahtar → değer, tablolar CSV metni."""
    h = hashlib.sha256()
    for f in dataclasses.fields(carpanlar):
        v = getattr(carpanlar, f.name)
        if isinstance(v, dict):
            metin = json.dumps(sorted((repr(k), repr(x)) for k, x in v.items()))
        elif isinstance(v, pd.DataFrame):
            metin = v.to_csv(index=False)
        else:
            metin = repr(v)
        h.update(f.name.encode("utf-8") + b"\0" + metin.encode("utf-8") + b"\0")
    return h.hexdigest()


def baslangic_havuzu_denetimi(ilk_dagitim_kaydi: list, lansman_gun: np.ndarray, d0: int) -> None:
    """`gun <= d0 < max(lansman, gun)` olan dolu ilk dağıtım kaydı varsa
    `AssertionError` (modül notu)."""
    for e in ilk_dagitim_kaydi:
        gun, o = int(e["gun"]), int(e["args"][0])
        if gun > d0:
            break
        if d0 < max(int(lansman_gun[o]), gun) and np.asarray(e["cikti"]).sum() > 0:
            raise AssertionError(
                f"başlangıç havuzu: option {o} ilk dağıtımı gün {gun}'de kararlaştırıldı, lansmanı "
                f"{int(lansman_gun[o])} pencere başından ({d0}) sonra; defter havuzu şişebilir")


# ---------------------------------------------------------------------------
# Kollar
# ---------------------------------------------------------------------------


class _Kol:
    """Ortak iskelet: pencere, bağlantı, defter, dağıtım, kayıt (modül notu).
    Alt sınıf `_hazirla_kol(g)` ve `_istek(g) -> (hedef_oc, ongoru_oc, istek_c)` verir
    (`hedef_oc` None: kol hedef kurmaz, yalnız lumoda)."""

    ad = ""
    gecmis_gerekir = False

    def __init__(self, temel, ayar: Ayar | None = None):
        self.temel = temel
        self.ayar = Ayar() if ayar is None else ayar
        self._kaydediciler: dict | None = None
        self._sifirla()

    # --- motor arayüzü ------------------------------------------------------
    def baglan(self, kaydediciler: dict) -> None:
        eksik = {"ilk_dagitim", "outlet_akisi"} - set(kaydediciler)
        if eksik:
            raise ValueError(f"kaydedici eksik: {sorted(eksik)}")
        self._kaydediciler = dict(kaydediciler)
        self._sifirla()

    def parametreler(self) -> dict:
        return {"kol": self.ad, "ayar": self.ayar.sozluk()}

    def kayit_tablosu(self) -> pd.DataFrame:
        if not self._parcalar:
            return pd.DataFrame({s: pd.Series(dtype=t) for s, t in zip(
                KAYIT_SUTUNLARI, ("int64", "datetime64[ns]", "object", "int64", "object", "object", "float64"))})
        return pd.concat(self._parcalar, ignore_index=True)

    def __call__(self, g) -> np.ndarray:
        tarih = pd.Timestamp(g.tarih).date()
        if not self.ayar.pencere[0] <= tarih <= self.ayar.pencere[1]:
            return self.temel(g)
        return self._pencerede(g)

    # --- pencere içi ---------------------------------------------------------
    def _sifirla(self) -> None:
        self._defter: GolgeDefter | None = None
        self._son_gun: int | None = None
        self._parcalar: list[pd.DataFrame] = []

    def _bagli(self, g) -> None:
        if self._kaydediciler is None:
            raise RuntimeError(f"{type(self).__name__} pencerede (gün {g.gun}) ama baglan(kaydediciler) "
                               "çağrılmadı: motoru kaydedici=True ile koşun")
        self._gun_denetimi(g)

    def _gun_denetimi(self, g) -> None:
        """Gün son pencere gününden geri gittiyse yeni bir koşudur: defter tutan kol
        `baglan`'sız yeni koşuya giremez (`RuntimeError`); defter tutmayan kol
        (`_kendiliginden_sifirlanir`) durumunu sıfırlayıp yeniden başlar."""
        d = int(g.gun)
        if self._son_gun is not None and d <= self._son_gun:
            if not self._kendiliginden_sifirlanir():
                raise RuntimeError(f"gün {d} son günden ({self._son_gun}) önce: yeni koşu baglan ile başlar")
            self._sifirla()

    def _kendiliginden_sifirlanir(self) -> bool:
        return False

    def _hazirla(self, g) -> None:
        """Pencerenin ilk pazartesisi: dünyadan indisler ve kolun bir kerelik hesapları."""
        w = g.dunya
        d = int(g.gun)
        if pd.Timestamp(w.takvim["tarih"].iloc[d]).normalize() != pd.Timestamp(g.tarih).normalize():
            raise ValueError("dünyanın takvimi Görünüm'ün günüyle hizalı değil")
        self._w = w
        self._harita = kaynak.harita_kur(w)
        self._hucre_magaza_id = w.magazalar["magaza_id"].to_numpy().astype(str)[self._harita.hucre_magaza]
        self._hucre_urun_id = w.urunler["urun_id"].to_numpy().astype(str)[self._harita.hucre_sku]
        self._hazirla_kol(g)

    def _hazirla_kol(self, g) -> None:
        pass

    def _yayimlanan_gecmis(self, g) -> tuple[np.ndarray, pd.DataFrame, int]:
        """(satış [CEVRIMDISI_BAS, bugün), aynı satırlardan başlayan takvim, satır sayısı)."""
        d = int(g.gun)
        gun0 = pd.Timestamp(g.tarih).normalize() - pd.Timedelta(days=d)
        i0 = int((pd.Timestamp(CEVRIMDISI_BAS) - gun0).days)
        if not 0 <= i0 < d:
            raise ValueError(f"pencere başı ({pd.Timestamp(g.tarih).date()}) yayımlanan geçmişten "
                             f"({CEVRIMDISI_BAS}) sonra olmalı")
        takvim = self._w.takvim.iloc[i0:].reset_index(drop=True)
        return np.asarray(g.satis_gecmisi)[i0:d], takvim, d - i0

    def _kural_dagitimi(self) -> tuple[KoliKurali, float, str]:
        return self.ayar.kural(), (math.inf if self.ayar.kisitsiz else float(self.ayar.tavan)), self.ayar.oncelik

    def _pencerede(self, g) -> np.ndarray:
        self._bagli(g)
        d = int(g.gun)
        if self._defter is None:
            self._hazirla(g)
            self._defter = GolgeDefter(self._w, ACIK_PAYI)
            baslangic_havuzu_denetimi(self._kaydediciler["ilk_dagitim"].kayit,
                                      self._w.optionlar["lansman_gun"].to_numpy(), d)
            uzl = self._defter.baslat(g)
        else:
            uzl = self._defter.uzlastir(g, self._kaydediciler["ilk_dagitim"].kayit,
                                        self._kaydediciler["outlet_akisi"].kayit)
        h = self._harita
        hedef_oc, ongoru_oc, istek = self._istek(g)
        istek = np.where(h.hucre_online, 0, np.maximum(np.asarray(istek, dtype=np.int64), 0))
        maske = motor_maskesi(g)
        kural, tavan, oncelik = self._kural_dagitimi()
        stok, yolda = np.asarray(g.magaza_stok), np.asarray(g.yolda)
        sevk = dagit(istek, self._defter, self._w, kural=kural, tavan=tavan, oncelik=oncelik,
                     ongoru_oc=ongoru_oc, eldeki_c=stok + yolda, maske_c=maske)
        giden = sevk.hucre_adet
        depo = np.asarray(g.depo)
        if (np.bincount(h.hucre_sku, giden, minlength=len(depo)) > depo).any() or giden[~maske].any():
            raise RuntimeError(f"gün {d}: gönderim depoyu ya da motor maskesini aşıyor (defter kaydı)")
        hedef = {} if hedef_oc is None else {"hedef_adet": float(np.sum(hedef_oc))}
        self._kaydet(g, giden, {
            **hedef,
            "istek_adet": int(istek.sum()),
            "maske_disi_adet": int(istek[~maske].sum()),
            "gonderilen_adet": int(giden.sum()),
            "karsilanmayan_adet": int(istek[maske].sum() - giden.sum()),
            "acik_adet": sevk.acik_adet,
            "koli_sayisi": sevk.koli_sayisi,
            "koli_adet": sevk.koli_adet,
            "tavan": tavan,
            "tavan_dolulugu": sevk.tavan_dolulugu,
            "defter_kapali_adet": int(self._defter.kapali_adet().sum()),
            "defter_acik_adet": int(self._defter.acik.sum()),
            **{f"uzl_{a}": float(getattr(uzl, a)) for a in _UZL_ALANLARI},
        })
        self._son_gun = d
        return giden

    def _kaydet(self, g, giden: np.ndarray, ozet: dict) -> None:
        d = int(g.gun)
        tarih = pd.Timestamp(g.tarih).normalize()
        c = np.flatnonzero(giden)
        kalemler = {"pazartesi": 1.0, **ozet}
        n = len(kalemler)
        self._parcalar.append(pd.DataFrame({
            "gun": np.full(len(c) + n, d, dtype=np.int64),
            "tarih": np.full(len(c) + n, tarih.to_datetime64(), dtype="datetime64[ns]"),
            "kalem": np.array(["istek"] * len(c) + list(kalemler), dtype=object),
            "hucre": np.concatenate([c, np.full(n, -1)]).astype(np.int64),
            "magaza_id": np.concatenate([self._hucre_magaza_id[c], np.full(n, "")]).astype(object),
            "urun_id": np.concatenate([self._hucre_urun_id[c], np.full(n, "")]).astype(object),
            "deger": np.concatenate([giden[c].astype(float),
                                     np.array([float(v) for v in kalemler.values()])]),
        }))

    def _istek(self, g) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        raise NotImplementedError


class LumodaKol(_Kol):
    """Lumoda'nın hücre isteği hedeftir; kısıtlıysa `dagit`'ten orantılı öncelikle
    geçer, kısıtsızsa motora aynen gider (modül notu)."""

    ad = "lumoda"

    def __init__(self, temel, ayar: Ayar | None = None):
        super().__init__(temel, dataclasses.replace(Ayar() if ayar is None else ayar, oncelik="orantili"))

    def _pencerede(self, g) -> np.ndarray:
        if not self.ayar.kisitsiz:
            return super()._pencerede(g)
        self._gun_denetimi(g)
        istek = np.asarray(self.temel(g))
        if self._son_gun is None:
            self._hazirla(g)
        maske = motor_maskesi(g)
        self._kaydet(g, np.where(maske, np.maximum(istek, 0), 0),
                     {"istek_adet": int(np.maximum(istek, 0).sum()),
                      "maske_disi_adet": int(np.maximum(istek, 0)[~maske].sum())})
        self._son_gun = int(g.gun)
        return istek

    def _kendiliginden_sifirlanir(self) -> bool:
        return self.ayar.kisitsiz          # kısıtsız Lumoda defter tutmaz, bağlantı istemez

    def _istek(self, g):
        # hedef yok (None): Lumoda'nın isteği zaten raf ve yolda düşülmüş eksiktir
        return None, np.zeros(len(self._harita.oc_magaza)), np.asarray(self.temel(g), dtype=np.int64)


class _HedefliKol(_Kol):
    """Hedef [OC] kuran kollar: beden payları bir kez, hedef → `bedene_bol`."""

    def _hazirla_kol(self, g) -> None:
        satis, _, n = self._yayimlanan_gecmis(g)
        self._paylar = magaza_beden_paylari(satis, self._harita, n)

    def _istek(self, g):
        hedef, ongoru = self._hedef(g)
        h = self._harita
        hedef = np.where(h.oc_online, 0.0, hedef)
        ongoru = np.where(h.oc_online, 0.0, ongoru)
        istek = bedene_bol(hedef, self._paylar, np.asarray(g.magaza_stok), np.asarray(g.yolda), h)
        return hedef, ongoru, istek

    def _gs(self, g) -> np.ndarray:
        return guvenlik_stoku(np.asarray(g.satis_gecmisi), self._harita, int(g.gun), self.ayar.gs,
                              np.asarray(g.stoklu_gecmisi))

    def _hedef(self, g) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError


class KuralKol(_HedefliKol):
    """hedef = max(kural öngörüsü, güvenlik stoku); özel gün katsayıları bir kez."""

    ad = "kural"

    def _hazirla_kol(self, g) -> None:
        super()._hazirla_kol(g)
        satis, takvim, n = self._yayimlanan_gecmis(g)
        self._katsayilar = ozel_gun_katsayilari(satis, self._harita, takvim, n)

    def _ongoru(self, g) -> np.ndarray:
        return kural_ongorusu(np.asarray(g.satis_gecmisi), self._harita, int(g.gun), self._katsayilar,
                              np.asarray(g.stoklu_gecmisi), takvim=self._w.takvim)

    def _hedef(self, g):
        ongoru = self._ongoru(g)
        return np.maximum(ongoru, self._gs(g)), ongoru


class KuralBasitKol(KuralKol):
    """Kural; öngörü karar anı Basit'i × hafta katsayısı (geçmiş kaydı ister)."""

    ad = "kural_basit"
    gecmis_gerekir = True

    def __init__(self, temel, ayar: Ayar | None = None, *, carpanlar):
        super().__init__(temel, ayar)
        self.carpanlar = copy.deepcopy(carpanlar)      # çağıranın nesnesi sonradan değişse de
        self._carpan_ozeti = carpan_ozeti(self.carpanlar)

    def parametreler(self) -> dict:
        return {**super().parametreler(), "carpanlar": self._carpan_ozeti}

    def _hazirla_kol(self, g) -> None:
        super()._hazirla_kol(g)
        self._kurucu = anlik.GunlukKurucu(self._w)

    def _ongoru(self, g) -> np.ndarray:
        ham = anlik.karar_ani_ongoru(g, self.carpanlar, self._harita, kurucu=self._kurucu)
        return ham * oc_hafta_katsayisi(self._harita, self._w.takvim, int(g.gun), self._katsayilar)


class TahminKol(_HedefliKol):
    """hedef = LightGBM öngörüsü (taban yok)."""

    ad = "tahmin"

    def __init__(self, temel, ayar: Ayar | None = None, *, tahminci: Tahminci):
        super().__init__(temel, ayar)
        self.tahminci = tahminci.sabitle()

    def parametreler(self) -> dict:
        return {**super().parametreler(), "tahminci": self.tahminci.kimlik}

    def _hazirla_kol(self, g) -> None:
        super()._hazirla_kol(g)
        self._oznitelik = gorunum_oznitelik(self._w, self._harita)

    def _ongoru(self, g) -> np.ndarray:
        return self.tahminci.tahmin(gorunum_ozellikleri(g, self._harita, self._oznitelik))

    def _hedef(self, g):
        ongoru = self._ongoru(g)
        return ongoru, ongoru


class TahminTabanKol(TahminKol):
    """hedef = max(LightGBM, güvenlik stoku): kuralla aynı taban, öngörü farklı."""

    ad = "tahmin_taban"

    def _hedef(self, g):
        ongoru = self._ongoru(g)
        return np.maximum(ongoru, self._gs(g)), ongoru


KOLLAR = {"lumoda": LumodaKol, "kural": KuralKol, "kural_basit": KuralBasitKol, "tahmin": TahminKol,
          "tahmin_taban": TahminTabanKol}


# ---------------------------------------------------------------------------
# Koşu sonrası denetim
# ---------------------------------------------------------------------------


def _kayit(kosu) -> pd.DataFrame:
    k = kosu.kayitlar.get("replenishment")
    if k is None:
        raise ValueError("koşunun replenishment kaydı yok (kol kayıt tablosu vermiyor)")
    if k.empty and "kalem" not in k.columns:
        return pd.DataFrame(columns=list(KAYIT_SUTUNLARI))
    return k


def istek_tablosu(kosu) -> pd.DataFrame:
    """Kolun hücre başına gönderimi: `gun, tarih, hucre, magaza_id, urun_id, adet` (int64).

    Satırlar kolun motora verdiği diziden (`dagit`'ten SONRA: koli, tavan, stok ve
    maske uygulanmış, yani sevkiyat), kesimden önceki istek değil; o haftalık toplam
    olarak `hafta_tablosu`'nun `istek_adet`'indedir."""
    k = _kayit(kosu)
    k = k[k["kalem"] == "istek"]
    return pd.DataFrame({
        "gun": k["gun"].to_numpy(dtype=np.int64),
        "tarih": pd.to_datetime(k["tarih"]).to_numpy("datetime64[ns]"),
        "hucre": k["hucre"].to_numpy(dtype=np.int64),
        "magaza_id": k["magaza_id"].astype(str).to_numpy(),
        "urun_id": k["urun_id"].astype(str).to_numpy(),
        "adet": np.rint(k["deger"].to_numpy(dtype=float)).astype(np.int64),
    })


def hafta_tablosu(kosu) -> pd.DataFrame:
    """Pazartesi başına özet kalemler (geniş biçim; satır = kolun pencere pazartesisi;
    sütunlar modül notundaki kalemler). `hedef_adet` hedef [OC] toplamıdır (raf ve
    yolda düşülmeden); lumoda kolunda hedef kurulmadığı için bu sütun yoktur, Lumoda'nın
    isteği `istek_adet`'tir."""
    k = _kayit(kosu)
    k = k[k["kalem"] != "istek"]
    if k.empty:
        return pd.DataFrame(columns=["gun", "tarih"])
    t = k.pivot_table(index=["gun", "tarih"], columns="kalem", values="deger", aggfunc="first", sort=True)
    t.columns.name = None
    return t.reset_index()


def sevkiyatla_karsilastir(kosu) -> pd.DataFrame:
    """Kolun pencere pazartesilerinde kaydettiği istek ile koşunun `sevkiyat`'ındaki
    `replenishment` satırları (çıkış günü, hedef mağaza, ürün) arasındaki fark
    satırları: `tarih, magaza_id, urun_id, istek, sevk`. Kayıtta pencere pazartesisi
    yoksa `ValueError` (boş sonuç "hiçbir şey denetlenmedi" anlamına gelmesin). Kısıtlı kolda boş olmalı:
    dolu ise motor isteği kesmiş ya da sıfırlamış, gölge defter kaymıştır."""
    k = _kayit(kosu)
    gunler = pd.to_datetime(k.loc[k["kalem"] == "pazartesi", "tarih"]).unique()
    if len(gunler) == 0:
        raise ValueError("kayıtta pencere pazartesisi yok: karşılaştırılacak bir şey yok "
                         "(kol pencereye hiç girmedi ya da kayıt boş)")
    anahtar = ["tarih", "magaza_id", "urun_id"]
    ist = istek_tablosu(kosu).groupby(anahtar, as_index=False)["adet"].sum().rename(columns={"adet": "istek"})
    sv = kosu.tablo("sevkiyat", ["tarih", "hedef", "urun_id", "adet", "tip"])
    sv = sv[(sv["tip"].astype(str) == "replenishment").to_numpy()]
    sv = pd.DataFrame({"tarih": pd.to_datetime(sv["tarih"]).dt.normalize().to_numpy("datetime64[ns]"),
                       "magaza_id": sv["hedef"].astype(str).to_numpy(),
                       "urun_id": sv["urun_id"].astype(str).to_numpy(),
                       "sevk": sv["adet"].to_numpy(dtype=np.int64)})
    sv = sv[sv["tarih"].isin(gunler)].groupby(anahtar, as_index=False)["sevk"].sum()
    m = ist.merge(sv, on=anahtar, how="outer")
    m[["istek", "sevk"]] = m[["istek", "sevk"]].fillna(0).astype(np.int64)
    return m[m["istek"] != m["sevk"]].sort_values(anahtar).reset_index(drop=True)
