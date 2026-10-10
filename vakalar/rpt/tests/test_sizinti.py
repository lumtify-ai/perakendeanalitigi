"""Sızıntı kilidi (spec §3.3): karar modülleri gizli gerçeğin kapılarını
içe aktarmaz.

Karar modülleri (`KARAR_MODULLERI`) ne `rpt.motor`'u, ne `perakende_veri`'yi
(v4 üreteci), ne `perakende_analitik.hakem`'i içe aktarır: ne doğrudan ne
paket içindeki başka bir modül üstünden (tarama geçişlidir: `aday` →
`oyun` → `motor` de ihlaldir). Gizli gerçek yalnız `IZINLI_MODULLER`'e
(`motor`, `kahin`, `olcutler`, `oyun`, `yollar`) ve vaka kökündeki
`rapor*.py`'ye gider; kâhin kolu bu yüzden `politika.py`'de değil ayrı
`kahin.py`'dedir (tarama dosya düzeyinde).

Tarama AST'dir: modül başı ve fonksiyon içi `import` / `from … import`
(göreli dahil) ile sabit dizgeli `importlib.import_module(...)` /
`__import__(...)`. Pakete eklenen her modül iki listeden birinde olmalıdır
(`test_her_modul_siniflandirilmis`).

Kâhin de yasaktır (`rpt.kahin` gerçek talebi argüman alır): karar modülü onu
ne doğrudan ne geçişli içe aktarır.

Geçici muafiyet (`GECICI_V3`): v3 üretecini (`perakende_veri.v3`) hâlâ
içe aktaran eski modüller, ilgili görev onları v4'e taşıyana dek yalnız
v3 için muaftır; motor, hakem ve v4 onlarda da yasaktır. Modül v3'ten
kurtulunca muafiyet satırı silinmelidir (test bunu ister). Görev 7'den beri
boştur.

GİZLİ ALANLAR (Görev 4'ten ertelenen, Görev 7). İçe aktarma kilidi motorun
dünyasını kapatmaz: karar modülleri `Gorunum.dunya` üstünden dünyanın nesnesini
görür. Sözleşme (`perakende_veri.v4.motor.durum.Gorunum`) yalnız kamuya açık
alanları serbest bırakır; `GORUNUM_MODULLERI` dünyanın gizli alanlarının hiçbirine
(`GIZLI_ALANLAR`, `GIZLI_ONEKLER`) öznitelik ya da sabit dizgeli `getattr` ile
erişmez (AST; adı her nesnede yasaktır, yalnız dünyada değil).

Tarayıcının YAKALAMADIKLARI (statik tarama sınırı; kod incelemesine kalır):
`vars(w)` / `w.__dict__[...]` / `inspect.getmembers`, `operator.attrgetter("lam")`,
sabit olmayan dizgeyle `getattr(w, ad)` (birleştirilmiş ya da değişkendeki ad),
takma adla dolaşma (`f = getattr; f(w, "lam")`), `exec` / `eval`, ve gizli değeri
taşıyan nesnenin kamuya açık bir adla argüman olarak verilmesi.
"""

import ast
from pathlib import Path

import pytest

import rpt

PAKET = Path(rpt.__file__).resolve().parent

KARAR_MODULLERI = (
    "kaynak", "egri", "sansur", "aday", "miktar", "dagitim", "politika",
    "hikaye", "hikaye_sec", "anlik", "bilgi", "hazirla",
)
IZINLI_MODULLER = ("motor", "kahin", "olcutler", "oyun", "yollar")
GECICI_V3: dict[str, str] = {}
# Muafiyet yalnız küçülür; son görev GECICI_V3'ün boş olduğunu sınamalı.
GECICI_V3_ILK = frozenset({"aday", "miktar", "dagitim", "politika"})


def yasaklar(paket_adi: str) -> tuple[str, ...]:
    return ("perakende_veri", "perakende_analitik.hakem", f"{paket_adi}.motor", f"{paket_adi}.kahin")


def _altinda(ad: str, kok: str) -> bool:
    return ad == kok or ad.startswith(kok + ".")


