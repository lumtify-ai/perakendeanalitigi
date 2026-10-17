"""`replenishment.hikaye_sec`: 1. yazının sahnesi (spec §6, Ruling R31).

Oyuncak veri: dört fiziksel mağaza (A1, A2 İstanbul = Ali; V1, V2 Anadolu = Veli),
oyunun 2. pazartesisi (2025-09-08, indeks 1). Temel sahne `X-S` (option X, Kadın Harf):
dört mağaza ister (14 adet), depo yalnız V1'e 2 adet verir (orantılı kesim); sonraki
dört haftada V1 stokluyken A1–A2'den yavaş satar; `kural` X'te Lumoda'dan iyi.
Her test temel sahneden tek bir şeyi bozar.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from replenishment import hikaye_sec as hs

P0 = pd.Timestamp("2025-09-08")          # oyunun 2. pazartesisi
P1 = pd.Timestamp("2025-09-15")

MAG = pd.DataFrame({
    "magaza_id": ["A1", "A2", "V1", "V2"],
    "ad": ["İstanbul 1", "İstanbul 2", "Ankara 1", "Konya 1"],
    "sehir": ["İstanbul", "İstanbul", "Ankara", "Konya"],
    "bolge": ["Marmara", "Marmara", "İç Anadolu", "İç Anadolu"],
    "istanbul": [True, True, False, False],
})


def _istek(p, sku, option, beden_seti, istekler: dict) -> pd.DataFrame:
    return pd.DataFrame({"tarih": p, "magaza_id": list(istekler), "urun_id": sku, "option_id": option,
                         "beden_seti": beden_seti, "istek": list(istekler.values())})


def _sevk(p, sku, gidenler: dict) -> pd.DataFrame:
    return pd.DataFrame({"tarih": p, "magaza_id": list(gidenler), "urun_id": sku, "adet": list(gidenler.values())})


def _gunluk(sku, magaza, bas, stoklu_gun, satis_gun, n=28, bos_satis=0):
    """`n` gün: ilk `stoklu_gun` gün stoklu, her stoklu gün `satis_gun` satış; sonra boş."""
    t = pd.date_range(bas, periods=n, freq="D")
    st = np.arange(n) < stoklu_gun
    adet = np.where(st, satis_gun, bos_satis)
    return (pd.DataFrame({"tarih": t, "magaza_id": magaza, "urun_id": sku, "adet": adet}),
            pd.DataFrame({"tarih": t, "magaza_id": magaza, "urun_id": sku, "stoklu": st}))


def _veri(sku="X-S", option="X", beden_seti="Kadın Harf", p=P0, istekler=None, gidenler=None,
          hizlar=None, olcut=None):
    """Tek sahne: istekler, sevkiyat, günlük satış/stoklu, kural ölçütü."""
    istekler = istekler or {"A1": 5, "A2": 3, "V1": 4, "V2": 2}
    gidenler = gidenler if gidenler is not None else {"V1": 2}
    # mağaza → (sonraki 28 gün stoklu gün, stoklu gün satışı, önceki 28 gün stoklu gün, satış)
    hizlar = hizlar or {"A1": (10, 2, 20, 1), "A2": (4, 1, 20, 1), "V1": (10, 0.5, 20, 1), "V2": (5, 1, 20, 1)}
    sat, sto = [], []
    for m, (sg, sa, osg, osa) in hizlar.items():
        a, b = _gunluk(sku, m, p, sg, sa)
        c, d = _gunluk(sku, m, p - pd.Timedelta(28, unit="D"), osg, osa)
        sat += [a, c]
        sto += [b, d]
    satis = pd.concat(sat, ignore_index=True)
    satis["adet"] = satis["adet"].astype(float)
    olcut = olcut or (70.0, 60.0, 30.0, 40.0)
    return {
        "istekler": _istek(p, sku, option, beden_seti, istekler),
        "sevkiyat": _sevk(p, sku, gidenler),
        "satis": satis,
        "stoklu": pd.concat(sto, ignore_index=True),
        "kural_olcut": pd.DataFrame({"option_id": [option], "bulunabilirlik_kural": [olcut[0]],
                                     "bulunabilirlik_lumoda": [olcut[1]], "kayip_orani_kural": [olcut[2]],
                                     "kayip_orani_lumoda": [olcut[3]]}),
    }


def _birlestir(*veriler) -> dict:
    return {a: pd.concat([v[a] for v in veriler], ignore_index=True) for a in veriler[0]}


def _f(v) -> pd.DataFrame:
    t = hs.magaza_tablosu(v["istekler"], v["sevkiyat"], v["satis"], v["stoklu"], MAG)
    return hs.ozellikler(t, v["kural_olcut"])


def _bayrak(v) -> pd.Series:
    f = _f(v)
    return hs.bayraklar(f).iloc[0]


def _sec(v, zorla=None) -> hs.Hikaye:
    return hs.sec(v["istekler"], v["sevkiyat"], v["satis"], v["stoklu"], MAG, v["kural_olcut"], zorla=zorla)


# ---------------------------------------------------------------- ölçütler


def test_temel_sahne_butun_olcutleri_tutar():
    b = _bayrak(_veri())
    assert list(b.index) == list(hs.OLCUTLER)
    assert b.all()


def test_ozellikler_sayilar():
    f = _f(_veri()).iloc[0]
    assert (f["istek_toplam"], f["giden_toplam"]) == (14, 2)
    assert (f["n_ali_gitmeyen"], f["n_veli_giden"]) == (2, 1)
    assert f["pazartesi_indeksi"] == 1
    # Ali gitmeyen: A1 10 gün × 2 + A2 4 gün × 1 = 24 / 14 gün; Veli giden: V1 10 × 0,5 = 5 / 10
    assert (f["sg_ali"], f["sat_ali"], f["sg_veli"], f["sat_veli"]) == (14, 24, 10, 5)
    assert f["hiz_ali"] == pytest.approx(24 / 14) and f["hiz_veli"] == pytest.approx(0.5)
    assert f["once_hiz_ali"] == pytest.approx(1.0) and f["once_hiz_veli"] == pytest.approx(1.0)


def test_kesim_istek_depoyu_asmali():
    v = _veri(gidenler={"A1": 5, "A2": 3, "V1": 4, "V2": 2})
    assert not _bayrak(v)["kesim"]


def test_iki_bolge_ali_gitmeyen_veli_giden_ister():
    assert not _bayrak(_veri(gidenler={"A1": 1}))["iki_bolge"]                  # mal Ali'ye gitti
    assert not _bayrak(_veri(istekler={"V1": 4, "V2": 2}))["iki_bolge"]          # Ali istemedi
    assert not _bayrak(_veri(gidenler={}))["iki_bolge"]                          # hiç gitmedi


def test_yavas_giden_stoklu_gun_hizi():
    hiz = {"A1": (10, 2, 20, 1), "A2": (4, 1, 20, 1), "V1": (10, 3, 20, 1), "V2": (5, 1, 20, 1)}
    assert not _bayrak(_veri(hizlar=hiz))["yavas_giden"]                        # V1 daha hızlı
    hiz = {"A1": (0, 2, 20, 1), "A2": (0, 1, 20, 1), "V1": (10, 0.5, 20, 1), "V2": (5, 1, 20, 1)}
    assert not _bayrak(_veri(hizlar=hiz))["yavas_giden"]                        # Ali hiç stoklu değil: tanımsız


def test_yavas_giden_bos_gun_satisini_saymaz():
    """Stoksuz günde satış (varış günü) stoklu gün hızına girmez."""
    v = _veri()
    v["satis"].loc[(v["satis"]["magaza_id"] == "V1") & (v["satis"]["adet"] == 0), "adet"] = 9.0
    f = _f(v).iloc[0]
    assert f["sat_veli"] == 5 and f["sg_veli"] == 10


def test_kural_iyi_bulunabilirlik_ya_da_kayip():
    assert _bayrak(_veri(olcut=(50.0, 60.0, 30.0, 40.0)))["kural_iyi"]          # yalnız kayıp iyi
    assert _bayrak(_veri(olcut=(70.0, 60.0, 50.0, 40.0)))["kural_iyi"]          # yalnız bulunabilirlik iyi
    assert not _bayrak(_veri(olcut=(50.0, 60.0, 50.0, 40.0)))["kural_iyi"]
    v = _veri()
    v["kural_olcut"]["option_id"] = "BASKA"
    assert not _bayrak(v)["kural_iyi"]                                           # ölçüt yok


def test_bedenli():
    assert not _bayrak(_veri(sku="Y-STD", option="Y", beden_seti="Standart"))["bedenli"]


def test_huni():
    v = _birlestir(_veri(), _veri(sku="X-M", gidenler={"A1": 5, "A2": 3, "V1": 4, "V2": 2}))
    h = dict(hs.huni(hs.bayraklar(_f(v))))
    assert h == {"havuz": 2, "kesim": 1, "iki_bolge": 1, "yavas_giden": 1, "kural_iyi": 1, "bedenli": 1}


# ---------------------------------------------------------------- merdiven


def test_merdiven_birebir_ilk_sira_kanit():
    """İki birebir sahne: iki yanın küçük stoklu günü (kanıt) büyük olan önde."""
    zayif = {"A1": (10, 2, 20, 1), "A2": (4, 1, 20, 1), "V1": (3, 0.5, 20, 1), "V2": (5, 1, 20, 1)}
    v = _birlestir(_veri(), _veri(sku="Z-S", option="Z", hizlar=zayif))
    v["kural_olcut"] = pd.concat([_veri()["kural_olcut"], _veri(option="Z")["kural_olcut"]])
    h = _sec(v)
    assert (h.option_id, h.sku, h.gevseyen) == ("X", "X-S", [])
    assert h.alternatif == "Z:Z-S"


def test_merdiven_once_de_hizli_ali_one_gecer():
    """Ali'nin mağazaları kesimden önceki dört haftada da hızlıysa (bilinenle de Ali'ye
    gönderilirdi) sahne öne geçer, kanıtı daha zayıf olsa da."""
    once = {"A1": (10, 2, 20, 3), "A2": (4, 1, 20, 3), "V1": (3, 0.5, 20, 1), "V2": (5, 1, 20, 1)}
    v = _birlestir(_veri(), _veri(sku="Z-S", option="Z", hizlar=once))
    v["kural_olcut"] = pd.concat([_veri()["kural_olcut"], _veri(option="Z")["kural_olcut"]])
    assert _sec(v).sku == "Z-S"


def test_gevsetme_sirasi_bedenli_once():
    """Birebir sahne yok: biri yalnız `bedenli`yi, öteki yalnız `kural_iyi`yi tutmuyor →
    önce `bedenli` gevşer."""
    v = _birlestir(_veri(sku="Y-STD", option="Y", beden_seti="Standart"),
                   _veri(sku="X-S", option="X", olcut=(50.0, 60.0, 50.0, 40.0)))
    v["kural_olcut"] = pd.concat([_veri(option="Y")["kural_olcut"],
                                  _veri(olcut=(50.0, 60.0, 50.0, 40.0))["kural_olcut"]])
    h = _sec(v)
    assert (h.sku, h.gevseyen) == ("Y-STD", ["bedenli"])
    assert h.alternatif == "X:X-S"


def test_gevsetme_sirasi_kural_yavastan_once():
    yavas_degil = {"A1": (10, 2, 20, 1), "A2": (4, 1, 20, 1), "V1": (10, 3, 20, 1), "V2": (5, 1, 20, 1)}
    v = _birlestir(_veri(sku="X-S", option="X", hizlar=yavas_degil),
                   _veri(sku="Z-S", option="Z", olcut=(50.0, 60.0, 50.0, 40.0)))
    v["kural_olcut"] = pd.concat([_veri()["kural_olcut"], _veri(option="Z", olcut=(50.0, 60.0, 50.0, 40.0))["kural_olcut"]])
    h = _sec(v)
    assert (h.sku, h.gevseyen) == ("Z-S", ["kural_iyi"])


def test_gevsemezler_gevsemez_bulunamazsa_hata():
    v = _veri(gidenler={"A1": 5, "A2": 3, "V1": 4, "V2": 2})       # kesim yok
    with pytest.raises(LookupError, match="huni"):
        _sec(v)


def test_zorla():
    yavas_degil = {"A1": (10, 2, 20, 1), "A2": (4, 1, 20, 1), "V1": (10, 3, 20, 1), "V2": (5, 1, 20, 1)}
    v = _birlestir(_veri(), _veri(sku="Z-S", option="Z", hizlar=yavas_degil))
    v["kural_olcut"] = pd.concat([_veri()["kural_olcut"], _veri(option="Z")["kural_olcut"]])
    h = _sec(v, zorla=("Z", "Z-S"))
    assert (h.option_id, h.sku, h.gevseyen) == ("Z", "Z-S", ["yavas_giden"])
    assert h.alternatif == "X:X-S"
    with pytest.raises(LookupError):
        _sec(v, zorla=("Q", "Q-S"))                                  # havuzda yok
    with pytest.raises(ValueError):
        _sec(v, zorla=("X", "Z-S"))                                  # SKU başka option'ın


def test_zorla_gevsemez_tutmasa_da_secer():
    v = _birlestir(_veri(), _veri(sku="Z-S", option="Z", gidenler={"A1": 5, "A2": 3, "V1": 4, "V2": 2}))
    v["kural_olcut"] = pd.concat([_veri()["kural_olcut"], _veri(option="Z")["kural_olcut"]])
    h = _sec(v, zorla=("Z", "Z-S"))
    assert "kesim" in h.gevseyen and "iki_bolge" in h.gevseyen


def test_hikaye_magazalari():
    h = _sec(_veri())
    assert h.pazartesi == date(2025, 9, 8) and h.pazartesi_indeksi == 1
    assert h.ali_magazalari == ["A1", "A2"] and h.veli_magazalari == ["V1", "V2"]
    assert h.giden == ["V1"] and h.gitmeyen == ["A1", "A2", "V2"]
    assert h.alternatif is None


def test_zorlanan_sku_en_iyi_pazartesisi():
    """Aynı SKU iki pazartesi istenmişse zorlama en az ölçütü tutmayan pazartesiyi alır
    (2025-09-08'de depo hepsini karşıladı, kesim yok; 09-15 birebir)."""
    v = _veri(p=P1)
    tam = {"A1": 5, "A2": 3, "V1": 4, "V2": 2}
    v["istekler"] = pd.concat([_istek(P0, "X-S", "X", "Kadın Harf", tam), v["istekler"]], ignore_index=True)
    v["sevkiyat"] = pd.concat([_sevk(P0, "X-S", tam), v["sevkiyat"]], ignore_index=True)
    h = _sec(v, zorla=("X", "X-S"))
    assert h.pazartesi == date(2025, 9, 15) and h.pazartesi_indeksi == 2 and h.gevseyen == []


def test_secim_ayristir():
    assert hs.secim_ayristir("MDL1-SYH:MDL1-SYH-S") == ("MDL1-SYH", "MDL1-SYH-S")
    for kotu in ("MDL1-SYH", "a:", ":b", "a:b:c"):
        with pytest.raises(ValueError):
            hs.secim_ayristir(kotu)


# ---------------------------------------------------------------- sansür örneği


def test_sansur_ornegi_en_buyuk_fark():
    s1, t1 = _gunluk("X-S", "A1", P0, 7, 4)          # 7 stoklu gün × 4: takvim 1,0, stoklu 4,0
    s2, t2 = _gunluk("X-S", "V1", P0, 28, 2)         # hep stoklu: fark 0
    s3, t3 = _gunluk("X-S", "A2", P0, 3, 9)          # fark büyük ama stoklu gün az
    satis, stoklu = pd.concat([s1, s2, s3]), pd.concat([t1, t2, t3])
    assert hs.sansur_ornegi(satis, stoklu) == ("A1", "X-S")
    h = hs.hucre_hizlari(satis, stoklu).set_index("magaza_id")
    assert h.loc["A1", "hiz_takvim"] == pytest.approx(1.0) and h.loc["A1", "hiz_stoklu"] == pytest.approx(4.0)
    assert (h.loc["A1", "takvim_gun"], h.loc["A1", "stoklu_gun"]) == (28, 7)
    with pytest.raises(LookupError):
        hs.sansur_ornegi(s2, t2)                      # hiç boş günü olmayan hücre


# ---------------------------------------------------------------- girdi


def test_girdi_dogrula():
    oyun = {"kosular": {"lumoda_kisitsiz": {"anahtar": "a"}, "demo_kural_a100_kisitsiz": {"anahtar": "b"}}}
    iyi = {"lumoda": {"ad": "lumoda_kisitsiz", "anahtar": "a"}, "kural": {"ad": "demo_kural_a100_kisitsiz", "anahtar": "b"}}
    hs.girdi_dogrula({"kosular": iyi}, oyun)
    with pytest.raises(RuntimeError, match="bayat"):
        hs.girdi_dogrula({"kosular": {**iyi, "kural": {"ad": "demo_kural_a100_kisitsiz", "anahtar": "x"}}}, oyun)
    with pytest.raises(RuntimeError, match="R31"):
        hs.girdi_dogrula({"kosular": {**iyi, "kural": {"ad": "kural_ref", "anahtar": "b"}}}, oyun)
    with pytest.raises(RuntimeError):
        hs.girdi_dogrula({"kosular": {"lumoda": iyi["lumoda"]}}, oyun)
    with pytest.raises(RuntimeError, match="izgara"):
        hs.girdi_dogrula({"kosular": iyi}, {"kosular": {"lumoda_kisitsiz": {"anahtar": "a"}}})


def test_girdi_oku_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(FileNotFoundError, match="hikaye-girdi"):
        hs.girdi_oku(tmp_path / "yok", tmp_path / "oyun.json")


def test_ozet_json_yazilabilir():
    v = _veri()
    t = hs.magaza_tablosu(v["istekler"], v["sevkiyat"], v["satis"], v["stoklu"], MAG)
    f = hs.ozellikler(t, v["kural_olcut"])
    h = hs.sec(v["istekler"], v["sevkiyat"], v["satis"], v["stoklu"], MAG, v["kural_olcut"], tablo=t, f=f)
    urunler = pd.DataFrame({"urun_id": ["X-S"], "option_id": ["X"], "model_adi": ["Elbise"], "renk": ["Siyah"],
                            "alt_kategori": ["Elbise"], "line": ["Collection"], "beden": ["S"],
                            "lansman_tarihi": [pd.Timestamp("2025-08-25")]})
    o = hs.ozet(h, t, f, MAG, urunler)
    json.dumps(o, default=hs._json_degeri)
    assert o["option_id"] == "X" and o["pazartesi_sirasi"] == 2 and o["lansmandan_gun"] == 14
    assert [m["magaza_id"] for m in o["magazalar"]] == ["A1", "A2", "V1", "V2"]
    a1 = o["magazalar"][0]
    assert (a1["istek"], a1["giden"], a1["kisi"], a1["sonra"]["stoklu_gun"]) == (5, 0, "Ali", 10)
    assert o["gruplar"]["ali_gitmeyen"]["hiz"] == pytest.approx(24 / 14)
    assert o["kural_olcut"]["bulunabilirlik_kural"] == 70.0
