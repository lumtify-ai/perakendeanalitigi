"""Vakanın sızıntı kilidi: `blok_transfer` paketi gizli gerçeğe dokunmaz.

`hakem` ve `perakende_veri` pakette hiçbir yerde içe aktarılamaz (alt paketler dahil):
kestirim ve çözücü yayımlanan veriyle çalışır, hakem tablosu ölçüme argüman olarak
dışarıdan gelir (`olcum.kayip_tablosu`). Hakemi okuyan tek yer vakanın `rapor.py`'sidir
ve o paketin dışındadır. Vaka kökünün öteki iki betiği (`senaryolar.py`, `getiri.py`)
demo JSON'larını üretir; onlar da hakemi görmez (yayımlanan sayılar Basit kestirimle).
Tarayıcı yok-satma vakasınınkiyle aynı mantıkta, tek farkla: `rglob` ile bütün alt
dizinleri gezer (`cekirdek/`, `cozuculer/`)."""

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
PAKET = KOK / "blok_transfer"
KOK_BETIKLERI = ("senaryolar.py", "getiri.py")
YASAK = ("hakem", "perakende_veri")


def _ice_aktarir(dosya: Path, modul: str) -> bool:
    """`dosya` `modul`ü (ya da bir alt modülünü, göreli içe aktarma dahil) içe aktarıyor mu."""
    for d in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
        adlar = []
        if isinstance(d, ast.Import):
            adlar = [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            govde = ("." * d.level) + (d.module or "")
            adlar = [govde] + [f"{govde}.{a.name}".replace("..", ".") for a in d.names]
        for ad in adlar:
            son = ad.lstrip(".")
            if son == modul or son.startswith(modul + ".") or son.split(".")[-1] == modul:
                return True
    return False


def _icerenler(paket: Path, modul: str) -> set[str]:
    """`paket` altındaki (alt dizinler dahil) hangi `.py` dosyaları `modul`ü içe aktarıyor;
    göreli yol (posix) döner."""
    return {d.relative_to(paket).as_posix() for d in sorted(paket.rglob("*.py"))
            if _ice_aktarir(d, modul)}


def test_paket_gizli_gercegi_ice_aktarmaz():
    tarananlar = {d.relative_to(PAKET).as_posix() for d in PAKET.rglob("*.py")}
    # alt paketler ve yeni ölçüm katmanı gerçekten taranıyor
    assert {"hazirla.py", "olcum.py", "cekirdek/veri.py", "cozuculer/mip.py"} <= tarananlar
    for modul in YASAK:
        assert _icerenler(PAKET, modul) == set(), modul


def test_kok_betikleri_gizli_gercegi_ice_aktarmaz():
    # rapor.py hakemi okur (bilerek); senaryolar.py ve getiri.py okumaz.
    for ad in KOK_BETIKLERI:
        assert (KOK / ad).exists(), ad
        for modul in YASAK:
            assert not _ice_aktarir(KOK / ad, modul), (ad, modul)
    assert _ice_aktarir(KOK / "rapor.py", "hakem")     # tarayıcı kökte de çalışıyor


def test_tarayici_ihlali_yakalar(tmp_path):
    (tmp_path / "hazirla.py").write_text("from perakende_analitik import hakem\n", encoding="utf-8")
    alt = tmp_path / "cekirdek"
    alt.mkdir()
    (alt / "veri.py").write_text("import perakende_veri.v4\n", encoding="utf-8")
    (alt / "temiz.py").write_text("import pandas\n", encoding="utf-8")
    assert _icerenler(tmp_path, "hakem") == {"hazirla.py"}
    assert _icerenler(tmp_path, "perakende_veri") == {"cekirdek/veri.py"}
