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
    assert c.loc[("M2", "A-S", 0), "satis"] == 3 and c.loc[("M2", "A-S", 1), "satis"] == 0
    # İndirim 17. gün (2. haftanın 3. günü): indirim öncesi bölünmesi
    assert c.loc[("M1", "A-S", 2), "acik_io"] == 3
    assert c.loc[("M1", "A-S", 2), "satis_io"] == 6 and c.loc[("M1", "A-S", 2), "satis"] == 14
    assert c.loc[("M1", "A-S", 3), "acik_io"] == 0
    assert (hh["acik_gun"] == 7).all()
    # İlk dağıtım v4'te `hedef` ve varışlı sevkiyattan; replenishment sayılmaz
    assert c.loc[("M1", "A-S", 0), "ilk_dagitim"] == 60
    assert c.loc[("M2", "A-M", 2), "ilk_dagitim"] == 10


def test_kayip_sutunu_yok(oyuncak):
    """v3'ün `kayip` sütunları v4'te yok: gerçek talep yalnız hakemden gelir."""
    t, opt = oyuncak
    assert "kayip_satis" not in t
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    p = kaynak.option_panel(t, opt, hh, ("SS25",))
    for k in ("kayip", "kayip_io", "talep"):
        assert k not in hh.columns and k not in p.columns


def test_oyuncak_option_panel(oyuncak):
    t, opt = oyuncak
    p = kaynak.option_panel(t, opt, sezonlar=("SS25",)).set_index("h")
    # mağaza satışı 7×3 + 3; online 7 (S) + 2 (M, 5. gün)
    assert p.loc[0, "magaza_satis"] == 7 * 3 + 3
    assert p.loc[0, "online_satis"] == 7 + 2
    assert p.loc[0, "satis"] == 24 + 9
    assert p.loc[2, "satis_io"] == 9 + 3     # indirim öncesi 3 gün: mağaza 6 + 3, online 3
    # sevk = mağazaya VARAN ilk dağıtım + replenishment; varış haftasına yazılır
    assert p.loc[0, "sevk"] == 103
    assert p.loc[1, "sevk"] == 12            # gün 6'da çıktı, gün 8'de vardı; yolda kalan (7) ve
    assert p.loc[2, "sevk"] == 0             # outlet / devir / elle transferler sayılmaz
    assert p.loc[0, "depo_stok"] == 150
    assert p.loc[0, "magaza_stok"] == 0      # pazartesi sabahı mağazalar henüz boş
    assert p.loc[1, "stoklu_magaza"] == 2 and p.loc[1, "tasiyan_magaza"] == 2
    assert p["kum_satis"].iloc[-1] == p["satis"].sum()
    assert p["kum_sevk"].iloc[-1] == 115


def test_online_strde_dagitimda_degil(oyuncak):
    """Online satış option panelinin satışına (STR payı) girer; hücre evreninde
    (mağaza dağıtımı) ONL yoktur."""
    t, opt = oyuncak
    hh = kaynak.hucre_hafta(t, opt, ("SS25",))
    assert "ONL" not in set(hh["magaza_id"])
    magaza_toplam = t["satis"].query("magaza_id != 'ONL'")["adet"].sum()
    assert hh["satis"].sum() == magaza_toplam
    p = kaynak.option_panel(t, opt, hh, ("SS25",))
    online_toplam = t["satis"].query("magaza_id == 'ONL'")["adet"].sum()
    assert p["online_satis"].sum() == online_toplam == 28 + 2
    assert p["satis"].sum() == magaza_toplam + online_toplam
    assert p["tasiyan_magaza"].max() == 2    # ONL taşıyan mağaza değil


def test_depo_stok_pazartesi(oyuncak):
    """Günlük depo_stok pazartesi süzülmeden toplanırsa ~7 kat şişer."""
    t, opt = oyuncak
    assert len(t["depo_stok"]) == 28 * 2     # günlük
    p = kaynak.option_panel(t, opt, sezonlar=("SS25",)).set_index("h")
    # h. pazartesinin fotoğrafı: S 100 - 7h, M 50
    assert [p.loc[h, "depo_stok"] for h in range(4)] == [150, 143, 136, 129]
    gunluk_toplam = t["depo_stok"]["adet"].sum()
    assert p["depo_stok"].sum() < gunluk_toplam / 5


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
    assert "ONL" in set(temiz["satis"]["magaza_id"])           # online satış korunur
    assert "M9" not in set(temiz["stok"]["magaza_id"])
    assert len(temiz["stok"]) == len(t["stok"]) - 1
    # gerçek hücreler (varışlı, satışlı) olduğu gibi kalır
    assert len(temiz["sevkiyat"]) == len(t["sevkiyat"]) and len(temiz["depo_stok"]) == len(t["depo_stok"])


