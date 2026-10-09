import ast
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from conftest import sentetik_gunluk
from perakende_analitik.carpanlar import Carpanlar

import rpt
from rpt import egri, kaynak, miktar

NOTR = Carpanlar()


def _duz(n=10):
    return egri.Egri(paylar={(1,): np.full(n, 1.0 / n)}, grup=("dalga",), yontem="x", hedef="x", sezonlar=())


def test_sabitler_v4_ile_ayni():
    """Karar modülleri üreteci içe aktaramaz; Lumoda'nın sabitleri burada yerel kopyadır."""
    from perakende_veri.v4 import plan, sabitler

    assert miktar.ADIM == sabitler.YUVARLAMA_ADET
    assert miktar.IADE_ORANI == sabitler.IADE_ORANI_MAGAZA
    assert miktar.RPT_MIKTAR_ORANI == sabitler.RPT_MIKTAR_ORANI
    assert miktar.RPT_STR_ESIGI == sabitler.RPT_STR_ESIGI
    assert (miktar.RPT_ILK_HAFTA, miktar.RPT_SON_HAFTA) == (sabitler.RPT_ILK_HAFTA, sabitler.RPT_SON_HAFTA)
    q = np.array([0, 1, 149.5, 150, 299, 300, 301, 1039.99, 1040, 1041, 2500.2])
    for moq in (100, 300, 500):
        assert [miktar.moq_yuvarla(x, moq) for x in q] == plan.moq_yuvarla(q, np.full(len(q), moq)).tolist()


def test_banu_ve_frr():
    assert miktar.banu(2080, 300) == 1040
    assert miktar.banu(400, 300) == 300
    # (1 − 0,06) · 1000 / 0,25 − 2000 = 1760
    assert miktar.frr(1000, 0.25, 2000, 300) == 1760
    assert miktar.frr(1000, 0.5, 2000, 300) == 0         # tahmin ilk alımın altında
    assert miktar.frr(560, 0.25, 2000, 300) == 0          # 105 < MOQ/2
    assert miktar.frr(600, 0.25, 2000, 300) == 300        # 256 ≥ MOQ/2 → en az MOQ


def test_newsvendor_belirsizlik_yokken_eksigi_alir():
    # Düz eğri (10 hafta), h=2'de D=200 ⇒ sezon 1000; L=2 ⇒ geliş h=4.
    # Geliş öncesi talep 200, elde 100 ⇒ gelişte 0 stok; gelişten sonra tam
    # fiyat talep 600. İndirim dönemi yok (çıkış eğrisi = indirim eğrisi).
    e = _duz()
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q"] == 600
    assert nv["beklenen_tf"] == pytest.approx(600, abs=1)
    assert nv["beklenen_kar"] == pytest.approx(600 * 60, rel=1e-3)


def test_newsvendor_moq_kapisi():
    e = _duz()
    # Eksik yalnız 100 adet, MOQ 300: tam fiyattan MOQ/2 satamaz ⇒ sipariş yok
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=700, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q_serbest"] == 100
    assert nv["q"] == 0
    # Eksik 200: MOQ'nun beklenen kârı 200·100 − 300·40 = 8.000 > 0 ve 200 ≥ 150 ⇒ MOQ
    nv = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=600, p=100, c=40, p_ind=30, mu=0.0, sigma=1e-6, moq=300)
    assert nv["q"] == 300


def test_newsvendor_belirsizlikte_kritik_orana_gore():
    e = _duz()
    ucuz = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=10, p_ind=0, mu=0, sigma=0.4, moq=10)
    pahali = miktar.newsvendor(200, 2, 2, 10, e, e, 1, ip=100, p=100, c=90, p_ind=0, mu=0, sigma=0.4, moq=10)
    assert ucuz["q"] > 600 > pahali["q"]


def test_kar_egrisi_elle():
    Q = np.array([0, 10, 20])
    tf, ind, kar = miktar.kar_egrisi(Q, np.array([5.0]), np.array([12.0]), np.array([4.0]),
                                     ip=5, p=10, p_ind=5, c=4)
    # C0 = 0 ⇒ tam fiyat ihtiyacı 12, indirim 4
    assert tf.tolist() == [0, 10, 12]
    assert ind.tolist() == [0, 0, 4]
    assert kar.tolist() == [0, 100 - 40, 120 + 20 - 80]


# ------------------------------------------------------------ indirim beklentisi


