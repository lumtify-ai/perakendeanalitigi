"""`allocation.olcutler`: elle kurulmuş küçük bir koşunun ölçütleri (oyuncak dünya, `conftest`), erken
birincil talebin penceresi ve (veri) kahinin bağımsızlık varsayımı.

Oyuncak koşu (`_kosu`): oyun option'ları A (2, SS25 Collection d1, 5 beden, lansman 02-10), B (3, d2,
lansman 03-17, ilk dağıtım varışı yok), X (5, aksesuar). A'nın ilk dağıtımı M1'e 2 paket (02-10
varış), M2'ye 1 paket (02-11). Günlük tablo (`_gunluk`, ortak `stok.gunluk_magaza`'nın biçimi) elle
verilir: yeniden kurulumu ortak paketin işidir ve orada sınanır.
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from allocation import kaynak, olcutler

T = pd.Timestamp


def _df(satirlar, sutunlar, tarihler=("tarih",)):
    df = pd.DataFrame(satirlar, columns=sutunlar)
    for s in tarihler:
        if s in df:
            df[s] = pd.to_datetime(df[s])
    return df


class _Kosu:
    """`Kosu` / `KosuKaydi`'nın `tablo(ad, sutunlar, urunler)` arayüzü, bellekteki tablolarla."""

    def __init__(self, tablolar, kayitlar=None):
        self.tablolar = tablolar
        self.kayitlar = kayitlar or {}
        self.meta = {"gun_sayisi": None, "olcek": "kucuk"}

    def tablo(self, ad, sutunlar=None, urunler=None):
        df = self.tablolar[ad]
        if urunler is not None and "urun_id" in df:
            df = df[df["urun_id"].astype(str).isin(set(map(str, urunler)))]
        if sutunlar is not None:
            df = df[list(sutunlar)]
        return df.reset_index(drop=True)


@pytest.fixture
def w(dunya):
    dunya.urunler["alis_fiyati"] = 100.0
    return dunya


A = [f"OPT-A-{b}" for b in range(1, 6)]
PAKET = [1, 2, 2, 1, 1]


def _sevkiyat():
    s = [("2025-02-08", "2025-02-10", "DEPO", "M1", u, 2 * n, "ilk_dagitim", "PKT01") for u, n in zip(A, PAKET)]
    s += [("2025-02-08", "2025-02-11", "DEPO", "M2", u, n, "ilk_dagitim", "PKT01") for u, n in zip(A, PAKET)]
    s += [("2025-03-03", "2025-03-04", "DEPO", "M1", "OPT-A-3", 5, "replenishment", None),
          ("2025-04-01", "2025-04-02", "M1", "M2", "OPT-A-2", 1, "elle_transfer", None),
          ("2025-05-05", "2025-05-06", "M1", "DEPO", "OPT-A-1", 2, "stok_devri", None),     # sezon içi: kalan değil
          ("2025-08-25", "2025-08-26", "M1", "MO", "OPT-A-1", 10, "outlet_akisi", None),
          ("2025-08-25", "2025-08-26", "DEPO", "MO", "OPT-A-2", 20, "outlet_akisi", None),
          ("2025-08-27", "2025-08-28", "M1", "DEPO", "OPT-A-1", 3, "stok_devri", None),
          ("2025-11-17", "2025-11-18", "MO", "DEPO", "OPT-A-1", 15, "stok_devri", None),   # outlet penceresi sonu
          ("2023-08-28", "2023-08-29", "M1", "MO", "OPT-GA-1", 9, "outlet_akisi", None)]    # başka sezon
    return _df(s, ["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet", "tip", "paket_id"],
               ("tarih", "varis_tarihi"))


