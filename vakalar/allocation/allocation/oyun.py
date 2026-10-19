"""Oyun: kolları v4 motorunda oyun sezonunda (SS25) koşturur ve ölçer (spec §4.5); kalibrasyonun
koşucusu da burada (Ruling R22).

    .venv/Scripts/python -m allocation.oyun                         # ızgara, bütün bloklar sırayla
    .venv/Scripts/python -m allocation.oyun izgara --blok pay       # tek blok
    .venv/Scripts/python -m allocation.oyun kalibrasyon             # cikti/kalibrasyon.json (Görev 7)

Bu modül koşu dışıdır (`motor.KOSU_DISI`): motoru içe aktarır, gizli gerçeği okur
(`tests/test_sizinti.py` izinli listesi). Ölçütler `olcutler`'de.

**Izgara** (`IZGARA`; adlar tekil, `tests/test_oyun.py`). Bütün kollar `Ayar.sezon = OYUN_SEZONU`,
yol 0 (yayımlanan dünya), replenishment Lumoda, RPT ve markdown Lumoda'nın tepkili kararı, aksi
yazılmadıkça. Tutma oranı t gönderilebilir üst sınır U'ya göredir (spec §0/9); "tutma %30" (spec
§4.5 pay bloğu) Lumoda'nın kendi %30'udur, U'ya göre t = 0 (Ruling R27). `tavan` boşsa
kalibrasyonun seçimi (`kalibrasyon.json`), yalnız benzer ve tahminde etkin.

    esdegerlik    lumoda: Lumoda + kaydediciler, yayımlanan v4'ün kendisi (tests/test_esdegerlik.py)
    pay           esit, benzer tavanlı / tavansız, tahmin tavanlı / tavansız, kahin (t = 0)
    sabit_takvim  lumoda_takvimli (lumoda'nın RPT ve markdown kararlarını oyun option'larında
                  yeniden oynatır; eşdeğerlik testiyle aynı koşu) + esit, benzer, tahmin, kahin aynı
                  takvimle (`politika.TakvimRPT`, `TakvimMarkdown`)
    tutma         t ∈ TUTMA_DUZEYLERI × pay {lumoda_tut, en iyi} × replenishment {Lumoda, hiz}
                  (16; t = 0 dahil: lumoda_tut t = 0 Lumoda'nın U'ya sığdırılmış hâli, Ruling R28)
    strateji      belirsizlik: pay ve tavan en iyiden, t_o option başına (t̄ = %30); karşılığı
                  tut_eniyi_t30
    demo          esit, benzer, tahmin × DEMO_TUTMA'nın t > 0'ları (öteki demo noktaları
                  başka bloklarda; `demo_haritasi`)

"En iyi" (`secim_yap`, Ruling R29): pay bloğunun benzer ve tahmin kollarından (kalibrasyonun tavan
seçimiyle) `kalibrasyon.secim` kuralıyla (bulunabilirliği en yüksek olanın 0,3 puandan az
gerisindekiler arasında sezon sonu kalanı en düşük olan); pay bloğundan sonra `cikti/secim.json`.
tutma, strateji ve demo bunu okur: ızgara blok sırasıyla koşar (`BLOK_SIRASI`).

**Aynı koşu iki adla** (`imza`): kolun çözülmüş tanımı (en iyi, kalibrasyonun tavanı, etkisiz
alanlar) aynı olan iki `Kosum` bir kez koşulur; ikincisinin kaydı `ayni` alanıyla ilkine bağlanır
(ör. tut_eniyi_t00 = pay bloğundaki en iyi, demo_<en iyi>_t15 = tut_eniyi_t15).

**Girdiler** (`Girdi`, yol başına, tembel; sonuçları kollara `parametreler()` üstünden girer):
öğrenme tablosu oyun sezonunun en erken ilk dağıtım kararı gününde (`kalibrasyon.karar_gunu`)
kapanmış sezonlardan (`ogrenme.ogrenme_tablosu`); yol 0 TAM'da yayımlanan DuckDB'den, başka yolda
yolun `lumoda` koşusunun yayımlanan biçiminden (`motor.yayimlanan_bicim`). `benzer.ogren(...,
en_az, mevsim=<sezonun mevsimi>)` ve `tahmin.Tahminci.egit(..., tahmin_parametreleri)`
kalibrasyonun seçimleriyle. Kahinin sözlüğü yolun `lumoda` koşusunun erken birincil talebi
(`olcutler.erken_birincil_talep`); sabit takvim `motor.takvim(lumoda)`. Belirsizliğin `t_o`'su
kalibrasyonun ölçüsüyle (`kalibrasyon.belirsizlik_olculeri`) ve `kalibrasyon.tutma_egrisi`
(ağırlık ilk alım, t̄ = %30); γ kalibrasyonun seçimi, ölçünün Spearman'ı ≤ 0 ise 0 (sabit tutma).

**Koşu ve ölçüm** (`kos_bir`). `motor.kos(..., tembel=True)`, önbellek `cikti/kosular/`, sıralı;
`parametreler` boş (kolun bütün ayarı ve öğrenilmiş girdilerin içerik kimliği kolun
`parametreler()`'inde, anahtara kendiliğinden girer). `olcutler.hesapla` korunumu da sınar
(kolun kararını motor kırptıysa `RuntimeError`, Ruling R21). Sonuç `cikti/oyun.json`'a (ad →
grup, kosum, çözüm, imza, anahtar, ölçütler) her koşudan sonra; biten her koşu
`cikti/ilerleme.jsonl`'a. Yeniden başlatılan ızgara önbellekten sürer; anahtarı ve ölçüm kodu
(`olcum_kodu`) aynı kayıt yeniden ölçülmez. Uzun koşuda makine uyumaz (`uyanik_tut`).

**Kalibrasyon** (`kalibrasyon_kos`, Görev 7). Yol 0, TAM: dünya, yayımlanan tablolar →
`kalibrasyon.kosusuz` → `kalibrasyon.simulasyon(kalibrasyon_kosucusu(...))` → `cikti/kalibrasyon.json`.
`lumoda` referansı eşdeğerlik koşusudur. Kol koşusunda kalibrasyon sezonunun option'larına süzülmüş
`kirpma_tablosu` boş olmalı (Ruling R21). Ölçütler `kal_olcutleri`: `olcutler.bulunabilirlik` ve
`olcutler.sezon_sonu_kalan_yuzde` (tanımlar `olcutler` modül notunda; Ruling R23'ün tanımı + çıkış
sonrası depo eki ve varışı olmayan option'ın lansmandan sayılması, Görev 7 notları).
"""

