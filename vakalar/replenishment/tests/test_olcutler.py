"""`replenishment.olcutler` (asgari, Ruling R22): bulunabilirlik, toplama maliyeti,
pencere sonu mağaza stoğu. Elle kurulmuş tablolarla; koşuyla bağlantısı
`tests/test_oyun.py`'de."""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from replenishment import olcutler
from replenishment.sabitler import ACIK_TL_ADET, KOLI_TL

BAS, BIT = date(2024, 9, 2), date(2024, 9, 15)


def _gercek():
    return pd.DataFrame({
        "tarih": pd.to_datetime(["2024-09-01", "2024-09-02", "2024-09-02", "2024-09-03", "2024-09-10",
                                 "2024-09-15", "2024-09-15", "2024-09-16"]),
        "magaza_id": ["M1", "M1", "M2", "M1", "M2", "ONL", "M1", "M1"],
        "urun_id": ["A", "A", "A", "B", "B", "A", "A", "A"],
        "talep": [3, 2, 1, 4, 1, 5, 2, 1],
        "kendi_satis": [0, 2, 0, 1, 0, 0, 2, 0],
    })


def test_bulunabilirlik_fiziksel_pencere_talepli_gun():
    # pencerede fiziksel talepli hücre-gün: 09-02 M1, 09-02 M2, 09-03 M1, 09-10 M2, 09-15 M1 = 5;
    # kendi satışı olan: 09-02 M1, 09-03 M1, 09-15 M1 = 3 (ONL ve pencere dışı sayılmaz)
    assert olcutler.bulunabilirlik(_gercek(), BAS, BIT) == pytest.approx(60.0)


def test_bulunabilirlik_talep_sifir_satir_sayilmaz():
    g = _gercek()
    g.loc[1, "talep"] = 0           # gerçek tablo talepsiz satır içermez; içerse de payda dışı
    g.loc[1, "kendi_satis"] = 0
    assert olcutler.bulunabilirlik(g, BAS, BIT) == pytest.approx(50.0)


def test_bulunabilirlik_bos_pencere():
    assert olcutler.bulunabilirlik(_gercek(), date(2025, 1, 1), date(2025, 1, 7)) == 0.0


def test_toplama_maliyeti():
    hafta = pd.DataFrame({"gun": [1, 8], "acik_adet": [100.0, 50.0], "koli_sayisi": [3.0, 7.0]})
    assert olcutler.toplama_maliyeti(hafta) == 150 * ACIK_TL_ADET + 10 * KOLI_TL


def test_toplama_maliyeti_bos_hafta():
    assert olcutler.toplama_maliyeti(pd.DataFrame(columns=["gun", "tarih"])) == 0.0


def test_magaza_stok_son_son_fotograf_fiziksel():
    stok = pd.DataFrame({
        "tarih": pd.to_datetime(["2024-09-02", "2024-09-09", "2024-09-09", "2024-09-09", "2024-09-16"]),
        "magaza_id": ["M1", "M1", "M2", "ONL", "M1"],
        "adet": [10, 4, 6, 100, 99],
    })
    # BIT 09-15 (pazar): son fotoğraf 09-09; ONL sayılmaz; 09-16 pencereden sonra
    assert olcutler.magaza_stok_son(stok, BIT) == 10.0
    assert olcutler.magaza_stok_son(stok, date(2024, 9, 16)) == 99.0
    with pytest.raises(ValueError):
        olcutler.magaza_stok_son(stok, date(2024, 9, 1))


def test_temel_olcutler_kosudan_okur():
    tablolar = {
        "gercek": _gercek(),
        "stok": pd.DataFrame({"tarih": pd.to_datetime(["2024-09-09"]), "magaza_id": ["M1"],
                              "urun_id": ["A"], "adet": [7]}),
    }
    kayit = pd.DataFrame({
        "gun": [1, 1, 1, 1, 1], "tarih": pd.to_datetime(["2024-09-02"] * 5),
        "kalem": ["pazartesi", "acik_adet", "koli_sayisi", "gonderilen_adet", "koli_adet"],
        "hucre": [-1] * 5, "magaza_id": [""] * 5, "urun_id": [""] * 5, "deger": [1.0, 20.0, 2.0, 34.0, 14.0],
    })
    kosu = SimpleNamespace(tablo=lambda ad, sutunlar=None, urunler=None: tablolar[ad][list(sutunlar)],
                           kayitlar={"replenishment": kayit})
    o = olcutler.temel_olcutler(kosu, BAS, BIT)
    assert o == {
        "bulunabilirlik": pytest.approx(60.0),
        "toplama_maliyeti_tl": 20 * ACIK_TL_ADET + 2 * KOLI_TL,
        "magaza_stok_son": 7.0,
        "acik_adet": 20.0, "koli_sayisi": 2.0, "koli_adet": 14.0, "gonderilen_adet": 34.0,
    }


