"""rapor.py: Türkçe biçim, basılan değerlerden fark, tek yuvarlama, tampon + korunum (bozulursa stdout
boş, çıkış 1), bölüm sırası (spec §5), yedi başlık sorusunun satırı ve bölümü, eski/eksik girdi, taslak
kipi. Gerçek veri yok (sahte `sonuc`); uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`, iki koşu
bayt bayt aynı)."""

import json
import re

import pytest

import rapor
import senaryolar
from kumeleme import oyun
from tests import sahte_sonuc

# --------------------------------------------------------------------------- biçim


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89"
    assert rapor.s(824165) == "824.165"
    assert rapor.s(0.555, 2) == "0,56" and rapor.s(-3.2, 1) == "−3,2"
    assert rapor.s(float("nan")) == "—" and rapor.s(None) == "—"
    assert rapor.y(0.1234) == "%12,3" and rapor.y(-0.032) == "−%3,2" and rapor.y(None) == "—"
    assert rapor.yd(68.97698) == "%69,0" and rapor.yd(-4.56) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.32, 2) == "−0,32"
    assert rapor.isaretli(0.001, 2) == "0,00"
    assert rapor.tl(116405702.4) == "116.405.702 TL (116,4 milyon TL)"
    assert rapor.oran(55, 67) == "55/67 (%82,1)" and rapor.pay(0.0371) == "%3,7"


def test_eksi_sifir_basilmaz():
    assert rapor.s(-0.0004, 3) == "0,000" and rapor.s(-0.4) == "0" and rapor.yd(-0.04) == "%0,0"


def test_yuvarlama_yarim_yukari_ve_basilan_deger():
    for x in (1.005, 2.675, 0.8505, 13.47, 0.6415):
        for n in (0, 1, 2, 3):
            assert rapor.s(rapor.yuv(x, n), n) == rapor.s(x, n)
    assert rapor.fark(0.6415, 0.8034, 3) == pytest.approx(0.161)            # 0,803 − 0,642
    assert rapor.bolum(13.47, 19.24, 1, 1) == pytest.approx(13.5 / 19.2) and rapor.bolum(1, 0) is None


def test_bir_ondalik_iki_ondaligin_bir_kez_yuvarlanmasi():
    for x2, x1 in ((0.95, 1.0), (-0.35, -0.4), (0.25, 0.3), (1.45, 1.5), (0.02, 0.0)):
        assert rapor.tek_ondalik(x2) == pytest.approx(x1)
    # aynı büyüklük: iki ondalıklı fark 11,94 → 11,9; bir ondalıklı düzeylerin farkı 82,1 − 70,1 = 12,0 olurdu
    a, b = 100 * 47 / 67, 100 * 55 / 67
    assert rapor.fark1(a, b) == pytest.approx(11.9) and rapor.fark(a, b, 1) == pytest.approx(12.0)
    assert rapor.puan(47 / 67, 55 / 67) == "+11,9 puan"


def test_stirling_ve_bilimsel():
    assert rapor.stirling2(4, 2) == 7 and rapor.stirling2(5, 3) == 25 and rapor.stirling2(6, 6) == 1
    assert rapor.bilimsel(rapor.stirling2(67, 5)) == "5,6 × 10⁴⁴"
    # üs rakamları sayı denetimine girmez (üst simge Unicode ondalık rakam değil)
    from perakende_analitik import sayi_denetimi
    assert sayi_denetimi.rapor_sayilari("yaklaşık 5,6 × 10⁴⁴") == {"5.6"}


# ------------------------------------------------------------- tampon ve korunum


def test_tamponla_korunum_bozulursa_stdouta_yazmaz(capsys):
    def bozuk():
        print("=== VERİ ===")
        rapor.korunum([("sayı tutmuyor", False)])

    assert rapor.tamponla(bozuk) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "sayı tutmuyor" in yakalanan.err
    assert rapor.tamponla(lambda: print("=== VERİ ===")) == (0, "=== VERİ ===\n")


