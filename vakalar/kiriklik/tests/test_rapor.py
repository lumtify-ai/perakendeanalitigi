"""rapor.py ve senaryolar.py: Türkçe biçim ve fark kuralı (tek yuvarlama), başlık soruları (`SORU n · …` tek satır,
doğru bölümde), eski ya da eksik girdi (her kural ayrı: stdout boş, stderr mesaj, çıkış 1; `--taslak` çıkış 2), demo
dosyası `senaryolar.uret()` ile aynı ve rapordaki sayılarla eşit, yıl basmama. Gerçek veri yok (`tests/sahte_rapor`);
uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`)."""

import copy
import json
import re

import pytest

import rapor
import senaryolar
from tests import sahte_rapor

HAZIRLA = rapor.hazirla


def _metin(tmp_path, g=None, **ek) -> str:
    v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g), **ek)
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0, metin
    return metin


def _bolum(metin: str, ad: str) -> str:
    bas = metin.index(f"=== {ad} ===")
    son = metin.find("\n=== ", bas + 1)
    return metin[bas:] if son < 0 else metin[bas:son]


def _main(tmp_path, monkeypatch, g=None, argv=(), **yaz_ek) -> int:
    k = sahte_rapor.yaz(tmp_path, g, **yaz_ek)
    monkeypatch.setattr(rapor, "hazirla", lambda kucuk=False, taslak=False: HAZIRLA(**k, taslak=taslak))
    return rapor.main(list(argv))


# --------------------------------------------------------------------------- biçim ve fark kuralı


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89" and rapor.s(824165) == "824.165"
    assert rapor.s(-3.2, 1) == "−3,2" and rapor.s(-0.0004, 3) == "0,000" and rapor.s(None) == "—"
    assert rapor.yd(68.97698) == "%68,98" and rapor.y(0.1234) == "%12,3" and rapor.yd(-4.56, 1) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.001, 2) == "0,00"
    assert rapor.para(530_000) == "+0,53 M TL (+0,5)" and rapor.para(-1_049_999) == "−1,05 M TL (−1,1)"
    assert rapor.yuzde(0.45675) == "%45,68 (%45,7)"
    assert rapor.hk(0) == "0" and rapor.hk(-3) == "−3" and rapor.hk(2) == "+2"


def test_fark_kurali(tmp_path):
    """Tek ondalıklı her fark iki ondalıklı farkın bir kez yarım yukarı yuvarlanmışıdır (bir ondalıklı düzeylerin farkı
    değil); demo ve rapor aynı kuralla yuvarlar; raporun bastığı her `x,xx (y,y)` çifti bu kuralı tutar."""
    for x2, x1 in ((0.95, 1.0), (-0.35, -0.4), (0.25, 0.3), (1.45, 1.5), (0.02, 0.0), (-0.05, -0.1)):
        assert rapor.tek_ondalik(x2) == pytest.approx(x1)
    a, c = 40.04, 40.15                                   # iki ondalık: +0,11 → +0,1; bir ondalık düzeyler 40,0 / 40,2
    assert rapor.fark(a, c, 2) == pytest.approx(0.11) and rapor.fark1(a, c) == pytest.approx(0.1)
    assert rapor.fark(a, c, 1) == pytest.approx(0.2)
    assert rapor.fark_para(1_004_900, 1_149_900) == "+0,15 M TL (+0,2)"      # düzeyler 1,00 / 1,15: +0,15 → +0,2
    for x in (10.045, 94.2449, 37.205, 0.65, 4.2449, -0.049):
        assert senaryolar.yuvarla(x) == rapor.tek_ondalik(rapor.yuv(x, 2))
    m = _metin(tmp_path)
    bulunan = re.findall(r"([+−]?\d+,\d\d) M TL \(([+−]?\d+,\d)\)", m)
    assert len(bulunan) > 100
    for iki, bir in bulunan:
        x2 = float(iki.replace("−", "-").replace(",", "."))
        assert rapor.s(rapor.tek_ondalik(x2), 1) == bir.lstrip("+")
    yuzdeler = re.findall(r"−?%(\d+,\d\d) \(−?%(\d+,\d)\)", m)
    assert len(yuzdeler) > 20
    for iki, bir in yuzdeler:
        assert rapor.s(rapor.tek_ondalik(float(iki.replace(",", "."))), 1) == bir
    # AYRIŞIM: opt − opt_set farkı basılan iki ondalıklı düzeylerden
    g = sahte_rapor.girdiler()["oyun"]["kosular"]
    a_, b_ = (g[f"{k}_AW24"]["olcum"]["para"]["net"]["orta"] for k in ("opt_set", "opt"))
    assert f"opt − opt_set: net (orta) {rapor.fark_para(a_, b_)}" in _bolum(m, "AYRIŞIM")


