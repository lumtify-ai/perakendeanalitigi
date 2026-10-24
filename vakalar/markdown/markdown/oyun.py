"""Oyun: kalibrasyon ve ızgara; kolları yollarda kurar, koşar ve ölçer (spec §4.3–4.5, Ruling R4, R5, R18).

    .venv/Scripts/python -m markdown.oyun kalibrasyon                  # 18 koşu, cikti/kalibrasyon.json
    .venv/Scripts/python -m markdown.oyun izgara --blok yol0           # yol 0: lumoda + 8 kol × 2 sezon
    .venv/Scripts/python -m markdown.oyun izgara --blok yollar [--yol P]   # yollar 1–4: lumoda + 6 kol × 2
    .venv/Scripts/python -m markdown.oyun izgara --blok ablasyon       # yol 0: kural_takvim, kural_deposuz × 2 (R24)
    .venv/Scripts/python -m markdown.oyun olc                          # önbellekteki koşuları yeniden ölç
    ... --olcek KUCUK                                                  # cikti/kucuk/

Bu modül ölçüm tarafındadır (`simulasyon.KOSU_DISI`; `tests/test_sizinti.py` `OLCUM_MODULLERI`): kolları
kurar ve `simulasyon.kos`'la koşar, `olcutler`'le ölçer; kahinin girdisini `hakem` kurar. Dünyanın gizli
alanlarına kendisi dokunmaz (AST kilidi).

**Kollar** (`KOLLAR`, spec §3.4; `kip` korunumun kipi, `politika.KIPLER`): `tekduze` (takvim; oran
kalibrasyondan), `kural` (serbest; α kalibrasyondan), `opt_tuzak` (serbest, ε̂ markdown), `opt` (serbest, ε̂
kampanya; ana öneri), `opt_takvim` (takvim), `opt_erken_yok` (erken_yok), `opt_taban` (taban), `kahin`
(serbest, gerçek girdi). Yol 0'da sekizi (`YOL0_KOLLARI`), yollar 1–4'te `YOL_KOLLARI` (altısı). Ayrıştırma
kolları (Ruling R24; `politika_ablasyon`, yalnız yol 0, `ablasyon` bloğu, α kalibrasyondan): `kural_takvim`
(erken_yok: pencere indirim günü) ve `kural_deposuz` (serbest: stok raf + yolda).

**Koşular** (`izgara_listesi`; bir koşu tek sezon, Ruling R5). Adlar: Lumoda sezonsuz `lumoda` / `y<p>_lumoda`;
karar kolu `<kol>_<sezon>` (yol 0) / `y<p>_<kol>_<sezon>`; kalibrasyon `kal_<kol>_<değer>_<sezon>` (yol 0;
`kural` α 0,6 → `a060`, 1,25 → `a125`; `tekduze` %30 → `30`). Bloklar: `kalibrasyon` 18 (`kural` α ∈
{0,6; 0,8; 1,0; 1,25; 1,5; 2,0} ve `tekduze` {%30, 40, 50}, AW23 ve SS24; α ızgarası Ruling R20'yle bir kez
aşağı genişletildi: TAM'da 1,0 uçta seçilmişti), `yol0` 1 + 16, `yollar` 4 × 13, `ablasyon` 2 × 2 (Ruling R24;
`hepsi`'ye girmez); toplam 91.

**Yol** (`Yol`, yol başına, tembel). Sıra: (1) yolun Lumoda koşusu `simulasyon.kos(lumoda_adi(p), None,
yol=p, rpt_takvimi=None)`; (2) RPT takvimi `simulasyon.rpt_takvimi(lumoda)` (R4: her kolda bu takvim
oynatılır); (3) öğrenme, iki test sezonu tek bağlantıda, bir kez: `ogrenme.ogren(con, sezon,
OGRENME_BITIS[sezon], onbellek=<ogrenme>, kaynak_kimligi=...)`. TAM yol 0'da `con = kaynak.baglan()` ve
dosyanın varsayılan kimliği; başka her yolda (ve KÜÇÜK dünyada) `con` yolun Lumoda koşusunun yayımlanan
biçimini (`simulasyon.yayimlanan`) tutan DuckDB, `kaynak_kimligi` o koşunun anahtarı (zorunlu: yoksa
öğrenme önbelleği yol p'de yol 0'ın öğrenmesini sessizce okurdu). Yayımlanan biçim `:memory:`'ye kayıt
yerine geçici bir DuckDB dosyasına tablo tablo yazılır (içerik aynı, R10; pandas kopyası öğrenme
sürerken bellekte kalmaz) ve öğrenmeden sonra silinir. (4) Kahin girdisi `hakem.kahin_girdisi(w,
test_idx)`, sezon başına bir kez, yollar arasında paylaşılır (dünya ve λ yollarda aynı; yollar yalnız
müşteri akışını değiştirir, spec §4.4).
(5) Kollar. Kalibrasyon kolları (`kural`, `tekduze`) öğrenme istemez; kalibrasyonda `ogren` çağrılmaz.

**Kalibrasyon** (`kalibrasyon`, spec §4.3, R20). 18 koşu yol 0'da, yol 0 Lumoda'sının RPT takvimiyle; seçim
(`kalibrasyon_sec`) iki sezonun sezon katkısı (`olcutler` `katki`) toplamı en büyük değer, iki sezona
tek değer; korunumu bozuk koşusu olan aday seçilmez; eşitlikte ızgaranın ilk değeri. Sonuç
`kalibrasyon.json` (değer, tablo, ızgara ucunda mı, kalibrasyon sezonlarının en erken serbest karar
günü). Test kolları `tekduze` ve `kural` değeri buradan okur (`kalibrasyon_oku`); değer kolun
`parametreler()`'ine, yani koşu anahtarına girer.

**Ölçüm** (`olcum_kaydi`, `kos_bir`). `oyun.json` `kosular[ad]`: ad, yol, kol, sezon, (kalibrasyonda)
değer, kolun parametreleri (test option listesi yerine sayısı), anahtar, yolun Lumoda anahtarı, ölçüm
kodu, süreler ve ölçüm alanları (`OLCUM_ALANLARI`): `olcutler` (`olcutler.ozetle`, yani `hesapla`), `ceyrek`
(o yolun Lumoda'sının indirim başı STR çeyrekleri), `isabet`, `korunum` (kolun kipiyle), `yan_etki`,
`option_tablosu` (`cikti/olcum/<ad>.parquet`, option başına bileşenler; toplamlar ve rapor için),
`gecerli` (korunumun hepsi True; bozuksa hata verilmez, işaretlenir, rapor reddeder). Lumoda kaydında
`olcutler`, `ceyrek`, `option_tablosu` sezon başına sözlüktür (test sezonları; yol 0'da kalibrasyon
sezonları da). `toplamlar[yol][kol]`: iki test sezonunun option tablolarının birleşiminden `ozetle` (iki
koşunun toplamı; oranlar da doğru), yan etkilerin toplamı, geçerlilik. `yollar[yol]`: kaynak, Lumoda
koşusu, öğrenilenlerin özeti, gerçek ε (Lumoda koşusunun satışıyla, `hakem.gercek_eps`), kahin girdisinin
kimliği.

**Ölçüm önbelleği** (Beden ve Koli R14/R18 kalıbı). Kayıt koşu anahtarı, Lumoda anahtarı ve ölçüm kodu
(`OLCUM_OZETI`: `olcutler.py`, `hakem.py`, bu modülün `OLCUM_FONKSIYONLARI` kaynağı, `KOLLAR`'ın repr'i,
`OLCUM_SURUMU`; içe aktarma anında bir kez) aynıysa ve option tablosu diskteyse yeniden ölçülmez; ölçüm
kodu değiştiyse koşu önbellekten okunur, yalnız ölçüm yenilenir (`olc` bunu bütün önbellekli koşulara
yapar, koşmaz; `olc --zorla` ölçüm kodu aynı olsa da yeniden ölçer). Ölçümü değiştiren ama bu kapsamın
dışında kalan bir düzeltmede `OLCUM_SURUMU` artırılır.
Her koşudan sonra `ilerleme.jsonl`'a bir satır (İlk Sevkiyat `oyun._ilerleme`) ve `oyun.json` yazılır;
koşular sıralı, her koşunun tabloları ölçümden sonra bırakılır (TAM tepe ≈ bir koşu).
"""

