"""`replenishment.oyun` ve `replenishment.yollar`.

Izgara (R28) saf testlerle; koşucu, hazırlık ve ölçüm KÜÇÜK dünyada kısa koşularla
(pencere ve ufuk daraltılır, `oyun.Ortam`). Kalibrasyon koşucusunun (`kalibrasyon_kosucusu`:
`KuralKol` + motor + ölçütler) bağlantısı da burada: pencere test için 2023 sonbaharına
çekilir (`Ayar.pencere`; kalibrasyonun kendisi hep KAL_* verir, `tests/test_kalibrasyon.py`)."""

import json
import math
from datetime import date

import pandas as pd
import pytest

from replenishment import oyun, politika, tahmin, yollar
from replenishment.dagitim import KoliKurali
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.kalibrasyon import Kalibrasyon
from replenishment.politika import KOLLAR, Ayar
from replenishment.sabitler import ALIM_DUZEYLERI, OYUN_BAS, OYUN_BIT, TALEP_TOHUM_TABANI

PENCERE = (date(2023, 9, 4), date(2023, 10, 1))     # dört pazartesi
SON = date(2023, 10, 2)                             # koşunun son günü (fotoğraf 10-02 sabahı)


def _kal(tavan=25826):
    return Kalibrasyon(
        gs={"sabit": GuvenlikStoku("sabit", 4.0), "ros": GuvenlikStoku("ros", 6.0),
            "istatistik": GuvenlikStoku("istatistik")},
        koli={"A": KoliKurali("A", alfa=0.4, beta=3), "B": KoliKurali("B", gamma=0.5),
              "C": KoliKurali("C", alfa=0.4, beta=3, gamma=0.5)},
        secilen_aile="sabit", secilen_koli="A", tavan=tavan, hedef_bulunabilirlik=67.1,
        tablo=pd.DataFrame())


# ---------------------------------------------------------------- ızgara (saf)


def test_izgara_adlari_tekil():
    adlar = [s.ad for b in oyun.IZGARA.values() for s in b]
    yol_adlari = [s.ad for p in range(1, oyun.YOL_SAYISI) for _, s in oyun.yol_listesi(p)]
    assert len(adlar) == len(set(adlar))
    assert not set(adlar) & set(yol_adlari) and len(yol_adlari) == len(set(yol_adlari))
    for a in adlar + yol_adlari:
        assert oyun.motor._AD_DESENI.match(a), a


def test_izgara_butcesi():
    assert oyun.kosu_sayisi() <= 75
    assert oyun.kosu_sayisi() == 1 + 27 + 17 + 3 + 4 * 5


def test_izgara_r28():
    g = oyun.IZGARA
    assert [s.ad for s in g["esdegerlik"]] == ["lumoda_kisitsiz"]
    demo = g["demo"]
    assert len(demo) == 27
    assert {s.alim for s in demo} == set(ALIM_DUZEYLERI)
    assert {s.kol for s in demo} == {"kural", "tahmin_taban", "tahmin"}
    assert sum(s.kisitsiz for s in demo) == 9
    assert {s.tavan_kat for s in demo if not s.kisitsiz} == {1.6, 0.6}
    tarama = {s.ad: s for s in g["tarama"]}
    assert len(tarama) == 17
    assert tarama["kural_ref"] == oyun.Kosum("kural_ref", "kural")
    assert {s.oncelik for s in tarama.values() if s.alim == 0.4} == {"cover", "ihtiyac", "esit"}
    assert {s.koli for s in tarama.values()} >= {"yok", "B", "C"}
    assert {s.gs for s in tarama.values()} >= {"ros", "istatistik"}
    assert {s.tavan_kat for s in tarama.values()} >= {0.4, math.inf}
    assert {s.kol for s in tarama.values()} == set(KOLLAR)
    assert {s.alim for s in g["tarama_kit"]} == {0.2}


