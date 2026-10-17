"""senaryolar.py: demo kadranının şeması, 27 anahtar, boyut bütçesi, yalnız önbellekten okuma."""

import ast
import json
from pathlib import Path

import pytest

import senaryolar


def _olcut(i: int) -> dict:
    return {"bulunabilirlik": 60.0 + i / 7, "kayip_orani": 30.04, "satisa_donme_gun": 5.55,
            "magaza_stok_son": 123456.6, "toplama_maliyeti_tl": 7654321.4, "kirik_cift_pay_yuzde": 80.123,
            "talep_adet": 1.0}


def _sahte(tmp_path: Path, eksik_onbellek: str | None = None) -> tuple[dict, Path]:
    onbellek = tmp_path / "kosular"
    kosular = {}
    i = 0
    for a in senaryolar.ALIMLAR:
        for y in senaryolar.YONTEMLER:
            for t in senaryolar.TAVANLAR:
                ad = senaryolar.kosu_adi(a, y, t)
                an = f"{i:02d}" + "f" * 62
                kosular[ad] = {"anahtar": an, "olcutler": _olcut(i)}
                if ad != eksik_onbellek:
                    d = onbellek / f"{ad}_{an[:20]}"
                    d.mkdir(parents=True)
                    (d / "meta.json").write_text(json.dumps({"anahtar": an}), encoding="utf-8")
                i += 1
    return {"kosular": kosular}, onbellek


def test_kosu_adi_oyun_izgarasiyla_ayni():
    assert senaryolar.kosu_adi(40, "tahmin_taban", "siki") == "demo_tahmin_taban_a040_siki"
    assert senaryolar.kosu_adi(100, "kural", "kisitsiz") == "demo_kural_a100_kisitsiz"


def test_sema_ve_27_anahtar(tmp_path):
    oyun, onbellek = _sahte(tmp_path)
    icerik = senaryolar.uret(oyun, onbellek=onbellek, surum="abc 2026-01-01")
    assert set(icerik) == {"surum", "parametreler", "sonuclar"}
    p = icerik["parametreler"]
    assert [x["ad"] for x in p] == ["alim", "yontem", "tavan"]
    assert p[0]["degerler"] == [40, 70, 100] and set(p[0]["deger_etiketleri"]) == {"40", "70", "100"}
    assert p[1]["degerler"] == ["kural", "tahmin_taban", "tahmin"]
    assert p[2]["degerler"] == ["kisitsiz", "gevsek", "siki"]
    for x in p:
        assert x["etiket"] and set(x["deger_etiketleri"]) == {str(d) for d in x["degerler"]}
    s = icerik["sonuclar"]
    assert len(s) == 27
    assert list(s)[0] == "40|kural|kisitsiz" and list(s)[-1] == "100|tahmin|siki"
    for anahtar, girdi in s.items():
        a, y, t = anahtar.split("|")
        assert int(a) in senaryolar.ALIMLAR and y in senaryolar.YONTEMLER and t in senaryolar.TAVANLAR
        assert set(girdi) == {"ozet", "satirlar"} and girdi["satirlar"] == []
        assert set(girdi["ozet"]) == {"bulunabilirlik", "kayip_orani", "satisa_donme_gun", "magaza_stok_son",
                                      "toplama_maliyeti_tl", "kirik_cift_pay_yuzde"}


def test_degerler_olcutten_yuvarlanir(tmp_path):
    oyun, onbellek = _sahte(tmp_path)
    oz = senaryolar.sonuclar(oyun, onbellek)["40|kural|gevsek"]["ozet"]   # i = 1
    assert oz == {"bulunabilirlik": round(60 + 1 / 7, 1), "kayip_orani": 30.0, "satisa_donme_gun": 5.5,
                  "magaza_stok_son": 123457, "toplama_maliyeti_tl": 7654321, "kirik_cift_pay_yuzde": 80.1}
    assert isinstance(oz["magaza_stok_son"], int)


def test_onbellekte_olmayan_kosu_hata(tmp_path):
    oyun, onbellek = _sahte(tmp_path, eksik_onbellek="demo_tahmin_a070_gevsek")
    with pytest.raises(RuntimeError, match="demo_tahmin_a070_gevsek"):
        senaryolar.sonuclar(oyun, onbellek)


def test_olculmemis_kosu_hata(tmp_path):
    oyun, onbellek = _sahte(tmp_path)
    del oyun["kosular"]["demo_kural_a100_siki"]
    with pytest.raises(RuntimeError, match="oyun.json"):
        senaryolar.sonuclar(oyun, onbellek)


def test_anahtari_farkli_onbellek_hata(tmp_path):
    oyun, onbellek = _sahte(tmp_path)
    oyun["kosular"]["demo_kural_a040_siki"]["anahtar"] = oyun["kosular"]["demo_kural_a040_siki"]["anahtar"][:20] + "0" * 44
    with pytest.raises(RuntimeError, match="demo_kural_a040_siki"):
        senaryolar.sonuclar(oyun, onbellek)


def test_boyut_butcesi(tmp_path):
    oyun, onbellek = _sahte(tmp_path)
    m = senaryolar.metin(senaryolar.uret(oyun, onbellek=onbellek, surum="x"))
    assert len(m.encode("utf-8")) < senaryolar.BUTCE
    with pytest.raises(ValueError, match="bütçe"):
        senaryolar.metin({"x": "y" * senaryolar.BUTCE})


def test_motoru_ice_aktarmaz():
    agac = ast.parse(Path(senaryolar.__file__).read_text(encoding="utf-8"))
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            adlar.add(d.module or "")
    assert not any(a.startswith(("replenishment", "perakende_veri")) for a in adlar), adlar
