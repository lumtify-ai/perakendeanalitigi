"""`kumeleme.olcutler` ve `kumeleme.hakem`: ARI/AMI, çapraz tablo, saflık, kararlılık (yıllar arası
ve önyükleme), yeni mağaza doğruluğu; gizli segmentin okunuşu.

Kararlılık testleri `conftest`in 12 mağazalı fikstürünü kullanır (8 kümelenen mağaza; satış
2024-02-05'ten başlar, dönemler 26 haftalık iki örtüşmeyen pencere). `veri` işaretli test yayımlanan
v4 verisini ve v4 dünyasını (hakem) ister; sonuçları `-s` ile basar.
"""

from functools import partial
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from conftest import KARAR, oyuncak_baglan
from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

from kumeleme import hakem, kaynak, ogren, olcutler, ozellikler, sabitler

DONEM = {"a": (pd.Timestamp("2024-08-05"), 26), "b": (KARAR, 26)}


def _kapsam(tablolar):
    return kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"], tablolar["satis"], KARAR)


def _seri(degerler, on="M"):
    return pd.Series(list(degerler), index=pd.Index([f"{on}{i:02d}" for i in range(len(degerler))],
                                                    name="magaza_id"))


# ------------------------------------------------------------------ hakemli


def test_ari_bilinen():
    """sklearn ile aynı; satır sırası ve etiket adları sonucu değiştirmez; eksik mağaza hata."""
    rng = np.random.default_rng(3)
    e = _seri(rng.integers(0, 4, 40))
    g = _seri(rng.choice(["a", "b", "c"], 40))
    ari, ami = olcutler.ari_ami(e, g)
    assert ari == pytest.approx(adjusted_rand_score(g.to_numpy(), e.to_numpy()), abs=1e-15)
    assert ami == pytest.approx(adjusted_mutual_info_score(g.to_numpy(), e.to_numpy()), abs=1e-15)
    karisik = e.sample(frac=1.0, random_state=1)
    assert olcutler.ari_ami(karisik, g) == pytest.approx((ari, ami), abs=1e-15)
    yeniden = e.map({0: "z", 1: "y", 2: "x", 3: "w"})
    assert olcutler.ari_ami(yeniden, g) == pytest.approx((ari, ami), abs=1e-15)
    assert olcutler.ari_ami(g, g) == (1.0, 1.0)
    with pytest.raises(KeyError):
        olcutler.ari_ami(e, g.iloc[1:])


@pytest.mark.parametrize("segment", ["outlet", "online"])
def test_kapsam_disi_segment_olculmez(segment):
    """Ölçülen mağazalarda outlet/online segmenti hata; gerçek tabloda durması (ölçülmeyen) değil."""
    e = _seri([0, 0, 1, 1])
    g = _seri(["a", "a", "b", segment])
    for f in (olcutler.ari_ami, olcutler.capraz, olcutler.saflik, olcutler.toplam_saflik):
        with pytest.raises(ValueError, match="outlet/online"):
            f(e, g)
    tam = pd.concat([_seri(["a", "a", "b", "b"]), pd.Series({"O01": segment})])
    assert olcutler.ari_ami(e, tam) == (1.0, 1.0)


def test_capraz_saflik():
    e = _seri([0, 0, 0, 1, 1, 1, 1])
    g = _seri(["a", "a", "b", "b", "b", "c", "c"])
    t = olcutler.capraz(e, g)
    assert t.loc[0].to_dict() == {"a": 2, "b": 1, "c": 0} and t.loc[1].to_dict() == {"a": 0, "b": 2, "c": 2}
    s = olcutler.saflik(e, g)
    assert s.loc["a"].to_dict() == {"n": 2, "kume": 0, "pay": 1.0, "kume_payi": pytest.approx(2 / 3)}
    assert s.loc["b", "kume"] == 1 and s.loc["b", "pay"] == pytest.approx(2 / 3)
    assert s.loc["c", "kume_payi"] == pytest.approx(0.5)
    assert olcutler.toplam_saflik(e, g) == pytest.approx(4 / 7)


