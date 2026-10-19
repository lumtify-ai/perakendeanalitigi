"""`allocation.ogrenme`: ilk varışlar, sansür düzeltmeli erken talep, öğrenme tablosu.

Erken talep testleri sentetik `[gün, C]` matrislerle (oyuncak dünyanın hücre ekseni, gün 0 =
2025-02-03); öğrenme tablosu testleri iki geçmiş sezonu taşıyan uzun bir oyuncak dünyayla
(`gecmis_dunya`, `gecmis_tablolar`; akışlar elle kurulmuş bir stok zinciridir, pazartesi
fotoğrafları ondan). `veri` işaretli testler yayımlanan v4 dosyasını okur."""

import numpy as np
import pandas as pd
import pytest
from conftest import oyuncak_dunya, oyuncak_tablolar

from allocation import kaynak, ogrenme, sabitler

M1, M2, M3, M4, MO, ONL = range(6)          # oyuncak mağaza indisleri
GA, GB, A, B, C, X = range(6)               # oyuncak option indisleri
SKU = {GA: 0, GB: 5, A: 10, B: 15, C: 20, X: 25}   # option'ın ilk SKU'su
GUN0 = pd.Timestamp("2025-02-03")           # oyuncak dünyanın 0. günü


def _g(tarih: str) -> int:
    return (pd.Timestamp(tarih) - GUN0).days


def _hucre(w, m: int, sku: int) -> int:
    c = np.flatnonzero((np.asarray(w.hucre_magaza) == m) & (np.asarray(w.hucre_sku) == sku))
    assert len(c) == 1
    return int(c[0])


class _Matris:
    """Sentetik satış / stoklu matrisi kurucusu."""

    def __init__(self, w, gun: int = 130):
        self.w = w
        C = len(w.hucre_magaza)
        self.satis = np.zeros((gun, C), dtype=np.int16)
        self.stoklu = np.zeros((gun, C), dtype=bool)

    def koy(self, m: int, sku: int, gunler, satis=0, stoklu=True):
        c = _hucre(self.w, m, sku)
        g = np.asarray(list(gunler))
        self.satis[g, c] = satis
        self.stoklu[g, c] = stoklu
        return self


def _satir(df: pd.DataFrame, o: int, m: int) -> pd.Series:
    s = df[(df["option"] == o) & (df["magaza"] == m)]
    assert len(s) == 1, (o, m)
    return s.iloc[0]


# ---------------------------------------------------------------- ilk varışlar


def test_ilk_varislar_ilk_dagitimdan(dunya, tablolar):
    v = ogrenme.ilk_varislar(tablolar, dunya)
    # conftest: A-1'in ilk dağıtımı M1 ve M2'ye g0'da (dünya günü 7); replenishment sayılmaz
    assert v == {(M1, A): 7, (M2, A): 7}
    assert all(isinstance(k, int) and isinstance(g, int) for (k, _), g in v.items())


def test_ilk_varislar_option_basina_en_erken(dunya, tablolar):
    t = {**tablolar}
    s = t["sevkiyat"]
    ek = s[s["tip"] == "ilk_dagitim"].iloc[[0]].copy()     # M1, A-1
    ek["urun_id"] = "OPT-A-3"
    ek["varis_tarihi"] = pd.Timestamp("2025-02-08")
    gec = ek.copy()
    gec["urun_id"], gec["varis_tarihi"] = "OPT-A-4", pd.Timestamp("2025-02-20")
    t["sevkiyat"] = pd.concat([s, ek, gec], ignore_index=True)
    v = ogrenme.ilk_varislar(t, dunya)
    assert v[(M1, A)] == 5 and v[(M2, A)] == 7


# ---------------------------------------------------------------- erken talep


