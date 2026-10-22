"""rapor.py: Türkçe biçim, tek yuvarlama, tampon + korunum (bozulursa stdout boş, çıkış 1), eksik ya da eski
girdi, bölüm sırası (spec §5), başlık soruları, koşullu iddialar. Gerçek veri yok (`tests/sahte_rapor`);
uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`)."""

import copy
import re

import pytest

import analiz
import rapor
import senaryolar
from tests import sahte_rapor


def _metin(tmp_path, g=None, **ek) -> str:
    v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g), **ek)
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0, metin
    return metin


def _bolum(metin: str, ad: str) -> str:
    bas = metin.index(f"=== {ad} ===")
    son = metin.find("\n=== ", bas + 1)
    return metin[bas:] if son < 0 else metin[bas:son]


# --------------------------------------------------------------------------- biçim ve yuvarlama


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89" and rapor.s(824165) == "824.165"
    assert rapor.s(-3.2, 1) == "−3,2" and rapor.s(-0.0004, 3) == "0,000" and rapor.s(None) == "—"
    assert rapor.yd(68.97698, 2) == "%68,98" and rapor.y(0.1234) == "%12,3" and rapor.yd(-4.56) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.001, 2) == "0,00"
    assert rapor.tl(116405702.4) == "116.405.702 TL (116,4 milyon TL)"


def test_tek_yuvarlama():
    """Tek ondalıklı fark iki ondalıklı farkın bir kez yuvarlanmışıdır, bir ondalıklı düzeylerin farkı değil;
    demo ve rapor aynı kuralla yuvarlar."""
    for x2, x1 in ((0.95, 1.0), (-0.35, -0.4), (0.25, 0.3), (1.45, 1.5), (0.02, 0.0)):
        assert rapor.tek_ondalik(x2) == pytest.approx(x1)
    a, c = 40.04, 40.15                                   # iki ondalık: +0,11 → +0,1; bir ondalık düzeyler 40,0 / 40,2
    assert rapor.fark(a, c, 2) == pytest.approx(0.11) and rapor.fark1(a, c) == pytest.approx(0.1)
    assert rapor.fark(a, c, 1) == pytest.approx(0.2)
    assert rapor.fb("beden_kayip_payi", a, c) == "+0,11 puan (+0,1)"
    for x in (10.045, 94.2449, 37.205, 0.65):
        assert senaryolar.yuvarla(x, 1) == rapor.tek_ondalik(rapor.yuv(x, 2))
    assert senaryolar.yuvarla(10.045, 1) == pytest.approx(10.1)          # doğrudan bir ondalık 10,0 verirdi
    assert senaryolar.yuvarla(1234.5, 0) == 1235


def test_rapor_farklari_basilan_degerlerden(tmp_path):
    """KOLLAR'ın fark satırı iki ondalıklı farkı ve onun bir kez yuvarlanmışını basar (sahte veride beden kaybı
    P1 − Lumoda = 38,84 − 40,04 = −1,20 → −1,2)."""
    m = _bolum(_metin(tmp_path), "KOLLAR")
    assert "beden kaybı payı −1,20 puan (−1,2)" in m
    for iki, bir in re.findall(r"([+−]\d+,\d\d) puan \(([+−]?\d+,\d)\)", m):
        x2 = float(iki.replace("−", "-").replace(",", "."))
        assert rapor.s(rapor.tek_ondalik(x2), 1) == bir.lstrip("+")


# --------------------------------------------------------------------------- tampon, korunum, eksik


def test_rapor_tam_ve_bolum_sirasi(tmp_path):
    m = _metin(tmp_path)
    sira = [m.index(f"=== {ad} ===") for ad, _ in rapor.BOLUMLER]
    assert sira == sorted(sira) and [ad for ad, _ in rapor.BOLUMLER] == [
        "VERİ", "PAKET", "EĞRİ", "TASARIM", "KOLLAR", "YOLLAR", "K EĞRİSİ", "ABLASYON", "KÜMELEME ÇAPRAZI", "HİKÂYE",
        "DEMO", "ANLATI VARSAYIMLARI", "KORUNUM"]
    yer = {1: "PAKET", 2: "EĞRİ", 3: "KÜMELEME ÇAPRAZI", 4: "K EĞRİSİ", 5: "K EĞRİSİ", 6: "ABLASYON"}
    for n, bolum in yer.items():
        assert m.count(f"SORU {n} · ") == 1 and f"SORU {n} · " in _bolum(m, bolum)
    assert "denetim tuttu" in _bolum(m, "KORUNUM") and "TASLAK" not in m
    assert "depo:" in _bolum(m, "ANLATI VARSAYIMLARI") and "R16" in _bolum(m, "ANLATI VARSAYIMLARI")