def test_tarihten_once_fotograf_dahil(oyuncak):
    t, _ = oyuncak
    sinir = pd.Timestamp("2025-02-24")
    k = kaynak.tarihten_once(t, sinir)
    assert k["satis"]["tarih"].max() < sinir
    assert k["stok"]["tarih"].max() == sinir
    assert k["depo_stok"]["tarih"].max() == sinir


def test_tarihten_once_gelecegi_gizler(oyuncak):
    """Karar sabahından sonra olacak varış, teslim ve kalite sonucu görünmez."""
    t, _ = oyuncak
    t = dict(t)
    sinir = pd.Timestamp("2025-02-17")   # 7. gün
    k = kaynak.tarihten_once(t, sinir)
    # gün 6'da çıkan replenishment gün 8'de varır: çıkış bilinir, varış bilinmez (yolda)
    r = k["sevkiyat"].query("tip == 'replenishment' and adet == 12")
    assert len(r) == 1 and pd.isna(r["varis_tarihi"].iloc[0])
    assert k["sevkiyat"]["tarih"].max() < sinir
    assert (k["sevkiyat"]["varis_tarihi"].dropna() < sinir).all()
    assert t["sevkiyat"]["varis_tarihi"].notna().sum() == 8    # kaynak bozulmaz
    # sipariş: sınırdan sonra verilen yok; teslimi sınırdan sonra olan henüz teslim olmamış
    ilk = t["siparis"].assign(siparis_tarihi=pd.Timestamp("2025-02-01"),
                              gerceklesen_teslim=pd.Timestamp("2025-02-20"))
    gec = t["siparis"].assign(siparis_id="SP2", siparis_tarihi=pd.Timestamp("2025-02-18"))
    t["siparis"] = pd.concat([ilk, gec], ignore_index=True)
    k = kaynak.tarihten_once(t, sinir)
    assert set(k["siparis"]["siparis_id"]) == {"SP1"}
    assert k["siparis"]["gerceklesen_teslim"].isna().all()
    assert k["siparis"]["planlanan_teslim"].notna().all()
    assert len(k["kalite_kontrol"]) == 1
    assert kaynak.tarihten_once(t, pd.Timestamp("2025-02-01"))["kalite_kontrol"].empty


def test_optionlar_tedarikci_ve_ilk_alim(oyuncak):
    t, opt = oyuncak
    o = opt.set_index("option_id").loc["OPT-A"]
    # rpt_hafta, moq_option, mense (ve uzmanlik) tedarikçiden; ilk alım siparişten
    assert (o["rpt_hafta"], o["moq_option"], o["mense"], o["uzmanlik"]) == (4, 300, "Yerli", "dokuma")
    assert o["tedarikci"] == "Ege" and o["ilk_siparis_hafta"] == 12
    assert o["ilk_alim"] == 163 + 90
    assert o["satis_hafta"] == pytest.approx(17 / 7)


def test_gecmis_sezonlar_v4():
    assert kaynak.OYUN_SEZONLARI == ("AW24", "SS25")
    assert kaynak.gecmis_sezonlar("AW24") == ("SS23", "AW23", "SS24")
    assert kaynak.gecmis_sezonlar("SS25") == ("SS23", "AW23", "SS24", "AW24")
    assert "AW22" not in kaynak.TAM_SEZONLAR       # pencere başında yarım
    assert "AW25" not in kaynak.TAM_SEZONLAR       # indirimi pencerenin dışında
    with pytest.raises(ValueError):
        kaynak.gecmis_sezonlar("AW22")


def test_veri_yoksa_acik_hata(tmp_path):
    with pytest.raises(FileNotFoundError, match="lumoda-v4.duckdb"):
        kaynak.veri_yukle(tmp_path / "yok.duckdb")


