"""Vakanın simülasyon kapısı (tasarım §0/6, §0/7, §0/17, §0/23): v4 motoru, transfer yuvası, sabit RPT ve fiyat
takvimi, koşu önbelleği.

    lum = kos(lumoda_adi(p), p, parametreler={})                                  # yolun Lumoda'sı
    tk  = takvim(lum)                                                             # aynı mal (K6, K23)
    with karar_veritabani(lum, p) as (con, kimlik):                               # planın girdisi (K7)
        g = kaynak.karar_girdisi(con, "AW24")
    k   = kos("kural_AW24", p, plan=transfer_plani(plan, w), takvim=tk,
              karar_gun=karar_gun("AW24"), parametreler={"sezon": "AW24", "kol": "kural"})   # KosuKaydi

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py` `SIMULASYON_MODULLERI`): `perakende_veri`'yi ve İlk Sevkiyat'ın
motorunu içe aktarır. Karar modülleri bunu içe aktarmaz; kol yalnız `kiriklik.plan.Plan` üretir, bu modül planı
motor satırlarına çevirir ve yuvaya sokar.

**Koşu** (`kos`). İlk Sevkiyat'ın `motor.kos`'unun adımları, vakanın yuvalarıyla:

    plan None     Lumoda koşusu: yuva enjekte edilmez, üç kaydedici (`motor.KAYDEDILENLER`) Lumoda'yı sarar
                  (`meta["turler"] == {}`)
    plan verilmiş elle_transfer  KirikTransfer(Lumoda elle transferi, plan, karar_gun); kaydedicisiz, çünkü
                                 transferler `sevkiyat` tablosunda (`tip == "elle_transfer"`) görünür
                  rpt            motor.Kaydedici(TakvimRPT(Lumoda RPT'si, takvim, bütün option'lar))
                  markdown       motor.Kaydedici(TakvimMarkdown(Lumoda markdown'ı, takvim, bütün option'lar))
                  ilk_dagitim    motor.Kaydedici(Lumoda'nın ilk dağıtımı); öteki yuvalar Lumoda

Böylece karar gününe kadar her kolun dünyası yolun Lumoda koşusuyla birebir aynıdır; karar gününde plan
yuvadan girer; RPT siparişleri ve fiyat kararları Lumoda koşusunun kaydının yeniden oynatılmasıdır
(`kayitlar["rpt"]` ve `kayitlar["markdown"]` Lumoda'nınkiyle aynıdır, testli) ve kollar arasındaki tek fark
transferdir. Replenishment ve Lumoda'nın bölge müdürü transferleri tepkili kalır.

Plan koşusunda `parametreler` `sezon` (bir test sezonu) ve `kol` taşır; `karar_gun`, o sezonun karar gününün
gün indisi olmalıdır (`karar_gun(sezon)`). Karar kodundaki (kural, model, tahmin, uygunluk) bir değişiklik
anahtara **planın kimliğiyle** girer (`KirikTransfer.parametreler()`); bu yüzden o modüllerin baytı anahtarda
yoktur.

**Önbellek** `onbellek` (varsayılan `cikti/kosular/`) altında `<ad>_<anahtar[:20]>`, İlk Sevkiyat motorunun
yazıcısı ve okuyucusuyla. İlk Sevkiyat'ın çıktı dizinine (`vakalar/allocation/cikti/`) işaret eden `onbellek`
reddedilir.

**Anahtar** (`hazirla`). `motor.anahtar_icerigi`: ad, `parametreler` (çağıranınki + `yol`), enjekte edilen
yuvaların türü ve `politika_kimligi`'si (transfer yuvasında planın ve karar gününün kimliği, `temel`'in türü;
RPT ve markdown yuvalarında takvimin içerik kimliği ve option'ları), tohumlar, ölçek, gün sayısı, İlk Sevkiyat kod
özeti, v4 parmak izi, kütüphane sürümleri. `icerik["vaka"] = vaka_kod_ozeti()`: bu paketin simülasyonu etkileyen kodu
(`SIMULASYON_MODULLERI`; satır sonları LF). Öteki modüller (`KOSU_DISI`) anahtara girmez.

**Yollar.** Talep tohumu İlk Sevkiyat'ın `oyun.talep_tohumu(yol)`'u (yol 0 yayımlanan dünya, `None`). Yol p > 0'da
planın girdisi o yolun Lumoda koşusunun yayımlanan biçimidir (`karar_veritabani`).
"""

