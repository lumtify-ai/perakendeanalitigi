"""Hikâye seçimi (`hikaye_sec`): spec §6 merdiveni, gevşetme, zorlama, gizli doğrulama, hata.

Oyuncak dünya: 13 mağaza (12 kümelenen + 1 yeni). İki satış profili vardır, `genc` ve `aile`
(Collection karışımında alt kategori, fiyat segmenti, kalıp payları); ML kümesi profildir
(genc → 0, aile → 1). Gizli segment yalnız `gizli_segment` fikstüründe ve yalnız doğrulama
testlerindedir. Gerçek veri testi (`veri`) CLI'nin gerçek çıktısını kontrol eder.
"""

import json

import numpy as np
import pandas as pd
import pytest

from kumeleme import hikaye_sec as hs

NITELIK = {   # nitelik -> (değerler, genc payları, aile payları)
    "alt_kategori": (("Tişört", "Pantolon", "Elbise"), (0.55, 0.15, 0.30), (0.25, 0.50, 0.25)),
    "fiyat_segmenti": (("giris", "orta", "ust"), (0.20, 0.40, 0.40), (0.50, 0.40, 0.10)),
    "kalip": (("slim", "regular"), (0.70, 0.30), (0.30, 0.70)),
}

# magaza_id: (şehir, bölge, istanbul, metropol, profil, ciro sınıfı, kümelenir)
DUNYA = {
    "I1": ("İstanbul", "Marmara", True, True, "genc", "C", True),
    "I2": ("İstanbul", "Marmara", True, True, "aile", "C", True),
    "I3": ("İstanbul", "Marmara", True, True, "aile", "B", True),
    "I4": ("İstanbul", "Marmara", True, True, "genc", "B", True),
    "K1": ("Kocaeli", "Marmara", False, False, "aile", "C", True),
    "A1": ("Konya", "İç Anadolu", False, False, "aile", "C", True),
    "A2": ("Konya", "İç Anadolu", False, False, "aile", "C", True),
    "A3": ("Kayseri", "İç Anadolu", False, False, "aile", "B", True),
    "A4": ("Eskişehir", "İç Anadolu", False, False, "genc", "C", True),
    "E1": ("İzmir", "Ege", False, True, "genc", "A", True),
    "E2": ("Denizli", "Ege", False, False, "aile", "C", True),
    "E3": ("Denizli", "Ege", False, False, "aile", "C", True),
    "N1": ("Bursa", "Marmara", False, False, "aile", "C", False),     # yeni mağaza: kümelenmez
}


def kapsam_kur(dunya=DUNYA) -> pd.DataFrame:
    return pd.DataFrame([{"magaza_id": m, "sehir": v[0], "bolge": v[1], "istanbul": v[2],
                          "metropol": v[3], "kumelenir": v[6]} for m, v in dunya.items()])


def ozellik_kur(dunya=DUNYA, tohum=7) -> pd.DataFrame:
    """Mağaza × `karisim/Collection/<nitelik>/<değer>` payları; her nitelikte paylar bire toplanır."""
    rng = np.random.default_rng(tohum)
    satir = {}
    for m, v in dunya.items():
        r = {}
        for nitelik, (degerler, genc, aile) in NITELIK.items():
            taban = np.array(genc if v[4] == "genc" else aile)
            pay = np.clip(taban + rng.normal(0, 0.03, len(taban)), 0.01, None)
            pay = pay / pay.sum()
            r.update({f"karisim/Collection/{nitelik}/{d}": p for d, p in zip(degerler, pay)})
        satir[m] = r
    X = pd.DataFrame.from_dict(satir, orient="index")
    X.index.name = "magaza_id"
    return X


def etiketler_kur(dunya=DUNYA, k2=None, k3=None):
    k2 = pd.Series({m: v[5] for m, v in dunya.items()}, name="k2") if k2 is None else k2
    k3 = (pd.Series({m: f"{v[1]}×{v[5]}" for m, v in dunya.items()}, name="k3")
          if k3 is None else k3)
    ml = pd.Series({m: 0 if v[4] == "genc" else 1 for m, v in dunya.items()}, name="kume")
    return {"k2": k2, "k3": k3}, ml