def _fiyat_baglantisi(oyun_orani=0.4):
    """SS24 (geçmiş, 2 option, 1. dalga) ve AW24 (oyun) option'ları; haftalık `fiyat`."""
    con = duckdb.connect()
    sezon = pd.DataFrame({"sezon_kodu": ["SS24", "AW24"], "dalga": [1, 1],
                          "lansman_tarihi": pd.to_datetime(["2024-02-12", "2024-08-19"]),
                          "indirim_baslangic": pd.to_datetime(["2024-03-04", "2024-09-09"]),
                          "cikis_tarihi": pd.to_datetime(["2024-03-18", "2024-09-23"])})
    urun = pd.DataFrame({"urun_id": ["A-S", "A-M", "B-S", "G-S"], "option_id": ["A", "A", "B", "G"],
                         "sezon_kodu": ["SS24", "SS24", "SS24", "AW24"], "dalga": 1,
                         "line": "Collection",
                         "lansman_tarihi": pd.to_datetime(["2024-02-12"] * 3 + ["2024-08-19"]),
                         "cikis_tarihi": pd.to_datetime(["2024-03-18"] * 3 + ["2024-09-23"])})
    satir = []
    for oid, lan, oranlar in (("A", "2024-02-12", (0, 0, 0, 0.3, 0.5)),
                              ("B", "2024-02-12", (0, 0, 0.2, 0.3, 0.3)),
                              ("G", "2024-08-19", (0, 0, 0, oyun_orani, oyun_orani))):
        for w, r in enumerate(oranlar):
            for hat in ("normal", "online"):
                satir.append((pd.Timestamp(lan) + pd.Timedelta(days=7 * w), oid, hat,
                              r if hat == "normal" else 0.9))
    fiyat = pd.DataFrame(satir, columns=["hafta_baslangic", "option_id", "hat", "indirim_orani"])
    for ad, df in (("sezon", sezon), ("urun", urun), ("fiyat", fiyat)):
        con.register(ad, df)
    return con


def test_indirim_beklentisi_gecmisten():
    """Geçmiş sezonların (dalga, hafta) ortalaması; oyun sezonunun fiyatları değişse de aynı."""
    a = miktar.indirim_beklentisi(_fiyat_baglantisi(0.4), "AW24")
    b = miktar.indirim_beklentisi(_fiyat_baglantisi(0.7), "AW24")
    assert a == b
    assert a == pytest.approx({(1, 0): 0.0, (1, 1): 0.0, (1, 2): 0.1, (1, 3): 0.3, (1, 4): 0.4})


def test_indirim_fiyatlari_egriyle_agirlikli():
    opt = pd.DataFrame({"option_id": ["G"], "dalga": [1], "liste_fiyati": [100.0],
                        "lansman_tarihi": [pd.Timestamp("2024-08-19")],
                        "indirim_baslangic": [pd.Timestamp("2024-09-02")],
                        "cikis_tarihi": [pd.Timestamp("2024-09-16")]})
    beklenti = {(1, 0): 0.0, (1, 1): 0.0, (1, 2): 0.2, (1, 3): 0.5}
    # indirim haftaları 2 ve 3; eğri payları 0,3 ve 0,1 ⇒ (0,3·0,2 + 0,1·0,5) / 0,4
    e = egri.Egri(paylar={(1,): np.array([0.3, 0.3, 0.3, 0.1])}, grup=("dalga",), yontem="d",
                  hedef="cikis", sezonlar=())
    p = miktar.indirim_fiyatlari(opt, beklenti, e)
    assert p["G"] == pytest.approx(100 * (1 - (0.3 * 0.2 + 0.1 * 0.5) / 0.4))
    # eğrisiz: eşit ağırlık; bulunmayan hafta en yakın haftayla
    assert miktar.indirim_fiyatlari(opt, {(1, 0): 0.0, (1, 2): 0.3}, None)["G"] == pytest.approx(70.0)


# ------------------------------------------------------------ kalibrasyon

LAN = {"SS24": pd.Timestamp("2024-02-12"), "AW24": pd.Timestamp("2024-08-19")}


@pytest.fixture(scope="module")
def gecmis_ve_oyun():
    """SS24'te üç option (geçmiş; 14 hafta, indirim 12.), AW24'te bir option (oyun)."""
    g, opt, _ = sentetik_gunluk([("P1", "SS24", LAN["SS24"], 14, 1), ("P2", "SS24", LAN["SS24"], 14, 1),
                                 ("P3", "SS24", LAN["SS24"], 14, 1), ("G1", "AW24", LAN["AW24"], 8, 1)],
                                magaza_sayisi=30)
    return g, opt