import argparse
import functools
import gc
import hashlib
import inspect
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from allocation import motor
from allocation import oyun as al_oyun

from markdown import hakem, kaynak, ogrenme, olcutler, politika, politika_ablasyon, sabitler, simulasyon

CIKTI = simulasyon.PAKET_KOKU.parent / "cikti"
# OLCUM_SURUMU: ölçümü değiştiren ama OLCUM_FONKSIYONLARI, olcutler.py ve hakem.py dışında kalan her
# düzeltmede bir artırılır.
OLCUM_SURUMU = 1
OLCUM_FONKSIYONLARI = ("olcum_kaydi", "toplam_kaydi", "kalibrasyon_sec", "_kayitlar", "Yol.lumoda_tablo",
                       "Yol.lumoda_str")
OLCUM_ALANLARI = ("olcutler", "ceyrek", "isabet", "korunum", "yan_etki", "option_tablosu", "gecerli",
                  "olcum_sn")
LUMODA = "lumoda"
YOLLAR = tuple(range(1, sabitler.YOL_SAYISI))


@dataclass(frozen=True)
class Kol:
    ad: str
    kip: str                    # korunumun kipi (politika.KIPLER)
    eps: str | None             # optimizasyonun ε̂ kaynağı; None: öğrenme istemeyen kol
    aciklama: str


KOLLAR = {k.ad: k for k in (
    Kol("tekduze", "takvim", None, "herkese aynı oran indirim gününden çıkışa (oran kalibrasyondan)"),
    Kol("kural", "serbest", None, "kapsama kuralı, tek eşik α (kalibrasyondan); esneklik bilmez"),
    Kol("opt_tuzak", "serbest", "markdown", "optimizasyon, ε̂ markdown'dan (tuzak)"),
    Kol("opt", "serbest", "kampanya", "optimizasyon, ε̂ kampanyadan, serbest (ana öneri)"),
    Kol("opt_takvim", "takvim", "kampanya", "optimizasyon, takvime bağlı (kontrol)"),
    Kol("opt_erken_yok", "erken_yok", "kampanya", "optimizasyon, indirim gününden önce indirim yok (ayrışım)"),
    Kol("opt_taban", "taban", "kampanya", "optimizasyon, erken başlar, indirim gününden %30 taban (ayrışım)"),
    Kol("kahin", "serbest", "kampanya", "opt'un gerçek talep ve esneklik girdili hâli"),
    Kol("kural_takvim", "erken_yok", None, "kapsama kuralı, karar penceresi indirim günü (ayrışım, Ruling R24)"),
    Kol("kural_deposuz", "serbest", None, "kapsama kuralı, stok yalnız raf + yolda (ayrışım, Ruling R24)"),
)}
YOL0_KOLLARI = ("tekduze", "kural", "opt_tuzak", "opt", "opt_takvim", "opt_erken_yok", "opt_taban", "kahin")
# Ruling R24: kuralın ayrıştırma kolları (yalnız yol 0, `ablasyon` bloğu; α kalibrasyonun seçtiği)
ABLASYON_KOLLARI = ("kural_takvim", "kural_deposuz")
YOL_KOLLARI = ("tekduze", "kural", "opt_tuzak", "opt", "opt_takvim", "kahin")
# Ruling R20: α ızgarası bir kez aşağı genişletildi (TAM 1,0 uçta seçmişti); eski koşuların adı ve anahtarı aynı
KAL_DEGERLERI = {"kural": (0.6, 0.8, 1.0, 1.25, 1.5, 2.0), "tekduze": (0.30, 0.40, 0.50)}
BLOKLAR = ("kalibrasyon", "yol0", "yollar", "ablasyon")