def kur(dunya=DUNYA):
    k = kapsam_kur(dunya)
    kural, ml = etiketler_kur(dunya)
    X = ozellik_kur(dunya)
    return X.loc[k.loc[k["kumelenir"], "magaza_id"]], k, kural, ml


def mesafeler(X):
    Z = hs.ozellikler.standartla(X, "S1")
    A = Z.to_numpy()
    D = np.sqrt(((A[:, None, :] - A[None, :, :]) ** 2).sum(-1))
    return pd.DataFrame(D, index=Z.index, columns=Z.index)


def ceyrekler(X):
    D = mesafeler(X).to_numpy()
    v = D[np.triu_indices(len(D), 1)]
    return np.quantile(v, 0.25), np.quantile(v, 0.75)


# ------------------------------------------------------------------ 1. basamak: sıkı merdiven


def test_siki_merdiven_ozellikleri():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    a, b = h.cift1
    c, d = h.cift2
    kk = k.set_index("magaza_id")
    D = mesafeler(X)
    q25, q75 = ceyrekler(X)
    assert h.gevseyen == []
    # 1. çift: aynı bölge ve aynı ciro sınıfı, iki metropol mağazası, biri İstanbul; uzaklık üst çeyrekte;
    # ML kümeleri farklı
    assert kk.at[a, "bolge"] == kk.at[b, "bolge"] and kural["k2"][a] == kural["k2"][b]
    assert kk.at[a, "metropol"] and kk.at[b, "metropol"] and (kk.at[a, "istanbul"] or kk.at[b, "istanbul"])
    assert D.at[a, b] >= q75 - 1e-12 and ml[a] != ml[b]
    # 2. çift: farklı bölge, biri İstanbul biri değil; uzaklık alt çeyrekte; aynı ML kümesi
    assert kk.at[c, "bolge"] != kk.at[d, "bolge"] and kk.at[c, "istanbul"] and not kk.at[d, "istanbul"]
    assert D.at[c, d] <= q25 + 1e-12 and ml[c] == ml[d]
    assert h.mesafe == pytest.approx((D.at[a, b], D.at[c, d]))
    assert h.esikler == pytest.approx({"ust": q75, "alt": q25})
    assert h.dogrulama is None and h.elenen == 0


def test_yeni_magaza_secilmez():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    assert "N1" not in {*h.cift1, *h.cift2}
    kural2 = {a: s.drop("N1") for a, s in kural.items()}
    assert hs.sec(X, k, kural2, ml.drop("N1")).cift1 == h.cift1        # yeni mağazanın etiketi gerekmez


def test_ortak_istanbul_magazasi_tercih_edilir():
    """Ders: 1. çiftteki İstanbul mağazası 2. çiftte de varsa tek mağaza iki derse tanıklık eder."""
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    assert h.cift2[0] in h.cift1 and h.cift1[0] == h.cift2[0]


def test_kalemler_iki_uc_somut_kalem():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    assert 2 <= len(h.kalemler) == len(h.kalemler2) <= 3
    (a, b), (c, d) = h.cift1, h.cift2
    nitelikler = [ad.split("/")[2] for ad, _, _ in h.kalemler]
    assert len(set(nitelikler)) == len(nitelikler)                       # her nitelikten en çok bir kalem
    sd = X.std(axis=0, ddof=0)
    for (ad, va, vb), (ad2, vc, vd) in zip(h.kalemler, h.kalemler2):
        assert ad == ad2 and ad in X.columns
        assert (va, vb) == pytest.approx((X.at[a, ad], X.at[b, ad]))
        assert (vc, vd) == pytest.approx((X.at[c, ad], X.at[d, ad]))
        assert abs(va - vb) >= hs.KALEM_FARK_MIN                         # somut: payda gözle görülür fark
        assert abs(va - vb) / sd[ad] > abs(vc - vd) / sd[ad]             # 1. çiftte ayrışır, 2.de ayrışmaz


def test_belirlenimci_ve_satir_sirasindan_bagimsiz():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    assert hs.sec(X, k, kural, ml) == h
    h2 = hs.sec(X.sample(frac=1, random_state=3), k.sample(frac=1, random_state=4), kural, ml)
    assert h2 == h


# ------------------------------------------------------------------ gevşetme


