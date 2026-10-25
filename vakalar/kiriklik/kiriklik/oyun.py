"""Oyun: plan önbelleği, ızgara ve ölçüm (tasarım §0 K8, K12, K22; Ruling R7, R17, R24).

    .venv/Scripts/python -m kiriklik.oyun planlar --blok yol0 [--yol P] [--olcek KUCUK]   # planlar, simüle etmez
    .venv/Scripts/python -m kiriklik.oyun izgara  --blok yol0 [--yol P] [--olcek KUCUK]   # Lumoda, planlar, koşular
    .venv/Scripts/python -m kiriklik.oyun olc [--zorla] [--olcek KUCUK]                   # önbellektekileri ölç

`--blok` ∈ {yol0, ablasyon, yollar, hepsi}. TAM çıktı `cikti/` (koşular `cikti/kosular/`), KÜÇÜK `cikti/kucuk/`.

Bu modül ölçüm tarafındadır (`simulasyon.KOSU_DISI`; `tests/test_sizinti.py` OLCUM): kolların planını karar
modülleriyle kurar, `simulasyon.kos`'la koşar, `olcutler`'le ölçer; kahinin girdisini `hakem` kurar.

**Kollar** (K8; `KOLLAR`). `kural` = `kural.kural_plani(g)`; `kural_28` = aynı kural, puan yalnız son 28 gün;
`opt` = `model.coz(g, tahmin.ufuk_talebi(g, og), og.kalinti, orta paket)`, set koşulsuz, verici her mağaza;
`opt_set` = aynısı set koşullu, verici yalnız kırık çift; `kahin` = `opt`'un talebi yerine
`hakem.kahin_girdisi(w, lumoda, g, hücreler, og.iade["magaza"])` (K22; hücreler tahminin hücreleri). Kahin
çözülmeden önce her hücrede fiyat_tam ≥ fiyat_ind ≥ 0 sınanır (`kahin_fiyat_denetimi`, Ruling R17).

**Izgara** (K12; `izgara_listesi`, 47 TAM koşu). Bloklar: `yol0` = yol 0'ın Lumoda'sı + {kural, opt, opt_set, kahin}
× {AW24, SS25}; `ablasyon` = kural_28 × 2 sezon (yol 0); `yollar` = yol 1–4'ün her biri için Lumoda + 8 kol koşusu
(`--yol P` yalnız P). Adlar: Lumoda `simulasyon.lumoda_adi(p)`; kol koşusu yol 0'da `<kol>_<sezon>`, yol p'de
`y<p>_<kol>_<sezon>`. KÜÇÜK ızgara aynı yapıdadır.

**Yol** (`Yol`, yol başına, tembel). (1) Lumoda koşusu (önbellekten ya da koşulur); (2) takvim
`simulasyon.takvim(lumoda)` (bütün kollarda oynatılır, K6, K23); (3) karar girdisi, iki sezon tek bağlantıda:
`karar_veritabani` → `kaynak.karar_girdisi(con, sezon)` ve `tahmin.ogrenilen(con, sezon, onbellek=cikti/ogrenme,
kaynak_kimligi=kk)`; `tahmin.ufuk_talebi` sezon başına bir kez. TAM'da bağlantı `simulasyon.karar_veritabani`'dır
(yol 0 yayımlanan v4, kimlik None; yol p o yolun Lumoda koşusunun yayımlanan biçimi, kimlik koşunun anahtarı). KÜÇÜK
dünyada yayımlanan v4 TAM dünyanın verisidir; bu yüzden KÜÇÜK yol 0 da Lumoda koşusunun yayımlanan biçiminden kurulur
(İndirim Takvimi `Ortam.yayimlanan_mi` kalıbı; `simulasyon.py` koşu anahtarına girdiği için değişmez). Izgara bir
yolun bütün planlarını önce kurar, bağlantıyı ve girdileri bırakır, sonra kol koşularını sırayla koşar.

**Plan önbelleği** (`plan_kur`). `cikti/planlar/<kol>_<sezon>_y<yol>_<anahtar[:20]>.parquet` (hareketler) ve `.json`
(anahtar, içerik, kimlik, bilgi; önce Parquet, sonra JSON, ikisi de geçici adla yazılıp yerine konur). Anahtar
içeriği (`plan_icerigi`): kol, sezon, yol, ölçek, yolun Lumoda koşusunun anahtarı, karar kapanışının kod özeti
(`karar_kod_ozeti`), PuLP sürümü (CBC çözümü sürüme bağlıdır; ek, bedelsiz). Karar kapanışı: kiriklik karar modülleri
(`KARAR_MODULLERI`), `markdown` ogrenme / kaynak / sabitler, onların içe aktardığı `perakende_analitik` modüllerinin
kapanışı (`allocation.motor.ortak_kapanisi`, koşu anahtarındaki gibi), `kahin`'de ayrıca `hakem.py`; ve bu modülün
planı biçimlendiren işlevlerinin kaynağı (`KARAR_FONKSIYONLARI`: kol bağlantısı, bilgi dönüşümü, karar girdisinin
kurulumu); içerik LF'e çevrilir (`simulasyon.vaka_kod_ozeti` gibi). `bilgi["girdi"] = {"yol": yol, "lumoda_anahtari":
…}` (Ruling R7); kural planlarının puan tablosu yazılmaz, yerine `puan_sayisi` (Ruling R24). Önbellekten okunan
planın girdisi istenen yol ve Lumoda anahtarı değilse ya da kimliği kayıtlıdan farklıysa `ValueError` (yol p'nin kararı yol 0
verisinden kurulmuş olamaz; Review Focus). Plan koşunun anahtarına kimliğiyle girer (`simulasyon` modül notu).

**Ölçüm** (`olc`, `olcum_kaydi`). Önbellekte bulunan her ızgara koşusu için: `olcutler.korunum`; bir alanı False ise
kayıt `gecerli: false`, ölçüm yok; değilse `olcutler.olc`. `cikti/oyun.json`: `olcek`, `lumoda[yol]` (ad, anahtar,
süreler), `kosular[ad]` (ad, kol, sezon, yol, koşu anahtarı, Lumoda anahtarı, plan kimliği, `olcum_ozeti`, korunum,
gecerli, olcum, süreler ve tepe bellek). Ölçüm önbelleği (Beden ve Koli R14/R18, İndirim Takvimi kalıbı): koşu
anahtarı, Lumoda anahtarı, plan kimliği ve ölçüm kodu (`OLCUM_OZETI`: `olcutler.py` ve onun içe aktardığı kiriklik
modülleri, bu modülün `OLCUM_FONKSIYONLARI` kaynağı, `OLCUM_SURUMU`) aynıysa yeniden ölçülmez (`--zorla` ile ölçülür).
Planı ya da koşusu (ya da yolun Lumoda'sı) önbellekte olmayan koşu atlanır; eski kaydı varsa `{gecerli: false, olcum:
None, atlandi: neden}` ile değiştirilir (Lumoda kaydı da), eski ölçüm geçerli görünmez. `olc` koşmaz ve plan kurmaz.
Her ölçümden sonra `oyun.json` (geçici adla yazılıp yerine konur).

**İlerleme** `cikti/ilerleme.jsonl` (İlk Sevkiyat `oyun._ilerleme`): her plan, koşu, öğrenme ve ölçüm için bir satır
(`tur`, süre, önbellekten mi, sürecin tepe belleği `surec_tepe_gb`; koşuda motorun süresi ve koşunun tepe belleği).
"""