# ---------------------------------------------------------------------------
# Adlar ve ızgara
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kosum:
    """Izgaranın bir koşusu: `deger` kalibrasyon koşusunun α'sı ya da oranı (test kolunda None:
    `kalibrasyon.json`'dan)."""

    ad: str
    yol: int
    kol: str
    sezon: str | None
    deger: float | None = None


def deger_etiketi(kol: str, deger: float) -> str:
    """Kalibrasyon değerinin ad etiketi: `kural` α 1,25 → `a125`, `tekduze` %30 → `30`."""
    n = int(round(100 * float(deger)))
    return f"a{n:03d}" if kol == "kural" else f"{n:02d}"


def kosu_adi(yol: int, kol: str, sezon: str | None = None, deger: float | None = None) -> str:
    """Koşunun adı (modül notu); yanlış bileşim `ValueError`, bilinmeyen kol `KeyError`."""
    yol = int(yol)
    if kol == LUMODA:
        if sezon is not None or deger is not None:
            raise ValueError("Lumoda koşusu sezonsuzdur (bütün option'lar)")
        return simulasyon.lumoda_adi(yol)
    if kol not in KOLLAR:
        raise KeyError(f"bilinmeyen kol: {kol!r}")
    if sezon is None:
        raise ValueError(f"karar kolu tek sezonda koşar (Ruling R5): {kol!r}")
    if deger is not None:
        if kol not in KAL_DEGERLERI or yol != 0 or sezon not in sabitler.KAL_SEZONLARI:
            raise ValueError(f"kalibrasyon yalnız yol 0'da, {sorted(KAL_DEGERLERI)} kollarında ve "
                             f"{sabitler.KAL_SEZONLARI} sezonlarında: {kol!r}, yol {yol}, {sezon!r}")
        return f"kal_{kol}_{deger_etiketi(kol, deger)}_{sezon}"
    if sezon not in sabitler.TEST_SEZONLARI:
        raise ValueError(f"test kolu {sabitler.TEST_SEZONLARI}'den birinde koşar: {sezon!r}")
    if kol in ABLASYON_KOLLARI and yol != 0:
        raise ValueError(f"ayrıştırma kolu yalnız yol 0'da koşar (Ruling R24): {kol!r}, yol {yol}")
    return f"{kol}_{sezon}" if yol == 0 else f"y{yol}_{kol}_{sezon}"


def _kosum(yol: int, kol: str, sezon=None, deger=None) -> Kosum:
    return Kosum(kosu_adi(yol, kol, sezon, deger), int(yol), kol, sezon, deger)


def izgara_listesi(blok: str = "hepsi", yol: int | None = None) -> list[Kosum]:
    """Koşuların sırası: `kalibrasyon`, `yol0`, `yollar`, `ablasyon` ya da `hepsi` (yol0 + yollar; kalibrasyon
    ve ablasyon ayrı bloktur). `yol` verilirse yalnız o yolun koşuları (blokta yoksa `ValueError`)."""
    if blok not in (*BLOKLAR, "hepsi"):
        raise ValueError(f"blok {BLOKLAR} ya da 'hepsi' olmalı: {blok!r}")
    liste: list[Kosum] = []
    if blok == "kalibrasyon":
        liste = [_kosum(0, kol, s, d) for kol, degerler in KAL_DEGERLERI.items() for d in degerler
                 for s in sabitler.KAL_SEZONLARI]
    if blok in ("yol0", "hepsi"):
        liste += [_kosum(0, LUMODA)] + [_kosum(0, kol, s) for s in sabitler.TEST_SEZONLARI for kol in YOL0_KOLLARI]
    if blok == "ablasyon":
        liste = [_kosum(0, kol, s) for s in sabitler.TEST_SEZONLARI for kol in ABLASYON_KOLLARI]
    if blok in ("yollar", "hepsi"):
        for p in YOLLAR:
            liste += [_kosum(p, LUMODA)] + [_kosum(p, kol, s) for s in sabitler.TEST_SEZONLARI
                                            for kol in YOL_KOLLARI]
    if yol is not None:
        yollar = {k.yol for k in liste}
        if int(yol) not in yollar:
            raise ValueError(f"{blok} bloğunda yol {yol} yok (yollar: {sorted(yollar)})")
        liste = [k for k in liste if k.yol == int(yol)]
    return liste


# ---------------------------------------------------------------------------
# Ortam ve kalibrasyon dosyası
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ortam:
    """Koşuların nerede ve nasıl yapıldığı (TAM varsayılan; testler KÜÇÜK dünyada, geçici dizinde)."""

    olcek: str = "tam"
    onbellek: Path = simulasyon.KOSU_DIZINI
    cikti: Path = CIKTI
    ogrenme: Path = CIKTI / "ogrenme"
    gun_sayisi: int | None = None
    ilerleme: bool = True

    @property
    def ilerleme_yolu(self) -> Path | None:
        return Path(self.cikti) / "ilerleme.jsonl" if self.ilerleme else None

    @property
    def oyun_yolu(self) -> Path:
        return Path(self.cikti) / "oyun.json"

    @property
    def kalibrasyon_yolu(self) -> Path:
        return Path(self.cikti) / "kalibrasyon.json"

    def yayimlanan_mi(self, yol: int) -> bool:
        """Yol 0 TAM dünyada yayımlanan DuckDB'den öğrenir; başka her yol Lumoda koşusunun yayımlanan
        biçiminden."""
        return int(yol) == 0 and self.olcek == "tam" and self.gun_sayisi is None


