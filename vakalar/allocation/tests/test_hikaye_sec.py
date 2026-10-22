"""Hikâye seçimi (spec §6): merdivenin her ölçütü, gevşetme sırası, zorlama, bulunamazsa hata,
yardımcı tablolar ve önbellekten okuyan ince CLI (sentetik önbellek dizini; koşu yok)."""

import json

import numpy as np
import pandas as pd
import pytest

from allocation import hikaye_sec as hs
from allocation import kaynak

V = pd.Timestamp("2025-02-10")       # varış günü


def gun(n: int) -> pd.Timestamp:
    return V + pd.Timedelta(days=n)


MAG = pd.DataFrame(
    [("I1", "İstanbul 1", "İstanbul", "AVM"), ("A1", "Ankara 1", "Ankara", "AVM"),
     ("A2", "İzmir 1", "İzmir", "Cadde"), ("A3", "Bursa 1", "Bursa", "AVM"),
     ("A4", "Konya 1", "Konya", "AVM"), ("O1", "Ankara Outlet", "Ankara", "Outlet"),
     ("ONL", "Online", "Gebze", "Online")],
    columns=["magaza_id", "ad", "sehir", "tip"])


def plan(hedef: dict | None = None) -> pd.DataFrame:
    """SS25 Üst Giyim hedefleri (outlet en büyük: fiziksel sıraya girmez) + SS24 satırları
    (sezon süzgeci) + başka üst kategori."""
    h = {"A1": 900, "I1": 800, "A3": 700, "A2": 600, "A4": 500, "O1": 1000}
    h.update(hedef or {})
    satir = [("SS25", m, "Üst Giyim", v) for m, v in h.items()]
    satir += [("SS24", m, "Üst Giyim", 1000 - i) for i, m in enumerate(["A4", "A3", "A2", "I1", "A1"])]
    satir += [("SS25", m, "Alt Giyim", 100 + i) for i, m in enumerate(["A1", "A2", "A3", "A4", "I1"])]
    return pd.DataFrame(satir, columns=["sezon_kodu", "magaza_id", "ust_kategori", "satis_hedefi"])


def ilk(option="P", adetler=None, ad="Bluz Bej", ust="Üst Giyim") -> pd.DataFrame:
    a = {"A1": 100, "I1": 60, "A3": 40, "A2": 10, "A4": 20, "O1": 50}
    a.update(adetler or {})
    return pd.DataFrame({"option_id": option, "ad": ad, "ust_kategori": ust, "magaza_id": list(a),
                         "adet": list(a.values()), "varis": V})


def satis(option="P", tasan=5, biten=9, istanbul=59, ek=()) -> pd.DataFrame:
    s = [(option, "A1", gun(3), tasan), (option, "A1", gun(28), 50),   # 28. gün pencere dışı
         (option, "A1", gun(-1), 30),                                  # varıştan önce
         (option, "A2", gun(2), biten), (option, "A2", gun(14), 5),     # 14. gün pencere dışı
         (option, "A4", gun(5), 10), (option, "I1", gun(1), istanbul), (option, "A2", gun(4), -3)]
    s += list(ek)
    return pd.DataFrame(s, columns=["option_id", "magaza_id", "tarih", "adet"])


def kol(option="P", adetler=None) -> pd.DataFrame:
    a = {"A1": 40, "I1": 60, "A3": 60, "A2": 20, "A4": 30}
    a.update(adetler or {})
    return pd.DataFrame({"option_id": option, "magaza_id": list(a), "adet": list(a.values())})


def sec(i=None, s=None, p=None, k=None, **kw):
    return hs.sec(ilk() if i is None else i, satis() if s is None else s, MAG,
                  plan() if p is None else p, kol() if k is None else k, **kw)


# ---------------------------------------------------------------------------
# Merdivenin her ölçütü
# ---------------------------------------------------------------------------


