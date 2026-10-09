"""Karar anı Basit'i (`Basit(karar_ani=t)`) ve kapanmış sezonların çarpanları.

Karar anı `t` (karar pazartesisi) verildiğinde `t`'de ve sonrasındaki hiçbir
satır (satış, stok durumu, satırın varlığı) `t`'den önceki hücre-günlerin
kestirimini değiştirmemeli: havuz, komşu pencereleri, beden payı, göreli hız,
zincir ve son yedek, çarpanlar. `karar_ani=None` bugünkü Basit'tir.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from conftest import doldur, oyuncak_baglan, oyuncak_tablolar
from sentetik import birlestir, cerceve

from perakende_analitik import carpanlar, hazirlik, ozellikler, talep

BAS = pd.Timestamp("2023-01-02")   # pazartesi
T = BAS + pd.Timedelta(days=42)    # karar pazartesisi (2023-02-13)
SON = 84                           # gün sayısı (t'den sonra 6 hafta)
HF = {(k, g): (1.4 if g >= 5 else 0.84) * (1.1 if k == "online" else 1.0)
      for k in ("magaza", "online") for g in range(7)}


def _c() -> carpanlar.Carpanlar:
    return carpanlar.Carpanlar(hafta_gunu=HF, esneklik_kampanya={"*": 1.0})


def _dunya(tohum: int = 7) -> pd.DataFrame:
    """Dört mağaza (biri online) × dört option'ın SKU'ları, 84 gün; durum rastgele.

    Özel durumlar (kestirimin her yedeğini t'nin iki yanında sınar):
        M3 × X   t'den önce hiç stoklu değil, sonra stoklu (zincir yedeği)
        V        t'den önce hiçbir yerde stoklu değil, sonra M2'de (son yedek)
        M2 × Y-S t − 5 .. t + 9 boş: ±14 penceresi t'yi keser
        M1 × W   yalnız 0–10. günler stoklu, sonra t'den sonra yeniden (en yakın 28)
    """
    rng = np.random.default_rng(tohum)
    gun = np.arange(SON)
    tg = (T - BAS).days
    parcalar = []
    hucreler = [(m, u) for m in ("M1", "M2", "M3", "ONL")
                for u in ("X-S", "X-M", "X-L", "Y-S", "Y-M", "W-STD")]
    hucreler += [("M1", "V-STD"), ("M2", "V-STD")]
    for m, u in hucreler:
        durum = rng.choice(np.array(["stoklu", "bos", "tukenen"], dtype=object), size=SON,
                           p=[0.8, 0.1, 0.1])
        if (m, u[0]) == ("M3", "X"):
            durum = np.where(gun < tg, "bos", "stoklu").astype(object)
        if u == "V-STD":
            durum = np.where((gun >= tg) & (m == "M2"), "stoklu", "bos").astype(object)
        if (m, u) == ("M2", "Y-S"):
            durum[(gun >= tg - 5) & (gun < tg + 10)] = "bos"
        if (m, u) == ("M1", "W-STD"):
            durum = np.where((gun <= 10) | (gun >= tg + 3), "stoklu", "bos").astype(object)
        lam = (2.0 + 3.0 * (u[0] == "X") + (m == "ONL") * 4.0) * np.where(gun % 7 >= 5, 1.4, 0.84)
        lam = lam * np.where(gun >= tg, 1.8, 1.0)          # t'den sonra talep artar
        satis = np.where(durum == "bos", 0, rng.poisson(lam))
        parcalar.append(cerceve(BAS + pd.to_timedelta(gun, unit="D"), m, u, satis, durum=durum))
    return birlestir(*parcalar)


def _bozuk(df: pd.DataFrame, tohum: int = 11) -> pd.DataFrame:
    """t'de ve sonrasındaki satırları her yönden bozar; t'den önceki satırlar (indeksleriyle)
    aynı kalır. Satış ve durum değişir, satırların bir kısmı düşer, t'den sonra yeni
    mağaza ve yeni option satırları gelir (kategori evreni de değişir)."""
    rng = np.random.default_rng(tohum)
    b = df.copy()
    for k in ("magaza_id", "urun_id", "option_id", "durum"):
        b[k] = b[k].astype(object)
    sonra = (b["tarih"] >= T).to_numpy()
    n = int(sonra.sum())
    yeni_satis = (b.loc[sonra, "brut_satis"].to_numpy() * 3 + rng.integers(0, 9, n)).astype("int32")
    b.loc[sonra, "brut_satis"] = yeni_satis
    b.loc[sonra, "net_satis"] = yeni_satis
    b.loc[sonra, "satis_oncesi"] = yeni_satis + 2
    b.loc[sonra, "durum"] = rng.choice(np.array(["stoklu", "bos", "tukenen"], dtype=object), n,
                                       p=[0.5, 0.3, 0.2])
    b = b[~(sonra & (rng.random(len(b)) < 0.2))]          # bir kısmı yok olur
    gun = np.arange((T - BAS).days, SON)
    ek = [cerceve(BAS + pd.to_timedelta(gun, unit="D"), m, u, rng.poisson(40, len(gun)))
          for m, u in (("M9", "X-M"), ("M1", "Q-STD"), ("ONL", "Q-STD"), ("M3", "Y-S"))]
    return birlestir(b, *ek).set_axis([*b.index, *range(10**6, 10**6 + sum(map(len, ek)))])


def _kestir(df: pd.DataFrame, karar_ani=None, hedef: pd.DataFrame | None = None) -> pd.Series:
    k = talep.Basit(carpanlar=_c(), karar_ani=karar_ani)
    k.egit(df[df["durum"] == "stoklu"])
    return k.tahmin(df[df["tarih"] < T] if hedef is None else hedef)


# ------------------------------------------------------------------ Basit

def test_karar_ani_gelecegi_gormez():
    df = _dunya()
    bozuk = _bozuk(df)
    once = df[df["tarih"] < T]
    pd.testing.assert_frame_equal(bozuk.loc[once.index].astype(object), once.astype(object))

    a, b = _kestir(df, T.date()), _kestir(bozuk, T.date())
    assert len(a) == len(once) and np.isfinite(a.to_numpy()).all()
    pd.testing.assert_series_equal(a, b, check_exact=True)

    # aynı bozma karar anı olmadan t'den önceki kestirimi değiştirir (test güçlü)
    a0, b0 = _kestir(df), _kestir(bozuk)
    assert (np.abs(a0.to_numpy() - b0.to_numpy()) > 1e-9).sum() > 100
    assert (np.abs(a0.to_numpy() - a.to_numpy()) > 1e-9).sum() > 100


def test_karar_ani_her_yedekte_gelecegi_gormez():
    """Zincir yedeği, son yedek, t'yi kesen ±14 ve en yakın 28: dört hücre ayrı ayrı."""
    df = _dunya()
    bozuk = _bozuk(df)
    for m, u in (("M3", "X-M"), ("M1", "V-STD"), ("M2", "Y-S"), ("M1", "W-STD")):
        sec = (df["magaza_id"] == m) & (df["urun_id"] == u) & (df["tarih"] < T)
        h = df[sec]
        a = _kestir(df, T.date(), h)
        b = _kestir(bozuk, T.date(), bozuk.loc[h.index])
        pd.testing.assert_series_equal(a, b, check_exact=True)
        assert not np.allclose(_kestir(df, None, h), _kestir(bozuk, None, bozuk.loc[h.index]))


def test_karar_ani_komsulugu_t_den_once_keser():
    """t'den önce 2/gün, sonra 6/gün; t − 2 ve t − 1 boş. Karar anında yalnız geri
    bakılır (2); karar anı olmadan iki yan (4, `test_basit_iki_yana_bakar` gibi)."""
    tg = (T - BAS).days
    df = birlestir(cerceve(BAS + pd.to_timedelta(np.arange(tg - 2), unit="D"), "M1", "O-STD", 2),
                   cerceve(BAS + pd.to_timedelta([tg - 2, tg - 1], unit="D"), "M1", "O-STD", 0,
                           durum="bos"),
                   cerceve(BAS + pd.to_timedelta(np.arange(tg, tg + 30), unit="D"), "M1",
                           "O-STD", 6))
    hedef = df[df["tarih"] == T - pd.Timedelta(days=1)]
    k = talep.Basit(carpanlar=carpanlar.Carpanlar(), karar_ani=T.date())
    k.egit(df[df["durum"] == "stoklu"])
    assert k.tahmin(hedef).iloc[0] == pytest.approx(2.0)
    k0 = talep.Basit(carpanlar=carpanlar.Carpanlar())
    k0.egit(df[df["durum"] == "stoklu"])
    # ±14: önde 13 gün × 2 (t − 15 .. t − 3), arkada 14 gün × 6 (t .. t + 13)
    assert k0.tahmin(hedef).iloc[0] == pytest.approx((13 * 2 + 14 * 6) / 27)


def test_karar_ani_yoksa_eski_davranis():
    """`karar_ani=None` ile verinin sonundan sonraki bir karar anı aynı sonucu verir;
    ikisi de bugünkü Basit'tir (bütün satırlar, t'den sonrakiler dahil)."""
    df = _dunya()
    hedef = df[df["durum"] != "stoklu"]
    eski = talep.Basit(carpanlar=_c())
    eski.egit(df[df["durum"] == "stoklu"])
    beklenen = eski.tahmin(hedef)
    for t in (None, (BAS + pd.Timedelta(days=SON)).date()):
        pd.testing.assert_series_equal(_kestir(df, t, hedef), beklenen, check_exact=True)


def test_karar_ani_hedef_t_ve_sonrasi_hata():
    df = _dunya()
    k = talep.Basit(carpanlar=_c(), karar_ani=T.date())
    k.egit(df[df["durum"] == "stoklu"])
    with pytest.raises(ValueError, match="karar_ani"):
        k.tahmin(df[df["tarih"] <= T])
    k.tahmin(df[df["tarih"] < T])              # t − 1'e dek sorun yok


def test_karar_ani_timestamp_kabul_eder():
    df = _dunya()
    pd.testing.assert_series_equal(_kestir(df, T), _kestir(df, T.date()), check_exact=True)


# ------------------------------------------------------------- çarpanlar

W0 = pd.Timestamp("2024-01-01")    # günlük tablonun ilk günü (pazartesi)
WSON = pd.Timestamp("2024-06-30")
TK = date(2024, 5, 6)              # karar anı: S1 kapandı, S2 açık
# sezon -> (lansman, çıkış); S0 pencerenin başında yarım (W0'dan önce lanse)
SEZONLAR = {"S0": ("2023-11-06", "2024-02-05"), "S1": ("2024-01-08", "2024-04-01"),
            "S2": ("2024-03-04", "2024-06-03")}
URUNLER = {"S0": "A", "S1": "B", "S2": "C", "DEVAMLI": "D"}


def _carpan_tablolari():
    t = oyuncak_tablolar()
    urun = []
    for sezon, harf in URUNLER.items():
        lansman, cikis = SEZONLAR.get(sezon, ("2022-01-03", None))
        for beden, sira in (("S", 2), ("M", 3)):
            urun.append((f"{harf}01-SYH-{beden}", f"{harf}01-SYH", f"{harf}01", "Gömlek",
                         f"{harf} {beden}", "Lumoda", "Erkek", "Üst Giyim", "Gömlek",
                         "Basic" if sezon == "DEVAMLI" else "Collection", sezon,
                         0 if sezon == "DEVAMLI" else 1, "Siyah", "SYH", "Erkek Harf", beden,
                         sira, "pamuk", "regular", "düz", "klasik yaka", "yaka", "orta", 100.0,
                         250.0, lansman, cikis, "T01"))
    t["urun"] = doldur("urun", urun)
    t["sezon"] = doldur("sezon", [(s, 1, l, c, c) for s, (l, c) in SEZONLAR.items()])
    return t


def _gunluk(t, yol, bozan=None, tohum: int = 5) -> pd.DataFrame:
    """Uygun günler (lansman <= d < çıkış, pencere içinde), M001 ve ONL; satış hafta sonu
    yüksek, yaşla değişir. `bozan(df)` satırları yazmadan önce değiştirir."""
    rng = np.random.default_rng(tohum)
    parcalar = []
    for r in t["urun"].itertuples():
        bas = max(r.lansman_tarihi, W0)
        bit = WSON if pd.isna(r.cikis_tarihi) else min(r.cikis_tarihi - pd.Timedelta(days=1), WSON)
        gunler = pd.date_range(bas, bit, freq="D")
        for m in ("M001", "ONL"):
            hs = np.where(gunler.dayofweek >= 5, 1.5, 1.0)
            yas = (gunler - r.lansman_tarihi).days.to_numpy()
            lam = (6.0 if m == "ONL" else 3.0) * hs * (1.0 + 0.5 * np.exp(-yas / 30.0))
            durum = rng.choice(np.array(["stoklu", "bos", "tukenen"], dtype=object),
                               len(gunler), p=[0.85, 0.1, 0.05])
            satis = np.where(durum == "bos", 0, rng.poisson(lam)).astype("int32")
            parcalar.append(pd.DataFrame({
                "tarih": gunler.astype("datetime64[ns]"), "magaza_id": m, "urun_id": r.urun_id,
                "option_id": r.option_id, "satis_oncesi": satis + 1, "brut_satis": satis,
                "net_satis": satis, "durum": durum}))
    df = pd.concat(parcalar, ignore_index=True).sort_values(
        ["tarih", "magaza_id", "urun_id"], kind="stable", ignore_index=True)
    if bozan is not None:
        df = bozan(df)
    for k in ("magaza_id", "urun_id", "option_id", "durum"):
        df[k] = df[k].astype("category")
    df[hazirlik.GUNLUK_SUTUNLARI].to_parquet(yol, index=False)
    return df


def _ayni(a: carpanlar.Carpanlar, b: carpanlar.Carpanlar) -> bool:
    for alan in ("hafta_gunu", "ozel_gun", "esneklik_kampanya", "esneklik_markdown"):
        if getattr(a, alan) != getattr(b, alan):
            return False
    for alan in ("yasam", "beden_payi"):
        x, y = getattr(a, alan), getattr(b, alan)
        if not (x.shape == y.shape and x.reset_index(drop=True).equals(y.reset_index(drop=True))):
            return False
    return True


def _sezon(df: pd.DataFrame) -> pd.Series:
    harf = {v: k for k, v in URUNLER.items()}
    return df["urun_id"].astype(str).str[0].map(harf)


@pytest.mark.filterwarnings("ignore:Mean of empty slice:RuntimeWarning")
def test_carpanlar_kapanmis_sezonlardan(tmp_path):
    """Kapanmış (çıkışı < t) ve pencereye bütünüyle giren sezonların stoklu günleri;
    devamlı ürünler bu sezonların aralığında. Açık sezonun, yarım sezonun, aralık
    dışındaki devamlı günlerin ve t'den sonraki her satırın değişmesi çarpanları
    değiştirmez; kapanmış sezonun satırları değiştirir."""
    t = _carpan_tablolari()
    con = oyuncak_baglan(t)
    tk = pd.Timestamp(TK)
    s1_bas, s1_cikis = (pd.Timestamp(x) for x in SEZONLAR["S1"])
    df = _gunluk(t, tmp_path / "g.parquet")
    c = hazirlik.carpanlar_kapanmis(con, tmp_path / "g.parquet", TK)

    # beklenen: tanımın kendisiyle elle seçilen satırlardan `ogren`
    sz = _sezon(df)
    sec = ((df["durum"] == "stoklu") & (df["tarih"] < tk)
           & ((sz == "S1") | ((sz == "DEVAMLI") & (df["tarih"] >= s1_bas)
                              & (df["tarih"] < s1_cikis))))
    g = pd.read_parquet(tmp_path / "g.parquet")
    beklenen = carpanlar.ogren(ozellikler.ekle(
        con, g[sec.to_numpy()][["tarih", "magaza_id", "urun_id", "option_id", "brut_satis",
                                "durum"]], hazirlik.CARPAN_OZELLIKLERI))
    assert _ayni(c, beklenen)
    assert c.hafta_gunu and not c.yasam.empty

    def disari(d):
        d = d.copy()
        s = _sezon(d)
        oyun = ((s.isin(["S0", "S2"]))
                | ((s == "DEVAMLI") & ((d["tarih"] < s1_bas) | (d["tarih"] >= s1_cikis)))
                | (d["tarih"] >= tk))
        d.loc[oyun, "brut_satis"] = d.loc[oyun, "brut_satis"] * 5 + 3
        d.loc[oyun & (d["durum"] == "bos"), "durum"] = "stoklu"
        return d

    _gunluk(t, tmp_path / "d.parquet", disari)
    assert _ayni(hazirlik.carpanlar_kapanmis(con, tmp_path / "d.parquet", TK), c)

    def iceri(d):
        d = d.copy()
        s = (_sezon(d) == "S1") & (d["tarih"].dt.dayofweek == 2)
        d.loc[s, "brut_satis"] = d.loc[s, "brut_satis"] * 3 + 4
        return d

    _gunluk(t, tmp_path / "i.parquet", iceri)
    assert not _ayni(hazirlik.carpanlar_kapanmis(con, tmp_path / "i.parquet", TK), c)
    con.close()


def test_carpanlar_kapanmis_sezon_yoksa_hata(tmp_path):
    t = _carpan_tablolari()
    con = oyuncak_baglan(t)
    _gunluk(t, tmp_path / "g.parquet")
    with pytest.raises(ValueError, match="kapanmış sezon"):
        hazirlik.carpanlar_kapanmis(con, tmp_path / "g.parquet", date(2024, 3, 1))
    con.close()
