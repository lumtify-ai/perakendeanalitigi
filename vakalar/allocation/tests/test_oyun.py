"""`allocation.oyun` ve `allocation.yollar`: ızgaranın adları ve bütçesi, çözüm ve imza (aynı koşu iki
adla), en iyi seçimi, demo haritası; KÜÇÜK dünyada kablolama (kol kurma → `motor.kos` parametreleri →
kırpma denetimi → ölçüm → `oyun.json`, kaldığı yerden sürme) ve kalibrasyon koşucusu.

KÜÇÜK testleri motoru gerçekten koşar: tam pencere (oyun sezonu SS25, ~10 sn/koşu) ya da kısa koşu
(300 gün, SS23; kırpma denetimi). Önbellek ve çıktılar geçici dizinde.
"""

import json
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
SECIM = {"kol": "tahmin", "tavan": True, "ad": "pay_tahmin_tavanli"}


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
    assert [s.ad for _, s in oyun.yol_listesi(0, KAL)] == ["lumoda", "pay_esit", "pay_benzer_tavanli",
                                                           "pay_tahmin_tavanli", "pay_kahin"]
    assert list(oyun.IZGARA) == list(oyun.BLOK_SIRASI)
    tut = oyun.IZGARA["tutma"]
    assert {(s.kol, s.tutma, s.repl) for s in tut} == {
        (k, t, r) for k in ("lumoda_tut", "eniyi") for t in sabitler.TUTMA_DUZEYLERI for r in ("lumoda", "hiz")}
    assert oyun.IZGARA["esdegerlik"][0].ad == "lumoda" and oyun.IZGARA["sabit_takvim"][0].ad == "lumoda_takvimli"


def test_izgara_butcesi():
    """Yol 0 ≤ 45 koşu adı (aynı koşu iki adla sayılır: üst sınır), toplam ≤ 80 (spec §4.5)."""
    n = oyun.kosu_sayisi()
    assert n["yol0"] <= 45 and n["toplam"] <= 80
    assert n["yollar"] == (sabitler.YOL_SAYISI - 1) * len(oyun.YOL_KOLLARI)


def test_kosum_denetimi():
    with pytest.raises(ValueError):
        oyun.Kosum("x", "yok")
    with pytest.raises(ValueError):
        oyun.Kosum("x", "lumoda", tutma=0.15)
    with pytest.raises(ValueError):
        oyun.Kosum("x", "lumoda", repl="hiz")


def test_cozum_ve_imza():
    """En iyi `secim`'den, tavan boşsa kalibrasyonun seçimi, tavansız kollarda tavan kapalı; belirsizlikte
    tutma yok. Aynı çözüm aynı imza: tut_eniyi_t00 = pay bloğunun en iyisi, demo_<en iyi>_t15 =
    tut_eniyi_t15; ötekiler farklı."""
    tum = oyun.tum_kosumlar()

    def im(ad, secim=SECIM, kal=KAL):
        return oyun.imza(oyun.cozumle(tum[ad], kal, secim))

    assert im("tut_eniyi_t00") == im("pay_tahmin_tavanli")
    assert im("demo_tahmin_t15") == im("tut_eniyi_t15")
    benzer = {**SECIM, "kol": "benzer"}
    assert im("demo_benzer_t30", benzer) == im("tut_eniyi_t30", benzer)
    assert im("demo_tahmin_t15", benzer) != im("tut_eniyi_t15", benzer)
    assert im("pay_tahmin_tavansiz") != im("pay_tahmin_tavanli")
    assert im("pay_esit") != im("sabit_esit") != im("tut_lumoda_t00")
    c = oyun.cozumle(tum["belirsizlik"], KAL, SECIM)
    assert c == {"kol": "belirsizlik", "taban": "tahmin", "tutma": None, "tavan": True, "repl": "lumoda",
                 "takvim": False, "yol": 0}
    assert oyun.cozumle(tum["pay_kahin"], KAL, None)["tavan"] is False
    assert oyun.cozumle(tum["sabit_benzer"], {**KAL, "tavan": False}, None)["tavan"] is False
    with pytest.raises(RuntimeError, match="en iyi"):
        oyun.cozumle(tum["tut_eniyi_t15"], KAL, None)
    imzalar = {im(a) for a in tum}
    assert len(imzalar) == len(tum) - 3                 # 3 ad aynı koşunun ikinci adı