def test_butun_olcutler_tutan_sahne():
    h = sec()
    assert h == hs.Hikaye(option_id="P", ad="Bluz Bej", tasan_magaza="Ankara 1", biten_magaza="İzmir 1",
                          tasan_ilk_adet=100, tasan_satis_28=5, biten_ilk_adet=10, biten_satis_14=9,
                          tasan_plan_sirasi=1, kol_tasan_adet=40, kol_biten_adet=20, gevseyen=[],
                          alternatif=None)


def test_olcut1_satis_esigi_gevser():
    h = sec(s=satis(tasan=15))                           # %15 > %10
    assert h.tasan_satis_28 == 15
    assert h.gevseyen == [hs.MERDIVEN[1].gevseyen[-1]]
    with pytest.raises(hs.HikayeBulunamadi):
        sec(s=satis(tasan=21))                           # %21: son eşik %20'yi de aşar


def test_olcut1_en_buyuk_pay_istanbulda_ise_pay_sirasi_gevser():
    h = sec(i=ilk(adetler={"I1": 150}))                  # en büyük pay Veli'nin değil
    assert h.tasan_magaza == "Ankara 1"
    assert h.gevseyen == list(hs.MERDIVEN[2].gevseyen)
    assert "1: payda ilk 3" in h.gevseyen


def test_olcut3_istanbulda_tasan_magaza_secilmez():
    # İstanbul 1 malı yığmış ve satmamış (taşan olmanın bütün öteki ölçütleri tutuyor: sıra 1,
    # %3 satış, plan sırası 2, kol %25): yalnız Veli ölçütü dışarıda bırakır
    i, s = ilk(adetler={"I1": 150}), satis(istanbul=5)
    k = kol(adetler={"I1": 30})
    h = hs.hucreler(i, s, MAG, plan(), k).set_index("magaza_id")
    assert (h.loc["I1", "pay_sirasi"], h.loc["I1", "satis_28"], h.loc["I1", "plan_sirasi"]) == (1, 5, 2)
    assert not h.loc["I1", "veli"]
    t = hs.adaylar(i, s, MAG, plan(), k, hs.MERDIVEN[0])
    assert len(t) == 0                                   # basamak 0'da Veli'nin taşanı yok
    h = sec(i=i, s=s, k=k)
    assert h.tasan_magaza == "Ankara 1" and h.gevseyen == list(hs.MERDIVEN[2].gevseyen)


def test_olcut4_plani_olmayan_tasan_sira_0():
    # Ankara 1'in SS25 Üst Giyim planı yok: sıra 0, plan ölçütü düşene dek taşan olamaz
    p = plan()
    p = p[~((p["magaza_id"] == "A1") & (p["sezon_kodu"] == "SS25") & (p["ust_kategori"] == "Üst Giyim"))]
    assert hs.hucreler(ilk(), satis(), MAG, p, kol()).set_index("magaza_id").loc["A1", "plan_sirasi"] == 0
    for b in hs.MERDIVEN[:3]:
        assert hs.adaylar(ilk(), satis(), MAG, p, kol(), b).empty
    h = sec(p=p)
    assert h.tasan_magaza == "Ankara 1" and h.tasan_plan_sirasi == 0
    assert h.gevseyen == list(hs.MERDIVEN[3].gevseyen)


def test_olcut1_outlet_mağaza_aday_toplamina_ve_sirasina_girmez():
    h = sec(i=ilk(adetler={"O1": 500}))                  # outlet en büyük: sıra fizikselde
    assert h.tasan_magaza == "Ankara 1" and h.gevseyen == []


def test_olcut2_biten_14_gunde_yuzde_80():
    h = sec(s=satis(biten=8))                            # 8/10 = %80 sınırda tutar
    assert h.biten_magaza == "İzmir 1" and h.biten_satis_14 == 8
    with pytest.raises(hs.HikayeBulunamadi):             # 2 gevşemez (A4 %50)
        sec(s=satis(biten=7))


