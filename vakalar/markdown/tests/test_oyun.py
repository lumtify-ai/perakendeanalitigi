"""`markdown.oyun`: koşu adları, ızgara listesi (91 koşu), kalibrasyon seçimi, kolların kurulumu, yolun kendi
öğrenmesi (yol p'nin önbellek kimliği o yolun Lumoda koşusu), ölçümün koşu önbelleğinden yenilenmesi.

KÜÇÜK dünyada (SS25'in 32 Collection option'ı) tam pencere koşuları (~7 sn): yol 0 ve yol 1'in Lumoda'sı,
yol 0'da bir tekdüze kolu. Önbellek, öğrenme önbelleği ve çıktı modülün geçici dizininde. Kalibrasyonun
seçimi oyuncak kayıtlarla sınanır (18 koşu burada koşulmaz; KÜÇÜK uçtan uca koşu rapordadır).
"""

import datetime
import json

import numpy as np
import pandas as pd
import pytest
from allocation import motor

from markdown import hakem, kaynak, ogrenme, olcutler, oyun, politika, politika_ablasyon, sabitler, simulasyon
from markdown.ogrenme import Ogrenilen

SEZON = "SS25"


def _ayni(a, b) -> bool:
    """JSON biçiminde eşit (NaN'lı ölçütler `==` ile karşılaştırılamaz)."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def sentetik_ogrenilen(sezon=SEZON) -> Ogrenilen:
    bos = {c: pd.Series(dtype=t) for c, t in (("sezon_tipi", str), ("duzey", str), ("grup", str),
                                              ("dalga", "int64"), ("hafta", "int64"), ("carpan", float),
                                              ("kaynak", str))}
    return Ogrenilen(
        test_sezonu=sezon, bitis=datetime.date(2025, 5, 5), sezonlar=("SS23", "SS24"),
        eps_kampanya={"*": 1.8}, eps_markdown={"*": 1.28}, eps_saf=0.2, yasam=pd.DataFrame(bos),
        hafta_gunu={}, ozel_gun={},
        beden_payi=pd.DataFrame({c: pd.Series(dtype=t) for c, t in (("magaza_id", str), ("option_id", str),
                                                                     ("urun_id", str), ("pay", float))}),
        kalinti=0.13, iade={"magaza": 0.06, "online": 0.27}, islem=0.02)


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    kok = tmp_path_factory.mktemp("markdown_oyun")
    return oyun.Ortam(olcek="kucuk", onbellek=kok / "kosular", cikti=kok / "cikti", ogrenme=kok / "ogrenme")


KAL = {"olcek": "kucuk", "kural": {"alfa": 1.25}, "tekduze": {"oran": 0.30}}


# ---------------------------------------------------------------------------
# Adlar ve ızgara
# ---------------------------------------------------------------------------


def test_kol_adlari():
    assert oyun.kosu_adi(0, "lumoda") == "lumoda" and oyun.kosu_adi(3, "lumoda") == "y3_lumoda"
    assert oyun.kosu_adi(0, "opt", "SS25") == "opt_SS25"
    assert oyun.kosu_adi(2, "kahin", "AW24") == "y2_kahin_AW24"
    assert oyun.kosu_adi(0, "kural", "SS24", 1.25) == "kal_kural_a125_SS24"
    assert oyun.kosu_adi(0, "kural", "AW23", 1.0) == "kal_kural_a100_AW23"
    assert oyun.kosu_adi(0, "kural", "AW23", 0.6) == "kal_kural_a060_AW23"
    assert oyun.kosu_adi(0, "kural", "SS24", 0.8) == "kal_kural_a080_SS24"
    assert oyun.kosu_adi(0, "tekduze", "AW23", 0.30) == "kal_tekduze_30_AW23"
    assert oyun.kosu_adi(0, "tekduze", "SS24", 0.5) == "kal_tekduze_50_SS24"
    with pytest.raises(KeyError):
        oyun.kosu_adi(0, "yok", "SS25")
    with pytest.raises(ValueError):
        oyun.kosu_adi(0, "lumoda", "SS25")              # Lumoda sezonsuz
    with pytest.raises(ValueError):
        oyun.kosu_adi(0, "opt", None)                   # karar kolu tek sezon
    with pytest.raises(ValueError):
        oyun.kosu_adi(1, "kural", "SS24", 1.25)         # kalibrasyon yalnız yol 0
    with pytest.raises(ValueError):
        oyun.kosu_adi(0, "opt", "SS24", 1.0)            # kalibrasyon yalnız kural ve tekdüze
    with pytest.raises(ValueError):
        oyun.kosu_adi(0, "opt", "SS24")                 # test kolu test sezonunda
    with pytest.raises(ValueError):
        oyun.kosu_adi(0, "kural", "SS25", 1.25)         # kalibrasyon kalibrasyon sezonunda
    # Kollar spec §3.4; korunum kipi politika.KIPLER'den
    assert tuple(oyun.KOLLAR) == ("tekduze", "kural", "opt_tuzak", "opt", "opt_takvim", "opt_erken_yok",
                                  "opt_taban", "kahin", "kural_takvim", "kural_deposuz")
    assert oyun.YOL0_KOLLARI == tuple(oyun.KOLLAR)[:8] and oyun.ABLASYON_KOLLARI == ("kural_takvim", "kural_deposuz")
    assert oyun.kosu_adi(0, "kural_takvim", "SS25") == "kural_takvim_SS25"
    with pytest.raises(ValueError):
        oyun.kosu_adi(1, "kural_deposuz", "SS25")      # ayrıştırma yalnız yol 0'da
    assert {k.kip for k in oyun.KOLLAR.values()} <= set(politika.KIPLER)
    assert oyun.YOL_KOLLARI == ("tekduze", "kural", "opt_tuzak", "opt", "opt_takvim", "kahin")


def test_izgara_listesi():
    kal, y0, yp, ab = (oyun.izgara_listesi(b) for b in ("kalibrasyon", "yol0", "yollar", "ablasyon"))
    assert len(kal) == 18 and len(y0) == 1 + 16 and len(yp) == 4 * 13 and len(ab) == 4
    hepsi = kal + y0 + yp + ab
    adlar = [k.ad for k in hepsi]
    assert len(adlar) == 91 and len(set(adlar)) == 91
    assert {(k.kol, k.sezon, k.yol) for k in ab} == {(kol, s, 0) for kol in oyun.ABLASYON_KOLLARI
                                                    for s in sabitler.TEST_SEZONLARI}
    assert all(motor._AD_DESENI.match(a) for a in adlar)
    assert y0[0].ad == "lumoda" and y0[0].sezon is None and y0[0].kol == "lumoda"
    assert {(k.kol, k.sezon) for k in y0[1:]} == {(kol, s) for kol in oyun.YOL0_KOLLARI for s in sabitler.TEST_SEZONLARI}
    assert all(k.yol == 0 and k.deger is not None and k.sezon in sabitler.KAL_SEZONLARI for k in kal)
    assert sorted({(k.kol, k.deger) for k in kal}) == sorted(
        [("kural", a) for a in (0.6, 0.8, 1.0, 1.25, 1.5, 2.0)] + [("tekduze", r) for r in (0.30, 0.40, 0.50)])
    for p in range(1, 5):
        yol = [k for k in yp if k.yol == p]
        assert len(yol) == 13 and yol[0].ad == f"y{p}_lumoda"           # yolun Lumoda'sı önce
        assert {k.kol for k in yol[1:]} == set(oyun.YOL_KOLLARI)
        assert all(k.ad.startswith(f"y{p}_") for k in yol)
    assert [k.ad for k in oyun.izgara_listesi("yollar", yol=2)] == [k.ad for k in yp if k.yol == 2]
    assert oyun.izgara_listesi("hepsi") == y0 + yp
    with pytest.raises(ValueError):
        oyun.izgara_listesi("yol0", yol=1)


# ---------------------------------------------------------------------------
# Kalibrasyon seçimi (oyuncak)
# ---------------------------------------------------------------------------


def _kayitlar(katki: dict, gecersiz=()) -> dict:
    """{(kol, değer, sezon): katkı} → oyun.json kayıtları."""
    out = {}
    for (kol, d, s), v in katki.items():
        ad = oyun.kosu_adi(0, kol, s, d)
        out[ad] = {"ad": ad, "kol": kol, "deger": d, "sezon": s, "yol": 0, "olcutler": {"katki": v},
                   "gecerli": ad not in gecersiz, "anahtar": f"k-{ad}"}
    return out


def _oyuncak(alfa_katki: dict, oran_katki: dict) -> dict:
    k = {}
    for a, (aw, ss) in alfa_katki.items():
        k[("kural", a, "AW23")], k[("kural", a, "SS24")] = aw, ss
    for r, (aw, ss) in oran_katki.items():
        k[("tekduze", r, "AW23")], k[("tekduze", r, "SS24")] = aw, ss
    return k


def test_kalibrasyon_secimi():
    """İki sezonun katkı toplamı en büyük değer seçilir (iki sezona tek değer): α 1,5 AW23'te en iyi
    değil ama toplamda en iyi; geçersiz (korunumu bozuk) aday atlanır; eşitlikte ızgaranın ilk değeri;
    eksik koşu hata."""
    alfa = {0.6: (80.0, 40.0), 0.8: (85.0, 45.0), 1.0: (100.0, 50.0), 1.25: (90.0, 70.0), 1.5: (95.0, 80.0), 2.0: (120.0, 20.0)}
    oran = {0.30: (10.0, 10.0), 0.40: (12.0, 9.0), 0.50: (30.0, 1.0)}
    sec = oyun.kalibrasyon_sec(_kayitlar(_oyuncak(alfa, oran)))
    assert sec["kural"]["alfa"] == 1.5 and sec["tekduze"]["oran"] == 0.50
    t = {r["deger"]: r for r in sec["kural"]["tablo"]}
    assert t[1.5]["toplam"] == pytest.approx(175.0) and t[2.0]["AW23"] == 120.0 and t[1.0]["gecerli"]
    assert sec["tekduze"]["izgara_ucunda"] and not sec["kural"]["izgara_ucunda"]
    assert t[1.25]["kosular"] == ["kal_kural_a125_AW23", "kal_kural_a125_SS24"]

    # Geçersiz aday atlanır (toplamda en iyi olsa da)
    sec = oyun.kalibrasyon_sec(_kayitlar(_oyuncak(alfa, oran), gecersiz={"kal_kural_a150_SS24"}))
    assert sec["kural"]["alfa"] == 1.25
    assert {r["deger"]: r["gecerli"] for r in sec["kural"]["tablo"]}[1.5] is False

    # Eşitlik: ızgaranın ilk değeri
    esit = {a: (50.0, 50.0) for a in alfa}
    assert oyun.kalibrasyon_sec(_kayitlar(_oyuncak(esit, oran)))["kural"]["alfa"] == 0.6

    # Eksik koşu, bütün adaylar geçersiz
    eksik = _kayitlar(_oyuncak(alfa, oran))
    del eksik["kal_tekduze_40_SS24"]
    with pytest.raises(KeyError):
        oyun.kalibrasyon_sec(eksik)
    hepsi = _kayitlar(_oyuncak(alfa, oran), gecersiz={oyun.kosu_adi(0, "tekduze", "AW23", r) for r in oran})
    with pytest.raises(ValueError):
        oyun.kalibrasyon_sec(hepsi)


def test_kalibrasyon_oku(ortam, tmp_path):
    """Test kolları seçilen değerleri `kalibrasyon.json`'dan okur; yoksa ya da ölçek farklıysa hata."""
    o = oyun.Ortam(olcek="kucuk", onbellek=ortam.onbellek, cikti=tmp_path / "c", ogrenme=ortam.ogrenme)
    with pytest.raises(FileNotFoundError):
        oyun.kalibrasyon_oku(o)
    o.kalibrasyon_yolu.parent.mkdir(parents=True)
    o.kalibrasyon_yolu.write_text(json.dumps({**KAL, "olcek": "tam"}), encoding="utf-8")
    with pytest.raises(ValueError):
        oyun.kalibrasyon_oku(o)
    o.kalibrasyon_yolu.write_text(json.dumps(KAL), encoding="utf-8")
    assert oyun.kalibrasyon_oku(o) == {"kural": 1.25, "tekduze": 0.30}


