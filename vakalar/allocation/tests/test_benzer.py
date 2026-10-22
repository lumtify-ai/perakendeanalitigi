"""`allocation.benzer`: öznitelik hiyerarşisiyle benzer ürün endeksi, mutlak öngörü, belirsizlik.

Öğrenme tablosu elle kurulur (`ogrenme.ogrenme_tablosu`nun sütunları); mağazalar 0..3."""

import pickle

import numpy as np
import pandas as pd
import pytest

from allocation import benzer, ogrenme

M = 4
YENI = {"ust_kategori": "Üst Giyim", "alt_kategori": "Elbise", "fiyat_segmenti": "orta",
        "kalip": "A", "ilk_alim": 1000}


def _tablo(optionlar: list[dict]) -> pd.DataFrame:
    """optionlar: {"o", "talep": {m: değer}, öznitelikler..., "ilk_alim", "sezon_kodu"?}."""
    satir = []
    for d in optionlar:
        oz = {"ust_kategori": "Üst Giyim", "alt_kategori": "Elbise", "fiyat_segmenti": "orta",
              "kalip": "A", "kumas": "pamuk", "renk": "Siyah", "desen": "düz", "cinsiyet": "Kadın",
              "dalga": 1, "liste_fiyati": 500.0, "sezon_kodu": "SS24", "ilk_alim": 1000}
        oz.update({k: v for k, v in d.items() if k not in ("o", "talep", "stoksuz")})
        for m, t in d["talep"].items():
            satir.append({"option": d["o"], "magaza": m, "satis": int(t), "stoklu_gun": 42,
                          "talep": float(t), **oz})
        for m in d.get("stoksuz", ()):
            satir.append({"option": d["o"], "magaza": m, "satis": 0, "stoklu_gun": 0,
                          "talep": np.nan, **oz})
    df = pd.DataFrame(satir)
    return df[[*ogrenme.ERKEN_SUTUNLARI, *ogrenme.OZNITELIKLER, "ilk_alim"]]


HEPSI = np.ones(M, dtype=bool)


def test_hiyerarsi_degerleri():
    assert benzer.HIYERARSI == (("alt_kategori", "fiyat_segmenti", "kalip"),
                                ("alt_kategori", "fiyat_segmenti"), ("alt_kategori",),
                                ("ust_kategori",), ())


def test_hiyerarsi_geri_dusus():
    t = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10, 2: 20, 3: 20}},                      # düzey 0
        {"o": 2, "talep": {0: 20, 1: 20, 2: 20, 3: 20}},                      # düzey 0
        {"o": 3, "kalip": "B", "talep": {0: 10, 1: 30, 2: 20, 3: 20}},        # düzey 1
        {"o": 4, "kalip": "C", "talep": {0: 40, 1: 0, 2: 20, 3: 20}},         # düzey 1
        {"o": 5, "alt_kategori": "Bluz", "talep": {0: 5, 1: 5, 2: 5, 3: 25}},  # düzey 3
    ])
    # en_az 3: ilk düzeyde 2 option -> ikinci düzey (4 option)
    endeks, duzey, _ = benzer.ogren(t, en_az=3).endeks(YENI, HEPSI)
    assert duzey == 1
    np.testing.assert_allclose(endeks, [(1.5 + 1 + .5 + 2) / 4, (.5 + 1 + 1.5 + 0) / 4, 1, 1])
    endeks, duzey, _ = benzer.ogren(t, en_az=2).endeks(YENI, HEPSI)
    assert duzey == 0
    np.testing.assert_allclose(endeks, [1.25, .75, 1, 1])
    # 5 option ancak üst kategoride; 6 hiçbir düzeyde yok -> son düzey (bütün geçmiş)
    assert benzer.ogren(t, en_az=5).endeks(YENI, HEPSI)[1] == 3
    assert benzer.ogren(t, en_az=6).endeks(YENI, HEPSI)[1] == 4
    # yeni option'ın alt kategorisi geçmişte yok: üst kategoriye düşer
    assert benzer.ogren(t, en_az=1).endeks({**YENI, "alt_kategori": "Etek"}, HEPSI)[1] == 3


def test_gozlemsiz_magaza_ust_duzeyden():
    t = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10}, "stoksuz": [2]},                     # düzey 0
        {"o": 2, "talep": {0: 20, 1: 20}},                                       # düzey 0
        {"o": 3, "kalip": "B", "talep": {0: 10, 1: 20, 2: 30}},                 # düzey 1
        {"o": 4, "alt_kategori": "Bluz", "talep": {0: 10, 1: 10, 2: 10}},       # düzey 3
    ])
    e = benzer.ogren(t, en_az=2)
    endeks, duzey, mutlak = e.endeks(YENI, HEPSI)
    assert duzey == 0
    # mağaza 2'nin düzey 0'da gözlemi yok (stoksuz satır sayılmaz): düzey 1'in değeri 30/20
    # mağaza 3'ün hiç geçmişi yok: ortalama mağaza (1), mutlak öngörüsü gözlemli adayların ortalaması
    np.testing.assert_allclose(endeks, [(1.5 + 1) / 2, (.5 + 1) / 2, 1.5, 1.0])
    np.testing.assert_allclose(mutlak[:3], [25, 15, 30])
    assert mutlak[3] == pytest.approx(np.mean([25, 15, 30]))


