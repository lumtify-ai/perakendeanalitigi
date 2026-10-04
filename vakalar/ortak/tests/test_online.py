"""stok.gunluk_online: merkez depodan satılan çevrimiçi günlük stok."""

from datetime import date

import pandas as pd
import pytest
from conftest import ekle, oyuncak_baglan, oyuncak_tablolar

from perakende_analitik import stok

SUTUNLAR = ["tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis",
            "net_satis", "durum"]

A = "MDL0005-SYH-M"   # oyuncak senaryosu: depo 2 -> 2 online satış (mükerrer satır) -> tukenen
B = "MDL0006-SYH-M"   # pencerenin son günü: ileri kurulum
C = "MDL0007-SYH-M"   # lansman 01-09, çıkış 01-12
D = "MDL0008-SYH-M"   # hiç depo_stok satırı yok
E = "MDL0009-SYH-M"   # online iade


def _gun(g: pd.DataFrame, urun: str) -> pd.DataFrame:
    return g[g["urun_id"] == urun].set_index("tarih").sort_index()


def _t(ay_gun: str) -> pd.Timestamp:
    return pd.Timestamp(f"2025-{ay_gun}")


def _urun_ekle(t, urun_id: str, lansman: str = "2024-11-04", cikis=None) -> None:
    yeni = t["urun"].iloc[[0]].copy()
    yeni["urun_id"] = urun_id
    yeni["option_id"] = urun_id.rsplit("-", 1)[0]
    yeni["lansman_tarihi"] = pd.to_datetime(lansman)
    if cikis is not None:
        yeni["cikis_tarihi"] = pd.to_datetime(cikis)
    t["urun"] = pd.concat([t["urun"], yeni], ignore_index=True)


def _depo(t, urun: str, **gunler) -> None:
    """gunler: g0108=2 ... (gün -> depo sabah fotoğrafı)."""
    ekle(t, "depo_stok", [(f"2025-{k[1:3]}-{k[3:5]}", urun, n) for k, n in gunler.items()])


@pytest.fixture
def onl_con():
    t = oyuncak_tablolar()
    for u in (A, B, C, D, E):
        _urun_ekle(t, u, lansman="2025-01-09" if u == C else "2024-11-04",
                   cikis="2025-01-12" if u == C else None)

    # A) depo 2; 01-08'de 2 adet online satış (satır mükerrer, tek sayılır) -> tukenen;
    #    ertesi gün depo 0 -> bos
    _depo(t, A, g0108=2, g0109=0, g0110=0, g0111=0)
    ekle(t, "satis", [("2025-01-08", "ONL", A, 2, 500.0, 0.0, None),
                      ("2025-01-08", "ONL", A, 2, 500.0, 0.0, None)])

    # B) pencerenin son günü (depo_stok'un son günü 01-27). Zincir tutarlı:
    #    01-25 hareketsiz, net 1 -> 01-26 sabahı 9; 01-26: varış 2, çıkış 4, net 1 -> 01-27 sabahı 6
    _depo(t, B, g0125=10, g0126=9, g0127=6)
    ekle(t, "satis", [("2025-01-25", "ONL", B, 1, 250.0, 0.0, None),
                      ("2025-01-26", "ONL", B, 1, 250.0, 0.0, None),
                      ("2025-01-27", "ONL", B, 1, 250.0, 0.0, None)])
    ekle(t, "sevkiyat", [
        ("2025-01-25", "2025-01-26", "M003", "DEPO", B, 2, "stok_devri", None),    # varış 01-26
        ("2025-01-26", "2025-01-27", "M003", "DEPO", B, 2, "stok_devri", None),    # varış 01-27
        ("2025-01-26", "2025-01-27", "DEPO", "M001", B, 4, "replenishment", None),  # çıkış 01-26
        ("2025-01-27", "2025-01-28", "DEPO", "M001", B, 4, "replenishment", None),  # çıkış 01-27
    ])
    ekle(t, "siparis", [("S1", "surekli", "MDL0006-SYH", B, "T01", "2025-01-10",
                         "2025-01-27", "2025-01-27", 3)])

    # C) lansman 01-09, çıkış 01-12: uygun günler 01-09, 01-10, 01-11
    _depo(t, C, **{f"g01{g:02d}": 5 for g in range(6, 28)})

    # E) online iade: depo 3; 01-08'de 2 satış + 1 iade -> ertesi sabah depo 2
    _depo(t, E, g0108=3, g0109=2, g0110=2)
    ekle(t, "satis", [("2025-01-08", "ONL", E, 2, 500.0, 0.0, None),
                      ("2025-01-08", "ONL", E, -1, -250.0, 0.0, None)])

    con = oyuncak_baglan(t)
    yield con
    con.close()