import contextlib
import gc
import hashlib
import json
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from allocation import motor
from allocation import oyun as al_oyun
from allocation.politika import TakvimMarkdown, TakvimRPT
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar
from perakende_veri.v4.takvim import gun_indisi

from kiriklik import kaynak, sabitler
from kiriklik.plan import Plan
from kiriklik.politika import KirikTransfer, TransferPlani

PAKET_KOKU = Path(__file__).resolve().parent
KOSU_DIZINI = PAKET_KOKU.parent / "cikti" / "kosular"
# Anahtarın vaka kodu: simüle edilen tabloları değiştiren modüller. Karar modülleri burada değildir: karar
# değişikliği planın kimliğiyle anahtara girer. Paketteki her modül iki listeden tam birindedir (tests/test_sizinti.py);
# henüz yazılmamış modüller listede durabilir.
SIMULASYON_MODULLERI = ("__init__", "politika", "simulasyon")
KOSU_DISI = ("sabitler", "kaynak", "olcu", "uygunluk", "tahmin", "kural", "model", "plan",
             "hakem", "olcutler", "oyun", "hikaye")
_PLAN_SIRASI = ["option_id", "alici", "verici", "beden_sira"]       # `plan.Plan.kimlik`'in satır sırası


# ---------------------------------------------------------------------------
# Kod özeti
# ---------------------------------------------------------------------------


def vaka_kod_dosyalari(kok: Path | None = None) -> dict[str, Path]:
    """`kiriklik/<m>.py` (SIMULASYON_MODULLERI) ve onların içe aktardığı ortak modüllerin kapanışı
    (`ortak/<m>.py`; `motor.ortak_kapanisi`, tohumsuz)."""
    kok = PAKET_KOKU if kok is None else Path(kok)
    vaka = {f"kiriklik/{m}.py": kok / f"{m}.py" for m in sorted(SIMULASYON_MODULLERI)}
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
# Karar günü ve plan
# ---------------------------------------------------------------------------


def _sezon_kontrol(sezon) -> str:
    if sezon not in sabitler.TEST_SEZONLARI:
        raise ValueError(f"test sezonu değil: {sezon!r} (geçerli: {sabitler.TEST_SEZONLARI})")
    return sezon


def _sezon_karar_gunu(sezon) -> int:
    return gun_indisi(sabitler.KARAR[_sezon_kontrol(sezon)])


def karar_gun(sezon: str) -> int:
    """Sezonun karar gününün v4 dünyasındaki gün indisi (`perakende_veri.v4.takvim.gun_indisi`;
    `sabitler.KARAR`); test sezonu dışı `ValueError`."""
    return _sezon_karar_gunu(sezon)


def transfer_plani(plan: Plan, w) -> TransferPlani:
    """`Plan.hareketler`'i dünyanın satır indislerine çevirir: verici → `kaynak`, alıcı → `hedef` (`w.magazalar`
    satır indisi), urun_id → `sku` (`w.urunler` satır indisi), `adet`; kimlik = `plan.kimlik`. Satırlar planın
    kimliğindeki sırada (option_id, alici, verici, beden_sira) dizilir: aynı plan, girdi sırasından bağımsız,
    aynı koşuyu verir (motor aynı kaynaktan satırları sırayla tüketir). Dünyada olmayan mağaza ya da ürün
    `ValueError`."""
    h = plan.hareketler.sort_values(_PLAN_SIRASI, kind="mergesort")
    mag = pd.Index(w.magazalar["magaza_id"].astype(str))
    urun = pd.Index(w.urunler["urun_id"].astype(str))
    if mag.has_duplicates or urun.has_duplicates:
        raise ValueError("dünyada tekrarlı magaza_id ya da urun_id var")
    kaynak_ = mag.get_indexer(h["verici"].astype(str))
    hedef = mag.get_indexer(h["alici"].astype(str))
    sku = urun.get_indexer(h["urun_id"].astype(str))
    for ad, indis, kimlikler in (("verici", kaynak_, h["verici"]), ("alici", hedef, h["alici"]),
                                 ("urun_id", sku, h["urun_id"])):
        if (indis < 0).any():
            eksik = sorted(set(kimlikler.astype(str)[indis < 0]))[:5]
            raise ValueError(f"plan `{ad}` dünyada yok: {eksik}")
    return TransferPlani(kaynak=kaynak_, hedef=hedef, sku=sku, adet=h["adet"].to_numpy(dtype=np.int64),
                         kimlik=plan.kimlik)


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
    politikalar: dict          # yuva → enjekte edilen politika (transfer yuvası, RPT ve markdown takvim kaydedicileri)
    icerik: dict
    anahtar: str