def test_soru_satirlari_tek(tmp_path):
    """S1–S8 her biri tam bir kez, tek satır ve doğru bölümde; bölümler sırasıyla."""
    m = _metin(tmp_path)
    sira = [m.index(f"=== {ad} ===") for ad, _ in rapor.BOLUMLER]
    assert sira == sorted(sira)
    assert [ad for ad, _ in rapor.BOLUMLER][:13] == [
        "VERİ", "KIRIKLIK", "ATIL", "UYGUNLUK", "PLAN", "YOL 0", "YOLLAR", "AYRIŞIM", "SATIŞA DÖNÜŞ", "PARA", "TAHMİN",
        "YAN ETKİ", "HİKÂYE"]
    yer = {1: "SATIŞA DÖNÜŞ", 2: "PARA", 3: "AYRIŞIM", 4: "AYRIŞIM", 5: "SATIŞA DÖNÜŞ", 6: "SATIŞA DÖNÜŞ",
           7: "AYRIŞIM", 8: "HİKÂYE"}
    for n, bolum in yer.items():
        assert m.count(f"SORU {n} · ") == 1 and f"SORU {n} · " in _bolum(m, bolum)
        satir = next(x for x in m.splitlines() if x.startswith(f"SORU {n} · "))
        assert len(satir) > 60
    assert not re.search(r"SORU (9|\d\d) ", m)
    assert "denetim tuttu" in _bolum(m, "KORUNUM") and "TASLAK" not in m


def test_rapor_yil_basmaz_ve_bayt_bayt_ayni(tmp_path):
    g = sahte_rapor.girdiler()
    assert "2024-12-09" in json.dumps(g["hikaye"]) and "2023-01-01" in json.dumps(g["analiz"])
    m = _metin(tmp_path / "a", g)
    assert rapor.yillar(m) == [] and _metin(tmp_path / "b", g) == m


def test_demo_uret_ile_ayni(tmp_path, capsys):
    """Demo dosyası `senaryolar.uret()` ile aynı: 27 bileşim, Demo biçimi (parametreler, ikizler, sonuclar[anahtar]
    {ozet, satirlar}); kartlar rapordaki sayılarla aynı (DEMO bölümü denetler). Dosya bir kart farklıysa rapor
    korunumla düşer (stdout boş, çıkış 1)."""
    o = sahte_rapor.girdiler()["oyun"]
    d = senaryolar.uret(o)
    assert d == senaryolar.uret(copy.deepcopy(o)) and set(d) == {"surum", "parametreler", "ikizler", "sonuclar"}
    assert [p["ad"] for p in d["parametreler"]] == ["kol", "paket", "sezon"]
    et = {p["ad"]: p["deger_etiketleri"] for p in d["parametreler"]}
    assert et["kol"] == {"kural": "uzmanın kuralı", "opt_set": "optimizasyon, set tamamlanır",
                         "opt": "optimizasyon, serbest"}
    assert et["paket"]["dusuk"] == "düşük maliyet" and list(et["sezon"]) == ["kis", "yaz", "toplam"]
    assert len(d["sonuclar"]) == 27 and all(set(r) == {"ozet", "satirlar"} for r in d["sonuclar"].values())
    r = d["sonuclar"]["opt|yuksek|toplam"]
    assert list(r["ozet"]) == list(senaryolar.KARTLAR) and r["satirlar"] == [{"kosu": "opt_AW24"}, {"kosu": "opt_SS25"}]
    net = sum(o["kosular"][f"opt_{z}"]["olcum"]["para"]["net"]["yuksek"] for z in ("AW24", "SS25"))
    assert r["ozet"]["net_fark_mtl"] == rapor.tek_ondalik(rapor.yuv(net / 1e6, 2))
    assert all(isinstance(x, (int, float)) for r in d["sonuclar"].values() for x in r["ozet"].values())
    assert json.loads(senaryolar.metin(d)) == d
    m = _metin(tmp_path / "a")
    de = _bolum(m, "DEMO")
    assert "27 bileşim" in de and f"sürüm {d['surum']}" in de
    k = sahte_rapor.yaz(tmp_path / "b")
    bozuk = senaryolar.uret(o)
    bozuk["sonuclar"]["kural|orta|kis"]["ozet"]["kirik_beden_farki"] += 1
    senaryolar.yaz(bozuk, k["demo_yol"])
    v = rapor.hazirla(**k)
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    assert "DEMO" in capsys.readouterr().err


