"""Oyun: kolları aynı müşteri akışında v4 motorunda koşturur (spec §4.5, Ruling R28).

    .venv/Scripts/python -m replenishment.oyun                 # ızgara: eşdeğerlik, demo, tarama
    .venv/Scripts/python -m replenishment.oyun izgara --blok demo
    .venv/Scripts/python -m replenishment.oyun hazirlik        # yol 0: tahminci, günlük tablo, çarpanlar
    .venv/Scripts/python -m replenishment.oyun esitlik         # çevrimdışı ↔ Görünüm özellik eşitliği
    .venv/Scripts/python -m replenishment.oyun kalibrasyon     # cikti/kalibrasyon.json (Görev 9)

**Referans nokta** (R28): yol 0 (yayımlanan dünya), alım 1,0, kalibrasyonun seçtiği güvenlik
stoku ailesi (`cikti/kalibrasyon.json`: sabit 4), koli kuralı (A α 0,4 β 3), referans tavan
(25.826 adet/hafta) ×1,0, öncelik cover. Değerler `Ayar` varsayılanlarından değil, dosyadan
açıkça verilir (R20). Izgaranın her koşusu (`Kosum`) referans noktadan sapmalarıyla yazılır
(`ayar_kur`).

**Izgara** (`IZGARA`; adlar tekil, `tests/test_oyun.py`):

    esdegerlik   `lumoda_kisitsiz`: Lumoda + kaydediciler (R4), yayımlanan v4'ün kendisi
    demo         alım {0,4; 0,7; 1,0} × yöntem {kural, tahmin_taban, tahmin} × tavan
                 {kısıtsız (`Ayar.kisitsiz`), gevşek ×1,6, sıkı ×0,6} = 27
    tarama       referans + aileler (ros 6, istatistik); koli yok, B, C; öncelik ihtiyac, esit
                 @1,0 ve cover/ihtiyac/esit @0,4; tavan ×0,4 ve kısıtlı ∞ (×0,6 / ×1,6 demodan,
                 ×1,0 referans); lumoda kısıtlı; kural_basit; tahmin_taban, tahmin = 17
    tarama_kit   öncelik cover/ihtiyac/esit @0,2: yalnız @0,4'te öncelik kıtlığı bağlamıyorsa
                 (`kitlik_karari`: üç önceliğin bulunabilirlik aralığı < `KITLIK_ESIGI` puan)

Yollar (`yol_listesi`, `replenishment.yollar`): yol p > 0'da `lumoda_kisitsiz` (öğrenme
geçmişi) + {lumoda kısıtlı, kural, tahmin_taban, tahmin} @referans; yol 0'ın adları ızgaranınki
(aynı anahtar, önbellekten).

**Hazırlık** (`hazirlik(yol)`; açık adım, test yan etkisi değil — Görev 7 notu). Yolun
`lumoda_kisitsiz` koşusu; yol 0'da (TAM) yayımlanan DuckDB, yol p'de koşunun yayımlanan biçimi
(`motor.yayimlanan_bicim`) `cikti/yollar/yol<p>/perakende.duckdb`'ye yazılır (`veritabani_kur`;
RPT kalıbı). LightGBM tahmincisi bu veriden `tahmin.cevrimdisi_egit` ile (`EGITIM_BIT`'e dek)
eğitilir ve `cikti/tahmin/yol<p>.json`'a yazılır; yanındaki `_ozet.json`'un `anahtar`'ı (veri
kimliği + koşu kod özeti + parametreler) tutarsa yeniden eğitilmez. Eğitim alım düzeyinden
bağımsızdır (AW25 lansmanından önce biter): yol 0 tahmincisi bütün alım düzeylerinde aynıdır.
`kural_basit`'in çarpanları (yalnız yol 0'da koşar) DM'nin kendi günlük tablosundan
(`cikti/gunluk.parquet`, ortak `hazirlik.gunluk_yaz`; R19) `carpanlar_kapanmis(..., OYUN_BAS)`.

**Koşu ve ölçüm** (`kos_bir`). `motor.kos(..., tembel=True)` (önbellek `cikti/kosular/`,
sıralı); kol koşusunun kaydı `sevkiyat` ile karşılaştırılır (fark varsa motor isteği kesmiş,
gölge defter kaymıştır: `RuntimeError`), `olcutler.denetle` korunumu sınar, sonra
`olcutler.hesapla` ve `line_kirilimi` (pencere, `tavan_ref` = referans tavan). Sonuç
`cikti/oyun.json`'a (koşu adı → grup, kol, alım, yol, ayar, anahtar, ölçütler, line) her
koşudan sonra yazılır; biten her koşu `cikti/ilerleme.jsonl`'a. Yeniden başlatılan ızgara
önbellekten sürer; anahtarı ve ölçüm kodu (`olcum_kodu`) aynı kayıt yeniden ölçülmez. Alım
düzeyi değişince `motor.dunya.cache_clear()` (bellek). Uzun koşuda makine uyumaz
(`uyanik_tut`).

**Eşitlik denetimi** (`esitlik_denetimi`; Görev 7 notu): yol 0'ın Lumoda akışında oyun öncesi
bir pazartesi (2025-08-04) LightGBM özellikleri iki yoldan kurulur: çevrimdışı (`kaynak`
matrisleri, yayımlanan DuckDB) ve çevrimiçi (`Gorunum`, motor o güne dek koşar). Özellik başına
eşitlik payı ve fark; `cikti/esitlik.json`.

KALİBRASYON (Görev 9). `kalibrasyon.kalibre_et` koşuyu enjekte edilen `kos_fn(ad, ayar)`'a
bırakır (Ruling R5). `kalibrasyon_kosucusu` `kural` kolunu verilen `Ayar`'la yol 0'da, alım
1,0'da koşar ve kolun penceresinde ölçer (`olcutler.temel_olcutler`).
"""

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import kalibrasyon, kaynak, motor, olcutler, politika, tahmin
from .dagitim import KoliKurali
from .politika import KOLLAR, Ayar
from .sabitler import (
    ALIM_DUZEYLERI,
    CIKTI,
    DEMO_TAVANLARI,
    EGITIM_BIT,
    OYUN_BAS,
    OYUN_BIT,
    TALEP_TOHUM_TABANI,
    YOL_SAYISI,
)

