"""Kalibrasyon (spec §4.4): bir önceki yılın aynı penceresinde (AW24, `KAL_BAS`…
`KAL_BIT`) parametre seçimi; oyun penceresine hiç bakmadan.

    tavan = referans_tavan(con)                        # koşusuz, yayımlanan veriden
    k = kalibre_et(kos_fn, tavan)                      # ≤ 18 koşu
    yaz(k, CIKTI / "kalibrasyon.json"); k = oku(...)
    ayar = k.referans_ayar()                           # oyun penceresinde referans nokta

**Koşu enjekte edilir.** Bu modül bir karar modülüdür: motoru içe aktarmaz
(`tests/test_sizinti.py`; Ruling R5). Koşuyu `kos_fn(ad, ayar) -> dict` yapar; `ayar`
kolun `Ayar`'ıdır (pencere hep `KAL_BAS…KAL_BIT`; dışında kol Lumoda'dır), dönen
sözlükte en az `bulunabilirlik` (yüzde), `toplama_maliyeti_tl`, `magaza_stok_son`
bulunur. Gerçek koşucu `oyun.kalibrasyon_kosucusu` (`kural` kolu, yol 0, alım 1,0;
`python -m replenishment.oyun kalibrasyon`).

**Yöntem** (v2 kalıbı, Ruling R23):

1. Hedef: istatistik ailesi (Z = 1,65) **kısıtsız** (tavan ∞, koli zorunluluğu yok)
   koşar; bulunabilirliği hedeftir. Aileler hedef kurmayı ölçer, depo kısıtı ayrı
   (v2'nin "koli yok + kapasite sınırsız"ı v4'te koli açılmaz kuralıyla yalnız açık
   stoğu göndermek olurdu).
2. Sabit (`SABIT_IZGARA`, adet) ve ros (`ROS_IZGARA`, gün) ızgaraları aynı koşulla;
   her aileden hedefe en yakın değer (`en_yakin`; eşitlikte küçük değer).
3. Seçilen aile: üç ailenin seçilmiş değerleri arasında pencere sonu mağaza stoğu en
   düşük olan (aynı bulunabilirliğe en az stokla).
4. Koli: seçilen ailenin güvenlik stokuyla, referans tavanda, kısıtlı; A ızgarası
   α × β, B ızgarası γ; her birinden "en iyi bulunabilirliğin 1 puan yakınında en
   ucuz" (`maliyet_secimi`). C = A ∧ B, seçilen parametrelerle (koşulmaz; oyunun koli
   taraması ölçer). Seçilen koli kuralı: seçilmiş A ile B arasından aynı ölçüt.

Bütçe 1 + 4 + 5 + 6 + 2 = 18 koşu (Ruling R25: ros 6 ve β 4 eklendi; "hedefe en yakın"
seçimi ızgara kabalığına yenilmesin, β 3 ızgara ucuydu). Seçimler yalnız pencere içi ölçütlerden.

**Referans tavan** (spec §3.5): `TAVAN_ORANI` × Lumoda'nın penceredeki haftalık
ortalama replenishment adedi (yayımlanan `sevkiyat`, hedefi fiziksel mağaza), aşağı
yuvarlanır. Ortalamanın paydası penceredeki pazartesi sayısıdır (sevksiz hafta 0).

**Sonuç** `cikti/kalibrasyon.json`'a yazılır (`yaz`/`oku`); `Ayar` varsayılanları
değişmez (Ruling R20), oyun ve sonraki görevler değerleri bu dosyadan açıkça verir.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import kaynak
from .dagitim import KoliKurali
from .ihtiyac import GuvenlikStoku
from .politika import Ayar
from .sabitler import CIKTI, KAL_BAS, KAL_BIT, OYUN_BAS, OYUN_BIT, TAVAN_ORANI

PENCERE = (KAL_BAS, KAL_BIT)
SABIT_IZGARA = (1, 2, 3, 4)           # adet
ROS_IZGARA = (3, 5, 6, 7, 10)         # gün × hız (Ruling R25: 6 eklendi)
ALFA_IZGARA = (0.4, 0.6)
BETA_IZGARA = (2, 3, 4)               # Ruling R25: 4 eklendi (3 ızgara ucuydu)
GAMA_IZGARA = (0.5, 0.75)
ESIK_PUAN = 1.0                       # maliyet seçiminde en iyiye bulunabilirlik yakınlığı
AILELER = ("sabit", "ros", "istatistik")
GEREKEN_OLCUTLER = ("bulunabilirlik", "toplama_maliyeti_tl", "magaza_stok_son")
DOSYA = CIKTI / "kalibrasyon.json"


# ---------------------------------------------------------------------------
# Saf seçim
# ---------------------------------------------------------------------------


def en_yakin(degerler: dict, hedef: float):
    """`degerler` (anahtar → ölçüm) içinden `hedef`'e en yakın anahtar; eşitlikte küçük
    anahtar (artan sırada tarama + katı `<`)."""
    en_iyi_anahtar, en_iyi_fark = None, None
    for anahtar in sorted(degerler):
        fark = abs(degerler[anahtar] - hedef)
        if en_iyi_fark is None or fark < en_iyi_fark:
            en_iyi_anahtar, en_iyi_fark = anahtar, fark
    return en_iyi_anahtar


def maliyet_secimi(satirlar: list[dict], esik: float = ESIK_PUAN) -> dict:
    """Bulunabilirliği en iyisinin `esik` puan altına düşmeyen satırlar arasından
    `toplama_maliyeti_tl`'si en küçük olan (eşitlikte ilk satır)."""
    alt = max(s["bulunabilirlik"] for s in satirlar) - esik
    return min((s for s in satirlar if s["bulunabilirlik"] >= alt), key=lambda s: s["toplama_maliyeti_tl"])