def ice_aktarimlar(yol: Path, paket_adi: str) -> set[str]:
    """Dosyanın içe aktardığı tam modül adları (göreli adlar `paket_adi`
    altına çözülür; `from m import a` hem `m`'yi hem `m.a`'yı verir)."""
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    adlar: set[str] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            adlar |= {a.name for a in dugum.names}
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.level:
                taban = ".".join([paket_adi] + ([dugum.module] if dugum.module else []))
            else:
                taban = dugum.module or ""
            adlar.add(taban)
            adlar |= {f"{taban}.{a.name}" for a in dugum.names}
        elif isinstance(dugum, ast.Call):
            f = dugum.func
            dinamik = (isinstance(f, ast.Attribute) and f.attr == "import_module") or (
                isinstance(f, ast.Name) and f.id in ("__import__", "import_module"))
            if dinamik and dugum.args and isinstance(dugum.args[0], ast.Constant) \
                    and isinstance(dugum.args[0].value, str):
                adlar.add(dugum.args[0].value)
    return adlar


def ihlaller(paket: Path, paket_adi: str = "rpt",
             karar: tuple[str, ...] = KARAR_MODULLERI) -> dict[str, list[tuple[str, str]]]:
    """Karar modülü → [(zincir, yasak ad)]; zincir `aday > oyun` gibi,
    yasak adı içe aktaran paket içi yolu gösterir."""
    moduller = {y.stem: y for y in paket.glob("*.py")}
    aktarim = {ad: ice_aktarimlar(y, paket_adi) for ad, y in moduller.items()}
    yasak = yasaklar(paket_adi)
    sonuc: dict[str, list[tuple[str, str]]] = {}
    for kok in karar:
        if kok not in moduller:
            continue
        bulunan, gorulen, sira = [], {kok}, [(kok, kok)]
        while sira:
            ad, zincir = sira.pop(0)
            for hedef in sorted(aktarim[ad]):
                bulunan += [(zincir, hedef) for y in yasak if _altinda(hedef, y)]
                if _altinda(hedef, paket_adi) and hedef != paket_adi:
                    alt = hedef.split(".")[1]
                    if alt in moduller and alt not in gorulen:
                        gorulen.add(alt)
                        sira.append((alt, f"{zincir} > {alt}"))
        if bulunan:
            sonuc[kok] = sorted(set(bulunan))
    return sonuc


def siniflandirilmamis(paket: Path) -> list[str]:
    return sorted(y.stem for y in paket.glob("*.py")
                  if y.stem not in KARAR_MODULLERI + IZINLI_MODULLER + ("__init__",))


# ---------------------------------------------------------------------------


def test_paket_karar_modulleri_motoru_gormez():
    bulunan = ihlaller(PAKET)
    kalici = {}
    for modul, liste in bulunan.items():
        geri = [(z, h) for z, h in liste
                if not (modul in GECICI_V3 and _altinda(h, "perakende_veri.v3"))]
        if geri:
            kalici[modul] = geri
    assert not kalici, f"karar modülü gizli gerçeğin kapısını içe aktarıyor: {kalici}"
    eskimis = [m for m in GECICI_V3 if m not in bulunan]
    assert not eskimis, f"v3'ten kurtulmuş; GECICI_V3'ten silin: {eskimis}"


def test_gecici_v3_yalniz_kuculur():
    assert set(GECICI_V3) <= GECICI_V3_ILK


def test_gecici_v3_bos():
    """Görev 7'den beri hiçbir karar modülü v3 üretecini içe aktarmaz."""
    assert GECICI_V3 == {}


def test_her_modul_siniflandirilmis():
    assert siniflandirilmamis(PAKET) == []
    assert not set(KARAR_MODULLERI) & set(IZINLI_MODULLER)


def _yaz(dizin: Path, dosyalar: dict[str, str]) -> Path:
    dizin.mkdir(parents=True)
    for ad, metin in dosyalar.items():
        (dizin / f"{ad}.py").write_text(metin, encoding="utf-8")
    return dizin


def test_tarayici_ihlali_yakalar(tmp_path):
    paket = _yaz(tmp_path / "rpt", {
        "__init__": "",
        "kaynak": "import pandas as pd\nfrom perakende_analitik import kaynak as ortak\n",
        "hikaye": "from . import kaynak\nfrom .kaynak import ortak\n",
        "egri": "from perakende_veri.v4 import motor as m\n",
        "sansur": "from . import motor\n",
        "politika": "from rpt.motor import kos\n",
        "aday": "from .oyun import x\n",                       # geçişli: aday > oyun > motor
        "miktar": "def f():\n    from perakende_analitik import hakem\n",
        "dagitim": "import importlib\nm = importlib.import_module('perakende_veri.v4')\n",
        "anlik": "x = __import__('perakende_veri')\n",
        "motor": "import perakende_veri\n",                    # izinli
        "oyun": "from .motor import kos\nx = 1\n",             # izinli
        "yeni": "",
    })
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"egri", "sansur", "politika", "aday", "miktar", "dagitim", "anlik"}
    assert ("aday > oyun", "rpt.motor") in bulunan["aday"]
    assert any(h == "perakende_analitik.hakem" for _, h in bulunan["miktar"])
    assert siniflandirilmamis(paket) == ["yeni"]


