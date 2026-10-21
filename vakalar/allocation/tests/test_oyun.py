"""`allocation.oyun` ve `allocation.yollar`: ızgaranın adları ve bütçesi, çözüm ve imza (aynı koşu iki
adla), en iyi seçimi, demo haritası; KÜÇÜK dünyada kablolama (kol kurma → `motor.kos` parametreleri →
kırpma denetimi → ölçüm → `oyun.json`, kaldığı yerden sürme) ve kalibrasyon koşucusu.

KÜÇÜK testleri motoru gerçekten koşar: tam pencere (oyun sezonu SS25, ~10 sn/koşu) ya da kısa koşu
(300 gün, SS23; kırpma denetimi). Önbellek ve çıktılar geçici dizinde.
"""

import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from allocation import kalibrasyon, kaynak, motor, olcutler, oyun, sabitler, yollar
from allocation.politika import Ayar, EsitKol

KAL = {"en_az": 80, "tahmin_parametreleri": {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 400,
                                             "min_child_samples": 100},
       "tavan": True, "gamma": 2.0, "belirsizlik_olcusu": "benzer_tahmin_ayrisma", "belirsizlik_spearman": 0.107,
       "tbar": 0.3}
SECIM = {"kol": "tahmin", "tavan": False, "ad": "pay_tahmin_tavansiz"}     # Ruling R43: tavansız en iyi
# KÜÇÜK dünyanın ~10 kümelenen mağazası önerinin kuralına (k ≥ 3, en küçük küme ≥ 3) sığmaz (Ortam.kume_oneri)
KUCUK_ONERI = {"k_aralik": range(2, 6), "en_kucuk": 2}
# küme payının koşusuz seçimi (testte elle; gerçeği cikti/kume_kalibrasyon.json): KÜÇÜK'te geçmiş az, ince düzey
KUME_KAL = {"sezon": "SS24", "karar_gunu": "2024-02-09",
            "secim": {y: {"bas": b, "en_az": 3, "wape": None} for y, b in zip(oyun.KUME_YAPILARI, (0, 2, 0, 1))}}


# ---------------------------------------------------------------------------
# Izgara
# ---------------------------------------------------------------------------


def test_izgara_adlari_tekil():
    """Bütün bloklarda ve yollarda koşu adları tekil; dosya adına uygun; yol 0'ın yol kolları ızgarada."""
    adlar = [s.ad for b in oyun.IZGARA.values() for s in b]
    assert len(adlar) == len(set(adlar))
    yol_adlari = [s.ad for p in range(1, sabitler.YOL_SAYISI) for _, s in oyun.yol_listesi(p, KAL)]
    assert len(yol_adlari) == len(set(yol_adlari)) and not set(yol_adlari) & set(adlar)
    assert all(motor._AD_DESENI.match(a) for a in adlar + yol_adlari)
    assert [s.ad for _, s in oyun.yol_listesi(0, KAL)] == ["lumoda", "pay_esit", "pay_benzer_tavansiz",
                                                           "pay_tahmin_tavansiz", "pay_kahin", "kume_ml", "kume_gizli"]
    # yollarda benzer ve tahmin tavansız (R44), kalibrasyonun tavanı ne olursa olsun; yol 0 ile aynı çözüm
    for p in range(sabitler.YOL_SAYISI):
        for kal in (KAL, {**KAL, "tavan": True}):
            c = {k: oyun.cozumle(s, kal, None) for k, s in oyun.yol_listesi(p, kal)}
            assert c["benzer"]["tavan"] is False and c["tahmin"]["tavan"] is False, p
            assert all(v["yol"] == p and v["tutma"] == 0.0 for v in c.values())
    y0 = {k: {**oyun.cozumle(s, KAL, None), "yol": 1} for k, s in oyun.yol_listesi(0, KAL)}
    assert y0 == {k: oyun.cozumle(s, KAL, None) for k, s in oyun.yol_listesi(1, KAL)}
    assert list(oyun.IZGARA) == list(oyun.BLOK_SIRASI)
    tut = oyun.IZGARA["tutma"]
    assert {(s.kol, s.tutma, s.repl) for s in tut} == {
        (k, t, r) for k in ("lumoda_tut", "eniyi") for t in sabitler.TUTMA_DUZEYLERI for r in ("lumoda", "hiz")}
    assert oyun.IZGARA["esdegerlik"][0].ad == "lumoda" and oyun.IZGARA["sabit_takvim"][0].ad == "lumoda_takvimli"
    # eşleşik tutma: tavansız kol, t kaynağın (aynı kolun tavanlı pay koşusu) kaydından (R43)
    es = {s.ad: s for s in oyun.IZGARA["eslesik"]}
    assert {a: (s.kol, s.tavan, s.tutma, s.tutma_kaynagi) for a, s in es.items()} == {
        "es_benzer": ("benzer", False, None, "pay_benzer_tavanli"),
        "es_tahmin": ("tahmin", False, None, "pay_tahmin_tavanli")}
    assert all(s.tutma_kaynagi in {k.ad for k in oyun.IZGARA["pay"]} for s in es.values())
    assert oyun.BLOK_SIRASI.index("eslesik") > oyun.BLOK_SIRASI.index("pay")
    # demo'nun tahmin kolları tavansız
    assert all(s.tavan is False for s in oyun.IZGARA["demo"] if s.kol in oyun.TAVANLI)