def test_olcut2_biten_kucuk_pay_almis_olmali():
    # İzmir 1 ortalamanın (60) üstünde pay alırsa "biten mağaza" değildir
    i = ilk(adetler={"A2": 80})
    s = satis(biten=70)
    with pytest.raises(hs.HikayeBulunamadi):
        sec(i=i, s=s, k=kol(adetler={"A2": 90}))
    h = sec(i=ilk(adetler={"A2": 50}), s=satis(biten=45), k=kol(adetler={"A2": 90}))   # ortalama 54: tutar
    assert h.biten_ilk_adet == 50


def test_olcut3_istanbul_magazasi_biten_olamaz():
    s = satis(biten=0, ek=[("P", "I1", gun(2), 0)])
    i = ilk(adetler={"I1": 10})                          # İstanbul 1 küçük pay, 59 satış (> %80)
    with pytest.raises(hs.HikayeBulunamadi):
        sec(i=i, s=s, k=kol(adetler={"I1": 30}))


def test_olcut3_online_ve_outlet_disarida():
    m = hs.magaza_tablosu(MAG)
    assert m.set_index("magaza_id").loc[["I1", "A1", "O1", "ONL"], "veli"].tolist() == [
        False, True, False, False]


def test_magaza_tablosu_haritayla_ayni(dunya):
    h = kaynak.harita_kur(dunya)
    m = hs.magaza_tablosu(dunya.magazalar)
    assert (m["istanbul"].to_numpy() == h.magaza_istanbul).all()
    assert (m["fiziksel"].to_numpy() == h.magaza_fiziksel).all()
    assert (m["veli"].to_numpy() == (~h.magaza_istanbul & h.magaza_fiziksel)).all()


def test_olcut4_plan_sirasi_gevser():
    h = sec(p=plan({"A1": 550}))                         # A1 fiziksel sırada 4.
    assert h.tasan_plan_sirasi == 4
    assert h.gevseyen == list(hs.MERDIVEN[3].gevseyen)
    assert h.gevseyen[-1] == "4: plan sırası düştü"


def test_plan_sirasi_sezon_ve_ust_kategori_fiziksel_magazalarda():
    s = hs.plan_sirasi(plan(), MAG, "SS25")
    s = s.set_index(["magaza_id", "ust_kategori"])["sira"]
    assert s[("A1", "Üst Giyim")] == 1 and s[("I1", "Üst Giyim")] == 2 and s[("A4", "Üst Giyim")] == 5
    assert s[("I1", "Alt Giyim")] == 1
    assert ("O1", "Üst Giyim") not in s.index


def test_olcut5_oran_gevser_ama_asla_dusmez():
    h = sec(k=kol(adetler={"A1": 65}))                   # %65 > %50, ≤ %70
    assert h.kol_tasan_adet == 65 and h.gevseyen[-1] == "5: kol taşana ≤ %70"
    assert h.gevseyen == list(hs.MERDIVEN[4].gevseyen)
    with pytest.raises(hs.HikayeBulunamadi):
        sec(k=kol(adetler={"A1": 71}))
    with pytest.raises(hs.HikayeBulunamadi):             # bitene daha çok değil
        sec(k=kol(adetler={"A2": 10}))
    with pytest.raises(hs.HikayeBulunamadi):             # kol biteni hiç dağıtmadı
        sec(k=kol().query("magaza_id != 'A2'"))


def test_merdiven_sirasi_ve_5_her_basamakta():
    assert [d.gevseyen for d in hs.MERDIVEN][0] == ()
    for a, b in zip(hs.MERDIVEN, hs.MERDIVEN[1:]):
        assert b.gevseyen[:len(a.gevseyen)] == a.gevseyen and len(b.gevseyen) == len(a.gevseyen) + 1
    etiket = [d.gevseyen[-1][0] for d in hs.MERDIVEN[1:]]
    assert etiket == ["1", "1", "4", "5"]                # 1'in eşikleri → 4 → 5'in oranı
    assert all(d.kol_orani < 1 for d in hs.MERDIVEN)