# ---------------------------------------------------------------------------
# Kolların kurulumu ve yolun öğrenmesi
# ---------------------------------------------------------------------------


def test_kol_kurulumu(ortam, monkeypatch):
    """Her kol spec §3.4'teki sınıf, kip ve ε kaynağıyla kurulur; kalibrasyon değeri (test kolunda
    `kalibrasyon.json`'dan, kalibrasyonda koşumun kendi değeri) kolun `parametreler()`'ine, yani
    anahtara girer; kahin yolun (paylaşılan) kahin girdisini alır. Simülasyon koşmaz."""
    Y = oyun.Yol(0, ortam)
    monkeypatch.setattr(Y, "ogrenilen", lambda sezon: sentetik_ogrenilen(sezon))
    monkeypatch.setattr(Y, "kahin_girdisi", lambda sezon: hakem.kahin_girdisi(Y.w, Y.test_idx(sezon)))
    kal = {"kural": 1.25, "tekduze": 0.40}
    temel = motor.lumoda("markdown")
    beklenen = {"tekduze": (politika.Tekduze, None, None), "kural": (politika.Kural, None, None),
                "opt_tuzak": (politika.Optimizasyon, "serbest", "markdown"),
                "opt": (politika.Optimizasyon, "serbest", "kampanya"),
                "opt_takvim": (politika.Optimizasyon, "takvim", "kampanya"),
                "opt_erken_yok": (politika.Optimizasyon, "erken_yok", "kampanya"),
                "opt_taban": (politika.Optimizasyon, "taban", "kampanya"),
                "kahin": (politika.Kahin, "serbest", "kampanya")}
    for kol, (sinif, kip, eps) in beklenen.items():
        k = oyun.Kosum(oyun.kosu_adi(0, kol, SEZON), 0, kol, SEZON)
        p = Y.kol_kur(k, kal)(temel)
        assert type(p) is sinif and p.temel is temel, kol
        assert np.array_equal(p.test_idx, kaynak.test_optionlari(Y.w.optionlar, SEZON))
        prm = p.parametreler()
        if kip is not None:
            assert (prm["kip"], prm["eps"]) == (kip, eps) and oyun.KOLLAR[kol].kip == kip
    assert Y.kol_kur(oyun.Kosum("x", 0, "kural", SEZON), kal)(temel).parametreler()["alfa"] == 1.25
    for kol, sinif in politika_ablasyon.KOLLAR.items():
        p = Y.kol_kur(oyun.Kosum(oyun.kosu_adi(0, kol, SEZON), 0, kol, SEZON), kal)(temel)
        assert type(p) is sinif and p.parametreler()["alfa"] == 1.25 and p.parametreler()["kol"] == kol
        with pytest.raises(ValueError):
            Y.kol_kur(oyun.Kosum("x", 0, kol, SEZON), None)                   # α kalibrasyondan
    assert Y.kol_kur(oyun.Kosum("x", 0, "tekduze", SEZON), kal)(temel).parametreler()["oran"] == 0.40
    kk = oyun.Kosum(oyun.kosu_adi(0, "kural", "SS24", 2.0), 0, "kural", "SS24", 2.0)
    assert Y.kol_kur(kk, None)(temel).parametreler()["alfa"] == 2.0          # kalibrasyon: kendi değeri
    with pytest.raises(ValueError):
        Y.kol_kur(oyun.Kosum("x", 0, "kural", SEZON), None)                  # test kolu kalibrasyon ister


