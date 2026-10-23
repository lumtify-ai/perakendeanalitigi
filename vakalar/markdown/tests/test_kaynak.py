"""`markdown.kaynak`: bağlantı, tablo okuma (gizli tablo reddi, `bitis` kesimi), test option'ları
ve karar penceresi.

Oyuncak testleri `conftest`in 6 mağaza + ONL fikstürünü kullanır; `veri` işaretli testler yayımlanan
v4 verisini ve dünyayı (`allocation.motor.dunya`, yalnız bu test dosyasında) ister.
"""

import numpy as np
import pandas as pd
import pytest
from conftest import (GUN_SIFIRI, KAMPANYA_HAFTASI, SATIS_BITIS, SEZON_DONEMI, SIPARIS_TARIHLERI,
                      gun_indisi, oyuncak_optionlar)

from markdown import kaynak, sabitler


def _gun(tarih) -> int:
    return gun_indisi(tarih)


# ------------------------------------------------------------------ tablo okuma


@pytest.mark.parametrize("ad", ["gizli_magaza", "gizli_talep", "gizli_tedarikci"])
def test_gizli_tablo_reddedilir(con, ad):
    with pytest.raises(ValueError, match="gizli"):
        kaynak.yayimlanan_tablolar(con, (ad,))
    with pytest.raises(ValueError, match="gizli"):
        kaynak.yayimlanan_tablolar(con, ("magaza", ad))


@pytest.mark.parametrize("ad", ["magaza; drop table satis", "Magaza", "satis where 1=1", "",
                                "satis\n"])
def test_gecersiz_tablo_adi_reddedilir(con, ad):
    with pytest.raises(ValueError, match="geçersiz"):
        kaynak.yayimlanan_tablolar(con, (ad,))


def test_tablolar_adlar_sirasiyla(con, tablolar):
    t = kaynak.yayimlanan_tablolar(con, ("fiyat", "magaza"))
    assert list(t) == ["fiyat", "magaza"]
    assert len(t["fiyat"]) == len(tablolar["fiyat"]) and len(t["magaza"]) == 7


def test_bitis_yoksa_kesim_yok(con, tablolar):
    t = kaynak.yayimlanan_tablolar(con, ("satis", "siparis"))
    assert len(t["satis"]) == len(tablolar["satis"])
    assert t["satis"]["tarih"].max() == SATIS_BITIS


def test_bitis_gozlenen_tablolari_keser(con):
    bitis = pd.Timestamp("2025-01-13")
    t = kaynak.yayimlanan_tablolar(
        con, ("satis", "stok", "depo_stok", "fiyat", "siparis"), bitis=bitis)
    for ad, sutun in (("satis", "tarih"), ("stok", "tarih"), ("depo_stok", "tarih"),
                      ("fiyat", "hafta_baslangic"), ("siparis", "siparis_tarihi")):
        assert len(t[ad]) > 0
        assert t[ad][sutun].max() < bitis, ad
    # kesim yalnız sonrasını atar: öncesi tam
    tam = kaynak.yayimlanan_tablolar(con, ("satis",))["satis"]
    assert len(t["satis"]) == int((tam["tarih"] < bitis).sum())
    assert KAMPANYA_HAFTASI not in set(t["satis"]["tarih"])    # bitis günü dahil değil


def test_bitis_siparisin_gelecek_teslimini_gizler(con):
    """Bitişten önce verilmiş ama bitişten sonra teslim edilen siparişin gerçekleşen teslimi
    karar anında bilinemez: boşaltılır; planlanan teslim (açık plan) kalır."""
    bitis = pd.Timestamp("2025-02-01")
    s = kaynak.yayimlanan_tablolar(con, ("siparis",), bitis=bitis)["siparis"]
    assert list(s["siparis_tarihi"]) == [pd.Timestamp(SIPARIS_TARIHLERI[0])]
    assert s["gerceklesen_teslim"].isna().all()
    assert s["planlanan_teslim"].notna().all()
    tam = kaynak.yayimlanan_tablolar(con, ("siparis",))["siparis"]
    assert tam["gerceklesen_teslim"].notna().all()