def test_erken_talep_sansur(dunya):
    h = kaynak.harita_kur(dunya)
    x0, a0 = _g("2025-04-21"), _g("2025-02-10")     # X dalga 3, A dalga 1 lansmanı
    mt = _Matris(dunya)
    mt.koy(M1, SKU[X], range(x0, x0 + 3), satis=2)          # 3 stoklu günde 6 satış
    mt.koy(M2, SKU[X], range(x0, x0 + 2), satis=1)          # 2 stoklu gün: olduğu gibi
    mt.koy(M3, SKU[A], range(a0, a0 + 42), satis=0)
    mt.koy(M3, SKU[A], range(a0, a0 + 21), satis=1)         # beden 1: 42 stoklu gün, 21 satış
    mt.koy(M3, SKU[A] + 1, range(a0, a0 + 21), satis=2)     # beden 2: 21 stoklu gün, 42 satış
    mt.koy(M3, SKU[A] + 2, [a0 + 5], satis=1)               # beden 3: 1 stoklu gün
    mt.koy(M3, SKU[A] + 4, range(a0, a0 + 42), satis=0)     # beden 5: stoklu, satışsız
    mt.koy(M3, SKU[A], [a0 + 42, a0 + 43], satis=9)         # pencere sonrası: sayılmaz
    mt.koy(M3, SKU[A], [a0 - 1], satis=9, stoklu=False)     # pencere öncesi: sayılmaz
    varis = {(M1, X): x0, (M2, X): x0, (M3, A): a0}
    t = ogrenme.erken_talep(mt.satis, mt.stoklu, h, dunya, np.array([A, X]), varis)

    assert list(t.columns) == list(ogrenme.ERKEN_SUTUNLARI)
    r = _satir(t, X, M1)
    assert (r["satis"], r["stoklu_gun"], r["talep"]) == (6, 3, pytest.approx(84.0))   # 6 / 3 × 42
    r = _satir(t, X, M2)
    assert (r["satis"], r["stoklu_gun"], r["talep"]) == (2, 2, pytest.approx(2.0))
    # option = SKU'ların toplamı: 21 + 42/21×42 + 1 + 0 (beden 4 stoksuz, dışarıda)
    r = _satir(t, A, M3)
    assert (r["satis"], r["stoklu_gun"]) == (21 + 42 + 1, 42)
    assert r["talep"] == pytest.approx(21 + 84 + 1 + 0)
    assert t[["option", "magaza"]].values.tolist() == [[A, M3], [X, M1], [X, M2]]   # sıralı
    assert t["option"].dtype == t["magaza"].dtype == t["satis"].dtype == t["stoklu_gun"].dtype == np.int64
    assert t["talep"].dtype == np.float64


def test_erken_talep_kesimde_kesilir(dunya):
    h = kaynak.harita_kur(dunya)
    kesim = _g("2025-06-01")                    # SS25: indirim 2025-06-30 - 29
    assert kesim == (kaynak.erken_kesim(dunya, "SS25") - GUN0).days
    gec = _g("2025-05-12")                      # geç varış: pencere 42 değil 21 gün
    b0 = _g("2025-03-17")
    mt = _Matris(dunya)
    mt.koy(M4, SKU[A], range(gec, 130), satis=1)            # kesimden sonra da satıyor
    mt.koy(M1, SKU[B], range(b0, b0 + 50), satis=1)         # kesilmeyen pencere: 42 gün
    mt.koy(M2, SKU[X], range(_g("2025-04-21"), 130), satis=1)   # dalga 3: tam sınırda 42 gün
    varis = {(M4, A): gec, (M1, B): b0, (M2, X): _g("2025-04-21"), (M3, A): kesim + 1}
    t = ogrenme.erken_talep(mt.satis, mt.stoklu, h, dunya, np.array([A, B, X]), varis)
    r = _satir(t, A, M4)
    assert (r["satis"], r["stoklu_gun"], r["talep"]) == (kesim + 1 - gec, 21, pytest.approx(21.0))
    r = _satir(t, B, M1)
    assert (r["satis"], r["stoklu_gun"], r["talep"]) == (42, 42, pytest.approx(42.0))
    r = _satir(t, X, M2)
    assert (r["satis"], r["stoklu_gun"]) == (42, 42)
    # kesimden sonra varan: pencere yok, hücre dışarıda
    r = _satir(t, A, M3)
    assert r["stoklu_gun"] == 0 and r["satis"] == 0 and np.isnan(r["talep"])