ILERLEME = CIKTI / "ilerleme.jsonl"
ESDEGERLIK = "lumoda_kisitsiz"
KIT_ALIM = 0.4
DAHA_KIT_ALIM = 0.2
KITLIK_ESIGI = 0.5            # puan: üç önceliğin bulunabilirlik aralığı bunun altındaysa kıtlık bağlamıyor
ESITLIK_TARIHI = date(2025, 8, 4)
DUCKDB_BELLEK = "6GB"         # DuckDB bellek sınırı: büyük günlük sorgular sınırı aşınca diske taşar


def talep_tohumu(yol: int, taban: int = TALEP_TOHUM_TABANI) -> int | None:
    """Yolun talep tohumu: yol 0 yayımlanan dünya (None), yol p > 0 `taban + p`."""
    return None if int(yol) == 0 else int(taban) + int(yol)


def _ilerleme(ad: str, sn: float, onbellekten: bool, dosya: Path | None = ILERLEME, **ek) -> None:
    satir = {"ad": ad, "sn": round(float(sn), 1), "onbellekten": bool(onbellekten),
             "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), **ek}
    print(json.dumps(satir, ensure_ascii=False), flush=True)
    if dosya is not None:
        Path(dosya).parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def uyanik_tut() -> None:
    """Windows'ta süreç sürdükçe sistem uykusunu engeller (başka yerde etkisiz)."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _dosya_ozeti(*yollar) -> str:
    return _sha({Path(y).name: hashlib.sha256(Path(y).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                 for y in yollar})


def _json_yaz(yol: Path, icerik: dict) -> None:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(json.dumps(icerik, ensure_ascii=False, indent=1, default=_json_degeri), encoding="utf-8")
    gecici.replace(yol)


def _json_degeri(x):
    if isinstance(x, (np.integer, np.floating)):
        return x.item()
    if isinstance(x, (date, pd.Timestamp)):
        return x.isoformat()
    raise TypeError(type(x).__name__)


def _json_oku(yol: Path) -> dict:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


# ---------------------------------------------------------------------------
# Izgara
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kosum:
    """Bir ızgara koşusu: referans noktadan sapmalar (modül notu).

    kol        "lumoda_kisitsiz" (eşdeğerlik koşusu, `Kaydedici(lumoda)`) ya da `KOLLAR` adı
    alim       ilk alım oranı (AW25)
    tavan_kat  referans tavanın katı (∞ = tavan yok, kısıtlı)
    kisitsiz   `Ayar.kisitsiz` (tavan ∞, koli zorunluluğu yok)
    gs         güvenlik stoku ailesi (None: kalibrasyonun seçtiği)
    koli       "yok" | "A" | "B" | "C" (None: kalibrasyonun seçtiği)
    oncelik    `dagit` önceliği (lumoda kolunda hep orantılı)
    yol        talep yolu (`talep_tohumu`)
    """

    ad: str
    kol: str
    alim: float = 1.0
    tavan_kat: float = 1.0
    kisitsiz: bool = False
    gs: str | None = None
    koli: str | None = None
    oncelik: str = "cover"
    yol: int = 0

    def __post_init__(self):
        if self.kol != ESDEGERLIK and self.kol not in KOLLAR:
            raise ValueError(f"bilinmeyen kol: {self.kol!r}")


def _a(alim: float) -> str:
    return f"a{round(alim * 100):03d}"


def _demo() -> tuple[Kosum, ...]:
    kosumlar = []
    for alim in sorted(ALIM_DUZEYLERI, reverse=True):
        for kol in ("kural", "tahmin_taban", "tahmin"):
            for konum, kat in DEMO_TAVANLARI.items():
                kosumlar.append(Kosum(f"demo_{kol}_{_a(alim)}_{konum}", kol, alim=alim,
                                      tavan_kat=math.inf if konum == "kisitsiz" else kat,
                                      kisitsiz=konum == "kisitsiz"))
    return tuple(kosumlar)


def _oncelikler(alim: float, oncelikler) -> tuple[Kosum, ...]:
    if alim == 1.0:
        return tuple(Kosum(f"kural_oncelik_{o}", "kural", oncelik=o) for o in oncelikler)
    return tuple(Kosum(f"kural_{_a(alim)}_oncelik_{o}", "kural", alim=alim, oncelik=o) for o in oncelikler)


IZGARA: dict[str, tuple[Kosum, ...]] = {
    "esdegerlik": (Kosum(ESDEGERLIK, ESDEGERLIK),),
    "demo": _demo(),
    "tarama": (
        Kosum("kural_ref", "kural"),
        Kosum("kural_gs_ros", "kural", gs="ros"),
        Kosum("kural_gs_istatistik", "kural", gs="istatistik"),
        Kosum("kural_koli_yok", "kural", koli="yok"),
        Kosum("kural_koli_B", "kural", koli="B"),
        Kosum("kural_koli_C", "kural", koli="C"),
        *_oncelikler(1.0, ("ihtiyac", "esit")),
        *_oncelikler(KIT_ALIM, ("cover", "ihtiyac", "esit")),
        Kosum("kural_tavan_x040", "kural", tavan_kat=0.4),
        Kosum("kural_tavan_inf", "kural", tavan_kat=math.inf),
        Kosum("lumoda_ref", "lumoda"),
        Kosum("kural_basit_ref", "kural_basit"),
        Kosum("tahmin_taban_ref", "tahmin_taban"),
        Kosum("tahmin_ref", "tahmin"),
    ),
    "tarama_kit": _oncelikler(DAHA_KIT_ALIM, ("cover", "ihtiyac", "esit")),
}

# Yol başına koşulan kollar (kısa ad → yol 0'daki ızgara koşusu)
YOL_KOLLARI = ("lumoda_kisitsiz", "lumoda_ref", "kural_ref", "tahmin_taban_ref", "tahmin_ref")


def tum_kosumlar() -> dict[str, Kosum]:
    return {s.ad: s for blok in IZGARA.values() for s in blok}


def yol_listesi(yol: int) -> list[tuple[str, Kosum]]:
    """(kısa ad, `Kosum`): yol 0'da ızgaranın koşuları, yol p'de aynıları `y<p>_` önekiyle."""
    tum = tum_kosumlar()
    if int(yol) == 0:
        return [(a, tum[a]) for a in YOL_KOLLARI]
    return [(a, Kosum(**{**tum[a].__dict__, "ad": f"y{yol}_{a}", "yol": int(yol)})) for a in YOL_KOLLARI]


def kosu_sayisi() -> int:
    """Izgara (koşullu `tarama_kit` dahil) + yol p > 0 koşuları."""
    return sum(len(b) for b in IZGARA.values()) + (YOL_SAYISI - 1) * len(YOL_KOLLARI)


def ayar_kur(s: Kosum, kal: kalibrasyon.Kalibrasyon, pencere=(OYUN_BAS, OYUN_BIT)) -> Ayar:
    """Kosum'un `Ayar`'ı: kalibrasyonun referans noktası + sapmalar. Tavan adet,
    ⌊referans × kat⌋ (∞ kat = tavan yok)."""
    gs = kal.gs[s.gs or kal.secilen_aile]
    if s.kisitsiz:
        return Ayar(kisitsiz=True, gs=gs, oncelik=s.oncelik, pencere=tuple(pencere))
    koli_ad = s.koli or kal.secilen_koli
    koli = "yok" if koli_ad == "yok" else kal.koli[koli_ad]
    tavan = math.inf if math.isinf(s.tavan_kat) else float(math.floor(kal.tavan * s.tavan_kat))
    return Ayar(koli=koli, tavan=tavan, gs=gs, oncelik=s.oncelik, pencere=tuple(pencere))


# ---------------------------------------------------------------------------
# Ortam ve hazırlık
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Ortam:
    """Koşuların nerede ve nasıl yapıldığı (TAM varsayılan; testler KÜÇÜK dünyada daraltır)."""

    olcek: str = "tam"
    onbellek: Path = motor.KOSU_DIZINI
    cikti: Path = CIKTI
    pencere: tuple = (OYUN_BAS, OYUN_BIT)
    gun_sayisi: int | None = None
    tahmin_parametreleri: dict = field(default_factory=lambda: dict(tahmin.PARAMETRELER))
    ilerleme: bool = True

    @property
    def ilerleme_yolu(self) -> Path | None:
        return Path(self.cikti) / "ilerleme.jsonl" if self.ilerleme else None

    def yol_dizini(self, yol: int) -> Path:
        return Path(self.cikti) / "yollar" / f"yol{int(yol)}"

    def yayimlanan_mi(self, yol: int) -> bool:
        """Yol 0 TAM dünyada yayımlanan DuckDB'den öğrenir; başka her yol kendi DuckDB'sini kurar."""
        return int(yol) == 0 and self.olcek == "tam"


def baglan(db: Path, ortam: "Ortam"):
    """`kaynak.baglan` + bellek sınırı (`DUCKDB_BELLEK`) ve geçici dizin (`cikti/duckdb_gecici`).
    DuckDB'nin varsayılan sınırı RAM'in %80'i: makinenin kullanılabilir taahhüt belleği daha
    azken büyük günlük sorgu (`stok.gunluk_magaza`, ~2,6 yıl) diske taşmak yerine "Allocation
    failure" ile düşer. Sınır yalnız belleği yönetir, sonucu değiştirmez."""
    con = kaynak.baglan(db)
    gecici = Path(ortam.cikti) / "duckdb_gecici"
    gecici.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET memory_limit='{DUCKDB_BELLEK}'")
    con.execute(f"SET temp_directory='{gecici.as_posix()}'")
    return con


def veritabani_kur(kosu, db: Path, olcek: str = "tam") -> Path:
    """Koşunun yayımlanan biçimini (`motor.yayimlanan_bicim`) `db`'ye yazar (yayımlanan v4
    DuckDB'siyle aynı yol: tablo başına `CREATE TABLE … AS SELECT`; RPT kalıbı). Yanındaki
    `<db>.kosu` koşunun anahtarını tutar; aynı koşudan kurulmuşsa yeniden yazmaz."""
    import duckdb

    db = Path(db)
    iz = db.with_suffix(".kosu")
    anahtar = kosu.meta["anahtar"]
    if db.exists() and iz.exists() and iz.read_text(encoding="utf-8") == anahtar:
        return db
    db.parent.mkdir(parents=True, exist_ok=True)
    tablolar = motor.yayimlanan_bicim({a: kosu.tablo(a) for a in kosu.meta["tablolar"]}, olcek)
    gecici = db.with_name(db.name + ".yaziliyor")
    gecici.unlink(missing_ok=True)
    con = duckdb.connect(str(gecici))
    try:
        for ad, df in tablolar.items():
            con.register("gecici", df)
            con.execute(f"CREATE TABLE {ad} AS SELECT * FROM gecici")
            con.unregister("gecici")
    finally:
        con.close()
    del tablolar
    iz.unlink(missing_ok=True)
    gecici.replace(db)
    iz.write_text(anahtar, encoding="utf-8")
    return db


def _lumoda_kosusu(yol: int, ortam: Ortam, ad: str | None = None, alim: float = 1.0):
    return motor.kos(motor.Kaydedici(motor.lumoda("replenishment")), ad=ad or ESDEGERLIK,
                     parametreler={}, ilk_alim_orani=alim, talep_tohumu=talep_tohumu(yol),
                     onbellek=ortam.onbellek, olcek=ortam.olcek, gun_sayisi=ortam.gun_sayisi, tembel=True)


@dataclass(eq=False)
class Hazirlik:
    """Bir yolun öğrenme geçmişi ve ondan öğrenilenler (modül notu)."""

    yol: int
    talep_tohumu: int | None
    ortam: Ortam
    lumoda: motor.KosuKaydi            # yolun lumoda_kisitsiz koşusu (gerçekleşen tarih)
    db: Path
    kaynak_kimligi: list               # verinin kimliği (yayımlanan parmak izi ya da koşu anahtarı)
    tahminci: tahmin.Tahminci
    tahmin_ozet: dict
    _carpanlar: object = None

    @property
    def egitim_kaynagi(self) -> str:
        """Tahmin kollarının `parametreler`'ine giren eğitim verisi kimliği."""
        return "yayimlanan" if self.ortam.yayimlanan_mi(self.yol) else self.lumoda.meta["anahtar"]

    def gunluk(self) -> Path:
        """DM'nin kendi günlük tablosu (R19): yol 0 TAM'da `cikti/gunluk.parquet`, başka yolda
        yolun dizininde. Yanındaki `.kaynak` veri kimliğini ve ortak kodun özetini tutar."""
        from perakende_analitik import hazirlik as ortak_hazirlik
        from perakende_analitik import stok as ortak_stok

        from .anlik import PENCERE

        yol = (Path(self.ortam.cikti) / "gunluk.parquet" if self.ortam.yayimlanan_mi(self.yol)
               else self.ortam.yol_dizini(self.yol) / "gunluk.parquet")
        iz = yol.with_suffix(".kaynak")
        kimlik = _sha({"veri": self.kaynak_kimligi, "pencere": [str(p) for p in PENCERE],
                       "kod": _dosya_ozeti(ortak_hazirlik.__file__, ortak_stok.__file__)})
        if yol.exists() and iz.exists() and iz.read_text(encoding="utf-8") == kimlik:
            return yol
        t0 = time.perf_counter()
        yol.parent.mkdir(parents=True, exist_ok=True)
        con = baglan(self.db, self.ortam)
        try:
            n = ortak_hazirlik.gunluk_yaz(con, yol, PENCERE)
        finally:
            con.close()
        iz.write_text(kimlik, encoding="utf-8")
        _ilerleme(f"y{self.yol}_gunluk", time.perf_counter() - t0, False, self.ortam.ilerleme_yolu, satir=n)
        return yol

    def carpanlar(self):
        """`kural_basit`'in karar anı çarpanları (oyun başında kapanmış sezonlardan)."""
        if self._carpanlar is None:
            from perakende_analitik import hazirlik as ortak_hazirlik

            gunluk = self.gunluk()
            con = baglan(self.db, self.ortam)
            try:
                self._carpanlar = ortak_hazirlik.carpanlar_kapanmis(con, gunluk, self.ortam.pencere[0])
            finally:
                con.close()
        return self._carpanlar


def tahminci_hazirla(yol: int, db: Path, kaynak_kimligi: list, ortam: Ortam) -> tuple[tahmin.Tahminci, dict]:
    """Yolun LightGBM'i: `cikti/tahmin/yol<p>.json` anahtarı tutarsa oradan, yoksa eğitilir."""
    dizin = Path(ortam.cikti) / "tahmin"
    model, ozet_yolu = dizin / f"yol{yol}.json", dizin / f"yol{yol}_ozet.json"
    anahtar = _sha({"veri": kaynak_kimligi, "kod": motor.kod_ozeti(), "bit": EGITIM_BIT.isoformat(),
                    "parametreler": ortam.tahmin_parametreleri, "olcek": ortam.olcek})
    eski = _json_oku(ozet_yolu)
    if model.exists() and eski.get("anahtar") == anahtar:
        return tahmin.Tahminci.yukle(model), eski
    t0 = time.perf_counter()
    w = motor.dunya(ortam.olcek)
    con = baglan(db, ortam)
    try:
        t, ozet = tahmin.cevrimdisi_egit(con, w, kaynak.harita_kur(w), EGITIM_BIT, ortam.tahmin_parametreleri)
    finally:
        con.close()
    ozet = {**ozet, "anahtar": anahtar, "veri": kaynak_kimligi, "onceki_kimlik": eski.get("kimlik")}
    dizin.mkdir(parents=True, exist_ok=True)
    t.kaydet(model)
    _json_yaz(ozet_yolu, ozet)
    _ilerleme(f"y{yol}_tahmin_egitimi", time.perf_counter() - t0, False, ortam.ilerleme_yolu,
              satir=ozet["satir"], dogrulama_sapma=round(ozet["dogrulama_sapma"], 4),
              ayni_kimlik=eski.get("kimlik") == t.kimlik if eski.get("kimlik") else None)
    return t, ozet


def hazirlik(yol: int = 0, ortam: Ortam | None = None) -> Hazirlik:
    """Yolun `lumoda_kisitsiz` koşusu, verisi (DuckDB) ve tahmincisi (modül notu)."""
    ortam = ortam or Ortam()
    ad = ESDEGERLIK if int(yol) == 0 else f"y{yol}_{ESDEGERLIK}"
    lum = _lumoda_kosusu(yol, ortam, ad)
    if ortam.yayimlanan_mi(yol):
        db, kimlik = Path(kaynak.VERITABANI), ["yayimlanan", motor.veri_parmak_izi()]
    else:
        t0 = time.perf_counter()
        db = veritabani_kur(lum, ortam.yol_dizini(yol) / "perakende.duckdb", ortam.olcek)
        kimlik = ["kosu", lum.meta["anahtar"]]
        _ilerleme(f"y{yol}_veritabani", time.perf_counter() - t0, False, ortam.ilerleme_yolu)
    t, ozet = tahminci_hazirla(int(yol), db, kimlik, ortam)
    return Hazirlik(yol=int(yol), talep_tohumu=talep_tohumu(yol), ortam=ortam, lumoda=lum, db=db,
                    kaynak_kimligi=kimlik, tahminci=t, tahmin_ozet=ozet)


# ---------------------------------------------------------------------------
# Koşu ve ölçüm
# ---------------------------------------------------------------------------


def olcum_kodu(kal: kalibrasyon.Kalibrasyon, ortam: Ortam) -> str:
    """Ölçümü belirleyen: ölçüt kodu, referans tavan (doluluk paydası), pencere."""
    return _sha({"olcutler": _dosya_ozeti(olcutler.__file__), "tavan": kal.tavan,
                 "pencere": [str(p) for p in ortam.pencere]})


def politika_kur(s: Kosum, H: Hazirlik, kal: kalibrasyon.Kalibrasyon, ortam: Ortam):
    """(politika, parametreler, ayar | None)."""
    temel = motor.lumoda("replenishment")
    if s.kol == ESDEGERLIK:
        return motor.Kaydedici(temel), {}, None
    ayar = ayar_kur(s, kal, ortam.pencere)
    ek, parametreler = {}, {}
    if s.kol in ("tahmin", "tahmin_taban"):
        ek["tahminci"] = H.tahminci
        parametreler["egitim"] = H.egitim_kaynagi
    elif s.kol == "kural_basit":
        ek["carpanlar"] = H.carpanlar()
    return KOLLAR[s.kol](temel, ayar, **ek), parametreler, ayar


def kos_bir(s: Kosum, H: Hazirlik, kal: kalibrasyon.Kalibrasyon, ortam: Ortam, onceki: dict | None = None):
    """Koşu (önbellekten ya da yeni), denetim ve ölçüm; (`KosuKaydi`, kayıt sözlüğü).
    `onceki` (bu koşunun eski kaydı) anahtarı ve ölçüm kodu tutarsa yeniden ölçülmez."""
    if s.yol != H.yol:
        raise ValueError(f"{s.ad}: yol {s.yol}, hazırlık yol {H.yol}")
    t0 = time.perf_counter()
    pol, parametreler, ayar = politika_kur(s, H, kal, ortam)
    k = motor.kos(pol, ad=s.ad, parametreler=parametreler, ilk_alim_orani=s.alim, talep_tohumu=H.talep_tohumu,
                  onbellek=ortam.onbellek, olcek=ortam.olcek, gun_sayisi=ortam.gun_sayisi, tembel=True)
    del pol
    t1 = time.perf_counter()
    kod = olcum_kodu(kal, ortam)
    if onceki and onceki.get("anahtar") == k.meta["anahtar"] and onceki.get("olcum_kodu") == kod:
        kayit = onceki
    else:
        fark_satiri = None
        if s.kol != ESDEGERLIK:
            fark = politika.sevkiyatla_karsilastir(k)
            if not fark.empty:
                raise RuntimeError(f"{s.ad}: kolun kaydı sevkiyattan {len(fark)} satırda farklı (koşu geçersiz)")
            fark_satiri = 0
        olcutler.denetle(k)
        w = motor.dunya(ortam.olcek, s.alim)
        bas, bit = ortam.pencere
        o = olcutler.hesapla(k, w, bas, bit, tavan_ref=kal.tavan)
        lk = olcutler.line_kirilimi(k, w, bas, bit)
        kayit = {
            "kol": s.kol, "alim": s.alim, "yol": s.yol, "talep_tohumu": H.talep_tohumu,
            "kosum": {a: (None if isinstance(v, float) and math.isinf(v) else v) for a, v in s.__dict__.items()}
            | {"tavan_kat": "inf" if math.isinf(s.tavan_kat) else s.tavan_kat},
            "ayar": None if ayar is None else ayar.sozluk(),
            "anahtar": k.meta["anahtar"], "olcum_kodu": kod, "sevkiyat_farki": fark_satiri,
            "motor_sn": k.meta.get("motor_sn"), "sure_sn": k.meta.get("sure_sn"),
            "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"),
            "olcutler": o, "line": lk.to_dict("records"),
        }
    _ilerleme(s.ad, time.perf_counter() - t0, k.onbellekten, ortam.ilerleme_yolu,
              motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"),
              olcum_sn=round(time.perf_counter() - t1, 1),
              bulunabilirlik=round(kayit["olcutler"]["bulunabilirlik"], 3))
    return k, kayit