def test_izgara_butcesi():
    """Yol 0 ≤ 45 koşu adı (aynı koşu iki adla sayılır: üst sınır), toplam ≤ 80 (spec §4.5). R43 sonrası
    37 ad (eslesik 2 eklendi), 3'ü takma ad; yollar 20. Küme kolları (Mağaza Kümeleme spec §4.4): yol 0'da
    4, yol 1–4'te 2'şer: 41 ad, yollar 28; yeni TAM koşu 4 + 8 = 12."""
    n = oyun.kosu_sayisi()
    assert n["yol0"] <= 45 and n["toplam"] <= 80
    assert (n["yol0"], n["yollar"], n["toplam"]) == (41, 28, 69)
    assert n["yollar"] == (sabitler.YOL_SAYISI - 1) * (len(oyun.YOL_KOLLARI) + len(oyun.YOL_KUME_KOLLARI))
    assert len(oyun.IZGARA["kume"]) + (sabitler.YOL_SAYISI - 1) * len(oyun.YOL_KUME_KOLLARI) == 12


def test_kume_blogu_adlari():
    """`kume` bloğu: kume_k2 (ciro sınıfı), kume_k1 (bölge), kume_ml (öneri), kume_gizli (gizli segment, yalnız
    ölçüm); hepsi t = 0, tavansız, tepkili (aynı mal). Çözümleri birbirinden ve pay_kahin'den farklı (aynı
    koşunun takma adı olmazlar); öteki kolların çözümüne `kume` alanı girmez (imzaları değişmez). Yollarda
    kume_ml ve kume_gizli."""
    k = {s.ad: s for s in oyun.IZGARA["kume"]}
    assert list(k) == ["kume_k2", "kume_k1", "kume_ml", "kume_gizli"]
    assert {a: s.kume for a, s in k.items()} == {"kume_k2": "k2", "kume_k1": "k1", "kume_ml": "ml", "kume_gizli": "gizli"}
    assert oyun.BLOK_SIRASI[-1] == "kume" and set(oyun.KUME_YAPILARI) == {"k2", "k1", "ml", "gizli"}
    tum = oyun.tum_kosumlar()
    for kal in (KAL, {**KAL, "tavan": True}, {**KAL, "tavan": False}):
        c = {a: oyun.cozumle(s, kal, None) for a, s in k.items()}
        assert all(v["kol"] == "kume" and v["tutma"] == 0.0 and v["tavan"] is False and v["repl"] == "lumoda"
                   and not v["takvim"] and v["yol"] == 0 for v in c.values())
        imzalar = {oyun.imza(v) for v in c.values()} | {oyun.imza(oyun.cozumle(tum["pay_kahin"], kal, None))}
        assert len(imzalar) == 5
    for a, s in tum.items():
        if s.kol != "kume" and s.tutma_kaynagi is None:
            assert "kume" not in oyun.cozumle(s, KAL, SECIM), a
    assert oyun.cozumle(tum["pay_esit"], KAL, None) == {"kol": "esit", "taban": None, "tutma": 0.0, "tavan": False,
                                                        "repl": "lumoda", "takvim": False, "yol": 0}
    y3 = dict(oyun.yol_listesi(3, KAL))
    assert y3["kume_ml"].ad == "y3_kume_ml" and y3["kume_gizli"].kume == "gizli" and y3["kume_ml"].yol == 3
    with pytest.raises(ValueError, match="kume alanı"):
        oyun.Kosum("x", "kume")
    with pytest.raises(ValueError, match="kume alanı"):
        oyun.Kosum("x", "esit", kume="ml")
    with pytest.raises(ValueError, match="bilinmeyen"):
        oyun.Kosum("x", "kume", kume="k9")
    with pytest.raises(ValueError, match="aynı mal"):
        oyun.Kosum("x", "kume", kume="ml", tutma=0.15)


def test_kume_hiyerarsisi_benzer_ile_ayni():
    """Küme payının hiyerarşisi İlk Sevkiyat'ın benzer endeksininkiyle aynı (spec §4.4: aynı biçim)."""
    from kumeleme import kume_payi

    from allocation import benzer

    assert kume_payi.HIYERARSI == benzer.HIYERARSI and kume_payi.SUTUNLAR == benzer.SUTUNLAR


def test_kosum_denetimi():
    with pytest.raises(ValueError):
        oyun.Kosum("x", "yok")
    with pytest.raises(ValueError):
        oyun.Kosum("x", "lumoda", tutma=0.15)
    with pytest.raises(ValueError):
        oyun.Kosum("x", "lumoda", repl="hiz")
    with pytest.raises(ValueError, match="eşleşik"):
        oyun.Kosum("x", "benzer", tutma=None, tavan=True, tutma_kaynagi="pay_benzer_tavanli")
    with pytest.raises(ValueError, match="eşleşik"):
        oyun.Kosum("x", "esit", tutma=None, tavan=False, tutma_kaynagi="pay_esit")
    with pytest.raises(ValueError, match="boş"):
        oyun.Kosum("x", "benzer", tutma=None)


