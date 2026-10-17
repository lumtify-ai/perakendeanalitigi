"""rapor.py ve rapor_b.py'nin iç fonksiyonları: Türkçe biçim, basılan değerlerden fark/oran/ara
değer, tampon + korunum (bozulursa stdout boş), bölüm başlıkları ve sırası, önbellek kaydı denetimi,
teşhis tablosu ve ayrışımı. Gerçek veri yok; uçtan uca koşu el ile (`rapor.py > cikti/rapor.txt`,
iki koşu bayt bayt aynı)."""

import json

import numpy as np
import pandas as pd
import pytest

import rapor
import rapor_b

# --------------------------------------------------------------------------- biçim


def test_turkce_bicim():
    assert rapor.s(1234567.891, 2) == "1.234.567,89"
    assert rapor.s(1234567) == "1.234.567"
    assert rapor.s(0.555, 2) == "0,56"
    assert rapor.s(-3.2, 1) == "−3,2"
    assert rapor.s(float("nan")) == "—" and rapor.s(None) == "—"
    assert rapor.y(0.1234) == "%12,3" and rapor.y(-0.032) == "−%3,2" and rapor.y(None) == "—"
    assert rapor.yd(65.1021) == "%65,1" and rapor.yd(65.1021, 2) == "%65,10" and rapor.yd(-4.56) == "−%4,6"
    assert rapor.isaretli(1.234, 2) == "+1,23" and rapor.isaretli(-0.32, 2) == "−0,32"
    assert rapor.isaretli(0.001, 2) == "0,00" and rapor.isaretli(19866) == "+19.866"
    assert rapor.tl(7673800) == "7.673.800 TL"


def test_eksi_sifir_basilmaz():
    assert rapor.s(-0.004, 2) == "0,00" and rapor.s(-0.4) == "0" and rapor.yd(-0.04) == "%0,0"


def test_farklar_basilan_degerlerden():
    assert rapor.fark(100.4, 200.6) == 101
    assert rapor.fark(65.1021, 73.8705, 2) == pytest.approx(8.77)      # 73,87 − 65,10
    for x in (1.005, 2.675, 38904608.50914, 13.47):
        for n in (0, 1, 2):
            assert rapor.s(rapor.yuv(x, n), n) == rapor.s(x, n)
    assert rapor.bolum(13.47, 19.24, 1, 1) == pytest.approx(13.5 / 19.2)
    assert rapor.bolum(1, 0) is None


def test_ara_deger_basilan_degerlerden():
    # sınırda iki nokta (stok, bulunabilirlik): (420.497, 70,44) ve (443.229, 70,75); x = 428.097
    y = rapor.ara_deger(428097, 420497, 70.4412, 443229, 70.7531, ondalik_y=2)
    assert y == pytest.approx(70.44 + (70.75 - 70.44) * (428097 - 420497) / (443229 - 420497))
    with pytest.raises(ValueError):
        rapor.ara_deger(500000, 420497, 70.44, 443229, 70.75)        # aralık dışı: dış değer yok


def test_kisitin_baglamadigi_tavan():
    noktalar = [(0.4, 59.91), (0.6, 62.01), (1.0, 65.10), (1.6, 66.39), (float("inf"), 67.11)]
    assert rapor.kisitin_baglamadigi_tavan(noktalar, 66.73) == 1.6
    assert rapor.kisitin_baglamadigi_tavan(noktalar, 70.0) is None
    assert rapor.kisitin_baglamadigi_tavan(sorted(noktalar, reverse=True), 60.5) == 0.4


def test_yol_farklari():
    f = rapor.yol_farklari([65.10, 64.07, 64.74], [65.00, 63.23, 64.41], 2)
    assert f["farklar"] == pytest.approx([0.10, 0.84, 0.33])
    assert f["medyan"] == pytest.approx(0.33) and f["pozitif"] == 3 and f["negatif"] == 0 and f["n"] == 3


# ------------------------------------------------------------- tampon ve korunum


