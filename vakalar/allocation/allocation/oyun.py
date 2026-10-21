"""Oyun: kolları v4 motorunda oyun sezonunda (SS25) koşturur ve ölçer (spec §4.5); kalibrasyonun
koşucusu da burada (Ruling R22).

    .venv/Scripts/python -m allocation.oyun                         # ızgara, bütün bloklar sırayla
    .venv/Scripts/python -m allocation.oyun izgara --blok pay       # tek blok
    .venv/Scripts/python -m allocation.oyun kalibrasyon             # cikti/kalibrasyon.json (Görev 7)
    .venv/Scripts/python -m allocation.oyun kume_kalibrasyon        # cikti/kume_kalibrasyon.json (koşusuz)
    .venv/Scripts/python -m allocation.oyun izgara --blok kume      # küme kolları

Bu modül koşu dışıdır (`motor.KOSU_DISI`): motoru içe aktarır, gizli gerçeği okur
(`tests/test_sizinti.py` izinli listesi). Ölçütler `olcutler`'de.

**Izgara** (`IZGARA`; adlar tekil, `tests/test_oyun.py`). Bütün kollar `Ayar.sezon = OYUN_SEZONU`,
yol 0 (yayımlanan dünya), replenishment Lumoda, RPT ve markdown Lumoda'nın tepkili kararı, aksi
yazılmadıkça. Tutma oranı t gönderilebilir üst sınır U'ya göredir (spec §0/9); "tutma %30" (spec
§4.5 pay bloğu) Lumoda'nın kendi %30'udur, U'ya göre t = 0 (Ruling R27). `tavan` boşsa
kalibrasyonun seçimi (`kalibrasyon.json`), yalnız benzer ve tahminde etkin.

    esdegerlik    lumoda: Lumoda + kaydediciler, yayımlanan v4'ün kendisi (tests/test_esdegerlik.py)
    pay           esit, benzer tavanlı / tavansız, tahmin tavanlı / tavansız, kahin (t = 0)
    eslesik       es_benzer, es_tahmin: tavansız kol, t = aynı kolun tavanlı pay koşusunun depoda
                  bıraktığı pay (`eslesik_tutma`; Ruling R43). Tavanlı ↔ eşleşik = tavanın "kime"
                  etkisi (aynı mal), eşleşik ↔ tavansız t 0 = tutmanın etkisi
    sabit_takvim  lumoda_takvimli (lumoda'nın RPT ve markdown kararlarını oyun option'larında
                  yeniden oynatır; eşdeğerlik testiyle aynı koşu) + esit, benzer, tahmin, kahin aynı
                  takvimle (`politika.TakvimRPT`, `TakvimMarkdown`); benzer ve tahmin tavansız (aynı mal,
                  Ruling R46: tepkili karşılığı pay_*_tavansiz)
    tutma         t ∈ TUTMA_DUZEYLERI × pay {lumoda_tut, en iyi} × replenishment {Lumoda, hiz}
                  (16; t = 0 dahil: lumoda_tut t = 0 Lumoda'nın U'ya sığdırılmış hâli, Ruling R28)
    strateji      belirsizlik: pay en iyiden (tavansız), t_o option başına (t̄ = %30); karşılığı
                  tut_eniyi_t30. γ SS24'te tavanlı tabanla kalibre edildi (oyun.json `notlar`)
    demo          esit, benzer, tahmin × DEMO_TUTMA'nın t > 0'ları; benzer ve tahmin tavansız
                  (öteki demo noktaları başka bloklarda; `demo_haritasi`)
    kume          küme kolları (Mağaza Kümeleme vakası, spec 2026-10-20 §4.4): kume_k2 (ciro sınıfı),
                  kume_k1 (bölge), kume_ml (önerilen ML kümesi, yeni mağaza 5-NN), kume_gizli (gizli
                  segment: kümelemenin ulaşabileceği en iyi yapı, YALNIZ ÖLÇÜM kolu); pay =
                  `kumeleme.kume_payi` (küme düzeyi benzer endeksi × mağaza ölçeği), `KahinKol` ile
                  (kayıttaki kol adı "kahin", Ruling R2), t = 0, tavansız: Lumoda'yla aynı mal (⌊U⌋)

"En iyi" (`secim_yap`, Ruling R43; R29'un yerine): pay bloğunun tavansız benzer ve tahmin
kollarından (ikisi de Lumoda'yla aynı malı, ⌊U⌋'yu gönderir: fark yalnız "kime"; tavanlı kol
U'nun bir kısmını depoda bırakır, örtük bir tutma kolu olur) `kalibrasyon.secim` kuralıyla
(bulunabilirliği en yüksek olanın 0,3 puandan az gerisindekiler arasında sezon sonu kalanı en düşük
olan); `cikti/secim.json`. tutma, strateji ve demo bunu okur; seçim her çağrıda oyun.json'daki pay
kayıtlarından yeniden kurulur (dosya eskiyse üstüne yazılır), kayıt yoksa dosyadan okunur.

**Aynı koşu iki adla** (`imza`): kolun çözülmüş tanımı (en iyi, kalibrasyonun tavanı, etkisiz
alanlar) aynı olan iki `Kosum` bir kez koşulur; ikincisinin kaydı `ayni` alanıyla ilkine bağlanır
(ör. tut_eniyi_t00 = pay bloğundaki tavansız en iyi, demo_<en iyi>_t15 = tut_eniyi_t15).

**Girdiler** (`Girdi`, yol başına, tembel; sonuçları kollara `parametreler()` üstünden girer):
öğrenme tablosu oyun sezonunun en erken ilk dağıtım kararı gününde (`kalibrasyon.karar_gunu`)
kapanmış sezonlardan (`ogrenme.ogrenme_tablosu`); yol 0 TAM'da yayımlanan DuckDB'den, başka yolda
yolun `lumoda` koşusunun yayımlanan biçiminden (`motor.yayimlanan_bicim`). `benzer.ogren(...,
en_az, mevsim=<sezonun mevsimi>)` ve `tahmin.Tahminci.egit(..., tahmin_parametreleri)`
kalibrasyonun seçimleriyle. Kahinin sözlüğü yolun `lumoda` koşusunun erken birincil talebi
(`olcutler.erken_birincil_talep`); sabit takvim `motor.takvim(lumoda)`. Belirsizliğin `t_o`'su
kalibrasyonun ölçüsüyle (`kalibrasyon.belirsizlik_olculeri`) ve `kalibrasyon.tutma_egrisi`
(ağırlık ilk alım, t̄ = %30); γ kalibrasyonun seçimi, ölçünün Spearman'ı ≤ 0 ise 0 (sabit tutma).

**Küme kolları** (`kume` bloğu; `Girdi.kume_payi`). Kümeler: TAM yol 0'da git'teki
`vakalar/kumeleme/kumeler.json`'dan (`kumeleme.oyun.kumeler_oku`; K1, K2 ve ML `olcum=False` ile,
gizli segment ayrı bir `olcum=True` okumasıyla); başka her yolda (ve KÜÇÜK dünyada) kümeleme
paketinin işlevleriyle o yolun kendi tablolarından, aynı karar gününde yeniden kurulur
(`kumeleri_kur`: kapsam, K1, K2, ML önerisi, yeni mağazaya 5-NN; CRM yok). Gizli segment dünyadan
(`kumeleme.hakem.gizli_segment`). Pay sözlüğü kapsamın her aday (option, mağaza) çiftini taşır
(`kalibrasyon.aday_yaklasik`; `KahinKol` sözlükte olmayan adaya 0 verir): her küme kolunun sözlüğü
`cikti/kume_paylari.json`'a yazılır, rapor koşunun kimliğiyle ve kararlarındaki adaylarla denetler.
Küme payının ayarları (hiyerarşinin ilk düzeyi `bas` ve `en_az`, yapı başına) SS24'te koşusuz
seçilir (`kume_kalibre`, `python -m allocation.oyun kume_kalibrasyon` → `cikti/kume_kalibrasyon.json`;
İlk Sevkiyat R12 kalıbı: yalnız SS23 ile öğren, kümeler SS24 karar günündeki veriyle, ölçü
`kalibrasyon.pay_wape`). Her kolun kullandığı düzeyler ve kümeleme kimliği `oyun.json` `girdi.kume`'de.

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
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import kumeleme.oyun as kumeleme_oyun
from kumeleme import hakem as kumeleme_hakem
from kumeleme import kume_payi
from kumeleme import ogren as kumeleme_ogren
from kumeleme import sabitler as kumeleme_sabitler
from kumeleme import yeni_magaza as kumeleme_yeni

from allocation import benzer, kalibrasyon, kaynak, motor, ogrenme, olcutler, sabitler, tahmin
from allocation.paylastir import paket_adedi
from allocation.politika import (Ayar, BelirsizlikKol, BenzerKol, EsitKol, HizReplenishment, KahinKol,
                                 LumodaTutKol, TahminKol, TakvimMarkdown, TakvimRPT)

ILERLEME = sabitler.CIKTI / "ilerleme.jsonl"
ESDEGERLIK = "lumoda"
TAKVIMLI = "lumoda_takvimli"
BLOK_SIRASI = ("esdegerlik", "pay", "eslesik", "sabit_takvim", "tutma", "strateji", "demo", "kume")
SECIM_GEREKEN = ("tutma", "strateji", "demo")
KOLLAR = ("lumoda", "lumoda_tut", "esit", "benzer", "tahmin", "kahin", "belirsizlik", "eniyi", "kume")
TAVANLI = ("benzer", "tahmin")
OLCUM_SURUMU = 1

# Küme kolları: yapı → ad (rapor ve yazılar koşu adıyla anar; politikadaki sınıf KahinKol, Ruling R2)
KUME_YAPILARI = {"k2": "ciro sınıfı (K2)", "k1": "bölge (K1)", "ml": "önerilen ML kümesi (yeni mağaza 5-NN)",
                 "gizli": "gizli segment (yalnız ölçüm: kümelemenin ulaşabileceği en iyi yapı)"}
KUME_KAL_DOSYASI = "kume_kalibrasyon.json"
KUME_PAYLARI_DOSYASI = "kume_paylari.json"
# Küme kolları eklenmeden önceki koşu anahtarları (İlk Sevkiyat önbelleği, ~6 sa TAM): küme bloğu bunları
# değiştirmemeli (spec 2026-10-20 §0/14; `tests/test_oyun.py::test_mevcut_kosular_onbellekten`, rapor KORUNUM)
MEVCUT_ANAHTARLAR = {
    "lumoda": "220ddbe436b0438d68646ad704808b256ff9a73f8d6c6a6865e403075c521033",
    "pay_esit": "4bb80406dac74be2f8f55a441b44c9cf0490b64b4ce7409049472ef000f8563a",
    "pay_benzer_tavansiz": "81b117fd70375db0751c06234dfd36c857c73726be456027acb2f037ec24654e",
    "pay_tahmin_tavansiz": "6d3222b1d2cb8858f7d3af6d79890fa63ecbae90b3922f622f524cd26919a160",
    "pay_kahin": "c5efb01682015c2d41ce67a8c58ca2790a417ba29d1d9e09de7620df59660609",
}


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
    tavan   kapsama tavanı; None kalibrasyonun seçimi (yalnız benzer ve tahminde etkin; en iyi ve
            belirsizlikte `secim`'in tavanı)
    repl    "lumoda" | "hiz" (`politika.HizReplenishment`)
    takvim  sabit takvim: lumoda koşusunun RPT ve markdown kararları oyun option'larında
    yol     talep yolu (`talep_tohumu`)
    tutma_kaynagi  eşleşik tutma: t bu pay koşusunun (aynı kolun tavanlı hâli) depoda bıraktığı
            paydır (`eslesik_tutma`); `tutma` None kalır, `kos_hepsi` çözer
    kume    küme kolunda kümeleme yapısı (`KUME_YAPILARI`); öteki kollarda None"""

    ad: str
    kol: str
    tutma: float | None = 0.0
    tavan: bool | None = None
    repl: str = "lumoda"
    takvim: bool = False
    yol: int = 0
    tutma_kaynagi: str | None = None
    kume: str | None = None

    def __post_init__(self):
        if self.kol not in KOLLAR:
            raise ValueError(f"bilinmeyen kol: {self.kol!r}")
        if (self.kol == "kume") != (self.kume is not None):
            raise ValueError("kume alanı yalnız ve her zaman küme kolunda")
        if self.kume is not None and self.kume not in KUME_YAPILARI:
            raise ValueError(f"bilinmeyen kümeleme yapısı: {self.kume!r}")
        if self.kol == "kume" and (self.tutma != 0.0 or self.tavan is not None or self.repl != "lumoda"
                                   or self.takvim):
            raise ValueError("küme kolu t = 0, tavansız, replenishment Lumoda, tepkili takvim (aynı mal)")
        if self.repl not in ("lumoda", "hiz"):
            raise ValueError(f"bilinmeyen replenishment: {self.repl!r}")
        if self.kol == "lumoda" and (self.tutma or self.repl != "lumoda"):
            raise ValueError("lumoda kolu Lumoda'nın kendisidir: tutma ve hiz için lumoda_tut")
        if self.tutma_kaynagi is not None and (self.kol not in TAVANLI or self.tavan is not False):
            raise ValueError("eşleşik tutma yalnız tavansız benzer ve tahminde")
        if self.tutma is None and self.tutma_kaynagi is None:
            raise ValueError("tutma yalnız eşleşik tutmada (tutma_kaynagi) boş olabilir")


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
    "eslesik": tuple(Kosum(f"es_{k}", k, tutma=None, tavan=False, tutma_kaynagi=f"pay_{k}_tavanli")
                     for k in TAVANLI),
    "sabit_takvim": (Kosum(TAKVIMLI, "lumoda", takvim=True), Kosum("sabit_esit", "esit", takvim=True),
                     Kosum("sabit_benzer", "benzer", takvim=True, tavan=False),
                     Kosum("sabit_tahmin", "tahmin", takvim=True, tavan=False),
                     Kosum("sabit_kahin", "kahin", takvim=True)),
    "tutma": _tutma(),
    "strateji": (Kosum("belirsizlik", "belirsizlik"),),
    "demo": tuple(Kosum(f"demo_{k}_{_t(t)}", k, tutma=t, tavan=False if k in TAVANLI else None)
                  for k in ("esit", "benzer", "tahmin") for t in sabitler.DEMO_TUTMA if t > 0),
    "kume": tuple(Kosum(f"kume_{y}", "kume", kume=y) for y in KUME_YAPILARI),
}