def test_bitis_takvim_gibi_ileriye_donuk_tablolara_dokunmaz(con, tablolar):
    """Kampanya takvimi, sezon takvimi ve takvim açık bilgidir (kararlar bunları ileri okur)."""
    t = kaynak.yayimlanan_tablolar(con, ("kampanya", "sezon", "takvim", "magaza", "urun"),
                                   bitis=pd.Timestamp("2024-09-01"))
    for ad in t:
        assert len(t[ad]) == len(tablolar[ad]), ad


def test_bitis_magaza_olayi_karar_tarihine_gore_keser(con):
    """Karar bitişten önce alındıysa olay tarihi bitişten sonra olsa da satır bilinir."""
    t = kaynak.yayimlanan_tablolar(con, ("magaza_olay",), bitis="2025-01-01")["magaza_olay"]
    assert list(t["magaza_id"]) == ["S6"]                 # olay_tarihi 2025-02-03 > bitis, karar 2024-12-02
    t = kaynak.yayimlanan_tablolar(con, ("magaza_olay",), bitis="2024-12-02")["magaza_olay"]
    assert len(t) == 0                                    # bitis günü dahil değil
    assert len(kaynak.yayimlanan_tablolar(con, ("magaza_olay",))["magaza_olay"]) == 2


def test_bitis_ile_siniflandirilmamis_tablo_hata_verir(con):
    con.execute("create table yeni_tablo as select 1 as x")
    with pytest.raises(ValueError, match="kesimi tanımsız"):
        kaynak.yayimlanan_tablolar(con, ("magaza", "yeni_tablo"), bitis="2025-01-01")
    # bitis yoksa sorun yok
    assert len(kaynak.yayimlanan_tablolar(con, ("yeni_tablo",))["yeni_tablo"]) == 1


def test_her_gercek_tablo_siniflandirilmis():
    """Yayımlanan v4'ün her tablosu kesilen ya da açık listede olmalı (veri gerektirmez: sabit liste)."""
    gercek = {"depo_stok", "fiyat", "kalite_kontrol", "kampanya", "magaza", "magaza_olay",
              "magaza_plan", "mfp_plan", "paket", "range_plan", "satis", "sevkiyat", "sezon",
              "siparis", "stok", "takvim", "tedarikci", "urun"}
    assert gercek == set(kaynak.DONEM_SUTUNLARI) | kaynak.ACIK_TABLOLAR
    assert not set(kaynak.DONEM_SUTUNLARI) & kaynak.ACIK_TABLOLAR


def test_bitis_tarih_dizgesi_kabul(con):
    a = kaynak.yayimlanan_tablolar(con, ("fiyat",), bitis="2025-01-06")["fiyat"]
    b = kaynak.yayimlanan_tablolar(con, ("fiyat",), bitis=pd.Timestamp("2025-01-06"))["fiyat"]
    assert len(a) == len(b) > 0


# ------------------------------------------------------------------ test option'ları


def test_test_optionlari_oyuncak(optionlar):
    idx = kaynak.test_optionlari(optionlar, sabitler.TEST_SEZONLARI)
    assert idx.dtype.kind == "i" and list(idx) == sorted(idx)
    assert len(idx) == 12
    assert set(optionlar.iloc[idx]["sezon_kodu"]) == {"AW24", "SS25"}
    assert (optionlar.iloc[idx]["line"] == "Collection").all()
    assert "Basic" not in set(optionlar.iloc[idx]["line"])


def test_test_optionlari_tek_sezon(optionlar):
    for sezon in ("AW24", "SS25"):
        idx = kaynak.test_optionlari(optionlar, (sezon,))
        assert len(idx) == 6
        assert set(optionlar.iloc[idx]["sezon_kodu"]) == {sezon}
    assert len(kaynak.test_optionlari(optionlar, ("SS25",))) == len(kaynak.test_optionlari(optionlar, "SS25"))
    assert len(kaynak.test_optionlari(optionlar, ())) == 0


def test_test_optionlari_konumsal_indis(optionlar):
    """İndis, `optionlar`ın satır konumudur (dünyada option indisi); etiket değil."""
    karisik = optionlar.iloc[::-1].reset_index(drop=True)
    idx = kaynak.test_optionlari(karisik, ("SS25",))
    assert set(karisik.iloc[idx]["option_id"]) == {f"SS25-{h}" for h in "abcdef"}