@pytest.mark.parametrize("boz", [
    lambda g: g["oyun"]["kosular"]["p1"]["olcutler"].__setitem__("kirpilan_adet", 7.0),
    lambda g: g["oyun"]["kosular"]["dogrulama"]["ilk_sevkiyat"].__setitem__("birebir", 50),
    lambda g: g["oyun"]["kosular"]["y2_p2"]["korunum"].__setitem__("fark_adet", 3),
    lambda g: g["oyun"]["kosular"]["p2"]["olcutler"].__setitem__("ilk_dagitim_adet", 6_993.0),
    lambda g: g["analiz"]["ilk_sevkiyat"]["3"].__setitem__("anahtar_ayni", False),
    lambda g: g["analiz"]["tasarim"]["p2"]["atama"].__setitem__("M4", "1-1-2-2-1"),
    lambda g: g["hikaye"]["kucuk"].__setitem__("desen", "1-1-2-2-1"),
    lambda g: g["oyun"]["kosular"]["y4_p3_12"].__setitem__("ayni_mal", False),
], ids=["kirpma", "dogrulama", "ayni_mal_cift", "ilk_dagitim", "ilk_sevkiyat_anahtar", "tasarim_kaydi", "hikaye_paket",
        "ayni_mal_12"])
def test_rapor_korunum_bozulunca_bos(tmp_path, capsys, boz):
    g = sahte_rapor.girdiler()
    boz(g)
    v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g))
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "korunum bozuldu" in yakalanan.err


def test_rapor_main_eksik_kosuda_bos_ve_cikis_1(tmp_path, capsys, monkeypatch):
    """Izgaranın bir koşusu yoksa (ya da bugünkü ölçüm koduyla ölçülmemişse, önbellek dizini yoksa) kesin kip
    `Eksik`: stdout boş, çıkış 1; taslak bölümü atlar ve eksikleri listeler (çıkış 2)."""
    g = sahte_rapor.girdiler()
    del g["oyun"]["kosular"]["y3_p1"]
    k = sahte_rapor.yaz(tmp_path, g)
    with pytest.raises(rapor.Eksik, match="y3_p1"):
        rapor.hazirla(**k)
    asil = rapor.hazirla
    monkeypatch.setattr(rapor, "hazirla", lambda kucuk=False, taslak=False: asil(**k, taslak=taslak))
    assert rapor.main([]) == 1
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "y3_p1" in yakalanan.err
    assert rapor.main(["--taslak"]) == 2
    out = capsys.readouterr().out
    assert "[eksik: koşu y3_p1]" in out and "TASLAK" in out and "=== KORUNUM ===" in out


def test_rapor_eski_girdiyi_reddeder(tmp_path):
    k = sahte_rapor.yaz(tmp_path)
    with pytest.raises(rapor.Eksik, match="ölçüm koduyla"):
        rapor.hazirla(**{**k, "olcum_kodu": "baska"})
    with pytest.raises(rapor.Eksik, match="analiz.json bugünkü kodla"):
        rapor.hazirla(**{**k, "analiz_kodu": "baska"})
    with pytest.raises(rapor.Eksik, match="hikaye.json bugünkü kodla"):
        rapor.hazirla(**{**k, "hikaye_kodu": "baska"})
    (k["onbellek"] / "p2_p2__________________").rename(k["onbellek"] / "silindi")
    with pytest.raises(rapor.Eksik, match="önbellek: p2 "):
        rapor.hazirla(**k)