# Yollar (`allocation.yollar`): yol başına koşulan kollar (kısa ad → yol 0'daki ızgara koşusu)
YOL_KOLLARI = ("lumoda", "esit", "benzer", "tahmin", "kahin")
# Yollarda küme kolları (kısa ad = yol 0'daki ad): önerilen ML kümesi ve gizli segment (spec §4.4)
YOL_KUME_KOLLARI = ("kume_ml", "kume_gizli")


def tum_kosumlar() -> dict[str, Kosum]:
    return {s.ad: s for blok in IZGARA.values() for s in blok}


def lumoda_adi(yol: int) -> str:
    return ESDEGERLIK if int(yol) == 0 else f"y{int(yol)}_{ESDEGERLIK}"


def yol_listesi(yol: int, kal: dict) -> list[tuple[str, Kosum]]:
    """(kısa ad, `Kosum`): yol 0'da ızgaranın koşuları (aynı anahtar), yol p'de `y<p>_` önekiyle. benzer ve
    tahmin tavansız (Ruling R44: aynı mal; tavanın etkisi yol 0'da eslesik bloğunda); sonra küme kolları
    (`YOL_KUME_KOLLARI`). `kal` imza uyumu için."""
    tum = tum_kosumlar()
    if int(yol) == 0:
        adlar = {"lumoda": ESDEGERLIK, "esit": "pay_esit", "benzer": "pay_benzer_tavansiz",
                 "tahmin": "pay_tahmin_tavansiz", "kahin": "pay_kahin"}
        return [(k, tum[adlar[k]]) for k in YOL_KOLLARI] + [(k, tum[k]) for k in YOL_KUME_KOLLARI]
    return ([(k, Kosum(lumoda_adi(yol) if k == "lumoda" else f"y{yol}_{k}", k, yol=int(yol),
                       tavan=False if k in TAVANLI else None)) for k in YOL_KOLLARI]
            + [(k, replace(tum[k], ad=f"y{yol}_{k}", yol=int(yol))) for k in YOL_KUME_KOLLARI])


