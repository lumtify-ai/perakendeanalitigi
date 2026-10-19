"""rapor.py ve rapor_b.py: Türkçe biçim, basılan değerlerden fark/oran, tampon + korunum (bozulursa
stdout boş), bölüm başlıkları ve sırası, sekiz başlık sorusunun satırı, taslak kipi, önbellek kaydı
denetimi. Gerçek veri yok (sahte `Veri`); uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`,
iki koşu bayt bayt aynı)."""

import json

import pandas as pd
import pytest

import rapor
import rapor_b
from tests import sahte_rapor

# --------------------------------------------------------------------------- biçim


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89"
    assert rapor.s(824165) == "824.165"
    assert rapor.s(0.555, 2) == "0,56" and rapor.s(-3.2, 1) == "−3,2"
    assert rapor.s(float("nan")) == "—" and rapor.s(None) == "—"
    assert rapor.y(0.1234) == "%12,3" and rapor.y(-0.032) == "−%3,2" and rapor.y(None) == "—"
    assert rapor.yd(68.97698) == "%69,0" and rapor.yd(68.97698, 2) == "%68,98" and rapor.yd(-4.56) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.32, 2) == "−0,32"
    assert rapor.isaretli(0.001, 2) == "0,00" and rapor.isaretli(19866) == "+19.866"
    assert rapor.tl(49133131.55) == "49.133.132 TL"


def test_eksi_sifir_basilmaz():
    assert rapor.s(-0.004, 2) == "0,00" and rapor.s(-0.4) == "0" and rapor.yd(-0.04) == "%0,0"


def test_farklar_basilan_degerlerden():
    assert rapor.fark(100.4, 200.6) == 101
    assert rapor.fark(68.97698, 71.37184, 2) == pytest.approx(2.39)          # 71,37 − 68,98
    assert rapor.fark(68.97698, 71.37184, 1) == pytest.approx(2.4)           # 71,4 − 69,0
    for x in (1.005, 2.675, 38904608.50914, 13.47):
        for n in (0, 1, 2):
            assert rapor.s(rapor.yuv(x, n), n) == rapor.s(x, n)
    assert rapor.bolum(13.47, 19.24, 1, 1) == pytest.approx(13.5 / 19.2)
    assert rapor.bolum(1, 0) is None


def test_bir_ondalik_iki_ondaligin_bir_kez_yuvarlanmasi():
    # R53: yarımda sıfırdan uzağa, ondalık aritmetikle (ikili kayan nokta 0,95'i 0,9'a, 1,45'i 1,4'e indirirdi)
    for x2, x1 in ((0.95, 1.0), (-0.35, -0.4), (0.25, 0.3), (2.25, 2.3), (1.45, 1.5), (0.84, 0.8), (-0.18, -0.2),
                   (0.02, 0.0), (-0.03, 0.0)):
        assert rapor.tek_ondalik(x2) == pytest.approx(x1)
    assert rapor.isaretli(rapor.tek_ondalik(-0.03), 1) == "0,0"
    # aynı büyüklük: iki ondalıklı fark +2,25 → bir ondalık +2,3; bir ondalıklı düzeylerin farkı 71,2 − 69,0 = 2,2 olurdu
    assert rapor.fark(68.98, 71.23, 2) == pytest.approx(2.25)
    assert rapor.fark1(68.98, 71.23) == pytest.approx(2.3) and rapor.fark(68.98, 71.23, 1) == pytest.approx(2.2)
    assert rapor.fark1(76.0, 74.13) == pytest.approx(-1.9)


def test_yon_basilan_degerlerden():
    assert rapor.yon(71.372, 68.977, True, 1) == "önde"
    assert rapor.yon(17.844, 19.771, False, 2) == "önde"
    assert rapor.yon(68.981, 68.977, True, 2) == "eşit"                       # 68,98 = 68,98
    assert rapor.yon(67.6, 68.977, True, 1) == "geride"


def test_kapanan_pay():
    # (kol − lumoda) ÷ (kahin − lumoda), basılan değerlerden
    assert rapor.kapanan_pay(70.41, 68.98, 71.23, 2) == pytest.approx((70.41 - 68.98) / (71.23 - 68.98))
    assert rapor.kapanan_pay(70.0, 68.98, 68.98, 2) is None                  # kapatılacak fark yok


def test_yol_farklari():
    f = rapor.yol_farklari([65.10, 64.07, 64.74], [65.00, 63.23, 64.41], 2)
    assert f["farklar"] == pytest.approx([0.10, 0.84, 0.33])
    assert f["medyan"] == pytest.approx(0.33) and f["pozitif"] == 3 and f["negatif"] == 0 and f["n"] == 3


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


