"""Beden eğrisi (`egri`): ham pay, sansür düzeltmesi, daraltma, profil, yeni mağaza.

Oyuncak testleri `conftest`in 8 mağazalı fikstürünü kullanır (stok her hafta 7 gün dolu: ham ve
düzeltilmiş pay orada aynıdır). `veri` işaretli test yayımlanan v4 verisini ve hakemi ister.
"""

import numpy as np
import pandas as pd
import pytest
from conftest import KARAR, PAY, PROFIL, YENI, oyuncak_baglan

from beden_paket import egri, kaynak, sabitler

S = egri.SUTUNLAR


def _kapsam(tablolar, karar=KARAR):
    return kaynak.kapsam(tablolar, karar)


def _bire(df: pd.DataFrame) -> None:
    assert not df.isna().to_numpy().any()
    np.testing.assert_allclose(df.sum(axis=1).to_numpy(), 1.0, atol=1e-12)
    assert (df.to_numpy() >= 0).all()


# ---------------------------------------------------------------------------
# Ham ve düzeltilmiş pay
# ---------------------------------------------------------------------------


def test_paylar_bire_toplanir(tablolar):
    k = _kapsam(tablolar)
    h = egri.ham(tablolar, k, KARAR)
    d = egri.duzeltilmis(tablolar, k, KARAR)
    assert list(h.columns) == S and list(d.columns) == S
    assert list(h.index) == list(k["magaza_id"]) == list(d.index)
    _bire(h)
    _bire(d)
    z = egri.zincir(tablolar, KARAR)
    assert z.shape == (5,) and z.sum() == pytest.approx(1.0)
    e = egri.magaza_egrisi(tablolar, k, KARAR)
    _bire(e.magaza)
    assert list(e.magaza.index) == list(k["magaza_id"])


def test_ham_profil_payina_yakin(tablolar):
    """Oyuncakta satış profil payından üretilir; stok hep dolu olduğu için düzeltme ham'ı değiştirmez."""
    k = _kapsam(tablolar)
    h = egri.ham(tablolar, k, KARAR)
    d = egri.duzeltilmis(tablolar, k, KARAR)
    pd.testing.assert_frame_equal(h, d, atol=1e-12)
    for m in k["magaza_id"]:
        np.testing.assert_allclose(h.loc[m].to_numpy(), PAY[PROFIL[m]], atol=0.03)


def test_pencereler(tablolar):
    """Collection: lansman haftasından `EGRI_PENCERE_HAFTA` hafta; Basic/NOS: bütün geçmiş pencere;
    karar gününde lansmanı gelmemiş option ve tek bedenli set yok."""
    p = egri.option_pencereleri(tablolar["urun"], KARAR).set_index("option_id")
    assert set(p.index) == {"OPT-SS24-A", "OPT-SS24-B", "OPT-BAS"}
    assert p.at["OPT-SS24-A", "bas"] == pd.Timestamp("2024-02-12")
    assert p.at["OPT-SS24-A", "bit"] == pd.Timestamp("2024-02-12") + pd.Timedelta(weeks=8)
    assert p.at["OPT-BAS", "bas"] == pd.Timestamp("2023-02-06")       # 104 hafta önce
    assert p.at["OPT-BAS", "bit"] == pd.Timestamp("2025-02-03")       # karar haftasının pazartesisi
    yalniz = egri.option_pencereleri(tablolar["urun"], KARAR, hatlar=("Collection",))
    assert set(yalniz["option_id"]) == {"OPT-SS24-A", "OPT-SS24-B"}


def test_egri_karar_sonrasini_gormez(tablolar):
    k = _kapsam(tablolar)
    once = egri.magaza_egrisi(tablolar, k, KARAR)
    bozuk = {ad: df.copy() for ad, df in tablolar.items()}
    for ad in ("satis", "stok"):
        t = bozuk[ad]
        sonra = t["tarih"] >= KARAR
        assert sonra.any()
        t.loc[sonra, "adet"] = t.loc[sonra, "adet"] * 50 + 7
    t = bozuk["stok"]
    t.loc[t["tarih"] >= KARAR, "stoklu_gun"] = 1
    ek = bozuk["satis"].iloc[:40].copy()             # karar haftasında, karar gününde ve sonrasında yeni satır
    ek["tarih"] = [pd.Timestamp("2025-02-04"), KARAR, pd.Timestamp("2025-03-03"), pd.Timestamp("2025-06-02")] * 10
    ek["adet"] = 999
    bozuk["satis"] = pd.concat([bozuk["satis"], ek], ignore_index=True)
    sonra = egri.magaza_egrisi(bozuk, k, KARAR)
    pd.testing.assert_frame_equal(once.magaza, sonra.magaza)
    pd.testing.assert_series_equal(once.profil, sonra.profil)
    assert once.kaynak == sonra.kaynak and once.kappa == sonra.kappa
    np.testing.assert_array_equal(once.zincir, sonra.zincir)


