"""`markdown.simulasyon` ve `markdown.hakem`: kod özeti listeleri, anahtar, önbellek reddi, KÜÇÜK dünyada
eşdeğerlik, RPT takvimi (aynı mal), kahin girdisi, gerçek ε, ölçütlerin gerçek koşuda tutarlılığı.

KÜÇÜK dünya (20 mağaza + ONL, 357 option, 1277 gün; SS25'in 32 Collection option'ı; serbest karar
penceresi 1036–1064, indirim 1092, çıkış 1148): tam pencere koşusu ~6–7 sn. Modülde bir kez: İlk
Sevkiyat'ın `motor.kos` Lumoda'sı (önbelleksiz), vakanın Lumoda koşusu, onun RPT takvimini oynatan
Lumoda koşusu, serbest optimizasyon kolu ve kural kolu (geçici önbellekte). Optimizasyon kolunun
öğrenileni sentetiktir (ε̂ 1,8, düz yaşam eğrisi, zincir beden payı): sınanan şey aynı maldır, isabet
değil. Yayımlanan v4 ile TAM eşdeğerlik `test_esdegerlik_tam` (`veri`; denetleyici koşar).
"""

import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from allocation import kaynak as al_kaynak
from allocation import motor
from allocation import olcutler as al_olcutler

import markdown
from markdown import hakem, kaynak, olcutler, politika, simulasyon
from markdown.ogrenme import Ogrenilen
from markdown.tahmin import Tahminci

KUCUK = {"olcek": "kucuk"}
SEZON = "SS25"
PAKET = Path(markdown.__file__).resolve().parent


def sentetik_ogrenilen() -> Ogrenilen:
    bos = {c: pd.Series(dtype=t) for c, t in (("sezon_tipi", str), ("duzey", str), ("grup", str),
                                              ("dalga", "int64"), ("hafta", "int64"), ("carpan", float),
                                              ("kaynak", str))}
    return Ogrenilen(
        test_sezonu=SEZON, bitis=datetime.date(2025, 5, 5), sezonlar=("SS23", "SS24"),
        eps_kampanya={"*": 1.8}, eps_markdown={"*": 1.28}, eps_saf=0.2, yasam=pd.DataFrame(bos),
        hafta_gunu={}, ozel_gun={},
        beden_payi=pd.DataFrame({c: pd.Series(dtype=t) for c, t in (("magaza_id", str), ("option_id", str),
                                                                     ("urun_id", str), ("pay", float))}),
        kalinti=0.13, iade={"magaza": 0.06, "online": 0.27}, islem=0.02)


@pytest.fixture(scope="module")
def w():
    return motor.dunya("kucuk")


@pytest.fixture(scope="module")
def idx(w):
    return kaynak.test_optionlari(w.optionlar, SEZON)


@pytest.fixture(scope="module")
def onbellek(tmp_path_factory):
    return tmp_path_factory.mktemp("kosular")


@pytest.fixture(scope="module")
def lumoda_motor():
    return motor.kos(ad="lumoda", parametreler={}, onbellek=None, **KUCUK)


@pytest.fixture(scope="module")
def lumoda(onbellek):
    return simulasyon.kos("lumoda", None, parametreler={}, rpt_takvimi=None, onbellek=onbellek, **KUCUK)


@pytest.fixture(scope="module")
def takvim(lumoda):
    return simulasyon.rpt_takvimi(lumoda)


def _opt(idx):
    og = sentetik_ogrenilen()
    return lambda temel: politika.Optimizasyon(temel, idx, og, kip="serbest", eps="kampanya")


@pytest.fixture(scope="module")
def opt(idx, takvim, onbellek):
    return simulasyon.kos("opt_SS25", _opt(idx), parametreler={"sezon": SEZON}, rpt_takvimi=takvim,
                          onbellek=onbellek, **KUCUK)


