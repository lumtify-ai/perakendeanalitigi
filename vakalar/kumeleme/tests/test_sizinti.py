"""Sızıntı kilidi (spec §0/5, Global Constraints): karar modülleri gizli gerçeği içe aktarmaz
ve okumaz.

Karar modülleri (`KARAR_MODULLERI`) ne `perakende_veri`'yi (v4 üreteci), ne
`perakende_analitik.hakem`'i, ne `kumeleme.hakem`'i içe aktarır: ne doğrudan ne paket içindeki
başka bir modül üstünden (tarama geçişlidir: `kume_payi` → `olcutler` → `hakem` de ihlaldir).
Gizli segment (`gizli_magaza.segment`) yalnız `hakem.py`'ye ve testlere aittir; ölçüm
modülleri (`IZINLI_MODULLER`: `hakem`, `olcutler`, `oyun`, `senaryolar`) onu kullanabilir.
Vaka kökündeki `rapor*.py` paket dışıdır.

Tarama AST'dir: modül başı ve fonksiyon içi `import` / `from … import` (göreli dahil; `from
kumeleme import hakem` ve `from perakende_analitik import hakem` biçimlerinde içe aktarılan ad
da modül adı sayılır) ile sabit dizgeli `importlib.import_module(...)` / `__import__(...)`.
Ayrıca karar modülleri `gizli_`/`sapma_`/`esneklik` adlı öznitelik ya da sabit dizgeli
`getattr`, ve içinde `gizli_magaza` geçen dizge sabiti taşımaz (yayımlanan veride o tablo yoktur;
SQL'de adı geçmesi de ihlaldir).

Henüz yazılmamış karar modülleri atlanır; sonradan eklenen her modül iki listeden birinde
olmalıdır (`test_her_modul_siniflandirilmis`).

Tarayıcının YAKALAMADIKLARI (statik tarama sınırı; kod incelemesine kalır): `vars(...)`,
`__dict__`, sabit olmayan dizgeyle `getattr`, `exec` / `eval`, dizgenin parçalanıp birleştirilmesi.
"""

import ast
from pathlib import Path

import pytest

import kumeleme

PAKET = Path(kumeleme.__file__).resolve().parent
PAKET_ADI = "kumeleme"

# Global Constraints'in listesi + tarafsız sabitler
KARAR_MODULLERI = (
    "sabitler", "kaynak", "ozellikler", "kural", "ogren", "yeni_magaza", "kume_payi", "hikaye_sec",
)
IZINLI_MODULLER = ("hakem", "olcutler", "oyun", "senaryolar")


