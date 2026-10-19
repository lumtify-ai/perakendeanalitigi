"""`allocation.kalibrasyon`: pay WAPE'si, koşusuz seçim (SS23 ile öğren, SS24'te ölç), tutma
eğrisi ve SS24 simülasyonunun seçimi; `allocation.oyun`'un iki kalibrasyon ölçütü.

Koşusuz test test_ogrenme'nin uzun oyuncak dünyasıyla (GA SS23, GB SS24); simülasyon testi sahte
`kos_fn` ile (motor koşmaz)."""

import numpy as np
import pandas as pd
import pytest
from test_ogrenme import GA, GB, M1, M2, M3, M4, gecmis_dunya, gecmis_tablolar

from allocation import kalibrasyon, kaynak, ogrenme, sabitler
from allocation.politika import Ayar


def _pay(satirlar):
    return pd.DataFrame(satirlar, columns=["option", "magaza", "pay"])


def _talep(satirlar):
    return pd.DataFrame(satirlar, columns=["option", "magaza", "talep"])


# ---------------------------------------------------------------- pay WAPE


def test_pay_wape_ornek():
    pay = _pay([(0, 0, 0.7), (0, 1, 0.3)])
    gercek = _talep([(0, 0, 5.0), (0, 1, 5.0)])
    assert kalibrasyon.pay_wape(pay, gercek) == pytest.approx(0.2)


def test_pay_wape_olcekten_bagimsiz_ve_agirlikli():
    """Pay ve talep option içinde normalleşir; option'lar ağırlıkla ortalanır; gerçeği olmayan
    (NaN) mağaza aday kümesinden düşer; payı olmayan mağaza 0 alır."""
    pay = _pay([(0, 0, 7.0), (0, 1, 3.0), (1, 0, 1.0), (1, 2, 5.0)])
    gercek = _talep([(0, 0, 50.0), (0, 1, 50.0), (0, 2, np.nan), (1, 0, 2.0), (1, 1, 2.0)])
    # option 1: aday {0, 1}; pay {1, 0} -> {1, 0}; gerçek {0,5, 0,5} -> WAPE 0,5
    w = kalibrasyon.option_wape(pay, gercek)
    assert w.to_dict() == pytest.approx({0: 0.2, 1: 0.5})
    assert kalibrasyon.pay_wape(pay, gercek) == pytest.approx(0.35)
    assert kalibrasyon.pay_wape(pay, gercek, agirlik={0: 3.0, 1: 1.0}) == pytest.approx(0.275)


def test_pay_wape_bos_pay_esit_sayilir_ve_talepsiz_option_disarida():
    pay = _pay([(0, 0, 0.0), (0, 1, 0.0)])
    gercek = _talep([(0, 0, 3.0), (0, 1, 1.0), (1, 0, 0.0), (1, 1, 0.0)])
    w = kalibrasyon.option_wape(pay, gercek)
    assert list(w.index) == [0] and w[0] == pytest.approx(0.25)


