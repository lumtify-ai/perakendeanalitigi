"""Vakanın koşucusu: yayımlanan dünyanın paketli kopyası, Lumoda'nın giden paketi, doğrulama kolu,
koşu önbelleği, pakete duyarlı ölçütler, talep yolları (spec §0/5–7, §0/11, §0/16, §4.2).

    ns = lumoda_giden(allocation_lumoda(0))                 # Lumoda'nın giden paketi (option, mağaza)
    k = kos("p2", desenler, atama, ns)                       # KosuKaydi (TAM, önbellekli, tembel)
    olc(k)                                                   # İlk Sevkiyat ölçütleri + paket ölçütleri
    kos("dogrulama", [LUMODA_PAKET], None, None)             # doğrulama kolu (İlk Sevkiyat Lumoda'sı)

    .venv/Scripts/python -m beden_paket.kosucu dogrulama [--yol P] [--olcek tam|kucuk]

Bu modül ölçüm tarafındadır (`tests/test_sizinti.py`'de izinli): `perakende_veri`'yi ve İlk
Sevkiyat'ın motorunu ve ölçütlerini içe aktarır. Karar modülleri (`politika` dahil) bunu aktarmaz.

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
reddedilir; o önbellek yalnız `allocation_lumoda` ile salt okunur (hiçbir dosya silinmez). Anahtar
(`hazirla`): İlk Sevkiyat'ın `anahtar_icerigi` (ad, parametreler, enjekte edilen yuvaların türü ve
`parametreler()` kimliği, tohumlar, ölçek, gün sayısı, `KOSU_MODULLERI` + ortak kapanış + v4 kod
özeti, v4 DuckDB parmak izi, kütüphane sürümleri) ve `vaka` (bu paketin koşuyu etkileyen kodu,
`VAKA_KOSU_MODULLERI`). `parametreler`: yol, sezon, desenler, eklenen paket satırlarının özeti; paket
seçiminin kimliği atamayı ve haritayı, ilk dağıtımınki ns'in içerik özetini taşır.

**Ölçüm** (`olc`). İlk Sevkiyat'ın `olcutler.hesapla`'sı (yayımlanan dünyanın açık alanlarıyla;
paket kopyası yalnız `paketler`'de ayrılır) ve pakete duyarlı kayıt ölçütleri (`paket_olcutleri`):
İlk Sevkiyat'ın `kirpilan_adet`'i standart paketi varsayar (`paket_adedi`); vakada

    kirpilan_adet   Σ (istenen − giden paket) × seçilen paketin adedi (`motor.kirpma_tablosu`,
                    oyun option'ları; seçilen paket `kayitlar["paket_secimi"]`'nden, kayıt yoksa
                    setin standart paketi). 7'li paketlerde İlk Sevkiyat'ınkiyle aynı sayı
    kirpilan_hucre  kırpılan (option, mağaza) çifti
    istenen_adet    Σ istenen paket × seçilen paketin adedi (oyun option'ları)
    paket_tipi      oyun option'larının ilk dağıtımında giden ayrı `paket_id` sayısı

Doğrulama kolunda (`ns=None`, standart paket) bütün ölçütler İlk Sevkiyat'ın `lumoda` koşusunun
ölçütleriyle birebir aynıdır (`test_dogrulama_kucuk`; TAM'da `python -m beden_paket.kosucu
dogrulama`). Paket kollarında aynı mal: oyun (option, mağaza) başına giden adet Lumoda'nın giden
adedine eşit, kırpma 0 (`korunum`).

**Lumoda'nın giden paketi** (`lumoda_giden`): bir koşunun `sevkiyat`'ının `ilk_dagitim` satırları;
paket sayısı = beden adedi ÷ paketin (`paket_id`, koşunun `paket` tablosu) o bedendeki içeriği. 12'li
kollar için `ns_donustur` (adet ÷ 12, option toplamı en büyük kalanla mağazalara) ve
`donusum_ozeti` (adet farkı, sıfıra düşen çift).

**Yollar.** `kos(..., yol=p)`: talep tohumu İlk Sevkiyat'ın `oyun.talep_tohumu(p)`'si (yol 0
yayımlanan dünya). `lumoda_ns(p)`: yolun Lumoda `ns`'i; İlk Sevkiyat'ın önbellekli `lumoda` /
`y<p>_lumoda` koşusu salt okunur açılabiliyorsa ondan, yoksa vakanın o yoldaki doğrulama kolundan.
"""

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from allocation import kaynak as al_kaynak
from allocation import motor
from allocation import olcutler as al_olcutler
from allocation import oyun as al_oyun
from allocation import sabitler as al_sabitler
from perakende_veri.v4 import tablolar as v4_tablolar
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.plan import en_buyuk_kalan
from perakende_veri.v4.politika import Politikalar

