"""Sızıntı kilidi (spec §0/11-12, §9; Global Constraints): karar modülleri gizli gerçeği ve ölçüm
tarafını içe aktarmaz, gizli alanları okumaz.

Karar modülleri (`KARAR_MODULLERI`): `sabitler`, `kaynak`, `ogrenme`, `tahmin`, `model`, `politika`.
Henüz yazılmamış olanlar atlanır; dosya paketlere eklendiği anda kendiliğinden kilitlenir (listeye
sonradan eklenen modül de ayrıca taranır).

**Yasak içe aktarım** (`YASAK_ICE_AKTARIM`): `perakende_veri` (v4 üreteci ve motoru: gizli gerçek),
ölçüm tarafının her modülü (`OLCUM_MODULLERI`: simulasyon, hakem, olcutler, oyun, hikaye; ayrıca
henüz planlanan `kosucu`, `rapor`, `senaryolar`, `analiz` adları), `allocation.motor` (İlk Sevkiyat
motoru: `gercek_tablosu`), ayrıca `perakende_analitik.hakem`. Paketteki her modül karar ya da ölçüm
listesinde sınıflandırılmış olmalıdır (`test_her_modul_siniflandirilmis`). Tarama geçişlidir:
`politika` -> `kosucu` -> `perakende_veri` ihlaldir; paket `__init__.py`'si her içe aktarmada
çalıştığı için her karar modülünün erişim kümesine girer. Ölçüm modüllerinden de dünyanın gizli
alanlarına yalnız `hakem` ve `simulasyon` dokunur (`GIZLIYE_DOKUNAN`; spec §4.1); öteki ölçüm
modülleri koşunun `gercek` tablosunu okuyabilir.

**Yasak öznitelik adı** (`x.ad`, sabit dizgeli `getattr/hasattr/setattr(x, "ad")`): `lam`,
`esneklik`, `esneklik_hucre`, `gercek`, `ilk_siparisler` (tam ad) ve `gizli_*`, `sapma_*` (önek).
`esneklik_markdown` / `esneklik_kampanya` yasak değildir: ortak kestiricinin açık çıktılarıdır
(spec §0/10). İçinde `gizli_` önekli tablo adı geçen dizge sabiti de yasaktır (docstring hariç).

Tarayıcının YAKALAMADIKLARI (statik tarama sınırı; kod incelemesine kalır): `vars(...)`,
`__dict__`, sabit olmayan dizgeyle `getattr`, `exec` / `eval`, dizgenin parçalanıp birleştirilmesi,
tablo sözlüğünü anahtar anahtar gezmek.
"""

import ast
import re
from pathlib import Path

import pytest

import markdown

PAKET = Path(markdown.__file__).resolve().parent
PAKET_ADI = "markdown"

KARAR_MODULLERI = ("sabitler", "kaynak", "ogrenme", "tahmin", "model", "politika")
# Ruling R24: karar tarafının ayrıştırma kolları; karar modülleriyle aynı kilit (yasak içe aktarım ve gizli
# alan), ama `simulasyon.SIMULASYON_MODULLERI`'nde değil (kod özeti kolun `parametreler()`'inde).
ABLASYON_MODULLERI = ("politika_ablasyon",)
KILITLI = KARAR_MODULLERI + ABLASYON_MODULLERI
# Ölçüm tarafı: planlanan modüller (her biri bir karar modülünün erişimine girmemeli). Pakette
# bulunan her `.py` KARAR_MODULLERI ya da OLCUM_MODULLERI'nde olmalıdır (`__init__` karar tarafı
# sayılır ve kilitlidir); yeni bir modül önce bir listeye konur.
OLCUM_MODULLERI = ("simulasyon", "hakem", "olcutler", "oyun", "hikaye")
# Planlanan öteki ölçüm adları: ileride vaka kökünde betik de olabilir; paket içinde dosya olarak
# belirirse sınıflandırma testi onu OLCUM_MODULLERI'ne taşımayı zorlar. Adlar şimdiden yasaktır.
OLCUM_EK_ADLAR = ("kosucu", "rapor", "senaryolar", "analiz")
YASAK_ICE_AKTARIM = (("perakende_veri", "perakende_analitik.hakem", "allocation.motor")
                     + tuple(f"markdown.{m}" for m in OLCUM_MODULLERI + OLCUM_EK_ADLAR))
YASAK_AD = frozenset({"lam", "esneklik", "esneklik_hucre", "gercek", "ilk_siparisler"})
YASAK_ONEK = ("gizli_", "sapma_")
GIZLI_DIZGE = re.compile(r"gizli_[a-z]")


