"""Sızıntı kilidi (spec §0/5, §0/13, Global Constraints): karar modülleri gizli gerçeği içe
aktarmaz ve okumaz; `egri` yayımlanan `sevkiyat` tablosunu istemez.

Karar modülleri (`KARAR_MODULLERI`) ne `perakende_veri`'yi (v4 üreteci), ne
`perakende_analitik.hakem`'i içe aktarır, ne de ölçüm modüllerinden (`IZINLI_MODULLER`) herhangi
birine ulaşır: ne doğrudan ne paket içindeki başka bir modül üstünden (tarama geçişlidir:
`politika` → `kosucu` → `perakende_veri` ihlaldir). Başka vakaların ölçüm modülleri de kapalıdır
(`DIS_YASAK`: Kümeleme'nin `hakem`, `olcutler`, `oyun`, `senaryolar`, `hikaye_kos`'u; İlk
Sevkiyat'ın `motor`, `olcutler`, `oyun`, `yollar`, `senaryolar`'ı); Kümeleme ve İlk Sevkiyat'ın
`kaynak`, `sabitler`, `paylastir`, `politika` gibi karar modülleri açıktır. Gizli `beden_kayma`
yalnız `hakem.py`'ye ve testlere aittir. Paketin `__init__.py`'si her içe aktarmada çalışır; bu
yüzden her karar modülünün erişim kümesine girer. Vaka kökündeki `rapor*.py` paket dışıdır.

Tarama AST'dir: modül başı ve fonksiyon içi `import` / `from … import` (göreli dahil; `from
beden_paket import hakem` ve `from perakende_analitik import hakem` biçimlerinde içe aktarılan
ad da modül adı sayılır) ile sabit dizgeli `importlib.import_module(...)` / `__import__(...)`.
Ayrıca karar modüllerinin ve onlardan erişilen her modülün (`__init__` dahil) `gizli_`/`sapma_`/
`esneklik`/`gercek_`/`beden_kayma` adlı öznitelik ya da sabit dizgeli `getattr`, ve içinde `gizli_`
önekli bir tablo adı ya da `beden_kayma` geçen dizge sabiti yoktur (docstring'ler hariç: belge
gizli adı anabilir).

**`egri` ve `sevkiyat`.** `egri`'den (ve erişilen modüllerden) sabit dizge, öznitelik ya da ad
olarak `sevkiyat` istenmez: replenishment sevkiyatının beden karışımı Lumoda'nın (gizli gerçeği
bilen) planını taşır, eğriye girdi olamaz. `egri.py` henüz yoksa bu kontrol atlanır ve modül
gelince kendiliğinden devreye girer. Çalışma zamanı denetimi (tablo sözlüğünden `sevkiyat`'ı
çıkarınca sonucun değişmemesi) `test_egri.py`'dedir.

Henüz yazılmamış karar modülleri atlanır; sonradan eklenen her modül iki listeden birinde
olmalıdır (`test_her_modul_siniflandirilmis`).

Tarayıcının YAKALAMADIKLARI (statik tarama sınırı; kod incelemesine kalır): `vars(...)`,
`__dict__`, sabit olmayan dizgeyle `getattr`, `exec` / `eval`, dizgenin parçalanıp birleştirilmesi,
tablo sözlüğünü anahtar anahtar gezmek.
"""

import ast
import re
from pathlib import Path

import pytest

import beden_paket

PAKET = Path(beden_paket.__file__).resolve().parent
PAKET_ADI = "beden_paket"

KARAR_MODULLERI = ("sabitler", "kaynak", "egri", "paket_tasarim", "politika", "hikaye_sec")
IZINLI_MODULLER = ("hakem", "olcutler_egri", "olcutler", "kosucu", "oyun", "hikaye_kos", "senaryolar")
DIS_YASAK = (
    "kumeleme.hakem", "kumeleme.olcutler", "kumeleme.oyun", "kumeleme.senaryolar",
    "kumeleme.hikaye_kos",
    "allocation.motor", "allocation.olcutler", "allocation.oyun", "allocation.yollar",
    "allocation.senaryolar",
)