def test_egri_sevkiyat_okumaz(tablolar):
    """Çalışma zamanı denetimi: tablo sözlüğünde sevkiyat yokken sonuç aynı (AST denetimi
    `test_sizinti.test_egri_sevkiyat_istemez`)."""
    k = _kapsam(tablolar)
    once = egri.magaza_egrisi(tablolar, k, KARAR)
    t = {ad: df for ad, df in tablolar.items() if ad != "sevkiyat"}
    sonra = egri.magaza_egrisi(t, k, KARAR)
    pd.testing.assert_frame_equal(once.magaza, sonra.magaza)
    assert once.kaynak == sonra.kaynak and once.kappa == sonra.kappa


def _sansurle(tablolar, magaza: str, beden_sira: int, gun: int, oran: float):
    """`magaza`nın `beden_sira` bedenli bütün SKU'larında stoklu günü `gun`e, satışı `oran`a indirir."""
    t = {ad: df.copy() for ad, df in tablolar.items()}
    sku = set(t["urun"].loc[t["urun"]["beden_sira"] == beden_sira, "urun_id"].astype(str))
    s = t["satis"]
    m = (s["magaza_id"] == magaza) & s["urun_id"].isin(sku)
    s.loc[m, "adet"] = np.round(s.loc[m, "adet"] * oran).astype("int32")
    st = t["stok"]
    st.loc[(st["magaza_id"] == magaza) & st["urun_id"].isin(sku), "stoklu_gun"] = gun
    return t


def test_duzeltme_sansuru_geri_alir(tablolar):
    """Büyüğe kayık S06'da 4. beden haftanın 2 gününde stokta: ham pay düşer, stoklu gün hızı
    gerçek paya (0,30) yakın kalır."""
    t = _sansurle(tablolar, "S06", 4, 2, 2 / 7)
    k = _kapsam(t)
    h = egri.ham(t, k, KARAR).loc["S06", "b4"]
    d = egri.duzeltilmis(t, k, KARAR).loc["S06", "b4"]
    gercek = PAY["buyuk"][3]
    assert h < gercek - 0.12                     # sansür ham payı belirgin düşürür
    assert abs(d - gercek) < 0.03                # düzeltme geri alır
    assert abs(d - gercek) < abs(h - gercek) / 5


def test_duzeltme_stoksuz_beden_zincirle_dolar(tablolar):
    """Stoklu günü sıfır olan beden zincir hızıyla doldurulur: S06'nın 5. bedeni hiç stokta değilse
    düzeltilmiş payı zincir payıdır (ham payı 0)."""
    t = _sansurle(tablolar, "S06", 5, 0, 0.0)
    k = _kapsam(t)
    z = egri.zincir(t, KARAR)
    assert egri.ham(t, k, KARAR).loc["S06", "b5"] == 0
    assert egri.duzeltilmis(t, k, KARAR).loc["S06", "b5"] == pytest.approx(z[4], abs=1e-12)


def test_duzeltme_az_stoklu_gun_oldugu_gibi(tablolar):
    """Penceredeki stoklu günü 1–2 olan hücrenin satışı olduğu gibi alınır (oran çok az günden)."""
    hucre = pd.DataFrame({"magaza_id": ["X"] * 5, "option_id": ["O"] * 5, "beden_sira": [1, 2, 3, 4, 5],
                          "s": [2, 4, 4, 2, 1], "f": [2, 14, 14, 14, 0], "L": [14] * 5})
    z = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
    talep = egri.hucre_talebi(hucre, z)
    np.testing.assert_allclose(talep[:4], [2, 4, 4, 2])
    assert talep[4] == pytest.approx(12 * 0.1 / 0.9)


# ---------------------------------------------------------------------------
# Daraltma
# ---------------------------------------------------------------------------