def kalibrasyon_oku(ortam: Ortam) -> dict[str, float]:
    """`kalibrasyon.json`'un seçtiği değerler: {"kural": α, "tekduze": oran}."""
    if not ortam.kalibrasyon_yolu.exists():
        raise FileNotFoundError(f"{ortam.kalibrasyon_yolu} yok: önce `python -m markdown.oyun kalibrasyon`")
    k = al_oyun.json_oku(ortam.kalibrasyon_yolu)
    if k.get("olcek") != ortam.olcek:
        raise ValueError(f"{ortam.kalibrasyon_yolu} {k.get('olcek')!r} ölçeğinde; bu ızgara {ortam.olcek!r}")
    return {"kural": float(k["kural"]["alfa"]), "tekduze": float(k["tekduze"]["oran"])}


def kalibrasyon_sec(kosular: dict) -> dict:
    """Kalibrasyon seçimi (modül notu): kol başına iki kalibrasyon sezonunun `katki` toplamı en büyük
    geçerli değer. Eksik koşu `KeyError`, geçerli aday yoksa `ValueError`."""
    sonuc = {}
    for kol, degerler in KAL_DEGERLERI.items():
        tablo = []
        for d in degerler:
            adlar = [kosu_adi(0, kol, s, d) for s in sabitler.KAL_SEZONLARI]
            eksik = [a for a in adlar if a not in kosular]
            if eksik:
                raise KeyError(f"kalibrasyon koşusu yok: {eksik}")
            r = [kosular[a] for a in adlar]
            satir = {"deger": d, **{s: float(x["olcutler"]["katki"]) for s, x in zip(sabitler.KAL_SEZONLARI, r)},
                     "gecerli": all(bool(x.get("gecerli")) for x in r), "kosular": adlar}
            satir["toplam"] = sum(satir[s] for s in sabitler.KAL_SEZONLARI)
            tablo.append(satir)
        adaylar = [s for s in tablo if s["gecerli"]]
        if not adaylar:
            raise ValueError(f"{kol}: geçerli kalibrasyon adayı yok")
        en_iyi = adaylar[0]
        for s in adaylar[1:]:
            if s["toplam"] > en_iyi["toplam"]:
                en_iyi = s
        ad = "alfa" if kol == "kural" else "oran"
        sonuc[kol] = {ad: en_iyi["deger"], "tablo": tablo,
                      "izgara_ucunda": en_iyi["deger"] in (degerler[0], degerler[-1])}
    return sonuc


# ---------------------------------------------------------------------------
# Yol
# ---------------------------------------------------------------------------


def ogrenilen_ozeti(og: ogrenme.Ogrenilen) -> dict:
    return {"kimlik": og.kimlik(), "bitis": og.bitis.isoformat(), "sezonlar": list(og.sezonlar),
            "eps_kampanya": dict(og.eps_kampanya), "eps_markdown": dict(og.eps_markdown),
            "eps_saf": float(og.eps_saf), "kalinti": float(og.kalinti), "iade": dict(og.iade),
            "islem": float(og.islem)}