def kitlik_karari(kosular: dict, alim: float = KIT_ALIM) -> dict:
    """Öncelik taramasının kıtlık göstergesi: `alim`'daki ve 1,0'daki üç önceliğin
    bulunabilirliği, aralığı, depo-boş kayıp payı ve kısıtsız demo kolunun kesilen payı (yalnız
    depo stoğu). `baglayici`: `alim`'daki aralık ≥ `KITLIK_ESIGI` puan."""
    def ad(a, o):
        if o == "cover" and a == 1.0:
            return "kural_ref"
        return f"kural_oncelik_{o}" if a == 1.0 else f"kural_{_a(a)}_oncelik_{o}"

    sonuc = {}
    for a in (1.0, alim):
        deger = {o: kosular[ad(a, o)]["olcutler"] for o in ("cover", "ihtiyac", "esit") if ad(a, o) in kosular}
        if len(deger) < 3:
            continue
        b = [v["bulunabilirlik"] for v in deger.values()]
        demo = kosular.get(f"demo_kural_{_a(a)}_kisitsiz", {}).get("olcutler", {})
        sonuc[_a(a)] = {
            "bulunabilirlik": {o: v["bulunabilirlik"] for o, v in deger.items()},
            "aralik": max(b) - min(b),
            "depo_bos_kayip_pay_yuzde": {o: v["depo_bos_kayip_pay_yuzde"] for o, v in deger.items()},
            "kesilen_pay_yuzde": {o: v["kesilen_pay_yuzde"] for o, v in deger.items()},
            "kisitsiz_kesilen_pay_yuzde": demo.get("kesilen_pay_yuzde"),
            "kisitsiz_depo_bos_kayip_pay_yuzde": demo.get("depo_bos_kayip_pay_yuzde"),
        }
    if _a(alim) in sonuc:
        sonuc["baglayici"] = bool(sonuc[_a(alim)]["aralik"] >= KITLIK_ESIGI)
        sonuc["esik_puan"] = KITLIK_ESIGI
    return sonuc


