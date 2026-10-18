"""Sızıntı kilidi (spec §3.4, Global Constraints): karar modülleri gizli gerçeğin
kapılarını içe aktarmaz ve dünyanın gizli alanlarını okumaz.

Karar modülleri (`KARAR_MODULLERI`) ne `allocation.motor`'u, ne `perakende_veri`'yi (v4
üreteci), ne `perakende_analitik.hakem`'i içe aktarır: ne doğrudan ne paket içindeki başka
bir modül üstünden (tarama geçişlidir: `paylastir` → `oyun` → `motor` de ihlaldir). Gizli
gerçek yalnız `IZINLI_MODULLER`'e (`motor`, `olcutler`, `oyun`, `yollar`, `senaryolar`) ve
vaka kökündeki `rapor*.py`'ye gider. Kalibrasyon karar listesindedir: koşuyu çağıranın
verdiği koşu işleviyle yapar, motoru içe aktarmaz. Kahinin muafiyeti yoktur (Ruling R4):
girdisi `parametreler` üstünden ölçülmüş dizidir.

Tarama AST'dir: modül başı ve fonksiyon içi `import` / `from … import` (göreli dahil; `from
allocation import motor` ve `from perakende_analitik import hakem` biçimlerinde içe
aktarılan ad da modül adı sayılır) ile sabit dizgeli `importlib.import_module(...)` /
`__import__(...)`. Pakete eklenen her modül iki listeden birinde olmalıdır
(`test_her_modul_siniflandirilmis`).

GİZLİ ALANLAR. İçe aktarma kilidi motorun dünyasını kapatmaz: karar modülleri
`Gorunum.dunya` üstünden dünyanın nesnesini görür. Sözleşme
(`perakende_veri.v4.motor.durum.Gorunum`) yalnız kamuya açık alanları serbest bırakır;
karar modülleri dünyanın gizli alanlarının hiçbirine (`GIZLI_ALANLAR`, `GIZLI_ONEKLER`)
öznitelik ya da sabit dizgeli `getattr` ile erişmez (AST; adı her nesnede yasaktır, yalnız
dünyada değil).

Tarayıcının YAKALAMADIKLARI (statik tarama sınırı; kod incelemesine kalır): `vars(w)` /
`w.__dict__[...]` / `inspect.getmembers`, `operator.attrgetter("lam")`, sabit olmayan
dizgeyle `getattr(w, ad)`, takma adla dolaşma (`f = getattr; f(w, "lam")`), `exec` /
`eval`, ve gizli değeri taşıyan nesnenin kamuya açık bir adla argüman olarak verilmesi.
"""

import ast
from pathlib import Path

import pytest

import allocation

PAKET = Path(allocation.__file__).resolve().parent
PAKET_ADI = "allocation"

# Global Constraints'in listesi + tarafsız sabitler (o da motoru görmez)
KARAR_MODULLERI = (
    "kaynak", "ogrenme", "benzer", "tahmin", "paylastir", "politika", "kalibrasyon",
    "hikaye_sec", "sabitler",
)
IZINLI_MODULLER = ("motor", "olcutler", "oyun", "yollar", "senaryolar")


def yasaklar(paket_adi: str) -> tuple[str, ...]:
    return ("perakende_veri", "perakende_analitik.hakem", f"{paket_adi}.motor")


def _altinda(ad: str, kok: str) -> bool:
    return ad == kok or ad.startswith(kok + ".")


def ice_aktarimlar(yol: Path, paket_adi: str) -> set[str]:
    """Dosyanın içe aktardığı tam modül adları (göreli adlar `paket_adi` altına çözülür;
    `from m import a` hem `m`'yi hem `m.a`'yı verir)."""
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


def ihlaller(paket: Path, paket_adi: str = PAKET_ADI,
             karar: tuple[str, ...] = KARAR_MODULLERI) -> dict[str, list[tuple[str, str]]]:
    """Karar modülü → [(zincir, yasak ad)]; zincir `paylastir > oyun` gibi, yasak adı içe
    aktaran paket içi yolu gösterir. Henüz olmayan karar modülü atlanır."""
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
    assert (PAKET / "kaynak.py").is_file() and (PAKET / "motor.py").is_file()   # tarama boş dönmüyor
    bulunan = ihlaller(PAKET)
    assert not bulunan, f"karar modülü gizli gerçeğin kapısını içe aktarıyor: {bulunan}"


def test_her_modul_siniflandirilmis():
    assert siniflandirilmamis(PAKET) == []
    assert not set(KARAR_MODULLERI) & set(IZINLI_MODULLER)