def _altinda(ad: str, kok: str) -> bool:
    return ad == kok or ad.startswith(kok + ".")


def ice_aktarimlar(yol: Path, paket_adi: str) -> set[str]:
    """Dosyanın içe aktardığı tam modül adları (göreli adlar `paket_adi` altına çözülür;
    `from m import a` hem `m`'yi hem `m.a`'yı verir; sabit dizgeli `import_module` / `__import__`)."""
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


def ihlaller(paket: Path, paket_adi: str = PAKET_ADI, karar: tuple[str, ...] = KARAR_MODULLERI,
             yasak: tuple[str, ...] = YASAK_ICE_AKTARIM) -> dict[str, list[tuple[str, str]]]:
    """Karar modülü -> [(zincir, yasak ad)]; zincir `politika > kosucu` gibi, yasak adı içe
    aktaran paket içi yolu gösterir. Henüz olmayan karar modülü atlanır."""
    moduller = {y.stem for y in paket.glob("*.py")}
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


def _yasak_ad(ad: str) -> bool:
    return ad in YASAK_AD or ad.startswith(YASAK_ONEK)


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
    """Dosyadaki yasak erişimler: (satır, ad). `x.ad`, `getattr/hasattr/setattr(x, "ad")` ve
    içinde gizli tablo adı geçen dizge sabiti (docstring hariç)."""
    agac = ast.parse(Path(yol).read_text(encoding="utf-8"), filename=str(yol))
    belge = belge_dugumleri(agac)
    bulunan = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Attribute) and _yasak_ad(d.attr):
            bulunan.append((d.lineno, d.attr))
        elif (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
              and d.func.id in ("getattr", "hasattr", "setattr") and len(d.args) >= 2
              and isinstance(d.args[1], ast.Constant) and isinstance(d.args[1].value, str)
              and _yasak_ad(d.args[1].value)):
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


# ---------------------------------------------------------------------------
# Gerçek paket
# ---------------------------------------------------------------------------


def test_paket_karar_modulleri_gizli_gerceği_gormez():
    assert (PAKET / "kaynak.py").is_file() and (PAKET / "sabitler.py").is_file()   # tarama boş değil
    bulunan = ihlaller(PAKET, karar=KILITLI)
    assert not bulunan, f"karar modülü yasak modülü içe aktarıyor: {bulunan}"


def test_karar_modulleri_gizli_alan_okumaz():
    var = taranacaklar(PAKET)
    assert {"sabitler", "kaynak", "__init__"} <= var
    bulunan = gizli_erisim_bul(PAKET, KILITLI)
    assert not bulunan, f"karar modülü (ya da erişilen modül) gizli gerçeği okuyor: {bulunan}"


def siniflandirilmamis(paket: Path) -> list[str]:
    return sorted(y.stem for y in paket.glob("*.py")
                  if y.stem not in KARAR_MODULLERI + ABLASYON_MODULLERI + OLCUM_MODULLERI + ("__init__",))


def test_her_modul_siniflandirilmis():
    """Pakette sınıflandırılmamış modül yoksa kilit eksiksizdir; yeni dosya önce bir listeye girer."""
    assert siniflandirilmamis(PAKET) == []
    kumeler = (set(KARAR_MODULLERI), set(ABLASYON_MODULLERI), set(OLCUM_MODULLERI))
    assert all(not a & b for i, a in enumerate(kumeler) for b in kumeler[i + 1:])
    assert not set(OLCUM_EK_ADLAR) & set(KARAR_MODULLERI + ABLASYON_MODULLERI + OLCUM_MODULLERI)


def test_olcum_modulleri_yasakta():
    for m in OLCUM_MODULLERI + OLCUM_EK_ADLAR:
        assert f"markdown.{m}" in YASAK_ICE_AKTARIM, m
    assert "markdown.hikaye" in YASAK_ICE_AKTARIM and "markdown.oyun" in YASAK_ICE_AKTARIM


# Dünyanın gizli alanlarına (`lam`, `esneklik_hucre`, `gizli_*`, ...) dokunabilen ölçüm modülleri
# (spec §4.1). Öteki ölçüm modülleri koşunun `gercek` tablosunu okuyabilir (ölçüm verisi), dünyanın
# gizli alanlarını okumaz.
GIZLIYE_DOKUNAN = ("hakem", "simulasyon")