def test_tamponla_korunum_bozulursa_stdouta_yazmaz(capsys):
    def bozuk():
        print("=== VERİ ===")
        rapor.korunum([("sayı tutmuyor", False)])

    assert rapor.tamponla(bozuk) == (1, "")
    yakalanan = capsys.readouterr()
    assert yakalanan.out == "" and "sayı tutmuyor" in yakalanan.err
    assert rapor.tamponla(lambda: print("=== VERİ ===")) == (0, "=== VERİ ===\n")


def test_korunum_sayar_ve_adlari_soyler():
    assert rapor.korunum([("a", True), ("b", True)]) == 2
    with pytest.raises(AssertionError, match="korunum bozuldu") as e:
        rapor.korunum([("tutan", True), ("Σ grup = toplam", False)])
    assert "Σ grup = toplam" in str(e.value) and "tutan" not in str(e.value)
    with pytest.raises(AssertionError, match="hiç denetim"):
        rapor.korunum([])


def test_hedef_denetimleri():
    s = rapor_b.HedefSonucu(ad="k", gs={}, pazartesi=[pd.Timestamp("2025-09-01"), pd.Timestamp("2025-09-08")],
                            kayit_hedef=np.array([100.0, 200.0]), yeni_hedef=np.array([100.0, 200.0 + 1e-8]),
                            **{a: np.zeros(2) for a in ("satistaki", "ongoru", "ongoru_ham", "gs_top", "hedef",
                                                         "hedef_ham", "toplam", "baglayan", "baglayan_sifir", "talep")})
    assert all(ok for _, ok in rapor.hedef_denetimleri(s))
    s.yeni_hedef = np.array([100.0, 200.01])                          # 5e-5 > tolerans (birebir olmalı)
    assert not all(ok for _, ok in rapor.hedef_denetimleri(s))


# ------------------------------------------------------------- bölümler


def test_bolum_sirasi_spec_ile_ayni():
    assert [ad for ad, _ in rapor.BOLUMLER] == [
        "VERİ", "DEPO", "KALİBRASYON", "YOL 0", "LUMODA VE KURAL", "YOLLAR", "LINE KIRILIMI", "KOLİ VE TAVAN",
        "ÖNCELİK", "KURAL HEDEFİ", "SANSÜR", "BASİT", "HİKÂYE", "DEMO", "ANLATI VARSAYIMLARI", "KORUNUM"]


def test_govde_basliklari_sirayla_basar_korunum_en_sonda(monkeypatch):
    sira = []
    sahte = [(ad, (lambda ad: lambda v, ek: (sira.append(ad), ek.append((ad, True))))(ad)) for ad, _ in rapor.BOLUMLER]
    monkeypatch.setattr(rapor, "BOLUMLER", sahte)
    kod, metin = rapor.tamponla(lambda: rapor.govde(object()))
    assert kod == 0
    basliklar = [s[4:-4] for s in metin.splitlines() if s.startswith("=== ")]
    assert basliklar == [ad for ad, _ in sahte]
    assert sira == basliklar


def test_govde_korunum_bozulursa_bos(monkeypatch, capsys):
    sahte = [(ad, lambda v, ek: ek.append(("bozuk", False))) for ad, _ in rapor.BOLUMLER]
    monkeypatch.setattr(rapor, "BOLUMLER", sahte)
    assert rapor.tamponla(lambda: rapor.govde(object())) == (1, "")
    assert "bozuk" in capsys.readouterr().err


def test_main_girdi_yoksa_stdout_bos(monkeypatch, capsys):
    def yok():
        raise RuntimeError("kural_ref: koşu önbellekte yok")

    monkeypatch.setattr(rapor_b, "hazirla", yok)
    assert rapor.main([]) == 1
    y = capsys.readouterr()
    assert y.out == "" and "önbellekte yok" in y.err


def test_anlati_varsayimlari_basilir(capsys):
    rapor.anlati_bolumu(None, [])
    cikti = capsys.readouterr().out
    for ad in ("açık payı", "Collection", "%20", "%40", "10 TL", "20 TL", "0,25"):
        assert ad in cikti
    for anahtar, deger in rapor.ANLATI_VARSAYIMLARI.items():
        assert anahtar in cikti and str(deger) in cikti


