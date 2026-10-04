"""Vakanın sızıntı kilidi: `yok_satma` paketi (hazirla, hikaye_sec) gizli gerçeğe dokunmaz.

`hakem` ve `perakende_veri` yalnız `rapor.py`'de içe aktarılabilir (rapor ölçer; kestirim
ve hikâye seçimi yayımlanan veriyle yapılır). Tarayıcı ortak paketinkiyle aynı mantıkta."""

import ast
from pathlib import Path

PAKET = Path(__file__).resolve().parents[1] / "yok_satma"
YASAK = ("hakem", "perakende_veri")


def _icerenler(paket: Path, modul: str) -> set[str]:
    bulunan = set()
    for dosya in sorted(paket.glob("*.py")):
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
                    bulunan.add(dosya.name)
    return bulunan


def test_paket_gizli_gercegi_ice_aktarmaz():
    assert {"hazirla.py", "hikaye_sec.py"} <= {d.name for d in PAKET.glob("*.py")}
    for modul in YASAK:
        assert _icerenler(PAKET, modul) == set(), modul


def test_tarayici_ihlali_yakalar(tmp_path):
    (tmp_path / "hazirla.py").write_text("from perakende_analitik import hakem\n", encoding="utf-8")
    (tmp_path / "hikaye_sec.py").write_text("import perakende_veri.v4\n", encoding="utf-8")
    assert _icerenler(tmp_path, "hakem") == {"hazirla.py"}
    assert _icerenler(tmp_path, "perakende_veri") == {"hikaye_sec.py"}
