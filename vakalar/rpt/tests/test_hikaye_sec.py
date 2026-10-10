import pandas as pd
import pytest
from test_hikaye import rpt_tablolari

from rpt import hikaye_sec, kaynak
from rpt.hikaye_sec import (
    BOS_PAY_ESIGI,
    DEPODA_PAY_ESIGI,
    GELIS_ARALIGI,
    STOKSUZ_MAGAZA_MIN,
    en_yakin,
    gec_bayraklari,
    gec_sirasi,
    hit_bayraklari,
    hit_sirasi,
    huni,
    merdiven,
    sec_ozellikten,
    secim_ayristir,
)

# ---------------------------------------------------------------------------
# Saf ölçüt mantığı: elle kurulmuş özellik tabloları
# ---------------------------------------------------------------------------

VARSAYILAN = {
    "mense": "Yerli", "banu_h": True, "dalga": 3, "stoksuz_magaza": 5, "satis_ilk_alim": 0.6,
    "banu_rpt": True, "rpt_gelis_gun": 14.0, "bos_pay": 0.9, "depoda_pay": 0.9,
    "tedarikci": "Ted", "rpt": 500.0,
}


def tablo(*satirlar: dict) -> pd.DataFrame:
    return pd.DataFrame([{**VARSAYILAN, **s} for s in satirlar])


def test_bayrak_esikleri():
    f = tablo(
        {"option_id": "a", "stoksuz_magaza": STOKSUZ_MAGAZA_MIN - 1},
        {"option_id": "b", "stoksuz_magaza": STOKSUZ_MAGAZA_MIN},
        {"option_id": "c", "mense": "Yakın"},
        {"option_id": "d", "dalga": 2},
        {"option_id": "e", "banu_h": False},
    )
    b = hit_bayraklari(f).set_index(f["option_id"])
    assert not b.loc["a", "stoksuz"] and b.loc["b", "stoksuz"]
    assert not b.loc["c", "yerli"] and not b.loc["d", "dalga3"] and not b.loc["e", "banu_h"]
    assert list(b.columns) == list(hikaye_sec.HIT_OLCUTLERI)
    lo, hi = GELIS_ARALIGI
    g = tablo(
        {"option_id": "a", "mense": "Uzak Doğu", "rpt_gelis_gun": lo - 1},
        {"option_id": "b", "mense": "Uzak Doğu", "rpt_gelis_gun": lo},
        {"option_id": "c", "mense": "Uzak Doğu", "rpt_gelis_gun": hi},
        {"option_id": "d", "mense": "Uzak Doğu", "rpt_gelis_gun": hi + 1},
        {"option_id": "e", "mense": "Uzak Doğu", "bos_pay": BOS_PAY_ESIGI - 0.01},
        {"option_id": "f", "mense": "Uzak Doğu", "depoda_pay": DEPODA_PAY_ESIGI - 0.01},
        {"option_id": "g", "mense": "Uzak Doğu", "bos_pay": BOS_PAY_ESIGI, "depoda_pay": DEPODA_PAY_ESIGI},
        {"option_id": "h", "mense": "Uzak Doğu", "banu_rpt": False, "rpt_gelis_gun": float("nan"),
         "bos_pay": float("nan"), "depoda_pay": float("nan")},
    )
    gb = gec_bayraklari(g).set_index(g["option_id"])
    assert list(gb["gelis"]) == [False, True, True, False, True, True, True, False]
    assert not gb.loc["e", "bos"] and not gb.loc["f", "depoda"]
    assert gb.loc["g", "bos"] and gb.loc["g", "depoda"]
    assert not gb.loc["h", ["banu_rpt", "gelis", "bos", "depoda"]].any()    # eksik değer = tutmuyor
    assert list(gb.columns) == list(hikaye_sec.GEC_OLCUTLERI)


def test_merdiven_birebir_eslesme_gevsetmez():
    f = tablo(
        {"option_id": "tam", "stoksuz_magaza": 4},
        {"option_id": "daha_iyi_ama_dalga2", "dalga": 2, "stoksuz_magaza": 9},
    )
    adaylar, gev = merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert list(adaylar["option_id"]) == ["tam"] and gev == []