def test_cozum_ve_imza():
    """En iyi `secim`'den (kolu ve tavanı: R43'te tavansız), tavan boşsa kalibrasyonun seçimi, tavansız
    kollarda tavan kapalı; belirsizlikte tutma yok. Aynı çözüm aynı imza: tut_eniyi_t00 = pay bloğunun
    tavansız en iyisi, demo_<en iyi>_t15 = tut_eniyi_t15; ötekiler farklı. Eşleşik tutma çözülmeden
    imzalanamaz."""
    tum = oyun.tum_kosumlar()
    es_t = {"es_benzer": 0.209, "es_tahmin": 0.341}
    tum.update({a: replace(tum[a], tutma=v) for a, v in es_t.items()})

    def im(ad, secim=SECIM, kal=KAL):
        return oyun.imza(oyun.cozumle(tum[ad], kal, secim))

    assert im("tut_eniyi_t00") == im("pay_tahmin_tavansiz")
    assert im("tut_eniyi_t00") != im("pay_tahmin_tavanli")
    assert oyun.cozumle(tum["tut_eniyi_t15"], KAL, SECIM)["tavan"] is False     # kalibrasyonun tavanı True
    assert oyun.cozumle(tum["tut_eniyi_t15"], KAL, {**SECIM, "tavan": True})["tavan"] is True
    assert oyun.cozumle(tum["es_tahmin"], KAL, None) == {"kol": "tahmin", "taban": None, "tutma": 0.341,
                                                       "tavan": False, "repl": "lumoda", "takvim": False, "yol": 0}
    with pytest.raises(RuntimeError, match="çözülmedi"):
        oyun.cozumle(oyun.tum_kosumlar()["es_benzer"], KAL, None)
    assert im("demo_tahmin_t15") == im("tut_eniyi_t15")
    benzer = {**SECIM, "kol": "benzer"}
    assert im("demo_benzer_t30", benzer) == im("tut_eniyi_t30", benzer)
    assert im("demo_tahmin_t15", benzer) != im("tut_eniyi_t15", benzer)
    assert im("pay_tahmin_tavansiz") != im("pay_tahmin_tavanli")
    assert im("pay_esit") != im("sabit_esit") != im("tut_lumoda_t00")
    c = oyun.cozumle(tum["belirsizlik"], KAL, SECIM)
    assert c == {"kol": "belirsizlik", "taban": "tahmin", "tutma": None, "tavan": False, "repl": "lumoda",
                 "takvim": False, "yol": 0}
    assert oyun.cozumle(tum["pay_kahin"], KAL, None)["tavan"] is False
    # sabit takvimin benzer ve tahmini tavansız (R46), kalibrasyonun tavanı açıkken de; tepkili karşılığı
    # pay_*_tavansiz ile yalnız takvimde ayrışır
    for k in ("benzer", "tahmin"):
        cs = oyun.cozumle(tum[f"sabit_{k}"], {**KAL, "tavan": True}, None)
        assert cs["tavan"] is False and cs["takvim"] is True
        assert {**cs, "takvim": False} == oyun.cozumle(tum[f"pay_{k}_tavansiz"], KAL, None)
    with pytest.raises(RuntimeError, match="en iyi"):
        oyun.cozumle(tum["tut_eniyi_t15"], KAL, None)
    imzalar = {im(a) for a in tum}
    assert len(imzalar) == len(tum) - 3                 # 3 ad aynı koşunun ikinci adı


def _kayit(ad, kol, tavan, b, kalan):
    return ad, {"grup": "pay", "cozum": {"kol": kol, "tavan": tavan, "tutma": 0.0, "takvim": False,
                                         "repl": "lumoda"}, "anahtar": ad,
                "olcutler": {"bulunabilirlik": b, "sezon_sonu_kalan_yuzde": kalan}}


def test_secim_yap():
    """Tavansız benzer ve tahmin (R43; kalibrasyonun tavanı ne olursa olsun); bulunabilirlik farkı 0,3
    puandan azsa az kalan kazanır; tavanlı kollar ve öteki kollar aday değil."""
    k = dict([_kayit("pay_benzer_tavansiz", "benzer", False, 75.0, 24.0),
              _kayit("pay_tahmin_tavansiz", "tahmin", False, 75.2, 25.0),
              _kayit("pay_tahmin_tavanli", "tahmin", True, 80.0, 20.0),
              _kayit("pay_esit", "esit", False, 90.0, 10.0)])
    s = oyun.secim_yap(k, KAL)
    assert (s["kol"], s["ad"], s["tavan"]) == ("benzer", "pay_benzer_tavansiz", False)
    k["pay_tahmin_tavansiz"]["olcutler"]["bulunabilirlik"] = 75.4
    assert oyun.secim_yap(k, KAL)["ad"] == "pay_tahmin_tavansiz"
    assert oyun.secim_yap(k, {**KAL, "tavan": False})["ad"] == "pay_tahmin_tavansiz"
    del k["pay_benzer_tavansiz"]
    with pytest.raises(RuntimeError, match="eksik"):
        oyun.secim_yap(k, KAL)


