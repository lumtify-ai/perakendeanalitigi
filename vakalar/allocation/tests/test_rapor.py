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
    assert "kime" in soru3 and "tutma" in soru3                    # tavan eşleşik tutmayla ayrışır (R43)
    assert "R29" not in metin
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
                                   "eslesik_kaynagi_farkli", "eslesik_mal_farkli"])
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