def test_daralt_az_ornek():
    e = pd.DataFrame([[0.5, 0.2, 0.1, 0.1, 0.1], [0.1, 0.1, 0.1, 0.2, 0.5], [np.nan] * 5],
                     index=pd.Index(["A", "B", "C"], name="magaza_id"), columns=S)
    n = pd.Series([10.0, 1e6, 0.0], index=e.index)
    oncul = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
    d = egri.daralt(e, n, oncul, kappa=100)
    _bire(d)
    w = 10 / 110
    np.testing.assert_allclose(d.loc["A"], w * e.loc["A"] + (1 - w) * oncul)    # az örnek öncüle yakın
    np.testing.assert_allclose(d.loc["B"], e.loc["B"], atol=1e-3)                # çok örnek kendisi
    np.testing.assert_allclose(d.loc["C"], oncul)                                # örneksiz: öncül
    o = pd.DataFrame([oncul, oncul[::-1], oncul], index=e.index, columns=S)    # mağaza başına öncül
    d2 = egri.daralt(e, n, o, kappa=0)
    np.testing.assert_allclose(d2.loc[["A", "B"]], e.loc[["A", "B"]])           # κ = 0: daraltma yok
    np.testing.assert_allclose(d2.loc["C"], oncul)
    with pytest.raises(ValueError):
        egri.daralt(e, n, oncul, kappa=-1)


def test_kappa_sec_hakemsiz(tablolar):
    """κ, SS24 karar anında öğrenilip SS24'ün gerçekleşen ilk hafta paylarına uyumla seçilir;
    tablo ızgaranın her değerini taşır, seçilen en küçük ortalama L1'dir."""
    k, tablo = egri.kappa_sec(tablolar, KARAR)
    assert list(tablo["kappa"]) == list(egri.KAPPA_IZGARASI)
    assert k == tablo.loc[tablo["l1"].idxmin(), "kappa"]
    assert (tablo["magaza"] == 7).all()                                          # S08 SS24'te yok
    with pytest.raises(ValueError):
        egri.kappa_sec(tablolar, sabitler.KAL_KARAR_GUNU)                    # hedef karar anında yok


# ---------------------------------------------------------------------------
# Profil, yeni mağaza
# ---------------------------------------------------------------------------


def test_profil_etiketi_sirali(tablolar):
    k = _kapsam(tablolar)
    d = egri.duzeltilmis(tablolar, k, KARAR)
    eski = k.loc[~k["yeni"], "magaza_id"]
    p = egri.profiller(d.loc[eski], k=3)
    assert p.to_dict() == {m: PROFIL[m] for m in eski}
    ortalama = {g: (d.loc[p.index[p == g]].to_numpy() @ np.arange(1, 6)).mean() for g in egri.PROFIL_ADLARI}
    assert ortalama["kucuk"] < ortalama["orta"] < ortalama["buyuk"]
    # satır sırasından bağımsız
    p2 = egri.profiller(d.loc[eski[::-1]], k=3)
    assert p2.loc[p.index].to_dict() == p.to_dict()
    p4 = egri.profiller(d.loc[eski], k=2)
    assert set(p4) == {"P1", "P2"}


def test_yeni_magaza_egri(tablolar):
    k = _kapsam(tablolar)
    e = egri.magaza_egrisi(tablolar, k, KARAR)
    assert e.kaynak[YENI] in ("profil", "zincir")
    assert {m: v for m, v in e.kaynak.items() if m != YENI} == {m: "magaza" for m in k["magaza_id"] if m != YENI}
    assert e.yeni_secim["secim"] == e.kaynak[YENI]
    assert set(e.yeni_secim) >= {"secim", "l1_profil", "l1_zincir", "isabet", "magaza"}
    assert e.profil[YENI] in egri.PROFIL_ADLARI
    assert e.n[YENI] > 0                                     # 9 haftalık Basic geçmişi
    _bire(e.magaza)
    # geçmişi hiç yoksa eğri öncülün kendisi
    t = {ad: df.copy() for ad, df in tablolar.items()}
    t["satis"] = t["satis"][(t["satis"]["magaza_id"] != YENI) | (t["satis"]["tarih"] >= KARAR)]
    t["stok"] = t["stok"][t["stok"]["magaza_id"] != YENI]
    k2 = _kapsam(t)
    e2 = egri.magaza_egrisi(t, k2, KARAR)
    assert e2.n[YENI] == 0
    oncul = (e2.profil_egrisi.loc[e2.yeni_atama[YENI]].to_numpy() if e2.kaynak[YENI] == "profil"
             else e2.zincir)
    np.testing.assert_allclose(e2.magaza.loc[YENI].to_numpy(), oncul, atol=1e-12)