# ---------------------------------------------------------------------------
# hesapla: elle kurulmuş küçük dünya ve koşu (Görev 10)
# ---------------------------------------------------------------------------
#
# Dünya: mağazalar M1, M2, M3 (fiziksel) ve ONL; option A (Kadın Harf, 5 beden,
# Collection), option B (Standart, tek beden, Basic). Hücreler: M1/M2/M3 × A'nın 5
# bedeni, M1 × B, ONL × A-M. Pencere 2025-09-01 … 09-14 (iki pazartesi).
#
# Akış (kolun hücreleri M1 A-S ve M2 A-M):
#   M1 A-S  09-01 fotoğraf 3; kol sevki 09-01 çıkış, 09-02 varış 4; satış 09-03 2, 09-05 3,
#           09-09 1 → FIFO: başlangıç 3 (09-03'te 2, 09-05'te 1), kol partisi 09-05'te 2
#           (3 gün), 09-09'da 1 (7 gün); 1 adet duruyor
#   M2 A-M  09-01 fotoğraf 1; kol sevki 09-08 çıkış, 09-09 varış 2; 09-10'da M1'e 1 adet
#           transfer (başlangıç partisini tüketir) → kol partisinin 2'si duruyor
#   M1 A-L  09-04'te ilk dağıtımla 1 adet (kolun değil)

BAS2, BIT2 = date(2025, 9, 1), date(2025, 9, 14)
T0 = pd.Timestamp("2025-08-25")          # dünyanın günü 0


def _dunya():
    magazalar = pd.DataFrame({
        "magaza_id": ["M1", "M2", "M3", "ONL"], "tip": ["Cadde", "AVM", "AVM", "Online"],
        "acilis_tarihi": pd.to_datetime(["2015-01-01"] * 4), "kapanis_tarihi": pd.to_datetime([None] * 4),
    })
    optionlar = pd.DataFrame({
        "option_id": ["A", "B"], "line": ["Collection", "Basic"], "ust_kategori": ["Üst", "Aksesuar"],
        "beden_seti": ["Kadın Harf", "Standart"], "lansman_gun": [0, 0], "cikis_gun": [1000, 1000],
    })
    bedenler = ["XS", "S", "M", "L", "XL"]
    urunler = pd.DataFrame({"urun_id": [f"A-{b}" for b in bedenler] + ["B-STD"],
                            "beden_sira": [1, 2, 3, 4, 5, 1]})
    hm, ho, hs, onl = [], [], [], []
    for m in (0, 1, 2):
        for s in range(5):
            hm.append(m), ho.append(0), hs.append(s), onl.append(False)
    hm.append(0), ho.append(1), hs.append(5), onl.append(False)          # M1 × B-STD
    hm.append(3), ho.append(0), hs.append(2), onl.append(True)           # ONL × A-M
    return SimpleNamespace(
        magazalar=magazalar, optionlar=optionlar, urunler=urunler,
        takvim=pd.DataFrame({"tarih": pd.date_range(T0, periods=60)}),
        hucre_magaza=np.array(hm), hucre_option=np.array(ho), hucre_sku=np.array(hs),
        hucre_online=np.array(onl), hucre_outlet_akisi=np.zeros(len(hm), dtype=bool),
        sku_option=np.array([0, 0, 0, 0, 0, 1]),
        sku_beden_payi=np.array([0.1, 0.22, 0.32, 0.24, 0.12, 1.0]),
    )


def _df(satirlar, sutunlar, tarihler=("tarih",)):
    df = pd.DataFrame(satirlar, columns=sutunlar)
    for s in tarihler:
        df[s] = pd.to_datetime(df[s])
    return df