def test_korunum_sayar_ve_adlari_soyler():
    assert rapor.korunum([("a", True), ("b", True)]) == 2
    with pytest.raises(AssertionError, match="korunum bozuldu") as e:
        rapor.korunum([("tutan", True), ("Σ grup = toplam", False)])
    assert "Σ grup = toplam" in str(e.value) and "tutan" not in str(e.value)
    with pytest.raises(AssertionError, match="hiç denetim"):
        rapor.korunum([])


# ------------------------------------------------------------- sahte girdi


def _girdi(tmp_path, sonuc=None, *, kumeler=True, demo=True):
    sonuc = sahte_sonuc.sonuc() if sonuc is None else sonuc
    tmp_path.mkdir(parents=True, exist_ok=True)
    yollar = {"sonuc_yol": tmp_path / "sonuc.json", "kumeler_yol": tmp_path / "kumeler.json",
              "demo_yol": tmp_path / "demo.json"}
    yollar["sonuc_yol"].write_text(oyun.metin(sonuc), encoding="utf-8")
    if kumeler:
        yollar["kumeler_yol"].write_text(oyun.metin(oyun.kumeler_kaydi(sonuc)), encoding="utf-8")
    if demo:
        senaryolar.yaz(senaryolar.uret(sonuc), yollar["demo_yol"])
    return sonuc, yollar


def _veri(tmp_path, sonuc=None, taslak=False, **kw):
    sonuc, yollar = _girdi(tmp_path, sonuc, **kw)
    return rapor.hazirla(**yollar, taslak=taslak, kod=sonuc["kod"], veri_izi=sonuc["veri_izi"])


def _metin(tmp_path, **kw) -> str:
    kod, metin = rapor.tamponla(lambda: rapor.govde(_veri(tmp_path, **kw)))
    assert kod == 0, metin
    return metin


def _bolumler(metin: str) -> dict[str, str]:
    parca = re.split(r"^=== (.+) ===$", metin, flags=re.M)
    return dict(zip(parca[1::2], parca[2::2]))


# ------------------------------------------------------------- bölümler ve sorular


def test_bolum_sirasi_spec_ile_ayni():
    assert [ad for ad, _ in rapor.BOLUMLER] == [
        "VERİ", "KURAL", "ÖZELLİKLER", "ML", "HAKEM", "KARARLILIK", "YENİ MAĞAZA", "ABLASYON", "HİKÂYE", "DEMO",
        "ANLATI VARSAYIMLARI", "KORUNUM"]


def test_govde_bolumleri_sirayla_basar(tmp_path):
    metin = _metin(tmp_path)
    assert [s[4:-4] for s in metin.splitlines() if s.startswith("=== ")] == [ad for ad, _ in rapor.BOLUMLER]
    assert "denetim tuttu" in _bolumler(metin)["KORUNUM"]


def test_yedi_soru_birer_kez_kendi_bolumunde(tmp_path):
    bolum = _bolumler(_metin(tmp_path))
    yer = {1: "HAKEM", 2: "HAKEM", 3: "ABLASYON", 4: "ABLASYON", 5: "KARARLILIK", 6: "YENİ MAĞAZA", 7: "ML"}
    for n, ad in yer.items():
        satirlar = [s for b in bolum.values() for s in b.splitlines() if s.startswith(f"SORU {n} · ")]
        assert len(satirlar) == 1, n
        assert satirlar[0] in bolum[ad].splitlines(), (n, ad)


def test_sorular_basilan_degerlerden(tmp_path):
    s = sahte_sonuc.sonuc()
    bolum = _bolumler(_metin(tmp_path))
    g = s["hakem"]["gruplar"]
    soru1 = next(x for x in bolum["HAKEM"].splitlines() if x.startswith("SORU 1"))
    assert f"K1 bölge ARI {rapor.s(g['k1']['ari'], 3)}" in soru1 and f"ARI {rapor.s(g['k2']['ari'], 3)}" in soru1
    soru6 = next(x for x in bolum["YENİ MAĞAZA"].splitlines() if x.startswith("SORU 6"))
    assert "5-NN 7/8 (%87,5)" in soru6 and "1'i doğru (M09)" in soru6


def test_iki_kosu_bayt_bayt_ayni(tmp_path):
    assert _metin(tmp_path / "a") == _metin(tmp_path / "b")


