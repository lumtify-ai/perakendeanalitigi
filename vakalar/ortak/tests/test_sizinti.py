"""Sızıntı kilidi: gizli gerçek yalnız hakemde, hakem yalnız değerlendirmede.

`perakende_veri` (gizli gerçeği üreten paket) yalnız `hakem.py`'de içe
aktarılır; paketin hiçbir modülü `hakem`i içe aktarmaz (`degerlendir` hakem
tablosunu argüman alır, onu vakanın raporu okur). Kestiriciler bu yüzden talebin
gerçeğini göremez."""

import ast
from pathlib import Path

PAKET = Path(__file__).resolve().parents[1] / "perakende_analitik"


def _icerenler(modul: str) -> set[str]:
    """`modul`'ü (ya da alt modülünü) içe aktaran dosya adları."""
    bulunan = set()
    for dosya in sorted(PAKET.glob("*.py")):
        agac = ast.parse(dosya.read_text(encoding="utf-8"))
        for d in ast.walk(agac):
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


def test_perakende_veri_yalniz_hakemde():
    assert _icerenler("perakende_veri") <= {"hakem.py"}


def test_hakemi_paketten_kimse_ice_aktarmaz():
    assert _icerenler("hakem") == set()


def test_kilit_ihlali_yakalanir(tmp_path, monkeypatch):
    """Tarayıcının kendisi çalışıyor mu: sahte bir ihlal bulunmalı."""
    sahte = tmp_path / "perakende_analitik"
    sahte.mkdir()
    (sahte / "talep.py").write_text("from perakende_veri.v4 import uret\n", encoding="utf-8")
    (sahte / "stok.py").write_text("from . import hakem\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "PAKET", sahte)
    assert _icerenler("perakende_veri") == {"talep.py"}
    assert _icerenler("hakem") == {"stok.py"}
