"""`yollar.json`'ın devam anahtarı: biten yol yalnız aynı kodla yazılmışsa atlanır."""

import json

import pytest

from rpt import yollar

OYUN = ("AW24", "SS25")


def _sezon(d: float) -> dict:
    return {c: {"d_kar": d} for c in ("oneri|b", "mevcut|b", "mevcut|a", "frr3|b")}


@pytest.fixture
def sahte(monkeypatch, tmp_path):
    durum = {"kod": "kod-1", "kosulan": []}

    def yol_kos(yol, en_iyi, taban):
        durum["kosulan"].append(yol)
        return {"yol": yol, "sezon": {G: _sezon(float(yol)) for G in OYUN},
                "anahtarlar": {"oneri|b": f"anahtar-{yol}"}, "sure": 0.0}

    monkeypatch.setattr(yollar, "yol_kos", yol_kos)
    monkeypatch.setattr(yollar, "kod_ozeti", lambda: durum["kod"])
    monkeypatch.setattr(yollar.oyun, "OYUN", OYUN)
    cikti = tmp_path / "yollar.json"
    return durum, cikti, lambda: yollar.kos(n=2, taban=7, en_iyi="b", cikti=cikti)


def test_ayni_kodla_biten_yol_atlanir(sahte):
    durum, cikti, kos = sahte
    kos()
    assert durum["kosulan"] == [0, 1]
    kayit = json.loads(cikti.read_text(encoding="utf-8"))
    assert all(v["kod"] == "kod-1" for v in kayit["yollar"].values())
    assert kayit["yollar"]["1"]["anahtarlar"] == {"oneri|b": "anahtar-1"}
    kos()
    assert durum["kosulan"] == [0, 1]


def test_kod_degisince_yol_yeniden_hesaplanir(sahte):
    durum, cikti, kos = sahte
    kos()
    durum["kod"] = "kod-2"
    kos()
    assert durum["kosulan"] == [0, 1, 0, 1]
    assert all(v["kod"] == "kod-2" for v in json.loads(cikti.read_text(encoding="utf-8"))["yollar"].values())


def test_kodsuz_eski_kayit_yeniden_hesaplanir(sahte):
    durum, cikti, kos = sahte
    eski = {"taban": 7, "n": 2, "en_iyi": "b",
            "yollar": {str(y): {"yol": y, "sezon": {G: _sezon(9.0) for G in OYUN}} for y in (0, 1)}}
    cikti.write_text(json.dumps(eski), encoding="utf-8")
    kos()
    assert durum["kosulan"] == [0, 1]


def test_kod_ozeti_olcume_bagli(monkeypatch, tmp_path):
    o1 = yollar.kod_ozeti()
    sahte_olcut = tmp_path / "olcutler.py"
    sahte_olcut.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(yollar.olcutler, "__file__", str(sahte_olcut))
    assert yollar.kod_ozeti() != o1
