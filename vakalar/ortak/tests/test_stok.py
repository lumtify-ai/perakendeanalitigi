"""stok.gunluk_magaza: günlük mağaza stoğunun pazartesi fotoğrafından yeniden kurulması."""

from datetime import date

import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import stok

SUTUNLAR = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis",
            "net_satis", "durum"]
M = "MDL0001-SYH-M"


def _gun(g: pd.DataFrame, magaza: str, urun: str) -> pd.DataFrame:
    """Bir hücrenin günlük satırları, tarih sırasıyla (tarih -> satır)."""
    h = g[(g["magaza_id"] == magaza) & (g["urun_id"] == urun)]
    return h.set_index("tarih").sort_index()


def _gunler(g: pd.DataFrame, magaza: str, urun: str) -> list[pd.Timestamp]:
    return list(_gun(g, magaza, urun).index)


def _ayni_hafta(gunler) -> list[pd.Timestamp]:
    return [pd.Timestamp(2025, 1, d) for d in gunler]


# ------------------------------------------------------------ ek senaryolar
# Temel senaryoya DOKUNULMAZ; yeni mağaza / SKU / tarihlerle eklenir (R2).
# Her senaryo kendi hücresinde; stok korunumu yalnız ilgili testin baktığı
# kuralı sınayacak kadar tutarlı kurulur.

def _urun_ekle(t, urun_id: str, lansman: str = "2024-11-04") -> None:
    yeni = t["urun"].iloc[[0]].copy()
    yeni["urun_id"] = urun_id
    yeni["option_id"] = urun_id.rsplit("-", 1)[0]
    yeni["lansman_tarihi"] = pd.to_datetime(lansman)
    t["urun"] = pd.concat([t["urun"], yeni], ignore_index=True)


def _magaza_ekle(t, magaza_id: str, acilis: str = "2015-01-01", kapanis=None) -> None:
    ekle(t, "magaza", [(magaza_id, f"Mağaza {magaza_id}", "Ankara", "İç Anadolu", 39.9, 32.8,
                        "Cadde", 300, 1, 4000, acilis, kapanis)])


def _stok(t, magaza: str, urun: str, **fotograflar) -> None:
    """fotograflar: p0106=3, p0113=1 ... (pazartesi -> adet; stoklu_gun önemsiz)."""
    ekle(t, "stok", [(f"2025-{k[1:3]}-{k[3:5]}", magaza, urun, n, 7)
                     for k, n in fotograflar.items()])


@pytest.fixture
def ek_con():
    t = oyuncak_tablolar()
    for m in ("M003",):
        _magaza_ekle(t, m)
    _magaza_ekle(t, "M004")   # tadilat 01-08 .. 01-10 (01-11 yeniden açık)
    ekle(t, "magaza_olay", [("M004", "tadilat", "2024-12-01", "2025-01-08", "2025-01-11")])
    _magaza_ekle(t, "M005", acilis="2025-01-08")   # 01-08'de açıldı
    _magaza_ekle(t, "M006", kapanis="2025-01-10")  # 01-10'da kapandı (01-10 kapalı)
    for u in ("MDL0002-SYH-S", "MDL0002-SYH-M", "MDL0002-SYH-L", "MDL0003-SYH-M",
              "MDL0003-SYH-L", "MDL0004-SYH-S"):
        _urun_ekle(t, u)
    _urun_ekle(t, "MDL0003-SYH-S", lansman="2025-01-09")

    # A) iade: M003 x MDL0002-SYH-S, pzt 2 adet, 01-07'de 2 satış + 1 iade
    _stok(t, "M003", "MDL0002-SYH-S", p0106=2, p0113=1)
    ekle(t, "satis", [("2025-01-07", "M003", "MDL0002-SYH-S", 2, 500.0, 0.0, None),
                      ("2025-01-07", "M003", "MDL0002-SYH-S", -1, -250.0, 0.0, None)])
    # B) kenar haftası: yalnız 01-13 ve 01-20 fotoğrafı (01-06 ve 01-27 yok)
    _stok(t, "M003", "MDL0002-SYH-M", p0113=3, p0120=3)
    # C) kapalı günler: aynı SKU, üç mağaza, hepsi 01-06 ve 01-13 fotoğraflı
    for m in ("M004", "M005", "M006"):
        _stok(t, m, "MDL0002-SYH-L", p0106=5, p0113=5)
    # D) lansman 01-09
    _stok(t, "M003", "MDL0003-SYH-S", p0106=5, p0113=5)
    # E) tek taraflı transfer: M003 -> M004, varış boş (hedefte hücre doğmaz)
    _stok(t, "M003", "MDL0003-SYH-M", p0106=1, p0113=0)
    ekle(t, "sevkiyat", [("2025-01-07", None, "M003", "M004", "MDL0003-SYH-M", 2, "transfer", None)])
    # F) hiç stoğu olmamış hücre: iki fotoğraf da 0, varış yok, satış yok
    _stok(t, "M003", "MDL0003-SYH-L", p0106=0, p0113=0)
    # G) F'nin karşıtı: fotoğraflar 0 ama pencerede varış (4) ve satış (4) var
    _stok(t, "M003", "MDL0004-SYH-S", p0106=0, p0113=0)
    ekle(t, "sevkiyat", [("2025-01-07", "2025-01-08", "DEPO", "M003", "MDL0004-SYH-S", 4,
                          "replenishment", None)])
    ekle(t, "satis", [("2025-01-09", "M003", "MDL0004-SYH-S", 4, 1000.0, 0.0, None)])
    con = oyuncak_baglan(t)
    yield con
    con.close()


