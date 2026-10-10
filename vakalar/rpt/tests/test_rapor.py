"""rapor.py'nin iç fonksiyonları: biçim, basılan değerlerden fark/oran, tampon + korunum,
hakem kapısı, anlatı varsayımları. Gerçek veri ve hakem burada yok (hakem dizini boş
geçici dizin); uçtan uca koşu `veri` işaretli değildir, el ile (`rapor.py > cikti/rapor.txt`)."""

import pandas as pd
import pytest

import rapor

# --------------------------------------------------------------------------- biçim


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89"
    assert rapor.s(1234567) == "1.234.567"
    assert rapor.s(12345) == "12.345"
    assert rapor.s(0.555, 2) == "0,56"
    assert rapor.s(-3.2, 1) == "−3,2"
    assert rapor.s(float("nan")) == "—" and rapor.s(None) == "—"
    assert rapor.y(0.1234) == "%12,3"
    assert rapor.y(-0.032) == "−%3,2"
    assert rapor.y(0.5, 0) == "%50"
    assert rapor.y(None) == "—"
    assert rapor.tl(4978979.4) == "4.978.979 TL"
    assert rapor.tl(-8688769.97) == "−8.688.770 TL"
    assert rapor.mn(-8688769.97, 1) == "−8,7 milyon"
    assert rapor.t_(pd.Timestamp("2025-05-12")) == "2025-05-12" and rapor.t_(pd.NaT) == "—"


def test_eksi_sifir_basilmaz():
    # −0,0 yazıda "−0" görünmesin: yuvarlanınca sıfır olan negatif sayı işaretsiz
    assert rapor.s(-0.004, 2) == "0,00"
    assert rapor.s(-0.4) == "0"
    assert rapor.y(-0.0004) == "%0,0"


# ------------------------------------------------------- basılan değerlerden fark ve oran


def test_farklar_basilan_degerlerden():
    # basılan işlenenler 100 ve 201 → fark 101 (yuvarlanmamış fark 100,2 → 100 olurdu)
    assert rapor.fark(100.4, 200.6) == 101
    assert rapor.s(200.6) == "201" and rapor.s(100.4) == "100"
    for x in (1.005, 2.675, 38904608.50914, 0.0192 * 1000, 13.47):
        for n in (0, 1, 2):
            assert rapor.s(rapor.yuv(x, n), n) == rapor.s(x, n)
    # oran: basılan 13,5 ve 19,2
    assert rapor.bolum(13.47, 19.24, 1, 1) == pytest.approx(13.5 / 19.2)
    assert rapor.bolum(1, 0) is None
    # yüzde oran: basılan yüzdelerden (%22,4 / %39,4), ham oranlardan değil
    assert rapor.yuzde_bolum(0.22449, 0.39351) == pytest.approx(22.4 / 39.4)
    # pay (basılan adetlerden): 930 / 1.850
    assert rapor.pay(930.4, 1849.6) == pytest.approx(930 / 1850)


# ------------------------------------------------------------- tampon ve korunum


def test_tamponla_korunum_bozulursa_stdouta_yazmaz(capsys):
    def bozuk():
        print("=== HİKÂYE ===")
        raise AssertionError("korunum bozuldu: deneme")

    def saglam():
        print("=== HİKÂYE ===")

    assert rapor.tamponla(bozuk) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "korunum bozuldu: deneme" in yakalanan.err
    assert rapor.tamponla(saglam) == (0, "=== HİKÂYE ===\n")
    assert capsys.readouterr().out == ""


def test_korunum_tutarsa_sayar_bozulursa_adlari_soyler():
    assert rapor.korunum([("a", True), ("b", True)]) == 2
    with pytest.raises(AssertionError, match="korunum bozuldu") as e:
        rapor.korunum([("tutan", True), ("kovalar = giren", False), ("Σ Δkâr", False)])
    assert "kovalar = giren" in str(e.value) and "Σ Δkâr" in str(e.value) and "tutan" not in str(e.value)
    with pytest.raises(AssertionError, match="hiç denetim"):
        rapor.korunum([])


