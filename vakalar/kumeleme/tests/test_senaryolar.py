"""senaryolar.py: demo kadranının şeması (Demo.astro sözleşmesi), 15 anahtar, yuvarlama, boyut bütçesi,
bayt kararlılığı ve içerik özetli sürüm, yalnız `sonuc.json`'dan okuma; sitedeki dosyanın şeması."""

import ast
import json
from pathlib import Path

import pytest

import senaryolar
from tests import sahte_sonuc


def _sema(icerik: dict) -> None:
    assert set(icerik) == {"surum", "parametreler", "sonuclar"}
    p = icerik["parametreler"]
    assert [x["ad"] for x in p] == ["aile", "k"]
    assert p[0]["degerler"] == ["S1", "S2", "S4"] and p[1]["degerler"] == [4, 5, 6, 7, 8]
    for x in p:
        assert x["etiket"] and set(x["deger_etiketleri"]) == {str(d) for d in x["degerler"]}
    s = icerik["sonuclar"]
    beklenen = [f"{a}|{k}" for a in p[0]["degerler"] for k in p[1]["degerler"]]
    assert list(s) == beklenen and len(s) == 15          # Demo.astro: anahtar = parametre sırasıyla değerler
    for girdi in s.values():
        assert set(girdi) == {"ozet", "satirlar"}
        assert list(girdi["ozet"]) == ["hakem_ari", "kararlilik", "en_kucuk_kume", "siluet"]
        assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in girdi["ozet"].values())
        assert isinstance(girdi["ozet"]["en_kucuk_kume"], int)
        boy = [r["magaza"] for r in girdi["satirlar"]]
        assert boy == sorted(boy, reverse=True) and min(boy) == girdi["ozet"]["en_kucuk_kume"]
        assert [r["kume"] for r in girdi["satirlar"]] == list(range(1, len(boy) + 1))
        assert all(isinstance(r["ayirt_edici"], str) and r["ayirt_edici"] for r in girdi["satirlar"])


def test_sema_ve_15_anahtar():
    icerik = senaryolar.uret(sahte_sonuc.sonuc())
    _sema(icerik)
    assert len(icerik["surum"]) == 12 and icerik["surum"].isalnum()


def test_degerler_sonuctan_yuvarlanir():
    s = sahte_sonuc.sonuc()
    s["demo"]["S2|6"].update(ari=0.123456, kararlilik=0.98765, siluet=0.2805)
    oz = senaryolar.sonuclar(s)["S2|6"]["ozet"]
    assert oz == {"hakem_ari": 0.123, "kararlilik": 0.988, "en_kucuk_kume": 1, "siluet": 0.281}
    assert senaryolar.sonuclar(s)["S2|6"]["satirlar"][0] == {"kume": 1, "magaza": 3,
                                                             "ayirt_edici": "Collection · kalıp · regular"}


def test_eksik_bilesim_ve_eksik_sonuc_hata(tmp_path):
    s = sahte_sonuc.sonuc()
    del s["demo"]["S4|8"]
    with pytest.raises(RuntimeError, match="S4\\|8"):
        senaryolar.sonuclar(s)
    with pytest.raises(RuntimeError, match="kumeleme.oyun"):
        senaryolar.oku(tmp_path / "yok.json")


def test_boyut_butcesi_bayt_kararliligi_ve_surum(tmp_path):
    s = sahte_sonuc.sonuc()
    m = senaryolar.metin(senaryolar.uret(s))
    assert len(m.encode("utf-8")) < senaryolar.BUTCE
    assert m == senaryolar.metin(senaryolar.uret(sahte_sonuc.sonuc()))
    s["demo"]["S1|4"]["ari"] = 0.1
    assert senaryolar.uret(s)["surum"] != json.loads(m)["surum"]            # sürüm içeriğin özeti
    with pytest.raises(ValueError, match="bütçe"):
        senaryolar.metin({"x": "y" * senaryolar.BUTCE})
    yol = senaryolar.yaz(senaryolar.uret(s), tmp_path / "d.json")
    assert json.loads(yol.read_text(encoding="utf-8"))["sonuclar"] == senaryolar.sonuclar(s)
    assert b"\r\n" not in yol.read_bytes()


def test_ozellik_adi():
    a = senaryolar.ozellik_adi
    assert a("karisim/Basic+NOS/fiyat_segmenti/giris") == "Basic+NOS · fiyat segmenti · giriş"
    assert a("karisim_stoklu/Collection/alt_kategori/Jean") == "Collection · alt kategori · Jean (stoklu gün başına)"
    assert a("beden/3") == "beden sırası 3" and a("mevsim/07") == "Temmuz payı"
    assert a("olcek/log_metrekare") == "m²" and a("olcek/log_gunluk_ciro") == "günlük ciro"   # ozellikler._olcek
    assert a("bilinmeyen") == "bilinmeyen"


def test_site_dosyasi_semasi():
    """Sitedeki dosya (git'te) şemaya ve bütçeye uyar; sürümü içeriğin özeti."""
    yol = senaryolar.HEDEF
    if not yol.is_file():
        pytest.skip("demo dosyası henüz üretilmedi (senaryolar.py)")
    icerik = json.loads(yol.read_text(encoding="utf-8"))
    _sema(icerik)
    assert yol.stat().st_size < senaryolar.BUTCE
    assert icerik["surum"] == senaryolar._surum({"parametreler": icerik["parametreler"],
                                                 "sonuclar": icerik["sonuclar"]})


def test_kumelemeyi_ve_veriyi_ice_aktarmaz():
    agac = ast.parse(Path(senaryolar.__file__).read_text(encoding="utf-8"))
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            adlar.add(d.module or "")
    assert not any(a.startswith(("kumeleme", "perakende_veri", "perakende_analitik", "duckdb")) for a in adlar), adlar