# ---------------------------------------------------------------------------
# Gevşetme sırası, sıralama, alternatif, zorlama
# ---------------------------------------------------------------------------


def iki_option(q_tasan=100, q_tasan_satis=15):
    """P tam tutar (seviye 0); Q yalnız satış eşiği gevşeyince tutar ve daha çok mal oturtur."""
    q = ilk("Q", adetler={"A1": q_tasan}, ad="Etek Siyah")
    return (pd.concat([ilk(), q], ignore_index=True),
            pd.concat([satis(), satis("Q", tasan=q_tasan_satis)], ignore_index=True),
            pd.concat([kol(), kol("Q")], ignore_index=True))


def test_gevsetme_sirasi_once_siki_basamak():
    i, s, k = iki_option(q_tasan=300, q_tasan_satis=45)   # Q: %15, daha çok oturan
    h = sec(i=i, s=s, k=k)
    assert h.option_id == "P" and h.gevseyen == [] and h.alternatif == "Q"


def test_ayni_basamakta_cok_oturan_one_gecer():
    i, s, k = iki_option(q_tasan=300, q_tasan_satis=6)    # ikisi de tam; Q'da 294 oturur
    h = sec(i=i, s=s, k=k)
    assert (h.option_id, h.alternatif, h.tasan_ilk_adet) == ("Q", "P", 300)


def test_adaylar_tablosu():
    i, s, k = iki_option(q_tasan=300, q_tasan_satis=45)
    a0 = hs.adaylar(i, s, MAG, plan(), k, hs.MERDIVEN[0])
    a1 = hs.adaylar(i, s, MAG, plan(), k, hs.MERDIVEN[1])
    assert a0["option_id"].tolist() == ["P"]
    assert a1["option_id"].tolist() == ["Q", "P"]        # oturan adede göre
    assert {"tasan_magaza_id", "biten_magaza_id", "oturan", "tasan_pay", "biten_pay"} <= set(a1.columns)


def test_zorlama():
    i, s, k = iki_option(q_tasan=300, q_tasan_satis=45)
    h = sec(i=i, s=s, k=k, zorla="Q")
    assert h.option_id == "Q" and h.gevseyen == list(hs.MERDIVEN[1].gevseyen) and h.alternatif == "P"
    with pytest.raises(hs.HikayeBulunamadi, match="R"):
        sec(i=i, s=s, k=k, zorla="R")


def test_bulunamazsa_hata():
    with pytest.raises(hs.HikayeBulunamadi):
        sec(s=satis(biten=1))


def test_biten_secimi_en_hizli_satan():
    # A4 de %100 satarsa ve küçük paysa: en yüksek oran biten olur
    s = satis(ek=[("P", "A4", gun(6), 10)])                 # A4 20/20
    h = sec(s=s, k=kol(adetler={"A4": 30}))
    assert h.biten_magaza == "Konya 1" and h.biten_satis_14 == 20


# ---------------------------------------------------------------------------
# Yardımcı tablolar
# ---------------------------------------------------------------------------

URUN = pd.DataFrame(
    [("P-S", "P", "Bluz", "Bej", "Üst Giyim", "SS25", "Collection"),
     ("P-M", "P", "Bluz", "Bej", "Üst Giyim", "SS25", "Collection"),
     ("Z-S", "Z", "Bluz", "Mavi", "Üst Giyim", "SS24", "Collection"),
     ("C-S", "C", "Tişört", "Ak", "Üst Giyim", "SS25", "Outlet")],
    columns=["urun_id", "option_id", "model_adi", "renk", "ust_kategori", "sezon_kodu", "line"])


