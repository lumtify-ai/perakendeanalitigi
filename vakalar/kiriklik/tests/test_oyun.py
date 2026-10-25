"""`kiriklik.oyun`: ızgara listesi (47 koşu), plan önbelleği (anahtar, kod özeti, girdinin kaynağı), kahin fiyat sırası,
ölçüm kodu özeti; KÜÇÜK dünyada uçtan uca yol 0 bloğu, ölçüm önbelleği, geçersiz koşu, yol 1'in planının girdisi ve
kahin girdisinin gerçek Lumoda koşusuyla duman testi (`veri`).

KÜÇÜK koşular tam pencere (~20 sn); önbellek, öğrenme önbelleği, planlar ve `oyun.json` modülün geçici dizininde
(varsayılan `cikti/kosular/`'a hiçbir şey yazılmaz).
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from allocation import motor

from kiriklik import hakem, kaynak, olcutler, oyun, sabitler, simulasyon, tahmin
from kiriklik import plan as plan_modulu
from kiriklik.plan import Plan

SEZON = "AW24"


# ---------------------------------------------------------------------------
# Izgara
# ---------------------------------------------------------------------------


def test_izgara_47():
    """TAM ızgara (K12): Lumoda 5 + {kural, opt, opt_set, kahin} × 2 sezon × 5 yol + kural_28 × 2 sezon (yol 0) = 47;
    adlar tekil; bloklar yol0 (9), ablasyon (2), yollar (36; `--yol P` 9) sırayla ızgaranın kendisi. KÜÇÜK ızgara
    aynı."""
    liste = oyun.izgara_listesi("tam")
    assert len(liste) == 47 and len({i.ad for i in liste}) == 47
    assert oyun.KOLLAR == ("kural", "kural_28", "opt", "opt_set", "kahin")
    say = pd.Series([i.kol for i in liste]).value_counts().to_dict()
    assert say == {"lumoda": 5, "kural": 10, "opt": 10, "opt_set": 10, "kahin": 10, "kural_28": 2}
    assert {i.yol for i in liste if i.kol == "kural_28"} == {0}
    assert {i.ad for i in liste if i.kol == "lumoda"} == {"lumoda", "y1_lumoda", "y2_lumoda", "y3_lumoda", "y4_lumoda"}
    assert oyun.Is("kural", "AW24", 0).ad == "kural_AW24" and oyun.Is("kahin", "SS25", 3).ad == "y3_kahin_SS25"
    assert oyun.Is("lumoda", None, 2).ad == "y2_lumoda"
    bloklar = {b: oyun.blok_listesi(b) for b in oyun.BLOKLAR}
    assert {b: len(v) for b, v in bloklar.items()} == {"yol0": 9, "ablasyon": 2, "yollar": 36}
    assert bloklar["yol0"][0] == oyun.Is("lumoda", None, 0)
    assert bloklar["yol0"] + bloklar["ablasyon"] + bloklar["yollar"] == liste == oyun.blok_listesi("hepsi")
    y2 = oyun.blok_listesi("yollar", yol=2)
    assert len(y2) == 9 and {i.yol for i in y2} == {2} and y2[0].kol == "lumoda"
    assert oyun.izgara_listesi("kucuk") == liste
    with pytest.raises(ValueError, match="blok"):
        oyun.blok_listesi("kalibrasyon")
    with pytest.raises(ValueError, match="yol 3"):
        oyun.blok_listesi("yol0", yol=3)
    with pytest.raises(ValueError, match="ölçek"):
        oyun.izgara_listesi("orta")
    for kol, sezon, yol in (("kural_28", "AW24", 1), ("kural", "AW23", 0), ("baska", "AW24", 0), ("lumoda", "AW24", 0)):
        with pytest.raises(ValueError):
            oyun.Is(kol, sezon, yol).ad


# ---------------------------------------------------------------------------
# Plan önbelleği (oyuncak: plan hesabı yerine sahte plan)
# ---------------------------------------------------------------------------


def _sahte_lumoda(yol=0, anahtar="a" * 64, olcek="kucuk"):
    return SimpleNamespace(meta={"turler": {}, "parametreler": {"yol": yol}, "olcek": olcek, "anahtar": anahtar})


def _sahte_plan(kol, sezon):
    h = pd.DataFrame([("A", "A-2", 2, "S2", "S1", 2), ("A", "A-3", 3, "S3", "S1", 1)], columns=plan_modulu.KOLONLAR)
    bilgi = {"cozum": "kural", "puanlar": [{"magaza_id": "S1", "option_id": "A", "puan": 1.5}] * 3,
             "durum": "optimal", "gap": np.float64(0.01)}
    return Plan(kol=kol, sezon=sezon, hareketler=h, bilgi=bilgi)


@pytest.fixture
def sahte(tmp_path, monkeypatch):
    """Plan hesabı sayılır ve sahte planla değiştirilir; ortam geçici dizinde."""
    cagri = []

    def hesapla(kol, sezon, girdiler):
        cagri.append((kol, sezon, girdiler.yol))
        return _sahte_plan(kol, sezon)

    monkeypatch.setattr(oyun, "_plan_hesapla", hesapla)
    ortam = oyun.Ortam(olcek="kucuk", onbellek=tmp_path / "kosular", cikti=tmp_path / "cikti")
    return SimpleNamespace(cagri=cagri, ortam=ortam)


def test_plan_onbellegi_kod_degisince_yenilenir(sahte, monkeypatch):
    """Plan `cikti/planlar/<kol>_<sezon>_y<yol>_<anahtar[:20]>` (.parquet + .json) olarak yazılır; ikinci çağrı
    önbellekten okur (hesaplamaz, aynı kimlik); karar kapanışının kod özeti ya da Lumoda anahtarı değişince anahtar
    değişir ve plan yeniden hesaplanır (eski dosya yerinde). JSON: anahtar, içerik, kimlik, bilgi (girdi; kuralın
    puan tablosu yerine sayısı)."""
    ortam, lum = sahte.ortam, _sahte_lumoda()
    Y = oyun.Yol(0, ortam, lumoda=lum)
    p = oyun.plan_kur("kural", SEZON, 0, "kucuk", lum, ortam=ortam, girdiler=Y)
    assert sahte.cagri == [("kural", SEZON, 0)]
    icerik = oyun.plan_icerigi("kural", SEZON, 0, "kucuk", lum.meta["anahtar"])
    anahtar = oyun.plan_anahtari(icerik)
    assert icerik["kod"] == oyun.karar_kod_ozeti("kural") and icerik["lumoda_anahtari"] == "a" * 64
    kok = ortam.planlar / f"kural_{SEZON}_y0_{anahtar[:20]}"
    assert kok.with_suffix(".parquet").exists()
    disk = json.loads(kok.with_suffix(".json").read_text(encoding="utf-8"))
    assert disk["anahtar"] == anahtar and disk["kimlik"] == p.kimlik and disk["icerik"] == icerik
    assert disk["bilgi"]["girdi"] == {"yol": 0, "lumoda_anahtari": "a" * 64}
    assert "puanlar" not in disk["bilgi"] and disk["bilgi"]["puan_sayisi"] == 3
    assert p.bilgi == disk["bilgi"] and p.bilgi["gap"] == 0.01

    q = oyun.plan_kur("kural", SEZON, 0, "kucuk", lum, ortam=ortam, girdiler=Y)
    assert len(sahte.cagri) == 1 and q.kimlik == p.kimlik
    pd.testing.assert_frame_equal(q.hareketler, p.hareketler)
    assert oyun.plan_kur("opt", SEZON, 0, "kucuk", lum, ortam=ortam, kur=False) is None      # kurmadan: yok

    gercek_kod = oyun.karar_kod_ozeti
    monkeypatch.setattr(oyun, "karar_kod_ozeti", lambda kol: "degisti")
    oyun.plan_kur("kural", SEZON, 0, "kucuk", lum, ortam=ortam, girdiler=Y)
    assert len(sahte.cagri) == 2
    assert len(list(ortam.planlar.glob("kural_*.json"))) == 2
    monkeypatch.setattr(oyun, "karar_kod_ozeti", gercek_kod)
    lum2 = _sahte_lumoda(anahtar="b" * 64)
    oyun.plan_kur("kural", SEZON, 0, "kucuk", lum2, ortam=ortam, girdiler=oyun.Yol(0, ortam, lumoda=lum2))
    assert len(sahte.cagri) == 3
    assert oyun.plan_anahtari(oyun.plan_icerigi("kural", SEZON, 1, "kucuk", "a" * 64)) != anahtar
    assert oyun.plan_anahtari(oyun.plan_icerigi("kural_28", SEZON, 0, "kucuk", "a" * 64)) != anahtar


def test_plan_girdisi_denetlenir(sahte):
    """Planın girdisi yolun kendi Lumoda'sıdır: başka yolun Lumoda'sı, başka yolun girdileri, başka Lumoda'nın
    girdileri `ValueError`; önbellekteki planın `bilgi["girdi"]`'si istenen (yol, Lumoda anahtarı) değilse okunmaz,
    `ValueError` (yol p'nin kararı yol 0 verisinden kurulmuş olamaz)."""
    ortam = sahte.ortam
    lum0, lum1 = _sahte_lumoda(0, "a" * 64), _sahte_lumoda(1, "c" * 64)
    with pytest.raises(ValueError, match="yol"):
        oyun.plan_kur("kural", SEZON, 1, "kucuk", lum0, ortam=ortam)
    with pytest.raises(ValueError, match="yol"):
        oyun.plan_kur("kural", SEZON, 1, "kucuk", lum1, ortam=ortam, girdiler=oyun.Yol(0, ortam, lumoda=lum0))
    with pytest.raises(ValueError, match="Lumoda"):
        oyun.plan_kur("kural", SEZON, 0, "kucuk", lum0, ortam=ortam,
                      girdiler=oyun.Yol(0, ortam, lumoda=_sahte_lumoda(0, "d" * 64)))
    with pytest.raises(ValueError, match="ölçek uyuşmuyor"):
        oyun.plan_kur("kural", SEZON, 0, "tam", lum0, ortam=ortam)
    with pytest.raises(ValueError, match="Lumoda koşusu"):
        oyun.Yol(0, ortam, lumoda=SimpleNamespace(meta={**lum0.meta, "turler": {"rpt": "x"}}))
    assert sahte.cagri == []

    oyun.plan_kur("kural", SEZON, 1, "kucuk", lum1, ortam=ortam, girdiler=oyun.Yol(1, ortam, lumoda=lum1))
    dosya = next(ortam.planlar.glob("kural_*_y1_*.json"))
    d = json.loads(dosya.read_text(encoding="utf-8"))
    d["bilgi"]["girdi"] = {"yol": 0, "lumoda_anahtari": "a" * 64}
    dosya.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="girdi"):
        oyun.plan_kur("kural", SEZON, 1, "kucuk", lum1, ortam=ortam, kur=False)