def _gercek():
    g = [("2025-02-10", "M1", "OPT-A-1", 2, 2, 0, 0, 0),     # stoklu
         ("2025-02-11", "M1", "OPT-A-1", 1, 0, 1, 1, 0),     # stoksuz (beden boş, öteki bedenler stoklu)
         ("2025-02-12", "M2", "OPT-A-2", 1, 1, 0, 0, 0),
         ("2025-03-20", "M1", "OPT-A-3", 4, 1, 3, 2, 1),     # ilk 4 haftadan sonra
         ("2025-03-20", "M3", "OPT-B-1", 2, 0, 2, 0, 2),     # B: varışı yok, lansmandan sayılır
         ("2025-02-10", "ONL", "OPT-A-1", 5, 0, 5, 0, 5),    # online: dışarıda
         ("2025-02-09", "M1", "OPT-A-1", 1, 0, 1, 0, 1),     # ilk varıştan önce: dışarıda
         ("2025-08-25", "M1", "OPT-A-1", 1, 0, 1, 0, 1),     # çıkış günü: dışarıda
         ("2025-02-10", "M1", "OPT-GA-1", 1, 0, 1, 0, 1)]    # başka sezon
    return _df(g, olcutler.GERCEK)


def _satis():
    s = [("2025-02-10", "M1", "OPT-A-1", 2, 600.0, 0.0, None),       # tam fiyat
         ("2025-02-12", "M2", "OPT-A-2", 6, 1260.0, 540.0, None),     # işlem indirimi: tam fiyat sayılır, markdown değil
         ("2025-03-20", "M1", "OPT-A-3", 1, 240.0, 60.0, "K1"),       # kampanya
         ("2025-07-01", "M2", "OPT-A-2", 2, 420.0, 180.0, None),      # markdown haftası
         ("2025-07-02", "ONL", "OPT-A-1", 1, 210.0, 90.0, None),      # online markdown
         ("2025-07-08", "M2", "OPT-A-2", -1, -210.0, -90.0, None),    # iade
         ("2025-02-12", "ONL", "OPT-A-1", 4, 1200.0, 0.0, None),
         ("2025-08-26", "MO", "OPT-A-1", 3, 630.0, 270.0, None)]      # çıkıştan sonra: dışarıda
    return _df(s, olcutler.SATIS)


def _fiyat():
    f = [(h, "OPT-A", hat, o) for hat in ("normal", "online")
         for h, o in (("2025-06-23", 0.0), ("2025-06-30", 0.3), ("2025-07-07", 0.3))]
    return _df(f, ["hafta_baslangic", "option_id", "hat", "indirim_orani"], ("hafta_baslangic",))


def _depo():
    sabah = [("2025-02-09", u, a) for u, a in zip(A, [1, 2, 10, 12, 3])]     # son ilk sevkin ertesi sabahı
    son = [("2025-12-31", "OPT-A-1", 3 + 15 + 4), ("2025-12-31", "OPT-A-2", 0)]  # 4: çıkıştan sonra eklenen
    return _df(sabah + son, ["tarih", "urun_id", "adet"])


def _ilk_kaydi(m1=2):
    """Kolun kaydı (`politika.IlkDagitimKolu.kayit_tablosu` biçimi): A'nın kararı gün 5 (02-08)."""
    return pd.DataFrame({"gun": 5, "arg0": 2, "indis": [0, 1, 2, 3], "deger": [m1, 1, 0, 0], "kol": True,
                         "U": 3, "toplam": 3, "t": 0.0, "duzey": -1, "tavanda": 0, "geri_dusus": False})


def _gunluk_tablo():
    """(mağaza, gün, beden rafları, durumlar): M1 02-10'da beden 1 gün içinde biter; 02-12'de çekirdek
    beden 2 boş (kırık). M2 02-12'de beden 2 ve 3 biter, 02-13 kırık, 02-14 boş çift (stoklu değil)."""
    s, b, t = "stoklu", "bos", "tukenen"
    gunler = [("M1", "2025-02-10", [2, 4, 4, 2, 2], [t, s, s, s, s]),
              ("M1", "2025-02-11", [0, 4, 4, 2, 2], [b, s, s, s, s]),
              ("M1", "2025-02-12", [0, 0, 4, 2, 2], [b, b, s, s, s]),
              ("M2", "2025-02-11", [1, 2, 2, 1, 1], [s] * 5),
              ("M2", "2025-02-12", [1, 2, 2, 1, 1], [s, t, t, s, s]),
              ("M2", "2025-02-13", [1, 0, 0, 1, 1], [s, b, b, s, s]),
              ("M2", "2025-02-14", [0, 0, 0, 0, 0], [b] * 5)]
    satir = [(gun, m, u, raf, d) for m, gun, raflar, durumlar in gunler
             for u, raf, d in zip(A, raflar, durumlar)]
    df = _df(satir, ["tarih", "magaza_id", "urun_id", "satis_oncesi", "durum"])
    df["durum"] = pd.Categorical(df["durum"], categories=["stoklu", "tukenen", "bos"])
    return df