def test_merdiven_birebir_adaylar_arasinda_siralar():
    f = tablo({"option_id": "a", "stoksuz_magaza": 3, "satis_ilk_alim": 0.9},
              {"option_id": "b", "stoksuz_magaza": 6, "satis_ilk_alim": 0.5},
              {"option_id": "c", "stoksuz_magaza": 6, "satis_ilk_alim": 0.7})
    adaylar, gev = merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert list(adaylar["option_id"]) == ["c", "b", "a"] and gev == []


def test_merdiven_tek_olcut_gevsetir_ve_kaydeder():
    f = tablo({"option_id": "dalga2", "dalga": 2},
              {"option_id": "az_stoksuz", "stoksuz_magaza": 1},
              {"option_id": "ikisi_de", "dalga": 1, "stoksuz_magaza": 0})
    adaylar, gev = merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    # gevşetme sırası dalga3 → stoksuz: önce dalga3'ü gevşeten aday gelir
    assert adaylar.iloc[0]["option_id"] == "dalga2" and gev == ["dalga3"]
    f2 = f[f["option_id"] != "dalga2"]
    adaylar, gev = merdiven(f2, hit_bayraklari(f2), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert adaylar.iloc[0]["option_id"] == "az_stoksuz" and gev == ["stoksuz"]


def test_merdiven_tek_ikiliden_once():
    """İkili gevşetme ancak hiçbir tek gevşetme aday vermiyorsa denenir."""
    f = tablo({"option_id": "ikili", "dalga": 1, "stoksuz_magaza": 0, "satis_ilk_alim": 0.99})
    adaylar, gev = merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert list(adaylar["option_id"]) == ["ikili"] and gev == ["dalga3", "stoksuz"]
    f = tablo({"option_id": "ikili", "dalga": 1, "stoksuz_magaza": 0, "satis_ilk_alim": 0.99},
              {"option_id": "tek", "stoksuz_magaza": 0, "satis_ilk_alim": 0.1})
    adaylar, gev = merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert list(adaylar["option_id"]) == ["tek"] and gev == ["stoksuz"]


def test_merdiven_gevsemez_olcut_hata_verir():
    f = tablo({"option_id": "kotu_menseli", "mense": "Uzak Doğu"},
              {"option_id": "kural_tetiklemiyor", "banu_h": False})
    with pytest.raises(LookupError) as e:
        merdiven(f, hit_bayraklari(f), hikaye_sec.HIT_GEVSEK, hit_sirasi)
    assert "yerli 1" in str(e.value) and "banu_h 0" in str(e.value)       # huni mesajda


def test_huni_ardisik():
    f = tablo({"option_id": "a"}, {"option_id": "b", "mense": "Yakın"},
              {"option_id": "c", "banu_h": False}, {"option_id": "d", "dalga": 1})
    assert huni(hit_bayraklari(f)) == [("havuz", 4), ("yerli", 3), ("banu_h", 2), ("dalga3", 1), ("stoksuz", 1)]


def test_gec_merdiveni_gevsetme_sirasi():
    uzak = {"mense": "Uzak Doğu"}
    f = tablo({"option_id": "gec_degil", **uzak, "rpt_gelis_gun": 50.0},     # gelis tutmuyor
              {"option_id": "baska_pazartesi", **uzak, "banu_h": False},     # banu_h tutmuyor
              {"option_id": "dolu_magaza", **uzak, "bos_pay": 0.2})
    adaylar, gev = merdiven(f, gec_bayraklari(f), hikaye_sec.GEC_GEVSEK, gec_sirasi)
    # gevşetme sırası: gelis, bos, depoda, banu_h → gelis'i gevşeten aday gelir
    assert adaylar.iloc[0]["option_id"] == "gec_degil" and gev == ["gelis"]
    f2 = f[f["option_id"] != "gec_degil"]
    adaylar, gev = merdiven(f2, gec_bayraklari(f2), hikaye_sec.GEC_GEVSEK, gec_sirasi)
    assert adaylar.iloc[0]["option_id"] == "dolu_magaza" and gev == ["bos"]
    f3 = f[f["option_id"] == "baska_pazartesi"]
    adaylar, gev = merdiven(f3, gec_bayraklari(f3), hikaye_sec.GEC_GEVSEK, gec_sirasi)
    assert gev == ["banu_h"]


def test_gec_gevsemez_menses_ve_banu_rpt():
    f = tablo({"option_id": "yerli_mal", "mense": "Yerli"},
              {"option_id": "rpt_yok", "mense": "Uzak Doğu", "banu_rpt": False})
    with pytest.raises(LookupError, match="uzak_dogu 1"):
        merdiven(f, gec_bayraklari(f), hikaye_sec.GEC_GEVSEK, gec_sirasi)


def test_gec_sirasi_hedefe_yakin_once():
    uzak = {"mense": "Uzak Doğu"}
    f = tablo({"option_id": "a", **uzak, "rpt_gelis_gun": 22.0, "bos_pay": 0.99},
              {"option_id": "b", **uzak, "rpt_gelis_gun": 13.0, "bos_pay": 0.7},
              {"option_id": "c", **uzak, "rpt_gelis_gun": 15.0, "bos_pay": 0.8})
    adaylar, gev = merdiven(f, gec_bayraklari(f), hikaye_sec.GEC_GEVSEK, gec_sirasi)
    # b (13 gün) ve c (15 gün) hedefe (14) eşit uzakta: boş mağaza payı yüksek olan c önce; a en sonda
    assert list(adaylar["option_id"]) == ["c", "b", "a"] and gev == []


def test_zorla_gevseyen_butun_olcutleri_listeler():
    f = tablo({"option_id": "hit_tam"},
              {"option_id": "hit_yakin_mense", "mense": "Yakın", "stoksuz_magaza": 0},
              {"option_id": "gec_tam", "mense": "Uzak Doğu"},
              {"option_id": "gec_dalga", "mense": "Uzak Doğu", "banu_rpt": False, "rpt_gelis_gun": 90.0})
    s = sec_ozellikten(f, ("hit_yakin_mense", "gec_dalga"))
    assert s["hit"]["option_id"] == "hit_yakin_mense"
    assert s["gevseyen"]["hit"] == ["yerli", "stoksuz"]                 # gevşemez olan da listelenir
    assert s["gevseyen"]["gec"] == ["banu_rpt", "gelis"]
    assert s["merdiven"] == {"hit": "hit_tam", "gec": "gec_tam"}


def test_zorla_bilinmeyen_option_ve_ayni_option():
    f = tablo({"option_id": "x", "mense": "Uzak Doğu"}, {"option_id": "y"})
    with pytest.raises(LookupError, match="havuzda yok"):
        sec_ozellikten(f, ("y", "yok"))
    with pytest.raises(ValueError, match="aynı option"):
        sec_ozellikten(f, ("x", "x"))


def test_zorla_merdiven_bosken_de_calisir():
    """Ölçütleri sağlayan aday olmasa da `--hikaye` ile seçilebilir (merdiven ilk sırası None)."""
    f = tablo({"option_id": "a", "banu_h": False}, {"option_id": "b", "mense": "Yakın"})
    s = sec_ozellikten(f, ("a", "b"))
    assert s["merdiven"] == {"hit": None, "gec": None}
    assert s["gevseyen"]["hit"] == ["banu_h"] and "uzak_dogu" in s["gevseyen"]["gec"]
    with pytest.raises(LookupError):
        sec_ozellikten(f)                                    # varsayılan (merdiven) hata verir


def test_en_yakin_tutmayan_sayisina_gore():
    f = tablo({"option_id": "iki", "dalga": 1, "stoksuz_magaza": 0},
              {"option_id": "bir", "stoksuz_magaza": 0},
              {"option_id": "sifir"})
    d = en_yakin(f, hit_bayraklari(f), hit_sirasi)
    assert list(d["option_id"]) == ["sifir", "bir", "iki"]
    assert list(d["tutmayan"]) == [0, 1, 2]
    assert d.set_index("option_id").loc["iki", "gevseyen"] == "dalga3, stoksuz"


def test_secim_ayristir():
    assert secim_ayristir("MDL1-A:MDL2-B") == ("MDL1-A", "MDL2-B")
    for kotu in ("", "a", "a:b:c", "a:", ":b"):
        with pytest.raises(ValueError, match="HIT_OPTION:GEC_OPTION"):
            secim_ayristir(kotu)


def test_yurutucu_secimi_iki_ayri_option():
    hit_, gec_ = hikaye_sec.YURUTUCU_SECIMI
    assert hit_ != gec_ and hit_.startswith("MDL") and gec_.startswith("MDL")


# ---------------------------------------------------------------------------
# Toplayıcı: oyuncak (elle izlenebilir)
# ---------------------------------------------------------------------------


def test_ozellikler_oyuncak():
    t, opt = rpt_tablolari()
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    f = hikaye_sec.ozellikler(t, opt, hh, "SS25", h=2).set_index("option_id")
    a = f.loc["OPT-A"]
    # 2. pazartesi (2025-02-24) sabahı: satış 61 (M1 42 + M2 3 + ONL 16); depodan çıkan 103 (ilk dağıtım)
    # + 12 (replenishment) + 5 (outlet) + 7 (replenishment, yolda) = 127
    assert a["satilan_h"] == 61 and a["gonderilen_h"] == 127
    assert a["str_h"] == pytest.approx(61 / 127)
    assert a["satis_ilk_alim"] == pytest.approx(61 / 253)
    # Banu kuralı: STR ≥ %55 değil ve h < 3 (3. pazartesi öncesi) → tetiklenmez
    assert not a["banu_h"]
    # M1 her gün stoklu; M2'nin beden ortalaması 5,5 stoksuz gün (eşik 3) → bir mağaza
    assert a["tasiyan_magaza"] == 2 and a["stoksuz_magaza"] == 1
    assert a["stoksuz_en_cok"] == pytest.approx(5.5)
    # yayımlanan RPT: 200 sipariş, 10 red, 190 giren; indirime (17. gün) 3 gün kala geldi
    assert a["banu_rpt"] and a["rpt"] == 200 and a["rpt_giren"] == 190
    assert a["rpt_gelis_gun"] == 3 and a["rpt_h"] == pytest.approx(-1 / 7)
    # gelişin olduğu pazartesi (14. gün) iki mağazada da mal var
    assert a["gelis_tasiyan"] == 2 and a["gelis_bos"] == 0 and a["bos_pay"] == 0
    assert a["depoda_pay"] == pytest.approx(150 / 190)
    # RPT'siz option yok; OPT-Q'nun ilk dağıtımı olmadığından taşıyan mağazası yok
    assert f.loc["OPT-Q", "tasiyan_magaza"] == 0


def test_gelis_durumu_oyuncak_bos_magaza():
    """Geliş haftasının pazartesi fotoğrafında stoku 0 olan taşıyan mağaza `bos`; son 28 günde
    satışı da yoksa `satissiz` (replenishment'ın "satış sıfır" kuralı ona mal göndermezdi)."""
    t, opt = rpt_tablolari()
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    # 3. pazartesi (gun 21): M2'nin S'si 0 ama M'si 5 → M2 toplam 5 (boş değil); stoku sıfırlayalım
    st = t["stok"].copy()
    st.loc[(st["tarih"] == pd.Timestamp("2025-02-24")) & (st["magaza_id"] == "M2"), "adet"] = 0
    t2 = dict(t)
    t2["stok"] = st
    g = hikaye_sec.gelis_durumu(t2, hh, pd.DataFrame({"option_id": ["OPT-A"],
                                                       "gelis": [pd.Timestamp("2025-02-26")]}))
    g = g.set_index("magaza_id")
    assert g.loc["M2", "bos"] and not g.loc["M1", "bos"]
    # M2 son 28 günde (11 Şubat-24 Şubat) yalnız ilk 3 gün sattı: 3 adet → satışsız değil
    assert g.loc["M2", "satis_28"] == 3 and not g.loc["M2", "satissiz"]
    assert g.loc["M1", "satis_toplam"] == 42


# ---------------------------------------------------------------------------
# Gerçek v4 verisi
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ozellik(veri):
    t, opt, hh = veri["t"], veri["opt"], veri["hh"]
    return t, opt, hh, hikaye_sec.ozellikler(t, opt, hh)


@pytest.mark.veri
def test_banu_kurali_yayimlananla_ayni(ozellik):
    """Tablodan kurulan STR ile kural, yayımlanan RPT siparişlerinin 3. pazartesi verilenlerini birebir üretir."""
    _, _, _, f = ozellik
    yayim = f["rpt_h"].eq(hikaye_sec.HIKAYE_HAFTASI)
    assert yayim.sum() > 0
    assert (f["banu_h"] == yayim).all()
    assert (f.loc[f["banu_h"], "str_h"] >= 0.55).all()


@pytest.mark.veri
def test_merdiven_gercek_veride_birebir_sahne_var(ozellik):
    _, _, _, f = ozellik
    hb, gb = hit_bayraklari(f), gec_bayraklari(f)
    assert hb.all(axis=1).sum() >= 1 and gb.all(axis=1).sum() >= 1
    assert [n for _, n in huni(hb)][-1] == hb.all(axis=1).sum()
    assert set(f["sezon_kodu"]) == {"SS25"} and set(f["line"]) == {"Collection"}


@pytest.mark.veri
def test_yurutucu_secimi_merdivenle_tutarli(ozellik):
    t, opt, hh, f = ozellik
    s = sec_ozellikten(f)
    assert (s["merdiven"]["hit"], s["merdiven"]["gec"]) == hikaye_sec.YURUTUCU_SECIMI
    h = hikaye_sec.sec(t, opt, hh, f=f)
    assert (h.hit_option, h.gec_option) == hikaye_sec.YURUTUCU_SECIMI
    assert h.gevseyen == {"hit": [], "gec": []}            # birebir sahne: gevşeyen yok
    assert h.hit_tedarikci in set(t["tedarikci"]["ad"]) and h.gec_tedarikci in set(t["tedarikci"]["ad"])
    ad = t["magaza"].set_index("magaza_id")["ad"]
    for sahne in ("hit", "gec"):
        assert len(h.magazalar[sahne]) >= 3
        assert all(m in ad.index and ad[m] for m in h.magazalar[sahne])


@pytest.mark.veri
def test_gevseyen_override_gercek_veride(ozellik):
    t, opt, hh, f = ozellik
    # uzak doğulu bir option'ı hit olarak zorlarsak yerli (gevşemez) tutmuyor diye kaydedilir
    uzak = f[(f["mense"] == "Uzak Doğu") & f["banu_rpt"]].iloc[0]["option_id"]
    yerli = f[f["mense"] == "Yerli"].iloc[0]["option_id"]
    h = hikaye_sec.sec(t, opt, hh, zorla=(uzak, yerli), f=f)
    assert "yerli" in h.gevseyen["hit"] and "uzak_dogu" in h.gevseyen["gec"]


@pytest.mark.veri
def test_ozet_gercek_veride_tutarli(ozellik):
    t, opt, hh, f = ozellik
    h = hikaye_sec.sec(t, opt, hh, f=f)
    o = hikaye_sec.ozet(t, opt, hh, f, h, plan=pd.Series({h.hit_option: 1500.0}))
    hit, gec = o["hit"], o["gec"]
    assert hit["plan"] == 1500 and gec["plan"] is None
    for s in (hit, gec):
        # üç haftalık haftalık satış toplamı = karar sabahı kurulan "satılan" (mağaza + online)
        assert sum(s["haftalik_satis"]) == s["satilan"]
        assert s["tasiyan_magaza"] >= s["stoklu_magaza"] >= 0
        assert s["rpt"]["depoda_cikista"] + s["rpt"]["cikisa_kadar"] == s["rpt"]["giren"]
        assert s["rpt"]["depoda_cikista"] <= s["rpt"]["depo_cikista"]
        assert s["rpt"]["outlete"] + s["rpt"]["depoda_kalan"] == s["rpt"]["depoda_cikista"]
        assert s["rpt"]["kalan_son"] == s["rpt"]["depo_son"] + s["rpt"]["raf_son"]
        assert s["rpt"]["bosa"] <= min(s["rpt"]["giren"], s["rpt"]["kalan_son"])
    assert hit["mense"] == "Yerli" and hit["dalga"] == 3 and hit["banu_tetik"]
    assert gec["mense"] == "Uzak Doğu" and gec["banu_tetik"]
    assert hikaye_sec.GELIS_ARALIGI[0] <= gec["rpt"]["indirime_kalan_gun"] <= hikaye_sec.GELIS_ARALIGI[1]
    assert gec["rpt"]["gelis_bos"] / gec["rpt"]["gelis_tasiyan"] >= BOS_PAY_ESIGI


@pytest.mark.veri
def test_cli_calisir(capsys, ozellik):
    """CLI gerçek veride uçtan uca: iki sahne ve ölçüt bilgisi basılır."""
    o = hikaye_sec.main(["--adaylar"])
    cikti = capsys.readouterr().out
    assert o["hit"]["option_id"] in cikti and o["gec"]["option_id"] in cikti
    assert "HİT" in cikti and "GEÇ GELEN" in cikti and "en yakin adaylar" in cikti
    with pytest.raises(LookupError, match="havuzda yok"):
        hikaye_sec.main(["--hikaye", "YOK-1:YOK-2"])
