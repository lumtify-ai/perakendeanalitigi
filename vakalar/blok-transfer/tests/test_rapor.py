"""rapor.py'nin iç fonksiyonları: biçim, hakem kapısı, anlatı varsayımları, korunum.

Fikstür (`con`) planı MA → MC OPT2 taşır (8 adet; bkz. test_senaryolar.sahte_kayip).
Gerçek veri ve hakem burada yok: kayıp tabloları sahte, hakem dizini boş geçici dizin.
"""
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

import rapor
from blok_transfer import degerlendirme, olcum
from blok_transfer.cekirdek.parametreler import Parametreler

KARAR = date(2025, 12, 29)


def sahte_kayip(sutun: str = "kayip") -> pd.DataFrame:
    """Pencere içi, evren içi: MC OPT2-1 1 · MC OPT2-3 5 · MB OPT1-3 14 → payda 20;
    kurtarılan min(2, 1) + min(2, 5) = 3. ONL satırı evren dışı, düşer."""
    return pd.DataFrame(
        [("2026-01-05", "MC", "OPT2-1", 1), ("2026-01-12", "MC", "OPT2-3", 5),
         ("2026-01-12", "MB", "OPT1-3", 14), ("2026-01-05", "ONL", "OPT2-4", 9)],
        columns=["tarih", "magaza_id", "urun_id", sutun],
    )


def _zemin(con):
    p = Parametreler()
    plan, ozet = degerlendirme.boru_hatti(con, KARAR, p, "greedy")
    evren = set(con.execute("select magaza_id from bt_magaza").df()["magaza_id"].astype(str))
    kt = {
        "basit": olcum.kayip_tablosu(sahte_kayip(), KARAR, 8, evren, "kayip"),
        "hakem": olcum.kayip_tablosu(sahte_kayip("karsilanmayan"), KARAR, 8, evren,
                                     "karsilanmayan"),
    }
    satis = olcum.verici_satisi(con, KARAR, 8)
    o = olcum.olc(olcum.tasinan(con, plan.hareketler, KARAR), kt["basit"], satis)
    return p, plan, ozet, evren, kt, o


# --------------------------------------------------------------------------- biçim

def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89"
    assert rapor.s(1234567) == "1.234.567"
    assert rapor.s(-3.2, 1) == "−3,2"
    assert rapor.y(0.1234) == "%12,3"
    assert rapor.y(-0.032) == "−%3,2"
    assert rapor.y(None) == "—"
    assert rapor.tl(4978979.4) == "4.978.979 TL"


# ---------------------------------------------------------------------- hakem kapısı

def test_hakem_yoksa_komutu_soyler(tmp_path, capsys):
    assert rapor.main(["--hakem", str(tmp_path)]) == 1
    hata = capsys.readouterr().err
    assert rapor.HAKEM_KOMUTU in hata
    assert "karsilanmayan.parquet" in hata


# ----------------------------------------------------------------- anlatı varsayımları

def test_anlati_varsayimlari_basilir(capsys):
    assert rapor.ANLATI_VARSAYIMLARI == {
        "cift_basina_dakika": 10, "haftalik_mesai_saat": 90, "aksam_cozulen_cift": 40}
    rapor.anlati_bolumu(1234)
    cikti = capsys.readouterr().out
    assert "=== ANLATI VARSAYIMLARI ===" in cikti
    for anahtar in rapor.ANLATI_VARSAYIMLARI:
        assert anahtar in cikti
    assert "varsayım" in cikti
    assert "= 205,7 saat" in cikti                        # 1.234 × 10 / 60
    assert "haftalık mesainin 2,3 katı" in cikti          # 205,7 / 90
    assert "1.234 − akşam çözülen 40 = 1.194" in cikti


# ------------------------------------------------------- basılan değerlerden fark ve oran

def test_farklar_basilan_degerlerden():
    # basılan işlenenler 100 ve 201 → fark 101 (yuvarlanmamış fark 100,2 → 100 olurdu)
    assert rapor.fark(100.4, 200.6) == 101
    assert rapor.s(200.6) == "201" and rapor.s(100.4) == "100"
    # iki ondalık: 1,005 → biçimleme ne basıyorsa yuv o
    for x in (1.005, 2.675, 38904608.50914, 0.0192 * 1000, 13.47):
        for n in (0, 1, 2):
            assert rapor.s(rapor.yuv(x, n), n) == rapor.s(x, n)
    # oran: basılan 13,5 ve 19,2 → 703,1..., ham 13,47 / 19,24 değil
    assert rapor.bolum(13.47, 19.24, 1, 1) == pytest.approx(13.5 / 19.2)
    assert rapor.bolum(1, 0) is None
    # yüzde: basılan farkın basılan paydaya oranı
    assert rapor.bolum(rapor.fark(100.4, 200.6), 100.4) == pytest.approx(1.01)