def _sirala(kosumlar) -> list[Kosum]:
    """Alım düzeyine göre (azalan, kararlı): dünya önbelleği düzey başına bir kez kurulur."""
    return sorted(kosumlar, key=lambda s: -s.alim)


def _bloklar(blok: str) -> list[str]:
    if blok == "hepsi":
        return ["esdegerlik", "demo", "tarama"]
    if blok not in IZGARA:
        raise ValueError(f"blok {sorted(IZGARA) + ['hepsi']}'den biri olmalı: {blok!r}")
    return [blok]


def kos_hepsi(blok: str = "hepsi", ortam: Ortam | None = None, kal: kalibrasyon.Kalibrasyon | None = None,
              tut: bool = True) -> dict:
    """Bloğun koşuları sıralı (tembel `KosuKaydi`; `tut=False` iken sözlükte tutulmaz) ve
    ölçümleri `cikti/oyun.json`'a. "hepsi" eşdeğerlik + demo + tarama, ardından gerekirse
    `tarama_kit` (`kitlik_karari`)."""
    ortam = ortam or Ortam()
    kal = kal or kalibrasyon.oku()
    yol = Path(ortam.cikti) / "oyun.json"
    kayit = _json_oku(yol)
    kayit.setdefault("kosular", {})
    kayit["kalibrasyon"] = {"tavan": kal.tavan, "gs": {a: g.aile + f" {g.deger:g}" for a, g in kal.gs.items()},
                            "secilen_aile": kal.secilen_aile, "secilen_koli": kal.secilen_koli,
                            "koli": {a: [c.alfa, c.beta, c.gamma] for a, c in kal.koli.items()},
                            "hedef_bulunabilirlik": kal.hedef_bulunabilirlik}
    kayit["pencere"] = [str(p) for p in ortam.pencere]
    H = hazirlik(0, ortam)
    sonuc = {}

    def kos_liste(kosumlar, grup):
        alim = None
        for s in _sirala(kosumlar):
            if alim is not None and s.alim != alim:
                motor.dunya.cache_clear()
            alim = s.alim
            k, e = kos_bir(s, H, kal, ortam, kayit["kosular"].get(s.ad))
            kayit["kosular"][s.ad] = {"grup": grup, **e}
            _json_yaz(yol, kayit)
            if tut:
                sonuc[s.ad] = k
            del k

    for b in _bloklar(blok):
        kos_liste(IZGARA[b], b)
    if blok == "hepsi":
        karar = kitlik_karari(kayit["kosular"])
        kayit["kitlik"] = karar
        _json_yaz(yol, kayit)
        print(f"kıtlık kararı: {json.dumps(karar, ensure_ascii=False)}", flush=True)
        if karar.get("baglayici") is False:
            kos_liste(IZGARA["tarama_kit"], "tarama_kit")
            karar = kitlik_karari(kayit["kosular"])
            karar["daha_kit"] = kitlik_karari(kayit["kosular"], DAHA_KIT_ALIM)
            kayit["kitlik"] = karar
            _json_yaz(yol, kayit)
    motor.dunya.cache_clear()
    return sonuc