def _kosu(w, kayit=None):
    return _Kosu({
        "sevkiyat": _sevkiyat(), "gercek": _gercek(), "satis": _satis(), "fiyat": _fiyat(), "depo_stok": _depo(),
        "siparis": _df([("SP1", "ilk", "OPT-A", "OPT-A-1", "2025-01-20", 100),
                        ("SP1", "ilk", "OPT-A", "OPT-A-2", "2025-01-20", 100),
                        ("SP2", "rpt", "OPT-A", "OPT-A-3", "2025-04-01", 50),
                        ("SP3", "rpt", "OPT-A", "OPT-A-3", None, 40),
                        ("SP4", "ilk", "OPT-GA", "OPT-GA-1", "2023-01-20", 999)],
                       olcutler.SIPARIS, ("gerceklesen_teslim",)),
        "kalite_kontrol": pd.DataFrame({"siparis_id": ["SP1", "SP2", "SP4"], "hatali": [20, 5, 7]}),
        "paket": w.paketler,
    }, {"ilk_dagitim": _ilk_kaydi() if kayit is None else kayit})


def test_olcutler_oyuncak(w, monkeypatch):
    """Elle kurulmuş koşu: müşteri, para, mal akışı, isabet ve beden ölçütleri elle hesaplanan değerlerle."""
    h = kaynak.harita_kur(w)
    monkeypatch.setattr(olcutler, "_gunluk", lambda kosu, k, bas, bit: _gunluk_tablo())
    o = olcutler.hesapla(_kosu(w), w, h, "SS25")

    # müşteri: talepli 5 hücre-gün (A 4, B 1), 3'ü stoklu; ilk 4 hafta A'da 3'ün 2'si, B'de 1'in 0'ı
    assert o["bulunabilirlik"] == pytest.approx(100 * 3 / 5)
    assert o["bulunabilirlik_ilk4"] == pytest.approx(100 * 2 / 4)
    assert (o["talep_adet"], o["satis_adet"]) == (10.0, 4.0)
    assert o["kayip_orani"] == pytest.approx(60.0)
    assert o["ikame_payi"] == pytest.approx(50.0) and o["kalici_kayip_orani"] == pytest.approx(30.0)

    # mal akışı: teslim alınan 250 − hatalı 25; kalan = mağaza (10 akış + 3 devir) + depo (20 akış + 4 ek);
    # sezon içindeki 2'lik devir ne kalana girer ne depo ekinden düşülür
    assert (o["toplam_mal"], o["rpt_adet"]) == (225.0, 50.0)
    assert (o["kalan_magaza_adet"], o["kalan_depo_adet"], o["kalan_depo_ek_adet"]) == (13.0, 24.0, 4.0)
    assert o["sezon_sonu_kalan_yuzde"] == pytest.approx(100 * 37 / 225)
    assert (o["ilk_dagitim_adet"], o["replenishment_adet"], o["elle_transfer_adet"]) == (21.0, 5.0, 1.0)
    # depoda kalan beden: depo ÷ (depo + ilk dağıtım) = 1/4, 2/8, 10/16, 12/15, 3/6
    for b, v in zip(range(1, 6), [25.0, 25.0, 62.5, 80.0, 50.0]):
        assert o[f"depoda_kalan_beden_{b}"] == pytest.approx(v), b
    # ilk alıma göre: (teslim edilmiş ilk sipariş − ilk dağıtım) ÷ ilk sipariş; A-1 100 − 3, A-2 100 − 6
    assert [o[f"alimdan_kalan_beden_{b}"] for b in range(1, 6)] == pytest.approx([97.0, 94.0, 0.0, 0.0, 0.0])

    # para: tam fiyat 2 + 6 + 4 (online) ÷ 250 sipariş; markdown 180 + 90; kâr = tutar − 100 × adet
    assert o["tam_fiyat_str"] == pytest.approx(100 * 12 / 250)
    assert (o["markdown_tl"], o["markdown_tl_fiziksel"], o["markdown_tl_online"]) == (270.0, 180.0, 90.0)
    assert (o["brut_kar_tl"], o["brut_kar_tl_fiziksel"], o["brut_kar_tl_online"]) == (2220.0, 1310.0, 910.0)
    assert o["online_satis"] == 5.0

    # isabet: A gerçek M1 7, M2 1 / pay 14, 7 → 0,2083; B talep M3'te, payı yok (eşit) → 0,75; ağırlık ilk alım
    assert o["pay_wape"] == pytest.approx((2100 * 5 / 24 + 1400 * 0.75) / 3500)
    assert (o["ilk_hucre"], o["oturan_hucre"], o["hizli_biten_hucre"]) == (2.0, 1.0, 1.0)
    assert (o["kirpilan_adet"], o["tavan_baglayan"], o["tavan_kalan_adet"]) == (0.0, 0.0, 0.0)

    # beden: stoklu çift-gün 6 (M2 02-14 boş), kırık 2; karşılanmayan 6'nın 1'i bedeni boşken
    assert o["stoklu_cift_gun"] == 6.0
    assert o["kirik_cift_pay_yuzde"] == pytest.approx(100 * 2 / 6)
    assert o["beden_kayip_payi"] == pytest.approx(100 / 6)
    # ilk tükenen: M1 beden 1; M2 beden 2 ve 3 aynı gün (yarım)
    assert [o[f"ilk_tukenen_beden_{b}"] for b in range(1, 6)] == pytest.approx([50.0, 25.0, 25.0, 0.0, 0.0])
    assert o["tukenen_hucre_yuzde"] == 100.0
    assert all(isinstance(v, float) for v in o.values())


