import json
from datetime import date
from pathlib import Path

import pytest

import senaryolar

KARAR = date(2025, 12, 29)


def test_sema_ve_anahtar_tamligi(con, tmp_path):
    icerik = senaryolar.uret(con, KARAR)
    assert [p["ad"] for p in icerik["parametreler"]] == ["cover_esigi", "min_satis", "yontem"]
    assert icerik["surum"]
    assert len(icerik["sonuclar"]) == 3 * 4 * 2
    assert "12|2|greedy" in icerik["sonuclar"]
    ornek = icerik["sonuclar"]["12|2|mip"]
    assert set(ornek["ozet"]) == {
        "option_sayisi", "tasinan_adet", "rota_sayisi", "bosalan_magaza",
        "net_kazanc_tl", "sure_sn",
    }
    assert ornek["satirlar"] == []

    hedef = tmp_path / "blok-transfer.json"
    senaryolar.yaz(icerik, hedef)
    assert hedef.stat().st_size < 500 * 1024
    json.loads(hedef.read_text(encoding="utf-8"))


def test_boyut_bekcisi(tmp_path):
    sisik = {"surum": "x", "parametreler": [], "sonuclar": {"k": {"ozet": {"a": "b" * 600_000}, "satirlar": []}}}
    with pytest.raises(ValueError, match="500"):
        senaryolar.yaz(sisik, tmp_path / "sisik.json")