def kosu_sayisi() -> dict[str, int]:
    """Izgaranın (yol 0, adlar; aynı koşu iki adla sayılır: üst sınır) ve yolların koşu sayısı."""
    yol0 = sum(len(b) for b in IZGARA.values())
    yollar = (sabitler.YOL_SAYISI - 1) * (len(YOL_KOLLARI) + len(YOL_KUME_KOLLARI))
    return {"yol0": yol0, "yollar": yollar, "toplam": yol0 + yollar}


def cozumle(s: Kosum, kal: dict, secim: dict | None) -> dict:
    """Kosum'un çözülmüş tanımı: en iyi kol, kalibrasyonun tavanı, etkisiz alanlar kapalı. İki
    `Kosum`un çözümü aynıysa aynı koşudur (`imza`)."""
    kol = s.kol
    if kol in ("eniyi", "belirsizlik"):
        if secim is None:
            raise RuntimeError(f"{s.ad}: en iyi kol seçilmedi (önce pay bloğu; cikti/secim.json)")
    if s.tutma is None and kol != "belirsizlik":
        raise RuntimeError(f"{s.ad}: eşleşik tutma çözülmedi ({s.tutma_kaynagi}; kos_hepsi çözer)")
    taban = secim["kol"] if kol == "belirsizlik" else None
    if kol in ("eniyi", "belirsizlik"):
        tavan = bool(secim["tavan"])                 # en iyinin kendi tavanı (R43: tavansız)
        tavan_kol = secim["kol"]
    else:
        tavan = bool(kal["tavan"] if s.tavan is None else s.tavan)
        tavan_kol = kol
    if kol == "eniyi":
        kol = secim["kol"]
    tavan = tavan if tavan_kol in TAVANLI else False
    tutma = None if kol == "belirsizlik" else float(s.tutma)
    c = {"kol": kol, "taban": taban, "tutma": tutma, "tavan": tavan, "repl": s.repl, "takvim": bool(s.takvim),
         "yol": int(s.yol)}
    if kol == "kume":              # yalnız küme kolunda: öteki kolların çözümü (ve imzası) değişmez
        c["kume"] = s.kume
    return c


def imza(cozum: dict) -> str:
    return _sha(cozum)[:20]