def test_yol_listesi():
    y0 = dict(oyun.yol_listesi(0))
    assert [s.ad for s in y0.values()] == list(oyun.YOL_KOLLARI)
    y2 = oyun.yol_listesi(2)
    assert [a for a, _ in y2] == list(oyun.YOL_KOLLARI)
    for a, s in y2:
        assert s.ad == f"y2_{a}" and s.yol == 2
        assert s.__dict__ | {"ad": a, "yol": 0} == y0[a].__dict__
    assert oyun.talep_tohumu(0) is None and oyun.talep_tohumu(3) == TALEP_TOHUM_TABANI + 3


def test_ayar_kur_referans_ve_sapmalar():
    kal = _kal()
    ref = oyun.ayar_kur(oyun.Kosum("kural_ref", "kural"), kal)
    assert ref == Ayar(koli=KoliKurali("A", alfa=0.4, beta=3), tavan=25826.0, gs=GuvenlikStoku("sabit", 4.0),
                       oncelik="cover", pencere=(OYUN_BAS, OYUN_BIT))
    assert oyun.ayar_kur(oyun.Kosum("x", "kural", tavan_kat=1.6), kal).tavan == math.floor(25826 * 1.6)
    assert oyun.ayar_kur(oyun.Kosum("x", "kural", tavan_kat=math.inf), kal).tavan == math.inf
    k = oyun.ayar_kur(oyun.Kosum("x", "kural", kisitsiz=True, tavan_kat=math.inf), kal)
    assert k.kisitsiz and k.tavan == math.inf and k.kural().ad == "kisitsiz" and k.gs.aile == "sabit"
    assert oyun.ayar_kur(oyun.Kosum("x", "kural", koli="yok"), kal).kural().ad == "yok"
    assert oyun.ayar_kur(oyun.Kosum("x", "kural", koli="C"), kal).koli == KoliKurali("C", alfa=0.4, beta=3, gamma=0.5)
    assert oyun.ayar_kur(oyun.Kosum("x", "kural", gs="ros"), kal).gs == GuvenlikStoku("ros", 6.0)
    with pytest.raises(ValueError):
        oyun.Kosum("x", "bilinmeyen")


def test_kitlik_karari():
    def e(b):
        return {"olcutler": {"bulunabilirlik": b, "depo_bos_kayip_pay_yuzde": 1.0, "kesilen_pay_yuzde": 2.0}}

    k = {"kural_ref": e(70.0), "kural_oncelik_ihtiyac": e(69.0), "kural_oncelik_esit": e(70.5),
         "kural_a040_oncelik_cover": e(60.0), "kural_a040_oncelik_ihtiyac": e(60.2),
         "kural_a040_oncelik_esit": e(60.1)}
    karar = oyun.kitlik_karari(k)
    assert karar["a100"]["aralik"] == pytest.approx(1.5)
    assert karar["a040"]["aralik"] == pytest.approx(0.2)
    assert karar["baglayici"] is False
    k["kural_a040_oncelik_esit"] = e(61.0)
    assert oyun.kitlik_karari(k)["baglayici"] is True


def test_yollar_ozetle():
    def y(b_kural, b_tahmin, m_kural, m_tahmin):
        o = {olc: 1.0 for olc in yollar.OZET_OLCUTLERI}
        return {"kosular": {"kural_ref": {"olcutler": o | {"bulunabilirlik": b_kural, "toplama_maliyeti_tl": m_kural}},
                            "tahmin_ref": {"olcutler": o | {"bulunabilirlik": b_tahmin,
                                                            "toplama_maliyeti_tl": m_tahmin}}}}

    oz = yollar.ozetle({"0": y(70, 72, 100, 90), "1": y(71, 70, 100, 110), "2": y(69, 75, 100, 95)})
    assert oz["kollar"]["tahmin_ref"]["bulunabilirlik"] == {"min": 70.0, "medyan": 72.0, "max": 75.0, "n": 3}
    assert oz["onde"]["tahmin_ref|kural_ref"] == {"yol": 3, "bulunabilirlik": 2, "toplama_maliyeti_tl": 2,
                                                  "magaza_stok_son": 0, "kayip_orani": 0}
    assert oz["onde"]["tahmin_taban_ref|kural_ref"]["yol"] == 0