def test_yeni_secim_kurali(tablolar):
    """Kural: bırakbirde statik atanmış profil eğrisi kendi eğrisine zincirden yakınsa profil."""
    k = _kapsam(tablolar)
    e = egri.magaza_egrisi(tablolar, k, KARAR)
    s = e.yeni_secim
    assert s["magaza"] == 7
    assert s["secim"] == ("profil" if s["l1_profil"] < s["l1_zincir"] else "zincir")


def test_egri_tablolari_oyuncak(tablolar):
    """DuckDB yükleyicisi: haftalık brüt satış (pazartesi), beş bedenli SKU'lar, karar öncesi;
    sonuç DataFrame'lerle kurulanla aynı eğri."""
    con = oyuncak_baglan(tablolar)
    t = egri.egri_tablolari(con, KARAR)
    assert set(t) == {"magaza", "magaza_olay", "urun", "satis", "stok"}
    assert (t["satis"]["tarih"] < KARAR).all() and (t["stok"]["tarih"] < KARAR).all()
    assert (t["satis"]["tarih"].dt.weekday == 0).all()
    k = _kapsam(tablolar)
    pd.testing.assert_frame_equal(egri.duzeltilmis(t, k, KARAR), egri.duzeltilmis(tablolar, k, KARAR))
    pd.testing.assert_frame_equal(egri.ham(t, k, KARAR), egri.ham(tablolar, k, KARAR))


# ---------------------------------------------------------------------------
# Gerçek veri
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ss25():
    con = kaynak.baglan()
    k = kaynak.kapsam(kaynak.kapsam_tablolari(con, sabitler.KARAR_GUNU), sabitler.KARAR_GUNU)
    t = egri.egri_tablolari(con, sabitler.KARAR_GUNU)
    return k, t, egri.magaza_egrisi(t, k, sabitler.KARAR_GUNU)


@pytest.mark.veri
def test_egri_ss25(ss25):
    k, t, e = ss25
    assert len(e.magaza) == 69 and list(e.magaza.index) == list(k["magaza_id"])
    _bire(e.magaza)
    assert not e.profil.isna().any() and set(e.profil) <= set(egri.PROFIL_ADLARI)
    assert {m for m, v in e.kaynak.items() if v != "magaza"} == {"M027", "M041"}
    assert e.n["M027"] == 0 and e.n["M041"] > 0
    # yükleyicinin satışı kapsamı aynı kurar (gecmis_hafta beş bedenli haftalık satıştan)
    pd.testing.assert_frame_equal(kaynak.kapsam(t, sabitler.KARAR_GUNU), k)
    print("\nprofil dağılımı:", e.profil.value_counts().to_dict(), "κ =", e.kappa,
          "yeni:", e.kaynak["M027"], e.kaynak["M041"], e.yeni_secim)


@pytest.mark.veri
def test_egri_ss25_hakem(ss25):
    """Hakemli ölçü (yalnız ölçüm): gerçek paya L1 (yeni olmayan mağazalarda); düzeltilmiş ve
    daraltılmış eğri zincirden iyi; profiller etkin kaymayı bulur."""
    from beden_paket import hakem, olcutler_egri

    k, t, e = ss25
    gercek = hakem.gercek_pay()
    eski = k.loc[~k["yeni"], "magaza_id"].tolist()
    d = {"ham": egri.ham(t, k, sabitler.KARAR_GUNU), "duzeltilmis": e.duzeltilmis, "daraltilmis": e.magaza,
         "profil": pd.DataFrame(e.profil_egrisi.loc[e.profil.loc[eski]].to_numpy(), index=eski, columns=S),
         "zincir": pd.DataFrame([e.zincir] * len(eski), index=eski, columns=S)}
    l1 = {ad: olcutler_egri.uzaklik(v.loc[eski], gercek).mean() for ad, v in d.items()}
    yeni = olcutler_egri.uzaklik(e.magaza.loc[["M027", "M041"]], gercek)
    ari = olcutler_egri.ari(e.profil.loc[eski], hakem.kayma())
    print("\nL1 (67 mağaza):", {a: round(v, 4) for a, v in l1.items()}, "yeni:", yeni.round(4).to_dict(),
          "ARI:", round(ari, 3))
    assert l1["daraltilmis"] < l1["zincir"] and l1["duzeltilmis"] < l1["ham"]
    assert ari > 0.9
