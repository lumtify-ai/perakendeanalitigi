"""`markdown.hikaye`: yayımlanan tablolardan tulum hikâyesi (oyuncak fikstür), temizleme indirimi, geçmiş penceresi;
KÜÇÜK dünyada uçtan uca karar anı (yol 0 Lumoda tablolarından kurulan `Gorunum` kolların kaydını birebir üretir).

Analizin oyuncak denetimi (`analiz.option_tablosu`, `sezon_blogu`) de burada: aynı oyuncak tabloları okur."""

import math

import numpy as np
import pandas as pd
import pytest
from conftest import oyuncak_baglan, oyuncak_tablolar

import analiz
from markdown import hikaye, oyun

OPT = "SS25-a"           # 1. dalga, lansman 2025-02-10, indirim 2025-06-30, çıkış 2025-08-25; liste 700


def _tablolar():
    t = oyuncak_tablolar()
    u = t["urun"]
    u["model_adi"] = "Salopet Tulum"
    u["renk"] = "Lacivert"
    u["alis_fiyati"] = u["liste_fiyati"] * 0.4
    u["fiyat_segmenti"] = "orta"
    t["sevkiyat"] = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-02-03", "2025-02-03", "2025-08-25"]),
        "varis_tarihi": pd.to_datetime(["2025-02-05", "2025-02-05", "2025-08-27"]),
        "kaynak": ["DEPO", "DEPO", "S1"], "hedef": ["S1", "ONL", "S2"],
        "urun_id": [f"{OPT}-S", f"{OPT}-S", f"{OPT}-M"], "adet": [30, 5, 4],
        "tip": ["ilk_dagitim", "ilk_dagitim", "outlet_akisi"], "paket_id": [None, None, None]})
    t["siparis"] = pd.concat([t["siparis"], pd.DataFrame({
        "siparis_id": ["SP9", "SP9", "SP9"], "tip": ["ilk"] * 3, "option_id": [OPT] * 3,
        "urun_id": [f"{OPT}-{b}" for b in "SML"], "tedarikci_id": ["T1"] * 3,
        "siparis_tarihi": pd.to_datetime(["2024-10-01"] * 3), "planlanan_teslim": pd.to_datetime(["2025-01-20"] * 3),
        "gerceklesen_teslim": pd.to_datetime(["2025-01-27"] * 3), "adet": [400, 400, 400]})], ignore_index=True)
    t["siparis"]["adet"] = t["siparis"]["adet"].astype("int32")
    return t


@pytest.fixture
def con():
    c = oyuncak_baglan(_tablolar())
    yield c
    c.close()


def test_hikaye_oyuncak(con):
    k = hikaye.kunye(con, OPT)
    assert (k["dalga"], k["liste"], k["lansman"], k["indirim"], k["cikis"]) == (1, 700.0, "2025-02-10", "2025-06-30",
                                                                                 "2025-08-25")
    assert k["karar_gunu"] == "2025-05-05" and k["indirim_pazartesi"] == "2025-06-30"       # max(I − 56, L + 42)
    assert (k["arz_ilk"], k["arz_rpt"], k["rpt"]) == (1200, 0, [])
    seri = hikaye.haftalik_seri(con, OPT, k)
    ilk, ind = seri[0], next(r for r in seri if r["hafta"] == 0)
    assert (ilk["hafta"], ilk["hafta_lansman"], ilk["hafta_bas"]) == (-20, 0, "2025-02-10")
    assert seri[-1]["hafta_bas"] == "2025-11-17"                                             # çıkış + 84'ün haftası
    assert ind["satis"] == 2 * 3 * 7 and ind["oran"] == pytest.approx(0.3)                    # 7 mağaza × 3 beden × 2
    assert ind["magaza_stok"] == 6 * 3 * 10                                                  # ONL'nin satırı sayılmaz
    d = hikaye.stok_dagilimi(con, OPT, "2025-06-30", n=2)
    assert (d["magaza"], d["istanbul"], d["anadolu"], d["magaza_sayisi"], d["depo"]) == (180.0, 60.0, 120.0, 6, 0.0)
    assert [m["magaza_id"] for m in d["en_buyuk"]] == ["S1", "S2"] and d["en_buyuk"][0]["istanbul"]
    t = hikaye.tulum(con, OPT)
    assert t["arz"] == 1200 and t["satis_once"] == 20 * 42 and t["str_ind"] == pytest.approx(100 * 840 / 1200)
    assert t["lumoda"] == {"en_derin": pytest.approx(0.3), "ilk_indirim_hafta": 0}
    g = hikaye.gomlek(con, OPT)
    assert g["magazaya_giden"] == 30 and g["satis_once_fiziksel"] == 20 * 36                # ONL'ye giden ve satan girmez
    assert g["str_lumoda"] == pytest.approx(720 / 30) and g["str_arz"] == pytest.approx(840 / 1200)