def test_yol_kendi_ogrenmesi(ortam, monkeypatch):
    """Yol p > 0 (ve KÜÇÜK yol 0) öğrenmeyi kendi Lumoda koşusunun yayımlanan biçiminden yapar ve öğrenme
    önbelleğinin kaynak kimliği o koşunun anahtarıdır (T5 ⚠️: yoksa yol p sessizce yol 0'ın öğrenmesini
    okurdu); iki test sezonu tek bağlantıda, bir kez. TAM yol 0 yayımlanan dosyadan (varsayılan kimlik).
    Kahin girdisi yollar arasında paylaşılır (λ aynı)."""
    cagri = []

    def sahte(con, sezon, bitis, onbellek=None, kaynak_kimligi=None):
        tablolar = {r[0]: con.execute(f"select count(*) from {r[0]}").fetchone()[0]
                    for r in con.execute("show tables").fetchall()}
        cagri.append((sezon, str(bitis), onbellek, kaynak_kimligi, tablolar))
        return sentetik_ogrenilen(sezon)

    monkeypatch.setattr(ogrenme, "ogren", sahte)
    paylasilan = {}
    Y0, Y1 = oyun.Yol(0, ortam, paylasilan), oyun.Yol(1, ortam, paylasilan)
    for Y in (Y0, Y1):
        for s in sabitler.TEST_SEZONLARI:
            assert Y.ogrenilen(s).test_sezonu == s
        Y.ogrenilen(SEZON)                                                  # ikinci çağrı öğrenmez
    assert len(cagri) == 4
    assert Y0.lumoda.meta["anahtar"] != Y1.lumoda.meta["anahtar"]
    for (sezon, bitis, onb, kimlik, tablolar), Y in zip(cagri, (Y0, Y0, Y1, Y1)):
        assert bitis == sabitler.OGRENME_BITIS[sezon] and onb == ortam.ogrenme
        assert kimlik == Y.lumoda.meta["anahtar"]
        assert {a: len(df) for a, df in simulasyon.yayimlanan(Y.lumoda).items()} == tablolar   # içerik aynı
    assert Y1.kaynak_adi == f"vaka:{Y1.lumoda.dizin.name}"
    assert oyun.Ortam(olcek="tam").yayimlanan_mi(0) and not oyun.Ortam(olcek="tam").yayimlanan_mi(1)
    assert not ortam.yayimlanan_mi(0)
    assert Y0.kahin_girdisi(SEZON) is Y1.kahin_girdisi(SEZON)