@pytest.mark.veri
def test_gercek_panel_akli_basinda(veri):
    t, opt, hh = veri["t"], veri["opt"], veri["hh"]
    assert (hh["stoklu_gun"] <= hh["acik_gun"]).all()
    assert hh["acik_gun"].between(0, 7).all()
    assert (hh["satis_io"] <= hh["satis"]).all() and (hh["acik_io"] <= hh["acik_gun"]).all()
    assert "ONL" not in set(hh["magaza_id"])
    p = kaynak.option_panel(t, opt, hh)
    assert (p.loc[p["h"] == 0, "magaza_stok"] == 0).all()
    assert (p["depo_stok"] >= 0).all()
    assert (p["stoklu_magaza"] <= p["tasiyan_magaza"]).all()
    assert (p["online_satis"] > 0).any() and (p["satis"] == p["magaza_satis"] + p["online_satis"]).all()
    # Panelin satışı (mağaza + online), temiz satış tablosunun lansman→çıkış toplamına eşit
    o = opt[opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    s = t["satis"][t["satis"]["adet"] > 0].merge(t["urun"][["urun_id", "option_id"]]).merge(
        o[["option_id", "lansman_tarihi", "cikis_tarihi"]])
    s = s[(s["tarih"] >= s["lansman_tarihi"]) & (s["tarih"] < s["cikis_tarihi"])]
    assert p["satis"].sum() == s["adet"].sum()
    assert p["online_satis"].sum() == s.loc[s["magaza_id"] == "ONL", "adet"].sum()
    col = o[o["line"] == "Collection"]["option_id"]
    assert set(col) <= set(p["option_id"])


@pytest.mark.veri
def test_gercek_depo_stok_pazartesi(veri):
    """Yüklenen depo stoğu ve panel, ham günlük tablonun pazartesi fotoğraflarından."""
    t, opt = veri["t"], veri["opt"]
    with kaynak.baglan() as con:
        gun = con.execute("select count(distinct tarih) from depo_stok").fetchone()[0]
    assert gun == 1096                                           # ham tablo günlük
    assert t["depo_stok"]["tarih"].dt.dayofweek.eq(0).all()      # yüklenen: yalnız pazartesi
    p = kaynak.option_panel(t, opt)
    p0 = p[p["h"] == 0].set_index("option_id")["depo_stok"]
    # lansman sabahı depo = o option'ın o günkü toplam depo stoğu (günlük toplam değil)
    d = t["depo_stok"].merge(t["urun"][["urun_id", "option_id", "lansman_tarihi"]], on="urun_id")
    d = d[d["tarih"] == d["lansman_tarihi"]].groupby("option_id")["adet"].sum()
    assert (p0 == d.reindex(p0.index).fillna(0).astype(int)).all()
    assert p0.sum() > 0


@pytest.mark.veri
def test_gercek_ilk_alim_ve_tedarikci(veri):
    """R2: yayımlanan ilk alım her option'da var ve pozitif; plan ile ilişki
    (~%93) Görev 4'te motorun planıyla sınanır."""
    opt = veri["opt"]
    c = opt[opt["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)]
    assert len(c) > 0 and (c["ilk_alim"] > 0).all()
    # tedarikçi alanları her option'da dolu (urun.tedarikci_id → tedarikci)
    for k in ("rpt_hafta", "moq_option", "mense", "uzmanlik", "ilk_siparis_hafta"):
        assert c[k].notna().all(), k
    assert (c["moq_option"] > 0).all() and c["rpt_hafta"].between(1, 20).all()


@pytest.mark.veri
def test_temizlik_gercek_veri(veri):
    ortak = kaynak.ortak
    with kaynak.baglan() as con:
        ham = con.execute("select count(*) from satis").fetchone()[0]
        ad = ortak.temiz_satis(con)
        temiz = con.execute(f"select count(*) from {ad}").fetchone()[0]
        assert ham - temiz == 200                                # v4 MUKERRER_KAYIT
        cesit = ortak.cesit_hucreleri(con)
        stok_ham = con.execute("select count(*) from stok").fetchone()[0]
        stok_temiz = con.execute(
            f"select count(*) from stok s join {cesit} c using (magaza_id, urun_id)").fetchone()[0]
        assert stok_ham - stok_temiz == 150                      # v4 HAYALET_STOK_KAYDI
        # yüklenen kapsam, temiz görünümlerle aynı satır sayısı
        t = veri["t"]
        kapsam = "(select urun_id from urun where sezon_kodu in ('SS23','AW23','SS24','AW24','SS25'))"
        assert len(t["satis"]) == con.execute(
            f"select count(*) from {ad} where urun_id in {kapsam}").fetchone()[0]
        assert len(t["stok"]) == con.execute(
            f"select count(*) from stok s join {cesit} c using (magaza_id, urun_id) "
            f"where s.urun_id in {kapsam}").fetchone()[0]