# --------------------------------------------------------------------------- eski ya da eksik girdi


def _reddedilir(tmp_path, monkeypatch, capsys, g=None, mesaj="", **yaz_ek):
    """Kesin kipte `Eksik`: stdout boş, stderr mesaj, çıkış 1; taslakta bölüm atlanır, çıkış 2."""
    assert _main(tmp_path, monkeypatch, g, **yaz_ek) == 1
    y = capsys.readouterr()
    assert y.out == "" and re.search(mesaj, y.err), y.err
    assert _main(tmp_path, monkeypatch, g, argv=["--taslak"], **yaz_ek) == 2
    out = capsys.readouterr().out
    assert "TASLAK" in out and "=== KORUNUM ===" in out and rapor.yillar(out) == []
    return out


def test_eski_girdi_reddedilir(tmp_path, monkeypatch, capsys):
    """oyun.json yoksa iki kipte de `Eksik` (çıkış 1); bütün girdiler tazeyse çıkış 0."""
    assert _main(tmp_path / "tam", monkeypatch) == 0
    assert capsys.readouterr().out.startswith("Kırıklık Transferi")
    monkeypatch.undo()
    k = sahte_rapor.yaz(tmp_path / "yok")
    (k["cikti"] / "oyun.json").unlink()
    with pytest.raises(rapor.Eksik, match="oyun.json"):
        rapor.hazirla(**k, taslak=True)