# ------------------------------------------------------------- bölümler


def test_bolum_sirasi_spec_ile_ayni():
    assert [ad for ad, _ in rapor.BOLUMLER] == [
        "VERİ", "KURAL", "KALİBRASYON", "YOL 0", "YOLLAR", "TAVAN", "SABİT TAKVİM", "TUTMA", "STRATEJİ",
        "İSABET", "BEDEN", "HİKÂYE", "DEMO", "ANLATI VARSAYIMLARI", "KORUNUM"]


def test_govde_basliklari_sirayla_basar_korunum_en_sonda(monkeypatch):
    sira = []
    sahte = [(ad, (lambda ad: lambda v, ek: (sira.append(ad), ek.append((ad, True))))(ad)) for ad, _ in rapor.BOLUMLER]
    monkeypatch.setattr(rapor, "BOLUMLER", sahte)
    kod, metin = rapor.tamponla(lambda: rapor.govde(sahte_rapor.bos_veri()))
    assert kod == 0
    basliklar = [s[4:-4] for s in metin.splitlines() if s.startswith("=== ")]
    assert basliklar == [ad for ad, _ in sahte]
    assert sira == basliklar


def test_govde_korunum_bozulursa_bos(monkeypatch, capsys):
    sahte = [(ad, lambda v, ek: ek.append(("bozuk", False))) for ad, _ in rapor.BOLUMLER]
    monkeypatch.setattr(rapor, "BOLUMLER", sahte)
    assert rapor.tamponla(lambda: rapor.govde(sahte_rapor.bos_veri())) == (1, "")
    assert "bozuk" in capsys.readouterr().err


def test_kesin_kipte_eksik_kosu_korunum_gibi_bos(monkeypatch, capsys):
    def eksik(v, ek):
        raise rapor_b.Eksik("tut_eniyi_t45")

    monkeypatch.setattr(rapor, "BOLUMLER", [("VERİ", eksik), ("KORUNUM", lambda v, ek: ek.append(("x", True)))])
    assert rapor.tamponla(lambda: rapor.govde(sahte_rapor.bos_veri())) == (1, "")
    assert "tut_eniyi_t45" in capsys.readouterr().err


def test_taslak_kipte_eksik_satiri_basilir_ve_surer(monkeypatch):
    def eksik(v, ek):
        print("  önce basılan satır")
        raise rapor_b.Eksik("tut_eniyi_t45", "belirsizlik")

    monkeypatch.setattr(rapor, "BOLUMLER", [("VERİ", eksik), ("KORUNUM", lambda v, ek: ek.append(("x", True)))])
    v = sahte_rapor.bos_veri(taslak=True, eksik=["tut_eniyi_t45: oyun.json'da yok"])
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0
    assert "önce basılan satır" in metin and "[eksik: tut_eniyi_t45, belirsizlik]" in metin
    assert "=== KORUNUM ===" in metin and "TASLAK" in metin and "tut_eniyi_t45: oyun.json'da yok" in metin


def test_main_girdi_yoksa_stdout_bos(monkeypatch, capsys):
    def yok(**_):
        raise RuntimeError("pay_kahin: önbellekte yok")

    monkeypatch.setattr(rapor_b, "hazirla", yok)
    assert rapor.main([]) == 1
    y = capsys.readouterr()
    assert y.out == "" and "önbellekte yok" in y.err


def test_main_taslak_cikis_kodu_2(monkeypatch, capsys):
    monkeypatch.setattr(rapor_b, "hazirla", lambda **_: sahte_rapor.bos_veri(taslak=True, eksik=["x eksik"]))
    monkeypatch.setattr(rapor, "BOLUMLER", [("KORUNUM", lambda v, ek: ek.append(("x", True)))])
    assert rapor.main(["--taslak"]) == 2
    assert "TASLAK" in capsys.readouterr().out


# ------------------------------------------------------------- uçtan uca (sahte, eksiksiz Veri)


