import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import sentetik_gunluk
from perakende_analitik.carpanlar import Carpanlar

import rpt
from rpt import egri, hazirla, kaynak, sansur

NOTR = Carpanlar()   # bütün çarpanlar 1 (sentetik veride gün karakteri yok)
LANSMAN = pd.Timestamp("2025-02-10")


def _egri(pay=(0.25, 0.25, 0.25, 0.25)):
    return egri.Egri(paylar={(1,): np.array(pay)}, grup=("dalga",), yontem="duzeltilmis",
                     hedef="indirim", sezonlar=("SS24",))


@pytest.fixture(scope="module")
def sentetik():
    g, opt, _ = sentetik_gunluk([("O1", "SS25", LANSMAN, 12, 1), ("O2", "SS25", LANSMAN, 12, 1)],
                                magaza_sayisi=24)
    return g, opt


def _havuz(opt, t):
    return sansur.karar_havuzu(opt, "SS25", t)


# --------------------------------------------------------------- kestirim


def test_karar_ani_talep_stoksuz_gunleri_doldurur(sentetik):
    g, opt = sentetik
    t = LANSMAN + pd.Timedelta(days=42)
    r = sansur.karar_ani_talep(g, t, NOTR, _havuz(opt, t))
    assert r["tarih"].max() < t and r["tarih"].min() >= LANSMAN
    stoklu = r["durum"] == "stoklu"
    assert (r.loc[stoklu, "kayip"] == 0).all() and r.loc[stoklu, "tahmini_talep"].isna().all()
    assert (r.loc[r["durum"] == "bos", "kayip"] > 0).all()
    tuk = r["durum"] == "tukenen"
    assert tuk.any() and (r.loc[tuk, "kayip"] > 0).all()
    np.testing.assert_allclose(r["talep"], r["brut_satis"] + r["kayip"])
    # düzeltme sansür açığının çoğunu kapatır (kalan açık: tükenen günler havuza
    # girmez, stoklu kalan pazartesiler düşük talepli olanlardır — Basit'in bilinen yanlılığı)
    gercek = g[(g["tarih"] < t)]["gercek_talep"].sum()
    acik = gercek - r["brut_satis"].sum()
    assert acik > 0.2 * gercek
    assert abs(r["talep"].sum() - gercek) < 0.25 * acik


def test_karar_ani_katmanlari_gelecegi_gormez(sentetik):
    """t ve sonrasındaki satırlar (satış, durum, stok, yeni satırlar) katmanları değiştirmez."""
    g, opt = sentetik
    h = 5                                   # sansür 3. haftada başlar
    t = LANSMAN + pd.Timedelta(days=7 * h)
    a = sansur.katmanlar(t, h, g, opt, NOTR, _egri((0.3, 0.2, 0.2, 0.1, 0.1, 0.1)), _egri(np.full(8, 0.125)))
    bozuk = g.copy()
    sonra = bozuk["tarih"] >= t
    bozuk.loc[sonra, "brut_satis"] = bozuk.loc[sonra, "brut_satis"] * 5 + 3
    bozuk.loc[sonra, "satis_oncesi"] = 0
    bozuk.loc[sonra, "durum"] = "bos"
    bozuk.loc[sonra, "oran"] = np.float32(0.5)
    ek = g[g["tarih"] == g["tarih"].max()].assign(tarih=g["tarih"].max() + pd.Timedelta(days=30),
                                                  magaza_id="M99")
    bozuk = pd.concat([bozuk, ek], ignore_index=True)
    b = sansur.katmanlar(t, h, bozuk, opt, NOTR, _egri((0.3, 0.2, 0.2, 0.1, 0.1, 0.1)),
                         _egri(np.full(8, 0.125)))
    pd.testing.assert_frame_equal(a, b)
    assert (a["D"] > a["x"]).all()
    # test boş geçmiyor: t'den önceki bir günü değiştirmek katmanları değiştirir
    once = g.copy()
    son_gun = once["tarih"] == t - pd.Timedelta(days=1)
    once.loc[son_gun, "brut_satis"] += 2
    c = sansur.katmanlar(t, h, once, opt, NOTR, _egri((0.3, 0.2, 0.2, 0.1, 0.1, 0.1)),
                         _egri(np.full(8, 0.125)))
    assert not np.allclose(a["d"], c["d"])


def test_kayip_okunmaz_davranis(sentetik):
    """Girdide gerçek talep / kayıp / hakem sütunları dursa da kestirim değişmez."""
    g, opt = sentetik
    t = LANSMAN + pd.Timedelta(days=28)
    a = sansur.karar_ani_talep(g.drop(columns="gercek_talep"), t, NOTR, _havuz(opt, t))
    zehir = g.assign(kayip=999.0, karsilanmayan=777, talep=g["gercek_talep"] * 3, kalici_kayip=5)
    b = sansur.karar_ani_talep(zehir, t, NOTR, _havuz(opt, t))
    pd.testing.assert_frame_equal(a, b)