def test_gizli_alanlara_yalniz_hakem_ve_simulasyon():
    assert set(GIZLIYE_DOKUNAN) <= set(OLCUM_MODULLERI)
    assert any(ad == "lam" for _, ad in gizli_erisimler(PAKET / "hakem.py"))     # tarayıcı hakemi görüyor
    bulunan = {}
    for m in OLCUM_MODULLERI:
        y = PAKET / f"{m}.py"
        if m in GIZLIYE_DOKUNAN or not y.is_file():
            continue
        if b := [(satir, ad) for satir, ad in gizli_erisimler(y) if ad != "gercek"]:
            bulunan[m] = b
    assert (PAKET / "olcutler.py").is_file()
    assert not bulunan, f"ölçüm modülü dünyanın gizli alanını okuyor: {bulunan}"


def test_siniflandirma_testi_yeni_modulu_yakalar(tmp_path):
    paket = _yaz(tmp_path / "markdown", {"__init__": "", "kaynak": "", "hakem": "", "yeni": "",
                                          "rapor": ""})
    assert siniflandirilmamis(paket) == ["rapor", "yeni"]


def test_ablasyon_modulu_kilitli(tmp_path):
    """Ayrıştırma kolları karar modülü kilidindedir: dosya pakette, taranıyor; aynı içe aktarma ihlali yakalanır."""
    var = {y.stem for y in PAKET.glob("*.py")}
    assert set(ABLASYON_MODULLERI) <= var and set(ABLASYON_MODULLERI) <= taranacaklar(PAKET, KILITLI)
    assert "politika" in taranacaklar(PAKET, ABLASYON_MODULLERI)
    paket = _yaz(tmp_path / "markdown", {"__init__": "", "politika": "", "politika_ablasyon": "import markdown.oyun\n"})
    assert ihlaller(paket, karar=KILITLI) and not ihlaller(paket)


def test_sonradan_eklenen_karar_modulleri_listede():
    """Listedeki her ad tarayıcıya girer: dosya bugün yoksa atlanır, yarın gelince kilitlenir."""
    assert set(KARAR_MODULLERI) == {"sabitler", "kaynak", "ogrenme", "tahmin", "model", "politika"}
    var = {y.stem for y in PAKET.glob("*.py")}
    assert {"sabitler", "kaynak"} <= var
    assert taranacaklar(PAKET) >= (set(KARAR_MODULLERI) & var) | {"__init__"}


# ---------------------------------------------------------------------------
# Tarayıcının kendisi (geçici paketlerde)
# ---------------------------------------------------------------------------


def _yaz(dizin: Path, dosyalar: dict[str, str]) -> Path:
    dizin.mkdir(parents=True)
    for ad, metin in dosyalar.items():
        (dizin / f"{ad}.py").write_text(metin, encoding="utf-8")
    return dizin


def test_tarayici_ihlali_yakalar(tmp_path):
    paket = _yaz(tmp_path / "markdown", {
        "__init__": "",
        "sabitler": "import numpy as np\nfrom . import kaynak\n",                     # temiz
        "kaynak": "from perakende_analitik import kaynak as ortak\n",                   # izinli
        "ogrenme": "from perakende_veri.v4 import dunya as d\n",
        "tahmin": "from . import hakem\n",
        "model": "from markdown.olcutler import hesapla\n",
        "politika": "from .kosucu import kos\n",                  # geçişli: kosucu > allocation.motor
        "kosucu": "from allocation import motor\nfrom .simulasyon import kos\n",
        "hakem": "import perakende_veri\n",
        "simulasyon": "",
        "olcutler": "",
    })
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"ogrenme", "tahmin", "model", "politika"}
    assert ("politika > kosucu", "allocation.motor") in bulunan["politika"]
    assert ("politika > kosucu", "markdown.simulasyon") in bulunan["politika"]
    assert ("tahmin", "markdown.hakem") in bulunan["tahmin"]


@pytest.mark.parametrize("metin", [
    "import perakende_veri.v4.motor\n",
    "from perakende_veri.v4.dunya import dunya_kur\n",
    "from markdown import hakem\n",
    "from markdown import kaynak, simulasyon\n",
    "from markdown import olcutler as o\n",
    "from markdown import oyun\n",
    "from markdown.hikaye import sahne\n",
    "from markdown import kosucu\n",
    "import markdown.rapor\n",
    "from . import senaryolar\n",
    "from .analiz import x\n",
    "from . import hakem\n",
    "from .olcutler import hesapla\n",
    "import markdown.simulasyon as s\n",
    "from perakende_analitik import hakem\n",
    "import perakende_analitik.hakem\n",
    "from allocation import motor\n",
    "from allocation.motor import Takvim\n",
    "def f():\n    from markdown import hakem\n",
    "import importlib\nimportlib.import_module('perakende_veri')\n",
    "__import__('allocation.motor')\n",
])
def test_tarayici_tek_satir_ihlal(tmp_path, metin):
    paket = _yaz(tmp_path / "markdown", {"__init__": "", "hakem": "", "simulasyon": "",
                                          "olcutler": "", "model": metin})
    assert "model" in ihlaller(paket)