def test_tam_rapor_sekiz_soru_ve_korunum(capsys):
    v = sahte_rapor.tam_veri()
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0, capsys.readouterr().err
    basliklar = [s[4:-4] for s in metin.splitlines() if s.startswith("=== ")]
    assert basliklar == [ad for ad, _ in rapor.BOLUMLER]
    for n in range(1, 9):
        satirlar = [s for s in metin.splitlines() if s.startswith(f"SORU {n} · ")]
        assert len(satirlar) == 1, (n, satirlar)
    assert "[eksik" not in metin and "TASLAK" not in metin
    soru3 = next(s_ for s_ in metin.splitlines() if s_.startswith("SORU 3 · "))
    assert "biçim" in soru3 and "tutma" in soru3                   # tavan eşleşik tutmayla ayrışır (R43)
    assert "R29" not in metin
    assert "tavanıyla koşuldu" not in metin and "Ruling R46" in metin
    assert "genel (bütün Collection) 67" in metin and "5/5 yolda önde" in metin
    assert "denetim tuttu" in metin
    # iki kez aynı çıktı (süre basılmaz)
    assert rapor.tamponla(lambda: rapor.govde(sahte_rapor.tam_veri()))[1] == metin


def test_tam_rapor_sayilari_turkce(capsys):
    metin = rapor.tamponla(lambda: rapor.govde(sahte_rapor.tam_veri()))[1]
    from perakende_analitik import sayi_denetimi as sd

    bicimsiz = [m.group(1) for m in sd.SAYI.finditer(metin) if not sd.gecerli(m.group(1))]
    # tarih (2025-03-17) ve kimlikler (MDL0553, M029) ayrık rakam dizileridir; nokta ondalık yok
    assert bicimsiz == [], bicimsiz[:20]


@pytest.mark.parametrize("bozma", ["takvimli_farkli", "sabit_rpt_farkli", "demo_dosyasi_farkli",
                                   "satis_talebi_asar", "yol0_anahtar_farkli", "hikaye_kaynagi_farkli",
                                   "eslesik_kaynagi_farkli", "eslesik_mal_farkli",
                                   "yol_girdisi_yol0dan"])
def test_tam_rapor_korunum_bozulunca_bos(bozma, capsys):
    v = sahte_rapor.tam_veri()
    sahte_rapor.boz(v, bozma)
    assert rapor.tamponla(lambda: rapor.govde(v)) == (1, "")
    assert "korunum bozuldu" in capsys.readouterr().err


def test_kahin_bagimsizligi_tutmazsa_olculemedi(capsys):
    v = sahte_rapor.tam_veri()
    v.bagimsizlik["pay_kahin"] = False
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0
    assert "ölçülemedi" in metin
    assert not [s for s in metin.splitlines() if s.startswith("SORU 2 · ") and "kahin %" in s]


def test_anlati_varsayimlari_basilir(capsys):
    rapor.anlati_bolumu(None, [])
    cikti = capsys.readouterr().out
    for anahtar, deger in rapor.ANLATI_VARSAYIMLARI.items():
        assert anahtar in cikti and str(deger) in cikti


# ------------------------------------------------------------- önbellek kaydı (rapor_b)


def _meta(**ek):
    m = {"ad": "k", "parametreler": {}, "turler": {}, "talep_tohumu": None, "operasyon_tohumu": 2026, "olcek": "tam",
         "gun_sayisi": None, "kod": "kod1", "veri": ["perakende.duckdb", 1, 2], "surumler": {"numpy": "2"}}
    m.update(ek)
    m["anahtar"] = rapor_b.motor._ozet({a: m[a] for a in rapor_b.ANAHTAR_ALANLARI if a in m})
    return m


def test_kayit_sorunlari():
    m = _meta()
    guncel = {"kod": "kod1", "veri": ["perakende.duckdb", 1, 2], "surumler": {"numpy": "2"}}
    assert rapor_b.kayit_sorunlari(m, m["anahtar"], guncel) == []
    assert rapor_b.kayit_sorunlari(m, "baska", guncel) == ["anahtar ölçülmüş kayıttakinden farklı"]
    assert rapor_b.kayit_sorunlari(m, m["anahtar"], {**guncel, "kod": "kod2"}) == ["kod bugünkünden farklı"]
    bozuk = {**m, "parametreler": {"x": 1}}
    assert "meta alanlarının özeti anahtarı vermiyor" in rapor_b.kayit_sorunlari(bozuk, m["anahtar"], guncel)