# ---------------------------------------------------------------------------
# Referans tavan
# ---------------------------------------------------------------------------


def _pazartesi_sayisi(bas: date, bit: date) -> int:
    ilk = bas + timedelta(days=(7 - bas.weekday()) % 7)
    return 0 if ilk > bit else (bit - ilk).days // 7 + 1


def referans_tavan(con, bas: date = KAL_BAS, bit: date = KAL_BIT, oran: float = TAVAN_ORANI) -> int:
    """⌊`oran` × haftalık ortalama replenishment adedi⌋ (`[bas, bit]`, fiziksel mağaza,
    yayımlanan `sevkiyat`; payda penceredeki pazartesi sayısı)."""
    bas, bit = pd.Timestamp(bas).date(), pd.Timestamp(bit).date()
    n = _pazartesi_sayisi(bas, bit)
    if n == 0:
        raise ValueError(f"pencerede pazartesi yok: {bas} … {bit}")
    toplam = float(kaynak.haftalik_replenishment(con, bas, bit)["adet"].sum())
    return math.floor(oran * toplam / n)


# ---------------------------------------------------------------------------
# Kalibrasyon
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Kalibrasyon:
    """Kalibrasyonun seçimleri (modül notu). `tablo`: her koşu bir satır (`asama`,
    `ad`, `aile`, `deger`, `koli`, `alfa`, `beta`, `gamma` + `kos_fn`'in ölçütleri)."""

    gs: dict[str, GuvenlikStoku]
    koli: dict[str, KoliKurali]
    secilen_aile: str
    secilen_koli: str
    tavan: int
    hedef_bulunabilirlik: float
    tablo: pd.DataFrame = field(repr=False)

    def referans_ayar(self, *, pencere: tuple[date, date] = (OYUN_BAS, OYUN_BIT), **ek) -> Ayar:
        """Referans noktanın kol ayarı (seçilen koli, referans tavan, seçilen aile);
        `ek` alanları üzerine yazar (ör. `tavan`, `oncelik`, `koli`)."""
        alanlar = {"koli": self.koli[self.secilen_koli], "tavan": self.tavan,
                   "gs": self.gs[self.secilen_aile], "pencere": pencere, **ek}
        return Ayar(**alanlar)