def yasaklar(paket_adi: str) -> tuple[str, ...]:
    return ("perakende_veri", "perakende_analitik.hakem", f"{paket_adi}.hakem")


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
    """Karar modülü → [(zincir, yasak ad)]; zincir `kume_payi > olcutler` gibi, yasak adı içe
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


def test_paket_karar_modulleri_gizli_gerceği_gormez():
    assert (PAKET / "kaynak.py").is_file()                  # tarama boş dönmüyor
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
    paket = _yaz(tmp_path / "kumeleme", {
        "__init__": "",
        "kaynak": "import pandas as pd\nfrom perakende_analitik import kaynak as ortak\n",
        "sabitler": "from . import kaynak\nfrom .kaynak import ortak\n",
        "ozellikler": "from perakende_veri.v4 import dunya as d\n",
        "kural": "from . import hakem\n",
        "ogren": "from kumeleme.hakem import gizli_segment\n",
        "yeni_magaza": "from .olcutler import ari\n",             # geçişli: yeni_magaza > olcutler > hakem
        "kume_payi": "def f():\n    from perakende_analitik import hakem\n",
        "hikaye_sec": "x = __import__('perakende_veri')\n",
        "hakem": "import perakende_veri\n",                        # izinli
        "olcutler": "from .hakem import gizli_segment\nx = 1\n",   # izinli
        "oyun": "",
        "yeni": "",
    })
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"ozellikler", "kural", "ogren", "yeni_magaza", "kume_payi", "hikaye_sec"}
    assert ("yeni_magaza > olcutler", "kumeleme.hakem") in bulunan["yeni_magaza"]
    assert any(h == "perakende_analitik.hakem" for _, h in bulunan["kume_payi"])
    assert ("kural", "kumeleme.hakem") in bulunan["kural"]
    assert siniflandirilmamis(paket) == ["yeni"]


@pytest.mark.parametrize("metin", [
    "import perakende_veri.v4.motor\n",
    "from perakende_veri.v4.dunya import dunya_kur\n",
    "from kumeleme import hakem\n",
    "from kumeleme import kaynak, hakem\n",
    "from kumeleme import hakem as h\n",
    "from . import hakem\n",
    "from .hakem import gizli_segment\n",
    "import kumeleme.hakem as h\n",
    "from perakende_analitik import hakem\n",
    "from perakende_analitik import kaynak, hakem\n",
    "import perakende_analitik.hakem\n",
    "def f():\n    from kumeleme import hakem\n",
    "import importlib\nimportlib.import_module('perakende_veri')\n",
])
def test_tarayici_tek_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "kumeleme", {"__init__": "", "hakem": "", "kural": metin})
    assert "kural" in ihlaller(paket)


@pytest.mark.parametrize("metin", [
    "from kumeleme import kaynak\n",
    "from perakende_analitik import kaynak, stok\n",
    "from . import sabitler\n",
    "import numpy as np\n",
])
def test_tarayici_izinli_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "kumeleme", {"__init__": "", "hakem": "", "kaynak": "", "sabitler": "",
                                          "kural": metin})
    assert ihlaller(paket) == {}


# ---------------------------------------------------------------------------
# Gizli alanlar ve gizli tablo adı
# ---------------------------------------------------------------------------

GIZLI_ALANLAR = frozenset({"lam", "ilk_siparisler", "gercek"})
GIZLI_ONEKLER = ("gizli_", "sapma_", "esneklik")
GIZLI_TABLO = "gizli_magaza"


def _gizli(ad: str) -> bool:
    return ad in GIZLI_ALANLAR or ad.startswith(GIZLI_ONEKLER)


def gizli_erisimler(yol: Path) -> list[tuple[int, str]]:
    """Dosyadaki gizli erişimler: (satır, ad). `x.ad`, `getattr/hasattr/setattr(x, "ad")` ve
    içinde gizli tablonun adı geçen dizge sabiti."""
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
        elif isinstance(d, ast.Constant) and isinstance(d.value, str) and GIZLI_TABLO in d.value:
            bulunan.append((d.lineno, GIZLI_TABLO))
    return sorted(bulunan)


def test_karar_modulleri_gizli_alan_okumaz():
    var = [m for m in KARAR_MODULLERI if (PAKET / f"{m}.py").is_file()]
    assert "kaynak" in var                                  # tarama boş dönmüyor
    bulunan = {m: gizli_erisimler(PAKET / f"{m}.py") for m in var}
    bulunan = {m: b for m, b in bulunan.items() if b}
    assert not bulunan, f"karar modülü gizli gerçeği okuyor: {bulunan}"


def test_gizli_alan_tarayicisi(tmp_path):
    yol = tmp_path / "x.py"
    yol.write_text("\n".join([
        "def f(w, con):",
        "    a = w.lam",
        "    b = w.gizli_magaza['segment']",
        "    c = getattr(w, 'sapma_rpt')",
        "    d = con.execute('select segment from gizli_magaza').df()",
        "    e = w.esneklik_hucre",
        "    ok = w.magazalar, x['lam'], getattr(w, 'depo'), 'segment'",
        "    return a",
    ]) + "\n", encoding="utf-8")
    assert gizli_erisimler(yol) == [(2, "lam"), (3, "gizli_magaza"), (4, "sapma_rpt"),
                                    (5, "gizli_magaza"), (6, "esneklik_hucre")]