@pytest.fixture
def ek(ek_con):
    return stok.gunluk_magaza(ek_con, date(2025, 1, 6), date(2025, 2, 2))


# ------------------------------------------------------------------ temel

def test_yeniden_kurma_elle(oyuncak_con):
    g = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 12)).set_index(
        ["tarih", "magaza_id", "urun_id"])
    # M001 × -M: pzt 3 adet; salı 2 satış; çarşamba 1 satış → perşembe boş; cuma 4 varış
    assert g.loc[(pd.Timestamp(2025, 1, 7), "M001", M), "satis_oncesi"] == 3
    assert g.loc[(pd.Timestamp(2025, 1, 8), "M001", M), "durum"] == "tukenen"
    assert g.loc[(pd.Timestamp(2025, 1, 9), "M001", M), "durum"] == "bos"
    assert g.loc[(pd.Timestamp(2025, 1, 10), "M001", M), "durum"] == "stoklu"


def test_yeniden_kurma_butun_hafta(oyuncak_con):
    g = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 12))
    h = _gun(g, "M001", M)
    assert list(h["satis_oncesi"]) == [3, 3, 1, 0, 4, 3, 3]
    # mükerrer satış satırı tek sayılır: salı brüt 2
    assert list(h["brut_satis"]) == [0, 2, 1, 0, 1, 0, 0]
    assert list(h["net_satis"]) == [0, 2, 1, 0, 1, 0, 0]
    assert list(h["durum"]) == ["stoklu", "stoklu", "tukenen", "bos", "stoklu", "stoklu", "stoklu"]
    assert list(h["option_id"].astype(str).unique()) == ["MDL0001-SYH"]


def test_sema(oyuncak_con):
    g = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 26))
    assert list(g.columns) == SUTUNLAR
    for s in ("magaza_id", "urun_id", "option_id", "durum"):
        assert isinstance(g[s].dtype, pd.CategoricalDtype), s
    for s in ("satis_oncesi", "brut_satis", "net_satis"):
        assert str(g[s].dtype) == "int32", s
    assert str(g["tarih"].dtype) == "datetime64[ns]"
    # tarih, magaza_id, urun_id sırası
    anahtar = list(zip(g["tarih"], g["magaza_id"].astype(str), g["urun_id"].astype(str)))
    assert anahtar == sorted(anahtar)
    assert set(g["durum"].astype(str)) <= {"stoklu", "tukenen", "bos"}


def test_online_ve_hayalet_yok(oyuncak_con):
    g = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 26))
    assert "ONL" not in set(g["magaza_id"].astype(str))
    assert _gunler(g, "M002", "MDL0001-SYH-L") == []   # hayalet: çeşit dışı
    assert len(g) == 5 * 21  # 5 hücre × 3 tam hafta


def test_pencere_yarim_hafta_ayni_degerler(oyuncak_con):
    tam = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 12))
    kis = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 8), date(2025, 1, 10))
    assert set(kis["tarih"]) == {pd.Timestamp(2025, 1, 8), pd.Timestamp(2025, 1, 9), pd.Timestamp(2025, 1, 10)}
    a = tam[tam["tarih"].isin(set(kis["tarih"]))].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, kis.reset_index(drop=True))


# ------------------------------------------------------- uygunluk ve kenarlar

def test_iade_satistan_sonra(ek):
    h = _gun(ek, "M003", "MDL0002-SYH-S")
    assert list(h.index) == _ayni_hafta(range(6, 13))
    # 01-07: 2 satış (brüt 2), 1 iade (net 1); iade aynı günün satis_oncesi'ne girmez
    assert h.loc[pd.Timestamp(2025, 1, 7), ["satis_oncesi", "brut_satis", "net_satis"]].tolist() == [2, 2, 1]
    assert h.loc[pd.Timestamp(2025, 1, 7), "durum"] == "tukenen"
    # ertesi gün raf stoğu 2 - 1 = 1, iade rafa döndü
    assert h.loc[pd.Timestamp(2025, 1, 8), "satis_oncesi"] == 1
    assert h.loc[pd.Timestamp(2025, 1, 8), "durum"] == "stoklu"