# ------------------------------------------------------------------ kararlılık


def _bolge_kumesi(kapsam):
    """Bölgeye göre sabit bölme; her çağrıda etiket adları değişir (permütasyon)."""
    bolge = kapsam.set_index("magaza_id")["bolge"]
    sira = {b: i for i, b in enumerate(sorted(bolge.unique()))}
    sayac = {"n": 0}

    def fn(Z):
        sayac["n"] += 1
        kod = [sira[bolge[str(m).split("#")[0]]] for m in Z.index]
        return pd.Series([f"k{(c + sayac['n']) % len(sira)}" for c in kod], index=Z.index)
    return fn, sayac


def test_kararlilik_permutasyon(tablolar):
    """Aynı bölme, her çağrıda başka etiket adları: yıllar arası ARI 1,0, önyüklemede değişme 0."""
    k = _kapsam(tablolar)
    fn, sayac = _bolge_kumesi(k)
    r = olcutler.kararlilik(fn, tablolar, k, tablolar["urun"], DONEM, aile="S1", en_az_hafta=10, ornek=10)
    ids = sorted(k.loc[k["kumelenir"], "magaza_id"])
    assert r["ari"] == {("a", "b"): 1.0}
    assert r["onyukleme_ari"] == 1.0 and r["degisme_ort"] == 0.0
    assert (r["degisme"] == 0).all() and list(r["degisme"].index) == ids
    assert r["gorulme"].sum() > 0 and (r["gorulme"] <= 10).all()
    assert sayac["n"] == 2 + 1 + 10                                    # iki dönem, tam, 10 çekiliş
    assert r["disarida"] == [] and (r["satisli_hafta"] == 26).all().all()
    assert r["donem"].loc["a", "bas"] == pd.Timestamp("2024-02-05")
    assert r["donem"].loc["a", "bit"] == r["donem"].loc["b", "bas"] == pd.Timestamp("2024-08-05")
    assert r["donem"].loc["b", "bit"] == pd.Timestamp("2025-02-03")
    for d in "ab":
        assert sorted(r["etiketler"][d].index) == ids


def test_kararlilik_belirlenimci_ve_disarida(tablolar):
    """Aynı tohum aynı sonuç; geçmişi eşiğin altındaki mağaza yıllar arası karşılaştırmaya girmez."""
    k = _kapsam(tablolar)
    fn = partial(ogren.kume, yontem="kmeans", k=2)
    a = olcutler.kararlilik(fn, tablolar, k, tablolar["urun"], DONEM, aile="S1", en_az_hafta=10, ornek=5)
    b = olcutler.kararlilik(fn, tablolar, k, tablolar["urun"], DONEM, aile="S1", en_az_hafta=10, ornek=5)
    assert a["ari"] == b["ari"] and a["degisme"].equals(b["degisme"])
    t = {**tablolar, "satis": tablolar["satis"][~((tablolar["satis"]["magaza_id"] == "M02")
                                                  & (tablolar["satis"]["tarih"] < pd.Timestamp("2024-06-03")))]}
    c = olcutler.kararlilik(fn, t, k, tablolar["urun"], DONEM, aile="S1", en_az_hafta=10, ornek=2)
    assert c["disarida"] == ["M02"] and c["satisli_hafta"].loc["M02", "a"] == 9
    assert "M02" not in c["etiketler"]["a"].index and "M02" in c["degisme"].index