def _yaz(dizin: Path, dosyalar: dict[str, str]) -> Path:
    dizin.mkdir(parents=True)
    for ad, metin in dosyalar.items():
        (dizin / f"{ad}.py").write_text(metin, encoding="utf-8")
    return dizin


def test_tarayici_ihlali_yakalar(tmp_path):
    paket = _yaz(tmp_path / "allocation", {
        "__init__": "",
        "kaynak": "import pandas as pd\nfrom perakende_analitik import kaynak as ortak\n",
        "sabitler": "from . import kaynak\nfrom .kaynak import ortak\n",
        "tahmin": "from perakende_veri.v4 import motor as m\n",
        "ogrenme": "from . import motor\n",
        "politika": "from allocation.motor import kos\n",
        "paylastir": "from .oyun import x\n",                  # geçişli: paylastir > oyun > motor
        "benzer": "def f():\n    from perakende_analitik import hakem\n",
        "kalibrasyon": "import importlib\nm = importlib.import_module('perakende_veri.v4')\n",
        "hikaye_sec": "x = __import__('perakende_veri')\n",
        "motor": "import perakende_veri\n",                    # izinli
        "oyun": "from .motor import kos\nx = 1\n",             # izinli
        "yeni": "",
    })
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"tahmin", "ogrenme", "politika", "paylastir", "benzer", "kalibrasyon",
                            "hikaye_sec"}
    assert ("paylastir > oyun", "allocation.motor") in bulunan["paylastir"]
    assert any(h == "perakende_analitik.hakem" for _, h in bulunan["benzer"])
    assert ("ogrenme", "allocation.motor") in bulunan["ogrenme"]
    assert siniflandirilmamis(paket) == ["yeni"]


@pytest.mark.parametrize("metin", [
    "import perakende_veri.v4.motor\n",
    "from perakende_veri.v4.dunya import dunya_kur\n",
    "from allocation import motor\n",
    "from allocation import kaynak, motor\n",
    "from allocation import motor as m\n",
    "from . import motor\n",
    "from .motor import Kosu\n",
    "import allocation.motor as m\n",
    "from perakende_analitik import hakem\n",
    "from perakende_analitik import kaynak, hakem\n",
    "import perakende_analitik.hakem\n",
    "def f():\n    from allocation import motor\n",
])
def test_tarayici_tek_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "allocation", {"__init__": "", "motor": "", "politika": metin})
    assert "politika" in ihlaller(paket)


@pytest.mark.parametrize("metin", [
    "from allocation import kaynak\n",
    "from perakende_analitik import kaynak, stok\n",
    "from . import sabitler\n",
    "import numpy as np\n",
])
def test_tarayici_izinli_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "allocation", {"__init__": "", "motor": "", "kaynak": "", "sabitler": "",
                                            "politika": metin})
    assert ihlaller(paket) == {}


# ---------------------------------------------------------------------------
# Gizli alanlar (Gorunum.dunya)
# ---------------------------------------------------------------------------

# `Gorunum` sözleşmesinin "asla" listesi + `dunya.gercek()` / `Kosu.gercek`
GIZLI_ALANLAR = frozenset({"lam", "ilk_siparisler", "gercek"})
GIZLI_ONEKLER = ("gizli_", "sapma_", "esneklik")


def _gizli(ad: str) -> bool:
    return ad in GIZLI_ALANLAR or ad.startswith(GIZLI_ONEKLER)


def gizli_erisimler(yol: Path) -> list[tuple[int, str]]:
    """Dosyadaki gizli alan erişimleri: (satır, ad). `x.ad` ve `getattr(x, "ad"[, …])` /
    `hasattr` / `setattr` sabit dizgeyle."""
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
    var = [m for m in KARAR_MODULLERI if (PAKET / f"{m}.py").is_file()]
    assert "kaynak" in var                                  # tarama boş dönmüyor
    bulunan = {m: gizli_erisimler(PAKET / f"{m}.py") for m in var}
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
        "    f = g.dunya.ilk_siparisler",
        "    ok = g.dunya.optionlar, x['lam'], g.satis_gecmisi, getattr(g, 'depo'), g.dunya.ilk_alim",
        "    return a",
    ]) + "\n", encoding="utf-8")
    assert gizli_erisimler(yol) == [(2, "lam"), (3, "gizli_tedarikci"), (4, "sapma_rpt"),
                                    (5, "esneklik_hucre"), (6, "gercek"), (7, "ilk_siparisler")]