import argparse
import functools
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from allocation import benzer, kalibrasyon, kaynak, motor, ogrenme, olcutler, sabitler, tahmin
from allocation.politika import (Ayar, BelirsizlikKol, BenzerKol, EsitKol, HizReplenishment, KahinKol,
                                 LumodaTutKol, TahminKol, TakvimMarkdown, TakvimRPT)

ILERLEME = sabitler.CIKTI / "ilerleme.jsonl"
ESDEGERLIK = "lumoda"
TAKVIMLI = "lumoda_takvimli"
BLOK_SIRASI = ("esdegerlik", "pay", "sabit_takvim", "tutma", "strateji", "demo")
SECIM_GEREKEN = ("tutma", "strateji", "demo")
KOLLAR = ("lumoda", "lumoda_tut", "esit", "benzer", "tahmin", "kahin", "belirsizlik", "eniyi")
TAVANLI = ("benzer", "tahmin")
OLCUM_SURUMU = 1


def uyanik_tut() -> None:
    """Windows'ta süreç sürdükçe sistem uykusunu engeller (başka yerde etkisiz)."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def talep_tohumu(yol: int, taban: int = sabitler.TALEP_TOHUM_TABANI) -> int | None:
    """Yolun talep tohumu: yol 0 yayımlanan dünya (None), yol p > 0 `taban + p`."""
    return None if int(yol) == 0 else int(taban) + int(yol)


def _ilerleme(ad: str, sn: float, onbellekten: bool, dosya: Path | None = ILERLEME, **ek) -> None:
    satir = {"ad": ad, "sn": round(float(sn), 1), "onbellekten": bool(onbellekten),
             "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), **ek}
    print(json.dumps(satir, ensure_ascii=False, default=str), flush=True)
    if dosya is not None:
        Path(dosya).parent.mkdir(parents=True, exist_ok=True)
        with open(dosya, "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False, default=str) + "\n")


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _dosya_ozeti(*yollar) -> str:
    return _sha({Path(y).name: hashlib.sha256(Path(y).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                 for y in yollar})


def _json_degeri(x):
    if isinstance(x, (np.integer, np.floating, np.bool_)):
        return x.item()
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    raise TypeError(type(x).__name__)


def json_yaz(yol: Path, icerik: dict) -> None:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(json.dumps(icerik, ensure_ascii=False, indent=1, default=_json_degeri), encoding="utf-8")
    gecici.replace(yol)


def json_oku(yol: Path) -> dict:
    yol = Path(yol)
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


# ---------------------------------------------------------------------------
# Kalibrasyon ölçütleri ve koşucusu (Görev 7)
# ---------------------------------------------------------------------------


def kal_olcutleri(kosu, w, harita, sezon: str = sabitler.KAL_SEZONU) -> dict[str, float]:
    """Koşunun kalibrasyon ölçütleri (`olcutler`'in tanımları), `sezon`un `LINE` hücrelerinde."""
    opt = kaynak.oyun_optionlari(w, sezon)
    sku = olcutler.Kapsam(w, harita, opt).skular
    sevk = kosu.tablo("sevkiyat", olcutler.SEVK, urunler=sku)
    gercek = kosu.tablo("gercek", ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis"], urunler=sku)
    siparis = kosu.tablo("siparis", ["siparis_id", "tip", "option_id", "gerceklesen_teslim", "adet"])
    kalite = kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"])
    depo = kosu.tablo("depo_stok", ["tarih", "urun_id", "adet"], urunler=sku)
    return {"bulunabilirlik": olcutler.bulunabilirlik(gercek, sevk, w, harita, opt),
            "sezon_sonu_kalan_yuzde": olcutler.sezon_sonu_kalan_yuzde(sevk, siparis, kalite, w, harita, opt, depo)}


def kalibrasyon_kosucusu(cev: kalibrasyon.Cevrimdisi, w, harita, *, onbellek: Path | None = motor.KOSU_DIZINI,
                         olcek: str = "tam", gun_sayisi: int | None = None, sezon: str = sabitler.KAL_SEZONU,
                         ilerleme: Path | None = ILERLEME):
    """`kalibrasyon.simulasyon`'un `kos_fn(ad, tanim) -> dict`'i: kolu kurar (`kalibrasyon.kol_kur`,
    temel Lumoda'nın ilk dağıtımı), yol 0'da koşar, kırpmayı denetler, ölçer. `olcek`, `gun_sayisi`,
    `sezon` testler içindir."""
    ids = set(w.optionlar["option_id"].astype(str).to_numpy()[kaynak.oyun_optionlari(w, sezon)])

    def kos_fn(ad: str, tanim: kalibrasyon.KalKol) -> dict:
        t0 = time.perf_counter()
        kol = kalibrasyon.kol_kur(tanim, cev, motor.lumoda("ilk_dagitim"), harita)
        ortak = {"onbellek": onbellek, "olcek": olcek, "gun_sayisi": gun_sayisi, "tembel": True}
        if kol is None:
            k = motor.kos(ad="lumoda", parametreler={}, **ortak)
        else:
            k = motor.kos(ilk_dagitim=kol, ad=ad, parametreler=tanim.parametreler(), **ortak)
            kirp = motor.kirpma_tablosu(k, w)
            kirp = kirp[kirp["option_id"].astype(str).isin(ids).to_numpy()]
            if len(kirp):
                raise RuntimeError(f"{ad}: motor kalibrasyon option'larında {len(kirp)} (option, mağaza) "
                                   "kırptı (kollar U'ya sığmalı; Ruling R21)")
        olcut = kal_olcutleri(k, w, harita, sezon)
        sure = time.perf_counter() - t0
        ek = {"sure_sn": round(sure, 1), "motor_sn": k.meta.get("motor_sn"), "kosu_sn": k.meta.get("sure_sn"),
              "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"), "onbellekten": bool(k.onbellekten),
              "anahtar": k.meta["anahtar"]}
        _ilerleme(ad, sure, k.onbellekten, ilerleme, blok="kalibrasyon", **olcut)
        return {**olcut, **ek}

    return kos_fn


def kalibrasyon_kos(yol: Path = kalibrasyon.DOSYA) -> dict:
    """Gerçek kalibrasyon (yol 0, TAM): koşusuz seçim, sonra 7 TAM koşu (+ önbellekli `lumoda`)."""
    t0 = time.perf_counter()
    w = motor.dunya("tam")
    harita = kaynak.harita_kur(w)
    con = kaynak.baglan()
    try:
        tablolar = kaynak.yayimlanan_tablolar(con)
    finally:
        con.close()
    cev = kalibrasyon.kosusuz(tablolar, w)
    del tablolar
    t1 = time.perf_counter()
    print(f"koşusuz: {t1 - t0:.0f} sn; en_az {cev.en_az}, tahmin {cev.tahmin_parametreleri}, "
          f"kaynak {cev.kaynak}, ölçü {cev.belirsizlik_olcusu}", flush=True)
    sim = kalibrasyon.simulasyon(kalibrasyon_kosucusu(cev, w, harita), cev)
    t2 = time.perf_counter()
    kalibrasyon.yaz(cev, sim, yol, kosusuz_sn=round(t1 - t0, 1), simulasyon_sn=round(t2 - t1, 1),
                    sure_sn=round(t2 - t0, 1))
    return kalibrasyon.oku(yol)


# ---------------------------------------------------------------------------
# Izgara
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kosum:
    """Bir ızgara koşusu (modül notu).

    kol     `KOLLAR`: "lumoda" (Lumoda'nın kendisi), "lumoda_tut", "esit", "benzer", "tahmin",
            "kahin", "belirsizlik" (taban en iyi), "eniyi" (`secim.json`'un kolu)
    tutma   t (U'ya göre; belirsizlikte yok sayılır, t_o)
    tavan   kapsama tavanı; None kalibrasyonun seçimi (yalnız benzer ve tahminde etkin)
    repl    "lumoda" | "hiz" (`politika.HizReplenishment`)
    takvim  sabit takvim: lumoda koşusunun RPT ve markdown kararları oyun option'larında
    yol     talep yolu (`talep_tohumu`)"""

    ad: str
    kol: str
    tutma: float = 0.0
    tavan: bool | None = None
    repl: str = "lumoda"
    takvim: bool = False
    yol: int = 0

    def __post_init__(self):
        if self.kol not in KOLLAR:
            raise ValueError(f"bilinmeyen kol: {self.kol!r}")
        if self.repl not in ("lumoda", "hiz"):
            raise ValueError(f"bilinmeyen replenishment: {self.repl!r}")
        if self.kol == "lumoda" and (self.tutma or self.repl != "lumoda"):
            raise ValueError("lumoda kolu Lumoda'nın kendisidir: tutma ve hiz için lumoda_tut")


def _t(t: float) -> str:
    return f"t{round(t * 100):02d}"


def _tutma() -> tuple[Kosum, ...]:
    return tuple(Kosum(f"tut_{kaynak}_{_t(t)}{'_hiz' if r == 'hiz' else ''}",
                       "lumoda_tut" if kaynak == "lumoda" else "eniyi", tutma=t, repl=r)
                 for kaynak in ("lumoda", "eniyi") for t in sabitler.TUTMA_DUZEYLERI for r in ("lumoda", "hiz"))


IZGARA: dict[str, tuple[Kosum, ...]] = {
    "esdegerlik": (Kosum(ESDEGERLIK, "lumoda"),),
    "pay": (Kosum("pay_esit", "esit"),
            Kosum("pay_benzer_tavanli", "benzer", tavan=True), Kosum("pay_benzer_tavansiz", "benzer", tavan=False),
            Kosum("pay_tahmin_tavanli", "tahmin", tavan=True), Kosum("pay_tahmin_tavansiz", "tahmin", tavan=False),
            Kosum("pay_kahin", "kahin")),
    "sabit_takvim": (Kosum(TAKVIMLI, "lumoda", takvim=True), Kosum("sabit_esit", "esit", takvim=True),
                     Kosum("sabit_benzer", "benzer", takvim=True), Kosum("sabit_tahmin", "tahmin", takvim=True),
                     Kosum("sabit_kahin", "kahin", takvim=True)),
    "tutma": _tutma(),
    "strateji": (Kosum("belirsizlik", "belirsizlik"),),
    "demo": tuple(Kosum(f"demo_{k}_{_t(t)}", k, tutma=t) for k in ("esit", "benzer", "tahmin")
                  for t in sabitler.DEMO_TUTMA if t > 0),
}

# Yollar (`allocation.yollar`): yol başına koşulan kollar (kısa ad → yol 0'daki ızgara koşusu)
YOL_KOLLARI = ("lumoda", "esit", "benzer", "tahmin", "kahin")


def tum_kosumlar() -> dict[str, Kosum]:
    return {s.ad: s for blok in IZGARA.values() for s in blok}


def lumoda_adi(yol: int) -> str:
    return ESDEGERLIK if int(yol) == 0 else f"y{int(yol)}_{ESDEGERLIK}"


def yol_listesi(yol: int, kal: dict) -> list[tuple[str, Kosum]]:
    """(kısa ad, `Kosum`): yol 0'da ızgaranın koşuları (aynı anahtar), yol p'de `y<p>_` önekiyle."""
    if int(yol) == 0:
        tavan = "tavanli" if kal["tavan"] else "tavansiz"
        tum = tum_kosumlar()
        adlar = {"lumoda": ESDEGERLIK, "esit": "pay_esit", "benzer": f"pay_benzer_{tavan}",
                 "tahmin": f"pay_tahmin_{tavan}", "kahin": "pay_kahin"}
        return [(k, tum[adlar[k]]) for k in YOL_KOLLARI]
    return [(k, Kosum(lumoda_adi(yol) if k == "lumoda" else f"y{yol}_{k}", k, yol=int(yol))) for k in YOL_KOLLARI]


def kosu_sayisi() -> dict[str, int]:
    """Izgaranın (yol 0, adlar; aynı koşu iki adla sayılır: üst sınır) ve yolların koşu sayısı."""
    yol0 = sum(len(b) for b in IZGARA.values())
    return {"yol0": yol0, "yollar": (sabitler.YOL_SAYISI - 1) * len(YOL_KOLLARI),
            "toplam": yol0 + (sabitler.YOL_SAYISI - 1) * len(YOL_KOLLARI)}


def cozumle(s: Kosum, kal: dict, secim: dict | None) -> dict:
    """Kosum'un çözülmüş tanımı: en iyi kol, kalibrasyonun tavanı, etkisiz alanlar kapalı. İki
    `Kosum`un çözümü aynıysa aynı koşudur (`imza`)."""
    kol = s.kol
    if kol in ("eniyi", "belirsizlik"):
        if secim is None:
            raise RuntimeError(f"{s.ad}: en iyi kol seçilmedi (önce pay bloğu; cikti/secim.json)")
    taban = secim["kol"] if kol == "belirsizlik" else None
    if kol == "eniyi":
        kol = secim["kol"]
    tavan_kol = taban or kol
    tavan = bool(kal["tavan"] if s.tavan is None else s.tavan) if tavan_kol in TAVANLI else False
    tutma = None if kol == "belirsizlik" else float(s.tutma)
    return {"kol": kol, "taban": taban, "tutma": tutma, "tavan": tavan, "repl": s.repl, "takvim": bool(s.takvim),
            "yol": int(s.yol)}


def imza(cozum: dict) -> str:
    return _sha(cozum)[:20]


# ---------------------------------------------------------------------------
# Ortam ve girdiler
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Ortam:
    """Koşuların nerede ve nasıl yapıldığı (TAM, oyun sezonu varsayılan; testler KÜÇÜK dünyada)."""

    olcek: str = "tam"
    onbellek: Path = motor.KOSU_DIZINI
    cikti: Path = sabitler.CIKTI
    gun_sayisi: int | None = None
    sezon: str = sabitler.OYUN_SEZONU
    ilerleme: bool = True

    @property
    def ilerleme_yolu(self) -> Path | None:
        return Path(self.cikti) / "ilerleme.jsonl" if self.ilerleme else None

    @property
    def oyun_yolu(self) -> Path:
        return Path(self.cikti) / "oyun.json"

    @property
    def secim_yolu(self) -> Path:
        return Path(self.cikti) / "secim.json"

    def yayimlanan_mi(self, yol: int) -> bool:
        """Yol 0 TAM dünyada yayımlanan DuckDB'den öğrenir; başka her yol lumoda koşusunun yayımlanan
        biçiminden."""
        return int(yol) == 0 and self.olcek == "tam" and self.gun_sayisi is None

    def kos(self, yol: int, ad: str, **politikalar):
        return motor.kos(**politikalar, ad=ad, parametreler={}, talep_tohumu=talep_tohumu(yol),
                         onbellek=self.onbellek, olcek=self.olcek, gun_sayisi=self.gun_sayisi, tembel=True)


def belirsizlik_gammasi(kal: dict) -> float:
    """Kalibrasyonun γ'sı; seçilen belirsizlik ölçüsünün Spearman'ı ≤ 0 (ya da yok) ise 0: sinyal
    yoksa eğri düzdür, belirsizlik kolu sabit t̄ tutar (Görev 7 notu)."""
    rho = kal.get("belirsizlik_spearman")
    return float(kal["gamma"]) if rho is not None and np.isfinite(rho) and rho > 0 else 0.0


class Girdi:
    """Bir yolun kollara giden öğrenilmiş girdileri (modül notu), tembel; testler doğrudan verebilir
    (`endeks=`, `tahminci=`, `kahin=`, `t_o=`)."""

    def __init__(self, yol: int, ortam: Ortam, kal: dict, **verilen):
        self.yol, self.ortam, self.kal = int(yol), ortam, kal
        bilinmeyen = set(verilen) - {"endeks", "tahminci", "kahin", "t_o", "takvim"}
        if bilinmeyen:
            raise TypeError(f"bilinmeyen girdi: {sorted(bilinmeyen)}")
        self.__dict__.update(verilen)
        self.bilgi: dict = {}

    @functools.cached_property
    def w(self):
        return motor.dunya(self.ortam.olcek)

    @functools.cached_property
    def harita(self):
        return kaynak.harita_kur(self.w)

    @functools.cached_property
    def optionlar(self) -> np.ndarray:
        return kaynak.oyun_optionlari(self.w, self.ortam.sezon)

    @functools.cached_property
    def lumoda(self):
        """Yolun `lumoda` koşusu (gerçekleşen tarih; öğrenme, kahin ve takvim buradan)."""
        return self.ortam.kos(self.yol, lumoda_adi(self.yol))

    def _tablolar(self) -> dict:
        if self.ortam.yayimlanan_mi(self.yol):
            con = kaynak.baglan()
            try:
                return kaynak.yayimlanan_tablolar(con)
            finally:
                con.close()
        kirli = ("satis", "stok", "sevkiyat")
        t = motor.yayimlanan_bicim({a: self.lumoda.tablo(a) for a in kirli}, self.ortam.olcek)
        t.update({a: self.lumoda.tablo(a) for a in kaynak.GUNLUK_TABLOLARI if a not in kirli})
        return t

    @functools.cached_property
    def ogrenme_tablosu(self) -> pd.DataFrame:
        t0 = time.perf_counter()
        tablolar = self._tablolar()
        karar = kalibrasyon.karar_gunu(tablolar, self.w, self.ortam.sezon)
        sezonlar = ogrenme.kapanmis_sezonlar(self.w, tablolar, karar)
        tablo = ogrenme.ogrenme_tablosu(tablolar, self.w, karar)
        del tablolar
        self.bilgi.update(karar_gunu=karar.date().isoformat(), kapanmis_sezonlar=sezonlar,
                          ogrenme_satir=int(len(tablo)),
                          kaynak="yayimlanan" if self.ortam.yayimlanan_mi(self.yol) else self.lumoda.meta["anahtar"])
        _ilerleme(f"y{self.yol}_ogrenme", time.perf_counter() - t0, False, self.ortam.ilerleme_yolu,
                  karar_gunu=self.bilgi["karar_gunu"], satir=int(len(tablo)))
        return tablo

    @functools.cached_property
    def endeks(self):
        return benzer.ogren(self.ogrenme_tablosu, int(self.kal["en_az"]), mevsim=self.ortam.sezon[:2]).sabitle()

    @functools.cached_property
    def tahminci(self):
        t0 = time.perf_counter()
        t = tahmin.Tahminci.egit(self.ogrenme_tablosu, self.w.magazalar, dict(self.kal["tahmin_parametreleri"])).sabitle()
        _ilerleme(f"y{self.yol}_tahmin_egitimi", time.perf_counter() - t0, False, self.ortam.ilerleme_yolu)
        return t

    @functools.cached_property
    def kahin(self) -> dict:
        e = olcutler.erken_birincil_talep(self.lumoda, self.w, self.harita, self.ortam.sezon)
        return {(o, m): float(t) for o, m, t in e.itertuples(index=False)}

    @functools.cached_property
    def takvim(self):
        return motor.takvim(self.lumoda, self.w).sabitle()

    @functools.cached_property
    def t_o(self) -> dict:
        ad = self.kal["belirsizlik_olcusu"]
        u = kalibrasyon.belirsizlik_olculeri(self.endeks, self.tahminci, self.w, self.harita, self.optionlar)[ad]
        ids = self.w.optionlar["option_id"].astype(str).to_numpy()[self.optionlar]
        agirlik = pd.Series(np.asarray(self.w.ilk_alim, dtype=float)[self.optionlar], index=ids)
        g = belirsizlik_gammasi(self.kal)
        t = kalibrasyon.tutma_egrisi(pd.Series(np.asarray(u, dtype=float), index=ids), agirlik, g,
                                     float(self.kal.get("tbar", sabitler.BELIRSIZLIK_TBAR)))
        self.bilgi.update(belirsizlik={"olcu": ad, "gamma": g, "t_en_az": float(t.min()), "t_en_cok": float(t.max()),
                                       "t_ortalama": float((t * agirlik).sum() / agirlik.sum())})
        return {str(o): float(v) for o, v in t.items()}


def politika_kur(s: Kosum, G: Girdi, kal: dict, secim: dict | None) -> dict:
    """Kosum'un motor yuvaları (`ilk_dagitim`, `replenishment`, `rpt`, `markdown`; verilmeyen Lumoda)."""
    c = cozumle(s, kal, secim)
    h, sezon = G.harita, G.ortam.sezon
    temel = motor.lumoda("ilk_dagitim")

    def kol_kur(kol: str, tutma: float):
        ayar = Ayar(sezon=sezon, tutma=tutma, tavan=c["tavan"])
        if kol == "lumoda_tut":
            return LumodaTutKol(temel, h, ayar)
        if kol == "esit":
            return EsitKol(temel, h, ayar)
        if kol == "benzer":
            return BenzerKol(temel, h, ayar, endeks=G.endeks)
        if kol == "tahmin":
            return TahminKol(temel, h, ayar, tahminci=G.tahminci)
        if kol == "kahin":
            return KahinKol(temel, h, ayar, erken_talep=G.kahin)
        raise ValueError(f"kol kurulamaz: {kol!r}")

    yuvalar = {}
    if c["kol"] == "belirsizlik":
        yuvalar["ilk_dagitim"] = BelirsizlikKol(kol_kur(c["taban"], 0.0), G.t_o)
    elif c["kol"] != "lumoda":
        yuvalar["ilk_dagitim"] = kol_kur(c["kol"], c["tutma"])
    if c["repl"] == "hiz":
        yuvalar["replenishment"] = HizReplenishment(motor.lumoda("replenishment"), h, sezon)
    if c["takvim"]:
        yuvalar["rpt"] = TakvimRPT(motor.lumoda("rpt"), G.takvim, G.optionlar)
        yuvalar["markdown"] = TakvimMarkdown(motor.lumoda("markdown"), G.takvim, G.optionlar)
    return yuvalar


# ---------------------------------------------------------------------------
# Koşu ve ölçüm
# ---------------------------------------------------------------------------

# Ölçüm kodunun özeti içe aktarma anında bir kez (süreç sürerken dosya değişse de kayıt o süreçte
# koşan kodun özetini taşır)
OLCUTLER_OZETI = _dosya_ozeti(olcutler.__file__, kalibrasyon.__file__)


def olcum_kodu() -> str:
    return _sha({"olcutler": OLCUTLER_OZETI, "surum": OLCUM_SURUMU})


def kos_bir(s: Kosum, G: Girdi, kal: dict, secim: dict | None, onceki: dict | None = None):
    """Koşu (önbellekten ya da yeni) ve ölçüm; (`KosuKaydi`, kayıt sözlüğü). `onceki` (bu koşunun
    eski kaydı) anahtarı ve ölçüm kodu tutarsa yeniden ölçülmez."""
    if s.yol != G.yol:
        raise ValueError(f"{s.ad}: yol {s.yol}, girdi yol {G.yol}")
    t0 = time.perf_counter()
    c = cozumle(s, kal, secim)
    yuvalar = politika_kur(s, G, kal, secim)
    k = G.ortam.kos(s.yol, s.ad, **yuvalar)
    del yuvalar
    t1 = time.perf_counter()
    kod = olcum_kodu()
    if onceki and onceki.get("anahtar") == k.meta["anahtar"] and onceki.get("olcum_kodu") == kod:
        kayit = {**onceki, "kosum": asdict(s), "cozum": c, "imza": imza(c)}
        kayit.pop("ayni", None)
    else:
        o = olcutler.hesapla(k, G.w, G.harita, G.ortam.sezon)
        kayit = {"kosum": asdict(s), "cozum": c, "imza": imza(c), "talep_tohumu": talep_tohumu(s.yol),
                 "anahtar": k.meta["anahtar"], "olcum_kodu": kod, "motor_sn": k.meta.get("motor_sn"),
                 "kosu_sn": k.meta.get("sure_sn"), "tepe_bellek_gb": k.meta.get("tepe_bellek_gb"),
                 "olcum_sn": round(time.perf_counter() - t1, 1), "olcutler": o}
    _ilerleme(s.ad, time.perf_counter() - t0, k.onbellekten, G.ortam.ilerleme_yolu,
              motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"),
              olcum_sn=kayit.get("olcum_sn"), surec_tepe_gb=motor._tepe_bellek_gb(),
              bulunabilirlik=round(kayit["olcutler"]["bulunabilirlik"], 3),
              sezon_sonu_kalan=round(kayit["olcutler"]["sezon_sonu_kalan_yuzde"], 3))
    return k, kayit


def secim_yap(kosular: dict, kal: dict) -> dict:
    """Pay bloğunun benzer ve tahmin kollarından (kalibrasyonun tavanıyla) en iyisi (Ruling R29;
    `kalibrasyon.secim`)."""
    adaylar = []
    for ad, e in kosular.items():
        c = e.get("cozum", {})
        if e.get("grup") == "pay" and c.get("kol") in TAVANLI and c.get("tavan") == bool(kal["tavan"]):
            o = e["olcutler"]
            adaylar.append({"ad": ad, "kol": c["kol"], "tavan": c["tavan"], "bulunabilirlik": o["bulunabilirlik"],
                            "sezon_sonu_kalan_yuzde": o["sezon_sonu_kalan_yuzde"], "anahtar": e["anahtar"]})
    if sorted(a["kol"] for a in adaylar) != sorted(TAVANLI):
        raise RuntimeError(f"en iyi seçilemiyor: pay bloğunun benzer ve tahmin koşuları eksik ({adaylar})")
    adaylar.sort(key=lambda a: TAVANLI.index(a["kol"]))
    en_iyi = kalibrasyon.secim(adaylar)
    return {"kol": en_iyi["kol"], "tavan": en_iyi["tavan"], "ad": en_iyi["ad"], "adaylar": adaylar,
            "esik_puan": kalibrasyon.ESIK_PUAN,
            "kural": "bulunabilirliği en yüksek olanın esik_puan'dan az gerisindekiler arasında sezon sonu "
                     "kalanı en düşük olan (eşitlikte benzer)"}


def demo_haritasi(kosular: dict, kal: dict) -> dict:
    """Demo kadranı: pay {lumoda, esit, benzer, tahmin} × `DEMO_TUTMA` → koşu adı (çözümden; benzer ve
    tahmin kalibrasyonun tavanıyla; bulunmayan nokta None)."""
    adlar = {}
    for ad, e in kosular.items():
        c = e.get("cozum", {})
        if c.get("yol") != 0 or c.get("takvim") or c.get("repl") != "lumoda":
            continue
        kol = c.get("kol")
        if kol in TAVANLI and c.get("tavan") != bool(kal["tavan"]):
            continue
        adlar.setdefault((kol, c.get("tutma")), ad)
    harita = {}
    for pay in ("lumoda", "esit", "benzer", "tahmin"):
        harita[pay] = {}
        for t in sabitler.DEMO_TUTMA:
            if pay == "lumoda":
                ad = ESDEGERLIK if t == 0 else adlar.get(("lumoda_tut", float(t)))
            else:
                ad = adlar.get((pay, float(t)))
            harita[pay][f"{t:g}"] = ad
    return harita


def kos_hepsi(blok: str = "hepsi", ortam: Ortam | None = None, kal: dict | None = None, tut: bool = True,
              girdi: Girdi | None = None, adlar=None) -> dict:
    """Bloğun (ya da "hepsi": `BLOK_SIRASI`) koşuları sıralı; ad → tembel `KosuKaydi` (`tut=False`
    iken sözlükte tutulmaz). Ölçümler `cikti/oyun.json`'a, en iyi seçimi `cikti/secim.json`'a (pay
    bloğunun benzer ve tahmin koşuları ölçülmüşse). `adlar` verilirse bloklardan yalnız o koşular."""
    ortam = ortam or Ortam()
    kal = kal if kal is not None else kalibrasyon.oku()
    bloklar = list(BLOK_SIRASI) if blok == "hepsi" else [blok]
    for b in bloklar:
        if b not in IZGARA:
            raise ValueError(f"blok {list(BLOK_SIRASI) + ['hepsi']}'den biri olmalı: {b!r}")
    if adlar is not None:
        adlar = set(adlar)
        bilinmeyen = adlar - {s.ad for b in bloklar for s in IZGARA[b]}
        if bilinmeyen:
            raise ValueError(f"bloklarda olmayan koşu adı: {sorted(bilinmeyen)}")
    kayit = json_oku(ortam.oyun_yolu)
    kosular = kayit.setdefault("kosular", {})
    kayit.update(sezon=ortam.sezon, olcek=ortam.olcek,
                 kalibrasyon={a: kal.get(a) for a in ("en_az", "tahmin_parametreleri", "tavan", "gamma",
                                                       "belirsizlik_olcusu", "belirsizlik_spearman", "tbar")},
                 belirsizlik_gamma=belirsizlik_gammasi(kal))
    G = girdi or Girdi(0, ortam, kal)
    secim = json_oku(ortam.secim_yolu) or None
    tum = tum_kosumlar()
    sonuc, gecerli = {}, set()            # gecerli: bu süreçte koşulmuş / önbellekten doğrulanmış

    def kos_tek(s: Kosum, grup: str) -> None:
        k, e = kos_bir(s, G, kal, secim, kosular.get(s.ad))
        kosular[s.ad] = {**e, "grup": grup}       # eski kaydın grubu değil, bu bloğunki
        gecerli.add(s.ad)
        if tut:
            sonuc[s.ad] = k

    def kos_liste(kosumlar, grup):
        for s in kosumlar:
            im = imza(cozumle(s, kal, secim))
            taban = next((a for a, e in kosular.items()
                          if a != s.ad and e.get("imza") == im and "ayni" not in e), None)
            if taban is None:
                kos_tek(s, grup)
            else:
                if taban not in gecerli:          # eski kayıt: önce tabanın kendisi (önbellekten)
                    kos_tek(tum[taban], kosular[taban]["grup"])
                kosular[s.ad] = {**kosular[taban], "grup": grup, "kosum": asdict(s), "ayni": taban}
                _ilerleme(s.ad, 0.0, True, ortam.ilerleme_yolu, ayni=taban)
            kayit["girdi"] = G.bilgi
            json_yaz(ortam.oyun_yolu, kayit)

    for b in bloklar:
        if b in SECIM_GEREKEN and secim is None:
            secim = secim_yap(kosular, kal)
            json_yaz(ortam.secim_yolu, secim)
        kos_liste([s for s in IZGARA[b] if adlar is None or s.ad in adlar], b)
        if b == "pay":
            try:
                secim = secim_yap(kosular, kal)
            except RuntimeError as e:
                print(f"en iyi seçilmedi: {e}", flush=True)
            else:
                json_yaz(ortam.secim_yolu, secim)
                print(f"en iyi: {secim['kol']} ({secim['ad']})", flush=True)
    kayit["secim"] = secim
    kayit["demo"] = demo_haritasi(kosular, kal)
    json_yaz(ortam.oyun_yolu, kayit)
    return sonuc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m allocation.oyun")
    alt = ap.add_subparsers(dest="komut")
    alt.add_parser("kalibrasyon", help="SS24 kalibrasyonu (cikti/kalibrasyon.json)")
    iz = alt.add_parser("izgara", help="oyun ızgarası (cikti/oyun.json, cikti/secim.json)")
    iz.add_argument("--blok", default="hepsi", choices=[*BLOK_SIRASI, "hepsi"])
    iz.add_argument("--ad", action="append", help="yalnız bu koşu(lar) (tekrarlanabilir)")
    a = ap.parse_args(argv)
    uyanik_tut()
    if a.komut == "kalibrasyon":
        d = kalibrasyon_kos()
        print(json.dumps({k: d[k] for k in ("en_az", "tahmin_parametreleri", "kaynak", "belirsizlik_olcusu",
                                            "tavan", "gamma", "belirsizlik_taban", "izgara_ucunda",
                                            "belirsizlik_spearman", "gamma_bulunabilirlik_araligi_puan",
                                            "sure_sn")},
                         ensure_ascii=False), flush=True)
    else:
        t0 = time.perf_counter()
        kos_hepsi(getattr(a, "blok", "hepsi"), tut=False, adlar=getattr(a, "ad", None))
        print(f"ızgara bitti: {time.perf_counter() - t0:.0f} sn", flush=True)


if __name__ == "__main__":
    main()
