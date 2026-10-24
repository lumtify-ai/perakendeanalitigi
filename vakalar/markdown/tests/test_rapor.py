"""rapor.py: Türkçe biçim, tek yuvarlama, tampon + korunum (bozulunca stdout boş, çıkış 1), eksik ya da eski girdi,
bölüm sırası (spec §5), başlık soruları (spec §4.6), yıl basmama, koşullu iddialar. Gerçek veri yok
(`tests/sahte_rapor`); uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`)."""

import copy
import re

import pytest

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
    assert rapor.yd(68.97698) == "%68,98" and rapor.y(0.1234) == "%12,3" and rapor.yd(-4.56, 1) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.001, 2) == "0,00"
    assert rapor.farki("t", 37_490_000, 38_020_000) == "+0,53 M TL (+0,5)"
    assert rapor.farki("y", 46.57, 40.73) == "−5,84 puan (−5,8)" and rapor.farki("a", 4252.0, 2229.0) == "−2.023"
    assert rapor.hk(0) == "0" and rapor.hk(-8) == "−8" and rapor.hk(3) == "+3"
    assert rapor.hafta_metni(-8) == "indirimden 8 hafta önce" and rapor.hafta_metni(0) == "indirim haftası"
    assert rapor.gun_metni(2) == "indirim gününden 2 gün sonra (indirimin 3. günü)"


def test_tek_yuvarlama():
    """Tek ondalıklı fark iki ondalıklı farkın bir kez yuvarlanmışıdır, bir ondalıklı düzeylerin farkı değil;
    demo ve rapor aynı kuralla yuvarlar."""
    for x2, x1 in ((0.95, 1.0), (-0.35, -0.4), (0.25, 0.3), (1.45, 1.5), (0.02, 0.0)):
        assert rapor.tek_ondalik(x2) == pytest.approx(x1)
    a, c = 40.04, 40.15                                   # iki ondalık: +0,11 → +0,1; bir ondalık düzeyler 40,0 / 40,2
    assert rapor.fark(a, c, 2) == pytest.approx(0.11) and rapor.fark1(a, c) == pytest.approx(0.1)
    assert rapor.fark(a, c, 1) == pytest.approx(0.2)
    assert rapor.farki("y", a, c) == "+0,11 puan (+0,1)"
    for x in (10.045, 94.2449, 37.205, 0.65, 4.2449):
        assert senaryolar.yuvarla(x) == rapor.tek_ondalik(rapor.yuv(x, 2))
    assert senaryolar.yuvarla(10.045) == pytest.approx(10.1)          # doğrudan bir ondalık 10,0 verirdi
    for a, c in ((37.4949, 38.0251), (21.814, 21.8149), (15.68, 15.6849), (-1.005, 2.004)):
        assert senaryolar.fark1(a, c) == rapor.fark1(a, c)


def test_rapor_farklari_basilan_degerlerden(tmp_path):
    """YOL 0'ın fark satırı iki ondalıklı farkı ve onun bir kez yuvarlanmışını basar."""
    m = _bolum(_metin(tmp_path), "YOL 0")
    bulunan = re.findall(r"([+−]?\d+,\d\d) (?:M TL|puan) \(([+−]?\d+,\d)\)", m)
    assert len(bulunan) > 50
    for iki, bir in bulunan:
        x2 = float(iki.replace("−", "-").replace(",", "."))
        assert rapor.s(rapor.tek_ondalik(x2), 1) == bir.lstrip("+")
    assert "opt: sezon katkısı +0,53 M TL (+0,5)" in m


# --------------------------------------------------------------------------- tampon, korunum, eksik


def test_rapor_tam_ve_bolum_sirasi(tmp_path):
    m = _metin(tmp_path)
    sira = [m.index(f"=== {ad} ===") for ad, _ in rapor.BOLUMLER]
    assert sira == sorted(sira) and [ad for ad, _ in rapor.BOLUMLER] == [
        "VERİ", "ESNEKLİK", "KALİBRASYON", "YOL 0", "AYRIŞIM", "ÇEYREK", "YOLLAR", "TAHMİN İSABETİ", "YAN ETKİ", "HİKÂYE",
        "DEMO", "ANLATI VARSAYIMLARI", "KORUNUM"]
    yer = {1: "YOL 0", 2: "YOL 0", 3: "YOL 0", 4: "ESNEKLİK", 5: "AYRIŞIM", 6: "YOL 0", 7: "ÇEYREK", 8: "HİKÂYE"}
    for n, bolum in yer.items():
        assert m.count(f"SORU {n} · ") == 1 and f"SORU {n} · " in _bolum(m, bolum)
        satir = next(s for s in m.splitlines() if s.startswith(f"SORU {n} · "))
        assert "\n" not in satir and len(satir) > 40
    assert "denetim tuttu" in _bolum(m, "KORUNUM") and "TASLAK" not in m
    assert "kadro:" in _bolum(m, "ANLATI VARSAYIMLARI")