def test_hucre_gevsetmesi_kayda_gecer():
    """İstanbul'da aynı ciro sınıfında farklı satan çift yok; K3 grubu birleşik → hücre gevşer."""
    d = dict(DUNYA)
    d["I1"] = d["I1"][:5] + ("B",) + d["I1"][6:]       # genc B
    d["I4"] = d["I4"][:5] + ("B",) + d["I4"][6:]
    d["I2"] = d["I2"][:5] + ("C",) + d["I2"][6:]       # aile C
    d["I3"] = d["I3"][:5] + ("C",) + d["I3"][6:]
    k = kapsam_kur(d)
    k3 = pd.Series({m: (f"{v[1]}×BC" if v[1] == "Marmara" and v[5] in "BC" else f"{v[1]}×{v[5]}")
                    for m, v in d.items()}, name="k3")
    kural, ml = etiketler_kur(d, k3=k3)
    X = ozellik_kur(d)
    X = X.loc[k.loc[k["kumelenir"], "magaza_id"]]
    h = hs.sec(X, k, kural, ml)
    assert len(h.gevseyen) == 1 and "K3" in h.gevseyen[0]
    a, b = h.cift1
    kk = k.set_index("magaza_id")
    assert kural["k2"][a] != kural["k2"][b] and kural["k3"][a] == kural["k3"][b]
    assert kk.at[a, "bolge"] == kk.at[b, "bolge"] and ml[a] != ml[b]


def test_metropol_sarti_gevser():
    """İstanbul'da hiç farklı satan çift yok (hepsi aile): 1. çift Kocaeli ile kurulur, metropol şartı kalkar."""
    d = {m: v for m, v in DUNYA.items()}
    for m in ("I1", "I4"):
        d[m] = d[m][:4] + ("aile",) + d[m][5:]
    d["K1"] = d["K1"][:4] + ("genc",) + d["K1"][5:]
    k = kapsam_kur(d)
    kural, ml = etiketler_kur(d)
    X = ozellik_kur(d)
    X = X.loc[k.loc[k["kumelenir"], "magaza_id"]]
    h = hs.sec(X, k, kural, ml)
    assert any("metropol" in g for g in h.gevseyen)
    kk = k.set_index("magaza_id")
    assert "K1" in h.cift1 and kk.loc[list(h.cift1), "istanbul"].any()


def test_anadolu_sarti_metropol_ankara_izmir_haric_tutar():
    """2. çiftin İstanbul olmayan mağazası sıkı merdivende metropol değildir; gevşeyince İzmir girer."""
    X, k, kural, ml = kur()
    w = hs._Dunya(X, k, kural, ml)
    siki = hs.MERDIVEN[0]
    gevsek = next(g for g in hs.MERDIVEN if not g.anadolu)
    bos = frozenset()
    a = hs._cift2_adaylari(w, siki, 1e9, bos)
    b = hs._cift2_adaylari(w, gevsek, 1e9, bos)
    assert a and all(not w.metropol[m] or w.istanbul[m] for c in a for m in c)
    assert any("E1" in c for c in b) and not any("E1" in c for c in a)


def test_merdiven_kumulatif():
    k = hs.MERDIVEN[0]
    assert (k.hucre, k.metropol, k.istanbul1, k.istanbul2, k.anadolu, k.ust, k.alt, k.gevseyen) ==         ("bolge_sinif", True, True, True, True, 0.75, 0.25, ())
    assert len(hs.MERDIVEN) == len(hs.ADIMLAR) + 1
    for onceki, sonraki in zip(hs.MERDIVEN, hs.MERDIVEN[1:]):
        assert sonraki.gevseyen[:len(onceki.gevseyen)] == onceki.gevseyen
        assert len(sonraki.gevseyen) == len(onceki.gevseyen) + 1
        assert sonraki.ust <= onceki.ust and sonraki.alt >= onceki.alt


def _ilk_kademe(kosul):
    return next(i for i, k in enumerate(hs.MERDIVEN) if kosul(k))


