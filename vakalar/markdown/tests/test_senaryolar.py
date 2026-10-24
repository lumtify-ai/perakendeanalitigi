"""senaryolar.py: demo dosyasının şeması, 18 bileşim, kartların tek yuvarlaması, boyut bütçesi (spec §8)."""

import json
import re

import pytest

import rapor
import senaryolar
from tests import sahte_rapor


def test_demo_sema_ve_boyut(tmp_path):
    o = sahte_rapor.girdiler()["oyun"]
    d = senaryolar.uret(o)
    assert set(d) == {"surum", "parametreler", "ikizler", "sonuclar"} and d["ikizler"] == {}
    assert re.fullmatch(r"[0-9a-f]{12}", d["surum"])
    assert [p["ad"] for p in d["parametreler"]] == ["kol", "sezon"]
    kollar, sezonlar = (p["degerler"] for p in d["parametreler"])
    assert kollar == ["lumoda", "tekduze", "kural", "opt_tuzak", "opt_takvim", "opt"] and sezonlar == ["yaz", "kis", "toplam"]
    for p in d["parametreler"]:
        assert set(p["deger_etiketleri"]) == set(map(str, p["degerler"]))
    etiket = " ".join(v for p in d["parametreler"] for v in p["deger_etiketleri"].values())
    assert not re.search(r"\b(SS|AW)\d\d\b", etiket + " ".join(sezonlar))           # sayfada sezon kodu yok
    assert list(d["sonuclar"]) == [f"{k}|{z}" for k in kollar for z in sezonlar] and len(d["sonuclar"]) == 18
    for a, r in d["sonuclar"].items():
        assert set(r) == {"ozet", "satirlar"} and list(r["ozet"]) == list(senaryolar.KARTLAR)
        assert all(isinstance(x, float) and round(x, 1) == x for x in r["ozet"].values())
        assert r["satirlar"] and all(set(x) == {"kosu"} for x in r["satirlar"])
    assert all(d["sonuclar"][f"lumoda|{z}"]["ozet"]["katki_farki_mtl"] == 0.0 for z in sezonlar)
    lu, op = o["kosular"]["lumoda"]["olcutler"]["SS25"], o["kosular"]["opt_SS25"]["olcutler"]
    oz = d["sonuclar"]["opt|yaz"]["ozet"]
    assert oz["katki_farki_mtl"] == rapor.fark1(lu["katki"] / 1e6, op["katki"] / 1e6)
    assert oz["olu_stok_bin"] == rapor.yuv(op["olu_stok_adet"] / 1e3, 1)
    assert senaryolar.ozet({**op, "olu_stok_adet": 175_349.0}, lu)["olu_stok_bin"] == 175.3     # çift yuvarlama 175,4
    assert oz["markdown_mtl"] == rapor.tek_ondalik(rapor.yuv(op["markdown_tl"] / 1e6, 2))
    assert list(d["sonuclar"]["lumoda|yaz"]["ozet"]) == ["katki_farki_mtl", "olu_stok_bin", "markdown_mtl", "tf_str", "son_str"]
    assert oz["tf_str"] == rapor.tek_ondalik(rapor.yuv(op["tam_fiyat_str"], 2))       # İlk Sevkiyat'ın tam_fiyat_str anahtarı değil
    t = o["toplamlar"]["0"]["kural"]["olcutler"]
    assert d["sonuclar"]["kural|toplam"]["ozet"]["son_str"] == rapor.tek_ondalik(rapor.yuv(t["son_str"], 2))
    yol = senaryolar.yaz(d, tmp_path / "demo.json")
    assert yol.stat().st_size < senaryolar.BUTCE and json.loads(yol.read_text(encoding="utf-8")) == d
    assert senaryolar.uret(o) == d                                                  # bayt bayt aynı içerik


def test_demo_eksik_kosu_hata():
    o = sahte_rapor.girdiler()["oyun"]
    del o["kosular"]["kural_AW24"]
    with pytest.raises(RuntimeError, match="kural_AW24"):
        senaryolar.uret(o)
    o = sahte_rapor.girdiler()["oyun"]
    del o["toplamlar"]["0"]["opt"]
    with pytest.raises(RuntimeError, match=r"opt\|toplam"):
        senaryolar.uret(o)


def test_demo_butce(monkeypatch):
    monkeypatch.setattr(senaryolar, "BUTCE", 100)
    with pytest.raises(ValueError, match="bütçeyi aşıyor"):
        senaryolar.metin(senaryolar.uret(sahte_rapor.girdiler()["oyun"]))