def test_rapor_tarih_yok(tmp_path):
    """Rapor yazıya girecek satırlarda (bütün çıktıda) sezon kodu dışında yıl basmaz; girdilerde ISO tarihler var."""
    g = sahte_rapor.girdiler()
    assert "2025-06-30" in str(g["hikaye"]) and "2023-01-01" in str(g["analiz"])
    m = _metin(tmp_path, g)
    assert rapor.yillar(m) == [] and "SS25" in m and "AW24" in m
    assert rapor.yillar("hafta 2025 ve 1999; a2019b; SS25; 12.024; 20261021") == ["2025", "1999"]


@pytest.mark.parametrize("boz", [
    lambda g: g["oyun"]["kosular"]["opt_SS25"]["korunum"].__setitem__("rpt_birebir", False),
    lambda g: g["oyun"]["kosular"]["y2_kural_AW24"].__setitem__("gecerli", False),
    lambda g: g["oyun"]["kosular"]["kal_tekduze_50_SS24"]["korunum"].__setitem__("takvim_tabani", False),
    lambda g: g["oyun"]["kosular"]["kural_AW24"]["olcutler"].__setitem__("arz_adet", 48_001.0),
    lambda g: g["oyun"]["toplamlar"]["3"]["opt"].__setitem__("gecerli", False),
    lambda g: g["oyun"]["yollar"]["0"].__setitem__("kaynak", "vaka:lumoda_x"),
    lambda g: g["analiz"]["sezonlar"]["SS25"]["huni"].__setitem__("arz", 60_001.0),
    lambda g: g["analiz"]["sezonlar"]["AW24"]["kademe"]["dagilim"].__setitem__("0.40", 1),
    lambda g: g["hikaye"]["esneklik"]["dogrulama"]["opt"].__setitem__("esit", False),
    lambda g: g["hikaye"].__setitem__("lumoda_anahtar", "baska"),
    lambda g: g["hikaye"].__setitem__("eksik_kollar", ["kahin_SS25"]),
    lambda g: g["kalibrasyon"]["kural"].__setitem__("alfa", 1.5),
], ids=["rpt_birebir", "gecersiz_yol2", "kalibrasyon_tabani", "ayni_mal_arz", "toplam_gecersiz", "yol0_yayimlanan",
        "veri_arz", "veri_kademe", "karar_ani", "hikaye_lumoda", "hikaye_eksik_kol", "kalibrasyon_secimi"])
def test_rapor_korunum_bozulunca_bos(tmp_path, capsys, boz):
    g = sahte_rapor.girdiler()
    boz(g)
    v = rapor.hazirla(**sahte_rapor.yaz(tmp_path, g))
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "korunum bozuldu" in yakalanan.err


def test_rapor_main_eksik_kosuda_bos_ve_cikis_1(tmp_path, capsys, monkeypatch):
    """Izgaranın bir koşusu yoksa kesin kip `Eksik`: stdout boş, çıkış 1; taslak bölümü atlar ve eksikleri listeler
    (çıkış 2)."""
    g = sahte_rapor.girdiler()
    del g["oyun"]["kosular"]["y3_opt_SS25"]
    k = sahte_rapor.yaz(tmp_path, g)
    with pytest.raises(rapor.Eksik, match="y3_opt_SS25"):
        rapor.hazirla(**k)
    asil = rapor.hazirla
    monkeypatch.setattr(rapor, "hazirla", lambda kucuk=False, taslak=False: asil(**k, taslak=taslak))
    assert rapor.main([]) == 1
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "y3_opt_SS25" in yakalanan.err
    assert rapor.main(["--taslak"]) == 2
    out = capsys.readouterr().out
    assert "[eksik yollar: 3]" in out and "TASLAK" in out and "=== KORUNUM ===" in out


def test_rapor_main_yil_basarsa_cikis_1(tmp_path, capsys, monkeypatch):
    g = sahte_rapor.girdiler()
    g["hikaye"]["tulumlar"]["cok"]["model_adi"] = "Salopet Tulum 2025"
    k = sahte_rapor.yaz(tmp_path, g)
    asil = rapor.hazirla
    monkeypatch.setattr(rapor, "hazirla", lambda kucuk=False, taslak=False: asil(**k, taslak=taslak))
    assert rapor.main([]) == 1
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "yıl basıyor (2025)" in yakalanan.err