def test_belirsizlik_gammasi():
    """Ölçünün Spearman'ı ≤ 0 (ya da yok) ise γ = 0: belirsizlik kolu sabit t̄ tutar."""
    assert oyun.belirsizlik_gammasi(KAL) == 2.0
    assert oyun.belirsizlik_gammasi({**KAL, "belirsizlik_spearman": 0.0}) == 0.0
    assert oyun.belirsizlik_gammasi({**KAL, "belirsizlik_spearman": -0.2}) == 0.0
    assert oyun.belirsizlik_gammasi({**KAL, "belirsizlik_spearman": None}) == 0.0
    assert oyun.belirsizlik_gammasi({**KAL, "belirsizlik_spearman": float("nan")}) == 0.0


def test_demo_haritasi():
    tum = oyun.tum_kosumlar()
    kosular = {}
    for ad in ("lumoda", "pay_esit", "pay_benzer_tavanli", "pay_benzer_tavansiz", "pay_tahmin_tavanli",
               "pay_tahmin_tavansiz",
               "tut_lumoda_t15", "tut_lumoda_t30", "tut_eniyi_t15", "tut_eniyi_t30", "tut_eniyi_t15_hiz",
               "demo_esit_t15", "demo_esit_t30", "demo_benzer_t15", "demo_benzer_t30", "sabit_esit"):
        kosular[ad] = {"cozum": oyun.cozumle(tum[ad], KAL, SECIM)}
    h = oyun.demo_haritasi(kosular, KAL)
    assert h["lumoda"] == {"0": "lumoda", "0.15": "tut_lumoda_t15", "0.3": "tut_lumoda_t30"}
    assert h["esit"] == {"0": "pay_esit", "0.15": "demo_esit_t15", "0.3": "demo_esit_t30"}
    assert h["benzer"] == {"0": "pay_benzer_tavansiz", "0.15": "demo_benzer_t15", "0.3": "demo_benzer_t30"}
    assert h["tahmin"] == {"0": "pay_tahmin_tavansiz", "0.15": "tut_eniyi_t15", "0.3": "tut_eniyi_t30"}


def test_talep_tohumu():
    assert oyun.talep_tohumu(0) is None
    assert oyun.talep_tohumu(3) == sabitler.TALEP_TOHUM_TABANI + 3


def test_yollar_ozetle():
    yol = {str(p): {"kosular": {k: {"olcutler": {o: float(p + i) for o in yollar.OZET_OLCUTLERI + tuple(
        yollar.YUKSEK_IYI)}} for i, k in enumerate(oyun.YOL_KOLLARI)}} for p in range(3)}
    oz = yollar.ozetle(yol)
    assert oz["kollar"]["tahmin"]["bulunabilirlik"] == {"min": 3.0, "medyan": 4.0, "max": 5.0, "n": 3}
    assert oz["onde"]["tahmin|lumoda"]["bulunabilirlik"] == 3 and oz["onde"]["tahmin|lumoda"]["kayip_orani"] == 0


# ---------------------------------------------------------------------------
# KÜÇÜK dünya: kablolama
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kucuk(tmp_path_factory):
    """Tam pencere KÜÇÜK ızgara parçası (SS25): esdegerlik bloğu (`kos_hepsi`), sonra seçili kosumlar
    `kos_bir` ile (öğrenme yolun lumoda koşusunun yayımlanan biçiminden)."""
    d = tmp_path_factory.mktemp("oyun_kucuk")
    ortam = oyun.Ortam(olcek="kucuk", onbellek=d / "kosular", cikti=d / "cikti", kume_oneri=KUCUK_ONERI)
    oyun.kos_hepsi("esdegerlik", ortam, KAL)
    G = oyun.Girdi(0, ortam, KAL, kume_kal=KUME_KAL)
    tum = oyun.tum_kosumlar()
    kosular = {"lumoda": G.lumoda}
    kayitlar = {}
    for ad in ("pay_esit", "pay_kahin", "pay_tahmin_tavanli", "pay_tahmin_tavansiz", "tut_lumoda_t15_hiz",
               "sabit_esit", "belirsizlik"):
        k, e = oyun.kos_bir(tum[ad], G, KAL, SECIM)
        kosular[ad], kayitlar[ad] = k, e
    return SimpleNamespace(ortam=ortam, G=G, kosular=kosular, kayitlar=kayitlar, dizin=d)


