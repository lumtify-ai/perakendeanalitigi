from dataclasses import replace
from datetime import date

import pandas as pd

from blok_transfer.cekirdek import adaylar, metrikler
from blok_transfer.cekirdek.parametreler import Parametreler

from conftest import HAFTALAR

KARAR = date(2025, 12, 29)
P = Parametreler()  # verici_cover_esigi=6, min_satis=1


def ciftler(df):
    return set(zip(df.verici, df.alici, df.option_id))


def test_beklenen_uc_aday(con):
    # OPT3 (MA, cover 16) verici olur ama hızı ≥ 1 olan alıcısı yok → aday doğmaz
    df = adaylar.uret(con, KARAR, P)
    assert ciftler(df) == {
        ("MA", "MB", "OPT1"),   # kırık + hızlı alıcı
        ("MA", "MC", "OPT1"),   # stoksuz alıcı
        ("MA", "MC", "OPT2"),   # stoksuz outlet alıcı
    }


def test_soguma_vericiyi_eler(con):
    # MD-OPT1: cover 10/0.125 = 80 ≥ 6 ama 2025-12-22 sevkiyatı soğumada
    df = adaylar.uret(con, KARAR, P)
    assert not (df.verici == "MD").any()


def test_line_kurali_outlet_urunu_vitrine_gitmez(con):
    # MB-OPT2 kırık ve hızlı (3/hafta) ama OPT2 line=Outlet, MB tip=Cadde
    df = adaylar.uret(con, KARAR, P)
    assert ("MA", "MB", "OPT2") not in ciftler(df)


def test_esikler_senaryo_parametresi(con):
    dar = adaylar.uret(con, KARAR, replace(P, min_satis=2.0))
    assert ("MA", "MC", "OPT1") not in ciftler(dar)          # MC-OPT1 hız 1 < 2
    cok_dar = adaylar.uret(con, KARAR, replace(P, verici_cover_esigi=30.0))
    assert ciftler(cok_dar) == {("MA", "MC", "OPT2")}        # MA-OPT1 cover 24, MA-OPT3 16 < 30
    assert cok_dar.iloc[0].adet == 8                         # blok = vericinin tüm stoğu


def test_kapasite_boslugu(con):
    # bosluk = max(0, tepe − karar günü stok); tepe = 8 haftalık fotoğrafların
    # mağaza toplamının en büyüğü (elle; fikstür docstring'inde de):
    #   MA 24−24=0 · MB 11−6=5 · MC 8−0=8 · MD 10−10=0 (hayalet 2 sayılmaz) · ME 5−5=0
    b = adaylar.kapasite_boslugu(con, KARAR)
    assert b == {"MA": 0, "MB": 5, "MC": 8, "MD": 0, "ME": 0}
    assert all(isinstance(v, int) for v in b.values())


def test_kapasite_tepe_stoktan(con):
    # MC tepesi ilk 4 haftada (8 adet), sonra 5. Pencere alt sınırı dahil:
    # tepe_hafta=5 → [11-24, 12-29) tepeyi içerir, tepe_hafta=4 → [12-01, 12-29) içermez.
    assert adaylar.kapasite_boslugu(con, KARAR, tepe_hafta=5)["MC"] == 8
    assert adaylar.kapasite_boslugu(con, KARAR, tepe_hafta=4)["MC"] == 5
    # geçmişi olmayan mağaza 0 (kapasite kolonu artık hesaba girmez)
    con.execute("insert into magaza values ('MZ', 'Yeni', 'Bursa', 'Cadde', 9999, '2020-01-01', NULL)")
    assert adaylar.kapasite_boslugu(con, KARAR)["MZ"] == 0
    # karar günü stoğu tepeyi aşarsa boşluk negatif olmaz
    con.execute("insert into stok values ('2025-12-29', 'MB', 'OPT3-1', 100)")
    con.execute("insert into satis values ('2025-12-01', 'MB', 'OPT3-1', 1)")
    assert adaylar.kapasite_boslugu(con, KARAR)["MB"] == 0


def test_kapasite_yalniz_evren_magazalari(con):
    assert set(adaylar.kapasite_boslugu(con, KARAR)) == {"MA", "MB", "MC", "MD", "ME"}


def test_cok_siki_esikte_bos_ama_dogru_bicimli_cerceve(con):
    # Eşikler her şeyi elediğinde çökmemeli; kolonlar korunmalı (çözücüler
    # boş çerçeveyi bu kolonlarla bekliyor).
    bos = adaylar.uret(con, KARAR, replace(P, min_satis=99.0))
    assert len(bos) == 0
    assert list(bos.columns) == adaylar.KOLONLAR