# ---------------------------------------------------------------------------
# Ölçüm önbelleği
# ---------------------------------------------------------------------------


def test_olcum_kodu_kapsami():
    """Ölçüm kodu özeti içe aktarma anında bir kez kurulur; ölçütler ve hakem modülünü ve oyun'un ölçüm
    işlevlerini kapsar; kaynak ya da `OLCUM_SURUMU` değişince değişir."""
    assert oyun.olcum_kodu() == oyun.OLCUM_OZETI
    m = oyun.olcum_metinleri()
    assert {"olcutler.py", "hakem.py", "olcum_kaydi"} <= set(m)
    taban = oyun.olcum_ozeti(m, oyun.OLCUM_SURUMU)
    assert taban == oyun.OLCUM_OZETI
    assert oyun.olcum_ozeti(m | {"olcum_kaydi": "değişti"}, oyun.OLCUM_SURUMU) != taban
    assert oyun.olcum_ozeti(m, oyun.OLCUM_SURUMU + 1) != taban


def test_olcum_onbellekten(ortam, monkeypatch):
    """Yol 0'ın Lumoda'sı ve tekdüze kolu (SS25) baştan sona: `oyun.json` kaydı (ölçütler, çeyrek, korunum,
    yan etki, geçerlilik), option tablosu, `ilerleme.jsonl`; yeniden çağrı koşmaz ve ölçmez; ölçüm kodu
    değişince yalnız yeniden ölçer (koşu önbellekten)."""
    ortam.kalibrasyon_yolu.parent.mkdir(parents=True, exist_ok=True)
    ortam.kalibrasyon_yolu.write_text(json.dumps(KAL), encoding="utf-8")
    adlar = {"lumoda", "tekduze_SS25"}
    kayit = oyun.kos_hepsi("yol0", ortam, adlar=adlar)
    t = kayit["kosular"]["tekduze_SS25"]
    lum = kayit["kosular"]["lumoda"]
    assert set(kayit["kosular"]) == adlar
    assert t["kol"] == "tekduze" and t["sezon"] == SEZON and t["yol"] == 0 and t["gecerli"]
    assert t["parametreler"]["oran"] == 0.30 and t["parametreler"]["test_option_sayisi"] == 32
    assert all(t["korunum"].values()) and len(t["ceyrek"]) == 4
    assert t["olcutler"]["option_sayisi"] == 32 and np.isnan(t["isabet"]["wape"])
    assert {"ciro_farki_test_disi", "elle_transfer_farki"} <= set(t["yan_etki"])
    assert set(lum["olcutler"]) == set(sabitler.TEST_SEZONLARI + sabitler.KAL_SEZONLARI)
    assert t["lumoda_anahtar"] == lum["anahtar"]
    # option tablosu diskte; ölçütleri yeniden kurar
    tab = pd.read_parquet(ortam.cikti / t["option_tablosu"])
    assert olcutler.ozetle(tab)["katki"] == pytest.approx(t["olcutler"]["katki"])
    # Lumoda'nın çeyrek toplamı bütün
    assert sum(c["katki"] for c in lum["ceyrek"][SEZON]) == pytest.approx(lum["olcutler"][SEZON]["katki"])
    # İki test sezonunun toplamı (Lumoda'nın iki sezonu bir koşuda; tekdüzenin AW24'ü koşulmadı)
    top = kayit["toplamlar"]["0"]
    assert set(top) == {"lumoda"} and top["lumoda"]["gecerli"]
    assert top["lumoda"]["olcutler"]["katki"] == pytest.approx(
        sum(lum["olcutler"][s]["katki"] for s in sabitler.TEST_SEZONLARI))
    disk = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    assert disk["kosular"]["tekduze_SS25"]["anahtar"] == t["anahtar"] and disk["olcek"] == "kucuk"
    satirlar = [json.loads(s) for s in ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()]
    assert any(s["ad"] == "tekduze_SS25" and not s["onbellekten"] for s in satirlar)
    dizinler = sorted(p.name for p in ortam.onbellek.iterdir())

    ikinci = oyun.kos_hepsi("yol0", ortam, adlar=adlar)["kosular"]
    assert _ayni(ikinci["tekduze_SS25"], t) and _ayni(ikinci["lumoda"], lum)           # yeniden ölçülmedi
    monkeypatch.setattr(oyun, "olcum_kodu", lambda: "baska")
    ucuncu = oyun.kos_hepsi("yol0", ortam, adlar=adlar)["kosular"]["tekduze_SS25"]
    assert ucuncu["olcum_kodu"] == "baska" and ucuncu["anahtar"] == t["anahtar"]
    assert _ayni(ucuncu["olcutler"], t["olcutler"]) and ucuncu["olcum_sn"] is not None
    son = json.loads(ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()[-1])
    assert son["ad"] == "tekduze_SS25" and son["onbellekten"]
    assert sorted(p.name for p in ortam.onbellek.iterdir()) == dizinler       # yeni simülasyon yok


def test_gecersiz_kosu_isaretlenir(ortam, monkeypatch):
    """Korunumu bozuk koşu hata vermez, `gecerli: False` işaretlenir (rapor reddeder)."""
    monkeypatch.setattr(oyun, "olcum_kodu", lambda: "bozuk")
    gercek_korunum = olcutler.korunum
    monkeypatch.setattr(olcutler, "korunum", lambda *a, **k: {**gercek_korunum(*a, **k), "rpt_birebir": False})
    t = oyun.kos_hepsi("yol0", ortam, adlar={"tekduze_SS25"})["kosular"]["tekduze_SS25"]
    assert t["gecerli"] is False and t["korunum"]["rpt_birebir"] is False