def test_ilk_tablosu_skulari_toplar_ilk_varis():
    sv = pd.DataFrame(
        [("ilk_dagitim", "A1", "P-S", 3, gun(1)), ("ilk_dagitim", "A1", "P-M", 4, gun(0)),
         ("replenishment", "A1", "P-S", 9, gun(5)), ("ilk_dagitim", "A1", "Z-S", 5, gun(0)),
         ("ilk_dagitim", "A1", "C-S", 5, gun(0)), ("ilk_dagitim", "A2", "P-S", 2, gun(2))],
        columns=["tip", "hedef", "urun_id", "adet", "varis_tarihi"])
    sv["tip"] = sv["tip"].astype("category")
    t = hs.ilk_tablosu(sv, URUN, "SS25")
    assert t.to_dict("records") == [
        {"option_id": "P", "ad": "Bluz Bej", "ust_kategori": "Üst Giyim", "magaza_id": "A1", "adet": 7,
         "varis": gun(0)},
        {"option_id": "P", "ad": "Bluz Bej", "ust_kategori": "Üst Giyim", "magaza_id": "A2", "adet": 2,
         "varis": gun(2)}]


def test_satis_tablosu_option_eslemesi():
    s = pd.DataFrame([(gun(0), "A1", "P-S", 2), (gun(0), "A1", "Z-S", 3)],
                     columns=["tarih", "magaza_id", "urun_id", "adet"])
    t = hs.satis_tablosu(s, URUN, "SS25")
    assert t.to_dict("records") == [{"option_id": "P", "magaza_id": "A1", "tarih": gun(0), "adet": 2}]


# ---------------------------------------------------------------------------
# İnce CLI: önbellek dizininden okuma (sentetik; koşu yok)
# ---------------------------------------------------------------------------


def _kosu_yaz(onbellek, ad, anahtar, tablolar):
    d = onbellek / f"{ad}_{anahtar[:20]}"
    d.mkdir(parents=True)
    for t, df in tablolar.items():
        df.to_parquet(d / f"tablo_{t}.parquet", index=False)
    (d / "meta.json").write_text(json.dumps({"anahtar": anahtar, "ad": ad, "tablolar": sorted(tablolar)}),
                                 encoding="utf-8")
    return d


def _sevkiyat(i: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"tip": "ilk_dagitim", "hedef": i["magaza_id"], "urun_id": i["option_id"] + "-S",
                         "adet": i["adet"], "varis_tarihi": i["varis"]})


def _sentetik_onbellek(tmp_path, kol_adi="pay_tahmin_tavanli", takma=False):
    i, s, k = iki_option(q_tasan=300, q_tasan_satis=45)
    urun = pd.DataFrame({"urun_id": ["P-S", "Q-S"], "option_id": ["P", "Q"], "model_adi": ["Bluz", "Etek"],
                         "renk": ["Bej", "Siyah"], "ust_kategori": "Üst Giyim", "alt_kategori": ["Bluz", "Etek"],
                         "sezon_kodu": "SS25", "line": "Collection"})
    sat = s.assign(urun_id=s["option_id"] + "-S").drop(columns="option_id")
    onb = tmp_path / "kosular"
    a_l, a_k = "a" * 64, "b" * 64
    _kosu_yaz(onb, "lumoda", a_l, {"sevkiyat": _sevkiyat(i), "satis": sat, "urun": urun, "magaza": MAG,
                                   "magaza_plan": plan()})
    taban = "pay_tahmin_tavanli"
    _kosu_yaz(onb, taban, a_k, {"sevkiyat": _sevkiyat(k.assign(varis=V))})
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    kosular = {"lumoda": {"anahtar": a_l}, taban: {"anahtar": a_k}}
    if takma:
        kosular[kol_adi] = {"anahtar": a_k, "ayni": taban}
    (cikti / "oyun.json").write_text(json.dumps({"kosular": kosular}), encoding="utf-8")
    (cikti / "secim.json").write_text(json.dumps({"kol": "tahmin", "ad": kol_adi}), encoding="utf-8")
    return onb, cikti