def test_rapor_demo_dosyasi_guncel_degilse_korunum(tmp_path, capsys):
    k = sahte_rapor.yaz(tmp_path)
    d = senaryolar.uret(*(lambda g: (g["oyun"], g["analiz"]))(sahte_rapor.girdiler()))
    d["sonuclar"]["1|7"]["ozet"]["brut_kar_tl"] += 1
    senaryolar.yaz(d, k["demo_yol"])
    v = rapor.hazirla(**k)
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    assert "DEMO" in capsys.readouterr().err


# --------------------------------------------------------------------------- koşullu iddialar


def test_rapor_kosullu_iddialar(tmp_path, monkeypatch):
    """Anlatı cümleleri hesaplanan değere bağlıdır: değer tutmazsa cümle basılmaz."""
    g = sahte_rapor.girdiler()
    m = _metin(tmp_path / "a", g)
    ke, eg, ab, km = (_bolum(m, b) for b in ("K EĞRİSİ", "EĞRİ", "ABLASYON", "KÜMELEME ÇAPRAZI"))
    assert "kazanç K = 2'de doyuyor" in ke and "(doyum K = 2)" in ke
    assert "12'li pakette K = 4 ve mağazaya özel K = 3 ile aynı" in ke
    assert "ızgaranın üst ucu" in eg and "kıl payı" in eg and "daraltma sonucu değiştirmiyor" in eg
    assert "hakemsiz ölçüt havuz hattını seçer, hakemli ölçüt Collection hattını" in eg
    assert "sansür düzeltmesi 7'li tasarımı değiştirmiyor" in ab
    assert "iki eksen bağımsız" not in km and "(bağımsız)" not in km      # sahte kümeler profille ilişkili
    assert "kahin atamayı yalnız şu mağazada değiştirir: M3" in ke
    assert "depo tanımı bu veride tasarımı değiştirmiyor" in _bolum(m, "TASARIM")
    assert "en iyi tek paket Lumoda'nınki değil" in _bolum(m, "PAKET")

    g2 = copy.deepcopy(g)
    for r in g2["analiz"]["k_egrisi"]:
        if r["adet"] == 7 and r["K"] == 3:
            r["ayni"] = None
    g2["analiz"]["egri"]["kappa"] = 1600.0
    g2["analiz"]["egri"]["kappa_tablosu"][1]["l1"] = 0.0270
    g2["analiz"]["egri"]["yeni_secim"]["l1_zincir"] = 0.19
    g2["analiz"]["egri"]["l1"]["daraltilmis"] = 0.0300
    g2["analiz"]["depo"]["tasarim_ayni"]["p2"]["iki_tanim"] = False
    monkeypatch.setattr(rapor, "BAGIMSIZ_ARI", 0.3)               # sahte ARI −0,286: eşiğin altında
    g2["analiz"]["kahin"] |= {"ayni_atama": True, "farkli_magaza": [], "farkli": {}}
    m2 = _metin(tmp_path / "b", g2)
    ke2, eg2, km2 = (_bolum(m2, b) for b in ("K EĞRİSİ", "EĞRİ", "KÜMELEME ÇAPRAZI"))
    assert "doyuyor" not in ke2 and "doyum" not in ke2
    assert "K = 3       koşulmadı" in ke2
    assert "ızgaranın üst ucu" not in eg2 and "kıl payı" not in eg2 and "daraltma sonucu değiştirmiyor" not in eg2
    assert "depo tanımı bu veride tasarımı değiştirmiyor" not in _bolum(m2, "TASARIM")
    assert "iki eksen bağımsız" in km2 and "(bağımsız)" in km2
    assert "kahin atamayı değiştirmez" in ke2
    assert re.search(r"dosyada olmayan bileşim.*3\|7", _bolum(m2, "DEMO"))


def test_rapor_bayt_bayt_ayni(tmp_path):
    assert _metin(tmp_path / "a") == _metin(tmp_path / "b")


def test_analiz_kod_ozeti_hikaye_disinda():
    """Analizin kod özeti paketin hikâye dışındaki modüllerini ve analiz.py'yi kapsar."""
    assert len(analiz.kod_ozeti()) == 64 and analiz.kod_ozeti() == analiz.kod_ozeti()