# ------------------------------------------------------------- önbellek kaydı (rapor_b)


def _meta(**ek):
    m = {"ad": "k", "parametreler": {}, "ilk_alim_orani": 1.0, "kaydedici": True, "turler": {},
         "talep_tohumu": None, "operasyon_tohumu": 2026, "olcek": "tam", "gun_sayisi": None,
         "kod": "kod1", "veri": ["perakende.duckdb", 1, 2], "surumler": {"numpy": "2"}}
    m.update(ek)
    m["anahtar"] = rapor_b.motor._ozet({a: m[a] for a in rapor_b.ANAHTAR_ALANLARI if a in m})
    return m


def test_kayit_sorunlari():
    m = _meta()
    guncel = {"kod": "kod1", "veri": ["perakende.duckdb", 1, 2], "surumler": {"numpy": "2"}}
    assert rapor_b.kayit_sorunlari(m, m["anahtar"], guncel) == []
    assert rapor_b.kayit_sorunlari(m, "baska", guncel) == ["anahtar oyun.json'daki ölçülmüş kayıttan farklı"]
    assert rapor_b.kayit_sorunlari(m, m["anahtar"], {**guncel, "kod": "kod2"}) == ["kod bugünkünden farklı"]
    bozuk = {**m, "parametreler": {"x": 1}}
    assert "meta alanlarının özeti anahtarı vermiyor" in rapor_b.kayit_sorunlari(bozuk, m["anahtar"], guncel)


def test_onbellek_eksik_kosuyu_kosmaz_silmez(tmp_path):
    m = _meta()
    guncel = {a: m[a] for a in ("kod", "veri", "surumler")}
    ob = rapor_b.Onbellek({"k": {"anahtar": m["anahtar"]}}, dizin=tmp_path, guncel=guncel)
    with pytest.raises(RuntimeError, match="oyun.json'da yok"):
        ob.ac("yok")
    with pytest.raises(RuntimeError, match="önbellekte yok"):
        ob.ac("k")
    d = tmp_path / f"k_{m['anahtar'][:20]}"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({**m, "tablolar": ["satis"], "kayitlar": []}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="dosya eksik"):
        ob.ac("k")
    assert d.exists()                                                  # motor.kos gibi silmez
    (d / "tablo_satis.parquet").write_bytes(b"")
    (d / "gercek.parquet").write_bytes(b"")
    k = ob.ac("k")
    assert k.meta["anahtar"] == m["anahtar"] and ob.acilan == {"k"}


# ------------------------------------------------------------- teşhis (rapor_b)


def _gruplar():
    urun = pd.DataFrame({
        "urun_id": ["C1-M", "C1-XS", "C2-M", "N1-M", "A1-STD"],
        "option_id": ["C1", "C1", "C2", "N1", "A1"],
        "line": ["Collection", "Collection", "Collection", "NOS", "Collection"],
        "sezon_kodu": ["AW25", "AW25", "AW25", "NOS", "SS25"],
        "dalga": [2, 2, 1, 0, 3],
        "lansman_tarihi": pd.to_datetime(["2025-09-22", "2025-09-22", "2025-08-18", "2020-01-01", "2025-04-01"]),
        "beden_seti": ["Kadın Harf"] * 4 + ["Standart"],
        "beden_sira": [3, 1, 3, 3, 1],
    })
    return rapor_b.urun_gruplari(urun)