# ---------------------------------------------------------------------------
# Ortam ve girdiler
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Ortam:
    """Koşuların nerede ve nasıl yapıldığı (TAM, oyun sezonu varsayılan; testler KÜÇÜK dünyada).
    `kume_oneri` yalnız testler içindir: KÜÇÜK dünyanın ~10 mağazası kümeleme önerisinin kuralına (k ≥ 3, en
    küçük küme ≥ 3) sığmaz; `kumeleme.ogren.oneri`'nin `k_aralik` / `en_kucuk`'u (None: kümeleme sabitleri)."""

    olcek: str = "tam"
    onbellek: Path = motor.KOSU_DIZINI
    cikti: Path = sabitler.CIKTI
    gun_sayisi: int | None = None
    sezon: str = sabitler.OYUN_SEZONU
    ilerleme: bool = True
    kume_oneri: dict | None = None

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


# ---------------------------------------------------------------------------
# Küme kolları: kümeler, küme payı, kalibrasyon (Mağaza Kümeleme vakası, spec 2026-10-20 §4.4)
# ---------------------------------------------------------------------------


def _bellek_baglantisi(tablolar) -> duckdb.DuckDBPyConnection:
    """Yayımlanan biçimdeki tabloları (DataFrame) bellek içi bir DuckDB bağlantısına kaydeder: kümeleme
    paketinin girdisi (`kumeleme.oyun.girdiler`) bağlantıdır."""
    con = duckdb.connect(":memory:")
    for ad in ("satis", "stok", "magaza", "magaza_olay", "urun"):
        con.register(ad, tablolar[ad])
    return con


def _kume_bilgisi(e: pd.Series, kaynak_adi: str, **ek) -> dict:
    boy = e.astype(str).value_counts()
    return {"kaynak": kaynak_adi, "kimlik": kumeleme_ogren.bolme_kimligi(e), "magaza": int(len(e)),
            "grup": int(e.nunique()), "boyutlar": sorted((int(n) for n in boy.to_numpy()), reverse=True), **ek}


def kumeleri_kur(tablolar, karar_gunu, gizli: pd.Series, oneri_ayari: dict | None = None) -> dict:
    """Karar gününde (yalnız o güne kadarki yayımlanan biçimdeki veriyle) kümeleme paketinin işlevleriyle
    kurulan yapılar: `{"etiket": {yapı: magaza_id → küme}, "bilgi": {yapı: …}}` (`KUME_YAPILARI`).

    tablolar   yayımlanan v4'e bağlantı ya da `satis`, `stok`, `magaza`, `magaza_olay`, `urun` DataFrame'leri
               (bir yolun `lumoda` koşusunun yayımlanan biçimi)
    gizli      mağaza → gizli segment (`kumeleme.hakem.gizli_segment`; yalnız ölçüm kolu)
    oneri_ayari  `kumeleme.ogren.oneri`'nin `k_aralik` / `en_kucuk`'u (yalnız testler; `Ortam.kume_oneri`)

    Kümeleme vakasının koşumuyla (`kumeleme.oyun.kos`) aynı adımlar: kapsam, K1 bölge, K2 ciro sınıfı,
    önerinin S1/S2 adaylarından seçilen ML kümesi, yeni mağazaya statiklerle 5-NN (`yeni_magaza.ata`)."""
    con = tablolar if isinstance(tablolar, duckdb.DuckDBPyConnection) else _bellek_baglantisi(tablolar)
    karar = pd.Timestamp(karar_gunu).normalize()
    try:
        g = kumeleme_oyun.girdiler(con, karar)
    finally:
        if con is not tablolar:
            con.close()
    k = g["kapsam"]
    o = kumeleme_ogren.oneri(None, k, None, karar, ozellik={a: g["X"][a] for a in kumeleme_ogren.ONERI_AILELERI},
                             **(oneri_ayari or {}))
    yeni, kum = k[k["yeni"]], k[k["kumelenir"]]
    atama = kumeleme_yeni.ata(yeni, kum, o.etiket) if len(yeni) else pd.Series(dtype=object)
    ml = pd.concat([o.etiket, atama]).sort_index()
    ids = list(k["magaza_id"].astype(str))
    eksik = sorted(set(ids) - set(gizli.index.astype(str)))
    if eksik:
        raise ValueError(f"gizli segmenti olmayan kapsam mağazası: {eksik}")
    etiket = {"k2": g["k2"], "k1": g["k1"], "ml": ml, "gizli": gizli.loc[ids]}
    kaynak_adi = f"yeniden kuruldu ({karar.date().isoformat()})"
    bilgi = {y: _kume_bilgisi(e, kaynak_adi) for y, e in etiket.items()}
    bilgi["ml"].update(aile=o.aile, yontem=o.yontem, k=int(o.k), oneri_kimligi=o.kimlik,
                       yeni_atama={str(m): int(c) for m, c in atama.items()})
    bilgi["_kapsam"] = {"karar_gunu": karar.date().isoformat(), "aday": len(ids), "kumelenen": int(len(kum)),
                        "yeni": sorted(yeni["magaza_id"].astype(str))}
    return {"etiket": {y: e.copy() for y, e in etiket.items()}, "bilgi": bilgi}


def kumeler_json_yapilari(karar_gunu, yol=kumeleme_oyun.KUMELER) -> dict:
    """TAM yol 0: git'teki `kumeler.json`'un karar günü eşlemeleri (Ruling R3); `kumeleri_kur` biçiminde.
    K1, K2, ML `kumeler_oku(olcum=False)` ile (gizli alan hiç görülmez); gizli segment ayrı okumayla."""
    k = kumeleme_oyun.kumeler_oku(yol, olcum=False)
    karar = pd.Timestamp(karar_gunu).normalize()
    if pd.Timestamp(k["karar_gunu"]) != karar:
        raise ValueError(f"kumeler.json karar günü {k['karar_gunu']}, oyunun karar günü {karar.date()}")
    gizli = kumeleme_oyun.kumeler_oku(yol, olcum=True)[kumeleme_oyun.GIZLI_ALAN]["etiket"]
    ml = {**k["ml"]["etiket"], **k["ml"]["yeni_magaza"]["atama"]}
    etiket = {"k2": pd.Series(k["kural"]["k2"]["etiket"]), "k1": pd.Series(k["kural"]["k1"]["etiket"]),
              "ml": pd.Series(ml).sort_index(), "gizli": pd.Series(gizli).sort_index()}
    bilgi = {y: _kume_bilgisi(e, "kumeler.json") for y, e in etiket.items()}
    bilgi["ml"].update(aile=k["ml"]["aile"], yontem=k["ml"]["yontem"], k=int(k["ml"]["k"]),
                       oneri_kimligi=k["ml"]["kimlik"], yeni_atama=dict(k["ml"]["yeni_magaza"]["atama"]))
    bilgi["_kapsam"] = {"karar_gunu": karar.date().isoformat(), "aday": len(etiket["k1"]),
                        "kumelenen": len(k["kapsam"]["kumelenen"]), "yeni": sorted(k["kapsam"]["yeni"]),
                        "kumeler_json_kod": k["kod"]}
    return {"etiket": etiket, "bilgi": bilgi}