class Yol:
    """Bir yolun Lumoda koşusu, RPT takvimi, öğrenilenleri ve kolları (modül notu), tembel.
    `kahin_onbellegi`: yollar arasında paylaşılan kahin girdileri ((ölçek, sezon) → girdi)."""

    def __init__(self, yol: int, ortam: Ortam, kahin_onbellegi: dict | None = None):
        self.yol, self.ortam = int(yol), ortam
        self._kahin = {} if kahin_onbellegi is None else kahin_onbellegi
        self._lumoda_tablolari: dict = {}
        self._gercek_eps: dict = {}

    @functools.cached_property
    def w(self):
        return motor.dunya(self.ortam.olcek)

    @functools.cached_property
    def lumoda(self):
        """Yolun Lumoda koşusu (önbellekten ya da koşulur)."""
        return simulasyon.kos(simulasyon.lumoda_adi(self.yol), None, self.yol, self.ortam.olcek, parametreler={},
                              rpt_takvimi=None, onbellek=self.ortam.onbellek, gun_sayisi=self.ortam.gun_sayisi,
                              tembel=True)

    @functools.cached_property
    def takvim(self):
        """Yolun Lumoda RPT takvimi (Ruling R4)."""
        return simulasyon.rpt_takvimi(self.lumoda)

    @property
    def kaynak_adi(self) -> str:
        """Öğrenmenin tablo kaynağı: "yayimlanan" ya da Lumoda koşusunun dizin adı."""
        return "yayimlanan" if self.ortam.yayimlanan_mi(self.yol) else f"vaka:{self.lumoda.dizin.name}"

    def _baglanti(self, dizin: Path) -> tuple[duckdb.DuckDBPyConnection, str | None]:
        """(bağlantı, öğrenme önbelleğinin kaynak kimliği). Yol p'de yolun Lumoda koşusunun yayımlanan
        biçimi `dizin`'de geçici bir DuckDB dosyasına tablo tablo yazılır ve her DataFrame yazılınca
        bırakılır: öğrenme kendi kesik kopyalarını kurarken yayımlanan biçimin pandas kopyası bellekte
        kalmaz (TAM tepe ≈ bir koşu). İçerik `:memory:`'ye kayıtla aynıdır (Ruling R10)."""
        if self.ortam.yayimlanan_mi(self.yol):
            return kaynak.baglan(), None
        t = simulasyon.yayimlanan(self.lumoda)
        con = duckdb.connect(str(Path(dizin) / f"y{self.yol}_yayimlanan.duckdb"))
        try:
            for ad in sorted(t):
                con.register("_tablo", t.pop(ad))
                con.execute(f"create table {ad} as select * from _tablo")
                con.unregister("_tablo")
                gc.collect()
        except BaseException:
            con.close()                                   # geçici dizin silinebilsin
            raise
        del t
        return con, self.lumoda.meta["anahtar"]

    @functools.cached_property
    def _ogrenilenler(self) -> dict:
        """Test sezonu → (Ogrenilen, süre); iki sezon tek bağlantıda (modül notu)."""
        sonuc = {}
        with tempfile.TemporaryDirectory(prefix="markdown_yol_") as dizin:
            con, kimlik = self._baglanti(Path(dizin))
            try:
                for s in sabitler.TEST_SEZONLARI:
                    t0 = time.perf_counter()
                    og = ogrenme.ogren(con, s, sabitler.OGRENME_BITIS[s], onbellek=self.ortam.ogrenme,
                                       kaynak_kimligi=kimlik)
                    sn = time.perf_counter() - t0
                    sonuc[s] = (og, round(sn, 1))
                    al_oyun._ilerleme(f"y{self.yol}_ogrenme_{s}", sn, False, self.ortam.ilerleme_yolu,
                                      kaynak=self.kaynak_adi, kimlik=og.kimlik(),
                                      surec_tepe_gb=motor._tepe_bellek_gb())
            finally:
                con.close()
                gc.collect()
        return sonuc

    def ogrenilen(self, sezon: str) -> ogrenme.Ogrenilen:
        return self._ogrenilenler[sezon][0]

    def test_idx(self, sezon: str) -> np.ndarray:
        return kaynak.test_optionlari(self.w.optionlar, sezon)

    def kahin_girdisi(self, sezon: str) -> politika.KahinGirdisi:
        anahtar = (self.ortam.olcek, sezon)
        if anahtar not in self._kahin:
            self._kahin[anahtar] = hakem.kahin_girdisi(self.w, self.test_idx(sezon))
        return self._kahin[anahtar]

    def kol_kur(self, k: Kosum, kal: dict | None) -> Callable:
        """`kol_kur(temel)`: kolun nesnesi (spec §3.4). Kalibrasyon koşusu kendi değerini, test kolu
        `kal`'ınkini (`kalibrasyon_oku`) kullanır."""
        idx = self.test_idx(k.sezon)
        kol = KOLLAR[k.kol]
        if kol.ad in ABLASYON_KOLLARI:
            if kal is None:
                raise ValueError(f"{k.ad}: ayrıştırma kolu kalibrasyonun seçtiği α'yı ister (kalibrasyon.json)")
            a, sinif = float(kal["kural"]), politika_ablasyon.KOLLAR[kol.ad]
            return lambda temel: sinif(temel, idx, a)
        if kol.ad in KAL_DEGERLERI:
            if k.deger is None and kal is None:
                raise ValueError(f"{k.ad}: test kolu kalibrasyonun seçtiği değeri ister (kalibrasyon.json)")
            d = float(k.deger if k.deger is not None else kal[kol.ad])
            if kol.ad == "tekduze":
                return lambda temel: politika.Tekduze(temel, idx, d)
            return lambda temel: politika.Kural(temel, idx, d)
        og = self.ogrenilen(k.sezon)
        if kol.ad == "kahin":
            girdi = self.kahin_girdisi(k.sezon)
            return lambda temel: politika.Kahin(temel, idx, og, girdi)
        return lambda temel: politika.Optimizasyon(temel, idx, og, kip=kol.kip, eps=kol.eps)

    def _kos_argumanlari(self, k: Kosum, kal: dict | None) -> dict:
        return dict(ad=k.ad, kol_kur=self.kol_kur(k, kal), yol=self.yol, olcek=self.ortam.olcek,
                    parametreler={"sezon": k.sezon}, rpt_takvimi=self.takvim, gun_sayisi=self.ortam.gun_sayisi)

    def kos(self, k: Kosum, kal: dict | None):
        """Koşunun tembel kaydı (önbellekten ya da koşulur)."""
        if k.kol == LUMODA:
            return self.lumoda
        return simulasyon.kos(**self._kos_argumanlari(k, kal), onbellek=self.ortam.onbellek, tembel=True)

    def onbellekte(self, k: Kosum, kal: dict | None) -> bool:
        """Koşu önbellekte mi (koşmadan; yolun Lumoda'sı önbellekte değilse hiçbiri)."""
        lum = simulasyon.hazirla(simulasyon.lumoda_adi(self.yol), None, self.yol, self.ortam.olcek,
                                 parametreler={}, rpt_takvimi=None, gun_sayisi=self.ortam.gun_sayisi)
        if not simulasyon.onbellekte_mi(lum, self.ortam.onbellek):
            return False
        if k.kol == LUMODA:
            return True
        return simulasyon.onbellekte_mi(simulasyon.hazirla(**self._kos_argumanlari(k, kal)), self.ortam.onbellek)

    # --- ölçüm girdileri ---------------------------------------------------

    def lumoda_tablo(self, sezon: str) -> pd.DataFrame:
        """Lumoda koşusunun `sezon` option tablosu (bir kez)."""
        if sezon not in self._lumoda_tablolari:
            self._lumoda_tablolari[sezon] = olcutler.option_tablosu(self.lumoda, self.w, sezon)
        return self._lumoda_tablolari[sezon]

    def lumoda_str(self, sezon: str) -> pd.Series:
        """Lumoda'nın indirim başı STR'si (çeyreklerin ölçüsü)."""
        return olcutler.indirim_basi_str(self.lumoda, self.w, sezon, tablo=self.lumoda_tablo(sezon))

    def gercek_eps(self, sezon: str) -> dict:
        """Gizli gerçek ε, Lumoda koşusunun indirim dönemi satışıyla ağırlıklı (hakem)."""
        if sezon not in self._gercek_eps:
            so = np.asarray(self.w.sku_option, dtype=np.int64)
            sku = self.w.urunler["urun_id"].astype(str).to_numpy()[np.isin(so, self.test_idx(sezon))]
            satis = self.lumoda.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"], urunler=sku)
            self._gercek_eps[sezon] = hakem.gercek_eps(self.w, satis, sezon)
        return self._gercek_eps[sezon]

    def bilgi(self) -> dict:
        """`oyun.json` `yollar` kaydı (yalnız bu süreçte kurulanlar)."""
        if "lumoda" not in vars(self):
            return {"yol": self.yol}
        b = {"yol": self.yol, "kaynak": self.kaynak_adi, "lumoda": self.lumoda.dizin.name,
             "lumoda_anahtar": self.lumoda.meta["anahtar"], "talep_tohumu": self.lumoda.meta.get("talep_tohumu")}
        if "_ogrenilenler" in vars(self):
            b["ogrenme"] = {s: {**ogrenilen_ozeti(og), "sn": sn, "gercek_eps": self.gercek_eps(s)}
                            for s, (og, sn) in self._ogrenilenler.items()}
        kahin = {s: g.kimlik() for (o, s), g in self._kahin.items() if o == self.ortam.olcek}
        if kahin:
            b["kahin_girdisi"] = kahin
        return b


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def _kayitlar(df: pd.DataFrame) -> list[dict]:
    return [{a: (v.item() if isinstance(v, np.generic) else v) for a, v in r.items()}
            for r in df.to_dict("records")]