def test_kalibrasyon_sezonlari_oyuncakta_yok(optionlar):
    assert kaynak.test_optionlari(optionlar, sabitler.KAL_SEZONLARI).size == 0


# ------------------------------------------------------------------ karar penceresi


def _pencere(optionlar, sezon, kol):
    idx = kaynak.test_optionlari(optionlar, (sezon,))
    return optionlar.iloc[idx].reset_index(drop=True), kaynak.karar_penceresi(optionlar, idx, kol)


def test_karar_penceresi_oyuncak_serbest(optionlar):
    """SS25: indirim 2025-06-30; -56 gün = 2025-05-05 (pazartesi). Dalga 1 ve 2: 05-05; dalga 3:
    lansman 04-21 + 42 = 06-02 daha geç."""
    o, p = _pencere(optionlar, "SS25", "serbest")
    assert p.dtype.kind == "i" and len(p) == 6
    by = dict(zip(o["option_id"], p))
    for harf in "abcd":
        assert by[f"SS25-{harf}"] == _gun("2025-05-05"), harf
    for harf in "ef":
        assert by[f"SS25-{harf}"] == _gun("2025-04-21") + sabitler.RPT_SON_GUN == _gun("2025-06-02")


def test_karar_penceresi_oyuncak_takvim(optionlar):
    for sezon in ("AW24", "SS25"):
        o, p = _pencere(optionlar, sezon, "takvim")
        assert (p == o["indirim_gun"].to_numpy()).all()
        assert (p == _gun(SEZON_DONEMI[sezon][0])).all()
    # takvim kolu pazartesiye yuvarlanmaz: AW24 indirimi perşembe
    assert pd.Timestamp(SEZON_DONEMI["AW24"][0]).weekday() == 3


def test_karar_penceresi_aw24_pazartesiye_yukari(optionlar):
    """AW24: indirim 2025-01-02 (perşembe); -56 gün 2024-11-07 (perşembe) -> ilk pazartesi
    2024-11-11. Dalga 3: lansman 10-28 + 42 = 12-09 daha geç."""
    o, p = _pencere(optionlar, "AW24", "serbest")
    by = dict(zip(o["option_id"], p))
    for harf in "abcd":
        assert by[f"AW24-{harf}"] == _gun("2024-11-11")
    for harf in "ef":
        assert by[f"AW24-{harf}"] == _gun("2024-12-09")
    assert (p % 7 == 0).all()                       # gün 0 pazartesi: pazartesi <=> gün % 7 == 0


def test_serbest_pencere_pazartesisidir_ve_asla_erken_degil():
    """Hesaplanan gün pazartesiyse aynen kalır, değilse ileri (geriye değil) yuvarlanır; indirim
    gününü haftanın her gününe kaydırarak sınanır."""
    o = oyuncak_optionlar()
    idx = kaynak.test_optionlari(o, sabitler.TEST_SEZONLARI)
    for kayma in range(7):
        k = o.copy()
        k["indirim_gun"] = k["indirim_gun"] + kayma
        p = kaynak.karar_penceresi(k, idx, "serbest")
        h = np.maximum(k["indirim_gun"].to_numpy()[idx] - sabitler.ERKEN_GUN,
                       k["lansman_gun"].to_numpy()[idx] + sabitler.RPT_SON_GUN)
        assert (p % 7 == 0).all()
        assert ((p - h) >= 0).all() and ((p - h) < 7).all()
        assert ((p == h) == (h % 7 == 0)).all()


def test_karar_penceresi_gecersiz_girdi(optionlar):
    idx = kaynak.test_optionlari(optionlar, ("SS25",))
    with pytest.raises(ValueError, match="kol"):
        kaynak.karar_penceresi(optionlar, idx, "tepkili")
    sezonsuz = np.flatnonzero(~optionlar["sezonluk"].to_numpy())
    assert len(sezonsuz) == 1
    for kol in ("serbest", "takvim"):
        with pytest.raises(ValueError, match="sezonluk"):
            kaynak.karar_penceresi(optionlar, sezonsuz, kol)