def test_kucuk_kablolama(kucuk):
    """Kol kurulur, `motor.kos`'a doğru yuvalarla ve kimlikle gider; motor kolları kırpmaz, Lumoda'yı kırpar;
    ölçütler tam."""
    k, e = kucuk.kosular, kucuk.kayitlar
    assert k["lumoda"].meta["turler"] == {} and k["lumoda"].meta["parametreler"] == {}
    assert k["pay_esit"].meta["turler"] == {"ilk_dagitim": "allocation.politika.EsitKol"}
    assert k["tut_lumoda_t15_hiz"].meta["turler"] == {"ilk_dagitim": "allocation.politika.LumodaTutKol",
                                                     "replenishment": "allocation.politika.HizReplenishment"}
    assert set(k["sabit_esit"].meta["turler"]) == {"ilk_dagitim", "rpt", "markdown"}
    p = k["tut_lumoda_t15_hiz"].meta["politikalar"]
    assert p["ilk_dagitim"]["parametreler"]["ayar"] == {"sezon": "SS25", "tutma": 0.15, "tavan": False,
                                                       "en_az_gosterim": False}
    assert p["replenishment"]["parametreler"]["sezon"] == "SS25"
    tahmin = k["pay_tahmin_tavanli"].meta["politikalar"]["ilk_dagitim"]["parametreler"]
    assert tahmin["ayar"]["tavan"] is True and tahmin["tahminci"] == kucuk.G.tahminci.kimlik
    bel = k["belirsizlik"].meta["politikalar"]["ilk_dagitim"]["parametreler"]
    assert bel["taban"]["kol"] == "tahmin" and len(bel["t_o"]) == len(kucuk.G.optionlar)
    assert bel["taban"]["ayar"]["tavan"] is False                        # tavansız en iyi (R43)
    t = np.array([v for _, v in bel["t_o"]])
    assert t.min() >= 0 and t.max() <= 2 * sabitler.BELIRSIZLIK_TBAR + 1e-12
    assert k["pay_kahin"].meta["politikalar"]["ilk_dagitim"]["parametreler"]["kol"] == "kahin"
    for ad, kayit in e.items():
        assert kayit["olcutler"]["kirpilan_adet"] == 0.0, ad
        assert kayit["cozum"] == oyun.cozumle(oyun.tum_kosumlar()[ad], KAL, SECIM)
    lum = json.loads(kucuk.ortam.oyun_yolu.read_text(encoding="utf-8"))["kosular"]["lumoda"]["olcutler"]
    assert lum["kirpilan_adet"] > 0                       # Lumoda'nın paketlerini motor kırpar
    assert set(lum) == set(e["pay_esit"]["olcutler"])
    assert {f"depoda_kalan_beden_{b}" for b in range(1, 6)} <= set(lum)
    # t = 0.15'te U'nun daha azı gider; aynı müşteri akışı: talep aynı değil (fiyat), sipariş aynı değil (RPT)
    assert e["tut_lumoda_t15_hiz"]["olcutler"]["ilk_dagitim_adet"] < lum["ilk_dagitim_adet"]
    # sabit takvim: RPT lumoda'nınkiyle aynı adet
    assert e["sabit_esit"]["olcutler"]["rpt_adet"] == lum["rpt_adet"]


def test_kucuk_erken_talep_kollar_arasi_ayni(kucuk):
    """Kahinin varsayımı KÜÇÜK'te: dağıtım, replenishment ve takvim değişse de erken penceredeki birincil
    talep hücre-gün aynı (veri testi TAM'da aynısını sınar)."""
    w, h = kucuk.G.w, kucuk.G.harita
    a = olcutler.erken_hucre_gunleri(kucuk.kosular["lumoda"], w, h)
    assert len(a) > 1000
    for ad in ("pay_esit", "tut_lumoda_t15_hiz", "sabit_esit", "belirsizlik"):
        pd.testing.assert_frame_equal(olcutler.erken_hucre_gunleri(kucuk.kosular[ad], w, h), a, obj=ad)
    e = olcutler.erken_birincil_talep(kucuk.kosular["lumoda"], w, h)
    assert set(kucuk.G.kahin) == set(zip(e["option_id"], e["magaza_id"]))


def test_kucuk_kaldigi_yerden(kucuk, monkeypatch):
    """İkinci çağrı koşmaz ve ölçmez (önbellek + oyun.json'daki ölçüm kodu); ilerleme her koşuyu yazar."""
    def olcme(*a, **k):
        raise AssertionError("yeniden ölçüldü")

    monkeypatch.setattr(olcutler, "hesapla", olcme)
    sonuc = oyun.kos_hepsi("esdegerlik", kucuk.ortam, KAL)
    assert sonuc["lumoda"].onbellekten
    satirlar = [json.loads(s) for s in kucuk.ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()]
    assert [s["ad"] for s in satirlar if s["ad"] == "lumoda"] == ["lumoda", "lumoda"]
    assert satirlar[-1]["onbellekten"] is True
    d = json.loads(kucuk.ortam.oyun_yolu.read_text(encoding="utf-8"))
    assert d["kosular"]["lumoda"]["grup"] == "esdegerlik" and d["sezon"] == "SS25"
    assert d["demo"]["lumoda"]["0"] == "lumoda"


