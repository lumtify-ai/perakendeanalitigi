"""Vakanın simülasyon çekirdeği: yayımlanan dünyanın paketli kopyası, politikalar, koşu önbelleği ve
anahtarı (spec §0/7, Ruling R14). Ölçüm (`kosucu.olc`, korunum, giden paket) ve ızgara (`oyun`)
burada değildir: onların kodu değişince simülasyon önbelleği bozulmaz, yalnız ölçüm yeniden yapılır.

    k = kos("p2", desenler, atama, ns)                       # KosuKaydi (TAM, önbellekli, tembel)
    kos("dogrulama", [LUMODA_PAKET], None, None)             # doğrulama kolu (İlk Sevkiyat Lumoda'sı)

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py`'de izinli): `perakende_veri`'yi ve İlk
Sevkiyat'ın motorunu içe aktarır. Karar modülleri (`politika` dahil) bunu aktarmaz.

**Koşu** (`kos`). İlk Sevkiyat'ın `motor.kos`'u `paket_secimi` yuvasını açmaz ve yayımlanan dünyayı
koşar; vaka aynı adımları kendi dünya kopyasıyla yapar, motorun parçalarını içe aktararak:

    w2      = dataclasses.replace(w, paketler=paket_ekle(w.paketler, desenler))   (dunya_kopyasi)
    yuvalar paket_secimi = PaketSecimi(atama)          oyun option'larında mağazanın deseni
            ilk_dagitim  = GidenIlkDagitim(ns)         oyun option'larında Lumoda'nın giden paketi;
                           ns None ise Lumoda'nın kendi kuralı (doğrulama kolu)
            replenishment, RPT, markdown Lumoda'nın (İlk Sevkiyat'taki gibi, tepkili)
    simule_et(w2, Politikalar(...), kayit_talep=True, talep_tohumu, operasyon_tohumu)
    gercek  = motor.gercek_tablosu(w2, ham); tablolar = hareket_tablolari(w2, ham)

Oyun option'ları İlk Sevkiyat'ınkiler (SS25 Collection, `allocation.kaynak.oyun_optionlari`); öteki
option'lar Lumoda'nın standart paketi ve ilk dağıtımıdır. İlk dağıtım, RPT ve markdown
`motor.Kaydedici`'yle sarılır (çıktıyı değiştirmez; `kayitlar` İlk Sevkiyat biçiminde); paket
seçimi `PaketKaydi`'yla (oyun option'larında her çağrının [M] indisi; `kayitlar["paket_secimi"]`).
Kayıtlar kararın kendisidir; motorun kırpması `motor.kirpma_tablosu`'nda.

**Önbellek.** `onbellek` (varsayılan `cikti/kosular/`) altında `<ad>_<anahtar[:20]>`, İlk Sevkiyat
motorunun yazıcısı ve okuyucusuyla (aynı dosya düzeni, `meta.json` en son, bozuk kayıt silinir).
İlk Sevkiyat'ın önbelleğine (`vakalar/allocation/cikti/`) yazılmaz: oraya işaret eden `onbellek`
reddedilir. Önbellekte yalnız koşunun tabloları, gizli gerçeği ve kayıtları durur; ölçütler
durmaz (onları `oyun` kendi `oyun.json`'unda ölçüm kodu özetiyle tutar).

**Anahtar** (`hazirla`; Ruling R14: yalnız simüle edilen tabloları değiştirenler). İlk Sevkiyat'ın
`anahtar_icerigi` (ad, parametreler, enjekte edilen yuvaların türü ve `parametreler()` kimliği,
tohumlar, ölçek, gün sayısı, İlk Sevkiyat `KOSU_MODULLERI` + ortak kapanış + v4 kod özeti, v4 DuckDB
parmak izi, kütüphane sürümleri) ve `vaka`: bu paketin simülasyonu etkileyen kodu
(`SIMULASYON_MODULLERI`: bu modül ve paket içi içe aktarma kapanışı, `politika`, `sabitler`,
`__init__`). Ölçüm, ızgara, eğri ve tasarım kodu (`SIMULASYON_DISI`) anahtara girmez: eğri ve
tasarımın sonucu desen, atama ve `ns` olarak `parametreler`'e ve politikaların kimliğine girer.
`parametreler`: yol, sezon, desenler, eklenen paket satırlarının özeti; paket seçiminin kimliği
atamayı ve haritayı, ilk dağıtımınki ns'in içerik özetini taşır.

**Yollar.** `kos(..., yol=p)`: talep tohumu İlk Sevkiyat'ın `oyun.talep_tohumu(p)`'si (yol 0
yayımlanan dünya). Doğrulama kolu her yolda `kos_dogrulama(p)` (`dogrulama`, `y<p>_dogrulama`).
"""