def kume_ogrenme_tablosu(tablo: pd.DataFrame, w) -> pd.DataFrame:
    """`ogrenme.ogrenme_tablosu` → `kume_payi`'nın girdisi (modül notu orada): `option` option_id'ye,
    `magaza` magaza_id'ye çevrilir; öteki sütunlar aynen."""
    oid = w.optionlar["option_id"].astype(str).to_numpy()
    mid = w.magazalar["magaza_id"].astype(str).to_numpy()
    t = tablo.copy()
    t["option"] = oid[tablo["option"].to_numpy(dtype=np.int64)]
    t["magaza_id"] = mid[tablo["magaza"].to_numpy(dtype=np.int64)]
    return t


def kume_adaylari(w, harita, optionlar) -> dict[str, list[str]]:
    """option_id → aday mağazalar: kolun aday kümesinin karar öncesi yaklaşığı (`kalibrasyon.aday_yaklasik`;
    kapanış kararı ve bugünkü açıklık bilinmeden, gerçek aday kümesini kapsar)."""
    oid = w.optionlar["option_id"].astype(str).to_numpy()
    mid = w.magazalar["magaza_id"].astype(str).to_numpy()
    return {str(oid[o]): [str(m) for m in mid[np.flatnonzero(kalibrasyon.aday_yaklasik(w, harita, int(o)))]]
            for o in np.asarray(optionlar, dtype=np.int64)}


def kume_option_tablosu(w, optionlar) -> pd.DataFrame:
    """Yeni option'ların `option_id` + öznitelikleri (`kume_payi.paylar`'ın girdisi)."""
    opt = np.asarray(optionlar, dtype=np.int64)
    return ogrenme.option_oznitelikleri(w, opt).assign(
        option_id=w.optionlar["option_id"].astype(str).to_numpy()[opt])


def kume_sozlugu(tablo: pd.DataFrame, etiket: pd.Series, oz: pd.DataFrame, adaylar: dict, bas: int, en_az: int,
                 mevsim: str) -> tuple[dict, dict]:
    """Bir yapının küme payı sözlüğü (`KahinKol.erken_talep`) ve bilgisi. Etiketi olmayan aday (kapsam dışı:
    karar gününde kapanış kararı verilmiş) sözlüğe girmez, bilgide sayılır; motorun gerçek aday kümesi bu
    mağazaları zaten dışarıda bırakır (rapor koşunun kararlarıyla denetler)."""
    e = kume_payi.ogren(tablo, etiket, int(en_az), kume_payi.HIYERARSI[int(bas):], mevsim=mevsim).sabitle()
    olc = kume_payi.olcek(tablo, etiket, mevsim=mevsim)
    etiketli = set(e.etiket)
    dis = sorted({m for ms in adaylar.values() for m in ms} - etiketli)
    ad = {o: [m for m in ms if m in etiketli] for o, ms in adaylar.items()}
    p = e.paylar(oz, ad, olc)
    duzey = e.duzeyler(oz)
    sayim = pd.Series(list(duzey.values()), dtype=np.int64).value_counts().sort_index()
    gozlemsiz = sorted(m for m in etiketli if m not in set(tablo.loc[tablo["talep"].notna(), "magaza_id"].astype(str)))
    bilgi = {"bas": int(bas), "en_az": int(en_az),
             "hiyerarsi": [list(d) for d in e.hiyerarsi],
             "duzey": {" × ".join(e.hiyerarsi[int(d)]) or "genel": int(n) for d, n in sayim.items()},
             "duzey_tam": {str(int(bas) + int(d)): int(n) for d, n in sayim.items()},     # HIYERARSI indisi
             "endeks": e.kimlik, "cift": len(p), "sifir_pay": int(sum(v == 0 for v in p.values())),
             "etiketsiz_aday": dis, "gecmissiz_magaza": gozlemsiz,
             "medyan_olcek_alan": {m: olc[m] for m in gozlemsiz},
             "pay": KahinKol(None, None, erken_talep=p).parametreler()["erken_talep"]}
    return p, bilgi


def _uzun_pay(p: dict, w) -> pd.DataFrame:
    """(option_id, magaza_id) → pay sözlüğü, `kalibrasyon.pay_wape`'nin `option, magaza, pay` biçiminde."""
    oi = pd.Index(w.optionlar["option_id"].astype(str))
    mi = pd.Index(w.magazalar["magaza_id"].astype(str))
    o, m = zip(*p) if p else ((), ())
    return pd.DataFrame({"option": oi.get_indexer(list(o)).astype(np.int64), "magaza": mi.get_indexer(list(m)).astype(np.int64),
                         "pay": np.array(list(p.values()), dtype=float)})


def _uctami(satirlar: list[dict], sec: dict) -> bool:
    """Seçilen `en_az` ızgaranın ucunda ve aynı `bas`ta komşusundan kesin iyi mi (eşitlikte uç değil: ızgarayı
    uzatmak sonucu değiştirmez; Ruling R24/R25 kalıbı)."""
    iz = list(kalibrasyon.EN_AZ_IZGARASI)
    i = iz.index(sec["en_az"])
    if i not in (0, len(iz) - 1):
        return False
    komsu = iz[1] if i == 0 else iz[-2]
    w = next(r["wape"] for r in satirlar if r["yapi"] == sec["yapi"] and r["bas"] == sec["bas"] and r["en_az"] == komsu)
    return bool(sec["wape"] < w)