def test_istanbul_bayraklari_ayri_sirada_gevser():
    """1. çiftin "tercihen İstanbul" şartı erken, 2. çiftin İstanbul-Anadolu şartı (kadro) en son gevşer."""
    i1 = _ilk_kademe(lambda k: not k.istanbul1)
    i2 = _ilk_kademe(lambda k: not k.istanbul2)
    ilk_nicelik = _ilk_kademe(lambda k: k.ust < hs.UST)
    ilk_anadolu = _ilk_kademe(lambda k: not k.anadolu)
    son_nicelik = _ilk_kademe(lambda k: k.ust <= 0.5)
    assert i1 < ilk_nicelik < son_nicelik < i2 == len(hs.MERDIVEN) - 1
    assert i1 < ilk_anadolu < i2
    assert hs.MERDIVEN[i1 - 1].istanbul2 and hs.MERDIVEN[-2].istanbul2 and hs.MERDIVEN[i2 - 1].istanbul2
    for k in hs.MERDIVEN[:i2]:
        assert k.istanbul2                                                    # son kademeye dek sürer
    assert hs.MERDIVEN[-1].gevseyen[-1].startswith("2. çift: İstanbul-Anadolu")


def test_kademelerde_adaylar_buyur():
    """Gevşeyen her kademede 1. çift ve 2. çift aday kümeleri öncekini kapsar; nicelik kademeleri büyütür."""
    X, k, kural, ml = kur()
    w = hs._Dunya(X, k, kural, ml)
    bos = frozenset()
    onceki1 = onceki2 = None
    sayilar = []
    for kad in hs.MERDIVEN:
        ust, alt = w.esikler(kad)
        c1 = set(hs._cift1_adaylari(w, kad, ust, bos))
        c2 = set(hs._cift2_adaylari(w, kad, alt, bos))
        if onceki1 is not None:
            assert onceki1 <= c1 and onceki2 <= c2
        onceki1, onceki2 = c1, c2
        sayilar.append((len(c1), len(c2)))
    ilk = _ilk_kademe(lambda kd: kd.ust < hs.UST)
    n50 = _ilk_kademe(lambda kd: kd.ust <= 0.5)
    assert sum(sayilar[n50]) > sum(sayilar[ilk - 1])                          # nicelik kademeleri adayı artırır


def _degistir(d, m, i, v):
    d[m] = d[m][:i] + (v,) + d[m][i + 1:]


def sahne(d, ml_ozel=None):
    """Dünya `d` için `sec` (ML kümeleri profil; `ml_ozel` ile mağaza başına geçersiz kılınır)."""
    k = kapsam_kur(d)
    kural, ml = etiketler_kur(d)
    for m, v in (ml_ozel or {}).items():
        ml[m] = v
    X = ozellik_kur(d)
    return hs.sec(X.loc[k.loc[k["kumelenir"], "magaza_id"]], k, kural, ml), k.set_index("magaza_id")


def test_istanbul1_kademesi_davranisi():
    """İstanbul'da farklı satan çift yok (hepsi aile); farklı satan çift İç Anadolu'da: ancak 1. çiftin
    İstanbul şartı kalkınca (3. kademe) sahne kurulur ve 1. çiftte İstanbul mağazası yoktur."""
    d = dict(DUNYA)
    for m in ("I1", "I4"):
        _degistir(d, m, 4, "aile")
    h, kk = sahne(d)
    assert len(h.gevseyen) == 3 and h.gevseyen[-1] == hs.ADIMLAR[2][2]
    assert not kk.loc[list(h.cift1), "istanbul"].any()
    assert kk.at[h.cift2[0], "istanbul"] != kk.at[h.cift2[1], "istanbul"]    # 2. çift İstanbul-Anadolu kalır


def test_anadolu_kademesi_davranisi():
    """2. çift İstanbul mağazasıyla yalnız İzmir'in (metropol) mağazası aynı ML kümesinde: ancak Anadolu
    şartı gevşeyince (6. kademe) sahne kurulur."""
    d = dict(DUNYA)
    _degistir(d, "E1", 4, "aile")
    ml = {m: 5 for m, v in d.items() if not v[3]}                            # metropol dışı hepsi ayrı küme
    h, kk = sahne(d, ml)
    assert len(h.gevseyen) == 6 and h.gevseyen[-1] == hs.ADIMLAR[5][2]
    assert "E1" in h.cift2 and kk.at["E1", "metropol"] and not kk.at["E1", "istanbul"]
    assert kk.at[h.cift2[0], "istanbul"] != kk.at[h.cift2[1], "istanbul"]