def test_erken_talep_matris_pencereyi_kapsamali(dunya):
    h = kaynak.harita_kur(dunya)
    mt = _Matris(dunya, gun=100)                # pencere [98, 119) matrisin dışına taşar
    with pytest.raises(ValueError, match="kapsam"):
        ogrenme.erken_talep(mt.satis, mt.stoklu, h, dunya, np.array([A]), {(M4, A): 98})


def test_erken_talep_stoksuz_hucre_disarida(dunya):
    h = kaynak.harita_kur(dunya)
    a0 = _g("2025-02-10")
    mt = _Matris(dunya)
    mt.koy(M1, SKU[A], range(a0, a0 + 42), satis=1)
    mt.koy(M1, SKU[A] + 1, [a0 + 3, a0 + 4], satis=5, stoklu=False)   # stoksuz günde satış
    mt.koy(M2, SKU[A], [a0 + 10], satis=3, stoklu=False)               # hiçbir bedeni stoklu değil
    mt.koy(MO, SKU[C], range(a0, a0 + 42), satis=1)                    # Outlet tipi mağaza
    mt.koy(ONL, SKU[A], range(a0, a0 + 42), satis=1)                   # online
    varis = {(M1, A): a0, (M2, A): a0, (MO, C): a0, (ONL, A): a0, (M3, GA): a0}
    t = ogrenme.erken_talep(mt.satis, mt.stoklu, h, dunya, np.array([A, C]), varis)
    # stoksuz beden toplama girmez; satışı `satis`'te görünür
    r = _satir(t, A, M1)
    assert (r["satis"], r["stoklu_gun"], r["talep"]) == (42 + 10, 42, pytest.approx(42.0))
    # bütün bedenleri stoksuz: satır var, stoklu_gun 0, talep yok
    r = _satir(t, A, M2)
    assert (r["satis"], r["stoklu_gun"]) == (3, 0) and np.isnan(r["talep"])
    # fiziksel olmayan mağaza, istenmeyen option, varışı olmayan mağaza tabloda yok
    assert t[["option", "magaza"]].values.tolist() == [[A, M1], [A, M2]]


def test_erken_talep_bos(dunya):
    h = kaynak.harita_kur(dunya)
    mt = _Matris(dunya)
    t = ogrenme.erken_talep(mt.satis, mt.stoklu, h, dunya, np.array([], dtype=np.int64), {})
    assert list(t.columns) == list(ogrenme.ERKEN_SUTUNLARI) and len(t) == 0


# ---------------------------------------------------------------- uzun oyuncak dünya

GECMIS_BASI = pd.Timestamp("2023-01-02")    # pazartesi; dünya günü 0
GECMIS_SONU = pd.Timestamp("2025-03-09")    # pazar
_PAKET = np.array([1, 2, 2, 1, 1])
# option -> (lansman, akış sonu, mağaza -> (paket katı, günlük option hızı))
_GECMIS = {
    GA: ("2023-02-13", "2023-11-12", {M1: (4, 3.0), M2: (2, 1.0), M3: (1, 2.0), M4: (3, 1.5)}),
    GB: ("2024-03-18", GECMIS_SONU, {M1: (2, 1.0), M2: (3, 2.5), M3: (2, 0.5), M4: (1, 1.0)}),
}
_BEDEN_PAYI = _PAKET / _PAKET.sum()


def gecmis_dunya():
    w = oyuncak_dunya()
    tarih = pd.date_range(GECMIS_BASI, GECMIS_SONU, freq="D")
    w.takvim = pd.DataFrame({"tarih": tarih, "pazartesi_mi": tarih.weekday == 0})
    w.gun_sayisi = len(tarih)
    aw22 = pd.DataFrame([("AW22", d, pd.Timestamp(l), pd.Timestamp("2023-01-02"), pd.Timestamp("2023-02-27"))
                         for d, l in ((1, "2022-08-22"), (2, "2022-09-26"), (3, "2022-10-31"))],
                        columns=w.sezon.columns)
    w.sezon = pd.concat([aw22, w.sezon], ignore_index=True)
    return w


