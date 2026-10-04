"""degerlendir: tahmin ile hakemin karşılaştırılması (elle kurulmuş çerçevelerle)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import degerlendir, stok

S, M, L = "MDL0001-SYH-S", "MDL0001-SYH-M", "MDL0001-SYH-L"


# --------------------------------------------------------------- çerçeveler

def _kayip(satirlar: list[tuple]) -> pd.DataFrame:
    """(tarih, magaza, urun, durum, kayip, kayip_saf) -> Kayıp tablosu (R9, R10)."""
    df = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id", "durum", "kayip", "kayip_saf"])
    df["tarih"] = pd.to_datetime(df["tarih"]).astype("datetime64[ns]")
    df["option_id"] = df["urun_id"].str.rsplit("-", n=1).str[0]
    df["durum"] = pd.Categorical(df["durum"], categories=stok.DURUMLAR)
    for c in ("magaza_id", "urun_id", "option_id"):
        df[c] = df[c].astype("category")
    return df


def _hakem(satirlar: list[tuple]) -> pd.DataFrame:
    """(tarih, magaza, urun, karsilanmayan, ikameye_giden, kalici_kayip) -> hakem tablosu (R9)."""
    df = pd.DataFrame(satirlar, columns=["tarih", "magaza_id", "urun_id", "karsilanmayan",
                                         "ikameye_giden", "kalici_kayip"])
    df["tarih"] = pd.to_datetime(df["tarih"]).astype("datetime64[ns]")
    for c in ("magaza_id", "urun_id"):
        df[c] = df[c].astype("category")
    for c in ("karsilanmayan", "ikameye_giden", "kalici_kayip"):
        df[c] = df[c].astype("int32")
    return df


def _eslesik(satirlar: list[tuple]) -> pd.DataFrame:
    """(tarih, magaza, urun, durum, kayip, kayip_saf, karsilanmayan) doğrudan eşleşmiş çerçeve."""
    k = _kayip([s[:6] for s in satirlar])
    k["karsilanmayan"] = np.array([s[6] for s in satirlar], dtype="int32")
    k["ikameye_giden"] = np.int32(0)
    k["kalici_kayip"] = k["karsilanmayan"]
    return k


# ---------------------------------------------------------------- eşleştir

def test_hakemde_olmayan_sifir():
    k = _kayip([("2025-01-08", "M001", S, "bos", 1.5, 1.5),
                ("2025-01-09", "M001", S, "tukenen", 2.0, 0.0),
                ("2025-01-09", "M002", M, "bos", 0.7, 0.7)])
    h = _hakem([("2025-01-09", "M001", S, 3, 1, 2)])
    e = degerlendir.eslestir(k, h)
    assert list(e.columns) == list(k.columns) + ["karsilanmayan", "ikameye_giden", "kalici_kayip"]
    assert e.index.equals(k.index)
    assert list(e["karsilanmayan"]) == [0, 3, 0]
    assert list(e["ikameye_giden"]) == [0, 1, 0]
    assert list(e["kalici_kayip"]) == [0, 2, 0]
    for s in ("karsilanmayan", "ikameye_giden", "kalici_kayip"):
        assert e[s].dtype == np.int32
    assert e["kayip"].tolist() == k["kayip"].tolist()           # girdi sütunları aynen
    assert "karsilanmayan" not in k.columns                      # girdi değişmedi


def test_eslestir_kategori_evrenleri_farkli_ve_bos_hakem():
    k = _kayip([("2025-01-09", "M001", S, "bos", 1.0, 1.0),
                ("2025-01-09", "M002", M, "bos", 1.0, 1.0)])
    # hakemde kayıpta olmayan mağaza / ürün de var, kategori sırası farklı
    h = _hakem([("2025-01-09", "M009", L, 5, 0, 5),
                ("2025-01-09", "M002", M, 2, 2, 0),
                ("2025-01-09", "M001", S, 4, 0, 4)])
    e = degerlendir.eslestir(k, h)
    assert list(e["karsilanmayan"]) == [4, 2]
    bos = degerlendir.eslestir(k, h.iloc[0:0])
    assert list(bos["karsilanmayan"]) == [0, 0] and bos["karsilanmayan"].dtype == np.int32


def test_eslestir_tekrarli_hakem_anahtari_hata():
    k = _kayip([("2025-01-09", "M001", S, "bos", 1.0, 1.0)])
    h = _hakem([("2025-01-09", "M001", S, 1, 0, 1), ("2025-01-09", "M001", S, 2, 0, 2)])
    with pytest.raises(ValueError, match="tekil"):
        degerlendir.eslestir(k, h)


# ---------------------------------------------------------------- ölçütler

def test_wape_elle():
    # t = [3, 1], g = [2, 2]; satır seviyesi (tarih): Σ|t-g| = 2, Σg = 4 -> wape 0.5, yanlılık 0
    e = _eslesik([("2025-01-08", "M001", S, "bos", 3.0, 3.0, 2),
                  ("2025-01-09", "M001", S, "bos", 1.0, 1.0, 2)])
    o = degerlendir.olcutler(e, ["tarih"])
    assert o["wape"] == pytest.approx(0.5) and o["yanlilik"] == pytest.approx(0.0)
    assert o["tahmin"] == pytest.approx(4.0) and o["karsilanmayan"] == pytest.approx(4.0)
    assert o["grup"] == 2
    # toplamda iki satır birbirini götürür: Σt = Σg = 4
    assert degerlendir.olcutler(e, [])["wape"] == pytest.approx(0.0)
    assert degerlendir.olcutler(e, [])["grup"] == 1
    # fazla tahmin: t = [3, 3], g = [2, 2] -> wape = yanlılık = 0.5 (her seviyede)
    e["kayip"] = [3.0, 3.0]
    for duzey in (["tarih"], []):
        o = degerlendir.olcutler(e, duzey)
        assert o["wape"] == pytest.approx(0.5) and o["yanlilik"] == pytest.approx(0.5)


def test_olcutler_once_toplar_sonra_fark_alir():
    # aynı hafta, iki gün: gün seviyesinde |3-1| + |1-3| = 4 / 4 = 1.0; haftada 0
    e = _eslesik([("2025-01-06", "M001", S, "bos", 3.0, 3.0, 1),
                  ("2025-01-07", "M001", S, "bos", 1.0, 1.0, 3),
                  ("2025-01-14", "M001", S, "bos", 2.0, 2.0, 1)])
    gun = degerlendir.olcutler(e, ["magaza_id", "option_id", "tarih"])
    hafta = degerlendir.olcutler(e, ["magaza_id", "option_id", "hafta"])
    assert gun["grup"] == 3 and hafta["grup"] == 2
    assert gun["wape"] == pytest.approx((2 + 2 + 1) / 5)
    assert hafta["wape"] == pytest.approx((0 + 1) / 5)          # hafta 1: 4 vs 4, hafta 2: 2 vs 1
    assert hafta["yanlilik"] == pytest.approx(1 / 5)
    assert "hafta" not in e.columns                              # türetme girdiyi değiştirmez
    assert degerlendir.olcutler(e, ["hafta"])["grup"] == 2


def test_olcutler_tahmin_sutunu_saf():
    e = _eslesik([("2025-01-08", "M001", S, "tukenen", 2.0, 1.0, 2),
                  ("2025-01-09", "M001", S, "tukenen", 1.0, 0.0, 2)])
    assert degerlendir.olcutler(e, [])["wape"] == pytest.approx(1 / 4)
    saf = degerlendir.olcutler(e, [], tahmin="kayip_saf")
    assert saf["wape"] == pytest.approx(3 / 4) and saf["yanlilik"] == pytest.approx(-3 / 4)


def test_olcutler_hakem_sifirsa_nan_ve_bos_girdi():
    e = _eslesik([("2025-01-08", "M001", S, "bos", 1.0, 1.0, 0)])
    assert np.isnan(degerlendir.olcutler(e, [])["wape"])
    bos = degerlendir.olcutler(e.iloc[0:0], ["magaza_id"])
    assert bos["grup"] == 0 and bos["tahmin"] == 0.0


# ---------------------------------------------------------------- ayrışım

def test_ayrisim_toplamlari():
    k = _kayip([("2025-01-08", "M001", S, "bos", 1.5, 1.5),
                ("2025-01-09", "M001", S, "tukenen", 2.5, 0.5),
                ("2025-01-10", "M001", S, "bos", 0.25, 0.25)])
    h = _hakem([("2025-01-08", "M001", S, 3, 1, 2), ("2025-01-09", "M001", S, 4, 4, 0),
                ("2025-01-20", "M001", S, 9, 9, 0)])          # son satır kayıp tablosunda yok
    a = degerlendir.ayrisim(degerlendir.eslestir(k, h))
    assert a == {"tahmin": pytest.approx(4.25), "kayip_saf": pytest.approx(2.25),
                 "karsilanmayan": 7, "ikameye_giden": 5, "kalici_kayip": 2}
    assert a["karsilanmayan"] == a["ikameye_giden"] + a["kalici_kayip"]


# -------------------------------------------------------------- kırılımlar

@pytest.fixture
def kir_con():
    """Üç option (iki sezonluk + bir devamlı), mağaza ve online satışı, teslim edilmiş ve edilmemiş sipariş."""
    t = oyuncak_tablolar()
    sablon = t["urun"].iloc[[0]]
    sat, sip = [], []
    satir = []
    # 20 sezonluk option (AW24), STR = 0.05 k (k = 1..20); 10 sezonluk (SS25), STR = 0.01 k;
    # bir devamlı (STR = 5); bir sezonluk teslimsiz; bir sezonluk teslimi olmayan satışsız
    opsiyonlar = ([(f"AWO{k:02d}", "AW24", 100, 5 * k) for k in range(1, 21)]
                  + [(f"SSO{k:02d}", "SS25", 100, k) for k in range(1, 11)]
                  + [("DEVO01", "DEVAMLI", 100, 500), ("TESO01", "AW24", 0, 900)])
    for o, sezon, teslim, satis in opsiyonlar:
        u = sablon.copy()
        u["urun_id"], u["option_id"], u["sezon_kodu"] = f"{o}-M", o, sezon
        u["line"] = "Premium" if o.startswith("SS") else "Basic"
        satir.append(u)
        if teslim:
            sip += [(f"{o}-1", "ilk", o, f"{o}-M", "T01", "2024-10-01", "2024-11-01", "2024-11-02", teslim * 6 // 10),
                    (f"{o}-2", "rpt", o, f"{o}-M", "T01", "2024-10-01", "2024-11-01", "2024-11-03", teslim * 4 // 10),
                    (f"{o}-3", "rpt", o, f"{o}-M", "T01", "2025-12-20", "2026-02-01", None, 10_000)]
        a, b = satis // 2, satis - satis // 2
        sat += [("2025-01-07", "M001", f"{o}-M", a, 0.0, 0.0, None),
                ("2025-01-08", "ONL", f"{o}-M", b, 0.0, 0.0, None)]
    t["urun"] = pd.concat([t["urun"]] + satir, ignore_index=True)
    ekle(t, "satis", sat)
    ekle(t, "siparis", sip)
    con = oyuncak_baglan(t)
    yield con
    con.close()


def test_hit_ust_ondalik(kir_con):
    et = degerlendir.hit_etiketleri(kir_con)
    aw = [o for o in et.index if o.startswith("AWO")]
    ss = [o for o in et.index if o.startswith("SSO")]
    # her sezon kendi içinde: 20 option'dan en üst 2, 10 option'dan en üst 1
    assert sorted(o for o in aw if et[o] == "hit") == ["AWO19", "AWO20"]
    assert sorted(o for o in ss if et[o] == "hit") == ["SSO10"]
    assert et["DEVO01"] == "diger"                  # devamlı, STR çok yüksek olsa da
    assert et["TESO01"] == "diger"                  # teslimi olmayan (STR tanımsız)
    assert et["MDL0001-SYH"] == "diger"             # sezonluk ama teslimi yok


def test_kirilimlar_hit_satirlari(kir_con):
    satirlar = [("2025-01-09", "M001", f"{o}-M", "bos", 1.0, 1.0, 2)
                for o in ("AWO20", "AWO19", "AWO05", "SSO10", "SSO01", "DEVO01")]
    k = degerlendir.kirilimlar(_eslesik(satirlar), kir_con).set_index(["kirilim", "deger"])
    assert k.loc[("hit", "hit"), "karsilanmayan"] == 6 and k.loc[("hit", "hit"), "grup"] == 3
    assert k.loc[("hit", "diger"), "karsilanmayan"] == 6 and k.loc[("hit", "diger"), "grup"] == 3
    assert k.loc[("hit", "hit"), "wape"] == pytest.approx(0.5)      # t = 1, g = 2
    assert k.loc[("hit", "hit"), "yanlilik"] == pytest.approx(-0.5)


def test_kirilimlar_sema_line_kanal_durum(kir_con):
    e = _eslesik([("2025-01-09", "M001", "AWO01-M", "bos", 1.0, 1.0, 2),
                  ("2025-01-09", "ONL", "AWO01-M", "tukenen", 3.0, 1.0, 1),
                  ("2025-01-09", "M001", "SSO01-M", "bos", 0.0, 0.0, 1)])
    k = degerlendir.kirilimlar(e, kir_con)
    assert list(k.columns) == ["kirilim", "deger", "wape", "yanlilik", "tahmin", "karsilanmayan", "grup"]
    assert set(k["kirilim"]) == set(degerlendir.KIRILIMLAR)
    kd = k.set_index(["kirilim", "deger"])
    assert kd.loc[("kanal", "magaza"), "karsilanmayan"] == 3 and kd.loc[("kanal", "online"), "karsilanmayan"] == 1
    assert kd.loc[("durum", "bos"), "grup"] == 2 and kd.loc[("durum", "tukenen"), "grup"] == 1
    assert ("durum", "stoklu") not in kd.index                      # gözlenmeyen kategori yok
    assert kd.loc[("line", "Premium"), "karsilanmayan"] == 1        # SSO01
    assert kd.loc[("line", "Basic"), "karsilanmayan"] == 3
    assert kd.loc[("durum", "tukenen"), "wape"] == pytest.approx(2.0)   # t = 3, g = 1
    # her kırılımda karşılanmayan toplamı aynı
    assert (k.groupby("kirilim")["karsilanmayan"].sum() == 4).all()


def test_sure_kisa_uzun_kosulari(kir_con):
    def gunler(m, u, gun_listesi):
        return [(f"2025-01-{g:02d}", m, u, "bos", 1.0, 1.0, 1) for g in gun_listesi]
    satirlar = (gunler("M001", "AWO01-M", [1, 2, 3])                 # 3 ardışık: kisa
                + gunler("M001", "AWO02-M", [1, 2, 3, 4])            # 4 ardışık: uzun
                + gunler("M001", "AWO03-M", [1, 2, 3, 5, 6])         # 3 + 2: ikisi de kisa
                + gunler("M001", "AWO04-M", [1, 2, 3, 4, 6])         # 4 uzun + 1 kisa
                + gunler("M002", "AWO01-M", [1, 2, 3, 4, 5]))        # aynı SKU, başka mağaza: uzun
    # satırları karıştır: sıra koşuyu etkilememeli
    satirlar = [satirlar[i] for i in np.random.default_rng(1).permutation(len(satirlar))]
    e = _eslesik(satirlar)
    etiket = degerlendir._sure_etiketi(e)
    cizelge = {(m, u, t.day): str(x) for m, u, t, x in
               zip(e["magaza_id"], e["urun_id"], e["tarih"], etiket)}
    assert {cizelge[("M001", "AWO01-M", g)] for g in (1, 2, 3)} == {"kisa"}
    assert {cizelge[("M001", "AWO02-M", g)] for g in (1, 2, 3, 4)} == {"uzun"}
    assert {cizelge[("M001", "AWO03-M", g)] for g in (1, 2, 3, 5, 6)} == {"kisa"}
    assert {cizelge[("M001", "AWO04-M", g)] for g in (1, 2, 3, 4)} == {"uzun"}
    assert cizelge[("M001", "AWO04-M", 6)] == "kisa"
    assert {cizelge[("M002", "AWO01-M", g)] for g in range(1, 6)} == {"uzun"}
    k = degerlendir.kirilimlar(e, kir_con).set_index(["kirilim", "deger"])
    assert k.loc[("sure", "kisa"), "karsilanmayan"] == 3 + 5 + 1
    assert k.loc[("sure", "uzun"), "karsilanmayan"] == 4 + 4 + 5


# --------------------------------------------------------------- çeşit dışı

def test_cesit_disi_ve_stoklu_gunde_karsilanmayan():
    uygun = _kayip([("2025-01-08", "M001", S, "bos", 0, 0), ("2025-01-09", "M001", S, "bos", 0, 0),
                    ("2025-01-10", "M001", S, "stoklu", 0, 0), ("2025-01-09", "M002", M, "bos", 0, 0)])
    kayip_keys = uygun[uygun["durum"] != "stoklu"]
    h = _hakem([("2025-01-08", "M001", S, 3, 0, 3),     # uygun, kayıp tablosunda
                ("2025-01-10", "M001", S, 2, 0, 2),     # uygun, stoklu gün: kayıp tablosunda yok
                ("2025-01-12", "M001", S, 4, 0, 4),     # uygun değil (gün)
                ("2025-01-09", "M003", L, 1, 0, 1)])    # uygun değil (hücre)
    c = degerlendir.cesit_disi(h, uygun, kayip_keys)
    assert c["toplam_adet"] == 10 and c["toplam_satir"] == 4
    assert c["disi_adet"] == 5 and c["disi_satir"] == 2
    assert c["disi_pay"] == pytest.approx(0.5) and c["disi_satir_pay"] == pytest.approx(0.5)
    assert c["stoklu_adet"] == 2 and c["stoklu_satir"] == 1 and c["stoklu_pay"] == pytest.approx(0.2)
    c2 = degerlendir.cesit_disi(h, uygun)
    assert "stoklu_adet" not in c2 and c2["disi_adet"] == 5


def test_cesit_disi_hicbiri_disarida_degil():
    uygun = _kayip([("2025-01-08", "M001", S, "bos", 0, 0)])
    h = _hakem([("2025-01-08", "M001", S, 3, 0, 3)])
    c = degerlendir.cesit_disi(h, uygun, uygun)
    assert c["disi_adet"] == 0 and c["disi_pay"] == 0.0 and c["stoklu_adet"] == 0


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_basit_bir_ay(v4_con):
    from perakende_analitik import carpanlar, kayip, ozellikler, talep
    from perakende_analitik import hakem
    if not (hakem.HAKEM_DIZINI / "karsilanmayan.parquet").exists():
        pytest.skip("hakem onbellegi yok (python -m perakende_analitik.hakem)")
    h = hakem.oku()["karsilanmayan"]
    bas, bit = date(2024, 12, 1), date(2025, 2, 28)
    g = pd.concat([stok.gunluk_magaza(v4_con, bas, bit), stok.gunluk_online(v4_con, bas, bit)],
                  ignore_index=True)
    g = ozellikler.ekle(v4_con, g)
    gozlem = g[g["durum"] == "stoklu"].reset_index(drop=True)
    hedef = g[(g["durum"] != "stoklu") & (g["tarih"] >= "2025-01-01") & (g["tarih"] <= "2025-01-31")]
    k = talep.Basit(carpanlar=carpanlar.ogren(gozlem))
    k.egit(gozlem)
    sutunlar = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis",
                "net_satis", "durum"]
    kd = kayip.kayip_yaz(hedef[sutunlar], k.tahmin(hedef))
    e = degerlendir.eslestir(kd, h)
    assert len(e) == len(kd)
    a = degerlendir.ayrisim(e)
    assert a["karsilanmayan"] == a["ikameye_giden"] + a["kalici_kayip"]
    for duzey in (["magaza_id", "option_id", "hafta"], ["hafta"], []):
        o = degerlendir.olcutler(e, duzey)
        assert np.isfinite(o["wape"]) and o["grup"] >= 1
    kl = degerlendir.kirilimlar(e, v4_con)
    assert set(kl["kirilim"]) == set(degerlendir.KIRILIMLAR)
    print(kl.to_string())