def test_karar_kod_ozeti_kapsami(tmp_path):
    """Karar kapanışının dosyaları: kiriklik karar modülleri, `markdown` ogrenme / kaynak / sabitler, onların
    `perakende_analitik` kapanışı; `kahin`'de ayrıca `hakem.py`. Özet içerikten (satır sonları LF) ve dosya adından."""
    k = oyun.karar_kod_dosyalari("kural")
    assert {f"kiriklik/{m}.py" for m in oyun.KARAR_MODULLERI} <= set(k)
    assert {"markdown/ogrenme.py", "markdown/kaynak.py", "markdown/sabitler.py"} <= set(k)
    ortak = {a for a in k if a.startswith("ortak/")}
    assert {"ortak/kaynak.py", "ortak/carpanlar.py", "ortak/hazirlik.py"} <= ortak
    assert "kiriklik/hakem.py" not in k and "kiriklik/simulasyon.py" not in k
    assert set(oyun.karar_kod_dosyalari("kahin")) == set(k) | {"kiriklik/hakem.py"}
    assert oyun.karar_kod_ozeti("kahin") != oyun.karar_kod_ozeti("opt") == oyun.karar_kod_ozeti("kural")

    kopya = {}
    for ad, yol in k.items():
        y = tmp_path / ad.replace("/", "_")
        y.write_bytes(yol.read_bytes().replace(b"\r\n", b"\n"))
        kopya[ad] = y
    taban = oyun.kod_ozeti(kopya)
    assert taban == oyun.kod_ozeti(k)
    y = kopya["kiriklik/model.py"]
    y.write_bytes(y.read_bytes().replace(b"\n", b"\r\n"))
    assert oyun.kod_ozeti(kopya) == taban
    y = kopya["markdown/ogrenme.py"]
    y.write_bytes(y.read_bytes() + b"\n# degisti\n")
    assert oyun.kod_ozeti(kopya) != taban