def kume_kalibre(ogr: pd.DataFrame, gercek: pd.DataFrame, yapilar: dict, w, harita,
                 sezon: str = sabitler.KAL_SEZONU) -> dict:
    """Koşusuz seçim (modül notu): her yapı için hiyerarşinin ilk düzeyi `bas` ∈ 0..4 × `en_az` ∈
    `kalibrasyon.EN_AZ_IZGARASI`, ölçü `kalibrasyon.pay_wape` (ilk alımla ağırlıklı; gerçek pay sezonun
    sansür düzeltmeli ilk 6 hafta talebi); en küçük WAPE, eşitlikte ızgara sırası (ince düzey önce, küçük
    eşik önce). `ogr` sezonun karar gününde kapanmış sezonlardan (`ogrenme.ogrenme_tablosu`), `yapilar`
    aynı karar günündeki kümeler (`kumeleri_kur`)."""
    opt = kaynak.oyun_optionlari(w, sezon)
    oz = kume_option_tablosu(w, opt)
    adaylar = kume_adaylari(w, harita, opt)
    ilk_alim = pd.Series(np.asarray(w.ilk_alim, dtype=float)[opt], index=opt)
    tablo = kume_ogrenme_tablosu(ogr, w)
    mevsim = sezon[:2]
    satirlar, secim = [], {}
    for yapi in KUME_YAPILARI:
        et = yapilar["etiket"][yapi]
        en_iyi = None
        for bas in range(len(kume_payi.HIYERARSI)):
            for en_az in kalibrasyon.EN_AZ_IZGARASI:
                p, b = kume_sozlugu(tablo, et, oz, adaylar, bas, en_az, mevsim)
                uzun = _uzun_pay(p, w)
                r = {"yapi": yapi, "bas": bas, "en_az": int(en_az), "wape": float(kalibrasyon.pay_wape(uzun, gercek, ilk_alim)),
                     "n_option": int(len(kalibrasyon.option_wape(uzun, gercek))), "duzey": b["duzey"],
                     "etiketsiz_aday": len(b["etiketsiz_aday"])}
                satirlar.append(r)
                if en_iyi is None or r["wape"] < en_iyi["wape"]:
                    en_iyi = r
        secim[yapi] = {"bas": en_iyi["bas"], "en_az": en_iyi["en_az"], "wape": en_iyi["wape"],
                       "hiyerarsi": [list(d) for d in kume_payi.HIYERARSI[en_iyi["bas"]:]],
                       "izgara_ucunda": _uctami(satirlar, en_iyi)}
    return {"sezon": sezon, "karar_gunu": None, "secim": secim, "tablo": satirlar,
            "kumeler": {y: b for y, b in yapilar["bilgi"].items()},
            "izgara": {"bas": list(range(len(kume_payi.HIYERARSI))), "en_az": list(kalibrasyon.EN_AZ_IZGARASI)},
            "hiyerarsi": [list(d) for d in kume_payi.HIYERARSI],
            "kural": "yapı başına en küçük pay WAPE'si (SS24, koşusuz); eşitlikte ince düzey ve küçük eşik önce"}


def kume_kalibrasyon_kos(cikti: Path = sabitler.CIKTI) -> dict:
    """Küme payının koşusuz kalibrasyonu (yol 0, TAM, SS24; simülasyon yok): `cikti/kume_kalibrasyon.json`."""
    t0 = time.perf_counter()
    w = motor.dunya("tam")
    harita = kaynak.harita_kur(w)
    con = kaynak.baglan()
    try:
        tablolar = kaynak.yayimlanan_tablolar(con)
        sezon = sabitler.KAL_SEZONU
        karar = kalibrasyon.karar_gunu(tablolar, w, sezon)
        if karar != kumeleme_sabitler.KAL_KARAR_GUNU:
            raise ValueError(f"SS24 karar günü {karar.date()}, kümeleme {kumeleme_sabitler.KAL_KARAR_GUNU.date()}")
        gercek = kalibrasyon.erken_gercek(tablolar, w, sezon)
        ogr = ogrenme.ogrenme_tablosu(tablolar, w, karar)
        sezonlar = ogrenme.kapanmis_sezonlar(w, tablolar, karar)
        del tablolar
        yapilar = kumeleri_kur(con, karar, kumeleme_hakem.gizli_segment(w))
    finally:
        con.close()
    d = kume_kalibre(ogr, gercek, yapilar, w, harita, sezon)
    d.update(karar_gunu=karar.date().isoformat(), kapanmis_sezonlar=sezonlar, ogrenme_satir=int(len(ogr)),
             sure_sn=round(time.perf_counter() - t0, 1))
    json_yaz(Path(cikti) / KUME_KAL_DOSYASI, d)
    return d


def kume_kalibrasyon_oku(cikti: Path = sabitler.CIKTI) -> dict:
    d = json_oku(Path(cikti) / KUME_KAL_DOSYASI)
    if not d:
        raise RuntimeError(f"{KUME_KAL_DOSYASI} yok: önce `python -m allocation.oyun kume_kalibrasyon`")
    return d


def kume_sozlugu_yaz(cikti: Path, ad: str, p: dict, bilgi: dict) -> None:
    """Küme kolunun pay sözlüğü `cikti/kume_paylari.json`'a (ad → kimlik, bilgi, [option, mağaza, pay])."""
    yol = Path(cikti) / KUME_PAYLARI_DOSYASI
    d = json_oku(yol)
    d[ad] = {"pay": bilgi["pay"], "yapi": bilgi.get("yapi"), "yol": bilgi.get("yol"),
             "paylar": sorted([o, m, float(v)] for (o, m), v in p.items())}
    json_yaz(yol, d)


