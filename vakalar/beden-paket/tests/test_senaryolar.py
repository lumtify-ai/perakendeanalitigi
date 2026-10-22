"""senaryolar.py: demo dosyasının şeması, bileşim haritası (koşu ya da aynı tasarımlı ikiz), boyut bütçesi,
belirlenimcilik. Gerçek veri yok (`tests/sahte_rapor`)."""

import copy
import json

import pytest

import senaryolar
from tests import sahte_rapor


def _uret(g=None):
    g = sahte_rapor.girdiler() if g is None else g
    return senaryolar.uret(g["oyun"], g["analiz"])


def test_demo_sema_ve_boyut(tmp_path):
    d = _uret()
    assert list(d) == ["surum", "parametreler", "sonuclar"] and len(d["surum"]) == 12
    adlar = [p["ad"] for p in d["parametreler"]]
    assert adlar == ["paket_tipi", "adet"]
    degerler = [[str(x) for x in p["degerler"]] for p in d["parametreler"]]
    assert degerler == [["1", "2", "3", "magaza"], ["7", "12"]]
    for p in d["parametreler"]:                       # Demo.astro: her değerin etiketi
        assert set(p["deger_etiketleri"]) == {str(x) for x in p["degerler"]}
    for a, r in d["sonuclar"].items():
        parca = a.split("|")
        assert len(parca) == 2 and parca[0] in degerler[0] and parca[1] in degerler[1]
        assert list(r["ozet"]) == list(senaryolar.OZET_OLCUTLERI)
        assert all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in r["ozet"].values())
        assert isinstance(r["ozet"]["brut_kar_tl"], int)
        assert r["satirlar"] and all(set(x) == {"desen", "magaza", "kosu", "ayni"} for x in r["satirlar"])
        assert sum(x["magaza"] for x in r["satirlar"]) == len(sahte_rapor.MAGAZALAR)
    yol = senaryolar.yaz(d, tmp_path / "beden-paket.json")
    assert yol.stat().st_size < senaryolar.BUTCE
    assert json.loads(yol.read_text(encoding="utf-8")) == d
    with pytest.raises(ValueError, match="bütçe"):
        senaryolar.metin({**d, "dolgu": "x" * senaryolar.BUTCE})


def test_demo_bilesim_haritasi():
    """Koşulmamış bileşim K eğrisindeki aynı tasarımlı en küçük K'nın koşusunu alır; ikizi de olmayan
    (12'li K = 2) dosyaya girmez."""
    d = _uret()["sonuclar"]
    assert list(d) == ["1|7", "1|12", "2|7", "3|7", "3|12", "magaza|7", "magaza|12"]
    assert d["3|7"]["satirlar"][0] | {"desen": None, "magaza": None} == {"desen": None, "magaza": None, "kosu": "p2",
                                                                          "ayni": "K = 2"}
    assert d["magaza|12"]["satirlar"][0]["kosu"] == "p3_12" and d["magaza|12"]["satirlar"][0]["ayni"] == "K = 3"
    assert d["2|7"]["satirlar"][0]["ayni"] is None
    assert d["3|7"]["ozet"] == d["2|7"]["ozet"] == d["magaza|7"]["ozet"]
    g = sahte_rapor.girdiler()
    assert senaryolar.eksik(g["analiz"]["k_egrisi"]) == ["2|12"]
    o = g["oyun"]["kosular"]["p2"]["olcutler"]
    assert d["2|7"]["ozet"]["beden_kayip_payi"] == senaryolar.yuvarla(o["beden_kayip_payi"], 1)


def test_demo_belirlenimci_ve_eksik_kosu():
    assert _uret() == _uret()
    g = sahte_rapor.girdiler()
    g2 = copy.deepcopy(g)
    g2["oyun"]["kosular"]["p1"]["olcutler"]["brut_kar_tl"] += 1
    assert senaryolar.uret(g2["oyun"], g2["analiz"])["surum"] != _uret(g)["surum"]
    del g2["oyun"]["kosular"]["p3_12"]
    with pytest.raises(RuntimeError, match="p3_12"):
        senaryolar.uret(g2["oyun"], g2["analiz"])
    with pytest.raises(RuntimeError, match="yok"):
        senaryolar._oku(senaryolar.CIKTI / "yok.json", "x")