def test_olcutler_korunum(w, monkeypatch):
    """Kolun kaydı motorun gönderdiğinden farklıysa (motor kırptı) ya da tavan bağlamadan ⌊U(1−t)⌋'dan az
    dağıtıldıysa ölçüm durur; Lumoda kaydında (kol sütunu yok) kırpma yalnız sayılır."""
    h = kaynak.harita_kur(w)
    monkeypatch.setattr(olcutler, "_gunluk", lambda kosu, k, bas, bit: _gunluk_tablo())
    with pytest.raises(RuntimeError, match="kırptı"):
        olcutler.hesapla(_kosu(w, _ilk_kaydi(m1=3)), w, h, "SS25")
    eksik = _ilk_kaydi().assign(toplam=4, U=4)
    with pytest.raises(RuntimeError, match="az"):
        olcutler.hesapla(_kosu(w, eksik), w, h, "SS25")
    iki_karar = pd.concat([_ilk_kaydi(), _ilk_kaydi().assign(gun=6, deger=0)], ignore_index=True)
    with pytest.raises(RuntimeError, match="birden çok"):
        olcutler.hesapla(_kosu(w, iki_karar), w, h, "SS25")
    lumoda = _ilk_kaydi(m1=3)[["gun", "arg0", "indis", "deger"]]
    lumoda = lumoda[lumoda["deger"] > 0]
    o = olcutler.hesapla(_kosu(w, lumoda), w, h, "SS25")
    assert o["kirpilan_adet"] == 7.0                   # M1'de 1 paket (7 adet) kırpıldı
    bozuk = _kosu(w)
    bozuk.tablolar["gercek"].loc[0, "kendi_satis"] = 3
    with pytest.raises(RuntimeError, match="kendi satış"):
        olcutler.hesapla(bozuk, w, h, "SS25")