# ---------------------------------------------------------------------------
# Kod özeti ve anahtar
# ---------------------------------------------------------------------------


def _paket_ici(yol: Path) -> set[str]:
    return {a.split(".")[1] for a in motor.ice_aktarimlar(yol, "markdown")
            if a.startswith("markdown.") and (PAKET / f"{a.split('.')[1]}.py").is_file()}


def test_kod_ozeti_listeleri(tmp_path, monkeypatch):
    """Her modül `SIMULASYON_MODULLERI` ya da `KOSU_DISI`'ndadır, ikisinde birden değil; simülasyonun ve
    kolların (`politika`: kolları çağıran kurar, simülasyon içe aktarmaz) paket içi içe aktarma
    kapanışı anahtarda; ortak paket kapanışı (öğrenme) da; ölçüm kodu (hakem, ölçütler) değişince vaka özeti aynı,
    simülasyon modülü değişince farklı."""
    var = {y.stem for y in PAKET.glob("*.py")}
    ic, dis = set(simulasyon.SIMULASYON_MODULLERI), set(simulasyon.KOSU_DISI)
    assert not ic & dis
    assert var <= ic | dis, sorted(var - ic - dis)
    assert {"hakem", "olcutler"} <= dis and ic <= var
    kapanis, sira = set(), ["simulasyon", "politika"]
    while sira:
        m = sira.pop()
        if m not in kapanis:
            kapanis.add(m)
            sira += sorted(_paket_ici(PAKET / f"{m}.py"))
    assert kapanis | {"__init__"} == ic
    dosyalar = simulasyon.vaka_kod_dosyalari()
    assert {f"markdown/{m}.py" for m in ic} <= set(dosyalar)
    assert {"ortak/kaynak.py", "ortak/hazirlik.py", "ortak/carpanlar.py"} <= set(dosyalar)   # öğrenmenin kapanışı

    kopya = tmp_path / "markdown"
    kopya.mkdir()
    for y in PAKET.glob("*.py"):
        (kopya / y.name).write_bytes(y.read_bytes())
    once = simulasyon.vaka_kod_ozeti(kopya)
    assert once == simulasyon.vaka_kod_ozeti()
    for ad in ("hakem", "olcutler"):
        (kopya / f"{ad}.py").write_text((kopya / f"{ad}.py").read_text(encoding="utf-8") + "\n# ölçüm\n",
                                        encoding="utf-8")
    assert simulasyon.vaka_kod_ozeti(kopya) == once
    for ad in ("politika", "tahmin", "model", "ogrenme"):
        y = kopya / f"{ad}.py"
        eski = y.read_bytes()
        y.write_bytes(eski + b"\n# karar\n")
        assert simulasyon.vaka_kod_ozeti(kopya) != once, ad
        y.write_bytes(eski)


def _takvim(w, gun=1036, o=0, adet=10):
    return motor.Takvim(rpt={gun: {o: adet}}, markdown={}, option_sayisi=len(w.optionlar)).sabitle()