import argparse
import contextlib
import functools
import gc
import hashlib
import importlib.metadata
import inspect
import json
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import duckdb
import markdown
import numpy as np
import pandas as pd
from allocation import motor
from allocation import oyun as al_oyun
from allocation import sabitler as al_sabitler

from kiriklik import hakem, kaynak, kural, model, olcutler, sabitler, simulasyon, tahmin
from kiriklik.plan import Plan

PAKET_KOKU = simulasyon.PAKET_KOKU
CIKTI = PAKET_KOKU.parent / "cikti"
LUMODA = "lumoda"
KOLLAR = ("kural", "kural_28", "opt", "opt_set", "kahin")
ANA_KOLLAR = ("kural", "opt", "opt_set", "kahin")            # her yolda
ABLASYON_KOLLARI = ("kural_28",)                             # yalnız yol 0 (`ablasyon` bloğu)
YOLLAR = tuple(range(al_sabitler.YOL_SAYISI))                # İlk Sevkiyat'ın 5 talep yolu
BLOKLAR = ("yol0", "ablasyon", "yollar")
# Karar kapanışı (plan anahtarı): kolların karar kodu ve onun içe aktardığı İndirim Takvimi modülleri
KARAR_MODULLERI = ("sabitler", "kaynak", "olcu", "uygunluk", "tahmin", "kural", "model", "plan")
MARKDOWN_MODULLERI = ("ogrenme", "kaynak", "sabitler")
# Bu modülde planı biçimlendiren kod (kol bağlantısı, bilgi dönüşümü, karar girdisinin kurulumu): kaynağı karar kod
# özetine girer
KARAR_FONKSIYONLARI = ("_plan_hesapla", "plan_kur", "_girdi", "kahin_fiyat_denetimi", "karar_veritabani",
                       "Yol._baglanti", "Yol.karar_girdisi", "Yol.ogrenilen", "Yol.talep")
# Ölçüm kodu: olcutler.py ve onun içe aktardığı kiriklik modülleri (testle eşit tutulur) + OLCUM_FONKSIYONLARI.
# OLCUM_SURUMU: ölçümü değiştiren ama bu kapsamın dışında kalan her düzeltmede bir artırılır.
OLCUM_MODULLERI = ("olcutler", "kaynak", "olcu", "plan", "sabitler")
OLCUM_FONKSIYONLARI = ("olcum_kaydi",)
OLCUM_SURUMU = 1


# ---------------------------------------------------------------------------
# Izgara
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Is:
    """Izgaranın bir koşusu: Lumoda (`kol == "lumoda"`, sezon None) ya da bir kolun bir sezondaki koşusu."""

    kol: str
    sezon: str | None
    yol: int

    @property
    def ad(self) -> str:
        return kosu_adi(self.kol, self.sezon, self.yol)


def kosu_adi(kol: str, sezon: str | None, yol: int) -> str:
    """Koşunun adı (modül notu); yanlış bileşim `ValueError`."""
    yol = int(yol)
    if yol not in YOLLAR:
        raise ValueError(f"yol {YOLLAR}'dan biri olmalı: {yol}")
    if kol == LUMODA:
        if sezon is not None:
            raise ValueError("Lumoda koşusu sezonsuzdur (iki sezonun ölçümü aynı koşudan)")
        return simulasyon.lumoda_adi(yol)
    if kol not in KOLLAR:
        raise ValueError(f"bilinmeyen kol: {kol!r} (kollar: {KOLLAR})")
    if sezon not in sabitler.TEST_SEZONLARI:
        raise ValueError(f"kol koşusu {sabitler.TEST_SEZONLARI}'den birinde: {sezon!r}")
    if kol in ABLASYON_KOLLARI and yol != 0:
        raise ValueError(f"{kol} yalnız yol 0'da koşar (K8): yol {yol}")
    return f"{kol}_{sezon}" if yol == 0 else f"y{yol}_{kol}_{sezon}"