def test_erken_birincil_talep_penceresi(w):
    """Lansmandan 42 gün, erken kesimde (indirim başlangıcı − 29, dahil) kesik; fiziksel mağazalar;
    (option, mağaza) toplamı. Indirim başlangıcı öne alınınca kesim X'in penceresini kısaltır."""
    h = kaynak.harita_kur(w)
    g = _df([("2025-02-10", "M1", "OPT-A-1", 2, 2, 0, 0, 0), ("2025-03-23", "M1", "OPT-A-2", 3, 0, 3, 0, 3),
             ("2025-03-24", "M1", "OPT-A-2", 9, 0, 9, 0, 9),     # lansman + 42: dışarıda
             ("2025-02-11", "M2", "OPT-A-1", 1, 1, 0, 0, 0), ("2025-02-11", "ONL", "OPT-A-1", 5, 5, 0, 0, 0),
             ("2025-02-11", "MO", "OPT-A-1", 5, 5, 0, 0, 0),     # outlet mağazası: dışarıda
             ("2025-05-22", "M1", "OPT-X-1", 4, 4, 0, 0, 0), ("2025-05-23", "M1", "OPT-X-1", 6, 6, 0, 0, 0)],
            olcutler.GERCEK)
    kosu = _Kosu({"gercek": g})
    e = olcutler.erken_birincil_talep(kosu, w, h, "SS25")
    assert e.to_dict("records") == [{"option_id": "OPT-A", "magaza_id": "M1", "talep": 5},
                                    {"option_id": "OPT-A", "magaza_id": "M2", "talep": 1},
                                    {"option_id": "OPT-X", "magaza_id": "M1", "talep": 10}]
    w.sezon.loc[w.sezon["sezon_kodu"] == "SS25", "indirim_baslangic"] = T("2025-06-20")   # kesim 05-22
    e = olcutler.erken_birincil_talep(kosu, w, h, "SS25")
    assert e.loc[e["option_id"] == "OPT-X", "talep"].tolist() == [4]
    gunler = olcutler.erken_hucre_gunleri(kosu, w, h, "SS25")
    assert list(gunler.columns) == ["tarih", "magaza_id", "urun_id", "talep"] and len(gunler) == 4


def test_bulunabilirlik_varissiz_option_lansmandan(w):
    """İlk dağıtım varışı olmayan kapsam option'ı düşmez: penceresi lansmandan başlar (Görev 7 notu)."""
    h = kaynak.harita_kur(w)
    opt = kaynak.oyun_optionlari(w, "SS25")
    g = _gercek()
    assert olcutler.bulunabilirlik(g, _sevkiyat(), w, h, opt) == pytest.approx(60.0)
    yalniz_b = olcutler.bulunabilirlik(g[g["urun_id"] == "OPT-B-1"], _sevkiyat(), w, h, opt)
    assert yalniz_b == 0.0
    assert olcutler.bulunabilirlik(g, _sevkiyat(), w, h, opt, ufuk=28) == pytest.approx(50.0)
    b = olcutler.baslangiclar(_sevkiyat(), olcutler.Kapsam(w, h, opt))
    assert b[2] == np.datetime64("2025-02-10") and b[3] == np.datetime64("2025-03-17")


@pytest.mark.veri
def test_erken_birincil_talep_kollar_arasi_ayni():
    """Kahinin varsayımı (spec §0/11, §9): erken penceredeki birincil talep politikadan bağımsızdır.
    TAM, yol 0: `lumoda` ve `pay_esit` koşularının erken penceresindeki fiziksel hücre-günleri ve
    talepleri birebir aynı. Tutmazsa kahin "ölçülemedi" (spec §10). `pay_esit` önbellekte değilse
    koşulur (~3 dk, tepe ~8 GB)."""
    from allocation import kalibrasyon, oyun

    if not kaynak.VERITABANI.exists():
        pytest.skip("yayımlanan v4 yok")
    ortam = oyun.Ortam(ilerleme=False)
    kal = kalibrasyon.oku()
    G = oyun.Girdi(0, ortam, kal)
    esit, _ = oyun.kos_bir(oyun.tum_kosumlar()["pay_esit"], G, kal, None)
    a = olcutler.erken_hucre_gunleri(G.lumoda, G.w, G.harita)
    b = olcutler.erken_hucre_gunleri(esit, G.w, G.harita)
    print(f"\nerken pencere: {len(a):,} hücre-gün, Σ talep {int(a['talep'].sum()):,}")
    assert len(a) > 100_000
    pd.testing.assert_frame_equal(a, b)
    assert esit.meta["turler"] == {"ilk_dagitim": "allocation.politika.EsitKol"}