def test_aday_sirasi_deterministik(con):
    # DuckDB sorgularinda ORDER BY yok; sira oynarsa MIP degisken adlandirmasi
    # oynar ve cozucu esit degerli optimumlar arasinda baska birini dondurur.
    df = adaylar.uret(con, KARAR, P)
    anahtar = list(zip(df.verici, df.alici, df.option_id))
    assert anahtar == sorted(anahtar)


def test_tavan_kapaliyken_bugunku_model(con):
    # Varsayılan tavan 0: ME-OPT1 ne kırık ne stoksuz, aday olamaz.
    # Bu, tasarımın geriye dönük uyum kilidi.
    df = adaylar.uret(con, KARAR, P)
    assert ciftler(df) == {
        ("MA", "MB", "OPT1"),
        ("MA", "MC", "OPT1"),
        ("MA", "MC", "OPT2"),
    }


def test_tavan_mali_bitmek_uzere_aliciyi_acar(con):
    # ME-OPT1 cover 5/2.0 = 2.5; tavan 3 onu alıcı yapar, tavan 2 yapmaz.
    genis = adaylar.uret(con, KARAR, replace(P, alici_cover_tavani=3.0))
    assert ("MA", "ME", "OPT1") in ciftler(genis)
    dar = adaylar.uret(con, KARAR, replace(P, alici_cover_tavani=2.0))
    assert ("MA", "ME", "OPT1") not in ciftler(dar)


def test_tavan_min_satisi_ezmez(con):
    # MA-OPT1 cover 24 ama hızı 0.5 < min_satis 1 → tavan ne olursa olsun alıcı değil
    df = adaylar.uret(con, KARAR, replace(P, alici_cover_tavani=999.0))
    assert not (df.alici == "MA").any()


def test_aday_alis_kolonu(con):
    df = adaylar.uret(con, KARAR, P)
    assert adaylar.KOLONLAR[-2:] == ["fiyat", "alis"]
    assert list(df.columns) == adaylar.KOLONLAR
    assert (df.fiyat == 100.0).all() and (df.alis == 40.0).all()


def test_karar_sonrasi_satirlar_cekirdegi_degistirmez(con, con_ileri):
    # con_ileri ayrı bağlantı: karar+1 hafta satış, varış (vericiye de) ve stok
    # fotoğrafı ekli. Hiçbiri çekirdeğin çıktısına sızmamalı.
    pd.testing.assert_frame_equal(adaylar.uret(con, KARAR, P), adaylar.uret(con_ileri, KARAR, P))
    assert adaylar.kapasite_boslugu(con, KARAR) == adaylar.kapasite_boslugu(con_ileri, KARAR)
    assert adaylar._sogumada(con, KARAR, 2) == adaylar._sogumada(con_ileri, KARAR, 2)
    for f in (lambda c: metrikler.strler(c, KARAR), lambda c: metrikler.hizlar(c, KARAR, 8)):
        pd.testing.assert_frame_equal(
            f(con).sort_values(["magaza_id", "option_id"]).reset_index(drop=True),
            f(con_ileri).sort_values(["magaza_id", "option_id"]).reset_index(drop=True),
        )
    # sızıntı olsaydı MA-OPT1 (karar+1 hafta varışı) soğumaya girer, aday düşerdi
    assert ("MA", "MB", "OPT1") in ciftler(adaylar.uret(con_ileri, KARAR, P))


def _opt3_hucresi(con, magaza, stok_karar, satis=2):
    """`magaza`da OPT3: 8 hafta stoklu (3) ve haftada `satis` satan; karar günü `stok_karar`."""
    for hafta in HAFTALAR:
        con.execute("insert into stok values (?, ?, 'OPT3-1', 3)", [hafta, magaza])
        con.execute("insert into satis values (?, ?, 'OPT3-1', ?)", [hafta, magaza, satis])
    con.execute("insert into stok values ('2025-12-29', ?, 'OPT3-1', ?)", [magaza, stok_karar])


def test_hayalet_stok_verici_olmaz(con):
    # MD-OPT3-1: yalnız karar günü, adet 7, varışsız, satışsız = hayalet.
    # Süzülmeseydi cover 999 ile verici olur, alıcılı OPT3'te aday doğardı.
    con.execute("insert into stok values ('2025-12-29', 'MD', 'OPT3-1', 7)")
    _opt3_hucresi(con, "MB", stok_karar=0)            # OPT3 için gerçek alıcı
    df = adaylar.uret(con, KARAR, P)
    assert not (df.verici == "MD").any()
    assert ("MA", "MB", "OPT3") in ciftler(df)       # gerçek verici (MA) etkilenmedi
    # fikstürün kendi hayaleti (MD-OPT2-3, 12-15) da hiçbir metrikte yok
    hiz = metrikler.hizlar(con, KARAR, 8)
    assert len(hiz[(hiz.magaza_id == "MD") & (hiz.option_id == "OPT2")]) == 0