def test_sure_ve_takvim_disi_satir_basilmaz(tmp_path):
    metin = _metin(tmp_path)
    assert not re.search(r"\b(sn|saniye|dakika)\b", metin)


# ------------------------------------------------------------- korunum, eski ve eksik girdi


def test_korunum_bozulursa_bos_cikti(tmp_path, capsys):
    s = sahte_sonuc.sonuc()
    s["hakem"]["gruplar"]["k1"]["capraz"]["degerler"][0][0] += 1        # çapraz toplamı tutmaz
    kod, metin = rapor.tamponla(lambda: rapor.govde(_veri(tmp_path, s)))
    assert (kod, metin) == (1, "")
    assert "HAKEM: k1 çapraz toplamı" in capsys.readouterr().err


def test_kumeler_json_farkliysa_korunum_bozulur(tmp_path, capsys):
    s, yollar = _girdi(tmp_path)
    k = json.loads(yollar["kumeler_yol"].read_text(encoding="utf-8"))
    k["ml"]["etiket"]["M01"] = 2
    yollar["kumeler_yol"].write_text(json.dumps(k), encoding="utf-8")
    v = rapor.hazirla(**yollar, kod=s["kod"], veri_izi=s["veri_izi"])
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    assert "kumeler.json" in capsys.readouterr().err


def test_demo_dosyasi_farkliysa_bos_cikti(tmp_path):
    s, yollar = _girdi(tmp_path)
    d = json.loads(yollar["demo_yol"].read_text(encoding="utf-8"))
    d["sonuclar"]["S1|4"]["ozet"]["hakem_ari"] = 0.0
    yollar["demo_yol"].write_text(json.dumps(d), encoding="utf-8")
    v = rapor.hazirla(**yollar, kod=s["kod"], veri_izi=s["veri_izi"])
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")


def test_eski_kod_ya_da_veri_kesin_kipte_hata(tmp_path):
    s, yollar = _girdi(tmp_path)
    with pytest.raises(RuntimeError, match="paket koduyla"):
        rapor.hazirla(**yollar, kod="baska", veri_izi=s["veri_izi"])
    with pytest.raises(RuntimeError, match="v4 dosyasıyla"):
        rapor.hazirla(**yollar, kod=s["kod"], veri_izi=["x", 0, 0])
    with pytest.raises(RuntimeError, match="yok.json yok"):
        rapor.hazirla(sonuc_yol=tmp_path / "yok.json", kumeler_yol=yollar["kumeler_yol"],
                      demo_yol=yollar["demo_yol"], kod=s["kod"], veri_izi=s["veri_izi"])


def test_eksik_kumeler_ve_demo_kesin_kipte_hata(tmp_path):
    s, yollar = _girdi(tmp_path, kumeler=False, demo=False)
    with pytest.raises(RuntimeError, match="kumeler.json yok"):
        rapor.hazirla(**yollar, kod=s["kod"], veri_izi=s["veri_izi"])


def test_taslak_eskiyi_basar_ve_listeler(tmp_path):
    s, yollar = _girdi(tmp_path, demo=False)
    v = rapor.hazirla(**yollar, taslak=True, kod="baska", veri_izi=s["veri_izi"])
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0
    assert "TASLAK: 2 eksik ya da eski girdi" in metin and "[eksik: demo dosyası güncel değil]" in metin


def test_main_bos_stdout_ve_cikis_kodlari(tmp_path, monkeypatch, capsys):
    v = _veri(tmp_path)
    v2 = _veri(tmp_path / "t", taslak=True)
    monkeypatch.setattr(rapor, "hazirla", lambda taslak=False: (_ for _ in ()).throw(RuntimeError("girdi yok")))
    assert rapor.main([]) == 1
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "girdi yok" in yakalanan.err

    monkeypatch.setattr(rapor, "hazirla", lambda taslak=False: v)
    assert rapor.main([]) == 0
    assert capsys.readouterr().out.startswith("Mağaza Kümeleme — v4 raporu.")

    monkeypatch.setattr(rapor, "hazirla", lambda taslak=False: v2)
    assert rapor.main(["--taslak"]) == 2
