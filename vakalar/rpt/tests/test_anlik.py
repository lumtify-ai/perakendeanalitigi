"""`rpt.anlik`: Gorunum → ortak günlük tablo adaptörü (Ruling R5, R6).

R5 eşitliği: KÜÇÜK dünyada bir koşu; karar pazartesisi `t`'de motor içi yol
(`anlik.gunluk_gorunumden`, geçmiş kaydıyla) ile aynı koşunun tablolarından
(`t`'ye kırpılmış) ortak `stok.gunluk_magaza` + `gunluk_online` +
`ozellikler.ekle` yolu karar havuzunda aynı günlük tabloyu ve
`sansur.karar_ani_talep`te aynı kestirimi verir (birebir).
"""

from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest
from perakende_analitik import carpanlar, hazirlik, ozellikler, stok

from rpt import aday, anlik, hazirla, kaynak, motor, sansur

SEZON = "AW24"


class _Yakala:
    """Lumoda'nın RPT'sini sarar; `t` pazartesisinde günlük tabloyu ve durumu yakalar."""

    gecmis_gerekir = True

    def __init__(self, t: int, havuz: pd.DataFrame, temel):
        self.t, self.havuz, self.temel = t, havuz, temel
        self.gunluk = self.durum = self.gorunum = None

    def __call__(self, g):
        if g.gun == self.t:
            self.gunluk = anlik.gunluk_gorunumden(g, self.havuz)
            self.durum = anlik.durum_gorunumden(g, self.havuz["option_id"])
            self.gorunum = g
        return self.temel(g)


def _tablo_yolu(tablolar: dict, t: pd.Timestamp, havuz: pd.DataFrame):
    """`hazirla` + `havuz_gunlugu`'nun yolu, koşunun tablolarıyla: `t`'ye kırpılmış
    tablolar → bellek içi DuckDB → ortak günlük tablo (yıl yıl, mağaza sonra online)
    → havuz satırları + Basit özellikleri. Çarpanlar aynı tablonun stoklu
    günlerinden (iki yol aynı çarpanı alır)."""
    kirpik = kaynak.tarihten_once(tablolar, t)
    con = duckdb.connect()
    for ad, df in {**tablolar, **kirpik}.items():
        con.register(ad, df)
    bas = date(t.year if t.month > 1 else t.year - 1, 1, 1)
    parca = []
    for yil in range(bas.year, t.year + 1):
        b, s = max(date(yil, 1, 1), bas), min(date(yil, 12, 31), (t - pd.Timedelta(days=1)).date())
        for f in (stok.gunluk_magaza, stok.gunluk_online):
            parca.append(f(con, b, s)[hazirlik.GUNLUK_SUTUNLARI])
    gunluk = pd.concat(parca, ignore_index=True)
    stoklu = gunluk[gunluk["durum"] == "stoklu"].reset_index(drop=True)
    carp = carpanlar.ogren(ozellikler.ekle(con, stoklu, hazirlik.CARPAN_OZELLIKLERI))
    ids = set(havuz["option_id"].astype(str))
    sec = gunluk["option_id"].astype(str).isin(ids) & (gunluk["tarih"] >= pd.to_datetime(havuz["bas"]).min())
    g = ozellikler.ekle(con, gunluk[sec].reset_index(drop=True), anlik.BASIT_OZELLIKLERI)
    return g, carp


@pytest.fixture(scope="module")
def r5():
    w = motor.dunya("kucuk")
    pb = motor.politika_gorunumu(w)
    opt = w.optionlar
    sec = (opt["sezon_kodu"] == SEZON) & (opt["line"] == "Collection")
    lans = sorted(opt.loc[sec, "lansman_gun"].unique())
    t = int(lans[1]) + 14                     # ikinci dalganın h = 2'si: havuzda iki dalga
    t_ts = pd.Timestamp(motor._gun_tarihi([t])[0])
    havuz = sansur.karar_havuzu(pb.optionlar, SEZON, t_ts)
    y = _Yakala(t, havuz, motor.lumoda("rpt"))
    k = motor.kos(rpt=y, ad="r5", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=t + 8)
    g_tablo, carp = _tablo_yolu(k.tablolar, t_ts, havuz)
    return {"t": t_ts, "havuz": havuz, "yakala": y, "kosu": k, "tablo": g_tablo, "carp": carp, "pb": pb}