class Girdi:
    """Bir yolun kollara giden öğrenilmiş girdileri (modül notu), tembel; testler doğrudan verebilir
    (`endeks=`, `tahminci=`, `kahin=`, `t_o=`, `kume_kal=`, `kume_yapilari=`)."""

    def __init__(self, yol: int, ortam: Ortam, kal: dict, **verilen):
        self.yol, self.ortam, self.kal = int(yol), ortam, kal
        bilinmeyen = set(verilen) - {"endeks", "tahminci", "kahin", "t_o", "takvim", "kume_kal", "kume_yapilari"}
        if bilinmeyen:
            raise TypeError(f"bilinmeyen girdi: {sorted(bilinmeyen)}")
        self.__dict__.update(verilen)
        self.bilgi: dict = {}
        self._kume_paylari: dict = {}

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

    # --- küme kolları ----------------------------------------------------------

    @functools.cached_property
    def kume_kal(self) -> dict:
        """Küme payının SS24 koşusuz seçimleri (`cikti/kume_kalibrasyon.json`)."""
        return kume_kalibrasyon_oku(self.ortam.cikti)

    @functools.cached_property
    def kume_yapilari(self) -> dict:
        """Yolun kümeleri (modül notu): TAM yol 0 `kumeler.json`, başka her yol kendi tablolarından."""
        t0 = time.perf_counter()
        if self.ortam.yayimlanan_mi(self.yol):
            self.ogrenme_tablosu                         # karar günü (yayımlanan sevkiyattan) bilgiye girer
            y = kumeler_json_yapilari(self.bilgi["karar_gunu"])
        else:
            tablolar = self._tablolar()
            karar = kalibrasyon.karar_gunu(tablolar, self.w, self.ortam.sezon)
            y = kumeleri_kur(tablolar, karar, kumeleme_hakem.gizli_segment(self.w), self.ortam.kume_oneri)
            del tablolar
        _ilerleme(f"y{self.yol}_kumeler", time.perf_counter() - t0, False, self.ortam.ilerleme_yolu,
                  kaynak=y["bilgi"]["k1"]["kaynak"])
        return y

    def kume_payi(self, yapi: str) -> dict:
        """Yapının küme payı sözlüğü (`(option_id, magaza_id) → pay`; oyun sezonunun her adayı), bir kez."""
        if yapi not in self._kume_paylari:
            sec = self.kume_kal["secim"][yapi]
            p, b = kume_sozlugu(kume_ogrenme_tablosu(self.ogrenme_tablosu, self.w),
                                self.kume_yapilari["etiket"][yapi], kume_option_tablosu(self.w, self.optionlar),
                                kume_adaylari(self.w, self.harita, self.optionlar), sec["bas"], sec["en_az"],
                                self.ortam.sezon[:2])
            b.update(yapi=yapi, yol=self.yol, kumeleme=self.kume_yapilari["bilgi"][yapi],
                     kume_kalibrasyon={"bas": sec["bas"], "en_az": sec["en_az"], "wape": sec.get("wape")})
            self.bilgi.setdefault("kume", {})[yapi] = b
            self._kume_paylari[yapi] = (p, b)
        return self._kume_paylari[yapi][0]

    def kume_bilgisi(self, yapi: str) -> dict:
        self.kume_payi(yapi)
        return self._kume_paylari[yapi][1]


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
        if kol == "kume":                         # pay dışarıdan verilir (KahinKol, Ruling R2): küme payı
            return KahinKol(temel, h, ayar, erken_talep=G.kume_payi(c["kume"]))
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
    if c["kol"] == "kume":
        kume_sozlugu_yaz(G.ortam.cikti, s.ad, G.kume_payi(c["kume"]), G.kume_bilgisi(c["kume"]))
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


def eslesik_tutma(kosu, w, harita, sezon: str = sabitler.OYUN_SEZONU) -> dict:
    """Tavanlı bir kol koşusunun depoda bıraktığı pay, kolun ilk dağıtım kaydından (Ruling R43):
    oyun option'larında t = 1 − Σ gönderilen ÷ Σ U, adetle (paket × paket adedi), 0,001'e
    yuvarlanmış. Kayıt kolun değilse (`kol` sütunu yok) `ValueError`."""
    kayit = kosu.kayitlar.get("ilk_dagitim")
    if kayit is None or "kol" not in kayit.columns:
        raise ValueError("eşleşik tutma: koşunun ilk dağıtım kaydı bir kolun değil")
    opt = kaynak.oyun_optionlari(w, sezon)
    kendi = kayit[kayit["kol"].to_numpy(dtype=bool) & np.isin(kayit["arg0"].to_numpy(), opt)]
    oz = kendi.groupby("arg0").agg(U=("U", "first"), giden=("deger", "sum"))
    pk = np.array([paket_adedi(w, int(o)) for o in oz.index], dtype=np.int64)
    U = int((oz["U"].to_numpy(dtype=np.int64) * pk).sum())
    giden = int((oz["giden"].to_numpy(dtype=np.int64) * pk).sum())
    if U <= 0:
        raise ValueError("eşleşik tutma: oyun option'larında U yok")
    ham = 1.0 - giden / U
    t = round(ham, 3)
    if not 0.0 <= t < 1.0:
        raise ValueError(f"eşleşik tutma [0, 1) dışında: {t}")
    return {"tutma": t, "ham": ham, "U_adet": U, "giden_adet": giden, "U_paket": int(oz["U"].sum()),
            "giden_paket": int(oz["giden"].sum()), "option": int(len(oz))}


def secim_yap(kosular: dict, kal: dict) -> dict:
    """Pay bloğunun tavansız benzer ve tahmin kollarından en iyisi (Ruling R43; `kalibrasyon.secim`).
    `kal` imza uyumu için (kullanılmaz)."""
    adaylar = []
    for ad, e in kosular.items():
        c = e.get("cozum", {})
        if (e.get("grup") == "pay" and "ayni" not in e and c.get("kol") in TAVANLI and c.get("tavan") is False
                and c.get("tutma") == 0.0 and not c.get("takvim") and c.get("repl") == "lumoda"):
            o = e["olcutler"]
            adaylar.append({"ad": ad, "kol": c["kol"], "tavan": c["tavan"], "bulunabilirlik": o["bulunabilirlik"],
                            "sezon_sonu_kalan_yuzde": o["sezon_sonu_kalan_yuzde"], "anahtar": e["anahtar"]})
    if sorted(a["kol"] for a in adaylar) != sorted(TAVANLI):
        raise RuntimeError(f"en iyi seçilemiyor: pay bloğunun benzer ve tahmin koşuları eksik ({adaylar})")
    adaylar.sort(key=lambda a: TAVANLI.index(a["kol"]))
    en_iyi = kalibrasyon.secim(adaylar)
    return {"kol": en_iyi["kol"], "tavan": en_iyi["tavan"], "ad": en_iyi["ad"], "adaylar": adaylar,
            "esik_puan": kalibrasyon.ESIK_PUAN,
            "kural": "tavansız benzer ve tahmin (aynı mal, Ruling R43); bulunabilirliği en yüksek olanın "
                     "esik_puan'dan az gerisindekiler arasında sezon sonu kalanı en düşük olan (eşitlikte benzer)"}