def _zincir(varis: dict[pd.Timestamp, int], hiz: float, bas: pd.Timestamp, son: pd.Timestamp,
            rng) -> tuple[list, list]:
    """Bir hücrenin günlük akışı: (satış satırları [(gün, adet)], fotoğraflar [(pazartesi, adet,
    stoklu_gun)]). Açılış = önceki gün sonu + varış; satış = min(talep, açılış)."""
    satis, foto, kalan, acik = [], [], 0, []
    for g in pd.date_range(bas, son, freq="D"):
        if g.weekday() == 0:
            foto.append((g, kalan, sum(acik[-7:])))
        acilis = kalan + varis.get(g, 0)
        adet = min(int(rng.poisson(hiz)), acilis)
        if adet:
            satis.append((g, adet))
        kalan = acilis - adet
        acik.append(acilis > 0)
    sonraki = son + pd.Timedelta(days=1)                    # son haftanın kapanış fotoğrafı
    foto.append((sonraki, kalan, sum(acik[-7:])))
    return satis, foto


def gecmis_tablolar() -> dict[str, pd.DataFrame]:
    """İki geçmiş sezonun (GA SS23, GB SS24) dört fiziksel mağazadaki akışı + conftest'in SS25
    A-1 akışı. M4'e GA'nın 5. bedeni hiç gönderilmez; M1'e GA'nın 3. bedeni lansmandan 10 gün
    sonra replenishment alır. GB'nin akışı SS25 karar gününden sonra da sürer."""
    t = oyuncak_tablolar()
    rng = np.random.default_rng(20261019)
    mag = ["M1", "M2", "M3", "M4", "MO", "ONL"]
    satis, stok, sevk = [], [], []
    for o, (lansman, son, magazalar) in _GECMIS.items():
        l, son = pd.Timestamp(lansman), pd.Timestamp(son)
        oid = oyuncak_dunya().optionlar["option_id"].iloc[o]
        for m, (kat, hiz) in magazalar.items():
            for b in range(5):
                if o == GA and m == M4 and b == 4:
                    continue
                u = f"{oid}-{b + 1}"
                varis = {l: int(_PAKET[b] * kat)}
                sevk.append((l - pd.Timedelta(days=2), l, "DEPO", mag[m], u, varis[l], "ilk_dagitim", "PKT"))
                if o == GA and m == M1 and b == 2:
                    r = l + pd.Timedelta(days=10)
                    varis[r] = 6
                    sevk.append((r - pd.Timedelta(days=1), r, "DEPO", mag[m], u, 6, "replenishment", None))
                s, f = _zincir(varis, hiz * _BEDEN_PAYI[b], l - pd.Timedelta(days=l.weekday()), son, rng)
                satis += [(g, mag[m], u, a, 100.0 * a, 0.0, None) for g, a in s]
                stok += [(g, mag[m], u, a, sg) for g, a, sg in f]
    yeni = {"satis": satis, "stok": stok, "sevkiyat": sevk}
    for ad, satirlar in yeni.items():
        ek = pd.DataFrame(satirlar, columns=t[ad].columns).astype(t[ad].dtypes.to_dict())
        t[ad] = pd.concat([ek, t[ad]], ignore_index=True)
    return t


@pytest.fixture(scope="module")
def gecmis():
    return gecmis_dunya(), gecmis_tablolar()


def test_kapanmis_sezonlar(gecmis):
    w, t = gecmis
    # veri 2023-02-13'te başlar (ilk fotoğraf): AW22'nin lansmanı öncesinde, hiç girmez
    assert ogrenme.kapanmis_sezonlar(w, t, pd.Timestamp("2025-02-01")) == ["SS23", "SS24"]
    assert ogrenme.kapanmis_sezonlar(w, t, pd.Timestamp("2024-03-01")) == ["SS23"]
    assert ogrenme.kapanmis_sezonlar(w, t, pd.Timestamp("2023-08-28")) == []    # çıkış günü: kapanmamış
    assert ogrenme.kapanmis_sezonlar(w, t, pd.Timestamp("2023-08-29")) == ["SS23"]