KAYIP_ADLARI = ("hakem", "karsilanmayan", "kalici_kayip", "ikameye_giden", "kayip_satis",
                "gercek_talep", "gizli")


@pytest.mark.parametrize("modul", ["egri", "sansur", "anlik"])
def test_kayip_okunmaz_ast(modul):
    """Modül hakemi / gerçeği içe aktarmaz ve gizli gerçeğin sütun ya da tablo adlarını
    (dizge ya da öznitelik olarak) anmaz. `kayip` ortak Basit kaybıdır (girdi)."""
    yol = Path(rpt.__file__).parent / f"{modul}.py"
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar |= {a.name for a in d.names}
        elif isinstance(d, ast.ImportFrom):
            adlar |= {d.module or ""} | {f"{d.module}.{a.name}" for a in d.names}
    assert not [a for a in adlar if "hakem" in a or a.startswith("perakende_veri") or a.endswith("motor")]
    govde = ast.get_docstring(agac) or ""
    for d in ast.walk(agac):
        metin = None
        if isinstance(d, ast.Constant) and isinstance(d.value, str) and d.value != govde:
            metin = d.value
        elif isinstance(d, ast.Attribute):
            metin = d.attr
        elif isinstance(d, ast.Name):
            metin = d.id
        if metin is None or (isinstance(d, ast.Constant) and _docstring_mi(agac, d)):
            continue
        assert not any(y in metin for y in KAYIP_ADLARI), f"{modul}: {metin!r}"


def _docstring_mi(agac, dugum) -> bool:
    for d in ast.walk(agac):
        if isinstance(d, (ast.FunctionDef, ast.ClassDef, ast.Module)) and d.body:
            ilk = d.body[0]
            if isinstance(ilk, ast.Expr) and ilk.value is dugum:
                return True
    return False


def test_havuz_disindaki_satirlar_etkilemez(sentetik):
    g, opt = sentetik
    t = LANSMAN + pd.Timedelta(days=28)
    havuz = _havuz(opt, t)
    a = sansur.karar_ani_talep(g, t, NOTR, havuz)
    yabanci = g[g["option_id"] == "O1"].assign(option_id="X9", brut_satis=50)
    b = sansur.karar_ani_talep(pd.concat([g, yabanci], ignore_index=True), t, NOTR, havuz)
    pd.testing.assert_frame_equal(a, b)
    # havuz daralınca kestirim değişir (havuz sınırı gerçekten uygulanıyor)
    c = sansur.karar_ani_talep(g, t, NOTR, havuz[havuz["option_id"] == "O1"])
    assert set(c["option_id"].astype(str)) == {"O1"}


def test_karar_aninda_hic_stoklanmamis_hucre_duser(sentetik):
    g, opt = sentetik
    t = LANSMAN + pd.Timedelta(days=21)
    hucre = (g["magaza_id"] == "M00") & (g["urun_id"] == "O1-S")
    once = hucre & (g["tarih"] < t)
    bos = g.copy()
    bos.loc[once, ["brut_satis", "net_satis", "satis_oncesi"]] = 0
    bos.loc[once, "durum"] = "bos"
    r = sansur.karar_ani_talep(bos, t, NOTR, _havuz(opt, t))
    assert not ((r["magaza_id"] == "M00") & (r["urun_id"] == "O1-S")).any()
    # ortak tablonun "hiç stoklanmamış" kuralı hücreyi baştan atsa da sonuç aynı
    r2 = sansur.karar_ani_talep(bos[~hucre], t, NOTR, _havuz(opt, t))
    pd.testing.assert_frame_equal(r, r2)


def test_ozet_duzeyleri(sentetik):
    g, opt = sentetik
    t = LANSMAN + pd.Timedelta(days=14)
    r = sansur.karar_ani_talep(g, t, NOTR, _havuz(opt, t))
    o = sansur.ozet(r)
    ob = sansur.ozet(r, ("option_id", "urun_id"))
    assert list(o["option_id"]) == ["O1", "O2"]
    np.testing.assert_allclose(o["D"].sum(), ob["D"].sum())
    assert o["x"].sum() == r["brut_satis"].sum()
    assert ((o["stoklu_pay"] > 0) & (o["stoklu_pay"] <= 1)).all()


# --------------------------------------------------------------- katmanlar


def test_kestirim_katmanlari_elle():
    oz = pd.DataFrame({"option_id": ["A"], "x": [45.0], "D": [56.0], "stoklu_pay": [0.8],
                       "hucre_gun": [10.0]})
    opt = pd.DataFrame({"option_id": ["A", "B"], "dalga": [1, 1], "ust_kategori": ["Üst"] * 2,
                        "satis_hafta": [17 / 7] * 2, "plan_sezon": [50.0, 20.0]})
    k = sansur.katman_hesapla(oz, opt, 2, _egri((0.4, 0.3, 0.2, 0.1)), _egri()).set_index("option_id")
    W = 17 / 7
    a = k.loc["A"]
    assert a["a"] == 45
    assert a["b"] == pytest.approx(56 / 2 * W)
    assert a["c"] == pytest.approx(45 / 0.7)
    assert a["d"] == pytest.approx(56 / 0.5)
    assert a["a_hiz"] == pytest.approx(45 / 2 * W)
    assert a["c_duz_egri"] == pytest.approx(45 / 0.5)
    assert a["plan"] == 50.0
    assert k.loc["B", "x"] == 0 and k.loc["B", "d"] == 0      # özette yok: satışı yok


