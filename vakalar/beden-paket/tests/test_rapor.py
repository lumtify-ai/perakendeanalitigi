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
    """KOLLAR'ın fark satırı iki ondalıklı farkı ve onun bir kez yuvarlanmışını basar (sahte veride ilk 4 hafta
    beden kaybı P1 − Lumoda = 38,84 − 40,04 = −1,20 → −1,2)."""
    m = _bolum(_metin(tmp_path), "KOLLAR")
    assert "ilk 4 hf beden kaybı −1,20 puan (−1,2)" in m
    for iki, bir in re.findall(r"([+−]\d+,\d\d) puan \(([+−]?\d+,\d)\)", m):
        x2 = float(iki.replace("−", "-").replace(",", "."))
        assert rapor.s(rapor.tek_ondalik(x2), 1) == bir.lstrip("+")


def test_rapor_ayni_mal_12_14_yaklasik(tmp_path):
    """KOLLAR'ın mal tablosu 'evet'i yalnız 7'li kola basar; 12'li ve 14'lü kollar 'yaklaşık (±N adet)' (dönüşüm
    farkı); ABLASYON hücre düzeyindeki yer değiştirmeyi basar; R16 'inceleme açık' değil."""
    m = _metin(tmp_path)
    mal = _bolum(m, "KOLLAR").split("mal ve kırpma")[1]
    satir = {ad: s_ for s_ in mal.splitlines() for ad in rapor.KOL_ADLARI.values() if s_.startswith(f"  {ad}  ")}
    assert "evet" in satir["P1 tek 7'li"] and "yaklaşık (+12 adet)" in satir["P3 üç 12'li"]
    assert "yaklaşık (−7 adet)" in satir["P1 14'lü 2-2-4-4-2"] and "evet" not in satir["P1 14'lü 2-2-4-4-2"]
    ab = _bolum(m, "ABLASYON")
    assert "12'li kollar (aynı dönüşüm): 4/8 hücrede adet farklı, Σ|fark| 20 adet, net +12 adet" in ab
    assert "P1 14'lü: 4/8 hücrede adet farklı, Σ|fark| 20 adet, net −7 adet" in ab
    assert "inceleme açık" not in m


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
    lambda g: g["oyun"]["kosular"]["y4_p3_12"]["korunum"].__setitem__("net_fark_adet", 11),
    lambda g: g["oyun"]["kosular"]["p1_14"]["donusum"].__setitem__("option_en_buyuk_fark", 14),
    lambda g: g["oyun"]["kosular"]["y4_p3_12"]["olcutler"].__setitem__("kirpilan_adet", 12.0),
], ids=["kirpma", "dogrulama", "ayni_mal_cift", "ilk_dagitim", "ilk_sevkiyat_anahtar", "tasarim_kaydi", "hikaye_paket",
        "donusum_korunum_12", "option_siniri_14", "kirpma_12"])
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
    assert "12'li karşılığı kurulamaz" in ab and "yalnız paket büyüklüğü (aynı içerik): P1 14'lü − P1" in ab
    assert re.search(r"P3 12'li − P1 12'li: ilk 4 hf bulun\. [+−]\d+,\d\d puan \([+−]?\d+,\d\)", ab)
    assert "iki eksen bağımsız" not in km and "(bağımsız)" not in km      # sahte kümeler profille ilişkili
    assert "kahin atamayı yalnız şu mağazada değiştirir: M3" in ke
    assert "depo tanımı bu veride tasarımı değiştirmiyor" in _bolum(m, "TASARIM")
    assert "en iyi tek paket Lumoda'nınki değil" in _bolum(m, "PAKET")
    assert "7'li pakette 1/7 = %14,3, 12'li pakette 1/12 = %8,3" in _bolum(m, "PAKET")
    assert senaryolar.HEDEF.name == "beden-koli.json"

    g2 = copy.deepcopy(g)
    g2["analiz"]["egri"]["kappa"] = 1600.0
    g2["analiz"]["egri"]["kappa_tablosu"][1]["l1"] = 0.0270
    g2["analiz"]["egri"]["yeni_secim"]["l1_zincir"] = 0.19
    g2["analiz"]["egri"]["l1"]["daraltilmis"] = 0.0300
    g2["analiz"]["depo"]["tasarim_ayni"]["p2"]["iki_tanim"] = False
    monkeypatch.setattr(rapor, "BAGIMSIZ_ARI", 0.3)               # sahte ARI −0,286: eşiğin altında
    g2["analiz"]["kahin"] |= {"ayni_atama": True, "farkli_magaza": [], "farkli": {}}
    m2 = _metin(tmp_path / "b", g2)
    ke2, eg2, km2 = (_bolum(m2, b) for b in ("K EĞRİSİ", "EĞRİ", "KÜMELEME ÇAPRAZI"))
    assert "ızgaranın üst ucu" not in eg2 and "kıl payı" not in eg2 and "daraltma sonucu değiştirmiyor" not in eg2
    assert "depo tanımı bu veride tasarımı değiştirmiyor" not in _bolum(m2, "TASARIM")
    assert "iki eksen bağımsız" in km2 and "(bağımsız)" in km2
    assert "kahin atamayı değiştirmez" in ke2
    assert "sonuç görüldükten sonra eklendi" in _bolum(m2, "HİKÂYE") and "once_sarti" in _bolum(m2, "ANLATI VARSAYIMLARI")
    assert "seçilmeyen zincir seçilseydi" not in eg2                   # sahte veride okunamayan mağaza yok