def _tablo_yaz(ortam: Ortam, ad: str, t: pd.DataFrame) -> str:
    """Option tablosunu `cikti/olcum/<ad>.parquet`'e yazar; `cikti`'ye göreli yol."""
    goreli = f"olcum/{ad}.parquet"
    yol = Path(ortam.cikti) / goreli
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    t.to_parquet(gecici, index=False)
    gecici.replace(yol)
    return goreli


def lumoda_sezonlari(yol: int) -> tuple[str, ...]:
    """Lumoda kaydının ölçüldüğü sezonlar: test sezonları (yol 0'da kalibrasyon sezonları da)."""
    return sabitler.TEST_SEZONLARI + (sabitler.KAL_SEZONLARI if int(yol) == 0 else ())


def olcum_kaydi(k, Y: Yol, ks: Kosum) -> dict:
    """Bir koşunun ölçüm alanları (modül notu)."""
    w = Y.w
    if ks.kol == LUMODA:
        olc, cey, dosya = {}, {}, {}
        for s in lumoda_sezonlari(ks.yol):
            t = Y.lumoda_tablo(s)
            olc[s] = olcutler.ozetle(t)
            cey[s] = _kayitlar(olcutler.ceyrek(k, w, s, Y.lumoda_str(s), tablo=t))
            dosya[s] = _tablo_yaz(Y.ortam, f"{ks.ad}_{s}", t)
        return {"olcutler": olc, "ceyrek": cey, "option_tablosu": dosya, "gecerli": True}
    s = ks.sezon
    t = olcutler.option_tablosu(k, w, s)
    kor = olcutler.korunum(k, Y.lumoda, KOLLAR[ks.kol].kip, w)
    return {"olcutler": olcutler.ozetle(t),
            "ceyrek": _kayitlar(olcutler.ceyrek(k, w, s, Y.lumoda_str(s), tablo=t)),
            "isabet": olcutler.isabet(k, w), "korunum": kor, "yan_etki": olcutler.yan_etki(k, Y.lumoda, w, s),
            "option_tablosu": _tablo_yaz(Y.ortam, ks.ad, t), "gecerli": all(bool(v) for v in kor.values())}


def _tablolar_var(ortam: Ortam, kayit: dict) -> bool:
    d = kayit.get("option_tablosu")
    yollar = list(d.values()) if isinstance(d, dict) else [d]
    return bool(yollar) and all(isinstance(y, str) and (Path(ortam.cikti) / y).exists() for y in yollar)