# ---------------------------------------------------------------------------
# Eşitlik denetimi (çevrimdışı ↔ Görünüm)
# ---------------------------------------------------------------------------


class _Yakalandi(Exception):
    pass


class _Yakalayici:
    """Lumoda'yı aynen çağırır; `gun`de Görünüm özelliklerini kurup koşuyu durdurur."""

    def __init__(self, gun: int, harita, oznitelik):
        self.temel = motor.lumoda("replenishment")
        self.gun, self.harita, self.oznitelik = gun, harita, oznitelik
        self.X = None

    def __call__(self, g):
        if int(g.gun) == self.gun:
            self.X = tahmin.gorunum_ozellikleri(g, self.harita, self.oznitelik)
            raise _Yakalandi
        return self.temel(g)


def _karsilastir(X_off: pd.DataFrame, X_on: pd.DataFrame) -> dict:
    sonuc = {}
    for s in tahmin.OZELLIKLER:
        a, b = X_off[s], X_on[s]
        if s in tahmin.KATEGORIK:
            sonuc[s] = {"esit_pay": float((a.astype(str).to_numpy() == b.astype(str).to_numpy()).mean())}
            continue
        a, b = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
        fark = b - a
        sonuc[s] = {"esit_pay": float(np.isclose(a, b, rtol=0, atol=1e-9).mean()),
                    "ort_cevrimdisi": float(a.mean()), "ort_gorunum": float(b.mean()),
                    "ort_fark": float(fark.mean()), "ort_mutlak_fark": float(np.abs(fark).mean()),
                    "en_buyuk_mutlak_fark": float(np.abs(fark).max()) if len(fark) else 0.0}
    return sonuc