def test_kenar_haftasi_uygun_degil(ek):
    # ertesi pazartesi fotoğrafı (01-27) olmayan hafta (01-20..01-26) yok;
    # o haftanın hücreleri başka haftalarda var
    assert ek["tarih"].max() == pd.Timestamp(2025, 1, 26)
    # B hücresi: 01-06 fotoğrafı yok (hafta 1 yok), 01-13..01-19 tam, 01-20 haftasının
    # ertesi pazartesisi yok
    assert _gunler(ek, "M003", "MDL0002-SYH-M") == _ayni_hafta(range(13, 20))
    # temel hücre: üç tam hafta
    assert len(_gunler(ek, "M001", M)) == 21
    # 01-27 pazartesisinde başlayan hafta (ertesi fotoğraf yok): hiç satır yok
    assert not (ek["tarih"] >= pd.Timestamp(2025, 1, 27)).any()


def test_kapali_gun_uygun_degil(ek):
    # tadilat [01-08, 01-11): 01-08, 01-09, 01-10 yok; 01-11 yeniden açık
    assert _gunler(ek, "M004", "MDL0002-SYH-L") == _ayni_hafta([6, 7, 11, 12])
    # açılış 01-08: ondan önceki günler yok
    assert _gunler(ek, "M005", "MDL0002-SYH-L") == _ayni_hafta(range(8, 13))
    # kapanış 01-10: kapanış günü ve sonrası yok
    assert _gunler(ek, "M006", "MDL0002-SYH-L") == _ayni_hafta(range(6, 10))


def test_lansmandan_once_uygun_degil(ek):
    assert _gunler(ek, "M003", "MDL0003-SYH-S") == _ayni_hafta(range(9, 13))


def test_negatif_stok_bos_sayilir(ek):
    h = _gun(ek, "M003", "MDL0003-SYH-M")
    assert h.loc[pd.Timestamp(2025, 1, 6), "durum"] == "stoklu"
    # 01-07: 1 adet - 2 adet çıkış (varışı hiç gelmeyen tek taraflı transfer) = -1
    assert h.loc[pd.Timestamp(2025, 1, 7), "satis_oncesi"] == -1
    assert set(h.loc[pd.Timestamp(2025, 1, 7):, "durum"].astype(str)) == {"bos"}
    # hedefte (M004) hücre doğmaz
    assert _gunler(ek, "M004", "MDL0003-SYH-M") == []


def test_hic_stogu_olmamis_hucre_uygun_degil(ek):
    # fotoğrafların hepsi 0, varış yok, satış yok: ikmal edilmemiş ürün, stoksuzluk değil
    assert _gunler(ek, "M003", "MDL0003-SYH-L") == []
    # fotoğrafları 0 olsa da pencerede varış ve satış varsa hücre uygun
    h = _gun(ek, "M003", "MDL0004-SYH-S")
    assert list(h.index) == _ayni_hafta(range(6, 13))
    assert list(h["durum"].astype(str)) == [
        "bos", "bos", "stoklu", "tukenen", "bos", "bos", "bos"]
    assert list(h["satis_oncesi"]) == [0, 0, 4, 4, 0, 0, 0]


# --------------------------------------------------------------- gerçek veri

def eslesme_orani_2025(v4_con):
    """(uyan hücre-hafta, tam hücre-hafta): 2025'te yeniden kurulan stoklu gün
    sayısı ile ertesi pazartesinin `stoklu_gun`ü."""
    g = stok.gunluk_magaza(v4_con, date(2025, 1, 6), date(2025, 12, 28))
    v4_con.register("g_2025", g)
    try:
        uyan, toplam = v4_con.execute("""
            with h as (
                select magaza_id::varchar m, urun_id::varchar u,
                       date_trunc('week', tarih::date)::date p,
                       count(*) n, count(*) filter (where durum <> 'bos') sg
                from g_2025 group by 1, 2, 3 having count(*) = 7)
            select count(*) filter (where h.sg = s.stoklu_gun), count(*)
            from h join stok s on s.magaza_id::varchar = h.m and s.urun_id::varchar = h.u
                              and s.tarih::date = h.p + 7
        """).fetchone()
    finally:
        v4_con.unregister("g_2025")
    return uyan, toplam


@pytest.mark.veri
def test_gercek_v4_stoklu_gun_eslesir(v4_con):
    # 2025: yeniden kurulan stoklu gün sayısı = ertesi pazartesinin stoklu_gun'ü
    uyan, toplam = eslesme_orani_2025(v4_con)
    print(f"eslesme: {uyan:,} / {toplam:,} = {uyan / toplam:.6f}")
    assert toplam > 1_000_000
    assert uyan / toplam >= 0.9999