def test_ogrenme_yalniz_kapanmis_sezon(gecmis):
    w, t = gecmis
    tum = ogrenme.ogrenme_tablosu(t, w, pd.Timestamp("2025-02-01"))
    assert list(tum.columns) == [*ogrenme.ERKEN_SUTUNLARI, *ogrenme.OZNITELIKLER, "ilk_alim"]
    assert sorted(set(tum["option"])) == [GA, GB]
    assert sorted(set(tum["sezon_kodu"])) == ["SS23", "SS24"]
    assert set(tum["magaza"]) == {M1, M2, M3, M4}
    yalniz_ss23 = ogrenme.ogrenme_tablosu(t, w, pd.Timestamp("2024-03-01"))
    assert set(yalniz_ss23["option"]) == {GA}
    bos = ogrenme.ogrenme_tablosu(t, w, pd.Timestamp("2023-08-28"))
    assert list(bos.columns) == list(tum.columns) and len(bos) == 0


def test_ogrenme_tablosu_degerler_ve_oznitelikler(gecmis):
    """Tablonun erken talebi, bütün tablolardan kurulan matrislerle `erken_talep`'in aynısı
    (öğrenme tabloları option kümesine daraltarak okur); öznitelikler `optionlar`dan."""
    w, t = gecmis
    karar = pd.Timestamp("2025-02-01")
    tablo = ogrenme.ogrenme_tablosu(t, w, karar)
    s, f = kaynak.gunluk_matrisler(t, w, karar)
    dogrudan = ogrenme.erken_talep(s, f, kaynak.harita_kur(w), w, np.array([GA, GB]),
                                   ogrenme.ilk_varislar(t, w))
    pd.testing.assert_frame_equal(tablo[list(ogrenme.ERKEN_SUTUNLARI)], dogrudan)
    assert len(tablo) == 8 and (tablo["stoklu_gun"] > 0).all()
    assert (tablo["talep"] >= tablo["satis"]).all()
    r = tablo[tablo["option"] == GA].iloc[0]
    assert (r["alt_kategori"], r["fiyat_segmenti"], r["kalip"], r["sezon_kodu"]) == (
        "Bluz", "orta", "regular", "SS23")
    assert (r["dalga"], r["ilk_alim"], r["liste_fiyati"]) == (1, 700, pytest.approx(499.99))
    assert tablo["dalga"].dtype == np.int64


def test_ogrenme_karar_sonrasini_gormez(gecmis):
    w, t = gecmis
    for karar in (pd.Timestamp("2025-02-01"), pd.Timestamp("2024-09-02")):
        once = ogrenme.ogrenme_tablosu(t, w, karar)
        bozuk = {ad: df.copy() for ad, df in t.items()}
        for ad in ("satis", "stok"):
            d = bozuk[ad]
            sonra = d["tarih"] >= karar
            assert sonra.any(), ad                         # bozulacak satır var
            d.loc[sonra, "adet"] = d.loc[sonra, "adet"] * 7 + 3
        sv = bozuk["sevkiyat"]
        sonra = sv["varis_tarihi"] >= karar
        sv.loc[sonra, "adet"] = sv.loc[sonra, "adet"] * 5 + 1
        sv.loc[sonra, "tip"] = "ilk_dagitim"
        pd.testing.assert_frame_equal(once, ogrenme.ogrenme_tablosu(bozuk, w, karar))


def test_ogrenme_karar_sonrasi_ilk_dagitimi_gormez(gecmis):
    """Kapanmış sezonun option'ına karar gününden sonra varan bir ilk dağıtım satırı (daraltmada
    düşmez) tabloya girmez. M4'ün GA ilk dağıtımı silinir; karardan sonra M4'e GA varışı eklenir:
    süzgeç olmasa (GA, M4) çifti tabloya girerdi (ya da pencere matrisin dışına taşardı)."""
    w, t = gecmis
    karar = pd.Timestamp("2025-02-01")
    sv = t["sevkiyat"]
    m4_ga = (sv["hedef"] == "M4") & sv["urun_id"].str.startswith("OPT-GA-") & (sv["tip"] == "ilk_dagitim")
    assert m4_ga.any()
    varissiz = {**t, "sevkiyat": sv[~m4_ga.to_numpy(dtype=bool)].reset_index(drop=True)}
    once = ogrenme.ogrenme_tablosu(varissiz, w, karar)
    assert ((once["option"] == GA) & (once["magaza"] == M4)).sum() == 0
    gec = sv[m4_ga.to_numpy(dtype=bool)].iloc[[0]].copy()
    gec["tarih"], gec["varis_tarihi"] = pd.Timestamp("2025-02-03"), pd.Timestamp("2025-02-05")
    sonra = {**varissiz, "sevkiyat": pd.concat([varissiz["sevkiyat"], gec], ignore_index=True)}
    pd.testing.assert_frame_equal(once, ogrenme.ogrenme_tablosu(sonra, w, karar))