def test_kirik_hucre_verici_olmaz(con):
    # Karar R4: kırık (mağaza, option) hücresi verici olamaz. Kırığın satışı
    # durur, cover → ∞ görünür; cover tek başına onu verici sayardı.
    # MC-OPT1'e karar günü yalnız beden 1'de 10 adet koy: toplam > 0, ara
    # kademeler 0 → kırık; hız 1.0 → cover 10 ≥ 6, soğumada da değil.
    con.execute("update stok set adet = 10 where tarih = '2025-12-29' "
                "and magaza_id = 'MC' and urun_id = 'OPT1-1'")
    assert ("MC", "OPT1") in set(zip(*[metrikler.kiriklar(con, KARAR)[c] for c in ("magaza_id", "option_id")]))
    cov = metrikler.coverlar(con, KARAR, P)
    assert cov[(cov.magaza_id == "MC") & (cov.option_id == "OPT1")].cover.iloc[0] >= P.verici_cover_esigi
    df = adaylar.uret(con, KARAR, P)
    assert ("MC", "MB", "OPT1") not in ciftler(df)    # kırık verici → kırık alıcı
    assert not (df.verici == "MC").any()
    assert ("MA", "MB", "OPT1") in ciftler(df)        # sağlam verici etkilenmedi


def test_std_option_kirik_sayilmaz(con):
    # OPT3 tek bedenli: ara kademesi yok, kırık olamaz. MB'de stoksuz+hızlı →
    # alıcı; MC'de stoklu (2) + hızlı (3) → kırık sayılsaydı alıcı olurdu.
    assert "OPT3" not in set(metrikler.kiriklar(con, KARAR).option_id)
    _opt3_hucresi(con, "MB", stok_karar=0)
    _opt3_hucresi(con, "MC", stok_karar=2, satis=3)
    assert "OPT3" not in set(metrikler.kiriklar(con, KARAR).option_id)
    df = adaylar.uret(con, KARAR, P)
    assert ("MA", "MB", "OPT3") in ciftler(df)       # stoksuz ve hızlı
    assert ("MA", "MC", "OPT3") not in ciftler(df)   # stoklu, kırık değil


def _varis_ekle(con, urun, hedef, varis, tip="elle_transfer", sevk_tarihi=None):
    """`varis` None ise yolda kalmış sevkiyat (varış tarihi boş)."""
    varis_sql = "NULL" if varis is None else f"timestamp '{varis}'"
    con.execute(
        f"insert into sevkiyat values (?, {varis_sql}, 'MX', ?, ?, 3, ?)",
        [sevk_tarihi or varis, hedef, urun, tip],
    )


def test_soguma_her_sevkiyat_turunde_ve_varista(con):
    assert ("MD", "OPT1") in adaylar._sogumada(con, KARAR, 2)         # replenishment
    # elle transfer varışı da soğutur → MA-OPT1 verici olmaktan çıkar
    _varis_ekle(con, "OPT1-1", "MA", "2025-12-22", tip="elle_transfer")
    assert ("MA", "OPT1") in adaylar._sogumada(con, KARAR, 2)
    assert ciftler(adaylar.uret(con, KARAR, P)) == {("MA", "MC", "OPT2")}
    # yolda kalan (varışı boş) sokmaz: sevk tarihi pencerede ama varmadı
    _varis_ekle(con, "OPT2-1", "MA", None, sevk_tarihi="2025-12-24")
    assert ("MA", "OPT2") not in adaylar._sogumada(con, KARAR, 2)
    assert ("MA", "MC", "OPT2") in ciftler(adaylar.uret(con, KARAR, P))
    # sınırlar: varış karar−2 hafta (12-15) dışarıda, karar günü içeride
    _varis_ekle(con, "OPT1-1", "ME", "2025-12-15")
    _varis_ekle(con, "OPT1-1", "MB", "2025-12-29")
    sogumada = adaylar._sogumada(con, KARAR, 2)
    assert ("ME", "OPT1") not in sogumada
    assert ("MB", "OPT1") in sogumada
    # ölçüt sevk tarihi değil varış: erken sevk, pencerede varış
    _varis_ekle(con, "OPT2-1", "MC", "2025-12-24", sevk_tarihi="2025-12-01")
    assert ("MC", "OPT2") in adaylar._sogumada(con, KARAR, 2)
