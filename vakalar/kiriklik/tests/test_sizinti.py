"""Sızıntı kilidi (tasarım Global Constraints): karar modülleri gizli gerçeği ve ölçüm tarafını içe aktarmaz,
gizli alanları okumaz.

**Sınıflandırma.** Paketteki her `.py` tam bir kümededir:

    KARAR        sabitler, kaynak, olcu, uygunluk, tahmin, kural, model, plan   (kolların karar kodu)
    SIMULASYON   __init__, politika, simulasyon                                 (koşu anahtarına giren vaka kodu)
    OLCUM        hakem, olcutler, oyun, hikaye                                  (gizli gerçeğe dokunabilir)

Yeni bir modül önce bir listeye konur (`test_her_modul_siniflandirilmis`).

**KARAR kilidi** (AST). Yasak içe aktarım: `perakende_veri`, `allocation.motor`, `allocation.politika`, kiriklik'in
KARAR dışındaki her modülü (`hakem`, `simulasyon`, `politika`, `olcutler`, `oyun`, `hikaye` ve bilinmeyenler), dinamik
içe aktarma (`import_module`, `__import__`). Yasak ad (ad, öznitelik, argüman, anahtar kelime ya da sabit dizge):
`lam`, `esneklik*`, `gercek*`, `gizli_*`.

**Kapanış kilidi** (taze süreçte `sys.modules`). AST yalnız bu paketin dosyalarını görür; karar modülleri başka pakete
(`markdown.ogrenme`, ortak paket) dayanır. Bütün karar modülleri içe aktarılınca `perakende_veri`, `allocation`,
ölçüm ve simülasyon modülleri yüklenmemiş olmalı.

**`politika` kilidi.** Yuva türünü `perakende_veri.v4.politika`'dan alır, `perakende_veri`'den başka hiçbir şey almaz;
`allocation`'a, ölçüm modüllerine ve karar kodunun hiçbirine dokunmaz.

Statik taramanın yakalamadıkları (kod incelemesine kalır): `vars(...)`, `__dict__`, sabit olmayan dizgeyle `getattr`,
`exec` / `eval`, dizgenin parçalanıp birleştirilmesi.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import kiriklik
from kiriklik import simulasyon

PAKET = Path(kiriklik.__file__).resolve().parent
PAKET_ADI = "kiriklik"

KARAR = frozenset({"sabitler", "kaynak", "olcu", "uygunluk", "tahmin", "kural", "model", "plan"})
SIMULASYON = frozenset({"__init__", "politika", "simulasyon"})
OLCUM = frozenset({"hakem", "olcutler", "oyun", "hikaye"})

YASAK_ICE_AKTARIM = ("perakende_veri", "allocation.motor", "allocation.politika")
YASAK_TAM_AD = frozenset({"lam"})
YASAK_ONEK = ("esneklik", "gercek", "gizli_")
GIZLI_DIZGE = re.compile(r"gizli_[a-z]")
DINAMIK_ICE_AKTARIM = frozenset({"import_module", "__import__"})


def _agac(yol: Path) -> ast.Module:
    return ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))


def _altinda(ad: str, kok: str) -> bool:
    return ad == kok or ad.startswith(kok + ".")


def ice_aktarimlar(yol: Path) -> set[str]:
    """Dosyanın içe aktardığı tam modül adları (göreli adlar `kiriklik` altına çözülür; `from m import a` hem `m`'yi hem
    `m.a`'yı verir)."""
    adlar: set[str] = set()
    for d in ast.walk(_agac(yol)):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            taban = ".".join([PAKET_ADI] + ([d.module] if d.module else [])) if d.level else (d.module or "")
            adlar.add(taban)
            adlar |= {f"{taban}.{a.name}" for a in d.names}
    return adlar


def dinamik_ice_aktarimlar(yol: Path) -> list[str]:
    bulunan = []
    for d in ast.walk(_agac(yol)):
        if isinstance(d, ast.Call):
            f = d.func
            ad = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if ad in DINAMIK_ICE_AKTARIM:
                bulunan.append(ad)
    return bulunan


def _yasak_ad(ad: str) -> bool:
    return ad in YASAK_TAM_AD or ad.startswith(YASAK_ONEK)


def okunan_adlar(yol: Path) -> list[str]:
    """Ad, öznitelik, argüman, anahtar kelime ve (docstring dışı) sabit dizge değerleri."""
    agac = _agac(yol)
    for d in ast.walk(agac):
        if isinstance(d, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(d):
            d.body = d.body[1:]
    adlar = []
    for d in ast.walk(agac):
        if isinstance(d, ast.Name):
            adlar.append(d.id)
        elif isinstance(d, ast.Attribute):
            adlar.append(d.attr)
        elif isinstance(d, ast.arg):
            adlar.append(d.arg)
        elif isinstance(d, ast.keyword) and d.arg:
            adlar.append(d.arg)
        elif isinstance(d, ast.Constant) and isinstance(d.value, str):
            adlar += [d.value] if _yasak_ad(d.value) else re.findall(GIZLI_DIZGE, d.value)
    return adlar


def mevcut() -> set[str]:
    return {y.stem for y in PAKET.glob("*.py")}


# ---------------------------------------------------------------------------
# Sınıflandırma
# ---------------------------------------------------------------------------


def test_her_modul_siniflandirilmis():
    """Her mevcut modül tam bir kümede; kümeler ayrık; listedeki her ad dosya olarak var."""
    assert not (KARAR & SIMULASYON or KARAR & OLCUM or SIMULASYON & OLCUM)
    siniflandirilmis = KARAR | SIMULASYON | OLCUM
    assert mevcut() <= siniflandirilmis, f"sınıflandırılmamış modül: {sorted(mevcut() - siniflandirilmis)}"
    for ad in mevcut():
        assert sum(ad in k for k in (KARAR, SIMULASYON, OLCUM)) == 1, ad
    assert siniflandirilmis - {"__init__"} <= mevcut() and "__init__" in mevcut()


def test_simulasyon_listeleri_siniflandirmayla_ayni():
    """`simulasyon.SIMULASYON_MODULLERI` = SIMULASYON; `KOSU_DISI` = KARAR + OLCUM (anahtara yalnız simülasyon
    kodu girer, karar kodu planın kimliğiyle)."""
    assert set(simulasyon.SIMULASYON_MODULLERI) == SIMULASYON
    assert set(simulasyon.KOSU_DISI) == KARAR | OLCUM


# ---------------------------------------------------------------------------
# KARAR kilidi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ad", sorted(KARAR))
def test_karar_modulu_ice_aktarma_kilidi(ad):
    yol = PAKET / f"{ad}.py"
    alinan = ice_aktarimlar(yol)
    yasak = [a for a in alinan if any(_altinda(a, y) for y in YASAK_ICE_AKTARIM)]
    assert not yasak, f"{ad}.py yasak içe aktarım: {yasak}"
    kiriklik_ici = {a.split(".")[1] for a in alinan if a.startswith(PAKET_ADI + ".")}
    assert kiriklik_ici <= KARAR, f"{ad}.py karar dışı modül alıyor: {sorted(kiriklik_ici - KARAR)}"
    assert not dinamik_ice_aktarimlar(yol), f"{ad}.py dinamik içe aktarma"


@pytest.mark.parametrize("ad", sorted(KARAR))
def test_karar_modulu_gizli_ad_kilidi(ad):
    yol = PAKET / f"{ad}.py"
    assert not [a for a in okunan_adlar(yol) if _yasak_ad(a) or GIZLI_DIZGE.match(a)], ad


def test_karar_kapanisi_taze_surecte():
    """Karar modüllerinin bütün içe aktarım kapanışı (başka paketler dahil), taze bir süreçte: gizli gerçeğe ve ölçüm
    tarafına giden modül yüklenmez. Kapanışın kendisi de sınanır: `markdown.ogrenme` yüklenmiş olmalı."""
    kod = (f"import importlib, sys; [importlib.import_module('kiriklik.' + m) for m in {sorted(KARAR)!r}]; "
           "print(' '.join(sorted(sys.modules)))")
    r = subprocess.run([sys.executable, "-c", kod], capture_output=True, encoding="utf-8", cwd=PAKET.parent, check=True)
    yuklu = set(r.stdout.split())
    assert "markdown.ogrenme" in yuklu and f"{PAKET_ADI}.model" in yuklu
    kok = ("perakende_veri", "allocation",
           *(f"markdown.{m}" for m in ("hakem", "hikaye", "olcutler", "oyun", "politika", "politika_ablasyon", "simulasyon")),
           *(f"{PAKET_ADI}.{m}" for m in (SIMULASYON | OLCUM) - {"__init__"}))
    yasak = sorted(a for a in yuklu if any(_altinda(a, k) for k in kok))
    assert not yasak, f"karar kapanışında yasak modül: {yasak}"


def test_kilit_ihlali_yakalar(tmp_path):
    """Tarayıcının kendisi: yasak içe aktarma, yasak ad ve dinamik içe aktarma yakalanır, docstring serbest."""
    yol = tmp_path / "kotu.py"
    yol.write_text('"""lam esneklik gizli_x"""\nimport perakende_veri.v4.politika\nfrom allocation import motor\n'
                   'from kiriklik import hakem\nimport importlib\nx = w.lam\nf(gercek_tablosu=1)\n'
                   'y = "gizli_kayip"\nz = importlib.import_module("a")\n', encoding="utf-8")
    alinan = ice_aktarimlar(yol)
    assert {"perakende_veri.v4.politika", "allocation.motor", "kiriklik.hakem"} <= alinan
    assert [a for a in alinan if any(_altinda(a, y) for y in YASAK_ICE_AKTARIM)]
    adlar = okunan_adlar(yol)
    assert "lam" in adlar and "gercek_tablosu" in adlar and "gizli_kayip" in adlar
    assert "esneklik" not in adlar                       # docstring'te
    assert dinamik_ice_aktarimlar(yol) == ["import_module"]
    yol.write_text('"""lam"""\nimport numpy as np\nfrom kiriklik import plan\nlamba = 1\n', encoding="utf-8")
    assert not [a for a in okunan_adlar(yol) if _yasak_ad(a)] and not dinamik_ice_aktarimlar(yol)


# ---------------------------------------------------------------------------
# politika kilidi
# ---------------------------------------------------------------------------


def test_politika_yalniz_v4_politika_alir():
    """`politika` `perakende_veri`'den yalnız `perakende_veri.v4.politika`'yı alır; `allocation`, ölçüm ve karar
    modüllerini almaz."""
    yol = PAKET / "politika.py"
    alinan = ice_aktarimlar(yol)
    veri = {a for a in alinan if _altinda(a, "perakende_veri")}
    assert veri and all(_altinda(a, "perakende_veri.v4.politika") for a in veri), sorted(veri)
    assert not [a for a in alinan if _altinda(a, "allocation") or _altinda(a, "markdown")], sorted(alinan)
    assert not [a for a in alinan if a.startswith(PAKET_ADI + ".")], sorted(alinan)
    assert not dinamik_ice_aktarimlar(yol)