def _tablolar():
    G = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan", "ikameye_giden", "kalici_kayip"]
    gercek = _df([
        ("2025-08-31", "M1", "A-S", 2, 2, 0, 0, 0),          # pencere dışı
        ("2025-09-02", "ONL", "A-M", 5, 5, 0, 0, 0),         # online
        ("2025-09-03", "M1", "A-S", 3, 2, 1, 1, 0),
        ("2025-09-05", "M1", "A-S", 3, 3, 0, 0, 0),
        ("2025-09-05", "M1", "A-M", 2, 0, 2, 0, 2),          # depoda A-M o gün 0
        ("2025-09-09", "M1", "A-S", 1, 1, 0, 0, 0),
        ("2025-09-10", "M2", "A-L", 1, 0, 1, 1, 0),
    ], G)
    stok = _df([
        ("2025-09-01", "M1", "A-S", 3), ("2025-09-01", "M1", "B-STD", 5),
        ("2025-09-01", "M2", "A-XS", 1), ("2025-09-01", "M2", "A-S", 1), ("2025-09-01", "M2", "A-M", 1),
        ("2025-09-01", "M2", "A-L", 1), ("2025-09-01", "ONL", "A-M", 10),
        ("2025-09-08", "M1", "A-S", 2), ("2025-09-08", "M1", "A-L", 1), ("2025-09-08", "M1", "A-M", 0),
        ("2025-09-08", "M1", "B-STD", 5),
        ("2025-09-08", "M2", "A-XS", 1), ("2025-09-08", "M2", "A-S", 1), ("2025-09-08", "M2", "A-M", 1),
        ("2025-09-08", "M2", "A-L", 1), ("2025-09-08", "ONL", "A-M", 9),
        ("2025-09-15", "M1", "A-S", 99),                     # pencereden sonra
    ], ["tarih", "magaza_id", "urun_id", "adet"])
    satis = _df([
        ("2025-08-26", "M1", "A-S", 2), ("2025-08-27", "M1", "A-M", 2),     # pencere öncesi (beden payı)
        ("2025-09-02", "ONL", "A-M", 5),
        ("2025-09-03", "M1", "A-S", 2), ("2025-09-05", "M1", "A-S", 3), ("2025-09-09", "M1", "A-S", 1),
        ("2025-09-15", "M1", "A-S", 4),
    ], ["tarih", "magaza_id", "urun_id", "adet"])
    sevkiyat = _df([
        ("2025-09-01", "2025-09-02", "DEPO", "M1", "A-S", 4, "replenishment"),
        ("2025-09-03", "2025-09-04", "DEPO", "M1", "A-L", 1, "ilk_dagitim"),
        ("2025-09-08", "2025-09-09", "DEPO", "M2", "A-M", 2, "replenishment"),
        ("2025-09-10", "2025-09-11", "M2", "M1", "A-M", 1, "elle_transfer"),
        ("2025-09-15", "2025-09-16", "DEPO", "M1", "A-S", 9, "replenishment"),
    ], ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"], ("tarih", "varis_tarihi"))
    depo = [(d, u, 0 if (u == "A-M" and d == pd.Timestamp("2025-09-05")) else 50)
            for d in pd.date_range("2025-09-01", "2025-09-14")
            for u in ["A-XS", "A-S", "A-M", "A-L", "A-XL", "B-STD"]]
    depo_stok = _df(depo, ["tarih", "urun_id", "adet"])
    return {"gercek": gercek, "stok": stok, "satis": satis, "sevkiyat": sevkiyat, "depo_stok": depo_stok}


def _kol_kaydi():
    kalemler = []
    for tarih, d, ozet in [
        ("2025-09-01", 7, {"istek_adet": 10, "maske_disi_adet": 2, "gonderilen_adet": 4, "karsilanmayan_adet": 4,
                           "acik_adet": 4, "koli_sayisi": 0, "koli_adet": 0, "tavan": 4, "uzl_kapali_adet": 70,
                           "uzl_acik_adet": 20, "defter_kapali_adet": 70, "defter_acik_adet": 16}),
        ("2025-09-08", 14, {"istek_adet": 5, "maske_disi_adet": 0, "gonderilen_adet": 2, "karsilanmayan_adet": 3,
                            "acik_adet": 2, "koli_sayisi": 0, "koli_adet": 0, "tavan": 4, "uzl_kapali_adet": 63,
                            "uzl_acik_adet": 30, "defter_kapali_adet": 63, "defter_acik_adet": 28}),
    ]:
        kalemler.append((d, tarih, "pazartesi", -1, "", "", 1.0))
        kalemler += [(d, tarih, k, -1, "", "", float(v)) for k, v in ozet.items()]
    kalemler += [(7, "2025-09-01", "istek", 1, "M1", "A-S", 4.0), (14, "2025-09-08", "istek", 7, "M2", "A-M", 2.0)]
    return _df(kalemler, ["gun", "tarih", "kalem", "hucre", "magaza_id", "urun_id", "deger"])


def _kosu(kayit=None, tablolar=None):
    t = tablolar or _tablolar()
    return SimpleNamespace(
        tablo=lambda ad, sutunlar=None, urunler=None: t[ad][list(sutunlar)] if sutunlar is not None else t[ad],
        kayitlar={"replenishment": _kol_kaydi() if kayit is None else kayit})


def test_hesapla_musteri():
    o = olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)
    # fiziksel pencere: 5 talepli hücre-gün, 3'ünde kendi satış; talep 10, kendi 6, karşılanmayan 4
    assert o["bulunabilirlik"] == pytest.approx(60.0)
    assert o["talep_adet"] == 10 and o["satis_adet"] == 6
    assert o["kayip_orani"] == pytest.approx(40.0)
    assert o["ikame_payi"] == pytest.approx(50.0)            # 2 / 4
    assert o["kalici_kayip_orani"] == pytest.approx(20.0)    # 2 / 10
    assert o["depo_bos_kayip_pay_yuzde"] == pytest.approx(50.0)   # A-M 09-05: 2 / 4