def test_karar_penceresi_bos_indis(optionlar):
    p = kaynak.karar_penceresi(optionlar, np.array([], dtype=int), "serbest")
    assert p.shape == (0,)


def test_ogrenme_bitisi_en_erken_karar_pazartesisi(optionlar):
    """`OGRENME_BITIS[sezon]` test sezonunun en erken serbest karar günüdür (spec §3.1)."""
    for sezon, tarih in sabitler.OGRENME_BITIS.items():
        _, p = _pencere(optionlar, sezon, "serbest")
        assert p.min() == _gun(tarih)
        assert pd.Timestamp(tarih).weekday() == 0


def test_gun_sifiri_pazartesi():
    assert GUN_SIFIRI.weekday() == 0 and sabitler.GUN_SIFIRI == str(GUN_SIFIRI.date())


# ------------------------------------------------------------------ gerçek veri


@pytest.fixture(scope="module")
def dunya_optionlari():
    from allocation import motor            # ölçüm modülü: yalnız test, karar kodu değil
    return motor.dunya("tam").optionlar


@pytest.mark.veri
def test_test_optionlari_veri(dunya_optionlari):
    idx = kaynak.test_optionlari(dunya_optionlari, sabitler.TEST_SEZONLARI)
    assert len(idx) == 420
    for sezon in sabitler.TEST_SEZONLARI:
        assert len(kaynak.test_optionlari(dunya_optionlari, (sezon,))) == 210
    assert (dunya_optionlari.iloc[idx]["sezonluk"]).all()
    assert (dunya_optionlari.iloc[idx]["line"] == sabitler.LINE).all()
    assert len(kaynak.test_optionlari(dunya_optionlari, sabitler.KAL_SEZONLARI)) > 0


@pytest.mark.veri
def test_karar_penceresi(dunya_optionlari):
    o = dunya_optionlari
    ss = kaynak.test_optionlari(o, ("SS25",))
    p = kaynak.karar_penceresi(o, ss, "serbest")
    d = o.iloc[ss]["dalga"].to_numpy()
    assert (p[d == 1] == _gun("2025-05-05")).all()          # SS25 dalga 1
    assert (p[d == 2] == _gun("2025-05-05")).all()
    assert (p[d == 3] == o.iloc[ss]["lansman_gun"].to_numpy()[d == 3] + sabitler.RPT_SON_GUN).all()
    assert (p[d == 3] == _gun("2025-06-02")).all()
    assert (p % 7 == 0).all() and p.min() == _gun(sabitler.OGRENME_BITIS["SS25"])
    aw = kaynak.test_optionlari(o, ("AW24",))
    assert (kaynak.karar_penceresi(o, aw, "takvim") == _gun("2025-01-02")).all()   # AW24 takvim
    assert kaynak.karar_penceresi(o, aw, "serbest").min() == _gun(sabitler.OGRENME_BITIS["AW24"])
    assert (kaynak.karar_penceresi(o, ss, "serbest") <= kaynak.karar_penceresi(o, ss, "takvim")).all()


@pytest.mark.veri
def test_yayimlanan_tablolar_veri_bitis():
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("fiyat", "kalite_kontrol"), bitis="2024-11-11")
        assert t["fiyat"]["hafta_baslangic"].max() < pd.Timestamp("2024-11-11")
        assert t["kalite_kontrol"]["teslim_tarihi"].max() < pd.Timestamp("2024-11-11")
        with pytest.raises(ValueError, match="gizli"):
            kaynak.yayimlanan_tablolar(con, ("gizli_magaza",))
    finally:
        con.close()


@pytest.mark.veri
def test_gercek_veri_tablolari_siniflandirilmis():
    """Gerçek v4'ün her tablosu `DONEM_SUTUNLARI` ya da `ACIK_TABLOLAR`'dadır."""
    con = kaynak.baglan()
    try:
        adlar = {t for (t,) in con.execute("show tables").fetchall()}
    finally:
        con.close()
    assert adlar == set(kaynak.DONEM_SUTUNLARI) | kaynak.ACIK_TABLOLAR