def test_anahtar_bilesenleri(w, idx, monkeypatch):
    """Anahtar kolun parametrelerini (α), `temel`'in türünü, RPT takviminin kimliğini, test sezonunu,
    yolu ve vaka kod özetini taşır; karar kolu takvimsiz, sezonsuz, yanlış sezonlu ya da `temel`siz
    kurulamaz."""
    tk = _takvim(w)

    def kural(a, i=idx):
        return lambda t: politika.Kural(t, i, alfa=a)

    def h(kol=kural(1.0), sezon=SEZON, takvim=tk, yol=0):
        return simulasyon.hazirla("k", kol, yol, parametreler={"sezon": sezon}, rpt_takvimi=takvim, **KUCUK)

    temel = h()
    mk = temel.icerik["politikalar"]["markdown"]
    assert mk["parametreler"]["alfa"] == 1.0 and mk["temel"]["tur"].endswith("LumodaMarkdown")
    assert temel.icerik["politikalar"]["rpt"]["temel"]["parametreler"]["takvim"] == tk.kimlik
    assert temel.icerik["parametreler"] == {"sezon": SEZON, "yol": 0}
    assert temel.icerik["vaka"] == simulasyon.vaka_kod_ozeti()
    aw = kaynak.test_optionlari(w.optionlar, "AW24")
    farkli = [h(kol=kural(1.25)), h(takvim=_takvim(w, adet=11)), h(sezon="AW24", kol=kural(1.0, aw)),
              h(yol=1), h(kol=lambda t: politika.Tekduze(t, idx, 0.3))]
    anahtarlar = {temel.anahtar} | {x.anahtar for x in farkli}
    assert len(anahtarlar) == 1 + len(farkli)
    assert h(yol=1).talep_tohumu == 20261020 and temel.talep_tohumu is None
    monkeypatch.setattr(simulasyon, "vaka_kod_ozeti", lambda kok=None: "baska")
    assert h().anahtar != temel.anahtar
    monkeypatch.undo()

    with pytest.raises(ValueError, match="RPT takvimi"):
        h(takvim=None)
    with pytest.raises(ValueError, match="sezon"):
        simulasyon.hazirla("k", kural(1.0), parametreler={}, rpt_takvimi=tk, **KUCUK)
    with pytest.raises(ValueError, match="R5"):
        h(sezon="AW24")                                   # SS25 option'larıyla AW24 koşusu
    with pytest.raises(ValueError, match="R5"):
        h(kol=kural(1.0, idx[:-1]))
    with pytest.raises(ValueError, match="temel"):
        h(kol=lambda t: politika.Kural(lambda g: t(g), idx, alfa=1.0))   # temel'i sarmalayan başka nesne
    with pytest.raises(ValueError, match="option sayısı"):
        h(takvim=motor.Takvim(rpt={}, markdown={}, option_sayisi=3))
    with pytest.raises(ValueError, match="yol"):
        simulasyon.hazirla("k", None, 0, parametreler={"yol": 2}, rpt_takvimi=None, **KUCUK)
    with pytest.raises(ValueError, match="Lumoda koşusu"):
        simulasyon.rpt_takvimi(motor.Kosu(tablolar={}, gercek=pd.DataFrame(), meta={"turler": {"rpt": "x"}}))


def test_onbellek_reddi(tmp_path):
    """İlk Sevkiyat'ın çıktı dizinine (ve altına) yazılmaz; koşmadan reddedilir."""
    for yer in (motor.KOSU_DIZINI, motor.KOSU_DIZINI.parent / "markdown_denemesi"):
        with pytest.raises(ValueError, match="salt okunur"):
            simulasyon.kos("lumoda", None, parametreler={}, rpt_takvimi=None, onbellek=yer, **KUCUK)
        assert not (motor.KOSU_DIZINI.parent / "markdown_denemesi").exists()
    with pytest.raises(ValueError, match="tembel"):
        simulasyon.kos("lumoda", None, parametreler={}, rpt_takvimi=None, onbellek=None, **KUCUK)


# ---------------------------------------------------------------------------
# KÜÇÜK koşular
# ---------------------------------------------------------------------------


def _ayni_kosu(a, b, kayitlar=True):
    assert sorted(a.meta["tablolar"]) == sorted(b.meta["tablolar"])
    for ad in a.meta["tablolar"]:
        pd.testing.assert_frame_equal(a.tablo(ad), b.tablo(ad), obj=ad)
    pd.testing.assert_frame_equal(a.tablo("gercek"), b.tablo("gercek"), obj="gercek")
    if kayitlar:
        assert sorted(a.kayitlar) == sorted(b.kayitlar)
        for ad in a.kayitlar:
            pd.testing.assert_frame_equal(a.kayitlar[ad], b.kayitlar[ad], obj=ad)