def test_istanbul2_en_son_gevser():
    """İstanbul mağazalarının hiçbiri başka bir mağazayla aynı ML kümesinde değil: 2. çift ancak son
    kademede (8.) İstanbul olmayan iki mağazadan kurulur, öncesinde hiçbir kademe bunu yapmaz."""
    d = dict(DUNYA)
    ml = {m: 5 for m, v in d.items() if not v[2]}
    ml.update({"I1": 7, "I2": 8, "I3": 8, "I4": 7})
    h, kk = sahne(d, ml)
    assert len(h.gevseyen) == len(hs.ADIMLAR) == 8
    assert h.gevseyen[-1] == hs.ADIMLAR[-1][2]
    assert not kk.loc[list(h.cift2), "istanbul"].any()
    assert kk.at[h.cift2[0], "bolge"] != kk.at[h.cift2[1], "bolge"]


def test_bulunamazsa_hata():
    X, k, kural, ml = kur()
    with pytest.raises(ValueError, match="hikâye"):
        hs.sec(X, k, kural, pd.Series(0, index=ml.index))                 # herkes tek ML kümesinde


def test_eksik_etiket_hata():
    X, k, kural, ml = kur()
    with pytest.raises(ValueError, match="ML"):
        hs.sec(X, k, kural, ml.drop("A1"))
    with pytest.raises(KeyError):
        hs.sec(X, k, {"k2": kural["k2"]}, ml)                             # k3 yok


# ------------------------------------------------------------------ zorlama


def test_zorla_gecerli_cift():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml, zorla=(("I1", "I3"), ("I2", "A1")))
    assert h.cift1 == ("I1", "I3") and h.cift2 == ("I2", "A1")
    assert "zorlandı" in h.gevseyen[0]
    assert 2 <= len(h.kalemler) <= 3 and h.kalemler[0][1] != h.kalemler[0][2]
    assert h.alternatif is None


@pytest.mark.parametrize("zorla", [
    (("I1", "ZZ"), ("I2", "A1")),            # bilinmeyen mağaza
    (("I1", "N1"), ("I2", "A1")),            # yeni mağaza kümelenmez
    (("I1", "I1"), ("I2", "A1")),            # aynı mağaza
])
def test_zorla_gecersiz_hata(zorla):
    X, k, kural, ml = kur()
    with pytest.raises(ValueError):
        hs.sec(X, k, kural, ml, zorla=zorla)


def test_zorla_saglanmayan_olcut_kayda_gecer():
    """Zorlanan çift ölçütleri sağlamıyorsa hata değil, kayıt: hangi ölçüt tutmuyor."""
    X, k, kural, ml = kur()
    zayif = hs.sec(X, k, kural, ml, zorla=(("I1", "I4"), ("A1", "A2")))   # 1. çift aynı ML; 2. çift aynı bölge
    assert zayif.gevseyen[0].startswith("zorlandı")
    assert any(g.startswith("1. çift") and "ML" in g for g in zayif.gevseyen)
    assert any(g.startswith("2. çift") and "bölge" in g for g in zayif.gevseyen)
    uygun = hs.sec(X, k, kural, ml, zorla=(("I1", "I2"), ("I2", "A1")))
    assert not any("ML" in g or "bölge" in g for g in uygun.gevseyen)


# ------------------------------------------------------------------ gizli doğrulama


def gizli_kur(d=DUNYA):
    return pd.Series({m: ("metropol_genc" if v[4] == "genc" else "anadolu_aile") for m, v in d.items()},
                     name="segment")


def test_gizli_dogrular():
    X, k, kural, ml = kur()
    h0 = hs.sec(X, k, kural, ml)
    h = hs.sec(X, k, kural, ml, gizli=gizli_kur())
    assert (h.cift1, h.cift2) == (h0.cift1, h0.cift2) and h.elenen == 0
    assert h.dogrulama == {"cift1_farkli": True, "cift2_ayni": True,
                           "segmentler": {m: gizli_kur()[m] for m in (*h.cift1, *h.cift2)}}