# ------------------------------------------------------------------- elle

def test_online_elle(onl_con):
    g = stok.gunluk_online(onl_con, date(2025, 1, 8), date(2025, 1, 10))
    h = _gun(g, A)
    assert list(h.index) == [_t("01-08"), _t("01-09"), _t("01-10")]
    # 01-08: depo(01-09) 0 + net 2 = 2; brüt 2 >= 2 -> tukenen
    assert h.loc[_t("01-08"), ["satis_oncesi", "brut_satis", "net_satis"]].tolist() == [2, 2, 2]
    assert h.loc[_t("01-08"), "durum"] == "tukenen"
    # ertesi gün depo 0, satış yok -> bos
    assert h.loc[_t("01-09"), ["satis_oncesi", "brut_satis", "net_satis"]].tolist() == [0, 0, 0]
    assert h.loc[_t("01-09"), "durum"] == "bos"
    assert set(g["magaza_id"].astype(str)) == {"ONL"}


def test_online_iade_satistan_sonra(onl_con):
    h = _gun(stok.gunluk_online(onl_con, date(2025, 1, 8), date(2025, 1, 9)), E)
    # sabah 3; 2 satış + 1 iade: iade aynı günün satis_oncesi'ne girmez
    assert h.loc[_t("01-08"), ["satis_oncesi", "brut_satis", "net_satis"]].tolist() == [3, 2, 1]
    assert h.loc[_t("01-08"), "durum"] == "stoklu"
    assert h.loc[_t("01-09"), "satis_oncesi"] == 2


def test_son_gun_ileri_kurulur(onl_con):
    g = stok.gunluk_online(onl_con, date(2025, 1, 25), date(2025, 1, 27))
    h = _gun(g, B)
    # pencerenin son günü (depo_stok'ta 01-28 yok) tabloda var
    assert list(h.index) == [_t("01-25"), _t("01-26"), _t("01-27")]
    # ileri kurulum: depo(01-27) 6 + sipariş teslimi 3 + varış(DEPO) 2 - çıkış(DEPO) 4 = 7
    assert h.loc[_t("01-27"), "satis_oncesi"] == 6 + 3 + 2 - 4
    assert h.loc[_t("01-27"), "durum"] == "stoklu"
    # teslimsiz günde d+1 formülü ileri kurulumla aynı sonucu verir:
    # depo(01-27) 6 + net 1 = 7  ==  depo(01-26) 9 + varış 2 - çıkış 4
    assert h.loc[_t("01-26"), "satis_oncesi"] == 7 == 9 + 2 - 4
    assert h.loc[_t("01-25"), "satis_oncesi"] == 10
    # d+1 formülü pencere sonundan bağımsız
    kisa = _gun(stok.gunluk_online(onl_con, date(2025, 1, 25), date(2025, 1, 26)), B)
    assert list(kisa["satis_oncesi"]) == [10, 7]