def test_kararlilik_ileri_bakis_reddedilir(tablolar):
    """Dönem penceresi karar günü penceresinden sonra bitemez (kalibrasyon gününde varsayılan
    dönemler geleceği okurdu); hata hiçbir okuma ve kümelemeden önce."""
    k = _kapsam(tablolar)
    fn, sayac = _bolge_kumesi(k)
    with pytest.raises(ValueError, match="b"):
        olcutler.kararlilik(fn, tablolar, k, tablolar["urun"], DONEM, aile="S1",
                            karar_gunu=pd.Timestamp("2024-08-09"), en_az_hafta=10, ornek=2)
    with pytest.raises(ValueError, match="2024"):
        olcutler.kararlilik(fn, None, k, None, aile="S1", karar_gunu=sabitler.KAL_KARAR_GUNU)
    assert sayac["n"] == 0
    r = olcutler.kararlilik(fn, tablolar, k, tablolar["urun"], {"a": DONEM["a"]}, aile="S1",
                            karar_gunu=pd.Timestamp("2024-08-09"), en_az_hafta=10, ornek=2)
    assert list(r["etiketler"]) == ["a"]                                # tam sınırda bitebilir


def test_satisli_hafta_baglanti_ile_ayni(tablolar):
    ids = ["M01", "M08", "M09", "YOK"]
    bas, bit = ozellikler.pencere(KARAR, 26)
    a = olcutler._satisli_hafta(tablolar, ids, bas, bit)
    con = oyuncak_baglan(tablolar)
    try:
        b = olcutler._satisli_hafta(con, ids, bas, bit)
    finally:
        con.close()
    assert a.equals(b) and a.to_dict() == {"M01": 26, "M08": 26, "M09": 10, "YOK": 0}


def test_eslesik_degisen():
    assert olcutler._eslesik_degisen(np.array([5, 5, 7, 7, 7, 7]), np.array([0, 0, 0, 1, 1, 1])).tolist() \
        == [False, False, True, False, False, False]
    # çekilişte fazladan küme: eşlenmeyen kümenin mağazaları değişmiş
    assert olcutler._eslesik_degisen(np.array([0, 0, 1, 1, 2, 2]), np.array([0, 0, 0, 0, 1, 1])).tolist() \
        == [False, False, True, True, False, False]


# ------------------------------------------------------------------ yeni mağaza doğruluğu


def test_birakbir_dogruluk():
    t = pd.DataFrame({"magaza_id": ["A", "B", "C", "D", "E"], "gercek_kume": [0, 0, 0, 1, 1],
                      "atanan": [0, 1, 0, 1, 0], "metropol": [True, True, False, False, False],
                      "ayni_bolme": True})
    g = pd.Series({"A": "x", "B": "x", "C": "y", "D": "y", "E": "y", "Z": "q"})
    m, o = olcutler.birakbir_dogruluk(t, g)
    assert m["gizli"].tolist() == ["x", "x", "y", "y", "y"]
    # A: küme 0'ın diğerleri B(x), C(y) → eşitlik: ıska (alfabetik ilk x, A'nın kendi segmenti,
    # isabet yazılmaz)
    assert m["atanan_segment"].tolist() == [None, "y", "x", "y", "x"]
    assert m["kume_segment"].tolist() == [None, None, "x", "y", "y"]
    assert m["dogru_kume"].tolist() == [True, False, True, True, False]
    assert m["dogru_segment"].tolist() == [False, False, False, True, False]
    assert m["kume_dogru_segment"].tolist() == [False, False, False, True, True]
    assert m["taban_kume"].tolist() == [False] * 5                    # A, B, C: 2-2 eşitlik
    assert m["taban_segment"].tolist() == [False] * 5
    assert o.loc["hepsi", "n"] == 5 and o.loc["hepsi", "dogru_kume"] == pytest.approx(0.6)
    assert o.loc["metropol", "n"] == 2 and o.loc["metropol", "dogru_segment"] == 0.0
    assert o.loc["metropol_disi", "kume_dogru_segment"] == pytest.approx(2 / 3)


def test_cogunluk_esitlik_iska():
    assert olcutler._cogunluk(pd.Series(["b", "a", "b"])) == "b"
    assert olcutler._cogunluk(pd.Series(["b", "a"])) is None
    assert olcutler._cogunluk(pd.Series([], dtype=object)) is None


# ------------------------------------------------------------------ hakem