from beden_paket import politika, sabitler

OYUN_SEZONU = al_sabitler.OYUN_SEZONU
KOSU_DIZINI = sabitler.CIKTI / "kosular"
PAKET_KOKU = Path(__file__).resolve().parent
# Anahtarın vaka kodu: koşuyu etkileyen modüller (kosucu'nun paket içi içe aktarmaları dahil; test)
VAKA_KOSU_MODULLERI = ("__init__", "kosucu", "politika", "sabitler")
_YOLDAN = "yoldan"           # talep_tohumu verilmezse yolun tohumu


# ---------------------------------------------------------------------------
# Kod özeti, dünya kopyası
# ---------------------------------------------------------------------------


def vaka_kod_dosyalari() -> dict[str, Path]:
    return {f"beden_paket/{m}.py": PAKET_KOKU / f"{m}.py" for m in sorted(VAKA_KOSU_MODULLERI)}


def vaka_kod_ozeti() -> str:
    """`vaka_kod_dosyalari`'nın göreli yol + içerik sha256'sı (satır sonları LF; `motor.kod_ozeti` gibi)."""
    ozet = hashlib.sha256()
    for ad, yol in vaka_kod_dosyalari().items():
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


def _option_idleri(w, idx) -> list[str]:
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
    ids = _option_idleri(w, oyun)
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


def kos_dogrulama(yol: int = 0, olcek: str = "tam", **ek):
    """Doğrulama kolu: standart paket (Lumoda'nın deseni eklenir, atanmaz), Lumoda'nın ilk dağıtımı."""
    return kos(dogrulama_adi(yol), [sabitler.LUMODA_PAKET], None, None, yol=yol, olcek=olcek, **ek)


# ---------------------------------------------------------------------------
# Giden paket, ns dönüşümü, korunum
# ---------------------------------------------------------------------------


def _tablo(k, ad: str, sutunlar) -> pd.DataFrame:
    if hasattr(k, "tablo"):
        return k.tablo(ad, sutunlar=list(sutunlar))
    return k[ad][list(sutunlar)].reset_index(drop=True)


ILK_DAGITIM_SUTUNLARI = ["option_id", "magaza_id", "paket_id", "paket", "adet"]