def test_urun_gruplari_ve_lansman_grubu():
    g = _gruplar()
    assert g.loc["C1-M", "beden"] == "çekirdek" and g.loc["C1-XS", "beden"] == "kenar"
    assert g.loc["A1-STD", "beden"] == "tek beden"
    et, pen = rapor_b.lansman_grubu(g["line"], g["sezon_kodu"], g["lansman_tarihi"],
                                    np.full(len(g), np.datetime64("2025-10-27")))
    d = dict(zip(g.index, et))
    assert d["C1-M"] == "pencerede lanse, lansmandan 28+ gün" and d["C2-M"] == "AW25 dalga 1"
    assert d["A1-STD"] == "önceki sezonlar" and d["N1-M"] == "NOS"
    assert list(pen) == [True, True, False, False, False]
    et, _ = rapor_b.lansman_grubu(g["line"], g["sezon_kodu"], g["lansman_tarihi"],
                                  np.full(len(g), np.datetime64("2025-10-01")))
    assert et[0] == "pencerede lanse, lansmandan 0–13 gün"


def test_teshis_tablosu_toplamlari_ve_alanlari():
    gercek = pd.DataFrame({
        "tarih": pd.to_datetime(["2025-09-25", "2025-10-20", "2025-11-30", "2025-09-02", "2025-12-01", "2025-09-03"]),
        "urun_id": ["C1-M", "C1-XS", "C1-M", "C2-M", "N1-M", "A1-STD"],
        "talep": [3, 2, 1, 4, 5, 0], "kendi_satis": [3, 0, 1, 2, 5, 0], "karsilanmayan": [0, 2, 0, 2, 0, 0]})
    t = rapor_b.teshis_tablosu(gercek, _gruplar())
    assert set(t["kesit"]) == {"lansman", "line_yari", "line_beden", "hafta"}
    for kesit, parca in t.groupby("kesit"):
        assert parca["talep"].sum() == 15 and parca["talepli"].sum() == 5 and parca["bulunan"].sum() == 4
        assert parca["karsilanmayan"].sum() == 4
    lan = t[t["kesit"] == "lansman"].set_index("grup")
    assert lan.loc["pencerede lanse, lansmandan 0–13 gün", "talep"] == 3          # lansmandan 3. gün
    assert lan.loc["pencerede lanse, lansmandan 28+ gün", "talepli"] == 2
    assert bool(lan.loc["pencerede lanse, lansmandan 28+ gün", "pencerede"]) and not bool(lan.loc["NOS", "pencerede"])
    assert lan.loc["NOS", "line"] == "NOS" and lan.loc["AW25 dalga 1", "line"] == "Collection"
    yari = t[t["kesit"] == "line_yari"]
    nos2 = yari[(yari["line"] == "NOS") & (yari["yari"] == "ikinci")]
    assert len(nos2) == 1 and nos2["talep"].iloc[0] == 5
    assert yari[(yari["line"] == "Collection") & (yari["yari"] == "ilk")]["talep"].sum() == 9
    h = t[t["kesit"] == "hafta"].set_index("hafta")
    assert h.loc[0, "talep"] == 4 and h.loc[0, "grup"] == "hafta 01" and h.loc[12, "talep"] == 1 and h.loc[13, "talep"] == 5   # 30 Kas (gün 90), 1 Ara (gün 91)


def test_katki_grup_alanlarini_tasir():
    gercek = pd.DataFrame({"tarih": pd.to_datetime(["2025-09-02", "2025-12-01"]), "urun_id": ["C2-M", "N1-M"],
                           "talep": [4, 5], "kendi_satis": [2, 5], "karsilanmayan": [2, 0]})
    t = rapor_b.teshis_tablosu(gercek, _gruplar())
    kk = rapor_b.grup_katkisi(t[t["kesit"] == "line_yari"], t[t["kesit"] == "line_yari"])
    assert set(kk.columns) >= {"line", "yari", "katki"} and (kk["katki"] == 0).all()


def test_grup_katkisi_toplami_farka_esit():
    a = pd.DataFrame({"grup": ["x", "y"], "talepli": [60, 40], "bulunan": [54, 20]})
    b = pd.DataFrame({"grup": ["x", "y"], "talepli": [61, 39], "bulunan": [48, 19]})
    k = rapor_b.grup_katkisi(a, b)
    fark = 100 * (74 / 100 - 67 / 100)
    assert k["katki"].sum() == pytest.approx(fark)
    assert k.set_index("grup").loc["x", "bul_a"] == pytest.approx(90.0)