import dataclasses
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import kaynak as al_kaynak
from allocation import motor
from allocation import oyun as al_oyun
from allocation import sabitler as al_sabitler
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar

from beden_paket import politika, sabitler

OYUN_SEZONU = al_sabitler.OYUN_SEZONU
KOSU_DIZINI = sabitler.CIKTI / "kosular"
PAKET_KOKU = Path(__file__).resolve().parent
# Anahtarın vaka kodu (Ruling R14): simüle edilen tabloları değiştiren modüller, yani bu modül ve
# paket içi içe aktarma kapanışı (test). Paketteki her modül iki listeden birindedir (test).
SIMULASYON_MODULLERI = ("__init__", "politika", "sabitler", "simulasyon")
SIMULASYON_DISI = ("kaynak", "egri", "hakem", "olcutler_egri", "paket_tasarim", "kosucu", "oyun",
                   "hikaye_sec", "hikaye_kos", "senaryolar")
_YOLDAN = "yoldan"           # talep_tohumu verilmezse yolun tohumu


# ---------------------------------------------------------------------------
# Kod özeti, dünya kopyası
# ---------------------------------------------------------------------------


def vaka_kod_dosyalari(kok: Path | None = None) -> dict[str, Path]:
    kok = PAKET_KOKU if kok is None else Path(kok)
    return {f"beden_paket/{m}.py": kok / f"{m}.py" for m in sorted(SIMULASYON_MODULLERI)}