def test_kucuk_takma_ad(kucuk):
    """Çözümü aynı ikinci ad koşulmaz: kaydı ilkine `ayni` ile bağlanır."""
    ortam = kucuk.ortam
    kayit = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    for ad, e in kucuk.kayitlar.items():
        kayit["kosular"][ad] = {"grup": "pay", **e}
    oyun.json_yaz(ortam.oyun_yolu, kayit)
    oyun.json_yaz(ortam.secim_yolu, SECIM)
    s = oyun.Kosum("tut_eniyi_t00", "eniyi")
    eski = dict(oyun.IZGARA)
    try:
        oyun.IZGARA["demo"] = (s,)
        oyun.kos_hepsi("demo", ortam, KAL, girdi=kucuk.G)
    finally:
        oyun.IZGARA.clear()
        oyun.IZGARA.update(eski)
    d = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))["kosular"]
    assert d["tut_eniyi_t00"]["ayni"] == "pay_tahmin_tavansiz"
    assert d["tut_eniyi_t00"]["anahtar"] == d["pay_tahmin_tavansiz"]["anahtar"]
    assert not list((kucuk.dizin / "kosular").glob("tut_eniyi_t00_*"))


def _beklenen_eslesik(kosu, w):
    """Test içi bağımsız hesap: 1 − Σ (paket × paket adedi) gönderilen ÷ Σ U × paket adedi."""
    from allocation.paylastir import paket_adedi

    r = kosu.kayitlar["ilk_dagitim"]
    opt = set(kaynak.oyun_optionlari(w, "SS25").tolist())
    U = giden = 0
    for o, g in r[r["kol"] & r["arg0"].isin(opt)].groupby("arg0"):
        pk = paket_adedi(w, int(o))
        U += int(g["U"].iloc[0]) * pk
        giden += int(g["deger"].sum()) * pk
    return round(1 - giden / U, 3), U, giden


def test_kucuk_eslesik_tutma(kucuk):
    """Eşleşik tutma (R43): t kaynağın (pay_tahmin_tavanli) kaydından, oyun.json'a yazılır; es_tahmin
    tavansız tahmin kolu bu t ile koşar (kayıtta toplam = ⌊U(1 − t)⌋); kaynak koşu önbellekten doğrulanır."""
    ortam, w = kucuk.ortam, kucuk.G.w
    kayit = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    for ad, e in kucuk.kayitlar.items():
        kayit["kosular"][ad] = {"grup": "pay", **e}
    oyun.json_yaz(ortam.oyun_yolu, kayit)
    oyun.json_yaz(ortam.secim_yolu, SECIM)
    t, U, giden = _beklenen_eslesik(kucuk.kosular["pay_tahmin_tavanli"], w)
    assert oyun.eslesik_tutma(kucuk.kosular["pay_tahmin_tavanli"], w, kucuk.G.harita)["tutma"] == t
    with pytest.raises(ValueError, match="kol"):
        oyun.eslesik_tutma(kucuk.kosular["lumoda"], w, kucuk.G.harita)
    sonuc = oyun.kos_hepsi("eslesik", ortam, KAL, girdi=kucuk.G, adlar=["es_tahmin"])
    d = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    es = d["eslesik_tutma"]["es_tahmin"]
    assert (es["kaynak"], es["tutma"], es["U_adet"], es["giden_adet"]) == ("pay_tahmin_tavanli", t, U, giden)
    assert es["anahtar"] == kucuk.kayitlar["pay_tahmin_tavanli"]["anahtar"]
    e = d["kosular"]["es_tahmin"]
    assert e["grup"] == "eslesik" and e["kosum"]["tutma"] == t and e["kosum"]["tutma_kaynagi"] == "pay_tahmin_tavanli"
    assert e["cozum"] == {"kol": "tahmin", "taban": None, "tutma": t, "tavan": False, "repl": "lumoda",
                          "takvim": False, "yol": 0}
    if t == 0.0:                                  # tavan KÜÇÜK'te bağlamadıysa tavansız t 0'ın kendisi
        assert e["ayni"] == "pay_tahmin_tavansiz"
    else:
        k = sonuc["es_tahmin"]
        ayar = k.meta["politikalar"]["ilk_dagitim"]["parametreler"]["ayar"]
        assert (ayar["tutma"], ayar["tavan"]) == (t, False)
        r = k.kayitlar["ilk_dagitim"]
        oz = r[r["kol"] & (r["t"] == t)].groupby("arg0").agg(U=("U", "first"), toplam=("toplam", "first"))
        assert len(oz) and (oz["toplam"] == np.floor(np.round(oz["U"] * (1 - t), 9))).all()
        assert e["olcutler"]["kirpilan_adet"] == 0.0
    assert "belirsizlik" in d["notlar"] and "tavanlı" in d["notlar"]["belirsizlik"]