def test_kosu_dizini_motorun_adlandirmasiyla_ayni(tmp_path):
    from allocation import motor          # testte serbest; modülün kendisi motoru içe aktarmaz

    assert hs.kosu_dizini_yolu(tmp_path, "lumoda", "c" * 64) == motor._dizin(tmp_path, "lumoda", "c" * 64)


def test_kosu_dizini_anahtar_tutmazsa_hata(tmp_path):
    _kosu_yaz(tmp_path, "lumoda", "a" * 64, {"magaza": MAG})
    assert hs.kosu_dizini(tmp_path, "lumoda", "a" * 64).name == "lumoda_" + "a" * 20
    with pytest.raises(FileNotFoundError):
        hs.kosu_dizini(tmp_path, "lumoda", "a" * 20 + "x" * 44)
    with pytest.raises(FileNotFoundError):
        hs.kosu_dizini(tmp_path, "esit", "a" * 64)


@pytest.mark.parametrize("takma", [False, True])
def test_cli_hikaye_json(tmp_path, capsys, takma):
    onb, cikti = _sentetik_onbellek(tmp_path, kol_adi="tut_eniyi_t00" if takma else "pay_tahmin_tavanli",
                                    takma=takma)
    hs.main(["--onbellek", str(onb), "--cikti", str(cikti)])
    j = json.loads((cikti / "hikaye.json").read_text(encoding="utf-8"))
    assert j["sahne"]["option_id"] == "P" and j["sahne"]["alternatif"] == "Q"
    assert j["sahne"]["tasan_magaza"] == "Ankara 1" and j["sahne"]["gevseyen"] == []
    assert j["alternatif_sahne"]["option_id"] == "Q"
    assert j["alternatif_sahne"]["gevseyen"] == list(hs.MERDIVEN[1].gevseyen)
    assert j["kol"] == {"kol": "tahmin", "ad": "tut_eniyi_t00" if takma else "pay_tahmin_tavanli"}
    assert j["magaza_idleri"] == {"tasan": "A1", "biten": "A2"}
    kol_k = j["kaynak"]["kol"]
    assert j["kaynak"]["lumoda"] == {"ad": "lumoda", "dizin": "lumoda_" + "a" * 20, "anahtar": "a" * 64,
                                     "anahtar_kaynagi": "cikti/oyun.json", "ayni": None}
    assert kol_k["dizin"] == "pay_tahmin_tavanli_" + "b" * 20 and kol_k["anahtar_kaynagi"] == "cikti/oyun.json"
    assert kol_k["ayni"] == ("pay_tahmin_tavanli" if takma else None)
    assert j["aday_sayilari"] == [1, 2, 2, 2, 2]
    assert "P" in capsys.readouterr().out


def test_cli_zorla_ve_adaylar(tmp_path, capsys):
    onb, cikti = _sentetik_onbellek(tmp_path)
    hs.main(["--onbellek", str(onb), "--cikti", str(cikti), "--hikaye", "Q", "--adaylar"])
    j = json.loads((cikti / "hikaye.json").read_text(encoding="utf-8"))
    assert j["sahne"]["option_id"] == "Q" and j["zorla"] == "Q" and j["alternatif_sahne"]["option_id"] == "P"
    out = capsys.readouterr().out
    assert "basamak 1" in out and "Etek Siyah" in out


def test_cli_secim_yoksa_hata(tmp_path):
    onb, cikti = _sentetik_onbellek(tmp_path)
    (cikti / "secim.json").unlink()
    with pytest.raises(SystemExit, match="secim.json"):
        hs.main(["--onbellek", str(onb), "--cikti", str(cikti)])


def test_sayilar_int():
    h = sec()
    for ad in ("tasan_ilk_adet", "tasan_satis_28", "biten_ilk_adet", "biten_satis_14", "tasan_plan_sirasi",
               "kol_tasan_adet", "kol_biten_adet"):
        assert type(getattr(h, ad)) is int and not isinstance(getattr(h, ad), np.integer)