def test_temizleme_indirimi():
    assert hikaye.temizleme_indirimi(100.0, 200.0, 2.0) == pytest.approx(1 - 0.5 ** 0.5)
    assert hikaye.temizleme_indirimi(300.0, 200.0, 2.0) == 0.0 and hikaye.temizleme_indirimi(1.0, 0.0, 2.0) == 0.0
    assert math.isnan(hikaye.temizleme_indirimi(100.0, 200.0, 0.0))
    # ε küçüldükçe stoğu eritmek için gereken indirim büyür (saf ε'nin dersi)
    assert hikaye.temizleme_indirimi(100.0, 200.0, 0.2) > hikaye.temizleme_indirimi(100.0, 200.0, 1.8)


def test_pencere():
    p = hikaye._Pencere(10, np.arange(12).reshape(4, 3))
    assert p[11:13, np.array([0, 2])].tolist() == [[3, 5], [6, 8]]
    with pytest.raises(IndexError):
        p[9:12, [0]]
    with pytest.raises(TypeError):
        p[10, [0]]


def test_analiz_oyuncak(con):
    t = analiz.option_tablosu(con, "SS25")
    assert list(t["option_id"]) == [f"SS25-{h}" for h in "abcdef"]
    a = t.set_index("option_id").loc[OPT]
    # haftalık satış pazartesi: indirim − 28'e (06-02) kadar 16 hafta, erken pencerede 4, indirim döneminde 2 (07-07'ye dek)
    assert (a["satis_tam"], a["satis_erken"], a["satis_ind"]) == (16 * 42, 4 * 42, 2 * 42)
    assert (a["arz_ilk"], a["arz"], a["outlet_akisi"], a["en_derin"]) == (1200, 1200, 4, pytest.approx(0.3))
    b = analiz.sezon_blogu(con, "SS25")
    assert b["kademe"]["dagilim"] == {"0.30": 6} and b["kademe"]["lumoda_oncesi_indirilen"] == 0
    assert sum(c["option"] for c in b["str"]["ceyrekler"]) == 6
    hf = {r["hafta"]: r["adet"] for r in b["haftalik"]}
    assert min(hf) == -8 and hf[0] > 0
    q = analiz.ceyrek_etiketi(np.array([5.0, 1.0, 1.0, 9.0]), np.array(["d", "c", "a", "b"]))
    assert q.tolist() == [3, 2, 1, 4]                                   # eşitlikte option_id


@pytest.fixture(scope="module")
def kucuk_ortam(tmp_path_factory):
    kok = tmp_path_factory.mktemp("markdown_hikaye")
    ortam = oyun.Ortam(olcek="kucuk", onbellek=kok / "kosular", cikti=kok / "cikti", ogrenme=kok / "ogrenme",
                       ilerleme=False)
    oyun.kos_hepsi("yol0", ortam, adlar={"lumoda", "opt_SS25", "opt_tuzak_SS25"})
    return ortam


def test_hikaye_kucuk_karar_ani(kucuk_ortam):
    """Yol 0 Lumoda'sının tablolarından kurulan karar anı, opt ve opt_tuzak koşularının o pazartesi kaydını (bütün
    option'ların satılabilir stoğu; sahne option'ının oranı, tahmini satışı, beklenen kalanı) birebir üretir."""
    h = hikaye.kur(kucuk_ortam)
    assert h["sahne_yedek"] and h["karar_gunu_tutarli"] and h["olcek"] == "kucuk"
    assert set(h["eksik_kollar"]) == {f"{k}_SS25" for k in oyun.YOL0_KOLLARI} - {"opt_SS25", "opt_tuzak_SS25"}
    e = h["esneklik"]
    for kol in ("opt", "opt_tuzak"):
        d = e["dogrulama"][kol]
        assert d["esit"] and d["satilabilir_option"] == d["satilabilir_esit"] > 1, (kol, d)
    r = {x["ad"]: x for x in e["epsler"]}
    assert set(r) == {"saf", "markdown", "kampanya", "gercek"} and r["saf"]["eps"] < 1 and r["saf"]["dp_oran"] == 0.0
    assert r["kampanya"]["dp_oran"] == e["dogrulama"]["opt"]["kayit"]["oran"]
    assert {"cok", "az", "gomlek"} == set(h["kollar"]["opt"]["optionlar"]) and "lumoda" in h["kollar"]
    with pytest.raises(hikaye.Eksik, match="önbellekte yok"):
        hikaye.kur(oyun.Ortam(olcek="kucuk", onbellek=kucuk_ortam.onbellek.parent / "bos", cikti=kucuk_ortam.cikti,
                              ogrenme=kucuk_ortam.ogrenme, ilerleme=False))