def test_kahin_fiyat_sirasi():
    """Ruling R17: kahin girdisinde her hücrede fiyat_tam ≥ fiyat_ind ≥ 0; bozan hücreler adlarıyla `ValueError`."""
    t = pd.DataFrame({"magaza_id": ["M1", "M2", "M3"], "urun_id": ["U1", "U2", "U3"], "mu_tam": 1.0, "mu_ind": 1.0,
                      "fiyat_tam": [100.0, 50.0, 80.0], "fiyat_ind": [70.0, 60.0, -1.0]})
    oyun.kahin_fiyat_denetimi(t.iloc[:1])
    with pytest.raises(ValueError, match=r"2 hücre.*M2.*U2.*M3.*U3"):
        oyun.kahin_fiyat_denetimi(t)
    with pytest.raises(ValueError, match="M1"):
        oyun.kahin_fiyat_denetimi(t.iloc[:1].assign(fiyat_ind=np.nan))


def test_olcum_kodu_kapsami():
    """Ölçüm kodu özeti içe aktarma anında bir kez: `olcutler.py` ve onun içe aktardığı kiriklik modülleri, oyun'un
    ölçüm işlevleri, `OLCUM_SURUMU`; biri değişince değişir."""
    assert oyun.olcum_kodu() == oyun.OLCUM_OZETI and oyun.OLCUM_SURUMU == 1
    m = oyun.olcum_metinleri()
    ice = {a.split(".")[1] for a in motor.ice_aktarimlar(oyun.PAKET_KOKU / "olcutler.py", "kiriklik")
           if a.startswith("kiriklik.") and a.count(".") == 1}
    assert {f"kiriklik/{a}.py" for a in ice | {"olcutler"}} | set(oyun.OLCUM_FONKSIYONLARI) == set(m)
    taban = oyun.olcum_ozeti(m, oyun.OLCUM_SURUMU)
    assert taban == oyun.OLCUM_OZETI
    assert oyun.olcum_ozeti(m | {"olcum_kaydi": "değişti"}, 1) != taban
    assert oyun.olcum_ozeti(m | {"kiriklik/olcu.py": "değişti"}, 1) != taban
    assert oyun.olcum_ozeti(m, 2) != taban


