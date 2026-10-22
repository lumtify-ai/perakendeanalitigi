"""senaryolar.py: demo kadranının şeması, 12 anahtar, boyut bütçesi, yalnız önbellekten okuma,
`oyun.demo_haritasi` ile anahtar uyumu."""

import ast
import json
import re
from pathlib import Path

import pytest

import senaryolar
from allocation import oyun, sabitler

KAL = {"tavan": True}


def _olcut(i: int) -> dict:
    return {"bulunabilirlik": 60.0 + i / 7, "tam_fiyat_str": 52.04, "sezon_sonu_kalan_yuzde": 19.75,
            "kayip_orani": 35.15, "replenishment_adet": 370691.6, "talep_adet": 1.0}


def _cozum(kol, tutma, tavan=False):
    return {"kol": kol, "taban": None, "tutma": tutma, "tavan": tavan, "repl": "lumoda", "takvim": False, "yol": 0}


def _kosular() -> dict:
    """Izgaranın demo noktalarını taşıyan sahte oyun.json kayıtları (takma ad dahil)."""
    k = {"lumoda": _cozum("lumoda", 0.0), "pay_esit": _cozum("esit", 0.0),
         "pay_benzer_tavanli": _cozum("benzer", 0.0, True), "pay_benzer_tavansiz": _cozum("benzer", 0.0),
         "pay_tahmin_tavanli": _cozum("tahmin", 0.0, True), "pay_tahmin_tavansiz": _cozum("tahmin", 0.0)}
    for t in (0.15, 0.30):
        k[f"tut_lumoda_t{round(t * 100):02d}"] = _cozum("lumoda_tut", t)
        k[f"tut_lumoda_t{round(t * 100):02d}_hiz"] = {**_cozum("lumoda_tut", t), "repl": "hiz"}
        k[f"tut_eniyi_t{round(t * 100):02d}"] = _cozum("tahmin", t)          # tavansız en iyi (R43)
        k[f"demo_esit_t{round(t * 100):02d}"] = _cozum("esit", t)
        k[f"demo_benzer_t{round(t * 100):02d}"] = _cozum("benzer", t)
        k[f"demo_tahmin_t{round(t * 100):02d}"] = _cozum("tahmin", t)
    return {ad: {"cozum": c} for ad, c in k.items()}


def _sahte(tmp_path: Path, eksik_onbellek: str | None = None) -> tuple[dict, Path]:
    onbellek = tmp_path / "kosular"
    kosular = _kosular()
    for i, (ad, e) in enumerate(kosular.items()):
        an = f"{i:02d}" + "f" * 62
        e.update(anahtar=an, olcutler=_olcut(i))
        if ad != eksik_onbellek and not ad.startswith("demo_tahmin"):
            d = onbellek / f"{ad}_{an[:20]}"
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"anahtar": an}), encoding="utf-8")
    for t in ("15", "30"):                     # demo_tahmin_tNN = tut_eniyi_tNN (Ruling R30)
        taban = f"tut_eniyi_t{t}"
        kosular[f"demo_tahmin_t{t}"] = {**kosular[taban], "ayni": taban}
    harita = oyun.demo_haritasi(kosular, KAL)
    return {"kosular": kosular, "demo": harita}, onbellek


def test_harita_anahtari_oyun_ile_ayni():
    assert [senaryolar.harita_anahtari(t) for t in senaryolar.TUTMALAR] == [f"{t:g}" for t in sabitler.DEMO_TUTMA]
    assert tuple(round(100 * t) for t in sabitler.DEMO_TUTMA) == senaryolar.TUTMALAR