def _yol_isleri(yol: int, kollar: tuple[str, ...], lumoda: bool) -> list[Is]:
    isler = [Is(LUMODA, None, yol)] if lumoda else []
    return isler + [Is(k, s, yol) for s in sabitler.TEST_SEZONLARI for k in kollar]


def blok_listesi(blok: str, yol: int | None = None) -> list[Is]:
    """Bloğun koşuları sırayla (modül notu); `hepsi` bütün ızgara. `yol` verilirse yalnız o yolunkiler (blokta o yol
    yoksa `ValueError`)."""
    if blok not in (*BLOKLAR, "hepsi"):
        raise ValueError(f"blok {BLOKLAR} ya da 'hepsi' olmalı: {blok!r}")
    liste: list[Is] = []
    if blok in ("yol0", "hepsi"):
        liste += _yol_isleri(0, ANA_KOLLAR, lumoda=True)
    if blok in ("ablasyon", "hepsi"):
        liste += _yol_isleri(0, ABLASYON_KOLLARI, lumoda=False)
    if blok in ("yollar", "hepsi"):
        for p in YOLLAR[1:]:
            liste += _yol_isleri(p, ANA_KOLLAR, lumoda=True)
    if yol is not None:
        if int(yol) not in {i.yol for i in liste}:
            raise ValueError(f"{blok} bloğunda yol {yol} yok")
        liste = [i for i in liste if i.yol == int(yol)]
    return liste


def izgara_listesi(olcek: str = "tam") -> list[Is]:
    """Bütün ızgara (K12): yol0 + ablasyon + yollar; TAM'da 47 koşu, KÜÇÜK'te aynı yapı."""
    if str(olcek).lower() not in motor.OLCEKLER:
        raise ValueError(f"ölçek {sorted(motor.OLCEKLER)}'den biri olmalı: {olcek!r}")
    return blok_listesi("hepsi")


def _yollara(isler: list[Is]) -> dict[int, list[Is]]:
    sonuc: dict[int, list[Is]] = {}
    for i in isler:
        sonuc.setdefault(i.yol, []).append(i)
    return sonuc


# ---------------------------------------------------------------------------
# Ortam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ortam:
    """Koşuların ve çıktının yeri (TAM varsayılan; testler KÜÇÜK dünyada, geçici dizinde)."""

    olcek: str = "tam"
    onbellek: Path = simulasyon.KOSU_DIZINI
    cikti: Path = CIKTI

    @property
    def planlar(self) -> Path:
        return Path(self.cikti) / "planlar"

    @property
    def ogrenme(self) -> Path:
        return Path(self.cikti) / "ogrenme"

    @property
    def oyun_yolu(self) -> Path:
        return Path(self.cikti) / "oyun.json"

    @property
    def ilerleme_yolu(self) -> Path:
        return Path(self.cikti) / "ilerleme.jsonl"


def varsayilan_ortam(olcek: str = "tam") -> Ortam:
    """Ölçeğin varsayılan ortamı: TAM `cikti/` (koşular `cikti/kosular/`), KÜÇÜK `cikti/kucuk/`."""
    olcek = str(olcek).lower()
    if olcek not in motor.OLCEKLER:
        raise ValueError(f"ölçek {sorted(motor.OLCEKLER)}'den biri olmalı: {olcek!r}")
    if olcek == "tam":
        return Ortam()
    return Ortam(olcek=olcek, onbellek=CIKTI / olcek / "kosular", cikti=CIKTI / olcek)


def _ortam_al(olcek: str, o: Ortam | None) -> Ortam:
    o = varsayilan_ortam(olcek) if o is None else o
    if o.olcek != str(olcek).lower():
        raise ValueError(f"ölçek uyuşmuyor: ortam {o.olcek!r}, istenen {olcek!r}")
    return o


def _ilerleme(o: Ortam, ad: str, sn: float, onbellekten: bool, **ek) -> None:
    al_oyun._ilerleme(ad, sn, onbellekten, o.ilerleme_yolu, **ek, surec_tepe_gb=motor._tepe_bellek_gb())


# ---------------------------------------------------------------------------
# Karar kapanışının kod özeti
# ---------------------------------------------------------------------------


def karar_kod_dosyalari(kol: str) -> dict[str, Path]:
    """Kolun planını belirleyen kod (modül notu "Plan önbelleği"): göreli ad → dosya, sıralı."""
    dosyalar = {f"kiriklik/{m}.py": PAKET_KOKU / f"{m}.py" for m in KARAR_MODULLERI}
    if kol == "kahin":
        dosyalar["kiriklik/hakem.py"] = PAKET_KOKU / "hakem.py"
    md_koku = Path(markdown.__file__).resolve().parent
    dosyalar |= {f"markdown/{m}.py": md_koku / f"{m}.py" for m in MARKDOWN_MODULLERI}
    ortak_koku = Path(motor.KOD_KOKLERI["ortak"])
    ortak = motor.ortak_kapanisi(list(dosyalar.values()), ortak_koku, tohum=())
    dosyalar |= {f"ortak/{m}.py": ortak_koku / f"{m}.py" for m in ortak}
    return dict(sorted(dosyalar.items()))