def esitlik_denetimi(ortam: Ortam | None = None, tarih: date = ESITLIK_TARIHI,
                     H: Hazirlik | None = None) -> dict:
    """Modül notundaki denetim; sonuç `cikti/esitlik.json`'a da yazılır."""
    ortam = ortam or Ortam()
    t0 = time.perf_counter()
    w = motor.dunya(ortam.olcek)
    h = kaynak.harita_kur(w)
    gun0 = pd.Timestamp(w.takvim["tarih"].iloc[0])
    d = int((pd.Timestamp(tarih) - gun0).days)
    yak = _Yakalayici(d, h, tahmin.gorunum_oznitelik(w, h))
    try:
        motor.kos(yak, ad="esitlik", parametreler={}, onbellek=None, olcek=ortam.olcek, gun_sayisi=d + 1)
    except _Yakalandi:
        pass
    if yak.X is None:
        raise RuntimeError(f"{tarih}: replenishment çağrılmadı (pazartesi değil mi?)")
    H = H or hazirlik(0, ortam)
    con = baglan(H.db, ortam)
    try:
        anahtar = kaynak.hucre_anahtari(w)
        son = pd.Timestamp(tarih) - pd.Timedelta(days=1)
        satis = kaynak.gunluk_satis_matrisi(con, anahtar, tahmin.CEVRIMDISI_BAS, son)
        stoklu = kaynak.gunluk_stoklu_matrisi(con, anahtar, tahmin.CEVRIMDISI_BAS, son)
    finally:
        con.close()
    oz = tahmin.oznitelik_kur(w, h, tahmin.CEVRIMDISI_BAS)
    X_off = tahmin.ozellik_tablosu(satis, stoklu, h, oz, oz.satir(tarih))
    del satis, stoklu
    fiz = ~h.oc_online
    p_off, p_on = H.tahminci.tahmin(X_off[fiz]), H.tahminci.tahmin(yak.X[fiz])
    sonuc = {
        "tarih": str(tarih), "oc": int(len(fiz)), "fiziksel_oc": int(fiz.sum()),
        "fiziksel": _karsilastir(X_off[fiz].reset_index(drop=True), yak.X[fiz].reset_index(drop=True)),
        "tum": {s: v["esit_pay"] for s, v in _karsilastir(X_off, yak.X).items()},
        "tahmin": {"ort_cevrimdisi": float(p_off.mean()), "ort_gorunum": float(p_on.mean()),
                   "ort_mutlak_fark": float(np.abs(p_on - p_off).mean()),
                   "goreli_mutlak_fark": float(np.abs(p_on - p_off).sum() / max(p_off.sum(), 1e-9)),
                   "tahminci": H.tahminci.kimlik},
        "sure_sn": round(time.perf_counter() - t0, 1),
    }
    _json_yaz(Path(ortam.cikti) / "esitlik.json", sonuc)
    return sonuc