def yasaklar(paket_adi: str, izinli: tuple[str, ...] = IZINLI_MODULLER,
             dis: tuple[str, ...] = DIS_YASAK) -> tuple[str, ...]:
    """Karar modülünün ulaşamayacağı adlar: gizli gerçeğin kapıları, bu paketin ölçüm modülleri
    ve öteki vakaların ölçüm modülleri."""
    return (("perakende_veri", "perakende_analitik.hakem")
            + tuple(f"{paket_adi}.{m}" for m in izinli) + tuple(dis))


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
    """Karar modülü → [(zincir, yasak ad)]; zincir `politika > kosucu` gibi, yasak adı içe
    aktaran paket içi yolu gösterir. Yasak ad: gizli gerçeğin kapıları, bu paketin her ölçüm
    modülü ve öteki vakaların ölçüm modülleri (içe aktarılması da, erişim zincirinde bulunması
    da). Henüz olmayan karar modülü atlanır."""
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
    paket = _yaz(tmp_path / "beden_paket", {
        "__init__": "",
        "kaynak": "import pandas as pd\nfrom perakende_analitik import kaynak as ortak\n"
                  "from kumeleme import kaynak as k\nfrom allocation import paylastir\n",   # izinli
        "sabitler": "from . import kaynak\nfrom .kaynak import ortak\n",
        "egri": "from perakende_veri.v4 import dunya as d\n",
        "paket_tasarim": "from . import hakem\n",
        "politika": "from beden_paket.hakem import gercek_pay\n",
        "hikaye_sec": "from .kosucu import kos\n",                    # geçişli: kosucu > perakende_veri
        "kosucu": "import perakende_veri\nfrom .hakem import gercek_pay\n",   # izinli
        "hakem": "import perakende_veri\n",                            # izinli
        "oyun": "",
        "yeni": "",
    })
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"egri", "paket_tasarim", "politika", "hikaye_sec"}
    assert ("hikaye_sec", "beden_paket.kosucu") in bulunan["hikaye_sec"]
    assert ("hikaye_sec > kosucu", "perakende_veri") in bulunan["hikaye_sec"]    # geçişli
    assert ("hikaye_sec > kosucu", "beden_paket.hakem") in bulunan["hikaye_sec"]
    assert ("paket_tasarim", "beden_paket.hakem") in bulunan["paket_tasarim"]
    assert siniflandirilmamis(paket) == ["yeni"]


@pytest.mark.parametrize("metin", [
    "import perakende_veri.v4.motor\n",
    "from perakende_veri.v4.dunya import dunya_kur\n",
    "from beden_paket import hakem\n",
    "from beden_paket import kaynak, hakem\n",
    "from beden_paket import hakem as h\n",
    "from . import hakem\n",
    "from .hakem import gercek_pay\n",
    "import beden_paket.hakem as h\n",
    "from beden_paket.olcutler_egri import uzaklik\n",
    "from beden_paket import oyun\n",
    "from perakende_analitik import hakem\n",
    "from perakende_analitik import kaynak, hakem\n",
    "import perakende_analitik.hakem\n",
    "def f():\n    from beden_paket import hakem\n",
    "import importlib\nimportlib.import_module('perakende_veri')\n",
    "from kumeleme import hakem\n",
    "from kumeleme.oyun import kos\n",
    "from kumeleme import olcutler\n",
    "from allocation import motor\n",
    "from allocation.oyun import kos\n",
    "from allocation.yollar import yollar\n",
])
def test_tarayici_tek_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "beden_paket", {"__init__": "", "hakem": "", "egri": metin})
    assert "egri" in ihlaller(paket)


@pytest.mark.parametrize("metin", [
    "from beden_paket import kaynak\n",
    "from perakende_analitik import kaynak, stok\n",
    "from . import sabitler\n",
    "import numpy as np\n",
    "from kumeleme import kaynak\n",
    "from kumeleme.kaynak import kapsam\n",
    "from allocation import paylastir, politika\n",
    "from allocation.kaynak import yukle\n",
])
def test_tarayici_izinli_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "beden_paket", {"__init__": "", "hakem": "", "kaynak": "", "sabitler": "",
                                            "egri": metin})
    assert ihlaller(paket) == {}


@pytest.mark.parametrize("izinli", IZINLI_MODULLER)
def test_tarayici_olcum_modulune_erisim_ihlal(tmp_path, izinli):
    """Karar modülü, yasak adı içe aktarmayan ama bir ölçüm modülüne uzanan zincirle de yakalanır."""
    paket = _yaz(tmp_path / "beden_paket", {
        "__init__": "", "egri": "from . import ara\n", "ara": f"from .{izinli} import x\n",
        **{m: "" for m in IZINLI_MODULLER}})
    bulunan = ihlaller(paket)
    assert ("egri > ara", f"beden_paket.{izinli}") in bulunan["egri"]