def test_onbellek_eksik_kosuyu_kosmaz_silmez_takma_adi_izler(tmp_path):
    m = _meta()
    guncel = {a: m[a] for a in ("kod", "veri", "surumler")}
    ob = rapor_b.Onbellek({"k": {"anahtar": m["anahtar"]}, "k2": {"anahtar": m["anahtar"], "ayni": "k"}},
                          dizin=tmp_path, guncel=guncel)
    with pytest.raises(RuntimeError, match="kayıtta"):
        ob.ac("yok")
    with pytest.raises(RuntimeError, match="önbellekte yok"):
        ob.ac("k")
    d = tmp_path / f"k_{m['anahtar'][:20]}"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({**m, "tablolar": ["satis"], "kayitlar": ["ilk_dagitim"]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="dosya eksik"):
        ob.ac("k")
    assert d.exists()                                                  # motor.kos gibi silmez
    (d / "tablo_satis.parquet").write_bytes(b"")
    (d / "gercek.parquet").write_bytes(b"")
    pd.DataFrame({"gun": [1], "arg0": [0], "indis": [2], "deger": [3]}).to_parquet(d / "kayit_ilk_dagitim.parquet")
    k = ob.ac("k")
    assert k.meta["anahtar"] == m["anahtar"] and list(k.kayitlar["ilk_dagitim"]["deger"]) == [3]
    assert ob.ac("k2").dizin == d and ob.acilan == {"k", "k2"}


def test_kol_karar_ozeti():
    kayit = pd.DataFrame({
        "gun": [5] * 6, "arg0": [0, 0, 0, 1, 7, 7], "indis": [0, 1, 2, -1, 0, 3], "deger": [2, 0, 3, 0, 4, 1],
        "kol": [True, True, True, True, False, False], "U": [6, 6, 6, 4, -1, -1], "toplam": [5, 5, 5, 4, -1, -1],
        "t": [0.0] * 4 + [float("nan")] * 2, "duzey": [-1] * 6, "tavanda": [1, 1, 1, 0, -1, -1],
        "geri_dusus": [False] * 6})
    oz = rapor_b.kol_karar_ozeti(kayit).set_index("arg0")
    assert list(oz.index) == [0, 1]                                    # Lumoda'ya devredilen 7 yok
    assert oz.loc[0, "U"] == 6 and oz.loc[0, "giden"] == 5 and oz.loc[0, "aday"] == 3 and oz.loc[0, "tavanda"] == 1
    assert oz.loc[1, "aday"] == 0 and oz.loc[1, "giden"] == 0           # adaysız karar: nöbetçi satır


# ------------------------------------------------------------- R50: SORU aritmetiği ve etiketler


def _bul(v, ad, deger, kalan=None):
    o = v.oyun["kosular"][ad]["olcutler"]
    o["bulunabilirlik"] = deger
    if kalan is not None:
        o["sezon_sonu_kalan_yuzde"] = kalan


def _soru(metin: str, n: int) -> str:
    return next(x for x in metin.splitlines() if x.startswith(f"SORU {n} · "))


def test_soru3_toplam_bicim_arti_tutma():
    v = sahte_rapor.tam_veri()
    _bul(v, "pay_benzer_tavansiz", 69.51, 19.65)       # basılan 69,5 / 19,6
    _bul(v, "es_benzer", 70.64, 18.22)                 # 70,6 / 18,2
    _bul(v, "pay_benzer_tavanli", 70.46, 18.12)        # 70,5 / 18,1
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0
    s3 = _soru(metin, 3)
    # iki ondalıkla toplanır; bir ondalıklı biçim iki ondalıklının bir kez yuvarlanmışı (R53): −0,18 → −0,2,
    # bir ondalıklı düzeylerin farkı (70,5 − 70,6 = −0,1) değil
    assert "bulunabilirlik toplam +0,95 = biçim −0,18 + tutma +1,13 (bir ondalıkla +1,0 / −0,2 / +1,1)" in s3
    assert "kalan toplam −1,53 = biçim −0,10 + tutma −1,43 (bir ondalıkla −1,5 / −0,1 / −1,4)" in s3
    assert "tavanlı − eşleşik (biçim): ilk dağıtım" in metin and "bulun. −0,18" in metin


def test_soru8_dogrudan_arti_tepki():
    v = sahte_rapor.tam_veri()
    k = v.oyun["kosular"]
    _bul(v, "lumoda", 68.98)
    k["lumoda_takvimli"]["olcutler"] = dict(k["lumoda"]["olcutler"])
    _bul(v, "pay_tahmin_tavansiz", 70.41)
    _bul(v, "sabit_tahmin", 70.41)
    _bul(v, "pay_kahin", 71.23)
    _bul(v, "sabit_kahin", 70.94)
    kod, metin = rapor.tamponla(lambda: rapor.govde(v))
    assert kod == 0
    s8 = _soru(metin, 8)
    assert "tahmin toplam +1,43 = doğrudan +1,43 + tepki 0,00 (bir ondalıkla +1,4 / +1,4 / 0,0; doğrudan payı %100)" in s8
    # +2,25 → +2,3 ve +1,96 → +2,0 (bir ondalıklı düzeylerden +2,2 ve +1,9 değil); doğrudan payı tablodakiyle aynı hesap
    assert "kahin toplam +2,25 = doğrudan +1,96 + tepki +0,29 (bir ondalıkla +2,3 / +2,0 / +0,3; doğrudan payı %87)" in s8
    assert "toplam +2,25 = doğrudan +1,96 + tepki +0,29 (doğrudan payı %87)" in metin
    assert "+ +" not in s8


def test_soru6_en_dusuk_tutma_kosularindan_ve_etiket_cozumden():
    v = sahte_rapor.tam_veri()
    v.oyun["kosular"]["tut_lumoda_t45_hiz"]["olcutler"]["beden_kayip_payi"] = 20.0
    v.oyun["kosular"]["pay_esit"]["olcutler"]["beden_kayip_payi"] = 60.0
    s6 = _soru(rapor.tamponla(lambda: rapor.govde(v))[1], 6)
    assert "en düşük tut_lumoda_t45_hiz %20,0 (depoda tutan)" in s6
    assert "en yüksek pay_esit %60,0 (her şeyi gönderen)" in s6
    assert rapor.depoda_tutar({"cozum": {"tutma": 0.0, "tavan": True}})
    assert rapor.depoda_tutar({"cozum": {"tutma": None, "tavan": False}})
    assert not rapor.depoda_tutar({"cozum": {"tutma": 0.0, "tavan": False}})


def test_soru5_sinyal_yalniz_esikle():
    kal = {"gamma_bulunabilirlik_araligi_puan": 0.0316, "gamma_esik_puan": 0.3, "belirsizlik_spearman": 0.1067}
    assert "ölçünün sinyali zayıf" in rapor.sinyal_metni(kal) and "0,03 puan < eşik 0,3" in rapor.sinyal_metni(kal)
    assert "zayıf" not in rapor.sinyal_metni({**kal, "gamma_bulunabilirlik_araligi_puan": 0.5})
    assert rapor.sinyal_metni({"belirsizlik_spearman": 0.1}) == "Spearman 0,100"


def test_yol_bir_ondalik_medyan_iki_ondaligin_yuvarlamasi():
    v = sahte_rapor.tam_veri()
    for p, (a, c) in enumerate([(69.51, 68.98), (69.75, 69.01), (69.46, 68.75), (69.31, 68.71), (69.81, 68.95)]):
        y_ = v.yollar["yollar"][str(p)]["kosular"]
        y_["benzer"]["olcutler"] = {**y_["benzer"]["olcutler"], "bulunabilirlik": a}
        y_["lumoda"]["olcutler"] = {**y_["lumoda"]["olcutler"], "bulunabilirlik": c}
    metin = rapor.tamponla(lambda: rapor.govde(v))[1]
    satir = next(x for x in metin.splitlines() if x.startswith("  benzer − lumoda: +0,5 ·"))
    assert "| medyan +0,7 ·" in satir                 # iki ondalıklı medyan +0,71 → +0,7 (+0,8 değil)
    assert "medyan fark +0,71" in metin


# ------------------------------------------------------------- R53: bir büyüklük, bir değer


def test_soru2_fark_ve_kapanan_pay_iki_ondalikli_farktan():
    v = sahte_rapor.tam_veri()
    _bul(v, "lumoda", 68.98)
    v.oyun["kosular"]["lumoda_takvimli"]["olcutler"] = dict(v.oyun["kosular"]["lumoda"]["olcutler"])
    _bul(v, "pay_benzer_tavansiz", 69.51)
    _bul(v, "pay_kahin", 71.23)
    s2 = _soru(rapor.tamponla(lambda: rapor.govde(v))[1], 2)
    assert "kahin %71,2 (+2,3 puan)" in s2                      # +2,25'in yuvarlanmışı
    assert "benzer %69,5 (+0,5 puan)" in s2
    assert "kapanan: bulunabilirlik %24" in s2                  # 0,53 ÷ 2,25 (bir ondalıkla 0,5 ÷ 2,2 = %23 olurdu)


def test_soru4_bir_ondalik_tablodaki_iki_ondaligin_yuvarlamasi():
    v = sahte_rapor.tam_veri()
    _bul(v, "tut_lumoda_t00", 68.98, 19.77)
    _bul(v, "tut_lumoda_t30", 70.85, 17.77)
    metin = rapor.tamponla(lambda: rapor.govde(v))[1]
    assert "t %30 − t %0: bulunabilirlik +1,87 · kalan −2,00" in metin
    s4 = _soru(metin, 4)
    assert "Lumoda payı × lumoda: t %0 → %30 +1,9 puan bulunabilirlik, −2,0 puan kalan" in s4   # 70,8 − 69,0 = 1,8 değil