def test_izgaranin_kosusu_eksik(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    del g["oyun"]["kosular"]["y3_opt_SS25"]
    out = _reddedilir(tmp_path, monkeypatch, capsys, g, "y3_opt_SS25 yok")
    assert "[eksik:" in out


def test_lumoda_kosusu_eksik(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["oyun"]["lumoda"]["2"] = {"ad": "y2_lumoda", "gecerli": False, "atlandi": "Lumoda koşusu önbellekte yok"}
    _reddedilir(tmp_path, monkeypatch, capsys, g, "y2_lumoda")


def test_gecersiz_kosu(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    r = g["oyun"]["kosular"]["kural_28_SS25"]
    r.update(gecerli=False, olcum=None)
    r["korunum"]["plan_kesilmedi"] = False
    _reddedilir(tmp_path, monkeypatch, capsys, g, "kural_28_SS25 geçersiz")


def test_baska_olcum_ozetiyle_olculmus(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["oyun"]["kosular"]["kahin_AW24"]["olcum_ozeti"] = "eski" * 16
    _reddedilir(tmp_path, monkeypatch, capsys, g, "kahin_AW24 bugünkü ölçüm koduyla")


def test_baska_lumoda_ile_olculmus(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["oyun"]["kosular"]["y1_kural_AW24"]["lumoda_anahtari"] = g["oyun"]["lumoda"]["0"]["anahtar"]
    _reddedilir(tmp_path, monkeypatch, capsys, g, "y1_kural_AW24 yolunun Lumoda")


def test_onbellekteki_kosu_eski_kodla(tmp_path, monkeypatch, capsys):
    """Koşunun önbellek dizini yoksa ya da `meta.json`'u bugünkü vaka koduyla değilse."""
    e = sahte_rapor.girdiler()["oyun"]["kosular"]["opt_set_AW24"]
    _reddedilir(tmp_path / "a", monkeypatch, capsys, mesaj="opt_set_AW24 .*vaka kod",
                metalar={"opt_set_AW24": {**sahte_rapor.KIMLIK, "anahtar": e["anahtar"], "vaka": "eski"}})
    _reddedilir(tmp_path / "b", monkeypatch, capsys, mesaj="opt_SS25 koşusu .* yok",
                metalar={"opt_SS25": {"anahtar": "baska"}})


def test_plan_bugunku_karar_koduyla_degil(tmp_path, monkeypatch, capsys):
    r = sahte_rapor.girdiler()["oyun"]["kosular"]["y4_kahin_SS25"]
    _reddedilir(tmp_path, monkeypatch, capsys, mesaj="y4_kahin_SS25 planı .*karar kodu",
                planlar={"y4_kahin_SS25": sahte_rapor.plan_json(r, "eski" * 16)})


def test_tahmin_isabeti_eski(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["oyun"]["tahmin"]["0"]["SS25"]["plan_kimligi"] = "baska"
    _reddedilir(tmp_path / "a", monkeypatch, capsys, g, "tahmin isabeti yol 0 SS25")
    g = sahte_rapor.girdiler()
    del g["oyun"]["tahmin"]["3"]
    _reddedilir(tmp_path / "b", monkeypatch, capsys, g, "tahmin isabeti yol 3")


def test_analiz_eski(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["analiz"]["kod"] = "eski"
    _reddedilir(tmp_path / "a", monkeypatch, capsys, g, "analiz.json bugünkü kodla")
    g = sahte_rapor.girdiler()
    g["analiz"]["veri"] = ["perakende.duckdb", 1, 2]
    _reddedilir(tmp_path / "b", monkeypatch, capsys, g, "analiz.json bugünkü v4")
    g = sahte_rapor.girdiler()
    g["analiz"] = None
    _reddedilir(tmp_path / "c", monkeypatch, capsys, g, "analiz.json yok")


def test_hikaye_eski(tmp_path, monkeypatch, capsys):
    g = sahte_rapor.girdiler()
    g["hikaye"]["kod"] = "eski"
    _reddedilir(tmp_path / "a", monkeypatch, capsys, g, "hikaye.json bugünkü kodla")
    g = sahte_rapor.girdiler()
    g["hikaye"]["kosu"]["anahtar"] = "baska"
    _reddedilir(tmp_path / "b", monkeypatch, capsys, g, "hikaye.json bu oyun.json")


def test_demo_dosyasi_yok(tmp_path, monkeypatch, capsys):
    _reddedilir(tmp_path, monkeypatch, capsys, mesaj="kiriklik-transferi.json yok", demo=False)


def test_korunum_bozulunca_bos(tmp_path, capsys):
    """Rapor içi tutarlılık (kural planının tamamlanan alıcıları = ölçülen alıcı çifti, analiz hunisi = referans
    fotoğrafı, hikâye sahnesi = ilk aday, yayımlanan karar sabahı = yol 0 Lumoda'nın karar fotoğrafı) tutmazsa stdout
    boş, çıkış 1."""
    for boz in (lambda g: g["oyun"]["kosular"]["kural_AW24"]["olcum"]["plan"].__setitem__("alici_cift", 1),
                lambda g: g["analiz"]["huni"]["SS25"]["basamaklar"][1].__setitem__("cift", 1),
                lambda g: g["hikaye"]["sahne"].__setitem__("alinan", 99),
                lambda g: g["analiz"]["huni"]["AW24"]["ozet"].__setitem__("kirik_beden", 1)):
        g = sahte_rapor.girdiler()
        boz(g)
        v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g))
        assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
        y = capsys.readouterr()
        assert y.out == "" and "korunum bozuldu" in y.err


# --------------------------------------------------------------------------- koşullu iddialar


def test_beklentiler_hesaplanan_degerden(tmp_path):
    """Nedensel beklentilerin (K13) satırı hesaplanan değere bağlı: tutmayınca TUTMUYOR basar."""
    m = _metin(tmp_path / "a")
    assert "set koşulu kazancı azaltır, kırık bedeni daha çok azaltır: TUTMUYOR" in _bolum(m, "AYRIŞIM")
    assert "maliyete bakmayan kural yüksek pakette net eksiye düşer: TUTUYOR" in _bolum(m, "PARA")
    g = sahte_rapor.girdiler()
    for z in ("AW24", "SS25"):
        for k in g["oyun"]["kosular"][f"opt_set_{z}"]["olcum"]["kiriklik"].values():
            k["kapsamlar"]["butun"]["fark"]["kirik_beden"] -= 1_000
    m2 = _metin(tmp_path / "b", g)
    assert "set koşulu kazancı azaltır, kırık bedeni daha çok azaltır: TUTUYOR" in _bolum(m2, "AYRIŞIM")