# ---------------------------------------------------------------------------
# Kalibrasyon (Görev 9)
# ---------------------------------------------------------------------------


def kalibrasyon_kosucusu(*, olcek: str = "tam", onbellek: Path | None = motor.KOSU_DIZINI,
                         gun_sayisi: int | None = None, ilerleme: Path | None = ILERLEME):
    """`kalibre_et`'in `kos_fn(ad, ayar) -> dict`'i (modül notu). `olcek`, `onbellek`,
    `gun_sayisi` testler içindir."""

    def kos_fn(ad: str, ayar: politika.Ayar) -> dict:
        t0 = time.perf_counter()
        kol = politika.KuralKol(motor.lumoda("replenishment"), ayar)
        k = motor.kos(kol, ad=ad, parametreler={}, onbellek=onbellek, olcek=olcek, gun_sayisi=gun_sayisi,
                      tembel=onbellek is not None, kaydedici=True)
        fark = politika.sevkiyatla_karsilastir(k)
        if not fark.empty:
            raise RuntimeError(f"{ad}: kolun kaydı sevkiyattan {len(fark)} satırda farklı (koşu geçersiz)")
        bas, bit = ayar.pencere
        olcut = olcutler.temel_olcutler(k, bas, bit)
        _ilerleme(ad, time.perf_counter() - t0, k.onbellekten, ilerleme,
                  motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"),
                  bulunabilirlik=round(olcut["bulunabilirlik"], 3))
        return olcut

    return kos_fn