def test_esdegerlik_kucuk(lumoda, lumoda_motor, onbellek):
    """`kol_kur=None`: İlk Sevkiyat'ın `motor.kos` Lumoda'sıyla tablo tablo, gizli gerçek ve kayıtlar
    birebir; anahtar vaka özetini taşır; ikinci çağrı önbellekten aynı kaydı okur."""
    assert lumoda.meta["turler"] == {} and lumoda.meta["vaka"] == simulasyon.vaka_kod_ozeti()
    assert sorted(lumoda.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    print(f"\nKÜÇÜK Lumoda: motor {lumoda.meta['motor_sn']} sn, toplam {lumoda.meta['sure_sn']} sn")
    _ayni_kosu(lumoda, lumoda_motor)
    tekrar = simulasyon.kos("lumoda", None, parametreler={}, rpt_takvimi=None, onbellek=onbellek, **KUCUK)
    assert tekrar.onbellekten and tekrar.meta["anahtar"] == lumoda.meta["anahtar"]
    assert simulasyon.lumoda_adi(0) == "lumoda" and simulasyon.lumoda_adi(3) == "y3_lumoda"


def test_takvim_lumoda_kucuk(lumoda, takvim, onbellek):
    """Lumoda markdown'ı + Lumoda'nın RPT takvimi (bütün option'lar) = Lumoda koşusu birebir; RPT
    kaydı takvimin oynattığıdır (Lumoda'nın kaydıyla aynı)."""
    assert len(takvim.rpt) > 0
    k = simulasyon.kos("lumoda_takvim", None, parametreler={}, rpt_takvimi=takvim, onbellek=onbellek, **KUCUK)
    assert k.meta["politikalar"]["rpt"]["temel"]["parametreler"]["takvim"] == takvim.kimlik
    _ayni_kosu(k, lumoda)
    assert simulasyon.rpt_takvimi(lumoda).kimlik == takvim.kimlik


def test_rpt_ayni_kucuk(opt, lumoda, w, idx):
    """Serbest optimizasyon kolu + Lumoda'nın RPT takvimi: `siparis`'in RPT satırları, test option'larının
    ilk dağıtım sevkiyatı ve arzı Lumoda'nınkiyle birebir; kol gerçekten farklı karar verdi (indirimden
    önce indirilen option var, satış değişti); kolun sözleşmeleri kayıtta ve uygulanan fiyatta tutar."""
    kayit = opt.kayitlar["markdown"]
    assert list(kayit.columns) == list(politika.KAYIT_SUTUNLARI)
    indirim = w.optionlar["indirim_gun"].to_numpy()[kayit["option"].to_numpy()]
    erken = kayit[(kayit["oran"] > 0) & (kayit["gun"] < indirim)]
    print(f"\nKÜÇÜK opt: motor {opt.meta['motor_sn']} sn; indirimden önce indirilen "
          f"{erken['option'].nunique()}/{len(idx)} option")
    assert erken["option"].nunique() > 0
    assert set(kayit["option"]) <= set(idx.tolist())
    k = olcutler.korunum(opt, lumoda, "serbest", w)
    assert all(k.values()), k
    pd.testing.assert_frame_equal(opt.kayitlar["rpt"], lumoda.kayitlar["rpt"])
    pd.testing.assert_frame_equal(opt.kayitlar["ilk_dagitim"], lumoda.kayitlar["ilk_dagitim"])
    assert not opt.tablo("satis")["adet"].equals(lumoda.tablo("satis")["adet"])
    # Lumoda'nın markdown'ı test option'larında kolun kararıyla değişmiş, öteki option'larda aynı
    fa, fl = opt.tablo("fiyat"), lumoda.tablo("fiyat")
    test_id = set(w.optionlar["option_id"].astype(str).to_numpy()[idx])
    disari = ~fa["option_id"].astype(str).isin(test_id) | (fa["hat"].astype(str) == "outlet")
    pd.testing.assert_frame_equal(fa[disari].reset_index(drop=True),
                                  fl[disari.to_numpy()].reset_index(drop=True))


def test_olcutler_kucuk_tutarlilik(opt, lumoda, w):
    """Gerçek koşuda: markdown TL ve tam fiyat STR İlk Sevkiyat `_para`'sıyla aynı (aynı kapsam); arz ve
    katkı farkı = ciro farkı (aynı mal); çeyrekler toplamı = bütün; isabet ve yan etki sonlu."""
    a, b = olcutler.hesapla(opt, w, SEZON), olcutler.hesapla(lumoda, w, SEZON)
    for r in (a, b):
        assert r["option_sayisi"] == 32 and np.isfinite(r["katki"])
    assert a["arz_adet"] == b["arz_adet"] and a["arz_alis"] == b["arz_alis"]
    assert a["katki"] - b["katki"] == pytest.approx(a["ciro_toplam"] - b["ciro_toplam"])
    assert a["indirilen_option"] >= 1 and a["ilk_indirim_hafta_medyan"] < 0 < a["ort_en_derin"]

    harita = al_kaynak.harita_kur(w)
    for kosu, r in ((opt, a), (lumoda, b)):
        k = al_olcutler.Kapsam(w, harita, kaynak.test_optionlari(w.optionlar, SEZON))
        satis = kosu.tablo("satis", al_olcutler.SATIS, urunler=k.skular)
        sp = kosu.tablo("siparis", al_olcutler.SIPARIS, urunler=k.skular)
        alinan = al_olcutler._alinan(sp, kosu.tablo("kalite_kontrol", ["siparis_id", "hatali"]), k)
        p = al_olcutler._para(satis, kosu.tablo("fiyat", olcutler.FIYAT), k, alinan["siparis"])
        assert r["markdown_tl"] == pytest.approx(p["markdown_tl"])
        assert r["markdown_tl_online"] == pytest.approx(p["markdown_tl_online"])
        assert r["tam_fiyat_str"] == pytest.approx(p["tam_fiyat_str"])
        assert r["arz_adet"] == alinan["siparis"]

    s = olcutler.indirim_basi_str(lumoda, w, SEZON)
    c = olcutler.ceyrek(opt, w, SEZON, s)
    for ad in ("ciro_toplam", "markdown_tl", "cikis_kalan_adet", "olu_stok_adet", "katki"):
        assert c[ad].sum() == pytest.approx(a[ad]), ad
    assert c["option_sayisi"].tolist() == [8, 8, 8, 8]
    i = olcutler.isabet(opt, w)
    assert i["satir"] > 0 and np.isfinite(i["wape"])
    y = olcutler.yan_etki(opt, lumoda, w, SEZON)
    assert np.isfinite(y["ciro_farki_test_disi"]) and y["ikame_alinan"] >= 0
    print(f"\nKÜÇÜK opt − Lumoda: ciro {a['ciro_toplam'] - b['ciro_toplam']:,.0f}, markdown TL "
          f"{a['markdown_tl'] - b['markdown_tl']:,.0f}, isabet WAPE {i['wape']:.1f}, test dışı ciro "
          f"{y['ciro_farki_test_disi']:,.0f}, elle transfer farkı {y['elle_transfer_farki']:,.0f}")


class _KuralCasus(politika.Kural):
    """Kural kolu; her kararında ONL hücrelerinin stoklu geçmişini (son `HIZ_GUN` gün) yoklar."""

    def hiz(self, g):
        c, _konum, online, _s, _sk = self._hucre_yapisi(g.dunya)
        d = int(g.gun)
        bas = max(0, d - politika.HIZ_GUN)
        on = c[online]
        st = np.asarray(g.stoklu_gecmisi[bas:d, on], dtype=bool)
        sat = np.asarray(g.satis_gecmisi[bas:d, on])
        self.yoklama.append((d, int(st.sum()), st.size, int((sat[~st] > 0).sum()),
                             float(sat[st].sum())))
        return super().hiz(g)


def test_kural_onl_stoklu_kucuk(idx, takvim, onbellek, lumoda, w):
    """T4 ⚠️: kuralın hızı ONL hücresinde motorun stoklu bayrağına dayanır (ONL stoklu ⇔ o gün satıştan
    önce SKU'nun depo stoğu > 0; dongu.py adım 14/17). KÜÇÜK koşuda: stoksuz ONL gününde satış yok, ONL
    hücrelerinin karar penceresinde stoklu günü ve satışı var (hız ONL'yi gerçekten içerir). Kural kolu
    motorda uçtan uca koşar ve aynı malı korur."""
    kollar = []

    def kur(t):
        k = _KuralCasus(t, idx, alfa=1.0)
        k.yoklama = []
        kollar.append(k)
        return k

    k = simulasyon.kos("kural_casus", kur, parametreler={"sezon": SEZON}, rpt_takvimi=takvim,
                       onbellek=onbellek, tembel=False, **KUCUK)
    y = np.array(kollar[0].yoklama)
    assert len(y) > 0
    assert (y[:, 3] == 0).all(), "stoksuz ONL gününde satış"
    assert y[:, 1].sum() > 0 and y[:, 4].sum() > 0
    print(f"\nKÜÇÜK kural: ONL stoklu hücre-gün payı {y[:, 1].sum() / y[:, 2].sum():.3f}, "
          f"{len(y)} karar")
    assert all(olcutler.korunum(k, lumoda, "serbest", w).values())


# ---------------------------------------------------------------------------
# Hakem
# ---------------------------------------------------------------------------


def test_kahin_girdisi_boyut(w, idx):
    """Hücreler test option'larının outlet akışı dışı hücreleri (tahmincininkiyle aynı küme), günler
    `[min serbest pencere, max çıkış)`; taban = λ (float32), ε = hücre ε'si; kahin her option'ın
    hücrelerini ve ufkunu girdide bulur; ufuk dışı gün hata."""
    g = hakem.kahin_girdisi(w, idx)
    pen = kaynak.karar_penceresi(w.optionlar, idx, "serbest")
    cikis = w.optionlar["cikis_gun"].to_numpy()[idx]
    assert g.gunler[0] == pen.min() and g.gunler[-1] == cikis.max() - 1
    assert g.taban.shape == (len(g.gunler), len(g.hucre)) and g.eps.shape == (len(g.hucre),)
    t = Tahminci(sentetik_ogrenilen(), idx)
    t._dunya(w)
    tum = np.sort(np.concatenate([t._opt[int(o)].hucre for o in idx]))
    np.testing.assert_array_equal(g.hucre, tum)
    for u in (0, len(g.gunler) // 2, len(g.gunler) - 1):
        np.testing.assert_array_equal(g.taban[u], w.lam.gun(int(g.gunler[u]))[g.hucre].astype(np.float32))
    np.testing.assert_array_equal(g.eps, np.asarray(w.esneklik_hucre)[g.hucre])
    for o in idx:
        g.sutunlar(t._opt[int(o)].hucre)
        g.satirlar(np.arange(int(pen[list(idx).index(o)]), int(cikis.max())))
    kisa = hakem.kahin_girdisi(w, idx, np.arange(1092, 1099))
    assert kisa.taban.shape == (7, len(g.hucre))
    with pytest.raises(ValueError, match="gün aralığı"):
        hakem.kahin_girdisi(w, idx, np.array([w.lam.gun_sayisi]))


def test_kahin_kucuk(idx, takvim, onbellek, lumoda, w):
    """Kahin kolu hakemin girdisiyle motorda uçtan uca koşar (her kararın ufku ve hücreleri girdide),
    aynı malı korur; girdinin kimliği anahtarda."""
    g = hakem.kahin_girdisi(w, idx)
    og = sentetik_ogrenilen()
    k = simulasyon.kos("kahin_SS25", lambda t: politika.Kahin(t, idx, og, g), parametreler={"sezon": SEZON},
                       rpt_takvimi=takvim, onbellek=onbellek, **KUCUK)
    assert k.meta["politikalar"]["markdown"]["parametreler"]["kahin_girdisi"] == g.kimlik()
    assert (k.kayitlar["markdown"]["oran"] > 0).any()
    assert all(olcutler.korunum(k, lumoda, "serbest", w).values())


def test_gercek_eps(lumoda, w):
    """Satış ağırlıklı hücre ε'si, test option'larının indirim döneminde: bağımsız birleştirmeyle aynı."""
    satis = lumoda.tablo("satis", ["tarih", "magaza_id", "urun_id", "adet"])
    r = hakem.gercek_eps(w, satis, SEZON)
    opt = w.optionlar
    u = w.urunler.assign(sku=np.arange(len(w.urunler)))
    hucre = pd.DataFrame({"magaza_id": w.magazalar["magaza_id"].astype(str).to_numpy()[w.hucre_magaza],
                          "urun_id": w.urunler["urun_id"].astype(str).to_numpy()[w.hucre_sku],
                          "eps": np.asarray(w.esneklik_hucre)})
    s = satis.astype({"magaza_id": str, "urun_id": str}).merge(u[["urun_id", "option_id"]], on="urun_id")
    s = s.merge(opt[["option_id", "line", "sezon_kodu", "indirim_gun", "cikis_gun", "ust_kategori"]],
                on="option_id")
    gun = (pd.to_datetime(s["tarih"]) - pd.Timestamp("2022-07-04")).dt.days
    s = s[(s["line"] == "Collection") & (s["sezon_kodu"] == SEZON) & (s["adet"] > 0)
          & (gun >= s["indirim_gun"]) & (gun < s["cikis_gun"])].merge(hucre, on=["magaza_id", "urun_id"])
    s["ae"] = s["adet"] * s["eps"]
    assert r["*"] == pytest.approx(s["ae"].sum() / s["adet"].sum())
    for ust, d in s.groupby("ust_kategori"):
        assert r[ust] == pytest.approx(d["ae"].sum() / d["adet"].sum()), ust
    assert set(r) == set(s["ust_kategori"]) | {"*"}
    assert 1.0 < r["*"] < 3.0
    assert hakem.gercek_eps(w, satis.iloc[:0], SEZON) == {}


# ---------------------------------------------------------------------------
# TAM (denetleyici koşar)
# ---------------------------------------------------------------------------


@pytest.mark.veri
def test_esdegerlik_tam():
    """Yol 0 Lumoda (`kol_kur=None`) → yayımlanan biçimi yayımlanan v4: 18 tablonun satır sayıları ve
    Σ satış adedi DuckDB'deki yayımlanan veriyle birebir (bir TAM koşu, ~4–6 dk, ~8 GB; önbellekte)."""
    if not kaynak.VERITABANI.exists():
        pytest.skip("yayımlanan v4 yok")
    k = simulasyon.kos(simulasyon.lumoda_adi(0), None, parametreler={}, rpt_takvimi=None)
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; motor {k.meta.get('motor_sn')} sn, "
          f"toplam {k.meta.get('sure_sn')} sn; tepe bellek {k.meta.get('tepe_bellek_gb')} GB")
    t = simulasyon.yayimlanan(k)
    assert len(t) == 18
    con = kaynak.baglan()
    try:
        for ad in sorted(t):
            assert len(t[ad]) == con.execute(f"select count(*) from {ad}").fetchone()[0], ad
        assert int(t["satis"]["adet"].sum()) == int(con.execute("select sum(adet) from satis").fetchone()[0])
    finally:
        con.close()
    assert sorted(k.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    assert len(simulasyon.rpt_takvimi(k).rpt) > 0