def vaka_kod_ozeti(kok: Path | None = None) -> str:
    """`vaka_kod_dosyalari`'nın göreli yol + içerik sha256'sı (satır sonları LF; `motor.kod_ozeti` gibi).
    `kok`: paket dizini (testler için; varsayılan bu paket)."""
    ozet = hashlib.sha256()
    for ad, yol in vaka_kod_dosyalari(kok).items():
        ozet.update(ad.encode("utf-8") + b"\0")
        ozet.update(yol.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return ozet.hexdigest()


def dunya_kopyasi(w, desenler):
    """(`dataclasses.replace(w, paketler=…)`, harita): yayımlanan dünya değişmez; kopya yalnız
    `paketler`'de ayrılır (öteki alanlar aynı nesneler, önbellekleri `__post_init__` kurar)."""
    df, harita = politika.paket_ekle(w.paketler, desenler)
    return dataclasses.replace(w, paketler=df), harita


def oyun_optionlari(w) -> np.ndarray:
    """Oyun option'larının indisleri (İlk Sevkiyat: `OYUN_SEZONU`'nun Collection option'ları)."""
    return al_kaynak.oyun_optionlari(w, OYUN_SEZONU)


def option_idleri(w, idx) -> list[str]:
    return w.optionlar["option_id"].astype(str).to_numpy()[np.asarray(idx, dtype=np.int64)].tolist()


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
    operasyon_tohumu: int
    gun_sayisi: int | None
    dunya: object                   # paket kopyası
    harita: dict
    desenler: np.ndarray
    oyun: np.ndarray                # oyun option indisleri
    politikalar: dict               # yuva → enjekte edilen politika (sarılmamış)
    icerik: dict
    anahtar: str


def hazirla(ad: str, desenler, atama, ns, *, yol: int = 0, olcek: str = "tam", talep_tohumu=_YOLDAN,
            operasyon_tohumu: int = motor.TOHUM, gun_sayisi: int | None = None) -> Hazirlik:
    """Dünya kopyası, politikalar, anahtar içeriği (modül notu). `atama` None ya da boş: herkes
    standart paket. `ns` None: Lumoda'nın kendi ilk dağıtımı."""
    if not motor._AD_DESENI.match(ad):
        raise ValueError(f"koşu adı dosya adına uygun olmalı: {ad!r}")
    olcek = str(olcek).lower()
    if olcek not in motor.OLCEKLER:
        raise ValueError(f"ölçek {sorted(motor.OLCEKLER)}'den biri olmalı: {olcek!r}")
    yol = int(yol)
    tt = al_oyun.talep_tohumu(yol) if talep_tohumu is _YOLDAN else talep_tohumu
    w = motor.dunya(olcek)
    D = politika.desen_dizisi(desenler)
    w2, harita = dunya_kopyasi(w, D)
    oyun = oyun_optionlari(w)
    ids = option_idleri(w, oyun)
    magazalar = set(w.magazalar["magaza_id"].astype(str))
    bilinmeyen = sorted({str(m) for m in (dict(atama) if atama is not None else {})} - magazalar)
    if ns is not None:
        oyun_kumesi = set(ids)
        bilinmeyen += sorted({str(m) for o, m in ns if str(o) in oyun_kumesi} - magazalar)
    if bilinmeyen:
        raise ValueError(f"atamada ya da ns'te dünyada olmayan mağaza: {bilinmeyen[:5]}")
    verilen = {"paket_secimi": politika.PaketSecimi(atama, harita, desenler=D, optionlar=ids)}
    if ns is not None:
        verilen["ilk_dagitim"] = politika.GidenIlkDagitim(ns, motor.lumoda("ilk_dagitim"), ids)
    turler = {a: motor._tur_adi(p) for a, p in verilen.items()}
    kimlikler = {a: k for a, p in verilen.items() if (k := motor.politika_kimligi(p))}
    yeni = w2.paketler.iloc[len(w.paketler):]
    parametreler = {"yol": yol, "sezon": OYUN_SEZONU, "desenler": D.tolist(),
                    "paket_satirlari": politika._ozet(yeni.astype(str).to_numpy().tolist())}
    icerik = motor.anahtar_icerigi(ad=ad, parametreler=parametreler, talep_tohumu=tt,
                                   operasyon_tohumu=operasyon_tohumu, olcek=olcek, gun_sayisi=gun_sayisi,
                                   turler=turler, politikalar=kimlikler)
    icerik["vaka"] = vaka_kod_ozeti()
    return Hazirlik(ad=ad, olcek=olcek, yol=yol, talep_tohumu=tt, operasyon_tohumu=int(operasyon_tohumu),
                    gun_sayisi=gun_sayisi, dunya=w2, harita=harita, desenler=D, oyun=oyun,
                    politikalar=verilen, icerik=icerik, anahtar=motor._ozet(icerik))


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------


class PaketKaydi:
    """`paket_secimi`'ni sarar: aynen çağırır, aynı nesneyi döndürür; oyun option'larında her çağrının
    [M] indisini kaydeder (çıktıyı değiştirmez). `kayit_tablosu()`: `gun, arg0` (option), `indis`
    (mağaza), `deger` (paket indisi), her mağaza bir satır (indis 0 dahil; `motor.Kaydedici` sıfırı atar)."""

    def __init__(self, temel, oyun):
        self.temel = temel
        self._oyun = frozenset(int(o) for o in oyun)
        self.kayit: list[tuple[int, int, np.ndarray]] = []

    def __call__(self, g, o: int):
        c = self.temel(g, o)
        if int(o) in self._oyun:
            self.kayit.append((int(g.gun), int(o), np.array(c, dtype=np.int64)))
        return c

    def kayit_tablosu(self) -> pd.DataFrame:
        if not self.kayit:
            return pd.DataFrame({s: np.zeros(0, dtype=np.int64) for s in ("gun", "arg0", "indis", "deger")})
        return pd.DataFrame({
            "gun": np.concatenate([np.full(len(c), g) for g, _, c in self.kayit]).astype(np.int64),
            "arg0": np.concatenate([np.full(len(c), o) for _, o, c in self.kayit]).astype(np.int64),
            "indis": np.concatenate([np.arange(len(c)) for *_, c in self.kayit]).astype(np.int64),
            "deger": np.concatenate([c for *_, c in self.kayit]).astype(np.int64)})


def _yazilabilir(onbellek: Path) -> Path:
    onbellek = Path(onbellek)
    yasak = motor.KOSU_DIZINI.resolve().parent                    # vakalar/allocation/cikti
    if onbellek.resolve().is_relative_to(yasak):
        raise ValueError(f"İlk Sevkiyat'ın önbelleği salt okunur: {onbellek}")
    return onbellek


def onbellekte_mi(h: Hazirlik, onbellek: Path = KOSU_DIZINI) -> bool:
    """Koşu `onbellek`'te tam ve anahtarı tutarak var mı (okumadan, silmeden; ızgaranın bütçesi)."""
    meta = motor._dizin(Path(onbellek), h.ad, h.anahtar) / "meta.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("anahtar") == h.anahtar
    except (FileNotFoundError, ValueError):
        return False


def kos(ad: str, desenler, atama, ns, yol: int = 0, olcek: str = "tam", talep_tohumu=_YOLDAN,
        operasyon_tohumu: int = motor.TOHUM, *, onbellek: Path | None = KOSU_DIZINI,
        gun_sayisi: int | None = None, tembel: bool = True):
    """Paketli dünya kopyasında koşu (modül notu); önbellekte varsa koşmadan okur. Dönüş:
    `motor.KosuKaydi` (`tembel`; tablolar istendikçe diskten) ya da `motor.Kosu`. `onbellek=None`
    önbelleği kapatır (tembel olamaz). `olcek` "tam" | "kucuk" (büyük-küçük harf fark etmez);
    `gun_sayisi` testler içindir."""
    if tembel and onbellek is None:
        raise ValueError("tembel koşu kaydı önbellek ister (onbellek=None verildi)")
    h = hazirla(ad, desenler, atama, ns, yol=yol, olcek=olcek, talep_tohumu=talep_tohumu,
                operasyon_tohumu=operasyon_tohumu, gun_sayisi=gun_sayisi)
    if onbellek is not None:
        onbellek = _yazilabilir(onbellek)
        motor._artiklari_sil(onbellek)
        k = (motor._oku_tembel if tembel else motor._oku)(motor._dizin(onbellek, ad, h.anahtar), h.anahtar)
        if k is not None:
            return k

    t0 = time.perf_counter()
    kaydediciler = {a: motor.Kaydedici(motor.lumoda(a)) for a in motor.KAYDEDILENLER if a not in h.politikalar}
    if "ilk_dagitim" in h.politikalar:
        kaydediciler["ilk_dagitim"] = motor.Kaydedici(h.politikalar["ilk_dagitim"])
    paket = PaketKaydi(h.politikalar["paket_secimi"], h.oyun)
    ham = simule_et(h.dunya, Politikalar(**kaydediciler, paket_secimi=paket), gun_sayisi=gun_sayisi,
                    operasyon_tohumu=h.operasyon_tohumu, kayit_talep=True, talep_tohumu=h.talep_tohumu,
                    gecmis_kaydi=False)
    t1 = time.perf_counter()
    gercek = motor.gercek_tablosu(h.dunya, ham)
    del ham["talep"]
    tablolar = v4_tablolar.hareket_tablolari(h.dunya, ham)
    del ham
    kayitlar = {a: pd.DataFrame(p.kayit_tablosu()).reset_index(drop=True)
                for a, p in {**kaydediciler, "paket_secimi": paket}.items()}
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


def dogrulama_adi(yol: int = 0) -> str:
    return "dogrulama" if int(yol) == 0 else f"y{int(yol)}_dogrulama"


def dogrulama_hazirla(yol: int = 0, olcek: str = "tam", **ek) -> Hazirlik:
    return hazirla(dogrulama_adi(yol), [sabitler.LUMODA_PAKET], None, None, yol=yol, olcek=olcek, **ek)


def kos_dogrulama(yol: int = 0, olcek: str = "tam", **ek):
    """Doğrulama kolu: standart paket (Lumoda'nın deseni eklenir, atanmaz), Lumoda'nın ilk dağıtımı."""
    return kos(dogrulama_adi(yol), [sabitler.LUMODA_PAKET], None, None, yol=yol, olcek=olcek, **ek)