def test_bilinmeyen_alt_komut():
    with pytest.raises(SystemExit):
        oyun.main(["bilinmeyen"])


# ---------------------------------------------------------------- kalibrasyon koşucusu (KÜÇÜK)


def _n(son):
    from replenishment import motor

    w = motor.dunya("kucuk")
    return int((pd.Timestamp(son) - pd.Timestamp(w.takvim["tarih"].iloc[0])).days) + 1


@pytest.fixture(scope="module")
def kos_fn():
    return oyun.kalibrasyon_kosucusu(olcek="kucuk", onbellek=None, gun_sayisi=_n(SON), ilerleme=None)


@pytest.mark.parametrize("ayar", [
    Ayar(kisitsiz=True, pencere=PENCERE),
    Ayar(koli=KoliKurali("A", alfa=0.6, beta=2), tavan=40.0, pencere=PENCERE),
], ids=["kisitsiz", "kisitli"])
def test_kalibrasyon_kosucusu_olcer(kos_fn, ayar):
    o = kos_fn("t_kal", ayar)
    assert set(o) >= {"bulunabilirlik", "toplama_maliyeti_tl", "magaza_stok_son", "acik_adet", "koli_sayisi"}
    assert 0 < o["bulunabilirlik"] <= 100
    assert o["magaza_stok_son"] > 0
    assert o["gonderilen_adet"] > 0
    assert o["toplama_maliyeti_tl"] == o["acik_adet"] * 10 + o["koli_sayisi"] * 20
    if not ayar.kisitsiz:
        assert o["koli_sayisi"] > 0


# ---------------------------------------------------------------- hazırlık, koşu, yol (KÜÇÜK)

OYUN_PENCERESI = (date(2025, 9, 1), date(2025, 9, 28))      # dört pazartesi, EGITIM_BIT'ten sonra


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    d = tmp_path_factory.mktemp("oyun")
    return oyun.Ortam(olcek="kucuk", onbellek=d / "kosular", cikti=d, pencere=OYUN_PENCERESI,
                      gun_sayisi=_n(date(2025, 9, 29)),
                      tahmin_parametreleri={**tahmin.PARAMETRELER, "n_estimators": 20})


@pytest.fixture(scope="module")
def hazirlik1(ortam):
    return oyun.hazirlik(1, ortam)


def test_hazirlik_yol_kendi_verisinden_egitir(hazirlik1, ortam):
    H = hazirlik1
    assert H.talep_tohumu == TALEP_TOHUM_TABANI + 1
    assert H.db == ortam.yol_dizini(1) / "perakende.duckdb" and H.db.exists()
    assert H.lumoda.meta["talep_tohumu"] == TALEP_TOHUM_TABANI + 1
    assert H.egitim_kaynagi == H.lumoda.meta["anahtar"]
    model = ortam.cikti / "tahmin" / "yol1.json"
    assert model.exists() and H.tahmin_ozet["kimlik"] == H.tahminci.kimlik
    # ikinci çağrı yeniden eğitmez: aynı kimlik, model dosyası değişmez
    zaman = model.stat().st_mtime_ns
    H2 = oyun.hazirlik(1, ortam)
    assert H2.tahminci.kimlik == H.tahminci.kimlik and model.stat().st_mtime_ns == zaman


