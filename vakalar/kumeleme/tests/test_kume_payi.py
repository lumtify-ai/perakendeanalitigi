"""`kumeleme.kume_payi`: İlk Sevkiyat'ın benzer ürün endeksinin küme düzeyindeki karşılığı.

Oyuncak öğrenme tablosu (İlk Sevkiyat `ogrenme.ogrenme_tablosu`nun sütunları + `magaza_id`): iki küme
(`a`: M1, M2; `b`: M3, M4), dört geçmiş SS option'ı (iki alt kategori × iki fiyat segmenti) ve bir AW
option'ı (mevsim süzgecinin dışında). M5 `a` kümesinde ama hiç geçmişi yok (yeni mağaza); M6 hiçbir
kümede değil. Sayılar elle izlenebilsin diye küçük.
"""

import numpy as np
import pandas as pd
import pytest

from kumeleme import kume_payi

ETIKET = pd.Series({"M1": "a", "M2": "a", "M3": "b", "M4": "b", "M5": "a"}, name="kume")

# (option, sezon, ust, alt, fiyat, kalip) → mağaza başına talep
_OPTIONLAR = {
    "P1": ("SS23", "Üst", "Tişört", "giriş", "regular", {"M1": 10, "M2": 30, "M3": 20, "M4": 20}),
    "P2": ("SS23", "Üst", "Tişört", "orta", "regular", {"M1": 12, "M2": 28, "M3": 30, "M4": 10}),
    "P3": ("SS24", "Alt", "Şort", "giriş", "slim", {"M1": 5, "M2": 5, "M3": 25, "M4": 25}),
    "P4": ("SS24", "Alt", "Şort", "orta", "slim", {"M1": 8, "M2": 4, "M3": 30, "M4": 18}),
    "A1": ("AW23", "Üst", "Tişört", "giriş", "regular", {"M1": 99, "M2": 1, "M3": 1, "M4": 1}),
}


def _tablo(optionlar=_OPTIONLAR) -> pd.DataFrame:
    satir = []
    for o, (sezon, ust, alt, fiyat, kalip, talep) in optionlar.items():
        for m, t in talep.items():
            satir.append({"option": o, "magaza": int(m[1:]), "magaza_id": m, "satis": int(t), "stoklu_gun": 30,
                          "talep": float(t), "sezon_kodu": sezon, "ust_kategori": ust, "alt_kategori": alt,
                          "fiyat_segmenti": fiyat, "kalip": kalip, "ilk_alim": 1000})
    return pd.DataFrame(satir)


def _yeni(**ek) -> pd.DataFrame:
    """SS25'in yeni option'ları: Y1 Tişört giriş regular (P1 ile her düzeyde eşleşir), Y2 hiçbir şeyle eşleşmez."""
    return pd.DataFrame([{"option_id": "Y1", "ust_kategori": "Üst", "alt_kategori": "Tişört", "fiyat_segmenti": "giriş",
                          "kalip": "regular"},
                         {"option_id": "Y2", "ust_kategori": "Aksesuar", "alt_kategori": "Şapka",
                          "fiyat_segmenti": "üst", "kalip": "standart"}]).assign(**ek)


def _goreli(t: pd.DataFrame) -> pd.DataFrame:
    """Test içi bağımsız hesap: option × mağaza göreli hız (talep ÷ option'ın gözlemli mağaza ortalaması)."""
    p = t.pivot(index="option", columns="magaza_id", values="talep")
    return p.div(p.mean(axis=1), axis=0)


def test_hiyerarsi_benzer_ile_ayni_bicimde():
    """İlk Sevkiyat `benzer.HIYERARSI` ile aynı (allocation testi ikisinin eşitliğini de sınar)."""
    assert kume_payi.HIYERARSI == (("alt_kategori", "fiyat_segmenti", "kalip"), ("alt_kategori", "fiyat_segmenti"),
                                   ("alt_kategori",), ("ust_kategori",), ())