def kalibre_et(kos_fn, tavan: int) -> Kalibrasyon:
    """Modül notundaki yöntem; `kos_fn(ad, ayar) -> dict` her koşu için bir kez."""
    satirlar: list[dict] = []

    def olc(asama: str, ad: str, ayar: Ayar, **etiket) -> dict:
        olcut = dict(kos_fn(ad, ayar))
        eksik = [o for o in GEREKEN_OLCUTLER if o not in olcut]
        if eksik:
            raise KeyError(f"kos_fn ölçütü eksik ({ad}): {eksik}")
        k = ayar.kural()
        satir = {"asama": asama, "ad": ad, "aile": ayar.gs.aile, "deger": float(ayar.gs.deger),
                 "koli": k.ad, "alfa": k.alfa, "beta": k.beta, "gamma": k.gamma, **etiket, **olcut}
        satirlar.append(satir)
        return satir

    def kisitsiz(gs: GuvenlikStoku) -> Ayar:
        return Ayar(kisitsiz=True, gs=gs, pencere=PENCERE)

    # 1. hedef: istatistik ailesi, kısıtsız
    istatistik = GuvenlikStoku("istatistik")
    hedef_satir = olc("hedef", "kal_gs_istatistik", kisitsiz(istatistik))
    hedef = float(hedef_satir["bulunabilirlik"])

    # 2. sabit ve ros ızgaraları, hedefe en yakın
    secilen = {"istatistik": (istatistik, hedef_satir)}
    for aile, izgara in (("sabit", SABIT_IZGARA), ("ros", ROS_IZGARA)):
        izgara_satirlari = {d: olc(aile, f"kal_gs_{aile}_{d}", kisitsiz(GuvenlikStoku(aile, d))) for d in izgara}
        d = en_yakin({d: s["bulunabilirlik"] for d, s in izgara_satirlari.items()}, hedef)
        secilen[aile] = (GuvenlikStoku(aile, d), izgara_satirlari[d])

    # 3. aile: en düşük pencere sonu mağaza stoğu (eşitlikte AILELER sırası)
    secilen_aile = min(AILELER, key=lambda a: secilen[a][1]["magaza_stok_son"])
    gs = secilen[secilen_aile][0]

    # 4. koli ızgaraları: seçilen aile, referans tavan, kısıtlı
    def kisitli(kural: KoliKurali) -> Ayar:
        return Ayar(koli=kural, tavan=float(tavan), gs=gs, pencere=PENCERE)

    a_satirlari = [olc("koli_A", f"kal_koli_A_{a}_{b}_{secilen_aile}", kisitli(KoliKurali("A", alfa=a, beta=b)))
                   for a in ALFA_IZGARA for b in BETA_IZGARA]
    a_sec = maliyet_secimi(a_satirlari)
    b_satirlari = [olc("koli_B", f"kal_koli_B_{g}_{secilen_aile}", kisitli(KoliKurali("B", gamma=g)))
                   for g in GAMA_IZGARA]
    b_sec = maliyet_secimi(b_satirlari)
    koli = {"A": KoliKurali("A", alfa=a_sec["alfa"], beta=int(a_sec["beta"])),
            "B": KoliKurali("B", gamma=b_sec["gamma"])}
    koli["C"] = KoliKurali("C", alfa=koli["A"].alfa, beta=koli["A"].beta, gamma=koli["B"].gamma)
    secilen_koli = maliyet_secimi([a_sec, b_sec])["koli"]

    return Kalibrasyon(
        gs={a: secilen[a][0] for a in AILELER},
        koli=koli,
        secilen_aile=secilen_aile,
        secilen_koli=secilen_koli,
        tavan=int(tavan),
        hedef_bulunabilirlik=hedef,
        tablo=pd.DataFrame(satirlar),
    )


# ---------------------------------------------------------------------------
# Dosya
# ---------------------------------------------------------------------------


def _json_degeri(x):
    if isinstance(x, float) and math.isnan(x):
        return None
    if hasattr(x, "item"):                       # numpy skaleri
        return _json_degeri(x.item())
    return x


def sozluk(k: Kalibrasyon) -> dict:
    """JSON'a dönen biçim."""
    return {
        "pencere": [PENCERE[0].isoformat(), PENCERE[1].isoformat()],
        "tavan": k.tavan,
        "hedef_bulunabilirlik": k.hedef_bulunabilirlik,
        "gs": {a: {"aile": g.aile, "deger": float(g.deger)} for a, g in k.gs.items()},
        "koli": {a: {"ad": c.ad, "alfa": c.alfa, "beta": c.beta, "gamma": c.gamma} for a, c in k.koli.items()},
        "secilen_aile": k.secilen_aile,
        "secilen_koli": k.secilen_koli,
        "tablo": [{s: _json_degeri(v) for s, v in r.items()} for r in k.tablo.to_dict("records")],
    }


def sozlukten(d: dict) -> Kalibrasyon:
    return Kalibrasyon(
        gs={a: GuvenlikStoku(g["aile"], g["deger"]) for a, g in d["gs"].items()},
        koli={a: KoliKurali(c["ad"], alfa=c["alfa"], beta=c["beta"], gamma=c["gamma"]) for a, c in d["koli"].items()},
        secilen_aile=d["secilen_aile"],
        secilen_koli=d["secilen_koli"],
        tavan=int(d["tavan"]),
        hedef_bulunabilirlik=float(d["hedef_bulunabilirlik"]),
        tablo=pd.DataFrame(d["tablo"]),
    )


def yaz(k: Kalibrasyon, yol: Path = DOSYA, **ek) -> Path:
    """`k`'yi (ve `ek` alanlarını, ör. süre) JSON olarak yazar."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps({**sozluk(k), **ek}, ensure_ascii=False, indent=1), encoding="utf-8")
    return yol


def oku(yol: Path = DOSYA) -> Kalibrasyon:
    return sozlukten(json.loads(Path(yol).read_text(encoding="utf-8")))