def test_tamponla_korunum_bozulursa_stdouta_yazmaz(capsys):
    def bozuk():
        print("=== VERİ ===")
        raise AssertionError("korunum bozuldu: deneme")

    def saglam():
        print("=== VERİ ===")

    assert rapor.tamponla(bozuk) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "korunum bozuldu: deneme" in yakalanan.err
    assert rapor.tamponla(saglam) == (0, "=== VERİ ===\n")
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------------- korunum

def test_korunum_tutarli_girdide_gecer(con):
    p, plan, ozet, evren, kt, o = _zemin(con)
    assert o.kurtarilan == 3 and o.payda == 20
    n = rapor.korunum({"greedy": (plan.hareketler, ozet)}, {"greedy basit": o}, evren, kt, p)
    assert n > 0


def test_korunum_ihlali_hata(con):
    p, plan, ozet, evren, kt, o = _zemin(con)
    planlar = {"greedy": (plan.hareketler, ozet)}

    # özet ↔ hareket tablosu: net kazanç tutmuyor
    bozuk = {"greedy": (plan.hareketler, {**ozet, "net_kazanc_tl": ozet["net_kazanc_tl"] + 1})}
    with pytest.raises(AssertionError, match="net_kazanc_tl"):
        rapor.korunum(bozuk, {"greedy basit": o}, evren, kt, p)

    # özet ↔ hareket tablosu: taşınan adet tutmuyor
    bozuk = {"greedy": (plan.hareketler, {**ozet, "tasinan_adet": ozet["tasinan_adet"] + 1})}
    with pytest.raises(AssertionError, match="tasinan_adet"):
        rapor.korunum(bozuk, {"greedy basit": o}, evren, kt, p)

    # kurtarılan > payda
    with pytest.raises(AssertionError, match="payda"):
        rapor.korunum(planlar, {"greedy basit": replace(o, payda=2.0)}, evren, kt, p)

    # p ∉ [0, 1]
    with pytest.raises(AssertionError, match="p_alici"):
        rapor.korunum(planlar, {"greedy basit": replace(o, p_alici=1.2)}, evren, kt, p)

    # hakem paydası Basit'in evreninin dışına taşıyor
    disari = pd.concat([kt["hakem"], pd.DataFrame(
        [("ONL", "OPT2-4", 9)], columns=["magaza_id", "urun_id", "kayip"])], ignore_index=True)
    with pytest.raises(AssertionError, match="evren"):
        rapor.korunum(planlar, {"greedy basit": o}, evren, {**kt, "hakem": disari}, p)


# ------------------------------------------------------------------ plan karşılaştırması

def _h(satirlar):
    return pd.DataFrame(satirlar, columns=["verici", "alici", "option_id", "adet", "w"])


def test_plan_farki_ve_ornek_rota():
    g = _h([("V", "A", "O1", 5, 1.0), ("V", "B", "O2", 4, 1.0), ("V", "C", "O3", 3, 1.0),
            ("W", "A", "O4", 6, 1.0)])
    m = _h([("V", "A", "O1", 5, 1.0), ("V", "A", "O2", 4, 1.0), ("V", "A", "O3", 3, 1.0),
            ("V", "A", "O5", 2, 1.0), ("X", "A", "O6", 7, 1.0)])
    f = rapor.plan_farki(g, m)
    assert (f["ortak"], f["ortak_alici_farkli"], f["yalniz_a"], f["yalniz_b"]) == (3, 2, 1, 2)
    assert not f["ayni_mal"]
    o = rapor.ornek_rota(g, m)
    assert (o["verici"], o["alici"], o["option"], o["adet"]) == ("V", "A", 4, 14)
    assert {g_ for _, _, g_ in o["satirlar"]} == {"A", "B", "C", None}
    assert rapor.rota_dagilimi(m) == {1: 1, 4: 1}
