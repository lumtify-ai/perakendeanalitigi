"""Vakanın simülasyon kapısı (spec §0/11, §0/13, §4.1): v4 motoru, kollar, RPT takvimi, koşu önbelleği.

    lum = kos(lumoda_adi(p), None, yol=p, parametreler={}, rpt_takvimi=None)        # yolun Lumoda'sı
    tk  = rpt_takvimi(lum)                                                           # aynı mal (R4)
    k   = kos("opt_SS25", lambda temel: Optimizasyon(temel, idx, og, "serbest", "kampanya"),
              yol=p, parametreler={"sezon": "SS25"}, rpt_takvimi=tk)                 # KosuKaydi
    yayimlanan(lum)                                                                  # yolun öğrenme girdisi

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py` `OLCUM_MODULLERI`): `perakende_veri`'yi ve İlk
Sevkiyat'ın motorunu içe aktarır, gizli gerçeğe dokunur (`gercek` tablosu). Karar modülleri bunu içe
aktarmaz; kol nesnesini `kol_kur` kurar ve kol yalnız `Gorunum`'ü okur.

**Koşu** (`kos`). İlk Sevkiyat'ın `motor.kos`'unun adımları, vakanın yuvalarıyla:

    markdown      kol_kur(temel), temel = motor.lumoda("markdown") (kol ötekileri Lumoda'ya devreder);
                  kol_kur None ise motor.Kaydedici(motor.lumoda("markdown"))
    rpt           rpt_takvimi verilmişse motor.Kaydedici(TakvimRPT(motor.lumoda("rpt"), takvim,
                  optionlar = bütün option'lar)) (Ruling R4: aynı yolun Lumoda RPT'si yeniden oynatılır);
                  None ise motor.Kaydedici(motor.lumoda("rpt"))
    ilk_dagitim   motor.Kaydedici(motor.lumoda("ilk_dagitim")); öteki yuvalar Lumoda (kaydedilmez)
    simule_et(w, Politikalar(...), kayit_talep=True, talep_tohumu=talep_tohumu(yol),
              operasyon_tohumu=motor.TOHUM, gecmis_kaydi=False)     # R12: kol oran geçmişini kendi tutar
    gercek = motor.gercek_tablosu(w, ham); tablolar = hareket_tablolari(w, ham)

Karar kolunda (`kol_kur` verilmiş) `rpt_takvimi` zorunludur ve `parametreler["sezon"]` koşunun tek test
sezonudur (Ruling R5): kolun `test_idx`'i o sezonun Collection option'larıyla birebir olmalıdır.
`kol_kur(temel)` dönen kolun `temel`'i verilen Lumoda kuralı olmalıdır (kimliği anahtara onun
üstünden girer). Kayıtlar `kayitlar[yuva]`: `markdown` kolun `kayit_tablosu()`'su (Lumoda koşusunda
kaydedicinin [O, 3] kaydı); `rpt` RPT kaydedicisinin kaydı (takvimli koşuda takvimin oynattığı
siparişler, yani Lumoda koşusunun RPT kaydının aynısı; testli); `ilk_dagitim` Lumoda'nınki.

**Önbellek** `onbellek` (varsayılan `cikti/kosular/`) altında `<ad>_<anahtar[:20]>`, İlk Sevkiyat
motorunun yazıcısı ve okuyucusuyla. İlk Sevkiyat'ın çıktı dizinine (`vakalar/allocation/cikti/`)
işaret eden `onbellek` reddedilir.

**Anahtar** (`hazirla`). `motor.anahtar_icerigi`: ad, `parametreler` (çağıranınki + `yol`), enjekte
edilen yuvaların türü ve `politika_kimligi`'si (kolun `parametreler()`'i: kol, pencere, taban, test
option'ları, kip, ε kaynağı, α, öğrenilenin içerik kimliği, kahin girdisinin kimliği; `temel` zinciri
özyinelemeli; RPT yuvasında takvimin içerik kimliği ve option'ları), tohumlar, ölçek, gün sayısı, İlk
Sevkiyat kod özeti, v4 parmak izi, kütüphane sürümleri. `icerik["vaka"] = vaka_kod_ozeti()`: bu
paketin simülasyonu etkileyen kodu (`SIMULASYON_MODULLERI` ve onların ortak paket kapanışı; satır
sonları LF). Ölçüm kodu (`KOSU_DISI`: hakem, ölçütler, oyun, hikâye) anahtara girmez; kahin
girdisini hakem kurar ama girdinin içeriği kolun kimliğindedir.

**Yollar.** Talep tohumu İlk Sevkiyat'ın `oyun.talep_tohumu(yol)`'u (yol 0 yayımlanan dünya, `None`).
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import motor
from allocation import oyun as al_oyun
from allocation.politika import TakvimRPT
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar

from markdown import kaynak, sabitler

PAKET_KOKU = Path(__file__).resolve().parent
KOSU_DIZINI = PAKET_KOKU.parent / "cikti" / "kosular"
# Anahtarın vaka kodu: simüle edilen tabloları değiştiren modüller (bu modülün paket içi içe aktarma
# kapanışı ve kolların kapanışı; test). Paketteki her modül iki listeden tam birindedir (test).
SIMULASYON_MODULLERI = ("__init__", "sabitler", "kaynak", "ogrenme", "tahmin", "model", "politika",
                        "simulasyon")
KOSU_DISI = ("hakem", "olcutler", "oyun", "hikaye")
SEZONLAR = sabitler.TEST_SEZONLARI + sabitler.KAL_SEZONLARI


# ---------------------------------------------------------------------------
# Kod özeti
# ---------------------------------------------------------------------------


def vaka_kod_dosyalari(kok: Path | None = None) -> dict[str, Path]:
    """`markdown/<m>.py` (SIMULASYON_MODULLERI) ve onların içe aktardığı ortak modüllerin kapanışı
    (`ortak/<m>.py`; `motor.ortak_kapanisi`, tohumsuz)."""
    kok = PAKET_KOKU if kok is None else Path(kok)
    vaka = {f"markdown/{m}.py": kok / f"{m}.py" for m in sorted(SIMULASYON_MODULLERI)}
    ortak_koku = Path(motor.KOD_KOKLERI["ortak"])
    ortak = {f"ortak/{m}.py": ortak_koku / f"{m}.py"
             for m in motor.ortak_kapanisi(list(vaka.values()), ortak_koku, tohum=())}
    return dict(sorted({**vaka, **ortak}.items()))


def vaka_kod_ozeti(kok: Path | None = None) -> str:
    """`vaka_kod_dosyalari`'nın göreli yol + içerik sha256'sı (satır sonları LF). `kok`: paket dizini
    (testler için)."""
    ozet = hashlib.sha256()
    for ad, yol in vaka_kod_dosyalari(kok).items():
        ozet.update(ad.encode("utf-8") + b"\0")
        ozet.update(yol.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return ozet.hexdigest()


# ---------------------------------------------------------------------------
# Hazırlık ve anahtar
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Hazirlik:
    """Bir koşunun belirlenmiş girdileri ve anahtarı (koşmadan; `hazirla`)."""

    ad: str
    olcek: str
    yol: int
    talep_tohumu: int | None
    gun_sayisi: int | None
    politikalar: dict          # yuva → enjekte edilen politika (kol, RPT takvim kaydedicisi)
    icerik: dict
    anahtar: str


def lumoda_adi(yol: int = 0) -> str:
    """Yolun Lumoda koşusunun adı: yol 0 `lumoda`, yol p `y<p>_lumoda`."""
    return "lumoda" if int(yol) == 0 else f"y{int(yol)}_lumoda"


def _kol_kur(kol_kur: Callable, w, sezon) -> object:
    if sezon not in SEZONLAR:
        raise ValueError(f"karar kolu `parametreler['sezon']` {SEZONLAR}'den biri olmalı: {sezon!r}")
    temel = motor.lumoda("markdown")
    kol = kol_kur(temel)
    if getattr(kol, "temel", None) is not temel:
        raise ValueError("kol_kur(temel) verilen Lumoda kuralını `temel` olarak taşımalı")
    beklenen = kaynak.test_optionlari(w.optionlar, sezon)
    idx = np.unique(np.asarray(getattr(kol, "test_idx", []), dtype=np.int64))
    if not np.array_equal(idx, beklenen):
        raise ValueError(f"kolun test option'ları {sezon} Collection option'larıyla birebir olmalı "
                         f"(Ruling R5: koşu başına tek test sezonu; {len(idx)} ≠ {len(beklenen)})")
    return kol


def hazirla(ad: str, kol_kur: Callable | None, yol: int = 0, olcek: str = "tam", *, parametreler: dict,
            rpt_takvimi: motor.Takvim | None, gun_sayisi: int | None = None) -> Hazirlik:
    """Politikalar ve anahtar içeriği, koşmadan (modül notu)."""
    if not motor._AD_DESENI.match(ad):
        raise ValueError(f"koşu adı dosya adına uygun olmalı: {ad!r}")
    olcek = str(olcek).lower()
    if olcek not in motor.OLCEKLER:
        raise ValueError(f"ölçek {sorted(motor.OLCEKLER)}'den biri olmalı: {olcek!r}")
    if kol_kur is not None and rpt_takvimi is None:
        raise ValueError("karar kolu RPT takvimi ister (Ruling R4): rpt_takvimi=rpt_takvimi(lumoda_kosusu)")
    yol = int(yol)
    if "yol" in parametreler and int(parametreler["yol"]) != yol:
        raise ValueError(f"parametreler['yol'] ({parametreler['yol']}) yol={yol} ile çelişiyor")
    w = motor.dunya(olcek)
    O = len(w.optionlar)
    verilen = {}
    if rpt_takvimi is not None:
        if int(rpt_takvimi.option_sayisi) != O:
            raise ValueError(f"RPT takviminin option sayısı {rpt_takvimi.option_sayisi} ≠ dünyanın {O}")
        verilen["rpt"] = motor.Kaydedici(TakvimRPT(motor.lumoda("rpt"), rpt_takvimi, np.arange(O)))
    if kol_kur is not None:
        verilen["markdown"] = _kol_kur(kol_kur, w, parametreler.get("sezon"))
    turler = {a: motor._tur_adi(p) for a, p in verilen.items()}
    kimlikler = {a: k for a, p in verilen.items() if (k := motor.politika_kimligi(p))}
    tt = al_oyun.talep_tohumu(yol)
    icerik = motor.anahtar_icerigi(ad=ad, parametreler={**parametreler, "yol": yol}, talep_tohumu=tt,
                                   operasyon_tohumu=motor.TOHUM, olcek=olcek, gun_sayisi=gun_sayisi,
                                   turler=turler, politikalar=kimlikler)
    icerik["vaka"] = vaka_kod_ozeti()
    return Hazirlik(ad=ad, olcek=olcek, yol=yol, talep_tohumu=tt, gun_sayisi=gun_sayisi,
                    politikalar=verilen, icerik=icerik, anahtar=motor._ozet(icerik))


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------


def _yazilabilir(onbellek: Path) -> Path:
    onbellek = Path(onbellek)
    yasak = motor.KOSU_DIZINI.resolve().parent                    # vakalar/allocation/cikti
    if onbellek.resolve().is_relative_to(yasak):
        raise ValueError(f"İlk Sevkiyat'ın önbelleği salt okunur: {onbellek}")
    return onbellek


def kos(ad: str, kol_kur: Callable | None, yol: int = 0, olcek: str = "tam", *, parametreler: dict,
        rpt_takvimi: motor.Takvim | None, onbellek: Path | None = KOSU_DIZINI, gun_sayisi: int | None = None,
        tembel: bool = True):
    """Koşu (modül notu); önbellekte varsa koşmadan okur. Dönüş `motor.KosuKaydi` (`tembel`) ya da
    `motor.Kosu`. `kol_kur` None ve `rpt_takvimi` None: Lumoda koşusu. `onbellek=None` önbelleği
    kapatır (tembel olamaz). `gun_sayisi` testler içindir."""
    if onbellek is not None:
        onbellek = _yazilabilir(onbellek)
    if tembel and onbellek is None:
        raise ValueError("tembel koşu kaydı önbellek ister (onbellek=None verildi)")
    h = hazirla(ad, kol_kur, yol, olcek, parametreler=parametreler, rpt_takvimi=rpt_takvimi,
                gun_sayisi=gun_sayisi)
    if onbellek is not None:
        motor._artiklari_sil(onbellek)
        k = (motor._oku_tembel if tembel else motor._oku)(motor._dizin(onbellek, ad, h.anahtar), h.anahtar)
        if k is not None:
            return k

    t0 = time.perf_counter()
    w = motor.dunya(h.olcek)
    politikalar = {**{a: motor.Kaydedici(motor.lumoda(a)) for a in motor.KAYDEDILENLER
                      if a not in h.politikalar}, **h.politikalar}
    ham = simule_et(w, Politikalar(**politikalar), gun_sayisi=h.gun_sayisi, operasyon_tohumu=motor.TOHUM,
                    kayit_talep=True, talep_tohumu=h.talep_tohumu, gecmis_kaydi=False)
    t1 = time.perf_counter()
    gercek = motor.gercek_tablosu(w, ham)
    del ham["talep"]
    tablolar = v4_tablolar.hareket_tablolari(w, ham)
    del ham
    kayitlar = {a: pd.DataFrame(politikalar[a].kayit_tablosu()).reset_index(drop=True)
                for a in motor.YUVALAR if callable(getattr(politikalar.get(a), "kayit_tablosu", None))}
    meta = {
        "anahtar": h.anahtar,
        **h.icerik,
        "motor_sn": round(t1 - t0, 1),
        "sure_sn": round(time.perf_counter() - t0, 1),
        "tepe_bellek_gb": motor._tepe_bellek_gb(),
        "tablolar": sorted(tablolar),
        "kayitlar": sorted(kayitlar),
        "satir_sayilari": {a: len(d) for a, d in sorted(tablolar.items())} | {"gercek": len(gercek)},
        "gercek_toplamlari": {s: int(gercek[s].to_numpy().sum(dtype=np.int64)) for s in motor.GERCEK_SUTUNLARI},
    }
    kosu = motor.Kosu(tablolar=tablolar, gercek=gercek, meta=meta, kayitlar=kayitlar)
    if onbellek is None:
        return motor._gidis_donus(kosu)
    dizin = motor._dizin(onbellek, ad, h.anahtar)
    motor._yaz(dizin, kosu)
    del kosu, tablolar, gercek
    if tembel:
        k = motor._oku_tembel(dizin, h.anahtar)
        if k is None:
            raise RuntimeError(f"koşu yazıldı ama okunamadı: {dizin}")
        k.onbellekten = False
        return k
    return motor._oku_zorunlu(dizin, h.anahtar)


def onbellekte_mi(h: Hazirlik, onbellek: Path = KOSU_DIZINI) -> bool:
    """Koşu `onbellek`'te tam ve anahtarı tutarak var mı (okumadan, silmeden)."""
    meta = motor._dizin(Path(onbellek), h.ad, h.anahtar) / "meta.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("anahtar") == h.anahtar
    except (FileNotFoundError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Lumoda koşusunun ürünleri
# ---------------------------------------------------------------------------


def _lumoda_mi(kosu) -> None:
    if kosu.meta.get("turler") != {}:
        raise ValueError(f"Lumoda koşusu bekleniyordu (enjekte yuva yok); koşunun yuvaları: "
                         f"{sorted(kosu.meta.get('turler') or {})}")


def rpt_takvimi(lumoda_kosusu) -> motor.Takvim:
    """Yolun Lumoda koşusunun kayıtlı RPT (ve markdown) kararlarından sabitlenmiş `motor.Takvim`
    (Ruling R4; kimliği içerikten, kolun anahtarına girer). Lumoda koşusu değilse `ValueError`."""
    _lumoda_mi(lumoda_kosusu)
    return motor.takvim(lumoda_kosusu).sabitle()


def yayimlanan(kosu) -> dict[str, pd.DataFrame]:
    """Koşunun yayımlanan biçimi (`motor.yayimlanan_bicim`: temiz tablolar + yayımlamanın kirli
    kayıtları; 18 tablo). Yol p'nin Lumoda koşusunda öğrenmenin girdisidir (Ruling R10)."""
    return motor.yayimlanan_bicim({a: kosu.tablo(a) for a in kosu.meta["tablolar"]}, kosu.meta["olcek"])