def test_sema_ve_12_anahtar(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    icerik = senaryolar.uret(oyun_k, onbellek=onbellek, surum="abc1234")
    assert set(icerik) == {"surum", "parametreler", "sonuclar"} and icerik["surum"] == "abc1234"
    p = icerik["parametreler"]
    assert [x["ad"] for x in p] == ["pay", "tutma"]
    assert p[0]["degerler"] == ["lumoda", "esit", "benzer", "tahmin"]
    assert p[1]["degerler"] == [0, 15, 30] and set(p[1]["deger_etiketleri"]) == {"0", "15", "30"}
    for x in p:
        assert x["etiket"] and set(x["deger_etiketleri"]) == {str(d) for d in x["degerler"]}
    s = icerik["sonuclar"]
    assert len(s) == 12
    assert list(s)[0] == "lumoda|0" and list(s)[-1] == "tahmin|30"
    for anahtar, girdi in s.items():
        pay, t = anahtar.split("|")
        assert pay in senaryolar.PAYLAR and int(t) in senaryolar.TUTMALAR
        assert set(girdi) == {"ozet", "satirlar"} and girdi["satirlar"] == []
        assert set(girdi["ozet"]) == {"bulunabilirlik", "tam_fiyat_str", "sezon_sonu_kalan_yuzde", "kayip_orani",
                                      "replenishment_adet"}


def test_bilesimler_dogru_kosudan(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    k = oyun_k["kosular"]
    s = senaryolar.sonuclar(oyun_k, onbellek)
    beklenen = {"lumoda|0": "lumoda", "lumoda|15": "tut_lumoda_t15", "lumoda|30": "tut_lumoda_t30",
                "esit|0": "pay_esit", "esit|30": "demo_esit_t30", "benzer|0": "pay_benzer_tavansiz",
                "benzer|15": "demo_benzer_t15", "tahmin|0": "pay_tahmin_tavansiz"}
    for anahtar, ad in beklenen.items():
        assert s[anahtar]["ozet"]["bulunabilirlik"] == round(k[ad]["olcutler"]["bulunabilirlik"], 1), anahtar
    # tahmin %15 (en iyi = tahmin): tutma ekseninin aynı koşusu
    assert s["tahmin|15"]["ozet"]["bulunabilirlik"] == round(k["tut_eniyi_t15"]["olcutler"]["bulunabilirlik"], 1)


def test_degerler_olcutten_yuvarlanir(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    oz = senaryolar.sonuclar(oyun_k, onbellek)["esit|0"]["ozet"]       # pay_esit: i = 1
    assert oz == {"bulunabilirlik": round(60 + 1 / 7, 1), "tam_fiyat_str": 52.0, "sezon_sonu_kalan_yuzde": 19.8,
                  "kayip_orani": 35.1, "replenishment_adet": 370692}
    assert isinstance(oz["replenishment_adet"], int)


def test_takma_ad_tabanin_onbellegini_okur(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    oyun_k["demo"]["tahmin"]["0.15"] = "demo_tahmin_t15"             # takma adın kendi dizini yok
    assert senaryolar.sonuclar(oyun_k, onbellek)["tahmin|15"]["ozet"]


def test_onbellekte_olmayan_kosu_hata(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path, eksik_onbellek="tut_lumoda_t30")
    with pytest.raises(RuntimeError, match="tut_lumoda_t30"):
        senaryolar.sonuclar(oyun_k, onbellek)


def test_olculmemis_kosu_ve_eksik_harita_hata(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    del oyun_k["kosular"]["demo_esit_t15"]
    with pytest.raises(RuntimeError, match="oyun.json"):
        senaryolar.sonuclar(oyun_k, onbellek)
    oyun_k, onbellek = _sahte(tmp_path / "b")
    oyun_k["demo"]["benzer"]["0.3"] = None                          # ızgara bitmedi
    with pytest.raises(RuntimeError, match=re.escape("benzer|30")):
        senaryolar.sonuclar(oyun_k, onbellek)


def test_anahtari_farkli_onbellek_hata(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    e = oyun_k["kosular"]["pay_esit"]
    e["anahtar"] = e["anahtar"][:20] + "0" * 44
    with pytest.raises(RuntimeError, match="pay_esit"):
        senaryolar.sonuclar(oyun_k, onbellek)


def test_boyut_butcesi_ve_bayt_kararliligi(tmp_path):
    oyun_k, onbellek = _sahte(tmp_path)
    m = senaryolar.metin(senaryolar.uret(oyun_k, onbellek=onbellek, surum="x"))
    assert len(m.encode("utf-8")) < senaryolar.BUTCE
    assert m == senaryolar.metin(senaryolar.uret(oyun_k, onbellek=onbellek, surum="x"))
    with pytest.raises(ValueError, match="bütçe"):
        senaryolar.metin({"x": "y" * senaryolar.BUTCE})
    yol = senaryolar.yaz(senaryolar.uret(oyun_k, onbellek=onbellek, surum="x"), tmp_path / "d.json")
    assert json.loads(yol.read_text(encoding="utf-8"))["sonuclar"] == senaryolar.sonuclar(oyun_k, onbellek)


def test_surum_tarih_tasimaz():
    s = senaryolar._surum()
    assert s == "yerel" or (s.isalnum() and len(s) <= 12)


def test_motoru_ice_aktarmaz():
    agac = ast.parse(Path(senaryolar.__file__).read_text(encoding="utf-8"))
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            adlar.add(d.module or "")
    assert not any(a.startswith(("allocation", "perakende_veri")) for a in adlar), adlar