@pytest.mark.parametrize("metin", [
    "import perakende_veri.v4.motor\n",
    "from perakende_veri.v4.dunya import dunya_kur\n",
    "from rpt import motor\n",
    "from rpt import kaynak, motor\n",
    "from .motor import Kosu\n",
    "import rpt.motor as m\n",
])
def test_tarayici_tek_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "rpt", {"__init__": "", "motor": "", "egri": metin})
    assert "egri" in ihlaller(paket)


# ---------------------------------------------------------------------------
# Gizli alanlar (Gorunum.dunya)
# ---------------------------------------------------------------------------

# `Gorunum` sözleşmesinin "asla" listesi + motorun kayıtlı talebi (`talep`,
# `kayit_talep`) + `Kosu.gercek` / `dunya.gercek()`.
GIZLI_ALANLAR = frozenset({"lam", "esneklik", "esneklik_hucre", "ilk_siparisler", "gercek",
                           "talep", "kayit_talep"})
GIZLI_ONEKLER = ("gizli_", "sapma_")
GORUNUM_MODULLERI = ("politika", "dagitim", "anlik", "aday", "miktar", "sansur", "egri", "bilgi")


def _gizli(ad: str) -> bool:
    return ad in GIZLI_ALANLAR or ad.startswith(GIZLI_ONEKLER)


def gizli_erisimler(yol: Path) -> list[tuple[int, str]]:
    """Dosyadaki gizli alan erişimleri: (satır, ad). `x.ad` ve
    `getattr(x, "ad"[, …])` / `hasattr` / `setattr` sabit dizgeyle."""
    agac = ast.parse(Path(yol).read_text(encoding="utf-8"), filename=str(yol))
    bulunan = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Attribute) and _gizli(d.attr):
            bulunan.append((d.lineno, d.attr))
        elif (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
              and d.func.id in ("getattr", "hasattr", "setattr") and len(d.args) >= 2
              and isinstance(d.args[1], ast.Constant) and isinstance(d.args[1].value, str)
              and _gizli(d.args[1].value)):
            bulunan.append((d.lineno, d.args[1].value))
    return sorted(bulunan)


def test_karar_modulleri_gizli_alan_okumaz():
    eksik = [m for m in GORUNUM_MODULLERI if not (PAKET / f"{m}.py").is_file()]
    assert not eksik, eksik
    bulunan = {m: gizli_erisimler(PAKET / f"{m}.py") for m in GORUNUM_MODULLERI}
    bulunan = {m: b for m, b in bulunan.items() if b}
    assert not bulunan, f"karar modülü dünyanın gizli alanını okuyor: {bulunan}"



def test_gizli_alan_tarayicisi(tmp_path):
    yol = tmp_path / "x.py"
    yol.write_text("\n".join([
        "def f(g):",
        "    a = g.dunya.lam.gun(g.gun)",
        "    b = g.dunya.gizli_tedarikci['hatali_orani']",
        "    c = getattr(g.dunya, 'sapma_rpt')",
        "    d = g.dunya.esneklik_hucre",
        "    e = g.dunya.gercek()",
        "    f = b_.talep",
        "    ok = g.dunya.optionlar, x['talep'], g.satis_gecmisi, getattr(g, 'depo')",
        "    return a",
    ]) + "\n", encoding="utf-8")
    assert gizli_erisimler(yol) == [(2, "lam"), (3, "gizli_tedarikci"), (4, "sapma_rpt"),
                                    (5, "esneklik_hucre"), (6, "gercek"), (7, "talep")]


def test_kahin_karar_modulunden_ice_aktarilamaz(tmp_path):
    paket = _yaz(tmp_path / "rpt", {"__init__": "", "kahin": "", "aday": "",
                                    "politika": "from . import aday\nfrom .kahin import Kahin\n",
                                    "dagitim": "from . import politika\n"})
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"politika", "dagitim"}
    assert ("dagitim > politika", "rpt.kahin.Kahin") in bulunan["dagitim"]