@pytest.mark.parametrize("metin", [
    "from markdown import kaynak\n",
    "from . import sabitler\n",
    "import numpy as np\n",
    "from perakende_analitik import kaynak, carpanlar, stok\n",
    "from allocation import kaynak, paylastir\n",
    "from allocation.kaynak import yukle\n",
    "from kumeleme import kaynak\n",
])
def test_tarayici_izinli_satir(tmp_path, metin):
    paket = _yaz(tmp_path / "markdown", {"__init__": "", "hakem": "", "kaynak": "", "sabitler": "",
                                          "model": metin})
    assert ihlaller(paket) == {}


@pytest.mark.parametrize("olcum", OLCUM_MODULLERI + OLCUM_EK_ADLAR)
def test_tarayici_olcum_modulune_gecisli_erisim_ihlal(tmp_path, olcum):
    paket = _yaz(tmp_path / "markdown", {
        "__init__": "", "model": "from . import ara\n", "ara": f"from .{olcum} import x\n",
        **{m: "" for m in OLCUM_MODULLERI + OLCUM_EK_ADLAR}})
    assert ("model > ara", f"markdown.{olcum}") in ihlaller(paket)["model"]


def test_tarayici_init_erisim_kumesinde(tmp_path):
    """`__init__` her içe aktarmada çalışır: içindeki ihlal bütün karar modüllerine yazılır."""
    paket = _yaz(tmp_path / "markdown", {
        "__init__": "from .hakem import x\n", "hakem": "", "kaynak": "", "model": ""})
    bulunan = ihlaller(paket)
    assert set(bulunan) == {"kaynak", "model"}
    assert ("kaynak > __init__", "markdown.hakem") in bulunan["kaynak"]
    temiz = _yaz(tmp_path / "temiz" / "markdown", {"__init__": '"""belge"""\n', "kaynak": ""})
    assert ihlaller(temiz) == {}


def test_tarayici_olmayan_karar_modulu_atlanir_sonradan_gelince_taranir(tmp_path):
    paket = _yaz(tmp_path / "markdown", {"__init__": "", "kaynak": "import numpy\n"})
    assert ihlaller(paket) == {} and gizli_erisim_bul(paket) == {}
    (paket / "tahmin.py").write_text("import perakende_veri\nx = w.lam\n", encoding="utf-8")
    assert set(ihlaller(paket)) == {"tahmin"}
    assert gizli_erisim_bul(paket) == {"tahmin": [(2, "lam")]}


def test_gizli_alan_tarayicisi(tmp_path):
    yol = tmp_path / "x.py"
    yol.write_text("\n".join([
        '"""Belge: gizli_magaza ve w.lam yalnız hakemde (docstring serbest)."""',
        "def f(w, con, k):",
        '    "belge: gizli_x"',
        "    a = w.lam",
        "    b = w.gizli_magaza['segment']",
        "    c = getattr(w, 'sapma_rpt')",
        "    d = con.execute('select * from gizli_talep').df()",
        "    e = w.esneklik_hucre + w.esneklik",
        "    g = w.gercek() + w.ilk_siparisler",
        "    ok = (w.magazalar, x['lam'], getattr(w, 'depo'), 'segment', GIZLI_ONEKI, 'gizli_',",
        "          k.esneklik_markdown, k.esneklik_kampanya, w.gercek_olmayan, w.sapmasiz)",
        "    return a",
    ]) + "\n", encoding="utf-8")
    assert gizli_erisimler(yol) == [(4, "lam"), (5, "gizli_magaza"), (6, "sapma_rpt"),
                                    (7, "gizli_t"), (8, "esneklik"), (8, "esneklik_hucre"),
                                    (9, "gercek"), (9, "ilk_siparisler")]


def test_gizli_tarama_erisilen_modulleri_kapsar(tmp_path):
    paket = _yaz(tmp_path / "markdown", {
        "__init__": "x = con.execute('select * from gizli_magaza')\n",
        "model": "from . import ara\n", "ara": "y = w.lam\n", "diger": "z = w.lam\n"})
    assert gizli_erisim_bul(paket) == {"__init__": [(1, "gizli_m")], "ara": [(1, "lam")]}