def test_tarayici_init_erisim_kumesinde(tmp_path):
    """`__init__` her içe aktarmada çalışır: içindeki ihlal bütün karar modüllerine yazılır."""
    paket = _yaz(tmp_path / "beden_paket", {
        "__init__": "from .hakem import gercek_pay\n", "hakem": "", "kaynak": "", "egri": ""})
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"kaynak", "egri"}
    assert ("kaynak > __init__", "beden_paket.hakem") in bulunan["kaynak"]
    paket = _yaz(tmp_path / "temiz" / "beden_paket", {"__init__": '"""belge"""\n', "kaynak": ""})
    assert ihlaller(paket) == {}


def test_tarayici_olmayan_karar_modulu_atlanir(tmp_path):
    """Yalnız `kaynak` varken öteki karar modülleri (egri, paket_tasarim, …) atlanır."""
    paket = _yaz(tmp_path / "beden_paket", {"__init__": "", "kaynak": "import numpy\n"})
    assert ihlaller(paket) == {}
    assert gizli_erisim_bul(paket) == {}
    assert sevkiyat_istekleri(paket) == {}


# ---------------------------------------------------------------------------
# Gizli alanlar ve gizli tablo adı
# ---------------------------------------------------------------------------

GIZLI_ALANLAR = frozenset({"lam", "ilk_siparisler", "gercek", "beden_kayma"})
GIZLI_ONEKLER = ("gizli_", "sapma_", "esneklik", "gercek_", "beden_kayma")
GIZLI_DIZGE = re.compile(r"gizli_[a-z]|beden_kayma")


def _gizli(ad: str) -> bool:
    return ad in GIZLI_ALANLAR or ad.startswith(GIZLI_ONEKLER)


def belge_dugumleri(agac: ast.AST) -> set[int]:
    """Modül, sınıf ve fonksiyon docstring'lerinin Constant düğümlerinin kimlikleri."""
    belge = set()
    for d in ast.walk(agac):
        if isinstance(d, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and d.body and isinstance(d.body[0], ast.Expr) \
                and isinstance(d.body[0].value, ast.Constant) and isinstance(d.body[0].value.value, str):
            belge.add(id(d.body[0].value))
    return belge


def gizli_erisimler(yol: Path) -> list[tuple[int, str]]:
    """Dosyadaki gizli erişimler: (satır, ad). `x.ad`, `getattr/hasattr/setattr(x, "ad")` ve
    içinde gizli tablo adı ya da `beden_kayma` geçen dizge sabiti (docstring hariç)."""
    agac = ast.parse(Path(yol).read_text(encoding="utf-8"), filename=str(yol))
    belge = belge_dugumleri(agac)
    bulunan = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Attribute) and _gizli(d.attr):
            bulunan.append((d.lineno, d.attr))
        elif (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
              and d.func.id in ("getattr", "hasattr", "setattr") and len(d.args) >= 2
              and isinstance(d.args[1], ast.Constant) and isinstance(d.args[1].value, str)
              and _gizli(d.args[1].value)):
            bulunan.append((d.lineno, d.args[1].value))
        elif isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in belge \
                and (m := GIZLI_DIZGE.search(d.value)):
            bulunan.append((d.lineno, m.group(0)))
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
    paket = _yaz(tmp_path / "beden_paket", {
        "__init__": "x = con.execute('select * from gizli_magaza')\n",
        "egri": "from . import ara\n", "ara": "y = w.beden_kayma\n", "diger": "z = w.beden_kayma\n"})
    assert gizli_erisim_bul(paket) == {"__init__": [(1, "gizli_m")], "ara": [(1, "beden_kayma")]}


def test_gizli_alan_tarayicisi(tmp_path):
    yol = tmp_path / "x.py"
    yol.write_text("\n".join([
        '"""Belge: gizli_magaza ve beden_kayma yalnız hakemde (docstring serbest)."""',
        "def f(w, con):",
        '    "belge: gizli_x"',
        "    a = w.lam",
        "    b = w.gizli_magaza['segment']",
        "    c = getattr(w, 'sapma_rpt')",
        "    d = con.execute('select beden_kayma from gizli_magaza').df()",
        "    e = w.esneklik_hucre",
        "    g = w.beden_kayma + w.gercek_pay",
        "    ok = w.magazalar, x['lam'], getattr(w, 'depo'), 'segment', GIZLI_TABLO_ONEKI, 'gizli_'",
        "    return a",
    ]) + "\n", encoding="utf-8")
    assert gizli_erisimler(yol) == [(4, "lam"), (5, "gizli_magaza"), (6, "sapma_rpt"),
                                    (7, "beden_kayma"), (8, "esneklik_hucre"), (9, "beden_kayma"),
                                    (9, "gercek_pay")]