def test_rapor_doyum_ve_olu_secim(tmp_path, capsys):
    """7'li K = 3'ün ikizi yoksa doyum cümlesi basılmaz, K = 3 "koşulmadı" görünür ve demo bileşimi 3|7 sonuçsuz
    kalır: arayüzde ölü seçim korunumu bozar."""
    g = sahte_rapor.girdiler()
    for r in g["analiz"]["k_egrisi"]:
        if r["adet"] == 7 and r["K"] == 3:
            r["ayni"] = None
    v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g))
    ek = []
    rapor.k_egrisi_bolumu(v, ek)
    rapor.demo_bolumu(v, ek)
    out = capsys.readouterr().out
    assert "doyuyor" not in out and "doyum" not in out and "K = 3       koşulmadı" in out
    assert re.search(r"dosyada olmayan bileşim.*3\|7", out)
    assert ("DEMO: arayüzün her bileşiminin sonucu var", False) in ek
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")


def test_rapor_yeni_magaza_secilmeyen_egriyle(tmp_path):
    """Okunamayan mağazanın hakem etiketi, kuralın seçmediği eğriye göredir (zincir seçildiyse statik profile)."""
    g = sahte_rapor.girdiler()
    g["analiz"]["egri"]["yeni"] = {
        "M9": {"kaynak": "zincir", "n": 0.0, "statik_profil": "buyuk", "profil": "orta", "kayma": -1, "l1_son": 0.24,
               "l1_zincir": 0.24, "l1_statik_profil": 0.43}}
    eg = _bolum(_metin(tmp_path / "a", g), "EĞRİ")
    assert "seçilmeyen statik profil seçilseydi 0,4300 (hakeme göre seçim iyi)" in eg
    g["analiz"]["egri"]["yeni"]["M9"] |= {"kaynak": "profil", "l1_son": 0.43}
    eg = _bolum(_metin(tmp_path / "b", g), "EĞRİ")
    assert "seçilmeyen zincir seçilseydi 0,2400 (hakeme göre seçim kötü)" in eg


def test_rapor_bayt_bayt_ayni(tmp_path):
    assert _metin(tmp_path / "a") == _metin(tmp_path / "b")


def test_analiz_kod_ozeti_hikaye_disinda():
    """Analizin kod özeti paketin hikâye dışındaki modüllerini ve analiz.py'yi kapsar."""
    assert len(analiz.kod_ozeti()) == 64 and analiz.kod_ozeti() == analiz.kod_ozeti()


def test_analiz_onbellek_yoksa_kosmaz(tmp_path):
    """analiz.py koşusuzdur: yol 0 doğrulama koşusu önbellekte yoksa `Eksik` verir, simülasyon başlatmaz."""
    from beden_paket import oyun as oyun_modulu
    ortam = oyun_modulu.Ortam(olcek="kucuk", onbellek=tmp_path / "kosular", cikti=tmp_path, ilerleme=False)
    with pytest.raises(analiz.Eksik, match="önbelleğinde yok"):
        analiz.kur(ortam)
    assert not (tmp_path / "kosular").exists() or not any((tmp_path / "kosular").iterdir())