def ilk_dagitim_tablosu(kosu_tablolari) -> pd.DataFrame:
    """İlk dağıtım sevkleri (option, mağaza, paket_id) başına giden paket ve adet. Paket = beden
    adedi ÷ paketin o bedendeki içeriği (koşunun `paket` tablosu); adet içeriğin katı değilse ya da
    bir sevkin bedenleri farklı paket sayısı verirse `RuntimeError`. `kosu_tablolari`: `Kosu`,
    `KosuKaydi` ya da `sevkiyat`, `urun`, `paket` tablolarının sözlüğü."""
    s = _tablo(kosu_tablolari, "sevkiyat", ["tarih", "hedef", "urun_id", "adet", "tip", "paket_id"])
    s = s[(s["tip"].astype(str) == "ilk_dagitim").to_numpy()]
    if not len(s):
        return pd.DataFrame({c: pd.Series([], dtype=object if c.endswith("_id") else np.int64)
                             for c in ILK_DAGITIM_SUTUNLARI})
    u = _tablo(kosu_tablolari, "urun", ["urun_id", "option_id", "beden_sira"])
    u = u.set_index(u["urun_id"].astype(str))
    p = _tablo(kosu_tablolari, "paket", ["paket_id", "beden_sira", "adet"])
    urun = s["urun_id"].astype(str)
    t = pd.DataFrame({
        "tarih": s["tarih"].to_numpy(),
        "option_id": urun.map(u["option_id"].astype(str)).to_numpy(),
        "magaza_id": s["hedef"].astype(str).to_numpy(),
        "paket_id": s["paket_id"].astype(str).to_numpy(),
        "beden_sira": urun.map(u["beden_sira"]).to_numpy(dtype=np.int64),
        "adet": s["adet"].to_numpy(dtype=np.int64),
    })
    p = pd.DataFrame({"paket_id": p["paket_id"].astype(str).to_numpy(),
                      "beden_sira": p["beden_sira"].to_numpy(dtype=np.int64),
                      "icerik": p["adet"].to_numpy(dtype=np.int64)})
    t = t.merge(p, on=["paket_id", "beden_sira"], how="left")
    ic = t["icerik"].fillna(0).to_numpy(dtype=np.int64)
    if (ic <= 0).any() or (t["adet"].to_numpy() % np.maximum(ic, 1) != 0).any():
        raise RuntimeError("ilk dağıtım sevki paket içeriğinin katı değil (paket ↔ sevkiyat tutmuyor)")
    t["paket"] = t["adet"].to_numpy() // ic
    anahtar = ["option_id", "magaza_id", "paket_id"]
    sevk = t.groupby(anahtar + ["tarih"])["paket"].agg(["min", "max"])
    if (sevk["min"] != sevk["max"]).any():
        raise RuntimeError("ilk dağıtım sevkinin bedenleri farklı paket sayısı veriyor: "
                           f"{int((sevk['min'] != sevk['max']).sum())} sevk")
    paket = sevk["min"].groupby(level=anahtar).sum().rename("paket")
    adet = t.groupby(anahtar)["adet"].sum()
    return pd.concat([paket, adet], axis=1).reset_index()[ILK_DAGITIM_SUTUNLARI].astype(
        {"paket": np.int64, "adet": np.int64})


def _sozluk(t: pd.DataFrame, sutun: str) -> dict[tuple[str, str], int]:
    g = t.groupby(["option_id", "magaza_id"])[sutun].sum()
    return {(str(o), str(m)): int(v) for (o, m), v in g.items() if v > 0}


def lumoda_giden(kosu_tablolari) -> dict[tuple[str, str], int]:
    """Bir koşunun (Lumoda'nın) ilk dağıtımında (option_id, magaza_id) başına giden paket sayısı
    (`ilk_dagitim_tablosu`; yalnız pozitif)."""
    return _sozluk(ilk_dagitim_tablosu(kosu_tablolari), "paket")


def giden_adet(kosu_tablolari) -> dict[tuple[str, str], int]:
    """İlk dağıtımda (option_id, magaza_id) başına giden adet (yalnız pozitif)."""
    return _sozluk(ilk_dagitim_tablosu(kosu_tablolari), "adet")