def test_endeks_aday_kumesine_goreli():
    """Her geçmiş option'da hız kendi aday kümesinin ortalamasına göredir: farklı aday
    kümeleri ve farklı ölçekler, mağazaların göreli hızı aynıysa aynı endeksi verir."""
    tek = _tablo([{"o": 1, "talep": {0: 30, 1: 10, 2: 20, 3: 20}}])
    farkli = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10, 2: 20, 3: 20}},
        {"o": 2, "talep": {0: 150, 1: 50}},                  # yalnız iki aday, 5 kat ölçek
        {"o": 3, "talep": {0: 60, 1: 20, 2: 40}},            # üç aday
    ])
    beklenen = [1.5, .5, 1, 1]
    np.testing.assert_allclose(benzer.ogren(tek, 1).endeks(YENI, HEPSI)[0], beklenen)
    np.testing.assert_allclose(benzer.ogren(farkli, 1).endeks(YENI, HEPSI)[0], beklenen)
    # yeni option'ın aday kümesi aday olan mağazaların değerini değiştirmez; aday olmayana 0
    aday = np.array([True, True, True, False])
    endeks, _, mutlak = benzer.ogren(farkli, 1).endeks(YENI, aday)
    np.testing.assert_allclose(endeks, [1.5, .5, 1, 0])
    assert mutlak[3] == 0 and (mutlak[:3] > 0).all()


def test_mutlak_ongoru_ilk_alimla_olcekli():
    t = _tablo([
        {"o": 1, "ilk_alim": 1000, "talep": {0: 30, 1: 10, 2: 20}},
        {"o": 2, "ilk_alim": 3000, "talep": {0: 150, 1: 50}},
    ])
    e = benzer.ogren(t, en_az=1)
    _, _, mutlak = e.endeks({**YENI, "ilk_alim": 2000}, HEPSI)
    # mağaza 0: ortalama talep 90, benzerlerin ortalama ilk alımı 2000 -> 90 × 2000 / 2000
    # mağaza 2: yalnız option 1'de gözlem -> 20 × 2000 / 1000
    np.testing.assert_allclose(mutlak[:3], [90, 30, 40])
    _, _, iki_kat = e.endeks({**YENI, "ilk_alim": 4000}, HEPSI)
    np.testing.assert_allclose(iki_kat, 2 * mutlak)


def test_ogren_stoksuz_ve_satissiz_option():
    t = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10}},
        {"o": 2, "talep": {0: 0, 1: 0}},                 # hiç satmamış: göreli hız tanımsız
        {"o": 3, "talep": {}, "stoksuz": [0, 1]},        # hiç gözlem yok
    ])
    e = benzer.ogren(t, en_az=1)
    assert e.option.tolist() == [1]
    assert e.goreli.shape == e.talep.shape == (1, 2)


def test_ogren_mevsim():
    t = _tablo([
        {"o": 1, "sezon_kodu": "SS23", "talep": {0: 30, 1: 10}},
        {"o": 2, "sezon_kodu": "AW23", "talep": {0: 10, 1: 30}},
        {"o": 3, "sezon_kodu": "SS24", "talep": {0: 20, 1: 20}},
    ])
    assert benzer.ogren(t, 1, mevsim="SS").option.tolist() == [1, 3]
    assert benzer.ogren(t, 1, mevsim="AW").option.tolist() == [2]
    assert benzer.ogren(t, 1).option.tolist() == [1, 2, 3]
    with pytest.raises(ValueError):
        benzer.ogren(t, 1, mevsim="KIS")
    with pytest.raises(ValueError):
        benzer.ogren(t, 0)


def test_endeks_genis_magaza_ekseni():
    """Tablonun görmediği mağazalar (ör. sonradan açılan) aday dizisinin uzunluğuna kadar
    gözlemsiz sayılır."""
    t = _tablo([{"o": 1, "talep": {0: 30, 1: 10}}])
    endeks, _, mutlak = benzer.ogren(t, 1).endeks(YENI, np.ones(6, dtype=bool))
    np.testing.assert_allclose(endeks, [1.5, .5, 1, 1, 1, 1])
    with pytest.raises(ValueError):
        benzer.ogren(t, 1).endeks(YENI, np.ones(1, dtype=bool))