@pytest.mark.parametrize("kisa", ["kural_ref", "tahmin_taban_ref", "lumoda_ref", "lumoda_kisitsiz"])
def test_kos_bir_olcer_ve_denetler(hazirlik1, ortam, kisa):
    s = dict(oyun.yol_listesi(1))[kisa]
    k, e = oyun.kos_bir(s, hazirlik1, _kal(tavan=60), ortam)
    o = e["olcutler"]
    assert 0 < o["bulunabilirlik"] <= 100 and o["talep_adet"] > 0
    assert o["gonderilen_adet"] > 0 and o["hafta_sayisi"] == 4
    assert o["toplama_maliyeti_tl"] == o["acik_adet"] * 10 + o["koli_sayisi"] * 20
    assert o["stoklu_cift"] > 0 and 0 <= o["kirik_cift_pay_yuzde"] <= 100
    assert o["satilan_gonderilen"] + o["satilmayan_gonderilen"] <= o["gonderilen_adet"]
    assert e["anahtar"] == k.meta["anahtar"] and k.meta["talep_tohumu"] == TALEP_TOHUM_TABANI + 1
    if kisa == "lumoda_kisitsiz":
        assert e["sevkiyat_farki"] is None and e["ayar"] is None
        assert k.meta["anahtar"] == hazirlik1.lumoda.meta["anahtar"]     # hazırlığın koşusu
    else:
        assert e["sevkiyat_farki"] == 0
        assert e["ayar"]["tavan"] == 60.0 and e["ayar"]["koli"]["ad"] == "A"
        assert politika.sevkiyatla_karsilastir(k).empty
    if kisa == "tahmin_taban_ref":
        assert k.meta["parametreler"] == {"egitim": hazirlik1.lumoda.meta["anahtar"]}
    assert {r["line"] for r in e["line"]} >= {"Collection", "NOS"}
    # ikinci çağrı: önbellekten koşu, eski kayıt yeniden ölçülmez
    k2, e2 = oyun.kos_bir(s, hazirlik1, _kal(tavan=60), ortam, onceki=e)
    assert k2.onbellekten and e2 is e
    satirlar = [json.loads(x) for x in (ortam.cikti / "ilerleme.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["ad"] == s.ad and r["onbellekten"] for r in satirlar)


def test_kos_bir_yol_uyusmazligi(hazirlik1, ortam):
    with pytest.raises(ValueError):
        oyun.kos_bir(oyun.Kosum("kural_ref", "kural"), hazirlik1, _kal(), ortam)


def test_kural_basit_carpanlari_yolun_gunluk_tablosundan(hazirlik1, ortam):
    s = oyun.Kosum("y1_kural_basit_ref", "kural_basit", yol=1)
    k, e = oyun.kos_bir(s, hazirlik1, _kal(tavan=60), ortam)
    assert (ortam.yol_dizini(1) / "gunluk.parquet").exists()
    assert e["sevkiyat_farki"] == 0 and 0 < e["olcutler"]["bulunabilirlik"] <= 100
    assert k.meta["politikalar"]["replenishment"]["parametreler"]["carpanlar"] == \
        politika.carpan_ozeti(hazirlik1.carpanlar())


def test_esitlik_denetimi(ortam):
    """Yol 0 (KÜÇÜK: kendi DuckDB'si) oyun öncesi pazartesisinde iki yolun özellikleri."""
    sonuc = oyun.esitlik_denetimi(ortam)
    f = sonuc["fiziksel"]
    assert set(f) == set(tahmin.OZELLIKLER)
    for s in ("tatil_gunu", "bf_gunu", "line", "kategori", "magaza_tipi"):
        assert f[s]["esit_pay"] == 1.0, s
    assert f["lag1"]["esit_pay"] > 0.95
    assert (ortam.cikti / "esitlik.json").exists()


def test_yollar_ayrisim():
    def y(kural, taban, tahmin):
        def o(b):
            return {"olcutler": {olc: 1.0 for olc in yollar.OZET_OLCUTLERI}
                    | {"bulunabilirlik": b, "kayip_orani": 100 - b, "magaza_stok_son": 10 * b}}
        return {"kosular": {"kural_ref": o(kural), "tahmin_taban_ref": o(taban), "tahmin_ref": o(tahmin)}}

    a = yollar.ozetle({"0": y(70, 72, 71), "1": y(70, 69, 68), "2": y(70, 73, 74)})["ayrisim"]
    og = a["ongoru"]["bulunabilirlik"]
    assert og["yollar"] == {"0": 2, "1": -1, "2": 3} and og["medyan"] == 2 and (og["pozitif"], og["negatif"]) == (2, 1)
    po = a["politika"]["kayip_orani"]
    assert po["yollar"] == {"0": 1, "1": 1, "2": -1} and po["medyan"] == 1
    assert a["politika"]["magaza_stok_son"]["medyan"] == pytest.approx(-10)