def test_spearman():
    assert kalibrasyon.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert kalibrasyon.spearman([1, 2, 3, np.nan], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert np.isnan(kalibrasyon.spearman([1, 1, 1], [1, 2, 3]))


# ---------------------------------------------------------------- tutma eğrisi


def test_belirsizlik_t_o_ortalama_ve_aralik():
    rng = np.random.default_rng(3)
    ids = [f"O{i}" for i in range(40)]
    u = pd.Series(rng.lognormal(0, 1, 40), index=ids)
    u.iloc[3] = np.nan                       # ölçü yok: ortalama option
    u.iloc[5] = 0.0
    agirlik = pd.Series(rng.integers(500, 5000, 40).astype(float), index=ids)
    tbar = sabitler.BELIRSIZLIK_TBAR
    for gamma in (0.5, 1.0, 2.0):
        t = kalibrasyon.tutma_egrisi(u, agirlik, gamma)
        assert list(t.index) == ids
        assert (t >= 0).all() and (t <= 2 * tbar + 1e-12).all()
        assert float((t * agirlik).sum() / agirlik.sum()) == pytest.approx(tbar, abs=1e-9)
        sira = u.dropna().sort_values().index
        assert t[sira].is_monotonic_increasing          # belirsiz option daha çok tutulur
        assert t.iloc[5] == 0.0
    assert (kalibrasyon.tutma_egrisi(u, agirlik, 0.0) == tbar).all()
    # dik eğri üst sınıra dayanır, kırpılan pay ötekilere dağılır
    dik = kalibrasyon.tutma_egrisi(u, agirlik, 2.0)
    assert (dik == 2 * tbar).any()


def test_tutma_egrisi_hepsi_ayni_ya_da_sifir():
    agirlik = pd.Series([1.0, 2.0, 3.0], index=list("abc"))
    for u in (pd.Series([2.0, 2.0, 2.0], index=list("abc")), pd.Series([0.0, 0.0, np.nan], index=list("abc"))):
        assert (kalibrasyon.tutma_egrisi(u, agirlik, 1.0) == sabitler.BELIRSIZLIK_TBAR).all()


# ---------------------------------------------------------------- seçim kuralı


def test_secim_bulunabilirlik_esitlikte_az_kalan():
    s = [{"ad": "a", "bulunabilirlik": 80.0, "sezon_sonu_kalan_yuzde": 20.0},
         {"ad": "b", "bulunabilirlik": 80.25, "sezon_sonu_kalan_yuzde": 25.0},
         {"ad": "c", "bulunabilirlik": 79.97, "sezon_sonu_kalan_yuzde": 18.0},
         {"ad": "d", "bulunabilirlik": 79.9, "sezon_sonu_kalan_yuzde": 5.0}]   # 0,35 puan geride
    assert kalibrasyon.secim(s)["ad"] == "c"
    assert kalibrasyon.secim(s[:2] + [{"ad": "e", "bulunabilirlik": 81.0, "sezon_sonu_kalan_yuzde": 30.0}])["ad"] == "e"


# ---------------------------------------------------------------- koşusuz


@pytest.fixture(scope="module")
def gecmis():
    """test_ogrenme'nin uzun oyuncak dünyası; LightGBM'in okuduğu mağaza alanlarıyla."""
    w = gecmis_dunya()
    w.magazalar = w.magazalar.assign(metrekare=[600, 450, 300, 520, 800, 0], kapasite=[6000, 4500, 3000, 5200, 8000, 0])
    return w, gecmis_tablolar()


def test_karar_gunu_ilk_dagitimdan(gecmis):
    w, t = gecmis
    # GB'nin (SS24) ilk dağıtımı lansmandan (2024-03-18) iki gün önce çıkar
    assert kalibrasyon.karar_gunu(t, w, "SS24") == pd.Timestamp("2024-03-16")


def test_erken_gercek_ss24(gecmis):
    w, t = gecmis
    g = kalibrasyon.erken_gercek(t, w, "SS24")
    assert set(g["option"]) == {GB} and set(g["magaza"]) == {M1, M2, M3, M4}
    assert (g["talep"] > 0).all() and (g["stoklu_gun"] > 0).all()
    # kesim 2024-06-02 (R5) dahil: matrisler 2024-06-03'e dek, bütün tablolarla aynı sonuç
    assert kaynak.erken_kesim(w, "SS24") == pd.Timestamp("2024-06-02")
    s, f = kaynak.gunluk_matrisler(t, w, pd.Timestamp("2024-06-03"))
    dogrudan = ogrenme.erken_talep(s, f, kaynak.harita_kur(w), w, np.array([GB]), ogrenme.ilk_varislar(t, w))
    pd.testing.assert_frame_equal(g, dogrudan)


def test_kosusuz_yalniz_ss23_gorur(gecmis):
    """SS24 karar gününden sonraki satırlar (SS24'ün bütün akışı) bozulunca öğrenilenler ve seçim
    aynı (gerçek pay ayrıca verilir: bozulan veriden ölçülmesin)."""
    w, t = gecmis
    gercek = kalibrasyon.erken_gercek(t, w, "SS24")
    once = kalibrasyon.kosusuz(t, w, gercek=gercek)
    karar = kalibrasyon.karar_gunu(t, w, "SS24")
    bozuk = {ad: df.copy() for ad, df in t.items()}
    for ad in ("satis", "stok"):
        d = bozuk[ad]
        sonra = d["tarih"] >= karar
        assert sonra.any()
        d.loc[sonra, "adet"] = d.loc[sonra, "adet"] * 7 + 3
    sv = bozuk["sevkiyat"]
    sonra = (sv["varis_tarihi"] >= karar).to_numpy()
    sv.loc[sonra, "adet"] = sv.loc[sonra, "adet"] * 5 + 1
    sonra_kosu = kalibrasyon.kosusuz(bozuk, w, gercek=gercek)

    assert once.karar_gunu == karar
    assert (once.en_az, once.tahmin_parametreleri, once.belirsizlik_olcusu, once.kaynak) == (
        sonra_kosu.en_az, sonra_kosu.tahmin_parametreleri, sonra_kosu.belirsizlik_olcusu, sonra_kosu.kaynak)
    # Lumoda'nın gerçekleşen SS24 payı bağlam satırıdır (SS24'ün kendi kararı, öğrenme değil)
    def ogrenilen(c):
        return c.tablo[~((c.tablo["asama"] == "taban") & (c.tablo["aday"] == "lumoda")).to_numpy()]

    pd.testing.assert_frame_equal(ogrenilen(once), ogrenilen(sonra_kosu))
    assert once.endeks.kimlik == sonra_kosu.endeks.kimlik
    assert once.tahminci.kimlik == sonra_kosu.tahminci.kimlik
    pd.testing.assert_series_equal(once.belirsizlik, sonra_kosu.belirsizlik)
    # yalnız SS23 öğrenildi
    assert once.endeks.option.tolist() == [GA]


def test_kosusuz_izgara_ve_secim(gecmis):
    w, t = gecmis
    c = kalibrasyon.kosusuz(t, w)
    tab = c.tablo
    assert sorted(tab.loc[tab["asama"] == "benzer", "en_az"].astype(int)) == list(kalibrasyon.EN_AZ_IZGARASI)
    tah = tab[tab["asama"] == "tahmin"]
    assert len(tah) == len(kalibrasyon.NUM_LEAVES) * len(kalibrasyon.MIN_CHILD_SAMPLES)
    assert set(c.tahmin_parametreleri) == set(kalibrasyon.tahmin.VARSAYILAN)
    secili = tab[tab["secildi"]]
    assert set(secili["asama"]) == {"benzer", "tahmin", "belirsizlik"}
    # seçilen her aşamada en küçük WAPE (belirsizlikte en büyük Spearman)
    for asama in ("benzer", "tahmin"):
        a = tab[tab["asama"] == asama]
        assert secili.loc[secili["asama"] == asama, "wape"].iloc[0] == a["wape"].min()
    assert c.belirsizlik_olcusu in kalibrasyon.BELIRSIZLIK_OLCULERI
    assert c.kaynak in ("benzer", "tahmin")
    assert list(c.belirsizlik.index) == list(c.agirlik.index) == ["OPT-GB"]


# ---------------------------------------------------------------- simülasyon


class _SahteKos:
    """Ada göre sabit ölçütler; her çağrının tanımını saklar."""

    def __init__(self, olcutler):
        self.olcutler = olcutler
        self.cagrilar = []

    def __call__(self, ad, tanim):
        self.cagrilar.append((ad, tanim))
        b, k = self.olcutler.get(ad, (50.0, 50.0))
        return {"bulunabilirlik": b, "sezon_sonu_kalan_yuzde": k}


def _cevrimdisi():
    ids = ["O1", "O2", "O3"]
    return kalibrasyon.Cevrimdisi(
        en_az=5, tahmin_parametreleri={**kalibrasyon.tahmin.VARSAYILAN, "num_leaves": 63, "min_child_samples": 100},
        belirsizlik_olcusu="benzer_dk",
        tablo=pd.DataFrame(), kaynak="benzer", karar_gunu=pd.Timestamp("2024-02-09"), endeks=None,
        tahminci=None, belirsizlik=pd.Series([0.2, 0.5, 1.0], index=ids),
        agirlik=pd.Series([1000.0, 2000.0, 1500.0], index=ids))


def test_simulasyon_penceresi_ss24():
    kos = _SahteKos({
        "kal_benzer_tavanli": (70.0, 30.0), "kal_benzer_tavansiz": (69.0, 20.0),
        "kal_tahmin_tavanli": (71.2, 28.0), "kal_tahmin_tavansiz": (71.0, 25.0),   # eşit: daha az kalan
        "kal_belirsizlik_g0.5": (68.0, 30.0), "kal_belirsizlik_g1": (68.5, 31.0),
        "kal_belirsizlik_g2": (68.3, 29.0),
    })
    s = kalibrasyon.simulasyon(kos, _cevrimdisi())
    assert all(t.ayar.sezon == sabitler.KAL_SEZONU == "SS24" for _, t in kos.cagrilar)
    adlar = [a for a, _ in kos.cagrilar]
    kollar = [a for a, t in kos.cagrilar if t.kol != "lumoda"]
    assert len(kollar) == 7 and len(set(adlar)) == len(adlar)
    assert adlar[0] == "lumoda"                    # referans: yayımlanan dünya (önbellekli)
    assert (s.tavan, s.belirsizlik_taban, s.gamma) == (False, "tahmin", 2.0)
    bel = [t for _, t in kos.cagrilar if t.kol == "belirsizlik"]
    assert {t.gamma for t in bel} == set(kalibrasyon.GAMMA_IZGARASI)
    for t in bel:
        assert t.taban == "tahmin" and t.ayar.tavan is False
        assert set(t.t_o) == {"O1", "O2", "O3"}
        ort = sum(t.t_o[o] * w for o, w in _cevrimdisi().agirlik.items()) / _cevrimdisi().agirlik.sum()
        assert ort == pytest.approx(sabitler.BELIRSIZLIK_TBAR)
    ilk4 = [t for _, t in kos.cagrilar if t.kol in ("benzer", "tahmin")]
    assert all(t.ayar.tutma == 0.0 for t in ilk4)
    assert {(t.kol, t.ayar.tavan) for t in ilk4} == {(k, v) for k in ("benzer", "tahmin") for v in (True, False)}
    assert len(s.tablo) == 8 and s.tablo["secildi"].sum() == 2


def test_kal_kol_parametreleri():
    t = kalibrasyon.KalKol("belirsizlik", Ayar(sezon="SS24", tavan=False), taban="benzer", gamma=1.0,
                           t_o={"O1": 0.3})
    p = t.parametreler()
    assert p["blok"] == "kalibrasyon" and p["kol"] == "belirsizlik" and p["gamma"] == 1.0
    assert p["taban"] == "benzer"


# ---------------------------------------------------------------- JSON


def test_json_gidis_donus(tmp_path):
    c = _cevrimdisi()
    s = kalibrasyon.Simulasyon(tavan=True, gamma=1.0, belirsizlik_taban="benzer",
                               tablo=pd.DataFrame([{"ad": "x", "bulunabilirlik": 1.0, "secildi": True}]))
    yol = kalibrasyon.yaz(c, s, tmp_path / "k.json", sure_sn=1.5)
    d = kalibrasyon.oku(yol)
    assert d["en_az"] == 5 and d["tavan"] is True and d["gamma"] == 1.0
    assert d["tahmin_parametreleri"] == {**kalibrasyon.tahmin.VARSAYILAN, "num_leaves": 63, "min_child_samples": 100}
    assert d["belirsizlik_olcusu"] == "benzer_dk" and d["belirsizlik_taban"] == "benzer"
    assert d["sezon"] == "SS24" and d["karar_gunu"] == "2024-02-09" and d["sure_sn"] == 1.5
    assert d["izgara"]["en_az"] == list(kalibrasyon.EN_AZ_IZGARASI) and d["izgara_ucunda"] == []
    assert d["belirsizlik_spearman"] is None and d["gamma_bulunabilirlik_araligi_puan"] is None


def test_json_belirsizlik_gucu_ve_uc_secim(tmp_path):
    """Seçilen ölçünün Spearman'ı, γ koşularının aralığı ve ızgara ucundaki seçim JSON'da açık."""
    c = _cevrimdisi()
    c = kalibrasyon.Cevrimdisi(**{**c.__dict__, "en_az": max(kalibrasyon.EN_AZ_IZGARASI), "tablo": pd.DataFrame([
        {"asama": "belirsizlik", "aday": "benzer_dk", "spearman": 0.05, "secildi": False},
        {"asama": "belirsizlik", "aday": "benzer_tahmin_ayrisma", "spearman": 0.11, "secildi": True}])})
    s = kalibrasyon.Simulasyon(tavan=True, gamma=2.0, belirsizlik_taban="tahmin", tablo=pd.DataFrame([
        {"asama": "tavan", "bulunabilirlik": 60.0, "sezon_sonu_kalan_yuzde": 30.0},
        {"asama": "gamma", "bulunabilirlik": 75.70, "sezon_sonu_kalan_yuzde": 24.59},
        {"asama": "gamma", "bulunabilirlik": 75.74, "sezon_sonu_kalan_yuzde": 24.56}]))
    d = kalibrasyon.oku(kalibrasyon.yaz(c, s, tmp_path / "k.json"))
    assert d["belirsizlik_spearman"] == pytest.approx(0.11)
    assert d["gamma_bulunabilirlik_araligi_puan"] == pytest.approx(0.04)
    assert d["gamma_kalan_araligi_puan"] == pytest.approx(0.03)
    assert d["izgara_ucunda"] == ["en_az"]


# ---------------------------------------------------------------- oyun'un kalibrasyon ölçütleri


def _gercek(satirlar):
    df = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id", "talep", "kendi_satis"])
    df["tarih"] = pd.to_datetime(df["tarih"])
    return df


def _sevk(satirlar):
    df = pd.DataFrame(satirlar, columns=["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip"])
    for s in ("tarih", "varis_tarihi"):
        df[s] = pd.to_datetime(df[s])
    return df


def test_kal_olcutleri_oyuncak(dunya):
    """Oyuncak dünyada SS25 Collection (A, B, X): bulunabilirlik fiziksel mağazalarda, option'ın ilk
    dağıtım varışından çıkışına (hariç); sezon sonu kalan = çıkıştaki outlet akışı + fiziksel
    hücrelerin stok devri ÷ (teslim alınan ilk alım + RPT)."""
    from allocation import kaynak, oyun

    h = kaynak.harita_kur(dunya)
    opt = kaynak.oyun_optionlari(dunya, "SS25")
    gercek = _gercek([
        ("2025-02-10", "M1", "OPT-A-1", 2, 2),      # stoklu
        ("2025-02-11", "M1", "OPT-A-1", 1, 0),      # stoksuz
        ("2025-02-12", "M2", "OPT-A-2", 1, 1),      # stoklu
        ("2025-02-10", "ONL", "OPT-A-1", 5, 0),     # online: dışarıda
        ("2025-02-09", "M1", "OPT-A-1", 1, 0),      # ilk varıştan önce: dışarıda
        ("2025-08-25", "M1", "OPT-A-1", 1, 0),      # çıkış günü: dışarıda
        ("2025-02-10", "M1", "OPT-GA-1", 1, 0),     # başka sezon: dışarıda
        ("2025-02-10", "MO", "OPT-C-1", 1, 0),      # outlet mağazası, Outlet line: dışarıda
    ])
    sevk = _sevk([
        ("2025-02-08", "2025-02-10", "DEPO", "M1", "OPT-A-1", 6, "ilk_dagitim"),
        ("2025-02-08", "2025-02-11", "DEPO", "M2", "OPT-A-2", 6, "ilk_dagitim"),
        ("2025-08-25", "2025-08-26", "M1", "MO", "OPT-A-1", 10, "outlet_akisi"),
        ("2025-08-25", "2025-08-26", "DEPO", "MO", "OPT-A-2", 20, "outlet_akisi"),
        ("2025-08-27", "2025-08-28", "M1", "DEPO", "OPT-A-1", 3, "stok_devri"),
        ("2025-11-17", "2025-11-18", "MO", "DEPO", "OPT-A-1", 15, "stok_devri"),   # outlet penceresi sonu
        ("2023-08-28", "2023-08-29", "M1", "MO", "OPT-GA-1", 9, "outlet_akisi"),   # başka sezon
    ])
    siparis = pd.DataFrame({
        "siparis_id": ["SP1", "SP1", "SP2", "SP3", "SP4"], "tip": ["ilk", "ilk", "rpt", "rpt", "ilk"],
        "option_id": ["OPT-A", "OPT-A", "OPT-A", "OPT-A", "OPT-GA"],
        "gerceklesen_teslim": pd.to_datetime(["2025-01-20", "2025-01-20", "2025-04-01", None, "2023-01-20"]),
        "adet": [100, 100, 50, 40, 999]})
    kalite = pd.DataFrame({"siparis_id": ["SP1", "SP2", "SP4"], "hatali": [20, 5, 7]})

    assert oyun.bulunabilirlik(gercek, sevk, dunya, h, opt) == pytest.approx(100 * 2 / 3)
    assert oyun.sezon_sonu_kalan_yuzde(sevk, siparis, kalite, dunya, h, opt) == pytest.approx(100 * 33 / 225)