def test_kume_endeksi_kumede_ortalama():
    """Kümenin geçmiş option'daki göreli hızı = üye mağazaların göreli hızlarının ortalaması; pay = kümenin,
    option'ın düzeyindeki göreli hızı × mağazanın ölçeği (geçmiş göreli hızının küme ortalamasına oranı)."""
    t = _tablo()
    e = kume_payi.ogren(t, ETIKET, en_az=1)
    g = _goreli(t[t["sezon_kodu"].str.startswith("SS")])
    beklenen = pd.DataFrame({"a": g[["M1", "M2"]].mean(axis=1), "b": g[["M3", "M4"]].mean(axis=1)})
    G = pd.DataFrame(e.goreli, index=list(e.option), columns=list(e.kumeler))
    pd.testing.assert_frame_equal(G.loc[beklenen.index, ["a", "b"]], beklenen, check_names=False)
    assert "A1" not in set(e.option)                                  # mevsim süzgeci (SS)

    olc = kume_payi.olcek(t, ETIKET)
    r = g.mean(axis=0)                                                 # mağazanın genel göreli hızı
    assert olc["M1"] == pytest.approx(r["M1"] / r[["M1", "M2"]].mean())
    assert olc["M3"] == pytest.approx(r["M3"] / r[["M3", "M4"]].mean())

    # Y1: en ince düzeyde (alt × fiyat × kalıp) yalnız P1 eşleşir (en_az = 1)
    p = e.paylar(_yeni(), {"Y1": ["M1", "M3"]}, olc)
    assert p[("Y1", "M1")] == pytest.approx(beklenen.at["P1", "a"] * olc["M1"])
    assert p[("Y1", "M3")] == pytest.approx(beklenen.at["P1", "b"] * olc["M3"])
    assert e.duzeyler(_yeni()) == {"Y1": 0, "Y2": 4}
    # en_az = 2: en ince düzeyde 1 eşleşme, alt × fiyat'ta 1, alt kategoride 2 (P1, P2)
    e2 = kume_payi.ogren(t, ETIKET, en_az=2)
    assert e2.duzeyler(_yeni())["Y1"] == 2
    p2 = e2.paylar(_yeni(), {"Y1": ["M2"]}, olc)
    assert p2[("Y1", "M2")] == pytest.approx(beklenen.loc[["P1", "P2"], "a"].mean() * olc["M2"])
    # Y2 hiçbir şeyle eşleşmez: son düzey (bütün geçmiş SS Collection'ı)
    p3 = e.paylar(_yeni(), {"Y2": ["M4"]}, olc)
    assert p3[("Y2", "M4")] == pytest.approx(beklenen["b"].mean() * olc["M4"])


def test_hiyerarsi_kesilebilir():
    """Hiyerarşi en ince düzeyi atlanarak verilebilir (kalibrasyonun ızgarası); son düzey her zaman genel."""
    t = _tablo()
    e = kume_payi.ogren(t, ETIKET, en_az=1, hiyerarsi=kume_payi.HIYERARSI[2:])
    assert e.hiyerarsi == kume_payi.HIYERARSI[2:]
    assert e.duzeyler(_yeni()) == {"Y1": 0, "Y2": 2}                 # kendi hiyerarşisinin indisi
    with pytest.raises(ValueError, match="genel"):
        kume_payi.ogren(t, ETIKET, en_az=1, hiyerarsi=kume_payi.HIYERARSI[:2])
    with pytest.raises(ValueError, match="en_az"):
        kume_payi.ogren(t, ETIKET, en_az=0)


def test_kume_payi_butun_adaylar():
    """Sözlükte her aday var ve payı > 0: geçmişi olmayan yeni mağaza (M5) kümesini statik atamadan alır,
    ölçeği kümesinin medyan ölçeğidir. Kümesi olmayan aday ya da ölçeği olmayan aday hata verir (KahinKol
    sözlükte olmayan adaya 0 verir; sessiz 0 yerine hata)."""
    t = _tablo()
    e = kume_payi.ogren(t, ETIKET, en_az=1)
    olc = kume_payi.olcek(t, ETIKET)
    assert set(olc) == set(ETIKET.index)
    assert olc["M5"] == pytest.approx(float(np.median([olc["M1"], olc["M2"]])))
    adaylar = {"Y1": ["M1", "M2", "M3", "M4", "M5"], "Y2": ["M3", "M5"]}
    p = e.paylar(_yeni(), adaylar, olc)
    assert set(p) == {(o, m) for o, ms in adaylar.items() for m in ms}
    assert all(v > 0 and np.isfinite(v) for v in p.values())
    assert p[("Y1", "M5")] == pytest.approx(p[("Y1", "M1")] / olc["M1"] * olc["M5"])
    with pytest.raises(ValueError, match="kümesi"):
        e.paylar(_yeni(), {"Y1": ["M6"]}, {**olc, "M6": 1.0})
    with pytest.raises(ValueError, match="ölçeği"):
        e.paylar(_yeni(), {"Y1": ["M1"]}, {k: v for k, v in olc.items() if k != "M1"})
    with pytest.raises(ValueError, match="öznitelik"):
        e.paylar(_yeni().drop(columns=["kalip"]), {"Y1": ["M1"]}, olc)
    with pytest.raises(KeyError):
        e.paylar(_yeni(), {"YOK": ["M1"]}, olc)