# ---------------------------------------------------------------- gerçek veri


@pytest.mark.veri
def test_daraltma_yayimlanan_veride_esdeger():
    """Tabloları option kümesine daraltmak, o option'ların hücrelerinde günlük matrisleri
    değiştirmez (stok kurulumu hücre başınadır). SS23 dalga 1, erken pencereden sonra (geç
    varışlar lansmandan 17 güne dek sürer; pencereler 2023-04-12'ye dek uzar)."""
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.TAM)
    h = kaynak.harita_kur(w)
    bit = pd.Timestamp("2023-05-01")
    o = np.flatnonzero((h.option_sezon == "SS23") & (h.option_line == sabitler.LINE) & (h.option_dalga == 1))
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con)
    finally:
        con.close()
    varis = ogrenme.ilk_varislar(t, w)
    tam = ogrenme.erken_talep(*kaynak.gunluk_matrisler(t, w, bit), h, w, o, varis)
    dar = ogrenme.erken_talep(*kaynak.gunluk_matrisler(ogrenme.daralt(t, w, o), w, bit), h, w, o, varis)
    assert len(tam) > 1000 and (tam["stoklu_gun"] > 0).mean() > 0.95
    pd.testing.assert_frame_equal(tam, dar)


@pytest.mark.veri
def test_ogrenme_tablosu_yayimlanan_veri():
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    from allocation import benzer

    w = dunya_kur(Olcek.TAM)
    karar = pd.Timestamp("2025-02-01")
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con)
        beklenen = con.execute(f"""
            select u.sezon_kodu, count(distinct (s.hedef, u.option_id)) as n
            from sevkiyat s join urun u using (urun_id) join magaza m on m.magaza_id = s.hedef
            where s.tip = 'ilk_dagitim' and u.line = '{sabitler.LINE}'
              and m.tip not in ('Outlet', 'Online')
              and u.sezon_kodu in ('SS23', 'AW23', 'SS24')
            group by 1 order by 1""").df()
    finally:
        con.close()
    tablo = ogrenme.ogrenme_tablosu(t, w, karar)
    assert ogrenme.kapanmis_sezonlar(w, t, karar) == ["SS23", "AW23", "SS24"]
    n = tablo.groupby("sezon_kodu").size()
    assert n.to_dict() == dict(zip(beklenen["sezon_kodu"], beklenen["n"]))
    assert tablo["stoklu_gun"].between(0, sabitler.ERKEN_GUN).all()
    gozlem = tablo["stoklu_gun"] > 0
    assert gozlem.mean() > 0.95 and tablo.loc[gozlem, "talep"].notna().all()
    assert tablo.loc[~gozlem, "talep"].isna().all()
    assert (tablo.loc[gozlem, "talep"] >= 0).all() and tablo["ilk_alim"].gt(0).all()
    assert not tablo[list(ogrenme.OZNITELIKLER)].isna().any().any()

    # benzer endeksi gerçek tabloda: SS25 option'ı, SS geçmişi
    e = benzer.ogren(tablo, en_az=5, mevsim="SS")
    o = int(kaynak.oyun_optionlari(w, sabitler.OYUN_SEZONU)[0])
    oz = ogrenme.option_oznitelikleri(w, np.array([o])).iloc[0].to_dict()
    aday = kaynak.harita_kur(w).magaza_fiziksel
    endeks, duzey, mutlak = e.endeks(oz, aday)
    assert endeks.shape == mutlak.shape == (len(w.magazalar),)
    assert 0 <= duzey < len(benzer.HIYERARSI)
    assert (endeks[aday] > 0).all() and (mutlak[aday] > 0).all() and not endeks[~aday].any()
    assert np.isfinite(benzer.belirsizlik(e, oz, aday))