def test_gizli_segment_tablodan_ve_dunyadan(gizli):
    a = hakem.gizli_segment(gizli)
    b = hakem.gizli_segment(SimpleNamespace(gizli_magaza=gizli.iloc[::-1]))
    assert a.equals(b) and a.name == "segment" and a.index.name == "magaza_id"
    assert list(a.index) == sorted(gizli["magaza_id"]) and a["M08"] == "turistik"
    with pytest.raises(ValueError):
        hakem.gizli_segment(pd.concat([gizli, gizli.iloc[:1]]))
    with pytest.raises(KeyError):
        hakem.gizli_segment(gizli[["magaza_id"]])


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_olcutler_ss25():
    """SS25: önerilen ML kümesi ve kural grupları hakeme karşı; kararlılık; bırakbir ve 2 gerçek
    yeni mağaza (-s ile basılır)."""
    from kumeleme import kural, yeni_magaza
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay", "urun"))
        satis = con.execute(
            "select tarih, magaza_id::varchar as magaza_id, adet, tutar from satis where tarih < ?",
            [sabitler.KARAR_GUNU]).df()
        k = kaynak.kapsam(t["magaza"], t["magaza_olay"], satis, sabitler.KARAR_GUNU)
        kum = k[k["kumelenir"]]
        X = {a: ozellikler.ozellik_tablosu(con, kum["magaza_id"], t["urun"], sabitler.KARAR_GUNU, a)
             for a in ogren.ONERI_AILELERI}
        o = ogren.oneri(None, k, None, sabitler.KARAR_GUNU, ozellik=X)
        fn = partial(ogren.kume, yontem=o.yontem, k=o.k)
        r = olcutler.kararlilik(fn, con, k, t["urun"], aile=o.aile, ozellik=X[o.aile])
    finally:
        con.close()
    g = hakem.gizli_segment()
    assert set(k["magaza_id"]) <= set(g.index)
    print(f"\nöneri {o.aile} {o.yontem} k={o.k}")
    k2 = kural.ciro_sinifi(satis, k, sabitler.KARAR_GUNU)
    gruplar = {"ML": o.etiket, "K1": kural.bolge(k), "K2": k2, "K3": kural.bolge_ciro(k, k2),
               "K4": kural.konum(k)}
    for ad, e in gruplar.items():
        e = e.loc[kum["magaza_id"]]
        ari, ami = olcutler.ari_ami(e, g)
        print(f"{ad}: ARI {ari:.3f} AMI {ami:.3f} saflık {olcutler.toplam_saflik(e, g):.3f}")
    print(olcutler.capraz(o.etiket, g).to_string())
    print(olcutler.saflik(o.etiket, g).to_string())
    print(r["donem"].to_string())
    print(f"yıllar arası ARI {r['ari']}, dışarıda {r['disarida']}")
    print(f"önyükleme ARI {r['onyukleme_ari']:.3f}, ortalama değişme {r['degisme_ort']:.3f}")
    print(r["degisme"][r["degisme"] > 0].sort_values(ascending=False).round(2).to_string())
    assert len(r["degisme"]) == 67 and 0 <= r["degisme_ort"] <= 1

    Z = ozellikler.standartla(X[o.aile], o.aile)
    for yontem in yeni_magaza.YONTEMLER:
        b = yeni_magaza.birakbir(kum, Z, fn, yontem=yontem)
        m, ozet = olcutler.birakbir_dogruluk(b, g)
        print(f"bırakbir {yontem}: aynı bölme {int(b['ayni_bolme'].sum())}/{len(b)}")
        print(ozet.round(3).to_string())
        assert len(b) == 67 and ozet.loc["hepsi", "n"] == 67
    yeni = yeni_magaza.ata(k[k["yeni"]], kum, o.etiket)
    print("gerçek yeni mağazalar:", yeni.to_dict(), {m: g[m] for m in yeni.index})
    assert sorted(yeni.index) == ["M027", "M041"]