def test_hesapla_toplama_ve_doluluk():
    o = olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)
    assert o["gonderilen_adet"] == 6 and o["acik_adet"] == 6 and o["koli_sayisi"] == 0
    assert o["toplama_maliyeti_tl"] == 6 * ACIK_TL_ADET
    assert o["acik_doluluk_ort"] == pytest.approx(75.0) and o["acik_doluluk_tepe"] == pytest.approx(100.0)
    assert o["tavan_bagli_hafta_yuzde"] == pytest.approx(50.0)
    assert o["kesilen_pay_yuzde"] == pytest.approx(100 * 7 / 13)   # (4 + 3) / ((10 − 2) + 5)


def test_hesapla_kirik_cift_paydalariyla():
    o = olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)
    # son fotoğraf 09-08: M1×A stoklu ama çekirdek M = 0 → kırık; M2×A stoklu, çekirdek tam;
    # M3×A boş; M1×B tek beden (evren dışı); ONL dışarıda
    assert (o["stoklu_cift"], o["bos_cift"], o["kirik_cift"]) == (2, 1, 1)
    assert o["kirik_cift_pay_yuzde"] == pytest.approx(50.0)
    assert o["magaza_stok_son"] == 12                         # M1 2+1+5, M2 4


def test_hesapla_beden_sapmasi():
    o = olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)
    # M1: pay (geçmiş satış S 2, M 2) .5/.5, stok S 2, L 1 → TVD .5; M2: geçmiş yok → zincir
    # eğrisi (.1 .22 .32 .24 .12), stok 1/1/1/1/0 → TVD .19; ortalama 34,5
    assert o["beden_sapmasi"] == pytest.approx(34.5)


def test_hesapla_fifo_ve_str():
    o = olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)
    assert o["satilan_gonderilen"] == 3 and o["satilmayan_gonderilen"] == 3
    assert o["satisa_donme_gun"] == pytest.approx(13 / 3)
    # STR: penceredeki fiziksel satış 6 / (09-01 fiziksel stok 12 + fiziksel varış 8)
    assert o["str"] == pytest.approx(30.0)
    assert all(isinstance(v, float) for v in o.values())


def test_fifo_eslestir_parcalari():
    giris = pd.DataFrame({"hucre": [5, 5, 9], "gun": [0, 2, 1], "adet": [3, 4, 2], "tur": ["b", "kol", "kol"]})
    cikis = pd.DataFrame({"hucre": [5, 5, 5, 9], "gun": [3, 5, 9, 4], "adet": [2, 3, 1, 5],
                          "tur": ["satis"] * 4})
    p = olcutler.fifo_eslestir(giris, cikis)
    kol5 = p[(p["hucre"] == 5) & (p["giris_tur"] == "kol")]
    assert list(zip(kol5["cikis_gun"], kol5["adet"])) == [(5, 2), (9, 1), (-1, 1)]
    # hücre 9: 2 giriş, 5 çıkış → fazla çıkış eşlenmez
    assert p.loc[p["hucre"] == 9, "adet"].sum() == 2 and (p.loc[p["hucre"] == 9, "cikis_gun"] == 4).all()


