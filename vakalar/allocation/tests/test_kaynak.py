"""`allocation.kaynak`: hücre haritası, oyun option'ları, erken pencere kesimi, günlük matrisler.

Oyuncak testleri `conftest`in elle izlenebilir dünyasını ve tablolarını kullanır; `veri`
işaretli testler gerçek v4 dosyasını."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import DUNYA_BASI, GUN_G0, IZLENEN, gun, oyuncak_baglan

from allocation import kaynak, sabitler

M1, M2, ONL = 0, 1, 5      # oyuncak mağaza indisleri
SKU_A1 = 10                # OPT-A-1 (GA 0-4, GB 5-9, A 10-14)


def _hucre(w, magaza: int, sku: int) -> int:
    c = np.flatnonzero((np.asarray(w.hucre_magaza) == magaza) & (np.asarray(w.hucre_sku) == sku))
    assert len(c) == 1
    return int(c[0])


# ---------------------------------------------------------------- harita


def test_harita_fiziksel_online_outlet(dunya):
    h = kaynak.harita_kur(dunya)
    C = len(dunya.hucre_magaza)
    assert h.hucre_magaza.shape == h.hucre_option.shape == h.hucre_sku.shape == (C,)
    assert h.hucre_online.dtype == bool and h.hucre_online.sum() == len(dunya.urunler)   # ONL her SKU'da
    assert (h.hucre_magaza[h.hucre_online] == 5).all()
    # fiziksel: yalnız M1-M4; ONL ve Outlet tipi (MO) hariç
    assert h.magaza_fiziksel.dtype == bool
    assert h.magaza_fiziksel.tolist() == [True, True, True, True, False, False]
    # outlet mağazasının hücreleri yalnız Outlet line'ında
    mo = h.hucre_magaza == 4
    assert mo.any() and (h.option_line[h.hucre_option[mo]] == "Outlet").all()
    # SKU-option eşlemesi ve beden sırası
    assert h.sku_option.shape == h.sku_beden_sira.shape == (len(dunya.urunler),)
    assert (h.sku_option[h.hucre_sku] == h.hucre_option).all()
    assert h.sku_beden_sira.tolist()[:6] == [1, 2, 3, 4, 5, 1]


def test_harita_option_ozellikleri(dunya):
    h = kaynak.harita_kur(dunya)
    assert h.option_line.tolist() == ["Collection"] * 4 + ["Outlet", "Collection"]
    assert h.option_sezon.tolist() == ["SS23", "SS24", "SS25", "SS25", "SS25", "SS25"]
    assert h.option_dalga.tolist() == [1, 2, 1, 2, 1, 3] and h.option_dalga.dtype.kind == "i"


def test_istanbul_ali(dunya):
    h = kaynak.harita_kur(dunya)
    assert h.magaza_istanbul.dtype == bool
    # ayrım şehirden: M1 ve MO İstanbul; Bursa (Marmara bölgesi) ve ONL (Gebze) değil
    assert h.magaza_istanbul.tolist() == [True, False, False, False, True, False]
    # Ali = İstanbul'daki fiziksel mağaza: yalnız M1 (Outlet tipi MO fiziksel değil)
    assert np.flatnonzero(h.magaza_istanbul & h.magaza_fiziksel).tolist() == [0]


def test_harita_salt_okunur_ve_gizli_alana_dokunmaz(dunya):
    h = kaynak.harita_kur(dunya)          # OyuncakDunya gizli alan okunursa AssertionError atar
    for ad in h.__dataclass_fields__:
        assert not getattr(h, ad).flags.writeable, ad
    dunya.hucre_magaza[0] = 3             # haritanın kopyası etkilenmez
    assert h.hucre_magaza[0] == 0


def test_kaynak_modulu_gizli_gerceği_ve_motoru_gormez():
    agac = ast.parse(Path(kaynak.__file__).read_text(encoding="utf-8"))
    modüller = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            modüller |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            modüller.add(n.module or "")
    assert not any(m.split(".")[0] == "perakende_veri" for m in modüller)
    assert not any("motor" in m.split(".") for m in modüller)
    assert "perakende_analitik.hakem" not in modüller


# ---------------------------------------------------------------- option, kesim


def test_oyun_optionlari_yalniz_collection(dunya):
    o = kaynak.oyun_optionlari(dunya, "SS25")
    assert o.dtype.kind == "i"
    assert o.tolist() == [2, 3, 5]                  # OPT-C (Outlet line) ve geçmiş sezonlar yok
    assert kaynak.oyun_optionlari(dunya, "SS24").tolist() == [1]
    assert kaynak.oyun_optionlari(dunya, "AW99").tolist() == []


def test_erken_kesim_indirimden_29_gun_once(dunya):
    assert kaynak.erken_kesim(dunya, "SS25") == pd.Timestamp("2025-06-01")   # 2025-06-30 - 29
    assert kaynak.erken_kesim(dunya, "SS24") == pd.Timestamp("2024-06-02")   # 2024-07-01 - 29
    assert kaynak.erken_kesim(dunya, "SS23") == pd.Timestamp("2023-06-04")
    assert isinstance(kaynak.erken_kesim(dunya, "SS25"), pd.Timestamp)
    with pytest.raises(KeyError):
        kaynak.erken_kesim(dunya, "AW99")


# ---------------------------------------------------------------- günlük matrisler

# (hücre) g0…g13; satış brüt, iade hariç
SATIS_M1 = [2, 2, 2, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0]
STOKLU_M1 = [1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1]
SATIS_M2 = [1, 1, 1] + [0] * 11
STOKLU_M2 = [1, 1, 1] + [0] * 11
SATIS_ONL = [1] * 6 + [0] * 8
STOKLU_ONL = [1] * 6 + [0] * 8


def test_gunluk_matrisler_degerler(dunya, tablolar):
    s, f = kaynak.gunluk_matrisler(tablolar, dunya, gun(14))
    C = len(dunya.hucre_magaza)
    assert s.shape == f.shape == (GUN_G0 + 14, C) and f.dtype == bool
    for m, sat, stk in ((M1, SATIS_M1, STOKLU_M1), (M2, SATIS_M2, STOKLU_M2), (ONL, SATIS_ONL, STOKLU_ONL)):
        c = _hucre(dunya, m, SKU_A1)
        assert s[GUN_G0:, c].tolist() == sat, m
        assert f[GUN_G0:, c].tolist() == [bool(x) for x in stk], m
        assert not s[:GUN_G0, c].any() and not f[:GUN_G0, c].any()      # veri öncesi: 0 / stoksuz
    # izlenmeyen hücre: ne satış ne stok
    diger = np.ones(C, dtype=bool)
    diger[[_hucre(dunya, m, SKU_A1) for m in (M1, M2, ONL)]] = False
    assert not s[:, diger].any() and not f[:, diger].any()


def test_gunluk_matrisler_bit_haric(dunya, tablolar):
    bit = gun(5)
    s, f = kaynak.gunluk_matrisler(tablolar, dunya, bit)
    assert s.shape[0] == f.shape[0] == (bit - DUNYA_BASI).days
    c = _hucre(dunya, M1, SKU_A1)
    assert s[GUN_G0:, c].tolist() == SATIS_M1[:5]        # g4 son satır; g5 (bit) yok
    # ön ek tutarlılığı: daha geç bir bit aynı günleri aynı verir
    s2, f2 = kaynak.gunluk_matrisler(tablolar, dunya, gun(14))
    assert np.array_equal(s, s2[:len(s)]) and np.array_equal(f, f2[:len(f)])
    # bit'ten sonraki veriyi bozmak sonucu değiştirmez (sızıntı yok)
    bozuk = {ad: df.copy() for ad, df in tablolar.items()}
    sa = bozuk["satis"]
    sonra = sa["tarih"] >= bit
    sa.loc[sonra, "adet"] = sa.loc[sonra, "adet"] * 7 + 3
    s3, f3 = kaynak.gunluk_matrisler(bozuk, dunya, bit)
    assert np.array_equal(s, s3) and np.array_equal(f, f3)


def test_gunluk_matrisler_iade_haric(dunya, tablolar):
    s, f = kaynak.gunluk_matrisler(tablolar, dunya, gun(14))
    c = _hucre(dunya, M1, SKU_A1)
    # g7: tablolarda yalnız -1'lik iade satırı var; brüt satış 0 (net -1 değil)
    iade = tablolar["satis"].query("adet < 0")
    assert iade["tarih"].tolist() == [gun(7)] and iade["magaza_id"].tolist() == ["M1"]
    assert s[GUN_G0 + 7, c] == 0
    assert (s >= 0).all()
    assert s[GUN_G0:, c].sum() == 9        # 2+2+2+1+1+1; mükerrer satır sayılmaz, iade düşmez


def test_gunluk_matrisler_stoklu_ortak_tanim(dunya, tablolar):
    """stoklu = ortak `stok.gunluk_*`'in satış öncesi > 0 (= `durum != 'bos'`) tanımı;
    `Gorunum.stoklu_gecmisi` de aynı anlamdadır (satıştan önceki raf > 0)."""
    from perakende_analitik import stok
    con = oyuncak_baglan(tablolar)
    try:
        m = stok.gunluk_magaza(con, gun(0), gun(13))
        o = stok.gunluk_online(con, gun(0), gun(13))
    finally:
        con.close()
    _, f = kaynak.gunluk_matrisler(tablolar, dunya, gun(14))
    for tablo, kimlik, mag in ((m, "M1", M1), (o, "ONL", ONL)):
        t = tablo[(tablo["urun_id"] == IZLENEN) & (tablo["magaza_id"] == kimlik)]
        assert len(t) == 14
        assert f[GUN_G0:, _hucre(dunya, mag, SKU_A1)].tolist() == (t["satis_oncesi"] > 0).tolist()


def test_gunluk_matrisler_bit_veri_oncesi_bos(dunya, tablolar):
    s, f = kaynak.gunluk_matrisler(tablolar, dunya, DUNYA_BASI)
    assert s.shape == f.shape == (0, len(dunya.hucre_magaza))
    s, f = kaynak.gunluk_matrisler(tablolar, dunya, gun(0))
    assert s.shape[0] == GUN_G0 and not s.any() and not f.any()


def test_gunluk_matrisler_takvim_disi_bit(dunya, tablolar):
    with pytest.raises(ValueError):
        kaynak.gunluk_matrisler(tablolar, dunya, DUNYA_BASI - pd.Timedelta(days=1))
    with pytest.raises(ValueError):
        kaynak.gunluk_matrisler(tablolar, dunya, DUNYA_BASI + pd.Timedelta(days=22))


def test_yayimlanan_tablolar_ad_sirasi_ve_icerik(tablolar):
    con = oyuncak_baglan(tablolar)
    try:
        t = kaynak.yayimlanan_tablolar(con, ["satis", "stok"])
    finally:
        con.close()
    assert list(t) == ["satis", "stok"]
    assert len(t["satis"]) == len(tablolar["satis"]) and len(t["stok"]) == len(tablolar["stok"])


# ---------------------------------------------------------------- gerçek veri


@pytest.mark.veri
def test_ss25_olcegi():
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.TAM)
    o = kaynak.oyun_optionlari(w, sabitler.OYUN_SEZONU)
    assert len(o) == 210
    h = kaynak.harita_kur(w)
    assert np.bincount(h.option_dalga[o])[1:].tolist() == [66, 75, 69]
    assert (h.option_line[o] == sabitler.LINE).all() and (h.option_sezon[o] == "SS25").all()
    assert h.magaza_fiziksel.sum() == 74           # 85 mağaza: 10 Outlet + ONL hariç
    assert h.magaza_istanbul[h.magaza_fiziksel].sum() > 0
    assert kaynak.erken_kesim(w, "SS25") == pd.Timestamp("2025-06-01")


@pytest.mark.veri
def test_erken_kesim_ss25_ss24():
    """Yayımlanan `sezon` tablosundan: kesim = indirim_baslangic - 29 gün.

    SS24 için Global Constraints'teki "2024-06-01" bir hesap kaymasıdır: indirim 2024-07-01,
    29 gün öncesi 2024-06-02 (SS25: 2025-06-30 -> 2025-06-01)."""
    from types import SimpleNamespace

    con = kaynak.baglan()
    try:
        w = SimpleNamespace(sezon=con.execute("select * from sezon").df())
    finally:
        con.close()
    assert kaynak.erken_kesim(w, "SS25") == pd.Timestamp("2025-06-01")
    assert kaynak.erken_kesim(w, "SS24") == pd.Timestamp("2024-06-02")


@pytest.mark.veri
def test_gunluk_matrisler_yayimlanan_veri():
    """Yayımlanan tablolardan kurulan matrisler: ortak günlük tablonun doğrudan okunmuşuyla aynı."""
    from perakende_analitik import stok
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    w = dunya_kur(Olcek.TAM)
    bit = pd.Timestamp("2023-03-06")
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, kaynak.GUNLUK_TABLOLARI)
        s, f = kaynak.gunluk_matrisler(t, w, bit)
        dogrudan = pd.concat([stok.gunluk_magaza(con, "2023-01-02", "2023-03-05"),
                              stok.gunluk_online(con, "2023-01-02", "2023-03-05")])
    finally:
        con.close()
    gun0 = pd.Timestamp(w.takvim["tarih"].iloc[0])
    assert s.shape == f.shape == ((bit - gun0).days, len(w.hucre_magaza))
    assert f.sum() == (dogrudan["durum"] != "bos").sum()
    assert s.sum() > 0 and (s >= 0).all()