def _kalibre(g, opt):
    return miktar.kalibrasyon(g, opt, "AW24", lambda t: NOTR, haftalar=(2, 3, 4))


def test_kalibrasyon_gecmisten(gecmis_ve_oyun):
    g, opt = gecmis_ve_oyun
    b = _kalibre(g, opt)
    assert b.sezonlar == ("SS24",)
    assert set(b.mu) == {2, 3, 4} and all(b.n[h] == 3 for h in b.mu)
    assert all(np.isfinite(b.mu[h]) and b.sigma[h] > 0 for h in b.mu)
    assert b.al(2.4) == (b.mu[2], b.sigma[2]) and b.al(9) == (b.mu[4], b.sigma[4])


def test_kalibrasyon_gelecegi_gormez(gecmis_ve_oyun):
    """Oyunun ilk lansman sabahından sonraki satırlar (oyun sezonu dahil) μ, σ'yı değiştirmez."""
    g, opt = gecmis_ve_oyun
    a = _kalibre(g, opt)
    bozuk = g.copy()
    sonra = bozuk["tarih"] >= LAN["AW24"]
    bozuk.loc[sonra, "brut_satis"] = bozuk.loc[sonra, "brut_satis"] * 7 + 2
    bozuk.loc[sonra, "durum"] = "bos"
    b = _kalibre(bozuk, opt)
    assert a == b
    # test boş geçmiyor: SS24'ün son haftası (oyundan önce) hedefi değiştirir
    once = g.copy()
    son = (once["tarih"] >= LAN["SS24"] + pd.Timedelta(days=70)) & (once["tarih"] < LAN["AW24"])
    once.loc[son, "brut_satis"] += 3
    assert _kalibre(once, opt).mu != a.mu


def test_kalibrasyon_gercek_kaybi_okumaz(gecmis_ve_oyun):
    """Gerçek talep / hakem sütunları bozulsa da μ, σ aynı; modüller gizli gerçeği anmaz."""
    g, opt = gecmis_ve_oyun
    a = _kalibre(g, opt)
    zehir = g.assign(gercek_talep=g["gercek_talep"] * 9 + 1, kayip=999.0, karsilanmayan=777,
                     talep=5.0, kalici_kayip=3)
    assert _kalibre(zehir, opt) == a
    assert _kalibre(g.drop(columns="gercek_talep"), opt) == a


GIZLI_ADLAR = ("hakem", "karsilanmayan", "kalici_kayip", "ikameye_giden", "kayip_satis",
               "gercek_talep", "gizli")


@pytest.mark.parametrize("modul", ["miktar", "aday"])
def test_gizli_gercek_anilmaz_ast(modul):
    """Modül hakemi, üreteci, motoru içe aktarmaz; gizli gerçeğin sütun / tablo adlarını
    (dizge, ad ya da öznitelik) kod içinde anmaz (açıklama metinleri hariç)."""
    yol = Path(rpt.__file__).parent / f"{modul}.py"
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    belge = set()
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.ClassDef, ast.Module)) and d.body:
            ilk = d.body[0]
            if isinstance(ilk, ast.Expr) and isinstance(ilk.value, ast.Constant):
                belge.add(id(ilk.value))
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar = [a.name for a in d.names]
        elif isinstance(d, ast.ImportFrom):
            adlar = [d.module or ""] + [a.name for a in d.names]
        else:
            adlar = []
        assert not [a for a in adlar if "hakem" in a or a.startswith("perakende_veri") or a == "motor"]
        metin = None
        if isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in belge:
            metin = d.value
        elif isinstance(d, ast.Attribute):
            metin = d.attr
        elif isinstance(d, ast.Name):
            metin = d.id
        if metin is not None:
            assert not any(y in metin for y in GIZLI_ADLAR), f"{modul}: {metin!r}"


# ------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_indirim_beklentisi_gercek_veri():
    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok")
    with kaynak.baglan() as con:
        b = miktar.indirim_beklentisi(con, "SS25")
    assert {d for d, _ in b} == {1, 2, 3}
    assert all(0.0 <= v <= 0.7 for v in b.values())
    # 1. dalga: ilk haftalar tam fiyat, indirim döneminde (20. haftadan) en az %30
    assert b[(1, 0)] < 0.01 and b[(1, 3)] < 0.01
    assert all(b[(1, w)] >= 0.29 for w in range(20, 26) if (1, w) in b)