# ---------------------------------------------------------------------------
# `egri` ve `sevkiyat` (spec §0/13)
# ---------------------------------------------------------------------------

SEVKIYAT = re.compile(r"(?<![A-Za-z0-9_])sevkiyat(?![A-Za-z0-9_])")


def sevkiyat_istekleri_dosya(yol: Path) -> list[tuple[int, str]]:
    """Dosyada `sevkiyat` tablosunu isteyen yerler: (satır, tür). Sabit dizge (docstring hariç;
    `tablolar["sevkiyat"]`, `yayimlanan_tablolar(con, ("sevkiyat",))`, SQL `from sevkiyat`),
    öznitelik (`x.sevkiyat`) ve ad (`sevkiyat = ...`)."""
    agac = ast.parse(Path(yol).read_text(encoding="utf-8"), filename=str(yol))
    belge = belge_dugumleri(agac)
    bulunan = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in belge \
                and SEVKIYAT.search(d.value):
            bulunan.append((d.lineno, "dizge"))
        elif isinstance(d, ast.Attribute) and d.attr == "sevkiyat":
            bulunan.append((d.lineno, "öznitelik"))
        elif isinstance(d, ast.Name) and d.id == "sevkiyat":
            bulunan.append((d.lineno, "ad"))
        elif isinstance(d, ast.arg) and d.arg == "sevkiyat":
            bulunan.append((d.lineno, "ad"))
        elif isinstance(d, ast.keyword) and d.arg == "sevkiyat":
            bulunan.append((d.value.lineno, "ad"))
    return sorted(bulunan)


def sevkiyat_istekleri(paket: Path) -> dict:
    """`egri` ve ondan erişilen modüllerdeki `sevkiyat` istekleri; `egri.py` yoksa boş (modül
    gelince kendiliğinden devreye girer)."""
    if not (paket / "egri.py").is_file():
        return {}
    return {m: b for m in sorted(erisim(paket, "egri")[0])
            if (b := sevkiyat_istekleri_dosya(paket / f"{m}.py"))}


def test_egri_sevkiyat_istemez():
    """Gerçek pakette `egri` bir dosya olarak vardır ve gerçekten taranır (yoksa ya da paket
    dizini olarak gelirse kırmızı: sessizce geçmez)."""
    assert (PAKET / "egri.py").is_file(), "egri.py yok: sevkiyat taraması boş geçerdi"
    assert not (PAKET / "egri").exists(), "egri bir paket dizini: tarayıcı yalnız egri.py'yi okur"
    assert "egri" in erisim(PAKET, "egri")[0]
    bulunan = sevkiyat_istekleri(PAKET)
    assert not bulunan, f"egri (ya da erişilen modül) sevkiyat tablosunu istiyor: {bulunan}"


def test_sevkiyat_tarayicisi(tmp_path):
    yol = tmp_path / "x.py"
    yol.write_text("\n".join([
        '"""Belge: sevkiyat tablosu okunmaz (docstring serbest)."""',
        "def f(tablolar, con, sevkiyat_plani):",
        '    "belge: sevkiyat"',
        "    a = tablolar['sevkiyat']",
        "    b = con.execute('select * from sevkiyat where adet > 0').df()",
        "    c = yayimlanan_tablolar(con, ('magaza', 'sevkiyat'))",
        "    d = tablolar.sevkiyat",
        "    sevkiyat = 1",
        "    ok = tablolar['satis'], 'ilk_sevkiyat', 'sevkiyatlar', sevkiyat_plani",
        "    return g(sevkiyat=a)",
    ]) + "\n", encoding="utf-8")
    assert sevkiyat_istekleri_dosya(yol) == [(4, "dizge"), (5, "dizge"), (6, "dizge"),
                                             (7, "öznitelik"), (8, "ad"), (10, "ad")]


def test_sevkiyat_taramasi_erisilen_modulleri_kapsar(tmp_path):
    paket = _yaz(tmp_path / "beden_paket", {
        "__init__": "", "egri": "from . import ara\n", "ara": "x = t['sevkiyat']\n",
        "kaynak": "x = 1\n", "diger": "y = t['sevkiyat']\n"})
    assert sevkiyat_istekleri(paket) == {"ara": [(1, "dizge")]}
    # egri'den erişilmeyen modül (ölçüm tarafı) serbest
    paket = _yaz(tmp_path / "temiz" / "beden_paket", {
        "__init__": "", "egri": "x = 1\n", "oyun": "y = t['sevkiyat']\n"})
    assert sevkiyat_istekleri(paket) == {}