def test_katmanlar_yalniz_dalganin_optionlari(sentetik):
    g, opt = sentetik
    opt2 = pd.concat([opt, opt.iloc[[0]].assign(option_id="O3", dalga=2,
                                                lansman_tarihi=LANSMAN + pd.Timedelta(days=7))])
    with pytest.raises(ValueError):
        sansur.katmanlar(LANSMAN + pd.Timedelta(days=15), 2, g, opt2, NOTR, _egri(), _egri())
    k = sansur.katmanlar(LANSMAN + pd.Timedelta(days=14), 2, g, opt2, NOTR, _egri(), _egri())
    assert sorted(k["option_id"]) == ["O1", "O2"]


# --------------------------------------------------------------- doğruluk


def test_hata_olcutleri_elle():
    tahmin = pd.Series([110.0, 50.0])
    gercek = pd.Series([100.0, 100.0])
    m = sansur.hata_olcutleri(tahmin, gercek)
    assert m["mape"] == pytest.approx((0.10 + 0.50) / 2)
    assert m["wape"] == pytest.approx(60 / 200)
    assert m["yanlilik"] == pytest.approx(-40 / 200)
    assert m["n"] == 2


def test_gercek_talep_ve_hata_tablosu_argumanla():
    opt = pd.DataFrame({"option_id": ["A", "B"], "lansman_tarihi": [LANSMAN] * 2,
                        "indirim_baslangic": [LANSMAN + pd.Timedelta(days=17)] * 2,
                        "cikis_tarihi": [LANSMAN + pd.Timedelta(days=28)] * 2})
    gg = pd.DataFrame({"tarih": [LANSMAN, LANSMAN + pd.Timedelta(days=20),
                                 LANSMAN - pd.Timedelta(days=1), LANSMAN + pd.Timedelta(days=3)],
                       "option_id": ["A", "A", "A", "B"], "talep": [10, 5, 99, 40]})
    gt = sansur.gercek_talep(gg, opt).set_index("option_id")
    assert gt.loc["A", "gercek_io"] == 10 and gt.loc["A", "gercek_cikis"] == 15
    assert gt.loc["B", "gercek_io"] == 40
    kat = pd.DataFrame({"option_id": ["A", "B"], "h": [2, 2], "a": [5.0, 20.0], "b": [10.0, 40.0],
                        "c": [20.0, 60.0], "d": [12.0, 36.0], "plan_sezon": [5.0, 40.0]})
    t = sansur.hata_tablosu(kat, gt.reset_index(), katmanlar_=sansur.KATMANLAR)
    tum = t[t["kesit"] == "tümü"].set_index("katman")
    assert tum.loc["a", "wape"] == pytest.approx(25 / 50)
    assert tum.loc["b", "wape"] == pytest.approx(0.0)
    assert tum.loc["d", "yanlilik"] == pytest.approx(-2 / 50)
    assert set(t["kesit"]) == {"tümü", "tutan", "tutmayan"}   # A tutan (10/5 ≥ 1,5)


# --------------------------------------------------------------- gerçek veri


@pytest.fixture(scope="module")
def gunluk_v4():
    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok")
    con = kaynak.baglan()
    try:
        yol = hazirla.gunluk_yolu(con=con)
    except RuntimeError as e:
        con.close()
        pytest.skip(str(e))
    yield con, yol
    con.close()


@pytest.mark.veri
def test_gercek_veri_kirpilmis_tabloyla_ayni(veri, gunluk_v4):
    """SS25 1. dalga h = 3: t'ye kırpılmış okuma ile t'den uzun okuma aynı kestirimi verir."""
    con, yol = gunluk_v4
    opt = veri["opt"]
    t = pd.Timestamp("2025-02-10") + pd.Timedelta(days=21)
    havuz = sansur.karar_havuzu(opt, "SS25", t)
    c = hazirla.carpanlar(con, yol, t)
    kisa = hazirla.havuz_gunlugu(yol, con, havuz, t)
    uzun = hazirla.havuz_gunlugu(yol, con, havuz, t + pd.Timedelta(days=28))
    a = sansur.ozet(sansur.karar_ani_talep(kisa, t, c, havuz))
    b = sansur.ozet(sansur.karar_ani_talep(uzun, t, c, havuz))
    pd.testing.assert_frame_equal(a, b)
    assert (a["D"] >= a["x"]).all() and np.isfinite(a["D"]).all()
    assert sorted(a["option_id"]) == sorted(havuz["option_id"])