def _saf(x):
    """JSON'a yazılan biçim (numpy türleri Python'a); bellekteki kayıt diskteki kayıtla aynı olsun."""
    if isinstance(x, dict):
        return {str(a): _saf(v) for a, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_saf(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    return x


def _kol_parametreleri(k) -> dict:
    p = dict(((k.meta.get("politikalar") or {}).get("markdown") or {}).get("parametreler") or {})
    if "test_optionlari" in p:
        p["test_option_sayisi"] = len(p.pop("test_optionlari"))
    return p


def olcum_kodu() -> str:
    """Ölçüm kodunun özeti (modül notu; içe aktarma anında kurulan `OLCUM_OZETI`)."""
    return OLCUM_OZETI


def kos_bir(ks: Kosum, Y: Yol, kal: dict | None, onceki: dict | None = None, zorla: bool = False) -> dict:
    """Koşu (önbellekten ya da yeni) ve ölçüm; kayıt sözlüğü (modül notu). `onceki` (bu koşunun eski
    kaydı) koşu anahtarı, Lumoda anahtarı ve ölçüm kodu tutar ve option tablosu diskteyse yeniden
    ölçülmez (`zorla` ile her zaman ölçülür)."""
    if ks.yol != Y.yol:
        raise ValueError(f"{ks.ad}: yol {ks.yol}, Yol {Y.yol}")
    t0 = time.perf_counter()
    k = Y.kos(ks, kal)
    t1 = time.perf_counter()
    kod = olcum_kodu()
    lum = Y.lumoda.meta["anahtar"]
    if (not zorla and onceki and onceki.get("anahtar") == k.meta["anahtar"] and onceki.get("olcum_kodu") == kod
            and onceki.get("lumoda_anahtar") == lum and _tablolar_var(Y.ortam, onceki)):
        olcum, olculdu = {a: onceki[a] for a in OLCUM_ALANLARI if a in onceki}, False
    else:
        olcum, olculdu = olcum_kaydi(k, Y, ks) | {"olcum_sn": round(time.perf_counter() - t1, 1)}, True
    kayit = _saf({"ad": ks.ad, "yol": ks.yol, "kol": ks.kol, "sezon": ks.sezon, "deger": ks.deger,
                  "kalibrasyon": ks.deger is not None,
                  "aciklama": "Lumoda (v4 kuralı)" if ks.kol == LUMODA else KOLLAR[ks.kol].aciklama,
                  "parametreler": _kol_parametreleri(k), "anahtar": k.meta["anahtar"], "lumoda_anahtar": lum,
                  "olcum_kodu": kod, "talep_tohumu": k.meta.get("talep_tohumu"),
                  "motor_sn": k.meta.get("motor_sn"), "kosu_sn": k.meta.get("sure_sn"),
                  "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"), **olcum})
    onbellekten = bool(k.onbellekten)
    del k
    gc.collect()
    o = kayit["olcutler"]
    katki = o.get("katki") if ks.kol != LUMODA else {s: v["katki"] for s, v in o.items()}
    al_oyun._ilerleme(ks.ad, time.perf_counter() - t0, onbellekten, Y.ortam.ilerleme_yolu,
                      olculdu=olculdu, motor_sn=kayit["motor_sn"], tepe_gb=kayit["tepe_bellek_gb"],
                      olcum_sn=kayit.get("olcum_sn"), surec_tepe_gb=motor._tepe_bellek_gb(),
                      katki=katki, gecerli=kayit["gecerli"])
    return kayit


def toplam_kaydi(kosular: dict, ortam: Ortam) -> dict:
    """`toplamlar[yol][kol]`: iki test sezonunun toplamı (modül notu); kaydı eksik ya da ölçüm kodu
    farklı olan (yol, kol) girmez."""
    sonuc: dict = {}
    for yol in (0, *YOLLAR):
        for kol in (LUMODA, *(YOL0_KOLLARI + ABLASYON_KOLLARI if yol == 0 else YOL_KOLLARI)):
            if kol == LUMODA:
                r = kosular.get(kosu_adi(yol, LUMODA))
                if not r or not _tablolar_var(ortam, r):
                    continue
                dosyalar, kayitlar = [r["option_tablosu"].get(s) for s in sabitler.TEST_SEZONLARI], [r]
                if None in dosyalar:
                    continue
                yan = None
            else:
                kayitlar = [kosular.get(kosu_adi(yol, kol, s)) for s in sabitler.TEST_SEZONLARI]
                if not all(kayitlar) or not all(_tablolar_var(ortam, r) for r in kayitlar):
                    continue
                dosyalar = [r["option_tablosu"] for r in kayitlar]
                yan = {a: sum(float(r["yan_etki"][a]) for r in kayitlar) for a in kayitlar[0]["yan_etki"]}
            if len({r["olcum_kodu"] for r in kayitlar}) != 1:
                continue
            t = pd.concat([pd.read_parquet(Path(ortam.cikti) / d) for d in dosyalar], ignore_index=True)
            sonuc.setdefault(str(yol), {})[kol] = {
                "olcutler": olcutler.ozetle(t), **({"yan_etki": yan} if yan is not None else {}),
                "gecerli": all(bool(r["gecerli"]) for r in kayitlar), "kosular": [r["ad"] for r in kayitlar]}
    return _saf(sonuc)


def kos_hepsi(blok: str = "hepsi", ortam: Ortam | None = None, *, adlar=None, yol: int | None = None,
              sadece_onbellek: bool = False, zorla: bool = False) -> dict:
    """Izgarayı (`izgara_listesi(blok, yol)`; `adlar` verilirse yalnız o koşu adları ya da kollar) sırayla
    koşar ve ölçer; her koşudan sonra `oyun.json`. Yeniden başlatılan ızgara önbellekten sürer.
    `sadece_onbellek`: önbellekte olmayan koşu koşulmaz, atlanır (`olc`); `zorla`: kayıt tutsa da ölçülür."""
    ortam = Ortam() if ortam is None else ortam
    liste = [k for k in izgara_listesi(blok, yol)
             if adlar is None or k.ad in adlar or k.kol in adlar]
    kayit = al_oyun.json_oku(ortam.oyun_yolu)
    if kayit.get("olcek", ortam.olcek) != ortam.olcek:
        raise ValueError(f"{ortam.oyun_yolu} {kayit['olcek']} ölçeğinde; bu ızgara {ortam.olcek}")
    kayit["olcek"] = ortam.olcek
    kosular, yollar = kayit.setdefault("kosular", {}), kayit.setdefault("yollar", {})
    kal = kalibrasyon_oku(ortam) if any((k.kol in KAL_DEGERLERI or k.kol in ABLASYON_KOLLARI) and k.deger is None
                                        for k in liste) else None
    Y, kahin = None, {}
    for ks in liste:
        if Y is None or Y.yol != ks.yol:
            Y = None
            gc.collect()                                  # önceki yolun tabloları bırakılır
            Y = Yol(ks.yol, ortam, kahin)
        if sadece_onbellek and not Y.onbellekte(ks, kal):
            al_oyun._ilerleme(ks.ad, 0.0, False, ortam.ilerleme_yolu, atlandi="önbellekte yok")
            continue
        kosular[ks.ad] = kos_bir(ks, Y, kal, kosular.get(ks.ad), zorla=zorla)
        yollar[str(Y.yol)] = {**yollar.get(str(Y.yol), {}), **Y.bilgi()}
        kayit["toplamlar"] = toplam_kaydi(kosular, ortam)
        al_oyun.json_yaz(ortam.oyun_yolu, kayit)
    return kayit


def en_erken_karar(w, sezon: str) -> str:
    """Sezonun Collection option'larının en erken serbest karar günü (tarih; kalibrasyon kayıtları için,
    `OGRENME_BITIS`'in kalibrasyon sezonlarındaki karşılığı)."""
    g = int(kaynak.karar_penceresi(w.optionlar, kaynak.test_optionlari(w.optionlar, sezon), "serbest").min())
    return str(np.datetime64(sabitler.GUN_SIFIRI, "D") + np.timedelta64(g, "D"))


def kalibrasyon(ortam: Ortam | None = None, sadece_onbellek: bool = False, zorla: bool = False) -> dict:
    """18 kalibrasyon koşusu, seçim ve `kalibrasyon.json` (modül notu)."""
    ortam = Ortam() if ortam is None else ortam
    kayit = kos_hepsi("kalibrasyon", ortam, sadece_onbellek=sadece_onbellek, zorla=zorla)
    sec = kalibrasyon_sec(kayit["kosular"])
    w = motor.dunya(ortam.olcek)
    sec = {"olcek": ortam.olcek, **sec, "olcum_kodu": olcum_kodu(),
           "lumoda_anahtar": kayit["kosular"][kosu_adi(0, "kural", sabitler.KAL_SEZONLARI[0], 1.0)]["lumoda_anahtar"],
           "olcut": "katki (iki kalibrasyon sezonunun toplamı)",
           "en_erken_karar": {s: en_erken_karar(w, s) for s in sabitler.KAL_SEZONLARI}}
    al_oyun.json_yaz(ortam.kalibrasyon_yolu, sec)
    return sec


# ---------------------------------------------------------------------------
# Ölçüm kodunun özeti
# ---------------------------------------------------------------------------


def olcum_metinleri() -> dict[str, str]:
    """Ölçüm özetinin girdileri: `olcutler.py`, `hakem.py`, `OLCUM_FONKSIYONLARI` kaynağı, `KOLLAR`'ın
    repr'i (korunum kipi) (satır sonları LF)."""
    m = {Path(y).name: Path(y).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
         for y in (olcutler.__file__, hakem.__file__)}
    for ad in OLCUM_FONKSIYONLARI:
        nesne = globals()[ad.split(".")[0]]
        for parca in ad.split(".")[1:]:
            nesne = vars(nesne)[parca]
        m[ad] = inspect.getsource(nesne).replace("\r\n", "\n")
    m["KOLLAR"] = repr(KOLLAR)
    return m


def olcum_ozeti(metinler: dict[str, str], surum: int) -> str:
    h = hashlib.sha256()
    for ad in sorted(metinler):
        h.update(ad.encode("utf-8") + b"\0" + metinler[ad].encode("utf-8") + b"\0")
    h.update(f"surum={int(surum)}".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _ortam(olcek: str) -> Ortam:
    olcek = olcek.lower()
    return Ortam(olcek=olcek, cikti=CIKTI if olcek == "tam" else CIKTI / "kucuk")


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m markdown.oyun")
    alt = ap.add_subparsers(dest="komut", required=True)
    ka = alt.add_parser("kalibrasyon", help="18 kalibrasyon koşusu ve cikti/kalibrasyon.json")
    iz = alt.add_parser("izgara", help="test ızgarası (cikti/oyun.json, cikti/ilerleme.jsonl)")
    iz.add_argument("--blok", default="hepsi", choices=["yol0", "yollar", "ablasyon", "hepsi"])
    iz.add_argument("--yol", type=int, default=None, help="yalnız bu yol")
    iz.add_argument("--ad", action="append", help="yalnız bu koşu(lar) ya da kol(lar) (tekrarlanabilir)")
    ol = alt.add_parser("olc", help="önbellekteki bütün koşuları yeniden ölç (koşmaz)")
    ol.add_argument("--zorla", action="store_true", help="ölçüm kodu aynı olsa da yeniden ölç")
    for p in (ka, iz, ol):
        p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = ap.parse_args(argv)
    al_oyun.uyanik_tut()
    t0 = time.perf_counter()
    ortam = _ortam(a.olcek)
    if a.komut == "kalibrasyon":
        sec = kalibrasyon(ortam)
        print(f"kalibrasyon: α {sec['kural']['alfa']}, tekdüze {sec['tekduze']['oran']}", flush=True)
    elif a.komut == "izgara":
        kos_hepsi(a.blok, ortam, adlar=None if a.ad is None else set(a.ad), yol=a.yol)
    else:
        kalibrasyon(ortam, sadece_onbellek=True, zorla=a.zorla)
        kos_hepsi("hepsi", ortam, sadece_onbellek=True, zorla=a.zorla)
        kos_hepsi("ablasyon", ortam, sadece_onbellek=True, zorla=a.zorla)
    print(f"{a.komut} bitti: {time.perf_counter() - t0:.0f} sn", flush=True)


# Ölçüm kodunun özeti, içe aktarma anında bir kez (bütün işlevler tanımlandıktan sonra)
OLCUM_OZETI = olcum_ozeti(olcum_metinleri(), OLCUM_SURUMU)


if __name__ == "__main__":
    main()