# ---------------------------------------------------------------------------
# KÜÇÜK dünya (veri)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    kok = tmp_path_factory.mktemp("kiriklik_oyun")
    o = oyun.Ortam(olcek="kucuk", onbellek=kok / "kosular", cikti=kok / "cikti")
    assert o.onbellek != simulasyon.KOSU_DIZINI
    return o


@pytest.fixture(scope="module")
def izgara0(ortam):
    """KÜÇÜK yol 0 bloğu: Lumoda + 4 kol × 2 sezon (planlar ve koşular), sonra ölçüm."""
    kosular = oyun.izgara("yol0", "kucuk", ortam=ortam)
    kayit = oyun.olc(olcek="kucuk", ortam=ortam)
    return kosular, kayit


def _yaprak(x, yol=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _yaprak(v, f"{yol}.{k}")
    else:
        yield yol, x


def _ayni_olcum(a: dict, b: dict) -> bool:
    """Aynı koşunun iki ölçümü: aynı alanlar, sayılar 1e-9 göreli yakın (DuckDB'nin paralel toplamı TL toplamlarının son
    basamaklarını çağrıdan çağrıya değiştirir)."""
    x, y = dict(_yaprak(a)), dict(_yaprak(b))
    return x.keys() == y.keys() and all(
        x[k] == y[k] or (isinstance(x[k], float) and y[k] == pytest.approx(x[k], rel=1e-9, abs=1e-6)) for k in x)


def _satirlar(ortam) -> list[dict]:
    return [json.loads(s) for s in ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()]


@pytest.mark.veri
def test_kucuk_izgara_yol0(izgara0, ortam):
    """Uçtan uca: 9 koşu; 8 kol koşusunun korunumu hepsi True, geçerli ve ölçülmüş; `oyun.json` kaydı koşu, Lumoda ve
    plan kimliklerini ve ölçüm kodunu taşır; planlar önbellekte, girdisi yol 0'ın Lumoda'sı; ilerleme satırları."""
    kosular, kayit = izgara0
    beklenen = [i.ad for i in oyun.blok_listesi("yol0")]
    assert [k["ad"] for k in kosular] == beklenen
    lum = kayit["lumoda"]["0"]
    assert lum["ad"] == "lumoda" and len(lum["anahtar"]) == 64
    disk = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    assert disk == kayit and disk["olcek"] == "kucuk"
    assert sorted(kayit["kosular"]) == sorted(beklenen[1:])
    Y = oyun.Yol(0, ortam)
    for ad, r in kayit["kosular"].items():
        assert r["gecerli"] is True and all(r["korunum"].values()), (ad, r["korunum"])
        assert tuple(r["korunum"]) == olcutler.KORUNUM_KOSULLARI
        assert r["lumoda_anahtari"] == lum["anahtar"] and r["olcum_ozeti"] == oyun.OLCUM_OZETI
        assert r["yol"] == 0 and f"{r['kol']}_{r['sezon']}" == ad
        p = Y.plan(r["kol"], r["sezon"], kur=False)
        assert p is not None and p.kimlik == r["plan_kimligi"]
        assert p.bilgi["girdi"] == {"yol": 0, "lumoda_anahtari": lum["anahtar"]}
        o = r["olcum"]
        assert set(o) == {"sezon", "tarihler", "kiriklik", "satisa_donus", "para", "stok", "yan_etki", "plan"}
        assert o["plan"]["hareket"] == len(p.hareketler) and o["plan"]["adet"] == int(p.hareketler["adet"].sum())
        assert o["stok"]["sezon"]["olu_stok"] is not None                  # tam pencere: çıkış + 120 kapsanır
        assert o["para"]["net"]["orta"] is not None
    assert any(kayit["kosular"][f"{k}_{SEZON}"]["olcum"]["plan"]["hareket"] > 0 for k in oyun.ANA_KOLLAR)
    assert kayit["kosular"]["kahin_AW24"]["olcum"]["plan"]["cozucu"]["durum"] in ("optimal", "dugum_siniri")
    assert len(list(ortam.planlar.glob("*.parquet"))) == len(list(ortam.planlar.glob("*.json"))) == 8
    satir = _satirlar(ortam)
    turler = {s.get("tur") for s in satir}
    assert {"kosu", "plan", "olcum", "ogrenme"} <= turler
    assert all("surec_tepe_gb" in s for s in satir if s.get("tur") in ("kosu", "plan", "olcum"))


@pytest.mark.veri
def test_olcum_onbellegi(izgara0, ortam, monkeypatch):
    """Koşu, Lumoda ve plan kimlikleri ile ölçüm kodu aynıysa yeniden ölçülmez; ölçüm kodu değişince ya da `zorla`
    ile yeniden ölçülür (koşu önbellekten okunur, yeni simülasyon yok)."""
    _, ilk = izgara0
    cagri = []
    gercek_olc = olcutler.olc
    monkeypatch.setattr(olcutler, "olc", lambda *a, **k: cagri.append(1) or gercek_olc(*a, **k))
    dizinler = sorted(p.name for p in ortam.onbellek.iterdir())
    ikinci = oyun.olc(olcek="kucuk", ortam=ortam)
    assert cagri == [] and ikinci["kosular"] == ilk["kosular"]
    gercek_kod = oyun.olcum_kodu
    monkeypatch.setattr(oyun, "olcum_kodu", lambda: "baska")
    ucuncu = oyun.olc(olcek="kucuk", ortam=ortam)
    assert len(cagri) == 8 and all(r["olcum_ozeti"] == "baska" for r in ucuncu["kosular"].values())
    assert all(_ayni_olcum(ucuncu["kosular"][a]["olcum"], ilk["kosular"][a]["olcum"]) for a in ilk["kosular"])
    oyun.olc(olcek="kucuk", ortam=ortam)
    assert len(cagri) == 8
    monkeypatch.setattr(oyun, "olcum_kodu", gercek_kod)
    son = oyun.olc(zorla=True, olcek="kucuk", ortam=ortam)                # kod geri döndü; zorla
    assert len(cagri) == 16 and all(r["olcum_ozeti"] == oyun.OLCUM_OZETI for r in son["kosular"].values())
    assert sorted(p.name for p in ortam.onbellek.iterdir()) == dizinler
    son = [s for s in _satirlar(ortam) if s.get("tur") == "olcum" and "olculdu" in s][-1]
    assert son["olculdu"] is True
    atlanan = {s["ad"]: s["atlandi"] for s in _satirlar(ortam) if s.get("tur") == "olcum" and "atlandi" in s}
    assert atlanan["kural_28_AW24"] == "plan önbellekte yok" and atlanan["y1_lumoda"] == "Lumoda koşusu önbellekte yok"


@pytest.mark.veri
def test_gecersiz_kosu_olculmez(izgara0, ortam, monkeypatch):
    """Planın bir satırı vericinin karar günü stoğunu aşarsa motor keser: `kural_28` AW24 koşusunun korunumu
    (`plan_kesilmedi`) False; `oyun.json` kaydı `gecerli: false`, ölçüm yok (`olcutler.olc` çağrılmaz)."""
    Y = oyun.Yol(0, ortam)
    g = Y.karar_girdisi(SEZON)
    Y.girdileri_birak()
    h = g.hucre[g.hucre["stok"] >= 1].sort_values(["option_id", "magaza_id", "beden_sira"]).iloc[0]
    alici = sorted(set(g.hucre.loc[(g.hucre["option_id"] == h.option_id), "magaza_id"]) - {h.magaza_id})[0]
    kesik = Plan(kol="kural_28", sezon=SEZON, hareketler=pd.DataFrame(
        [(h.option_id, h.urun_id, int(h.beden_sira), h.magaza_id, alici, int(h.stok) + 50)],
        columns=plan_modulu.KOLONLAR), bilgi={"girdi": {"yol": 0, "lumoda_anahtari": Y.lumoda.meta["anahtar"]}})
    icerik = oyun.plan_icerigi("kural_28", SEZON, 0, "kucuk", Y.lumoda.meta["anahtar"])
    oyun.plan_yaz(ortam, kesik, icerik)
    k = Y.kos(oyun.Is("kural_28", SEZON, 0))
    assert k.meta["politikalar"]["elle_transfer"]["parametreler"]["plan"] == kesik.kimlik
    cagri = []
    gercek_olc = olcutler.olc
    monkeypatch.setattr(olcutler, "olc", lambda *a, **kw: cagri.append(a) or gercek_olc(*a, **kw))
    r = oyun.olc(olcek="kucuk", ortam=ortam)["kosular"]["kural_28_AW24"]
    assert r["gecerli"] is False and r["olcum"] is None and r["korunum"]["plan_kesilmedi"] is False
    assert r["korunum"]["oncesi_birebir"] is True and r["plan_kimligi"] == kesik.kimlik
    assert cagri == []
    satir = [s for s in _satirlar(ortam) if s.get("ad") == "kural_28_AW24" and s.get("tur") == "olcum"][-1]
    assert satir["gecerli"] is False


@pytest.mark.veri
def test_plan_girdisi_yolun_lumodasindan(izgara0, ortam, monkeypatch):
    """Review Focus: yol 1'in planları yol 1'in Lumoda koşusunun yayımlanan biçiminden kurulur (karar girdisinin
    bağlantısındaki tablolar o koşunun yayımlanan biçimiyle aynı boyda) ve `bilgi["girdi"]["lumoda_anahtari"]` yol 1
    Lumoda'nınkidir (yol 0'ınki değil). `planlar` simüle etmez; Lumoda koşusu yoksa `ValueError`."""
    with pytest.raises(ValueError, match="önbellekte yok"):
        oyun.planlar("yollar", "kucuk", yol=2, ortam=ortam)
    lum1 = oyun.Yol(1, ortam).lumoda
    lum0 = oyun.Yol(0, ortam).lumoda
    assert lum1.meta["anahtar"] != lum0.meta["anahtar"] and lum1.meta["parametreler"]["yol"] == 1
    boylar = []
    gercek = kaynak.karar_girdisi

    def casus(con, sezon):
        boylar.append({r[0]: con.execute(f"select count(*) from {r[0]}").fetchone()[0]
                       for r in con.execute("show tables").fetchall()})
        return gercek(con, sezon)

    monkeypatch.setattr(kaynak, "karar_girdisi", casus)
    dizinler = sorted(p.name for p in ortam.onbellek.iterdir())
    planlar = oyun.planlar("yollar", "kucuk", yol=1, ortam=ortam)
    assert sorted(planlar) == sorted(f"{k}_{s}_y1" for k in oyun.ANA_KOLLAR for s in sabitler.TEST_SEZONLARI)
    for p in planlar.values():
        assert p.bilgi["girdi"] == {"yol": 1, "lumoda_anahtari": lum1.meta["anahtar"]}
    assert len(boylar) == 2
    yayimlanan = {a: len(df) for a, df in simulasyon.yayimlanan(lum1).items()}
    assert all(b == yayimlanan for b in boylar)
    assert sorted(p.name for p in ortam.onbellek.iterdir()) == dizinler                      # simülasyon yok
    with pytest.raises(ValueError, match="yol"):
        oyun.plan_kur("kural", SEZON, 1, "kucuk", lum0, ortam=ortam)


@pytest.mark.veri
def test_kahin_girdisi_gercek_lumoda(izgara0, ortam):
    """Duman testi (Görev 6 yalnız oyuncak takvimle sınamıştı): `hakem.kahin_girdisi` gerçek KÜÇÜK Lumoda koşusuyla
    (`motor.takvim` kayıtlı markdown kararlarından) tahminin hücrelerini aynı sırada verir; talep pozitif; fiyat sırası
    tutar (R17); indirim evresinin fiyatı Lumoda'nın en az %30 indirimini taşır (liste × 0,70 × (1 − iade) altında)."""
    Y = oyun.Yol(0, ortam)
    for sezon in sabitler.TEST_SEZONLARI:
        g, og, talep = Y.karar_girdisi(sezon), Y.ogrenilen(sezon), Y.talep(sezon)
        kg = hakem.kahin_girdisi(Y.w, Y.lumoda, g, talep[["magaza_id", "urun_id"]], og.iade["magaza"])
        assert list(kg.columns) == tahmin.KOLONLAR and len(kg) == len(talep) > 0
        assert (kg["magaza_id"].to_numpy() == talep["magaza_id"].to_numpy()).all()
        assert (kg["urun_id"].to_numpy() == talep["urun_id"].to_numpy()).all()
        assert kg["mu_tam"].sum() > 0 and kg["mu_ind"].sum() > 0
        oyun.kahin_fiyat_denetimi(kg)
        liste = g.hucre.drop_duplicates("urun_id").set_index("urun_id")["liste_fiyati"]
        ust = liste.reindex(kg["urun_id"]).to_numpy() * 0.70 * (1 - og.iade["magaza"])
        assert (kg["fiyat_ind"].to_numpy() <= ust + 1e-6).all()
        assert (kg["fiyat_tam"].to_numpy() > kg["fiyat_ind"].to_numpy()).mean() > 0.9
    Y.girdileri_birak()