def demo_haritasi(kosular: dict, kal: dict) -> dict:
    """Demo kadranı: pay {lumoda, esit, benzer, tahmin} × `DEMO_TUTMA` → koşu adı (çözümden; benzer ve
    tahmin tavansız, Ruling R43; bulunmayan nokta None). `kal` imza uyumu için."""
    adlar = {}
    for ad, e in kosular.items():
        c = e.get("cozum", {})
        if c.get("yol") != 0 or c.get("takvim") or c.get("repl") != "lumoda":
            continue
        kol = c.get("kol")
        if kol in TAVANLI and c.get("tavan") is not False:
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
    kayit["notlar"] = {
        "en_iyi": "tavansız benzer ve tahminden (aynı mal; Ruling R43). Tavanlı kollar U'nun bir kısmını "
                  "depoda bırakır; tavanın etkisi eslesik bloğunda",
        "belirsizlik": "taban tavansız en iyi; γ SS24'te tavanlı tabanla kalibre edildi (kalibrasyon.json "
                       "belirsizlik_taban, tavan; Ruling R43)",
        "eslesik": "es_<kol>: tavansız kol, t = pay_<kol>_tavanli'nin depoda bıraktığı pay (eslesik_tutma)",
        "kume": "kume_<yapı>: pay kumeleme.kume_payi'dan (küme düzeyi benzer endeksi × mağaza ölçeği), KahinKol ile "
                "(kayıtta kol adı kahin, düzey −1; düzey ve kümeleme kimliği girdi.kume'de); t = 0, tavansız. "
                "kume_gizli yalnız ölçüm kolu (gizli segment)"}
    G = girdi or Girdi(0, ortam, kal)
    secim = json_oku(ortam.secim_yolu) or None
    try:                                   # pay kayıtları varsa seçim onlardan (dosya eskiyse düzelir)
        yeni = secim_yap(kosular, kal)
    except RuntimeError:
        pass
    else:
        if yeni != secim:
            json_yaz(ortam.secim_yolu, yeni)
        secim = yeni
    tum = tum_kosumlar()
    sonuc, gecerli = {}, set()            # gecerli: bu süreçte koşulmuş / önbellekten doğrulanmış

    def kos_tek(s: Kosum, grup: str) -> None:
        k, e = kos_bir(s, G, kal, secim, kosular.get(s.ad))
        kosular[s.ad] = {**e, "grup": grup}       # eski kaydın grubu değil, bu bloğunki
        gecerli.add(s.ad)
        if tut:
            sonuc[s.ad] = k

    def cozulmus(s: Kosum) -> Kosum:
        """Eşleşik tutmanın t'si kaynağın (tavanlı pay koşusu) kaydından; oyun.json `eslesik_tutma`."""
        if s.tutma_kaynagi is None:
            return s
        ka = s.tutma_kaynagi
        if ka not in gecerli:
            kos_tek(tum[ka], kosular.get(ka, {}).get("grup", "pay"))
        an = kosular[ka]["anahtar"]
        k = motor._oku_tembel(motor._dizin(ortam.onbellek, ka, an), an)
        if k is None:
            raise RuntimeError(f"{s.ad}: kaynak koşu {ka} önbellekte yok")
        es = eslesik_tutma(k, G.w, G.harita, ortam.sezon)
        kayit.setdefault("eslesik_tutma", {})[s.ad] = {"kaynak": ka, "anahtar": an, **es}
        print(f"{s.ad}: t = {es['tutma']} ({ka}: {es['giden_adet']:,} / {es['U_adet']:,} adet)", flush=True)
        return replace(s, tutma=es["tutma"])

    def kos_liste(kosumlar, grup):
        for s in kosumlar:
            s = cozulmus(s)
            im = imza(cozumle(s, kal, secim))
            taban = next((a for a, e in kosular.items()
                          if a != s.ad and e.get("imza") == im and "ayni" not in e), None)
            if taban is None:
                kos_tek(s, grup)
            else:
                if taban not in gecerli:          # eski kayıt: önce tabanın kendisi (önbellekten)
                    kos_tek(cozulmus(tum[taban]), kosular[taban]["grup"])
                kosular[s.ad] = {**kosular[taban], "grup": grup, "kosum": asdict(s), "ayni": taban}
                _ilerleme(s.ad, 0.0, True, ortam.ilerleme_yolu, ayni=taban)
            kayit["girdi"] = G.bilgi
            json_yaz(ortam.oyun_yolu, kayit)

    for b in bloklar:
        if b in SECIM_GEREKEN and secim is None:
            secim = secim_yap(kosular, kal)
            json_yaz(ortam.secim_yolu, secim)
        if b == "kume":
            kk = G.kume_kal
            kayit["kume_kalibrasyon"] = {"sezon": kk.get("sezon"), "karar_gunu": kk.get("karar_gunu"),
                                         "secim": kk["secim"]}
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
    alt.add_parser("kume_kalibrasyon", help="küme payının SS24 koşusuz kalibrasyonu (cikti/kume_kalibrasyon.json)")
    iz = alt.add_parser("izgara", help="oyun ızgarası (cikti/oyun.json, cikti/secim.json)")
    iz.add_argument("--blok", default="hepsi", choices=[*BLOK_SIRASI, "hepsi"])
    iz.add_argument("--ad", action="append", help="yalnız bu koşu(lar) (tekrarlanabilir)")
    a = ap.parse_args(argv)
    uyanik_tut()
    if a.komut == "kume_kalibrasyon":
        d = kume_kalibrasyon_kos()
        print(f"küme kalibrasyonu ({d['sezon']}, karar günü {d['karar_gunu']}, öğrenme {', '.join(d['kapanmis_sezonlar'])}, "
              f"{d['sure_sn']:.0f} sn):", flush=True)
        for y, sec in d["secim"].items():
            print(f"  {y:<6} bas {sec['bas']} ({' × '.join(sec['hiyerarsi'][0]) or 'genel'}), en_az {sec['en_az']}, "
                  f"WAPE {sec['wape']:.4f}{' (ızgara ucunda)' if sec['izgara_ucunda'] else ''}", flush=True)
    elif a.komut == "kalibrasyon":
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