def test_pencere_hazirla_ve_v4_ile_ayni():
    from perakende_veri.v4 import sabitler

    assert anlik.PENCERE == hazirla.PENCERE
    assert anlik.PENCERE == (pd.Timestamp(sabitler.BASLANGIC).date(), pd.Timestamp(sabitler.BITIS).date())


def test_r5_gunluk_tablo_birebir(r5):
    t, havuz = r5["t"], r5["havuz"]
    a = sansur.havuz_satirlari(r5["tablo"], t, havuz)
    b = sansur.havuz_satirlari(r5["yakala"].gunluk, t, havuz)
    assert len(havuz) >= 2 and len(a) > 1000
    assert set(a["durum"]) == {"stoklu", "tukenen", "bos"}
    assert (a["kanal"] == "online").any() and (a["oran"] > 0).any()
    pd.testing.assert_frame_equal(a, b, check_exact=True)


def test_r5_motor_ici_kestirim_tablo_yoluyla_ayni(r5):
    """Ruling R5: iki yol aynı girdide aynı kestirimi verir (birebir)."""
    t, havuz, carp = r5["t"], r5["havuz"], r5["carp"]
    e_tablo = sansur.karar_ani_talep(r5["tablo"], t, carp, havuz)
    e_motor = sansur.karar_ani_talep(r5["yakala"].gunluk, t, carp, havuz)
    assert (e_tablo["kayip"] > 0).sum() > 100
    pd.testing.assert_frame_equal(e_tablo, e_motor, check_exact=True)
    pd.testing.assert_frame_equal(sansur.ozet(e_tablo), sansur.ozet(e_motor), check_exact=True)
    # Karar satırı: motor içi `karar_ani_satirlari` = tablo yolunun `karar_ozetleri` satırı
    opt = r5["pb"].optionlar
    tablo = sansur.karar_ozetleri(r5["tablo"], opt, [SEZON], (2, 3, 4, 5, 6), lambda _: carp)
    tablo = tablo[tablo["karar_ani"] == t].reset_index(drop=True)
    motor_ici = sansur.karar_ani_satirlari(r5["yakala"].gunluk, opt, SEZON, t, (2, 3, 4, 5, 6), carp)
    assert len(tablo) > 0
    pd.testing.assert_frame_equal(tablo, motor_ici, check_exact=True)


def test_durum_gorunumden_tablo_yoluyla(r5):
    """Karar sabahı durumu: STR ve mağaza payları tablo yolunun birebir aynısı;
    envanter pozisyonu (depo + mağaza + yolda + açık) aynı zinciri sayar (fark
    yalnız bu sabah teslim edilen siparişin kalite reddi)."""
    t, havuz = r5["t"], r5["havuz"]
    tablo = aday.durum_tablodan(r5["kosu"].tablolar, t, havuz["option_id"]).set_index("option_id")
    gor = r5["yakala"].durum.set_index("option_id")
    for s in ("satilan", "gonderilen", "str", "stoklu_magaza_payi", "kirik_magaza_payi", "rpt_sayisi"):
        np.testing.assert_array_equal(gor[s].to_numpy(), tablo.loc[gor.index, s].to_numpy(), err_msg=s)
    ip = lambda d: (d["depo"] + d["magaza"] + d["yolda"] + d["acik"]).to_numpy()  # noqa: E731
    fark = ip(tablo.loc[gor.index]) - ip(gor)
    assert (fark >= 0).all() and fark.sum() <= 0.02 * ip(tablo).sum()


def test_gecmissiz_gorunum_hata():
    w = motor.dunya("kucuk")

    class G:
        dunya = w
        gun = 7
        satis_oncesi_gecmisi = None

    with pytest.raises(ValueError, match="gecmis_kaydi"):
        anlik.gunluk_gorunumden(G(), pd.DataFrame({"option_id": [], "bas": []}))


def test_karar_ani_pazartesi_olmali(r5):
    import dataclasses

    g = r5["yakala"].gorunum
    g2 = dataclasses.replace(g, gun=g.gun + 1)
    with pytest.raises(ValueError, match="pazartesi"):
        anlik.gunluk_gorunumden(g2, r5["havuz"])