def kalibrasyon_kos(yol: Path = kalibrasyon.DOSYA) -> kalibrasyon.Kalibrasyon:
    """Gerçek kalibrasyon: referans tavan (yayımlanan veri) → `kalibre_et` → `yol`."""
    t0 = time.perf_counter()
    con = kaynak.baglan()
    try:
        tavan = kalibrasyon.referans_tavan(con)
    finally:
        con.close()
    print(f"referans tavan: {tavan}", flush=True)
    k = kalibrasyon.kalibre_et(kalibrasyon_kosucusu(), tavan)
    kalibrasyon.yaz(k, yol, sure_sn=round(time.perf_counter() - t0, 1))
    return k


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m replenishment.oyun")
    alt = ap.add_subparsers(dest="komut")
    alt.add_parser("kalibrasyon", help="AW24 penceresinde kalibrasyon (cikti/kalibrasyon.json)")
    iz = alt.add_parser("izgara", help="oyun ızgarası (cikti/oyun.json)")
    iz.add_argument("--blok", default="hepsi", choices=[*IZGARA, "hepsi"])
    hz = alt.add_parser("hazirlik", help="yolun tahmincisi (ve yol 0'da günlük tablo, çarpanlar)")
    hz.add_argument("--yol", type=int, default=0)
    alt.add_parser("esitlik", help="çevrimdışı ↔ Görünüm özellik eşitliği (cikti/esitlik.json)")
    secim = ap.parse_args(argv)
    komut = secim.komut or "izgara"
    uyanik_tut()
    if komut == "kalibrasyon":
        k = kalibrasyon_kos()
        sutunlar = ["asama", "ad", "bulunabilirlik", "toplama_maliyeti_tl", "magaza_stok_son"]
        print(k.tablo[sutunlar].to_string(), flush=True)
        print(f"hedef {k.hedef_bulunabilirlik:.3f}  gs {k.gs}  aile {k.secilen_aile}  koli {k.koli}  "
              f"seçilen koli {k.secilen_koli}  tavan {k.tavan}", flush=True)
    elif komut == "hazirlik":
        H = hazirlik(secim.yol)
        if secim.yol == 0:
            H.carpanlar()
        print(json.dumps({"yol": H.yol, "db": str(H.db), "tahminci": H.tahminci.kimlik,
                          "dogrulama_sapma": H.tahmin_ozet.get("dogrulama_sapma")}, ensure_ascii=False))
    elif komut == "esitlik":
        print(json.dumps(esitlik_denetimi(), ensure_ascii=False, indent=1))
    else:
        kos_hepsi(getattr(secim, "blok", "hepsi"), tut=False)


if __name__ == "__main__":
    main()