def kod_ozeti(dosyalar: dict[str, Path]) -> str:
    """Göreli ad + içerik sha256'sı (satır sonları LF)."""
    ozet = hashlib.sha256()
    for ad in sorted(dosyalar):
        ozet.update(ad.encode("utf-8") + b"\0")
        ozet.update(Path(dosyalar[ad]).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return ozet.hexdigest()


def _kaynak(ad: str) -> str:
    """Bu modülün `ad` (`f` ya da `Sinif.f`) işlevinin kaynağı, çağrı anındaki nesneden (LF)."""
    nesne = globals()[ad.split(".")[0]]
    for parca in ad.split(".")[1:]:
        nesne = vars(nesne)[parca]
    nesne = getattr(nesne, "__wrapped__", nesne)                   # contextmanager
    return inspect.getsource(nesne).replace("\r\n", "\n")


def karar_metinleri(kol: str) -> dict[str, str]:
    """Karar kod özetinin girdileri: `karar_kod_dosyalari`'nın içerikleri ve `KARAR_FONKSIYONLARI`'nın kaynağı (LF)."""
    m = {ad: y.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") for ad, y in karar_kod_dosyalari(kol).items()}
    return m | {ad: _kaynak(ad) for ad in KARAR_FONKSIYONLARI}


def karar_kod_ozeti(kol: str) -> str:
    """Kolun karar kapanışının özeti (modül notu "Plan önbelleği"; kahin'de `hakem.py` da). Her çağrıda dosyalardan
    ve işlevlerin kaynağından kurulur."""
    m = karar_metinleri(kol)
    h = hashlib.sha256()
    for ad in sorted(m):
        h.update(ad.encode("utf-8") + b"\0" + m[ad].encode("utf-8") + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Plan önbelleği
# ---------------------------------------------------------------------------


def _surum(paket: str) -> str | None:
    try:
        return importlib.metadata.version(paket)
    except importlib.metadata.PackageNotFoundError:
        return None


def plan_icerigi(kol: str, sezon: str, yol: int, olcek: str, lumoda_anahtari: str) -> dict:
    """Plan anahtarının içeriği (modül notu)."""
    kosu_adi(kol, sezon, yol)                                     # bileşim denetimi
    return {"kol": kol, "sezon": sezon, "yol": int(yol), "olcek": str(olcek).lower(),
            "lumoda_anahtari": str(lumoda_anahtari), "kod": karar_kod_ozeti(kol), "pulp": _surum("pulp")}


def plan_anahtari(icerik: dict) -> str:
    return hashlib.sha256(json.dumps(icerik, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _plan_koku(o: Ortam, icerik: dict, anahtar: str) -> Path:
    return o.planlar / f"{icerik['kol']}_{icerik['sezon']}_y{icerik['yol']}_{anahtar[:20]}"


def _girdi(yol: int, lumoda_anahtari: str) -> dict:
    return {"yol": int(yol), "lumoda_anahtari": str(lumoda_anahtari)}


def plan_yaz(o: Ortam, p: Plan, icerik: dict) -> None:
    """Planı önbelleğe yazar (Parquet sonra JSON; ikisi de geçici adla yazılıp yerine konur)."""
    if (p.kol, p.sezon) != (icerik["kol"], icerik["sezon"]):
        raise ValueError(f"plan {p.kol}/{p.sezon}, içerik {icerik['kol']}/{icerik['sezon']}")
    anahtar = plan_anahtari(icerik)
    kok = _plan_koku(o, icerik, anahtar)
    kok.parent.mkdir(parents=True, exist_ok=True)
    pq = kok.with_suffix(".parquet")
    gecici = pq.with_name(pq.name + ".yaziliyor")
    p.hareketler.to_parquet(gecici, index=False)
    gecici.replace(pq)
    al_oyun.json_yaz(kok.with_suffix(".json"), {"anahtar": anahtar, "icerik": icerik, "kimlik": p.kimlik,
                                                "kol": p.kol, "sezon": p.sezon, "bilgi": p.bilgi})


def _plan_oku(o: Ortam, icerik: dict) -> Plan | None:
    """Önbellekteki plan (yoksa None); anahtarı, girdisi ya da kimliği tutmuyorsa `ValueError`."""
    anahtar = plan_anahtari(icerik)
    kok = _plan_koku(o, icerik, anahtar)
    js, pq = kok.with_suffix(".json"), kok.with_suffix(".parquet")
    if not (js.exists() and pq.exists()):
        return None
    d = json.loads(js.read_text(encoding="utf-8"))
    if d.get("anahtar") != anahtar:
        raise ValueError(f"{js.name}: anahtar tutmuyor")
    beklenen = _girdi(icerik["yol"], icerik["lumoda_anahtari"])
    if (d.get("bilgi") or {}).get("girdi") != beklenen:
        raise ValueError(f"{js.name}: planın girdisi {(d.get('bilgi') or {}).get('girdi')}, beklenen {beklenen} "
                         "(plan başka yolun ya da Lumoda koşusunun verisinden kurulmuş)")
    p = Plan(kol=d["kol"], sezon=d["sezon"], hareketler=pd.read_parquet(pq), bilgi=d["bilgi"])
    if p.kimlik != d.get("kimlik"):
        raise ValueError(f"{js.name}: Parquet'ten kurulan planın kimliği kayıtlı kimlikten farklı")
    return p


def _lumoda_dogrula(lumoda_kosusu, yol: int, olcek: str) -> None:
    meta = lumoda_kosusu.meta
    if meta.get("turler") != {}:
        raise ValueError(f"Lumoda koşusu bekleniyordu (enjekte yuva yok): {sorted(meta.get('turler') or {})}")
    kosu_yolu = int((meta.get("parametreler") or {}).get("yol", 0))
    if kosu_yolu != int(yol):
        raise ValueError(f"Lumoda koşusu yol {kosu_yolu}'ın, istenen yol {yol}")
    if meta.get("olcek") != olcek:
        raise ValueError(f"Lumoda koşusunun ölçeği {meta.get('olcek')!r}, istenen {olcek!r}")


def kahin_fiyat_denetimi(talep: pd.DataFrame) -> None:
    """Ruling R17: her hücrede fiyat_tam ≥ fiyat_ind ≥ 0 (programın içbükeylik koşulu); bozan hücreler `ValueError`."""
    ft, fi = talep["fiyat_tam"].to_numpy(dtype=float), talep["fiyat_ind"].to_numpy(dtype=float)
    bozuk = ~((ft >= fi) & (fi >= 0))                              # NaN de bozuk
    if bozuk.any():
        h = talep.loc[bozuk, ["magaza_id", "urun_id", "fiyat_tam", "fiyat_ind"]]
        ornek = ", ".join(f"({r.magaza_id}, {r.urun_id}: {r.fiyat_tam:.2f} / {r.fiyat_ind:.2f})"
                          for r in h.head(10).itertuples())
        raise ValueError(f"kahin girdisinde fiyat_tam ≥ fiyat_ind ≥ 0 tutmayan {int(bozuk.sum())} hücre: {ornek}")


def _plan_hesapla(kol: str, sezon: str, girdiler: "Yol") -> Plan:
    """Kolun planı (modül notu "Kollar"); girdiler yolun karar girdisi, öğrenilenleri ve ufuk talebi."""
    g = girdiler.karar_girdisi(sezon)
    if kol == "kural":
        return kural.kural_plani(g)
    if kol == "kural_28":
        return kural.kural_plani(g, pencereler=(28,), kol="kural_28")
    og, talep = girdiler.ogrenilen(sezon), girdiler.talep(sezon)
    paket = sabitler.MALIYET_PAKETLERI[sabitler.KARAR_PAKETI]
    if kol in ("opt", "opt_set"):
        set_ = kol == "opt_set"
        return model.coz(g, talep, og.kalinti, paket, set_kosulu=set_, verici_yalniz_kirik=set_, kol=kol)
    if kol == "kahin":
        kg = hakem.kahin_girdisi(girdiler.w, girdiler.lumoda, g, talep[["magaza_id", "urun_id"]], og.iade["magaza"])
        kahin_fiyat_denetimi(kg)
        return model.coz(g, kg, og.kalinti, paket, set_kosulu=False, verici_yalniz_kirik=False, kol="kahin")
    raise ValueError(f"bilinmeyen kol: {kol!r}")


def plan_kur(kol: str, sezon: str, yol: int, olcek: str, lumoda_kosusu, *, ortam: Ortam | None = None,
             girdiler: "Yol | None" = None, kur: bool = True) -> Plan | None:
    """Kolun yol `yol`'daki `sezon` planı, önbellekten ya da kurulur (modül notu "Plan önbelleği"). `lumoda_kosusu`
    yolun Lumoda koşusu olmalı; `girdiler` (`Yol`) verilirse karar girdisi ondan (aynı yol ve aynı Lumoda koşusu
    olmalı), yoksa kendi bağlantısını açar. `kur=False`: önbellekte yoksa None (kurmaz)."""
    olcek = str(olcek).lower()
    o = _ortam_al(olcek, ortam)
    _lumoda_dogrula(lumoda_kosusu, yol, olcek)
    lum_anahtar = lumoda_kosusu.meta["anahtar"]
    icerik = plan_icerigi(kol, sezon, yol, olcek, lum_anahtar)
    p = _plan_oku(o, icerik)
    if p is not None or not kur:
        return p
    if girdiler is None:
        with Yol(yol, o, lumoda=lumoda_kosusu) as Y:
            return plan_kur(kol, sezon, yol, olcek, lumoda_kosusu, ortam=o, girdiler=Y)
    if girdiler.yol != int(yol) or girdiler.ortam.olcek != olcek:
        raise ValueError(f"girdiler yol {girdiler.yol} / {girdiler.ortam.olcek}, plan yol {yol} / {olcek}")
    if girdiler.lumoda.meta["anahtar"] != lum_anahtar:
        raise ValueError("girdilerin Lumoda koşusu planın Lumoda koşusu değil")
    t0 = time.perf_counter()
    ham = _plan_hesapla(kol, sezon, girdiler)
    bilgi = dict(ham.bilgi)
    if "puanlar" in bilgi:
        bilgi["puan_sayisi"] = len(bilgi.pop("puanlar"))
    bilgi["girdi"] = _girdi(yol, lum_anahtar)
    plan_yaz(o, Plan(kol=ham.kol, sezon=ham.sezon, hareketler=ham.hareketler, bilgi=bilgi), icerik)
    p = _plan_oku(o, icerik)
    _ilerleme(o, f"plan_{kol}_{sezon}_y{yol}", time.perf_counter() - t0, False, tur="plan",
              hareket=len(p.hareketler), adet=int(p.hareketler["adet"].sum()), durum=p.bilgi.get("durum"),
              gap=p.bilgi.get("gap"))
    return p


# ---------------------------------------------------------------------------
# Yol
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def karar_veritabani(lumoda_kosusu, yol: int, olcek: str) -> Iterator[tuple[duckdb.DuckDBPyConnection, str | None]]:
    """Planın girdisinin bağlantısı ve öğrenme önbelleğinin kaynak kimliği (modül notu "Yol"): TAM ya da yol p > 0
    `simulasyon.karar_veritabani`; KÜÇÜK yol 0 Lumoda koşusunun yayımlanan biçimi geçici bir DuckDB dosyasında,
    kimlik koşunun anahtarı."""
    if olcek == "tam" or int(yol) != 0:
        with simulasyon.karar_veritabani(lumoda_kosusu, yol) as baglanti:
            yield baglanti
        return
    _lumoda_dogrula(lumoda_kosusu, 0, olcek)
    with tempfile.TemporaryDirectory(prefix="kiriklik_kucuk_") as dizin:
        t = simulasyon.yayimlanan(lumoda_kosusu)
        con = duckdb.connect(str(Path(dizin) / "y0_yayimlanan.duckdb"))
        try:
            for ad in sorted(t):
                con.register("_tablo", t.pop(ad))
                con.execute(f"create table {ad} as select * from _tablo")
                con.unregister("_tablo")
            del t
            yield con, lumoda_kosusu.meta["anahtar"]
        finally:
            con.close()


class Yol:
    """Bir yolun Lumoda koşusu, takvimi, karar girdileri, planları ve kol koşuları (modül notu), tembel. Bağlam
    yöneticisidir: çıkışta karar bağlantısı kapanır ve girdiler bırakılır. `lumoda` verilirse o koşu kullanılır
    (yolun Lumoda koşusu olmalı)."""

    def __init__(self, yol: int, ortam: Ortam, lumoda=None):
        self.yol, self.ortam = int(yol), ortam
        if lumoda is not None:
            _lumoda_dogrula(lumoda, self.yol, ortam.olcek)
            self.__dict__["lumoda"] = lumoda
        self._yigin = contextlib.ExitStack()
        self._con: tuple | None = None
        self._g: dict = {}
        self._og: dict = {}
        self._talep: dict = {}

    def __enter__(self) -> "Yol":
        return self

    def __exit__(self, *_) -> None:
        self.girdileri_birak()

    @functools.cached_property
    def w(self):
        return motor.dunya(self.ortam.olcek)

    def lumoda_hazirligi(self) -> simulasyon.Hazirlik:
        return simulasyon.hazirla(simulasyon.lumoda_adi(self.yol), self.yol, self.ortam.olcek, parametreler={})

    def lumoda_var(self) -> bool:
        """Lumoda koşusu bellekte ya da önbellekte mi (koşmadan)."""
        return "lumoda" in vars(self) or simulasyon.onbellekte_mi(self.lumoda_hazirligi(), self.ortam.onbellek)

    @functools.cached_property
    def lumoda(self):
        """Yolun Lumoda koşusu (önbellekten ya da koşulur)."""
        t0 = time.perf_counter()
        k = simulasyon.kos(simulasyon.lumoda_adi(self.yol), self.yol, self.ortam.olcek, parametreler={},
                           onbellek=self.ortam.onbellek, tembel=True)
        _ilerleme(self.ortam, simulasyon.lumoda_adi(self.yol), time.perf_counter() - t0, bool(k.onbellekten),
                  tur="kosu", motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"))
        return k

    @functools.cached_property
    def takvim(self) -> motor.Takvim:
        return simulasyon.takvim(self.lumoda)

    # --- karar girdileri ---------------------------------------------------

    def _baglanti(self) -> tuple[duckdb.DuckDBPyConnection, str | None]:
        if self._con is None:
            self._con = self._yigin.enter_context(karar_veritabani(self.lumoda, self.yol, self.ortam.olcek))
        return self._con

    def karar_girdisi(self, sezon: str) -> kaynak.KararGirdisi:
        if sezon not in self._g:
            self._g[sezon] = kaynak.karar_girdisi(self._baglanti()[0], sezon)
        return self._g[sezon]

    def ogrenilen(self, sezon: str):
        if sezon not in self._og:
            con, kimlik = self._baglanti()
            t0 = time.perf_counter()
            self._og[sezon] = tahmin.ogrenilen(con, sezon, onbellek=self.ortam.ogrenme, kaynak_kimligi=kimlik)
            _ilerleme(self.ortam, f"y{self.yol}_ogrenme_{sezon}", time.perf_counter() - t0, False, tur="ogrenme",
                      kimlik=self._og[sezon].kimlik())
        return self._og[sezon]

    def talep(self, sezon: str) -> pd.DataFrame:
        if sezon not in self._talep:
            self._talep[sezon] = tahmin.ufuk_talebi(self.karar_girdisi(sezon), self.ogrenilen(sezon))
        return self._talep[sezon]

    def girdileri_birak(self) -> None:
        """Karar bağlantısını kapatır, girdileri bırakır (koşulardan önce bellek boşalsın)."""
        self._yigin.close()
        self._yigin = contextlib.ExitStack()
        self._con = None
        self._g.clear()
        self._og.clear()
        self._talep.clear()
        gc.collect()

    # --- planlar ve koşular ------------------------------------------------

    def plan(self, kol: str, sezon: str, kur: bool = True) -> Plan | None:
        return plan_kur(kol, sezon, self.yol, self.ortam.olcek, self.lumoda, ortam=self.ortam, girdiler=self,
                        kur=kur)

    def _kos_argumanlari(self, i: Is, p: Plan) -> dict:
        if i.yol != self.yol or i.kol == LUMODA:
            raise ValueError(f"{i.ad}: bu yolun (yol {self.yol}) kol koşusu değil")
        if p.bilgi.get("girdi") != _girdi(self.yol, self.lumoda.meta["anahtar"]):
            raise ValueError(f"{i.ad}: planın girdisi {p.bilgi.get('girdi')} bu yolun Lumoda koşusu değil")
        return dict(ad=i.ad, yol=self.yol, olcek=self.ortam.olcek, plan=simulasyon.transfer_plani(p, self.w),
                    takvim=self.takvim, karar_gun=simulasyon.karar_gun(i.sezon),
                    parametreler={"sezon": i.sezon, "kol": i.kol})

    def kol_hazirligi(self, i: Is, p: Plan) -> simulasyon.Hazirlik:
        return simulasyon.hazirla(**self._kos_argumanlari(i, p))

    def kos(self, i: Is):
        """Koşunun tembel kaydı (önbellekten ya da koşulur; plan önbellekten ya da kurulur)."""
        if i.kol == LUMODA:
            if i.yol != self.yol:
                raise ValueError(f"{i.ad}: yol {i.yol}, Yol {self.yol}")
            return self.lumoda
        p = self.plan(i.kol, i.sezon)
        t0 = time.perf_counter()
        k = simulasyon.kos(**self._kos_argumanlari(i, p), onbellek=self.ortam.onbellek, tembel=True)
        _ilerleme(self.ortam, i.ad, time.perf_counter() - t0, bool(k.onbellekten), tur="kosu",
                  motor_sn=k.meta.get("motor_sn"), tepe_gb=k.meta.get("tepe_bellek_gb"), plan=p.kimlik[:12])
        return k


# ---------------------------------------------------------------------------
# Planlar ve ızgara
# ---------------------------------------------------------------------------


def planlar(blok: str = "yol0", olcek: str = "tam", *, yol: int | None = None, ortam: Ortam | None = None
            ) -> dict[str, Plan]:
    """Bloğun bütün planlarını kurar ya da önbellekten okur, simüle etmez; yolun Lumoda koşusu önbellekte olmalı
    (yoksa `ValueError`). Dönüş `<kol>_<sezon>_y<yol>` → Plan."""
    o = _ortam_al(olcek, ortam)
    sonuc = {}
    for p, isler in _yollara(blok_listesi(blok, yol)).items():
        with Yol(p, o) as Y:
            if not Y.lumoda_var():
                raise ValueError(f"yol {p}'ın Lumoda koşusu önbellekte yok ({o.onbellek}): önce izgara")
            for i in isler:
                if i.kol != LUMODA:
                    sonuc[f"{i.kol}_{i.sezon}_y{p}"] = Y.plan(i.kol, i.sezon)
    return sonuc


def izgara(blok: str = "yol0", olcek: str = "tam", *, yol: int | None = None, ortam: Ortam | None = None
           ) -> list[dict]:
    """Bloğun koşuları sırayla: yol başına Lumoda, bütün planlar (sonra girdiler bırakılır), kol koşuları.
    Ölçmez (`olc`). Yeniden başlatılan ızgara önbellekten sürer. Dönüş koşu başına özet."""
    o = _ortam_al(olcek, ortam)
    ozet = []
    for p, isler in _yollara(blok_listesi(blok, yol)).items():
        with Yol(p, o) as Y:
            kollar = [i for i in isler if i.kol != LUMODA]
            for i in kollar:
                Y.plan(i.kol, i.sezon)
            Y.girdileri_birak()
            for i in isler:
                k = Y.kos(i)
                ozet.append({"ad": i.ad, "anahtar": k.meta["anahtar"], "onbellekten": bool(k.onbellekten),
                             "motor_sn": k.meta.get("motor_sn"), "tepe_bellek_gb": k.meta.get("tepe_bellek_gb")})
                del k
                gc.collect()
    return ozet


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def olcum_kaydi(kol_kosusu, lumoda_kosusu, p: Plan, sezon: str) -> dict:
    """Korunum; hepsi True ise ölçüm (modül notu "Ölçüm"): {korunum, gecerli, olcum}."""
    korunum = olcutler.korunum(kol_kosusu, lumoda_kosusu, p, sabitler.KARAR[sezon])
    gecerli = all(korunum.values())
    return {"korunum": korunum, "gecerli": gecerli,
            "olcum": olcutler.olc(kol_kosusu, lumoda_kosusu, p, sezon) if gecerli else None}


def olcum_metinleri() -> dict[str, str]:
    """Ölçüm özetinin girdileri (LF): `kiriklik/<m>.py` (`OLCUM_MODULLERI`) ve `OLCUM_FONKSIYONLARI` kaynağı."""
    m = {f"kiriklik/{ad}.py": (PAKET_KOKU / f"{ad}.py").read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
         for ad in OLCUM_MODULLERI}
    for ad in OLCUM_FONKSIYONLARI:
        m[ad] = inspect.getsource(globals()[ad]).replace("\r\n", "\n")
    return m


def olcum_ozeti(metinler: dict[str, str], surum: int) -> str:
    h = hashlib.sha256()
    for ad in sorted(metinler):
        h.update(ad.encode("utf-8") + b"\0" + metinler[ad].encode("utf-8") + b"\0")
    h.update(f"surum={int(surum)}".encode())
    return h.hexdigest()


def olcum_kodu() -> str:
    """Ölçüm kodunun özeti (içe aktarma anında kurulan `OLCUM_OZETI`)."""
    return OLCUM_OZETI


def _guncel(onceki: dict | None, anahtar: str, lumoda_anahtari: str, plan_kimligi: str, kod: str) -> bool:
    return bool(onceki) and (onceki.get("anahtar"), onceki.get("lumoda_anahtari"), onceki.get("plan_kimligi"),
                             onceki.get("olcum_ozeti")) == (anahtar, lumoda_anahtari, plan_kimligi, kod)


def _atla(o: Ortam, kayitlar: dict, i: Is, neden: str) -> None:
    """Atlanan koşu: ilerleme satırı; eski kaydı varsa geçersiz kayıtla değiştirilir (eski ölçüm kalmaz)."""
    _ilerleme(o, i.ad, 0.0, False, tur="olcum", atlandi=neden)
    if i.ad in kayitlar:
        kayitlar[i.ad] = {"ad": i.ad, "kol": i.kol, "sezon": i.sezon, "yol": i.yol, "gecerli": False, "olcum": None,
                          "atlandi": neden}


def olc(zorla: bool = False, olcek: str = "tam", *, ortam: Ortam | None = None) -> dict:
    """Önbellekte bulunan her ızgara koşusunu ölçer (modül notu "Ölçüm"); koşmaz, plan kurmaz. Dönüş `oyun.json`'un
    içeriği."""
    o = _ortam_al(olcek, ortam)
    kayit = al_oyun.json_oku(o.oyun_yolu)
    if kayit.get("olcek", o.olcek) != o.olcek:
        raise ValueError(f"{o.oyun_yolu} {kayit['olcek']!r} ölçeğinde; istenen {o.olcek!r}")
    kayit["olcek"] = o.olcek
    lumodalar, kosular = kayit.setdefault("lumoda", {}), kayit.setdefault("kosular", {})
    for p, isler in _yollara(izgara_listesi(o.olcek)).items():
        Y = Yol(p, o)
        if not Y.lumoda_var():
            neden = "Lumoda koşusu önbellekte yok"
            _ilerleme(o, simulasyon.lumoda_adi(p), 0.0, False, tur="olcum", atlandi=neden)
            if str(p) in lumodalar:
                lumodalar[str(p)] = {"ad": simulasyon.lumoda_adi(p), "gecerli": False, "atlandi": neden}
            for i in isler:
                if i.kol != LUMODA:
                    _atla(o, kosular, i, neden)
            continue
        lum = Y.lumoda
        lumodalar[str(p)] = {"ad": simulasyon.lumoda_adi(p), "anahtar": lum.meta["anahtar"],
                             "talep_tohumu": lum.meta.get("talep_tohumu"), "motor_sn": lum.meta.get("motor_sn"),
                             "kosu_sn": lum.meta.get("sure_sn"), "tepe_bellek_gb": lum.meta.get("tepe_bellek_gb")}
        al_oyun.json_yaz(o.oyun_yolu, kayit)
        for i in isler:
            if i.kol == LUMODA:
                continue
            pl = Y.plan(i.kol, i.sezon, kur=False)
            if pl is None:
                _atla(o, kosular, i, "plan önbellekte yok")
                continue
            h = Y.kol_hazirligi(i, pl)
            if not simulasyon.onbellekte_mi(h, o.onbellek):
                _atla(o, kosular, i, "koşu önbellekte yok")
                continue
            kod = olcum_kodu()
            if not zorla and _guncel(kosular.get(i.ad), h.anahtar, lum.meta["anahtar"], pl.kimlik, kod):
                _ilerleme(o, i.ad, 0.0, True, tur="olcum", olculdu=False, gecerli=kosular[i.ad]["gecerli"])
                continue
            t0 = time.perf_counter()
            k = Y.kos(i)
            olcum = olcum_kaydi(k, lum, pl, i.sezon)
            sn = time.perf_counter() - t0
            kosular[i.ad] = json.loads(json.dumps({
                "ad": i.ad, "kol": i.kol, "sezon": i.sezon, "yol": i.yol, "anahtar": k.meta["anahtar"],
                "lumoda_anahtari": lum.meta["anahtar"], "plan_kimligi": pl.kimlik, "olcum_ozeti": kod, **olcum,
                "olcum_sn": round(sn, 1), "motor_sn": k.meta.get("motor_sn"), "kosu_sn": k.meta.get("sure_sn"),
                "tepe_bellek_gb": k.meta.get("tepe_bellek_gb")}, default=_json_degeri))
            del k
            gc.collect()
            al_oyun.json_yaz(o.oyun_yolu, kayit)
            _ilerleme(o, i.ad, sn, True, tur="olcum", olculdu=True, gecerli=olcum["gecerli"])
    al_oyun.json_yaz(o.oyun_yolu, kayit)
    return kayit


def _json_degeri(x):
    if isinstance(x, np.generic):
        return x.item()
    raise TypeError(type(x).__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m kiriklik.oyun")
    alt = ap.add_subparsers(dest="komut", required=True)
    pl = alt.add_parser("planlar", help="bloğun planlarını kur (Lumoda koşuları gerekir; simüle etmez)")
    iz = alt.add_parser("izgara", help="bloğun Lumoda, plan ve kol koşuları (ölçmez)")
    for p in (pl, iz):
        p.add_argument("--blok", required=True, choices=[*BLOKLAR, "hepsi"])
        p.add_argument("--yol", type=int, default=None, help="yalnız bu yol")
    ol = alt.add_parser("olc", help="önbellekteki koşuları ölç (cikti/oyun.json; koşmaz)")
    ol.add_argument("--zorla", action="store_true", help="ölçüm kodu aynı olsa da yeniden ölç")
    for p in (pl, iz, ol):
        p.add_argument("--olcek", default="TAM", type=str.upper, choices=["TAM", "KUCUK"])
    a = ap.parse_args(argv)
    al_oyun.uyanik_tut()
    t0 = time.perf_counter()
    olcek = a.olcek.lower()
    if a.komut == "planlar":
        sonuc = planlar(a.blok, olcek, yol=a.yol)
        print(f"{len(sonuc)} plan", flush=True)
    elif a.komut == "izgara":
        izgara(a.blok, olcek, yol=a.yol)
    else:
        k = olc(zorla=a.zorla, olcek=olcek)["kosular"]
        print(f"{sum(bool(r['gecerli']) for r in k.values())}/{len(k)} geçerli koşu", flush=True)
    print(f"{a.komut} bitti: {time.perf_counter() - t0:.0f} sn", flush=True)


# Ölçüm kodunun özeti, içe aktarma anında bir kez (bütün işlevler tanımlandıktan sonra)
OLCUM_OZETI = olcum_ozeti(olcum_metinleri(), OLCUM_SURUMU)


if __name__ == "__main__":
    main()