def _kayit(ad, kol, tavan, b, kalan):
    return ad, {"grup": "pay", "cozum": {"kol": kol, "tavan": tavan}, "anahtar": ad,
                "olcutler": {"bulunabilirlik": b, "sezon_sonu_kalan_yuzde": kalan}}


def test_secim_yap():
    """Kalibrasyonun tavanıyla benzer ve tahmin; bulunabilirlik farkı 0,3 puandan azsa az kalan kazanır."""
    k = dict([_kayit("pay_benzer_tavanli", "benzer", True, 75.0, 24.0),
              _kayit("pay_tahmin_tavanli", "tahmin", True, 75.2, 25.0),
              _kayit("pay_tahmin_tavansiz", "tahmin", False, 80.0, 20.0),
              _kayit("pay_esit", "esit", False, 90.0, 10.0)])
    s = oyun.secim_yap(k, KAL)
    assert (s["kol"], s["ad"], s["tavan"]) == ("benzer", "pay_benzer_tavanli", True)
    k["pay_tahmin_tavanli"]["olcutler"]["bulunabilirlik"] = 75.4
    assert oyun.secim_yap(k, KAL)["kol"] == "tahmin"
    k.update([_kayit("pay_benzer_tavansiz", "benzer", False, 79.9, 19.0)])
    assert oyun.secim_yap(k, {**KAL, "tavan": False})["ad"] == "pay_benzer_tavansiz"
    del k["pay_benzer_tavanli"]
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
               "tut_lumoda_t15", "tut_lumoda_t30", "tut_eniyi_t15", "tut_eniyi_t30", "tut_eniyi_t15_hiz",
               "demo_esit_t15", "demo_esit_t30", "demo_benzer_t15", "demo_benzer_t30", "sabit_esit"):
        kosular[ad] = {"cozum": oyun.cozumle(tum[ad], KAL, SECIM)}
    h = oyun.demo_haritasi(kosular, KAL)
    assert h["lumoda"] == {"0": "lumoda", "0.15": "tut_lumoda_t15", "0.3": "tut_lumoda_t30"}
    assert h["esit"] == {"0": "pay_esit", "0.15": "demo_esit_t15", "0.3": "demo_esit_t30"}
    assert h["benzer"] == {"0": "pay_benzer_tavanli", "0.15": "demo_benzer_t15", "0.3": "demo_benzer_t30"}
    assert h["tahmin"] == {"0": "pay_tahmin_tavanli", "0.15": "tut_eniyi_t15", "0.3": "tut_eniyi_t30"}


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
    ortam = oyun.Ortam(olcek="kucuk", onbellek=d / "kosular", cikti=d / "cikti")
    oyun.kos_hepsi("esdegerlik", ortam, KAL)
    G = oyun.Girdi(0, ortam, KAL)
    tum = oyun.tum_kosumlar()
    kosular = {"lumoda": G.lumoda}
    kayitlar = {}
    for ad in ("pay_esit", "pay_kahin", "pay_tahmin_tavanli", "tut_lumoda_t15_hiz", "sabit_esit", "belirsizlik"):
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
    assert d["tut_eniyi_t00"]["ayni"] == "pay_tahmin_tavanli"
    assert d["tut_eniyi_t00"]["anahtar"] == d["pay_tahmin_tavanli"]["anahtar"]
    assert not list((kucuk.dizin / "kosular").glob("tut_eniyi_t00_*"))


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