def test_medyan_olcekliler():
    """Ölçeği kümesinin medyanından gelen mağazalar: hiç gözlemi olmayan (M5) ve yalnız mevsim süzgecinin dışında
    gözlemi olan (M8: yalnız AW; İlk Sevkiyat'ta 19 haftalık M041'in durumu). İkisi de kümesinin medyan ölçeğini
    alır; gözlemli mağaza listede değildir."""
    opt = dict(_OPTIONLAR)
    opt["A1"] = (*opt["A1"][:5], {**opt["A1"][5], "M8": 40})
    t = _tablo(opt)
    et = pd.concat([ETIKET, pd.Series({"M8": "b"})])
    assert kume_payi.medyan_olcekliler(t, et) == ["M5", "M8"]
    olc = kume_payi.olcek(t, et)
    assert olc["M8"] == pytest.approx(float(np.median([olc["M3"], olc["M4"]])))
    assert kume_payi.medyan_olcekliler(t, et, mevsim=None) == ["M5"]       # süzgeçsiz M8 gözlemli


def test_kumede_gozlem_yoksa_genel_duzey_sonra_bir():
    """Kümenin seçilen düzeyde gözlemi yoksa bir üst (daha genel) düzeyin değeri; hiçbir düzeyde yoksa 1.
    `c` kümesinin tek üyesi M4; M4 yalnız Şort'ta gözlenir."""
    opt = {o: v for o, v in _OPTIONLAR.items()}
    opt["P1"] = (*opt["P1"][:5], {m: x for m, x in opt["P1"][5].items() if m != "M4"})
    opt["P2"] = (*opt["P2"][:5], {m: x for m, x in opt["P2"][5].items() if m != "M4"})
    t = _tablo(opt)
    et = pd.Series({"M1": "a", "M2": "a", "M3": "b", "M4": "c", "M7": "d"})
    e = kume_payi.ogren(t, et, en_az=1)
    olc = kume_payi.olcek(t, et)
    assert olc["M7"] == 1.0                                         # kümesinde gözlemli mağaza yok
    p = e.paylar(_yeni(), {"Y1": ["M4", "M7"]}, olc)
    g = _goreli(t[t["sezon_kodu"].str.startswith("SS")])
    assert p[("Y1", "M4")] == pytest.approx(g["M4"].mean() * olc["M4"])   # Tişört'te gözlem yok → genel
    assert p[("Y1", "M7")] == pytest.approx(1.0)


def test_kume_payi_karar_sonrasini_gormez():
    """Pay yalnız öğrenme tablosundan (karar gününde kapanmış sezonlar) gelir: karar verilen option'ın kendi
    satırı tabloda görünürse (karar sonrası bilgi) `paylar` sessizce kullanmaz, hata verir. Mevsim süzgecinin
    dışındaki (AW) satırı bozmak payı da kimliği de değiştirmez."""
    t = _tablo()
    e = kume_payi.ogren(t, ETIKET, en_az=1)
    olc = kume_payi.olcek(t, ETIKET)
    p = e.paylar(_yeni(), {"Y1": ["M1", "M3"]}, olc)

    bozuk = t.copy()
    bozuk.loc[bozuk["option"] == "A1", "talep"] *= 1000              # AW: SS kararına girmez
    eb = kume_payi.ogren(bozuk, ETIKET, en_az=1)
    assert eb.paylar(_yeni(), {"Y1": ["M1", "M3"]}, kume_payi.olcek(bozuk, ETIKET)) == p
    assert eb.kimlik == e.kimlik

    sizan = pd.concat([t, _tablo({"Y1": ("SS25", "Üst", "Tişört", "giriş", "regular", {"M1": 1, "M3": 50})})],
                      ignore_index=True)
    es = kume_payi.ogren(sizan, ETIKET, en_az=1)
    with pytest.raises(ValueError, match="karar"):
        es.paylar(_yeni(), {"Y1": ["M1", "M3"]}, olc)


def test_kimlik_icerikten():
    """Kimlik içerikten: satır sırası değişse aynı; talep, eşik, hiyerarşi ya da etiket değişirse farklı.
    `sabitle()` özeti saklar; etiket adlarının sırası (Series sırası) kimliği değiştirmez."""
    t = _tablo()
    e = kume_payi.ogren(t, ETIKET, en_az=1)
    karisik = t.sample(frac=1.0, random_state=3).reset_index(drop=True)
    assert kume_payi.ogren(karisik, ETIKET.sample(frac=1.0, random_state=1), en_az=1).kimlik == e.kimlik
    s = e.sabitle()
    assert s.kimlik == e.kimlik and s.sabitle() is s
    farkli = t.copy()
    farkli.loc[0, "talep"] += 1.0
    assert kume_payi.ogren(farkli, ETIKET, en_az=1).kimlik != e.kimlik
    assert kume_payi.ogren(t, ETIKET, en_az=2).kimlik != e.kimlik
    assert kume_payi.ogren(t, ETIKET, en_az=1, hiyerarsi=kume_payi.HIYERARSI[1:]).kimlik != e.kimlik
    assert kume_payi.ogren(t, ETIKET.replace({"a": "x"}), en_az=1).kimlik != e.kimlik
    with pytest.raises(ValueError, match="birden çok"):
        kume_payi.ogren(pd.concat([t, t.iloc[:1]]), ETIKET, en_az=1)