def ns_donustur(giden_adet: dict, paket_adet: int) -> dict[tuple[str, str], int]:
    """Adetten `paket_adet`'lik paket sayısına (12'li kollar, R10): option başına toplam ⌊Σ adet ÷
    paket_adet + ½⌋ paket, mağazalara adet payıyla en büyük kalanla (v4 `en_buyuk_kalan`; eşitlikte
    magaza_id sırası). Payı 0'a düşen mağaza 0 paket alır (sözlükte yok; `donusum_ozeti` sayar)."""
    a = int(paket_adet)
    if a <= 0:
        raise ValueError(f"paket adedi pozitif olmalı: {paket_adet}")
    option: dict[str, dict[str, int]] = {}
    for (o, m), v in giden_adet.items():
        if int(v) < 0:
            raise ValueError(f"adet negatif olamaz: {(o, m)} → {v}")
        option.setdefault(str(o), {})[str(m)] = int(v)
    ns = {}
    for o, d in sorted(option.items()):
        mag = sorted(d)
        adet = np.array([d[m] for m in mag], dtype=np.int64)
        toplam = int((2 * int(adet.sum()) + a) // (2 * a))         # ⌊Σ/a + ½⌋, tamsayıyla
        for m, n in zip(mag, en_buyuk_kalan(toplam, adet)):
            if n > 0:
                ns[(o, m)] = int(n)
    return ns


def donusum_ozeti(giden_adet: dict, ns: dict, paket_adet: int) -> dict[str, int]:
    """`ns_donustur`'un bedeli: Lumoda'nın ve kolun toplam adedi, fark (kol − Lumoda), adetli çift ve
    paketi 0'a düşen çift sayısı."""
    lum = {(str(o), str(m)): int(v) for (o, m), v in giden_adet.items() if int(v) > 0}
    kol = int(sum(int(v) for v in ns.values())) * int(paket_adet)
    return {"lumoda_adet": int(sum(lum.values())), "kol_adet": kol, "fark_adet": kol - int(sum(lum.values())),
            "hucre": len(lum), "sifir_hucre": int(sum(1 for k in lum if int(ns.get(k, 0)) == 0)),
            "option": len({o for o, _ in lum})}


def korunum(kosu, referans_adet: dict) -> dict[str, int]:
    """Aynı mal: koşunun ilk dağıtım adedi ile `referans_adet` ((option, mağaza) → adet; ör.
    Lumoda'nın `giden_adet`'i) arasında, referansın option'larında: çift sayısı, farklı çift,
    Σ|fark| ve Σ(kol − referans)."""
    ref = {(str(o), str(m)): int(v) for (o, m), v in referans_adet.items()}
    secili = {o for o, _ in ref}
    kol = {a: v for a, v in giden_adet(kosu).items() if a[0] in secili}
    anahtar = set(ref) | set(kol)
    fark = [kol.get(a, 0) - ref.get(a, 0) for a in anahtar]
    return {"hucre": len(anahtar), "fark_hucre": int(sum(f != 0 for f in fark)),
            "fark_adet": int(sum(abs(f) for f in fark)), "net_fark_adet": int(sum(fark))}


# ---------------------------------------------------------------------------
# Ölçüm
# ---------------------------------------------------------------------------


def _paket_boylari(kosu) -> tuple[np.ndarray, dict[str, int], np.ndarray]:
    """Koşunun `paket` tablosundan (paket_idleri, set → standart indis, [P] paket adedi)."""
    p = kosu.tablo("paket", sutunlar=["paket_id", "beden_seti", "beden_sira", "adet"])
    ids, standart = politika.paket_indisleri(p)
    boy = p.groupby("paket_id", sort=False)["adet"].sum().reindex(ids).to_numpy(dtype=np.int64)
    return ids, standart, boy


def paket_olcutleri(kosu, w) -> dict[str, float]:
    """Pakete duyarlı kayıt ölçütleri (modül notu), oyun option'larında."""
    oyun = oyun_optionlari(w)
    oyun_ids = set(_option_idleri(w, oyun))
    O, M = len(w.optionlar), len(w.magazalar)
    ids, standart, boy = _paket_boylari(kosu)
    seti = w.optionlar["beden_seti"].astype(str).to_numpy()
    secim = np.full((O, M), -1, dtype=np.int64)
    for o in oyun:
        secim[o, :] = standart[seti[o]]
    ps = kosu.kayitlar.get("paket_secimi")
    if ps is not None and len(ps):
        son = ps.sort_values("gun", kind="stable").drop_duplicates(["arg0", "indis"], keep="last")
        secim[son["arg0"].to_numpy(), son["indis"].to_numpy()] = son["deger"].to_numpy()
    adet = np.where(secim >= 0, boy[np.maximum(secim, 0)], 0)

    kayit = kosu.kayitlar["ilk_dagitim"]
    k = kayit[np.isin(kayit["arg0"].to_numpy(), oyun) & (kayit["indis"].to_numpy() >= 0)]
    istenen = np.maximum(k["deger"].to_numpy(dtype=np.int64), 0)
    istenen_adet = int((istenen * adet[k["arg0"].to_numpy(), k["indis"].to_numpy()]).sum())

    kirp = motor.kirpma_tablosu(kosu, w)
    kirp = kirp[kirp["option_id"].isin(oyun_ids)]
    o_idx = pd.Index(w.optionlar["option_id"].astype(str)).get_indexer(kirp["option_id"])
    m_idx = pd.Index(w.magazalar["magaza_id"].astype(str)).get_indexer(kirp["magaza_id"])
    kirpilan = int(((kirp["istenen_paket"] - kirp["giden_paket"]).to_numpy() * adet[o_idx, m_idx]).sum())
    t = ilk_dagitim_tablosu(kosu)
    tip = t.loc[t["option_id"].isin(oyun_ids), "paket_id"].nunique()
    return {"kirpilan_adet": float(kirpilan), "kirpilan_hucre": float(len(kirp)),
            "istenen_adet": float(istenen_adet), "paket_tipi": float(tip)}


def olc(kosu, w=None) -> dict[str, float]:
    """Koşunun ölçütleri: İlk Sevkiyat'ın `olcutler.hesapla`'sı (oyun sezonu), `kirpilan_adet` pakete
    duyarlı olanla değiştirilmiş, ve `paket_olcutleri` (modül notu). `w`: yayımlanan dünya (verilmezse
    koşunun ölçeğinde)."""
    w = motor.dunya(kosu.meta["olcek"]) if w is None else w
    sonuc = al_olcutler.hesapla(kosu, w, al_kaynak.harita_kur(w), OYUN_SEZONU)
    return sonuc | paket_olcutleri(kosu, w)


# ---------------------------------------------------------------------------
# İlk Sevkiyat önbelleği (salt okunur) ve yollar
# ---------------------------------------------------------------------------


def allocation_anahtari(yol: int = 0, olcek: str = "tam") -> str:
    """İlk Sevkiyat'ın yol `yol` Lumoda koşusunun (`lumoda` / `y<p>_lumoda`) önbellek anahtarı."""
    return motor.onbellek_anahtari(ad=al_oyun.lumoda_adi(yol), parametreler={},
                                   talep_tohumu=al_oyun.talep_tohumu(yol), operasyon_tohumu=motor.TOHUM,
                                   olcek=str(olcek).lower(), gun_sayisi=None, turler={}, politikalar={})


def allocation_lumoda(yol: int = 0, olcek: str = "tam") -> motor.KosuKaydi | None:
    """İlk Sevkiyat'ın önbellekli Lumoda koşusu, salt okunur ve tembel (`motor.KosuKaydi`); anahtarı
    tutan tam bir kayıt yoksa None. Hiçbir dosyayı yazmaz ya da silmez (`motor._oku_tembel`'in
    aksine)."""
    anahtar = allocation_anahtari(yol, olcek)
    dizin = motor._dizin(motor.KOSU_DIZINI, al_oyun.lumoda_adi(yol), anahtar)
    meta_yolu = dizin / "meta.json"
    if not meta_yolu.is_file():
        return None
    meta = json.loads(meta_yolu.read_text(encoding="utf-8"))
    if meta.get("anahtar") != anahtar:
        return None
    dosyalar = ([dizin / f"tablo_{a}.parquet" for a in meta["tablolar"]]
                + [dizin / f"kayit_{a}.parquet" for a in meta["kayitlar"]] + [dizin / "gercek.parquet"])
    if not all(d.is_file() for d in dosyalar):
        return None
    kayitlar = {a: pd.read_parquet(dizin / f"kayit_{a}.parquet") for a in meta["kayitlar"]}
    return motor.KosuKaydi(dizin=dizin, meta=meta, kayitlar=kayitlar, onbellekten=True)


def lumoda_ns(yol: int = 0, *, olcek: str = "tam", onbellek: Path | None = KOSU_DIZINI
              ) -> tuple[dict[tuple[str, str], int], str]:
    """(Yolun Lumoda `ns`'i, kaynak): İlk Sevkiyat'ın önbellekli `lumoda` / `y<p>_lumoda` koşusu salt
    okunur açılabiliyorsa ondan ("allocation:<dizin>"), yoksa vakanın o yoldaki doğrulama kolundan
    ("vaka:<ad>_<anahtar[:20]>"; önbellekte yoksa koşulur)."""
    k = allocation_lumoda(yol, olcek)
    if k is not None:
        return lumoda_giden(k), f"allocation:{k.dizin.name}"
    k = kos_dogrulama(yol, olcek, onbellek=onbellek)
    return lumoda_giden(k), f"vaka:{dogrulama_adi(yol)}_{k.meta['anahtar'][:20]}"


# ---------------------------------------------------------------------------
# Komut satırı: TAM doğrulama
# ---------------------------------------------------------------------------


def _referans(yol: int) -> dict | None:
    """İlk Sevkiyat'ın kayıtlı Lumoda ölçütleri (salt okunur): yol 0 `oyun.json`, yol p `yollar.json`."""
    cikti = motor.KOSU_DIZINI.parent
    try:
        if int(yol) == 0:
            return json.loads((cikti / "oyun.json").read_text(encoding="utf-8"))["kosular"]["lumoda"]["olcutler"]
        y = json.loads((cikti / "yollar.json").read_text(encoding="utf-8"))["yollar"][str(int(yol))]
        return y["kosular"]["lumoda"]["olcutler"]
    except (FileNotFoundError, KeyError):
        return None


def dogrula(yol: int = 0, olcek: str = "tam") -> int:
    """Doğrulama kolunu koşar (ya da önbellekten okur), ölçütlerini İlk Sevkiyat'ın Lumoda'sınınkiyle
    kıyaslar; birebir ise 0."""
    t0 = time.perf_counter()
    k = kos_dogrulama(yol, olcek)
    print(f"koşu {dogrulama_adi(yol)}: {'önbellekten' if k.onbellekten else 'koşuldu'}, "
          f"{time.perf_counter() - t0:.0f} sn, motor {k.meta.get('motor_sn')} sn, "
          f"tepe {k.meta.get('tepe_bellek_gb')} GB", flush=True)
    o = olc(k)
    print(f"ölçüm: {time.perf_counter() - t0:.0f} sn; bulunabilirlik {o['bulunabilirlik']:.4f}, "
          f"kirpilan_adet {o['kirpilan_adet']:.0f}", flush=True)
    al = allocation_lumoda(yol, olcek)
    sonuc = 0
    if al is not None:
        ayni = lumoda_giden(k) == lumoda_giden(al)
        print(f"giden paket (option, mağaza) İlk Sevkiyat {al.dizin.name} ile {'aynı' if ayni else 'FARKLI'}")
        sonuc |= not ayni
    ref = _referans(yol) if str(olcek).lower() == "tam" else None
    if ref is None:
        print("İlk Sevkiyat'ın kayıtlı ölçütü yok (yalnız TAM): kıyas yapılmadı")
        return 1
    fark = {a: (o.get(a), v) for a, v in ref.items() if o.get(a) != v}
    for a, (b, v) in sorted(fark.items()):
        print(f"  FARK {a}: vaka {b!r} ≠ İlk Sevkiyat {v!r}")
    print(f"ölçütler: {len(ref) - len(fark)}/{len(ref)} birebir")
    return int(bool(fark) or sonuc)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m beden_paket.kosucu")
    alt = ap.add_subparsers(dest="komut", required=True)
    d = alt.add_parser("dogrulama", help="doğrulama kolu ↔ İlk Sevkiyat Lumoda (birebir ölçüt)")
    d.add_argument("--yol", type=int, default=0)
    d.add_argument("--olcek", default="tam")
    a = ap.parse_args(argv)
    al_oyun.uyanik_tut()
    return dogrula(a.yol, a.olcek)


if __name__ == "__main__":
    sys.exit(main())