def test_uygun_gun_lansman_ve_cikis(onl_con):
    h = _gun(stok.gunluk_online(onl_con, date(2025, 1, 6), date(2025, 1, 15)), C)
    # lansman_tarihi <= d < cikis_tarihi
    assert list(h.index) == [_t("01-09"), _t("01-10"), _t("01-11")]
    # çıkışı boş ürün pencere boyunca uygun
    assert len(_gun(stok.gunluk_online(onl_con, date(2025, 1, 6), date(2025, 1, 15)), A)) == 10


def test_depo_satiri_yok_sifir_stok(onl_con):
    h = _gun(stok.gunluk_online(onl_con, date(2025, 1, 8), date(2025, 1, 10)), D)
    assert list(h["satis_oncesi"]) == [0, 0, 0]
    assert set(h["durum"].astype(str)) == {"bos"}


# ------------------------------------------------------------------- şema

def test_sema_ve_magaza_ile_birlesme(oyuncak_con):
    onl = stok.gunluk_online(oyuncak_con, date(2025, 1, 6), date(2025, 1, 26))
    assert list(onl.columns) == SUTUNLAR
    for s in ("magaza_id", "urun_id", "option_id", "durum"):
        assert isinstance(onl[s].dtype, pd.CategoricalDtype), s
    for s in ("satis_oncesi", "brut_satis", "net_satis"):
        assert str(onl[s].dtype) == "int32", s
    assert str(onl["tarih"].dtype) == "datetime64[ns]"
    assert list(onl["durum"].cat.categories) == stok.DURUMLAR
    anahtar = list(zip(onl["tarih"], onl["urun_id"].astype(str)))
    assert anahtar == sorted(anahtar)
    assert len(onl) == 3 * 21   # 3 SKU x 21 gün
    # concat kategori türlerini korur
    mag = stok.gunluk_magaza(oyuncak_con, date(2025, 1, 6), date(2025, 1, 26))
    hepsi = pd.concat([mag, onl])
    for s in ("magaza_id", "urun_id", "option_id", "durum"):
        assert isinstance(hepsi[s].dtype, pd.CategoricalDtype), s
    assert len(hepsi) == len(mag) + len(onl)
    assert "ONL" in set(hepsi["magaza_id"].astype(str))


# --------------------------------------------------------------- gerçek veri

@pytest.mark.veri
def test_gercek_v4_depo_zinciri(v4_con):
    # teslimsiz günlerde depo_stok(d+1) = depo_stok(d) + varış(DEPO) - çıkış(DEPO) - net_satis_ONL(d)
    uyan, toplam = v4_con.execute("""
        with
        ds as (select urun_id::varchar u, tarih::date d, adet from depo_stok),
        teslim as (select distinct urun_id::varchar u, gerceklesen_teslim::date d
                   from siparis where gerceklesen_teslim is not null),
        varis as (select urun_id::varchar u, varis_tarihi::date d, sum(adet) n
                  from sevkiyat where hedef::varchar = 'DEPO' and varis_tarihi is not null
                  group by 1, 2),
        cikis as (select urun_id::varchar u, tarih::date d, sum(adet) n
                  from sevkiyat where kaynak::varchar = 'DEPO' group by 1, 2),
        onl as (select urun_id::varchar u, tarih::date d, sum(adet) n
                from (select distinct * from satis) where magaza_id::varchar = 'ONL'
                group by 1, 2)
        select count(*) filter (where b.adet = a.adet + coalesce(v.n, 0) - coalesce(c.n, 0)
                                              - coalesce(o.n, 0)),
               count(*)
        from ds a
        join ds b on b.u = a.u and b.d = a.d + 1
        left join varis v on v.u = a.u and v.d = a.d
        left join cikis c on c.u = a.u and c.d = a.d
        left join onl o on o.u = a.u and o.d = a.d
        where not exists (select 1 from teslim t where t.u = a.u and t.d = a.d)
    """).fetchone()
    print(f"depo zinciri: {uyan:,} / {toplam:,} = {uyan / toplam:.7f}")
    assert toplam > 1_000_000
    assert uyan / toplam >= 0.9999