def test_gizli_ilk_adayi_eler():
    """Gizli segment 1. çiftin ilk adayında aynıysa (hakem onaylamaz) sıradaki aday seçilir; elenen sayılır."""
    X, k, kural, ml = kur()
    h0 = hs.sec(X, k, kural, ml)
    g = gizli_kur()
    g[h0.cift1[1]] = g[h0.cift1[0]]                                       # ilk adayın çifti aynı segmentte
    h = hs.sec(X, k, kural, ml, gizli=g)
    assert h.elenen >= 1
    assert (h.cift1, h.cift2) != (h0.cift1, h0.cift2)
    assert g[h.cift1[0]] != g[h.cift1[1]] and g[h.cift2[0]] == g[h.cift2[1]]
    assert h.dogrulama["cift1_farkli"] and h.dogrulama["cift2_ayni"]


def test_gizli_hicbir_sahne_dogrulanmazsa_hata():
    X, k, kural, ml = kur()
    g = pd.Series("anadolu_aile", index=ml.index)                         # segmentler hep aynı
    with pytest.raises(ValueError, match="hakem"):
        hs.sec(X, k, kural, ml, gizli=g)


# ------------------------------------------------------------------ alternatif sahne


def test_alternatif_ayri_magazalarla():
    """Varsayılan dünyada İstanbul'un ikinci çifti ve İç Anadolu'daki mağazalar ikinci bir sahne verir."""
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    al = h.alternatif
    assert al is not None
    assert not {*h.cift1, *h.cift2} & {*al.cift1, *al.cift2}
    assert al.alternatif is None and 2 <= len(al.kalemler) <= 3
    assert len(al.gevseyen) >= len(h.gevseyen)
    assert al.cift1 != h.cift1 and al.cift2 != h.cift2


def test_alternatif_yoksa_none():
    """Beş mağazalı dünya: birinci sahne üç mağaza kullanır; kalan iki mağaza (aynı ML) 1. çift kuramaz."""
    d = {m: DUNYA[m] for m in ("I1", "I2", "A1", "A2", "A3")}
    h, _ = sahne(d)
    assert len({*h.cift1, *h.cift2}) == 3
    assert h.alternatif is None


def test_json_donusumu():
    X, k, kural, ml = kur()
    h = hs.sec(X, k, kural, ml)
    s = h.sozluk()
    assert s["cift1"] == list(h.cift1) and s["gevseyen"] == h.gevseyen
    assert s["kalemler"][0]["ozellik"] == h.kalemler[0][0]
    assert all(" adedinin " in e["olcu"] and e["olcu"].endswith("payı") for e in s["kalemler"] + s["kalemler2"])
    assert [e["olcu"] for e in s["kalemler"]] == [e["olcu"] for e in s["kalemler2"]]
    json.dumps(s, ensure_ascii=False)


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_gercek_veri_sahnesi():
    """SS25 karar günü: sıkı merdiven bulunur ve hakem doğrular (CLI'nin yaptığı; `-s` ile basılır)."""
    from kumeleme import hikaye_kos
    g = hikaye_kos.girdiler()
    h, hakemsiz, gizli = hikaye_kos.calistir(g)
    k = g["kapsam"].set_index("magaza_id")
    assert h.gevseyen == [] and h.elenen == 0
    assert h.dogrulama["cift1_farkli"] and h.dogrulama["cift2_ayni"]
    assert (hakemsiz.cift1, hakemsiz.cift2) == (h.cift1, h.cift2)
    a, b = h.cift1
    c, d = h.cift2
    assert k.at[a, "istanbul"] and k.at[b, "istanbul"] and a == c
    assert not k.at[d, "metropol"] and k.at[a, "bolge"] != k.at[d, "bolge"]
    assert 2 <= len(h.kalemler) <= 3
    print(json.dumps(hikaye_kos.kayit(g, h, hakemsiz, gizli), ensure_ascii=False, indent=1))


def test_olcu_metni():
    assert hs.olcu("karisim/Collection/alt_kategori/Sweatshirt") ==         "Collection adedinin Sweatshirt alt kategorisindeki payı"
    assert hs.olcu("karisim/Collection/kalip/regular") == "Collection adedinin regular kalıbındaki payı"
    assert hs.olcu("karisim/Basic+NOS/fiyat_segmenti/giris") ==         "Basic ve NOS adedinin giris fiyat segmentindeki payı"
    assert hs.olcu("mevsim/03") == "mevsim/03"                                # bilinmeyen sütun olduğu gibi