def lumoda_adi(yol: int = 0) -> str:
    """Yolun Lumoda koşusunun adı: yol 0 `lumoda`, yol p `y<p>_lumoda`."""
    return "lumoda" if int(yol) == 0 else f"y{int(yol)}_lumoda"


def _plan_kontrol(plan: TransferPlani, takvim: motor.Takvim | None, karar: int | None, parametreler: dict,
                  w, gun_sayisi: int | None) -> None:
    if takvim is None:
        raise ValueError("plan koşusu takvim ister (K6, K23): takvim=takvim(lumoda_kosusu)")
    if karar is None:
        raise ValueError("plan koşusu karar_gun ister: karar_gun=karar_gun(sezon)")
    sezon = parametreler.get("sezon")
    if sezon not in sabitler.TEST_SEZONLARI:
        raise ValueError(f"plan koşusu `parametreler['sezon']` {sabitler.TEST_SEZONLARI}'dan biri olmalı: {sezon!r}")
    kol = parametreler.get("kol")
    if not isinstance(kol, str) or not kol:
        raise ValueError(f"plan koşusu `parametreler['kol']` (kolun adı) ister: {kol!r}")
    if int(karar) != _sezon_karar_gunu(sezon):
        raise ValueError(f"karar_gun {karar}, {sezon} karar gününe ({_sezon_karar_gunu(sezon)}) eşit olmalı")
    if gun_sayisi is not None and int(gun_sayisi) <= int(karar):
        raise ValueError(f"gun_sayisi {gun_sayisi} karar gününü ({karar}) kapsamıyor: plan hiç uygulanmaz")
    O = len(w.optionlar)
    if int(takvim.option_sayisi) != O:
        raise ValueError(f"takvimin option sayısı {takvim.option_sayisi} ≠ dünyanın {O}")
    for ad, ust in (("kaynak", len(w.magazalar)), ("hedef", len(w.magazalar)), ("sku", len(w.urunler))):
        a = getattr(plan, ad)
        if len(a) and (int(a.min()) < 0 or int(a.max()) >= ust):
            raise ValueError(f"plan `{ad}` dünya dışı: [{int(a.min())}, {int(a.max())}] ∉ [0, {ust})")
    if len(plan) and int(plan.adet.min()) <= 0:
        raise ValueError("plan adetleri pozitif olmalı")


def hazirla(ad: str, yol: int = 0, olcek: str = "tam", *, plan: TransferPlani | None = None,
            takvim: motor.Takvim | None = None, karar_gun: int | None = None, parametreler: dict,
            gun_sayisi: int | None = None) -> Hazirlik:
    """Politikalar ve anahtar içeriği, koşmadan (modül notu)."""
    if not motor._AD_DESENI.match(ad):
        raise ValueError(f"koşu adı dosya adına uygun olmalı: {ad!r}")
    olcek = str(olcek).lower()
    if olcek not in motor.OLCEKLER:
        raise ValueError(f"ölçek {sorted(motor.OLCEKLER)}'den biri olmalı: {olcek!r}")
    yol = int(yol)
    if "yol" in parametreler and int(parametreler["yol"]) != yol:
        raise ValueError(f"parametreler['yol'] ({parametreler['yol']}) yol={yol} ile çelişiyor")
    if plan is None and (takvim is not None or karar_gun is not None):
        raise ValueError("Lumoda koşusu (plan yok) takvim ve karar_gun almaz")
    w = motor.dunya(olcek)
    verilen = {}
    if plan is not None:
        _plan_kontrol(plan, takvim, karar_gun, parametreler, w, gun_sayisi)
        O = len(w.optionlar)
        verilen["elle_transfer"] = KirikTransfer(motor.lumoda("elle_transfer"), plan, karar_gun)
        verilen["rpt"] = motor.Kaydedici(TakvimRPT(motor.lumoda("rpt"), takvim, np.arange(O)))
        verilen["markdown"] = motor.Kaydedici(TakvimMarkdown(motor.lumoda("markdown"), takvim, np.arange(O)))
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


