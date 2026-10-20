"""Sızıntı kilidi (spec §0/5, Global Constraints): karar modülleri gizli gerçeği içe aktarmaz
ve okumaz.

Karar modülleri (`KARAR_MODULLERI`) ne `perakende_veri`'yi (v4 üreteci), ne
`perakende_analitik.hakem`'i içe aktarır, ne de ölçüm modüllerinden (`IZINLI_MODULLER`:
`hakem`, `olcutler`, `oyun`, `senaryolar`, `hikaye_kos`) herhangi birine ulaşır: ne doğrudan ne paket içindeki
başka bir modül üstünden (tarama geçişlidir: `kume_payi` → `olcutler` ihlaldir). Gizli segment
(`gizli_magaza.segment`) yalnız `hakem.py`'ye ve testlere aittir. Paketin `__init__.py`'si her
içe aktarmada çalışır; bu yüzden her karar modülünün erişim kümesine girer. Vaka kökündeki
`rapor*.py` paket dışıdır.

Tarama AST'dir: modül başı ve fonksiyon içi `import` / `from … import` (göreli dahil; `from
kumeleme import hakem` ve `from perakende_analitik import hakem` biçimlerinde içe aktarılan ad
da modül adı sayılır) ile sabit dizgeli `importlib.import_module(...)` / `__import__(...)`.
Ayrıca karar modüllerinin ve onlardan erişilen her modülün (`__init__` dahil) `gizli_`/
`sapma_`/`esneklik` adlı öznitelik ya da sabit dizgeli `getattr`, ve içinde `gizli_magaza` geçen
dizge sabiti yoktur (yayımlanan veride o tablo yoktur;
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
IZINLI_MODULLER = ("hakem", "olcutler", "oyun", "senaryolar", "hikaye_kos")


def yasaklar(paket_adi: str, izinli: tuple[str, ...] = IZINLI_MODULLER) -> tuple[str, ...]:
    """Karar modülünün ulaşamayacağı adlar: gizli gerçeğin kapıları ve bütün ölçüm modülleri."""
    return ("perakende_veri", "perakende_analitik.hakem") + tuple(f"{paket_adi}.{m}" for m in izinli)


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


def erisim(paket: Path, kok: str, paket_adi: str = PAKET_ADI):
    """`kok` modülünden paket içi içe aktarmalarla ulaşılan modüller: {modül: zincir}.

    `__init__` her içe aktarmada çalıştığı için her zaman erişim kümesindedir."""
    moduller = {y.stem: y for y in paket.glob("*.py")}
    aktarim = {ad: ice_aktarimlar(y, paket_adi) for ad, y in moduller.items()}
    gorulen = {kok: kok}
    sira = [kok]
    if "__init__" in moduller and kok != "__init__":
        gorulen["__init__"] = f"{kok} > __init__"
        sira.append("__init__")
    while sira:
        ad = sira.pop(0)
        for hedef in sorted(aktarim[ad]):
            if _altinda(hedef, paket_adi) and hedef != paket_adi:
                alt = hedef.split(".")[1]
                if alt in moduller and alt not in gorulen:
                    gorulen[alt] = f"{gorulen[ad]} > {alt}"
                    sira.append(alt)
    return gorulen, aktarim


def ihlaller(paket: Path, paket_adi: str = PAKET_ADI,
             karar: tuple[str, ...] = KARAR_MODULLERI) -> dict[str, list[tuple[str, str]]]:
    """Karar modülü → [(zincir, yasak ad)]; zincir `kume_payi > olcutler` gibi, yasak adı içe
    aktaran paket içi yolu gösterir. Yasak ad: gizli gerçeğin kapıları ve her ölçüm modülü
    (içe aktarılması da, erişim zincirinde bulunması da). Henüz olmayan karar modülü atlanır."""
    moduller = {y.stem for y in paket.glob("*.py")}
    yasak = yasaklar(paket_adi)
    sonuc: dict[str, list[tuple[str, str]]] = {}
    for kok in karar:
        if kok not in moduller:
            continue
        gorulen, aktarim = erisim(paket, kok, paket_adi)
        bulunan = []
        for ad, zincir in gorulen.items():
            for hedef in sorted(aktarim[ad]):
                bulunan += [(zincir, hedef) for y in yasak if _altinda(hedef, y)]
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
    assert ("yeni_magaza", "kumeleme.olcutler") in bulunan["yeni_magaza"]
    assert ("yeni_magaza > olcutler", "kumeleme.hakem") in bulunan["yeni_magaza"]    # geçişli
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


@pytest.mark.parametrize("izinli", ["olcutler", "oyun", "senaryolar", "hakem"])
def test_tarayici_olcum_modulune_erisim_ihlal(tmp_path, izinli):
    """Karar modülü, yasak adı içe aktarmayan ama bir ölçüm modülüne uzanan zincirle de yakalanır."""
    paket = _yaz(tmp_path / "kumeleme", {
        "__init__": "", "kural": "from . import ara\n", "ara": f"from .{izinli} import x\n",
        "hakem": "", "olcutler": "", "oyun": "", "senaryolar": ""})
    bulunan = ihlaller(paket)
    assert ("kural > ara", f"kumeleme.{izinli}") in bulunan["kural"]


def test_tarayici_init_erisim_kumesinde(tmp_path):
    """`__init__` her içe aktarmada çalışır: içindeki ihlal bütün karar modüllerine yazılır."""
    paket = _yaz(tmp_path / "kumeleme", {
        "__init__": "from .hakem import gizli_segment\n", "hakem": "", "kaynak": "", "kural": ""})
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"kaynak", "kural"}
    assert ("kaynak > __init__", "kumeleme.hakem") in bulunan["kaynak"]
    paket = _yaz(tmp_path / "temiz" / "kumeleme", {"__init__": '"""belge"""\n', "kaynak": ""})
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


def taranacaklar(paket: Path, karar: tuple[str, ...] = KARAR_MODULLERI) -> set[str]:
    """Karar modülleri ve onlardan erişilen her modül (`__init__` dahil)."""
    moduller = {y.stem for y in paket.glob("*.py")}
    kume: set[str] = set()
    for kok in karar:
        if kok in moduller:
            kume |= set(erisim(paket, kok)[0])
    return kume


def gizli_erisim_bul(paket: Path, karar: tuple[str, ...] = KARAR_MODULLERI) -> dict:
    return {m: b for m in sorted(taranacaklar(paket, karar))
            if (b := gizli_erisimler(paket / f"{m}.py"))}


def test_karar_modulleri_gizli_alan_okumaz():
    var = taranacaklar(PAKET)
    assert {"kaynak", "__init__"} <= var                    # tarama boş dönmüyor
    bulunan = gizli_erisim_bul(PAKET)
    assert not bulunan, f"karar modülü (ya da erişilen modül) gizli gerçeği okuyor: {bulunan}"


def test_gizli_tarama_erisilen_modulleri_kapsar(tmp_path):
    paket = _yaz(tmp_path / "kumeleme", {
        "__init__": "x = con.execute('select * from gizli_magaza')\n",
        "kural": "from . import ara\n", "ara": "y = w.lam\n", "diger": "z = w.lam\n"})
    assert gizli_erisim_bul(paket) == {"__init__": [(1, "gizli_magaza")], "ara": [(1, "lam")]}


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
