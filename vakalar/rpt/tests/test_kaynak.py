import pandas as pd
import pytest

from rpt import kaynak


def test_oyuncak_hafta_eslemesi(oyuncak):
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    assert len(hh) == 4 * 4   # 4 hücre × 4 hafta (çıkış 28. gün)
    c = hh.set_index(["magaza_id", "urun_id", "h"])
    # h. haftanın stoklu günü (h+1). pazartesinin fotoğrafından gelir
    assert c.loc[("M2", "A-S", 0), "stoklu_gun"] == 3
    assert c.loc[("M2", "A-S", 1), "stoklu_gun"] == 0
    assert c.loc[("M1", "A-S", 3), "stoklu_gun"] == 7
    assert c.loc[("M2", "A-S", 0), "satis"] == 3 and c.loc[("M2", "A-S", 0), "kayip"] == 4
    # İndirim 17. gün (2. haftanın 3. günü): indirim öncesi bölünmesi
    assert c.loc[("M1", "A-S", 2), "acik_io"] == 3
    assert c.loc[("M1", "A-S", 2), "satis_io"] == 6 and c.loc[("M1", "A-S", 2), "satis"] == 14
    assert c.loc[("M1", "A-S", 3), "acik_io"] == 0
    assert (hh["acik_gun"] == 7).all()
    assert c.loc[("M1", "A-S", 0), "ilk_dagitim"] == 60


def test_oyuncak_option_panel(oyuncak):
    t, opt = oyuncak
    p = kaynak.option_panel(t, opt, sezonlar=("SS25",)).set_index("h")
    assert p.loc[0, "satis"] == 7 * 3 + 3
    assert p.loc[0, "talep"] == p.loc[0, "satis"] + 4
    assert p.loc[0, "sevk"] == 103 and p.loc[1, "sevk"] == 0
    assert p.loc[0, "depo_stok"] == 150
    assert p.loc[1, "stoklu_magaza"] == 2 and p.loc[1, "tasiyan_magaza"] == 2
    assert p["kum_satis"].iloc[-1] == p["satis"].sum()


def test_temizle_mukerrer_ve_hayalet(oyuncak):
    t, _ = oyuncak
    t = dict(t)
    t["satis"] = pd.concat([t["satis"], t["satis"].iloc[[0]]], ignore_index=True)
    iade = t["satis"].iloc[[1]].assign(adet=-1)
    t["satis"] = pd.concat([t["satis"], iade], ignore_index=True)
    hayalet = pd.DataFrame({"tarih": [pd.Timestamp("2025-02-17")], "magaza_id": ["M9"],
                            "urun_id": ["A-S"], "adet": [2], "stoklu_gun": [7]})
    t["stok"] = pd.concat([t["stok"], hayalet], ignore_index=True)
    temiz = kaynak.temizle(t)
    assert len(temiz["satis"]) == len(t["satis"]) - 1          # iade satırı kalır
    assert (temiz["satis"]["adet"] < 0).sum() == 1
    assert "M9" not in set(temiz["stok"]["magaza_id"])
    assert len(temiz["stok"]) == len(t["stok"]) - 1


def test_tarihten_once_fotograf_dahil(oyuncak):
    t, _ = oyuncak
    sinir = pd.Timestamp("2025-02-24")
    k = kaynak.tarihten_once(t, sinir)
    assert k["satis"]["tarih"].max() < sinir
    assert k["stok"]["tarih"].max() == sinir


@pytest.mark.veri
def test_gercek_panel_akli_basinda(veri):
    t, opt, hh = veri["t"], veri["opt"], veri["hh"]
    assert (hh["stoklu_gun"] <= hh["acik_gun"]).all()
    assert hh["acik_gun"].between(0, 7).all()
    assert (hh["satis_io"] <= hh["satis"]).all() and (hh["acik_io"] <= hh["acik_gun"]).all()
    p = kaynak.option_panel(t, opt, hh)
    assert (p.loc[p["h"] == 0, "magaza_stok"] == 0).all()
    assert (p["depo_stok"] >= 0).all()
    assert (p["stoklu_magaza"] <= p["tasiyan_magaza"]).all()
    # Panelin satışı, temiz satış tablosunun lansman→çıkış toplamına eşit
    o = opt[opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    s = t["satis"][t["satis"]["adet"] > 0].merge(t["urun"][["urun_id", "option_id"]]).merge(
        o[["option_id", "lansman_tarihi", "cikis_tarihi"]])
    s = s[(s["tarih"] >= s["lansman_tarihi"]) & (s["tarih"] < s["cikis_tarihi"])]
    assert p["satis"].sum() == s["adet"].sum()
    col = o[o["line"] == "Collection"]["option_id"]
    assert set(col) <= set(p["option_id"])
    # İlk alım siparişten, plan dünyadan: plan / 0,80 ≤ ilk alım (MOQ yuvarlaması)
    # (Tam sezonlar: v3 `siparis`i yalnız pencerede satışı olan option'lar için
    # yazar; AW23'ün pencerede hiç satmayan bir option'ı ilk alımsız görünür.)
    c = opt[(opt["line"] == "Collection") & opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    assert (c["ilk_alim"] >= c["plan_sezon"] / 0.80 - 1e-6).all()


@pytest.mark.veri
def test_temizlik_gercek_veri(veri):
    ham = kaynak.tablolari_oku()
    t = veri["t"]
    assert len(ham["satis"]) - len(t["satis"]) == 80          # v3 MUKERRER_KAYIT
    assert 0 < len(ham["stok"]) - len(t["stok"]) <= 60        # v3 HAYALET_STOK_KAYDI