def kos(ad: str, yol: int = 0, olcek: str = "tam", *, plan: TransferPlani | None = None,
        takvim: motor.Takvim | None = None, karar_gun: int | None = None, parametreler: dict,
        onbellek: Path | None = KOSU_DIZINI, gun_sayisi: int | None = None, tembel: bool = True):
    """Koşu (modül notu); önbellekte varsa koşmadan okur. Dönüş `motor.KosuKaydi` (`tembel`) ya da
    `motor.Kosu`. `plan` None: Lumoda koşusu. `onbellek=None` önbelleği kapatır (tembel olamaz).
    `gun_sayisi` testler içindir."""
    if onbellek is not None:
        onbellek = _yazilabilir(onbellek)
    if tembel and onbellek is None:
        raise ValueError("tembel koşu kaydı önbellek ister (onbellek=None verildi)")
    h = hazirla(ad, yol, olcek, plan=plan, takvim=takvim, karar_gun=karar_gun, parametreler=parametreler,
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


def takvim(lumoda_kosusu) -> motor.Takvim:
    """Yolun Lumoda koşusunun kayıtlı RPT ve markdown kararlarından sabitlenmiş `motor.Takvim` (K6, K23; kimliği
    içerikten, plan koşusunun anahtarına girer). Lumoda koşusu değilse `ValueError`."""
    _lumoda_mi(lumoda_kosusu)
    return motor.takvim(lumoda_kosusu).sabitle()


def yayimlanan(kosu) -> dict[str, pd.DataFrame]:
    """Koşunun yayımlanan biçimi (`motor.yayimlanan_bicim`: temiz tablolar + yayımlamanın kirli kayıtları;
    18 tablo). Yol p > 0'da planın girdisidir (K7)."""
    return motor.yayimlanan_bicim({a: kosu.tablo(a) for a in kosu.meta["tablolar"]}, kosu.meta["olcek"])


@contextlib.contextmanager
def karar_veritabani(lumoda_kosusu, yol: int) -> Iterator[tuple[duckdb.DuckDBPyConnection, str | None]]:
    """Planın girdisi için DuckDB bağlantısı ve öğrenme önbelleğinin kaynak kimliği (K7):

        with karar_veritabani(lum, p) as (con, kimlik):
            g = kaynak.karar_girdisi(con, sezon); og = tahmin.ogrenilen(con, sezon, onbellek, kaynak_kimligi=kimlik)

    Yol 0: yayımlanan v4 dosyasına salt okunur bağlantı (`kaynak.baglan()`), kimlik `None` (öğrenme dosya
    kimliğini kendisi bulur); `lumoda_kosusu` kullanılmaz. Yol p > 0: yolun Lumoda koşusunun yayımlanan biçimi
    (`yayimlanan`, 18 tablo) `%TEMP%` altında geçici bir DuckDB dosyasına tablo tablo yazılır (her DataFrame
    yazılınca bırakılır), kimlik Lumoda koşusunun anahtarıdır; çıkışta bağlantı kapanır, dosya silinir."""
    yol = int(yol)
    if yol == 0:
        con = kaynak.baglan()
        try:
            yield con, None
        finally:
            con.close()
        return
    _lumoda_mi(lumoda_kosusu)
    kosu_yolu = int(lumoda_kosusu.meta["parametreler"]["yol"])
    if kosu_yolu != yol:
        raise ValueError(f"Lumoda koşusu yol {kosu_yolu}'ın, istenen yol {yol}")
    with tempfile.TemporaryDirectory(prefix="kiriklik_yol_") as dizin:
        t = yayimlanan(lumoda_kosusu)
        con = duckdb.connect(str(Path(dizin) / f"y{yol}_yayimlanan.duckdb"))
        try:
            for ad in sorted(t):
                con.register("_tablo", t.pop(ad))
                con.execute(f"create table {ad} as select * from _tablo")
                con.unregister("_tablo")
                gc.collect()
            del t
            yield con, lumoda_kosusu.meta["anahtar"]
        finally:
            con.close()