def test_rapor_eski_girdiyi_reddeder(tmp_path):
    k = sahte_rapor.yaz(tmp_path)
    with pytest.raises(rapor.Eksik, match="ölçüm koduyla"):
        rapor.hazirla(**{**k, "olcum_kodu": "baska"})
    with pytest.raises(rapor.Eksik, match="analiz.json bugünkü kodla"):
        rapor.hazirla(**{**k, "analiz_kodu": "baska"})
    with pytest.raises(rapor.Eksik, match="hikaye.json bugünkü kodla"):
        rapor.hazirla(**{**k, "hikaye_kodu": "baska"})
    g = sahte_rapor.girdiler()
    g["kalibrasyon"]["olcum_kodu"] = "baska"
    with pytest.raises(rapor.Eksik, match="kalibrasyon.json"):
        rapor.hazirla(**sahte_rapor.yaz(tmp_path / "b", g))
    e = sahte_rapor.girdiler()["oyun"]["kosular"]["opt_SS25"]
    (k["onbellek"] / f"opt_SS25_{e['anahtar'][:20]}").rename(k["onbellek"] / "silindi")
    with pytest.raises(rapor.Eksik, match="önbellek: opt_SS25 "):
        rapor.hazirla(**k)


def test_rapor_demo_dosyasi_guncel_degilse_korunum(tmp_path, capsys):
    k = sahte_rapor.yaz(tmp_path)
    d = senaryolar.uret(sahte_rapor.girdiler()["oyun"])
    d["sonuclar"]["opt|yaz"]["ozet"]["olu_stok_bin"] += 1
    senaryolar.yaz(d, k["demo_yol"])
    v = rapor.hazirla(**k)
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    assert "DEMO" in capsys.readouterr().err


# --------------------------------------------------------------------------- koşullu iddialar


def test_rapor_kosullu_iddialar(tmp_path):
    """Anlatı cümleleri hesaplanan değere bağlıdır: ders tutmazsa rapor bunu açıkça basar (spec §6)."""
    g = sahte_rapor.girdiler()
    m = _metin(tmp_path / "a", g)
    hk, yo, es = (_bolum(m, b) for b in ("HİKÂYE", "YOL 0", "ESNEKLİK"))
    assert "ders karar anında görülüyor (opt Lumoda'dan önce indiriyor)" in hk and "GÖRÜLMÜYOR" not in hk
    assert "opt bu tulumu çıkışa kadar hiç indirmiyor" in hk
    assert "ikisi birlikte artıyor" in yo and "iki sezonda iyi" in yo            # sahte: tekdüze Lumoda'dan kötü
    assert "saf ε (0,164) 1'in altında" in es
    g2 = copy.deepcopy(g)
    g2["hikaye"]["ders"] |= {"cok_lumoda_oncesi": False, "cok_opt_ilk_indirim_hafta": 0, "az_opt_indirdi": True,
                              "az_opt_ilk_indirim_hafta": -1}
    g2["hikaye"]["esneklik"]["epsler"][0]["dp_oran"] = 0.3
    m2 = _metin(tmp_path / "b", g2)
    hk2 = _bolum(m2, "HİKÂYE")
    assert "DERS KARAR ANINDA GÖRÜLMÜYOR" in hk2 and "ders karar anında görülmüyor" in hk2
    assert "opt bu tulumu indirimden 1 hafta önce indiriyor" in hk2
    assert "1'in altında" not in _bolum(m2, "ESNEKLİK")


def test_rapor_soru_yonleri(tmp_path):
    """Yön sözcükleri hesaplanan değerden: tekdüze Lumoda'yı geçerse SORU 1 "kötü" der."""
    g = sahte_rapor.girdiler()
    for z in ("SS25", "AW24"):
        e = g["oyun"]["kosular"][f"tekduze_{z}"]
        e["olcutler"]["katki"] += 1_000_000
        for c, p in zip(e["ceyrek"], sahte_rapor.PAYLAR):
            c["katki"] += 1_000_000 * p
    for z, t in g["oyun"]["toplamlar"].items():
        if "tekduze" in t:
            t["tekduze"]["olcutler"]["katki"] += 2_000_000
    m = _metin(tmp_path, g)
    s1 = next(s for s in m.splitlines() if s.startswith("SORU 1 · "))
    assert s1.endswith("iki sezonda kötü")


def test_rapor_bayt_bayt_ayni(tmp_path):
    assert _metin(tmp_path / "a") == _metin(tmp_path / "b")


def test_rapor_yollar_ozeti(tmp_path):
    y = _bolum(_metin(tmp_path), "YOLLAR")
    assert "5/5 önde" in y and "yol 4: talep tohumu 20261023" in y