def test_korunum_bozulursa_rapor_hicbir_sey_basmaz(capsys):
    def govde():
        print("=== SONUÇ ===")
        rapor.korunum([("sayı tutmuyor", False)])

    assert rapor.tamponla(govde) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "sayı tutmuyor" in yakalanan.err


def test_fifo_denetimleri():
    ak = pd.DataFrame({"option_id": ["A", "B"], "rpt_giren": [190, 100], "rpt_cikisa_kadar": [40, 0],
                       "rpt_outlete": [130, 50], "rpt_depoda_kalan": [20, 50], "rpt_magazaya_alt": [26, 0],
                       "rpt_magazaya_ust": [40, 0], "rpt_depoda_cikista": [150, 100], "depo_cikista": [150, 300]})
    assert all(ok for _, ok in rapor.fifo_denetimleri(ak, "deneme"))
    bozuk = ak.assign(rpt_outlete=[131, 50])
    assert not all(ok for _, ok in rapor.fifo_denetimleri(bozuk, "deneme"))
    bozuk = ak.assign(rpt_magazaya_alt=[41, 0])
    assert not all(ok for _, ok in rapor.fifo_denetimleri(bozuk, "deneme"))


def test_olcut_denetimleri():
    o = pd.DataFrame({"option_id": ["A", "B"], "d_kar": [100.0, -20.0], "kurtarilan": [10.0, 3.0],
                      "kurtarilan_kalici": [7.0, 1.0], "kurtarilan_ikame": [3.0, 2.0],
                      "rpt": [500, 0], "rpt_giren": [490, 0], "rpt_bosa": [30, 0]})
    oz = {"d_kar": 80.0, "kurtarilan": 13.0, "kurtarilan_kalici": 8.0, "kurtarilan_ikame": 5.0}
    assert all(ok for _, ok in rapor.olcut_denetimleri(o, oz, "deneme"))
    assert not all(ok for _, ok in rapor.olcut_denetimleri(o, {**oz, "d_kar": 81.5}, "deneme"))
    assert not all(ok for _, ok in rapor.olcut_denetimleri(o.assign(rpt_bosa=[495, 0]), oz, "deneme"))
    assert not all(ok for _, ok in rapor.olcut_denetimleri(o.assign(kurtarilan_ikame=[2.0, 2.0]), oz, "deneme"))


# ---------------------------------------------------------------------- hakem kapısı


def test_hakem_yoksa_komutu_soyler(tmp_path, capsys):
    assert rapor.main(["--hakem", str(tmp_path)]) == 1
    yakalanan = capsys.readouterr()
    assert yakalanan.out == ""
    assert rapor.HAKEM_KOMUTU in yakalanan.err
    assert "karsilanmayan.parquet" in yakalanan.err


def test_hakem_eksik_listesi(tmp_path):
    assert rapor.hakem_eksik(tmp_path)
    for ad in rapor.HAKEM_DOSYALARI:
        (tmp_path / ad).write_text("x", encoding="utf-8")
    assert rapor.hakem_eksik(tmp_path) == []


# ----------------------------------------------------------------- anlatı varsayımları


def test_anlati_varsayimlari_basilir(capsys):
    assert rapor.ANLATI_VARSAYIMLARI == {
        "toplanti_saati": "09:15", "frr_ilk_iki_hafta_hatasi": 0.08, "frr_alim_komitesi_hatasi": 0.55,
        "frr_yayin_yili": 2001}
    rapor.anlati_bolumu(0.22449, 0.39351)
    cikti = capsys.readouterr().out
    assert "=== ANLATI VARSAYIMLARI ===" in cikti
    for anahtar in rapor.ANLATI_VARSAYIMLARI:
        assert anahtar in cikti
    assert "varsayım" in cikti
    assert "09:15" in cikti and "2001" in cikti
    assert "%8 / %55 = 0,15" in cikti                     # FRR'nin oranı
    assert "%22,4 / %39,4 = 0,57" in cikti                 # Lumoda SS25 h=2, basılan yüzdelerden