def test_kucuk_kume_kollari(kucuk):
    """Küme kolları KÜÇÜK'te (yol 0 yayımlanan değil: kümeler lumoda koşusunun tablolarından kümeleme paketiyle
    yeniden kurulur): `kos_hepsi("kume")` dört kolu koşar; kol `KahinKol`'dur ve kimliği küme payı sözlüğünün
    özeti; sözlük koşunun kararlarındaki HER adayı (yeni mağaza dahil) pozitif payla taşır; motor kırpmaz ve
    kol Lumoda'yla aynı malı (⌊U⌋, pay_esit'in ilk dağıtımı) gönderir; düzeyler ve kümeleme kimliği oyun.json
    `girdi.kume`'de; sözlükler `kume_paylari.json`'da; pay bloğunun koşuları ve anahtarları yerinde."""
    from allocation.politika import KahinKol

    ortam, G = kucuk.ortam, kucuk.G
    kayit = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    for ad, e in kucuk.kayitlar.items():
        kayit["kosular"][ad] = {"grup": "pay", **e}
    oyun.json_yaz(ortam.oyun_yolu, kayit)
    oyun.json_yaz(ortam.secim_yolu, SECIM)
    sonuc = oyun.kos_hepsi("kume", ortam, KAL, girdi=G)
    assert list(sonuc) == ["kume_k2", "kume_k1", "kume_ml", "kume_gizli"]
    d = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    paylar = json.loads((ortam.cikti / oyun.KUME_PAYLARI_DOSYASI).read_text(encoding="utf-8"))
    w = G.w
    oid = w.optionlar["option_id"].astype(str).to_numpy()
    mid = w.magazalar["magaza_id"].astype(str).to_numpy()
    esit = kucuk.kayitlar["pay_esit"]["olcutler"]
    yeni = set(G.kume_yapilari["bilgi"]["_kapsam"]["yeni"])
    assert yeni                                         # KÜÇÜK'te de yeni mağaza var (M027 ve/veya M041)
    for ad, k in sonuc.items():
        yapi = ad.removeprefix("kume_")
        p = G.kume_payi(yapi)
        par = k.meta["politikalar"]["ilk_dagitim"]["parametreler"]
        assert k.meta["turler"] == {"ilk_dagitim": "allocation.politika.KahinKol"} and par["kol"] == "kahin"
        assert par["erken_talep"] == KahinKol(None, None, erken_talep=p).parametreler()["erken_talep"]
        assert par["erken_talep"] == paylar[ad]["pay"] == d["girdi"]["kume"][yapi]["pay"]
        assert {(o, m): v for o, m, v in paylar[ad]["paylar"]} == p
        r = k.kayitlar["ilk_dagitim"]
        r = r[r["kol"].to_numpy(dtype=bool) & (r["indis"] >= 0).to_numpy()]
        ciftler = set(zip(oid[r["arg0"].to_numpy()], mid[r["indis"].to_numpy()]))
        assert ciftler and ciftler <= set(p), ad                  # her aday sözlükte
        assert all(p[c] > 0 for c in ciftler), ad
        assert {m for _, m in ciftler} & yeni, ad                 # yeni mağaza aday ve payı var
        assert not r["geri_dusus"].any() and (r["duzey"] == -1).all()
        e = d["kosular"][ad]
        assert e["grup"] == "kume" and "ayni" not in e and e["cozum"]["kume"] == yapi
        assert e["olcutler"]["kirpilan_adet"] == 0.0
        assert e["olcutler"]["ilk_dagitim_adet"] == esit["ilk_dagitim_adet"]     # aynı mal: ⌊U⌋
        b = d["girdi"]["kume"][yapi]
        assert (b["bas"], b["en_az"]) == (KUME_KAL["secim"][yapi]["bas"], 3)
        assert sum(b["duzey"].values()) == len(G.optionlar) and b["kumeleme"]["kimlik"]
        assert b["kumeleme"]["kaynak"].startswith("yeniden kuruldu")
    assert d["kume_kalibrasyon"]["secim"] == KUME_KAL["secim"]
    assert len({d["kosular"][a]["anahtar"] for a in sonuc} | {kucuk.kayitlar["pay_kahin"]["anahtar"]}) == 5
    for ad, e in kucuk.kayitlar.items():
        assert d["kosular"][ad]["anahtar"] == e["anahtar"]
    # gizli kol gizli segmenti, ML kolu önerinin kümelerini taşır; ikisi kapsamın aynı mağazalarında
    et = G.kume_yapilari["etiket"]
    from kumeleme import hakem

    assert (et["gizli"] == hakem.gizli_segment(w).loc[et["gizli"].index]).all()
    assert sorted(et["ml"].index) == sorted(et["gizli"].index) == sorted(et["k1"].index) == sorted(et["k2"].index)


def test_kucuk_kume_kalibre(kucuk):
    """`kume_kalibre` (koşusuz): her yapı için bas 0..4 × en_az ızgarası, WAPE `kalibrasyon.pay_wape`; seçilen en
    küçük WAPE'li satır. KÜÇÜK'te kablolama (gerçek pay KÜÇÜK lumoda koşusunun oyun sezonundan)."""
    G = kucuk.G
    t = G._tablolar()
    gercek = kalibrasyon.erken_gercek(t, G.w, "SS25")
    d = oyun.kume_kalibre(G.ogrenme_tablosu, gercek, G.kume_yapilari, G.w, G.harita, "SS25")
    tablo = pd.DataFrame(d["tablo"])
    assert len(tablo) == len(oyun.KUME_YAPILARI) * 5 * len(kalibrasyon.EN_AZ_IZGARASI)
    assert tablo["wape"].between(0, 1).all()
    for y, sec in d["secim"].items():
        ty = tablo[tablo["yapi"] == y]
        assert sec["wape"] == ty["wape"].min()
        en = ty[ty["wape"] == ty["wape"].min()].iloc[0]
        assert (sec["bas"], sec["en_az"]) == (en["bas"], en["en_az"])
        assert sec["hiyerarsi"][-1] == []