def test_endeks_kimligi_icerikten():
    t = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10, 2: 20, 3: 20}},
        {"o": 2, "kalip": "B", "talep": {0: 20, 1: 20}, "stoksuz": [3]},
    ])
    e = benzer.ogren(t, en_az=3)
    k = e.kimlik
    assert isinstance(k, str) and len(k) == 64
    # satır sırası ve DataFrame kimliği değil, içerik
    karisik = t.sample(frac=1.0, random_state=1).reset_index(drop=True)
    assert benzer.ogren(karisik, en_az=3).kimlik == k
    assert benzer.ogren(t.copy(), en_az=3).kimlik == k
    # içerik değişince değişir: talep, öznitelik, ilk alım, eşik
    t2 = t.copy()
    t2.loc[0, "talep"] += 1
    t3 = t.copy()
    t3.loc[t3["option"] == 2, "fiyat_segmenti"] = "üst"
    t4 = t.copy()
    t4.loc[t4["option"] == 2, "ilk_alim"] = 2000
    assert len({k, benzer.ogren(t2, 3).kimlik, benzer.ogren(t3, 3).kimlik,
                benzer.ogren(t4, 3).kimlik, benzer.ogren(t, 2).kimlik}) == 5
    # sabitle: kimliği saklayan kopya; ikinci kez kendisi; pickle'da korunur
    s = e.sabitle()
    assert s.kimlik == k and s.sabitle() is s
    assert pickle.loads(pickle.dumps(s)).kimlik == k
    np.testing.assert_array_equal(s.endeks(YENI, HEPSI)[0], e.endeks(YENI, HEPSI)[0])
    # öğrenilenler salt okunur
    with pytest.raises(ValueError):
        e.goreli[0, 0] = 9.0


def test_kimlik_satir_sirasindan_bagimsiz_gercel_talep():
    """Gerçel (tamsayı olmayan) talepte de satır sırası kimliği ve öğrenilenleri bit bit
    değiştirmez (kayan nokta toplamı sıraya bağlıdır; `ogren` kanonik sırayla toplar)."""
    rng = np.random.default_rng(7)
    optionlar = []
    for o in range(50):
        magazalar = np.flatnonzero(rng.random(84) < 0.8)
        optionlar.append({"o": o, "kalip": ["A", "B", "C"][o % 3],
                          "fiyat_segmenti": ["orta", "üst"][o % 2],
                          "ilk_alim": float(rng.integers(500, 5000)),
                          "talep": {int(m): float(rng.gamma(2.0, 7.3)) for m in magazalar}})
    t = _tablo(optionlar)
    e = benzer.ogren(t, en_az=3)
    aday = np.ones(84, dtype=bool)
    endeks, _, mutlak = e.endeks(YENI, aday)
    for tohum in range(10):
        k = benzer.ogren(t.sample(frac=1.0, random_state=tohum).reset_index(drop=True), en_az=3)
        assert k.kimlik == e.kimlik
        for ad in ("talep", "goreli", "ilk_alim", "option"):
            assert getattr(k, ad).tobytes() == getattr(e, ad).tobytes(), ad
        en2, _, mu2 = k.endeks(YENI, aday)
        assert en2.tobytes() == endeks.tobytes() and mu2.tobytes() == mutlak.tobytes()


def test_ogren_cift_satir_reddedilir():
    t = _tablo([{"o": 1, "talep": {0: 30, 1: 10}}])
    with pytest.raises(ValueError, match="birden çok"):
        benzer.ogren(pd.concat([t, t.iloc[[0]]], ignore_index=True), 1)


def test_belirsizlik():
    ayni = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10, 2: 20, 3: 20}},
        {"o": 2, "talep": {0: 60, 1: 20, 2: 40, 3: 40}},
    ])
    assert benzer.belirsizlik(benzer.ogren(ayni, 1), YENI, HEPSI) == pytest.approx(0.0)
    t = _tablo([
        {"o": 1, "talep": {0: 30, 1: 10}},
        {"o": 2, "talep": {0: 10, 1: 30}},
        {"o": 3, "kalip": "B", "talep": {0: 20, 1: 20, 2: 20}},
    ])
    e = benzer.ogren(t, en_az=2)
    endeks, duzey, mutlak = e.endeks(YENI, np.array([True, True, True, False]))
    assert duzey == 0
    # mağaza 0 ve 1: göreli (1.5, .5) / (.5, 1.5) -> DK = std(ddof=1) / ort = .7071;
    # mağaza 2 düzey 1'de tek gözlemli: DK tanımsız, ortalamaya girmez; ağırlık mutlak öngörü
    dk = np.std([1.5, .5], ddof=1) / 1.0
    assert mutlak[0] == pytest.approx(mutlak[1])
    assert benzer.belirsizlik(e, YENI, np.array([True, True, True, False])) == pytest.approx(dk)
    # hiçbir mağazada iki gözlem yoksa tanımsız
    tek = _tablo([{"o": 1, "talep": {0: 30, 1: 10}}])
    assert np.isnan(benzer.belirsizlik(benzer.ogren(tek, 1), YENI, HEPSI))