def test_hesapla_lumoda_kaydi_sevkiyattan():
    """Kol kaydı olmayan koşu (eşdeğerlik): gönderim sevkiyattan, hepsi açık adet; istek ham kayıttan."""
    kayit = pd.DataFrame({"gun": [7, 7, 14], "indis": [1, 3, 7], "deger": [5, 1, 3]})
    o = olcutler.hesapla(_kosu(kayit), _dunya(), BAS2, BIT2, tavan_ref=4)
    assert o["gonderilen_adet"] == 6 and o["acik_adet"] == 6 and o["koli_sayisi"] == 0
    assert o["kesilen_pay_yuzde"] == pytest.approx(100 * 3 / 9)
    assert o["acik_doluluk_ort"] == pytest.approx(75.0)      # tavan ∞ → tavan_ref paydası
    assert o["tavan_bagli_hafta_yuzde"] == 0.0
    assert olcutler.hesapla(_kosu(kayit), _dunya(), BAS2, BIT2)["acik_doluluk_ort"] == 0.0


def test_line_kirilimi():
    lk = olcutler.line_kirilimi(_kosu(), _dunya(), BAS2, BIT2).set_index("line")
    assert lk.loc["Collection", "talep_adet"] == 10 and lk.loc["Basic", "talep_adet"] == 0
    assert lk.loc["Collection", "bulunabilirlik"] == pytest.approx(60.0)
    assert lk.loc["Basic", "magaza_stok_son"] == 5 and lk.loc["Collection", "magaza_stok_son"] == 7
    assert lk.loc["Collection", "gonderilen_adet"] == 6


def test_denetle():
    olcutler.denetle(_kosu())
    bozuk = _kol_kaydi()
    bozuk.loc[(bozuk["kalem"] == "defter_acik_adet") & (bozuk["gun"] == 7), "deger"] = 17.0
    with pytest.raises(AssertionError):
        olcutler.denetle(_kosu(bozuk))
    t = _tablolar()
    t["gercek"].loc[2, "kendi_satis"] = 4                    # talep 3
    with pytest.raises(AssertionError):
        olcutler.denetle(_kosu(tablolar=t))


def test_fifo_negatif_sure_sayilir():
    """Akışlar fotoğrafla tutarsızsa (satış partinin varışından önce) birim sayılır, süre 0'a kırpılır."""
    t = _tablolar()
    # M1 A-S: 09-01 fotoğrafı 0 ve kol partisinin (4 adet) varışı 09-06. Ondan önceki satışlar
    # (09-03'te 2, 09-05'te 3) FIFO'da bu partiyle eşlenir ama partiden önce düşer: partinin 4
    # adedi negatif süreli (fazla 1 satış hiçbir partiyle eşlenmez)
    t["stok"].loc[(t["stok"]["tarih"] == "2025-09-01") & (t["stok"]["urun_id"] == "A-S"), "adet"] = 0
    t["sevkiyat"].loc[0, "varis_tarihi"] = pd.Timestamp("2025-09-06")
    o = olcutler.hesapla(_kosu(tablolar=t), _dunya(), BAS2, BIT2)
    assert o["fifo_negatif_adet"] == 4
    assert o["satisa_donme_gun"] == 0.0
    assert olcutler.hesapla(_kosu(), _dunya(), BAS2, BIT2)["fifo_negatif_adet"] == 0


def test_denetle_defter_kalemi_eksikse_hata():
    eksik = _kol_kaydi()
    eksik = eksik[~eksik["kalem"].isin(["uzl_kapali_adet", "defter_acik_adet"])]
    with pytest.raises(AssertionError, match="kalem eksik"):
        olcutler.denetle(_kosu(eksik))
    # meta'ya göre defter tutan kol (kısıtsız Lumoda değil): gonderilen_adet de yoksa yine hata
    yalin = _kol_kaydi()
    yalin = yalin[yalin["kalem"].isin(["pazartesi", "istek_adet", "maske_disi_adet", "istek"])]
    kosu = _kosu(yalin)
    kosu.meta = {"politikalar": {"replenishment": {"parametreler": {"kol": "kural", "ayar": {"kisitsiz": True}}}}}
    with pytest.raises(AssertionError, match="kalem eksik"):
        olcutler.denetle(kosu)
    kosu.meta = {"politikalar": {"replenishment": {"parametreler": {"kol": "lumoda", "ayar": {"kisitsiz": True}}}}}
    olcutler.denetle(kosu)          # kısıtsız Lumoda defter tutmaz