# ---------------------------------------------------------------------------
# KÜÇÜK kısa koşu: kırpma denetimi, kalibrasyon koşucusu
# ---------------------------------------------------------------------------

KISA = {"olcek": "kucuk", "gun_sayisi": 300}
KISA_SEZON = "SS23"      # KÜÇÜK kısa koşuda kararı pencereye düşen sezon


class _Fazla(EsitKol):
    """U'yu aşan kol: her adaya 10⁴ paket (motor kırpmalı)."""

    def _karar(self, g, o, aday, U, t, toplam):
        return np.where(aday, 10_000, 0), None, -1, False


def test_kirpma_denetimi_kos_bir(tmp_path, monkeypatch):
    """Kolun kararını motor kırparsa koşu geçersiz: `kos_bir` `RuntimeError` verir (Ruling R21)."""
    ortam = oyun.Ortam(onbellek=tmp_path / "kosular", cikti=tmp_path, sezon=KISA_SEZON, ilerleme=False, **KISA)
    G = oyun.Girdi(0, ortam, KAL)
    fazla = _Fazla(motor.lumoda("ilk_dagitim"), G.harita, Ayar(sezon=KISA_SEZON))
    monkeypatch.setattr(oyun, "politika_kur", lambda s, G, kal, secim: {"ilk_dagitim": fazla})
    with pytest.raises(RuntimeError, match="kırptı"):
        oyun.kos_bir(oyun.Kosum("fazla", "esit"), G, KAL, None)


def _kucuk_endeks(w, h):
    """KÜÇÜK dünyada sahte geçmiş (AW22 Collection, rastgele erken talep); SS23 kararlarıyla eşleşir."""
    from allocation import benzer, ogrenme

    rng = np.random.default_rng(3)
    gecmis = np.flatnonzero((w.optionlar["sezon_kodu"] == "AW22").to_numpy()
                            & (w.optionlar["line"] == "Collection").to_numpy())
    oz = ogrenme.option_oznitelikleri(w, gecmis)
    satir = [{"option": int(o), "magaza": int(m), "stoklu_gun": 30, "talep": float(rng.gamma(2.0, 15.0)),
              **oz.iloc[i].to_dict()} for i, o in enumerate(gecmis) for m in np.flatnonzero(h.magaza_fiziksel)]
    return benzer.ogren(pd.DataFrame(satir), en_az=2)


def test_kalibrasyon_kosucusu_kucuk(tmp_path, monkeypatch):
    """`kalibrasyon_kosucusu` (Görev 7 notu): `KalKol` → kol (sezon `Ayar`'dan) → `motor.kos` (parametreler
    `KalKol.parametreler()`, kolun kimliği) → kırpma denetimi → iki ölçüt; lumoda referansı önbellekli
    `lumoda`. U'yu aşan kolda `RuntimeError`."""
    w = motor.dunya("kucuk")
    h = kaynak.harita_kur(w)
    cev = kalibrasyon.Cevrimdisi(en_az=2, tahmin_parametreleri={}, belirsizlik_olcusu="benzer_dk",
                                 tablo=pd.DataFrame(), endeks=_kucuk_endeks(w, h))
    kos_fn = oyun.kalibrasyon_kosucusu(cev, w, h, onbellek=tmp_path, sezon=KISA_SEZON, ilerleme=None, **KISA)
    tanim = kalibrasyon.KalKol("benzer", Ayar(sezon=KISA_SEZON, tavan=True))
    o = kos_fn("kal_benzer", tanim)
    assert set(kalibrasyon.GEREKEN_OLCUTLER) <= set(o) and o["onbellekten"] is False
    meta = json.loads(next(tmp_path.glob("kal_benzer_*/meta.json")).read_text(encoding="utf-8"))
    assert meta["parametreler"] == tanim.parametreler()
    assert meta["turler"] == {"ilk_dagitim": "allocation.politika.BenzerKol"}
    assert meta["politikalar"]["ilk_dagitim"]["parametreler"]["ayar"]["sezon"] == KISA_SEZON
    assert meta["politikalar"]["ilk_dagitim"]["parametreler"]["endeks"] == cev.endeks.sabitle().kimlik
    assert 0 < o["bulunabilirlik"] <= 100
    r = kos_fn("lumoda", kalibrasyon.KalKol("lumoda", Ayar(sezon=KISA_SEZON)))
    assert r["anahtar"] == motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, tembel=True, **KISA).meta["anahtar"]
    monkeypatch.setattr(kalibrasyon, "kol_kur", lambda tanim, cev, temel, harita: _Fazla(temel, harita, tanim.ayar))
    with pytest.raises(RuntimeError, match="kırptı"):
        kos_fn("kal_fazla", tanim)
