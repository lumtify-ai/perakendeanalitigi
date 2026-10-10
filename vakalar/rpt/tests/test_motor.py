"""`rpt.motor`: üretecin tek kapısı, koşu önbelleği, gizli gerçek.

Hızlı testler KÜÇÜK dünyada kısa koşu yapar (pencere 181. günde başlar;
`GUN` günlük koşu pencereye ~80 gün girer). `veri` işaretli testler TAM
dünya ister; eşdeğerlik testi bir tam koşudur (~4 dk, ~6 GB; sonucu
`cikti/kosular/` önbelleğine yazılır, sonraki çağrılar oradan okur).
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

from rpt import motor

GUN = 260   # KÜÇÜK dünyada kısa koşu: [0, 260) günü, pencere 181'de başlar
KUCUK = {"olcek": "kucuk", "gun_sayisi": GUN}


# ---------------------------------------------------------------------------
# Önbellek anahtarı
# ---------------------------------------------------------------------------


def _kaynak_agaci(kok):
    """Üç kaynak kökünü taklit eden geçici ağaç. rpt: listedeki (motor,
    politika) ve dışındaki (hikaye) modüller; ortak: tohumdan (kaynak, stok)
    ve rpt'nin içe aktarmasından (ekstra > derin) ulaşılanlar, ulaşılmayan hakem."""
    (kok / "rpt").mkdir(parents=True)
    (kok / "rpt" / "motor.py").write_bytes(b"a = 1\n")
    (kok / "rpt" / "politika.py").write_bytes(b"from perakende_analitik import ekstra\n")
    (kok / "rpt" / "hikaye.py").write_bytes(b"h = 1\n")
    (kok / "rpt" / "notlar.txt").write_bytes(b"py olmayan dosya\n")
    o = kok / "ortak"
    o.mkdir()
    (o / "kaynak.py").write_bytes(b"c = 3\n")
    (o / "stok.py").write_bytes(b"from perakende_analitik import kaynak\n")
    (o / "ekstra.py").write_bytes(b"def f():\n    from perakende_analitik.derin import x\n")
    (o / "derin.py").write_bytes(b"x = 1\n")
    (o / "hakem.py").write_bytes(b"import perakende_veri\n")
    (kok / "v4" / "motor").mkdir(parents=True)
    (kok / "v4" / "motor" / "dongu.py").write_bytes(b"d = 4\n")
    return {"rpt": kok / "rpt", "ortak": o, "v4": kok / "v4"}


def test_onbellek_anahtari_duyarli(tmp_path, monkeypatch):
    """Anahtarın her bileşeni anahtarı değiştirir: ad, parametreler, iki
    tohum, ölçek, gün sayısı, politika türü, koşuyu etkileyen her kaynak (rpt
    listesi, ortak kapanış, v4), v4 dosyasının parmak izi. Değiştirmeyenler:
    parametre sözlüğünün sırası, satır sonları (CRLF/LF), `.py` dışı dosya,
    koşu dışı rpt modülü (hikaye; listede olmayan yeni modül), ortak
    kapanışa girmeyen modül (hakem)."""
    monkeypatch.setattr(motor, "KOD_KOKLERI", _kaynak_agaci(tmp_path / "kod"))
    db = tmp_path / "v4.duckdb"
    db.write_bytes(b"0" * 100)
    monkeypatch.setattr(motor, "VERI_YOLU", db)

    temel = dict(ad="kol", parametreler={"esik": 0.55, "hafta": [3, 6]}, talep_tohumu=None,
                 operasyon_tohumu=motor.TOHUM, olcek="tam", gun_sayisi=None, turler={})
    a0 = motor.onbellek_anahtari(**temel)
    assert a0 == motor.onbellek_anahtari(**temel)
    assert sorted(motor.kod_dosyalari()) == [
        "ortak/derin.py", "ortak/ekstra.py", "ortak/kaynak.py", "ortak/stok.py",
        "rpt/motor.py", "rpt/politika.py", "v4/motor/dongu.py"]

    degisik = {
        "ad": "baska_kol",
        "parametreler": {"esik": 0.56, "hafta": [3, 6]},
        "talep_tohumu": 20261010,
        "operasyon_tohumu": motor.TOHUM + 1,
        "olcek": "kucuk",
        "gun_sayisi": 100,
        "turler": {"rpt": "rpt.politika.Oneri"},
    }
    for alan, deger in degisik.items():
        assert motor.onbellek_anahtari(**{**temel, alan: deger}) != a0, alan
    assert motor.onbellek_anahtari(**{**temel, "parametreler": {"esik": 0.55, "hafta": [3, 6], "yeni": 1}}) != a0
    # Sözlük sırası anahtarı değiştirmez
    assert motor.onbellek_anahtari(**{**temel, "parametreler": {"hafta": [3, 6], "esik": 0.55}}) == a0
    # JSON'a dönmeyen parametre (ör. çağrılabilir) açıkça reddedilir
    with pytest.raises(TypeError):
        motor.onbellek_anahtari(**{**temel, "parametreler": {"f": len}})

    kod = tmp_path / "kod"
    for dosya, icerik in (                                    # değiştirmeyenler
        (kod / "rpt" / "notlar.txt", b"degisti\n"),
        (kod / "rpt" / "motor.py", b"a = 1\r\n"),
        (kod / "rpt" / "hikaye.py", b"h = 2\n"),
        (kod / "rpt" / "yeni.py", b"y = 1\n"),
        (kod / "ortak" / "hakem.py", b"import perakende_veri.v4\n"),
    ):
        dosya.write_bytes(icerik)
        assert motor.onbellek_anahtari(**temel) == a0, dosya
    for dosya, icerik in (                                    # değiştirenler
        (kod / "rpt" / "politika.py", b"from perakende_analitik import ekstra\nk = 1\n"),
        (kod / "rpt" / "kahin.py", b""),                      # listede, sonradan yazılan modül
        (kod / "ortak" / "stok.py", b"from perakende_analitik import kaynak\ns = 1\n"),
        (kod / "ortak" / "derin.py", b"x = 2\n"),             # politika > ekstra > derin
        (kod / "v4" / "motor" / "dongu.py", b"d = 44\n"),
    ):
        once = motor.onbellek_anahtari(**temel)
        dosya.write_bytes(icerik)
        assert motor.onbellek_anahtari(**temel) != once, dosya

    # v4 parmak izi: boyut ve değişiklik zamanı
    once = motor.onbellek_anahtari(**temel)
    db.write_bytes(b"0" * 101)
    assert motor.onbellek_anahtari(**temel) != once
    once = motor.onbellek_anahtari(**temel)
    st = db.stat()
    os.utime(db, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert motor.onbellek_anahtari(**temel) != once
    once = motor.onbellek_anahtari(**temel)
    db.unlink()
    assert motor.onbellek_anahtari(**temel) != once


def test_kod_kaynaklari_gercek_dosyalari_kapsar():
    """Gerçek kaynaklar: koşu modülleri ve ortak kapanış girer; ölçüm,
    anlatı ve hakem girmez; sürümler lightgbm ve scikit-learn'ü taşır."""
    adlar = motor.kod_dosyalari()
    for a in ("rpt/motor.py", "rpt/bilgi.py", "rpt/kaynak.py", "rpt/politika.py", "rpt/dagitim.py",
              "ortak/kaynak.py", "ortak/stok.py", "ortak/ozellikler.py", "ortak/carpanlar.py",
              "ortak/talep.py", "ortak/hazirlik.py", "ortak/agac.py", "ortak/kayip.py",
              "v4/motor/dongu.py", "v4/politika.py"):
        assert a in adlar, a
    for a in ("rpt/hikaye.py", "rpt/olcutler.py", "rpt/yollar.py", "rpt/__init__.py",
              "ortak/hakem.py", "ortak/sayi_denetimi.py", "ortak/degerlendir.py"):
        assert a not in adlar, a
    surum = motor.anahtar_icerigi(ad="a", parametreler={}, talep_tohumu=None, operasyon_tohumu=1,
                                  olcek="tam", gun_sayisi=None, turler={})["surumler"]
    assert surum["lightgbm"] and surum["scikit-learn"] and surum["numpy"]


def _rpt_kapanisi(baslangic):
    """rpt paketi içinde `baslangic` modüllerinden içe aktarmayla ulaşılanlar."""
    var = {y.stem for y in motor.PAKET_KOKU.glob("*.py")}
    gorulen, sira = set(), [m for m in baslangic if m in var]
    while sira:
        m = sira.pop()
        if m in gorulen:
            continue
        gorulen.add(m)
        for ad in motor.ice_aktarimlar(motor.PAKET_KOKU / f"{m}.py", "rpt"):
            parca = ad.split(".")
            if parca[0] == "rpt" and len(parca) > 1 and parca[1] in var:
                sira.append(parca[1])
    return gorulen


def test_kosu_modulleri_listesi_kapali():
    """rpt/'deki her modül ya koşuyu etkiler (KOSU_MODULLERI) ya etkilemez
    (KOSU_DISI). Politika tarafının (politika, dagitim, kahin, motor) içe
    aktardığı her rpt modülü listededir; oyun'un kapanışında liste dışı
    yalnız KOSU_DISI olabilir (ölçüm: sonucu politikaya girerse
    `parametreler`'e girer)."""
    liste, disi = set(motor.KOSU_MODULLERI), set(motor.KOSU_DISI)
    var = {y.stem for y in motor.PAKET_KOKU.glob("*.py")} - {"__init__"}
    assert var <= liste | disi, f"sınıflandırılmamış rpt modülü: {var - liste - disi}"
    assert not liste & disi
    politika_tarafi = _rpt_kapanisi(("politika", "dagitim", "kahin", "motor"))
    assert {"motor", "bilgi", "politika", "miktar"} <= politika_tarafi   # tarama boş dönmüyor
    assert politika_tarafi <= liste, politika_tarafi - liste
    oyun = _rpt_kapanisi(("oyun",))
    assert "politika" in oyun and oyun - disi <= liste, oyun - disi - liste


# ---------------------------------------------------------------------------
# Koşu ve önbellek
# ---------------------------------------------------------------------------


def _ayni_kosu(a, b):
    assert sorted(a.tablolar) == sorted(b.tablolar)
    for ad in a.tablolar:
        pd.testing.assert_frame_equal(a.tablolar[ad], b.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(a.gercek, b.gercek, obj="gercek")
    assert sorted(a.kayitlar) == sorted(b.kayitlar)
    for ad in a.kayitlar:
        pd.testing.assert_frame_equal(a.kayitlar[ad], b.kayitlar[ad], obj=ad)


class _KayitliRPT:
    """Lumoda'nın RPT'sini sarar, verdiği her siparişi kaydeder (`kayit_tablosu`)."""

    def __init__(self):
        from perakende_veri.v4.politika import LumodaRPT

        self.ic = LumodaRPT()
        self.satirlar = []

    def __call__(self, g):
        s = self.ic(g)
        self.satirlar += [(g.gun, o, m) for o, m in s.items()]
        return s

    def kayit_tablosu(self):
        return pd.DataFrame(self.satirlar, columns=["gun", "option", "adet"], dtype="int64")


def test_onbellek_ikinci_cagrida_kosmaz(tmp_path, monkeypatch):
    """İlk çağrı koşar ve yazar; aynı anahtarla ikinci çağrı motoru hiç
    çağırmadan aynı koşuyu (tablolar, gizli gerçek, politika kayıtları)
    döndürür. Başka anahtar yeniden koşar; yarım yazılmış kayıt okunmaz."""
    ilk = motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert not ilk.onbellekten
    assert ilk.meta["ad"] == "lumoda_kayitli" and ilk.meta["gun_sayisi"] == GUN
    assert "rpt" in ilk.kayitlar
    if sys.platform == "win32":
        assert ilk.meta["tepe_bellek_gb"] > 0
    assert len(list(tmp_path.iterdir())) == 1

    def yasak(*a, **k):
        raise AssertionError("önbellekteki koşu yeniden koşturuldu")

    monkeypatch.setattr(motor, "simule_et", yasak)
    ikinci = motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert ikinci.onbellekten
    _ayni_kosu(ilk, ikinci)
    assert ikinci.meta == ilk.meta

    # Başka anahtar (talep tohumu) önbellekte yok: koşmaya çalışır
    with pytest.raises(AssertionError, match="yeniden"):
        motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, talep_tohumu=7,
                  onbellek=tmp_path, **KUCUK)

    # meta.json yazımın son adımıdır: o yoksa kayıt yarımdır ve okunmaz
    (dizin,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    (dizin / "meta.json").unlink()
    with pytest.raises(AssertionError, match="yeniden"):
        motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)


def test_bozuk_kayit_ve_artiklar(tmp_path):
    """Meta'sı tam ama Parquet'i bozuk ya da eksik kayıt silinir ve yeniden
    koşulur; bu süreçten eski `.yaziliyor-*` artığı silinir, yenisi kalır."""
    ilk = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    (dizin,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    (dizin / "tablo_satis.parquet").write_bytes(b"bozuk")
    with pytest.warns(UserWarning, match="bozuk"):
        ikinci = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert not ikinci.onbellekten
    _ayni_kosu(ilk, ikinci)
    (dizin / "gercek.parquet").unlink()
    with pytest.warns(UserWarning, match="bozuk"):
        assert not motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK).onbellekten
    assert motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK).onbellekten

    eski, yeni = tmp_path / "x_1.yaziliyor-1", tmp_path / "x_2.yaziliyor-2"
    eski.mkdir()
    yeni.mkdir()
    os.utime(eski, (1_000_000_000, 1_000_000_000))
    os.utime(yeni, (motor._SUREC_BASI + 3600, motor._SUREC_BASI + 3600))
    motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert not eski.exists() and yeni.exists()


def test_tembel_kosu_kaydi(tmp_path, monkeypatch):
    """`tembel=True`: büyük tablolar bellekte değil, istendikçe diskten okunur
    (`KosuKaydi`); okunan her tablo ve süzülen satırlar tam koşununkiyle aynı.
    Önbelleksiz tembel koşu yoktur; eksik Parquet'li kayıt yeniden koşulur."""
    tam = motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    k = motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path,
                  tembel=True, **KUCUK)
    assert isinstance(k, motor.KosuKaydi) and k.onbellekten and k.meta == tam.meta
    assert sorted(k.tablolar) == sorted(tam.tablolar)
    for ad in ("satis", "urun", "siparis"):
        pd.testing.assert_frame_equal(k.tablolar[ad], tam.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(k.gercek, tam.gercek)
    pd.testing.assert_frame_equal(k.kayitlar["rpt"], tam.kayitlar["rpt"])
    urunler = sorted(set(tam.tablolar["satis"]["urun_id"].astype(str)))[:7]
    for kosu in (k, tam):
        s = kosu.tablo("satis", sutunlar=["tarih", "urun_id", "adet"], urunler=urunler)
        assert list(s.columns) == ["tarih", "urun_id", "adet"] and len(s) > 0
        assert set(s["urun_id"].astype(str)) <= set(urunler)
        g = kosu.tablo("gercek", urunler=urunler)
        assert set(g["urun_id"].astype(str)) <= set(urunler)
    a = k.tablo("satis", sutunlar=["tarih", "urun_id", "adet"], urunler=urunler)
    b = tam.tablo("satis", sutunlar=["tarih", "urun_id", "adet"], urunler=urunler)
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(k.yukle().tablolar["stok"], tam.tablolar["stok"])

    with pytest.raises(ValueError, match="tembel"):
        motor.kos(ad="lumoda", parametreler={}, onbellek=None, tembel=True, **KUCUK)

    (k.dizin / "tablo_stok.parquet").unlink()
    with pytest.warns(UserWarning, match="eksik"):
        yeni = motor.kos(rpt=_KayitliRPT(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path,
                         tembel=True, **KUCUK)
    assert not yeni.onbellekten and (yeni.dizin / "tablo_stok.parquet").exists()


def test_yayimlanan_bicim_yayimla_ile_ayni():
    """KÜÇÜK dünyada tam koşu: `yayimlanan_bicim(hareket_tablolari)` =
    `uret.yayimla` (kirletme adımı birebir)."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.tablolar import hareket_tablolari
    from perakende_veri.v4.uret import yayimla

    w = motor.dunya("kucuk")
    ham = simule_et(w)
    beklenen = yayimla(w, ham)
    yeni = motor.yayimlanan_bicim(hareket_tablolari(w, ham), "kucuk")
    assert sorted(yeni) == sorted(beklenen)
    for ad in beklenen:
        pd.testing.assert_frame_equal(yeni[ad], beklenen[ad], obj=ad)


def _parquet_turu(df):
    """Parquet gidiş-dönüşü bellekte (yayımlama `to_parquet(index=False)`;
    koşu tabloları da Parquet'ten döner: kategori adı gibi üst veri düşer)."""
    import io

    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


def test_kos_varsayilan_lumoda_ve_tohum():
    """Politika verilmezse Lumoda: tablolar `hareket_tablolari`'nın Parquet
    gidiş-dönüşü; talep tohumu talebi değiştirir."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.tablolar import hareket_tablolari

    w = motor.dunya("kucuk")
    k = motor.kos(ad="lumoda", parametreler={}, onbellek=None, **KUCUK)
    ham = simule_et(w, gun_sayisi=GUN)
    beklenen = hareket_tablolari(w, ham)
    assert sorted(k.tablolar) == sorted(beklenen)
    for ad in beklenen:
        pd.testing.assert_frame_equal(k.tablolar[ad], _parquet_turu(beklenen[ad]), obj=ad)
    b = motor.kos(ad="lumoda", parametreler={}, talep_tohumu=20261010, onbellek=None, **KUCUK)
    assert int(b.gercek["talep"].sum()) != int(k.gercek["talep"].sum())


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def test_gercek_kimlikleri():
    """Hücre-gün kimlikleri (hakem tanımı): kendi_satis + karsilanmayan =
    talep, ikameye_giden + kalici_kayip = karsilanmayan; hepsi ≥ 0; satırlar
    pencerede talebi olan hücre-günler. `karsilanmayan > 0` alt kümesi
    hakemin tablosunun kendisidir; toplamlar ham koşuyla tutar."""
    from perakende_analitik import hakem
    from perakende_veri.v4 import tablolar as v4t
    from perakende_veri.v4.motor import simule_et

    k = motor.kos(ad="lumoda", parametreler={}, onbellek=None, **KUCUK)
    g = k.gercek
    assert list(g.columns) == ["tarih", "magaza_id", "urun_id", *motor.GERCEK_SUTUNLARI]
    assert len(g) > 1000
    for s in motor.GERCEK_SUTUNLARI:
        assert g[s].dtype == np.int32 and (g[s] >= 0).all(), s
    assert (g["talep"] > 0).all()
    assert ((g["kendi_satis"] + g["karsilanmayan"]) == g["talep"]).all()
    assert ((g["ikameye_giden"] + g["kalici_kayip"]) == g["karsilanmayan"]).all()
    assert g["tarih"].min() >= pd.Timestamp("2023-01-01")
    assert not g.duplicated(["tarih", "magaza_id", "urun_id"]).any()
    assert (g["kalici_kayip"] > 0).any() and (g["ikameye_giden"] > 0).any()

    w = motor.dunya("kucuk")
    ham = simule_et(w, gun_sayisi=GUN, kayit_talep=True)
    bas, _ = v4t.pencere()
    assert int(g["talep"].sum()) == int(ham["talep"][bas:].sum(dtype=np.int64))
    gk = ham["gizli_kayip"]
    assert int(g["kalici_kayip"].sum()) == int(gk.loc[gk["gun"] >= bas, "adet"].sum())

    hk = hakem.karsilanmayan_tablosu(w, ham)
    alt = g[g["karsilanmayan"] > 0].reset_index(drop=True)
    pd.testing.assert_frame_equal(alt, hk.reset_index(drop=True), check_dtype=False)


# ---------------------------------------------------------------------------
# Politikanın gördüğü
# ---------------------------------------------------------------------------


GIZLI_IZLER = ("gizli", "sapma", "lam", "esneklik", "kapasite", "hatali", "surpriz", "gercek")


def test_politika_gorunumu_kucuk():
    """Option planı (zincir plan λ'sı, lansman → indirim ve haftalık),
    ilk alım, tedarikçi alanları; gizli alan adı yok."""
    w = motor.dunya("kucuk")
    pb = motor.politika_gorunumu(w)
    from rpt.bilgi import PolitikaBilgisi

    assert isinstance(pb, PolitikaBilgisi)
    o = pb.optionlar
    assert list(o["option_id"]) == list(w.optionlar["option_id"])
    for s in ("sezon_kodu", "line", "lansman_tarihi", "indirim_baslangic", "cikis_tarihi",
              "plan_sezon", "plan_cikis", "ilk_alim", "tedarikci_id", "mense", "rpt_hafta",
              "moq_option", "uzmanlik", "ilk_siparis_hafta", "alis_fiyati", "liste_fiyati"):
        assert s in o.columns, s
    for df in (o, pb.plan_hafta):
        for s in df.columns:
            assert not any(iz in s for iz in GIZLI_IZLER), s

    sez = w.optionlar["sezonluk"].to_numpy(dtype=bool)
    lan = w.optionlar["lansman_gun"].to_numpy()
    ind = w.optionlar["indirim_gun"].to_numpy()
    for i in np.flatnonzero(sez)[:25]:
        beklenen = w.ileri_plan_option(int(lan[i]), int(ind[i] - lan[i]))[i]
        assert o["plan_sezon"].iat[i] == pytest.approx(beklenen, rel=1e-9)
    np.testing.assert_array_equal(o["ilk_alim"].to_numpy(), np.asarray(w.ilk_alim))
    assert (o.loc[~sez, "ilk_alim"] == 0).all()
    ted = w.tedarikciler.set_index("tedarikci_id")
    for s in ("rpt_hafta", "moq_option", "mense"):
        np.testing.assert_array_equal(o[s].to_numpy(), ted.loc[o["tedarikci_id"], s].to_numpy())

    # Haftalık plan: yalnız sezonluk; kanalların toplamı; haftalar çıkışa kadar
    ph = pb.plan_hafta
    assert set(ph["option_id"]) == set(o.loc[sez, "option_id"])
    assert np.allclose(ph["plan"], ph["plan_magaza"] + ph["plan_online"])
    top = ph.groupby("option_id")["plan"].sum()
    np.testing.assert_allclose(top.loc[o.loc[sez, "option_id"]].to_numpy(),
                               o.loc[sez, "plan_cikis"].to_numpy(), rtol=1e-9)


# ---------------------------------------------------------------------------
# Gerçek veri
# ---------------------------------------------------------------------------


@pytest.mark.veri
def test_ilk_alim_plan_orani():
    """Ruling R2: yayımlanan ilk alım (siparis tip='ilk') option başına
    politikanın gördüğü ilk alımdır; ilk alım ≈ plan × 0,93 (MOQ'ya ve 10'un
    katına yukarı yuvarlama, tedarikçi kapasitesiyle aşağı kırpma)."""
    from rpt import kaynak

    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok")
    pb = motor.politika_gorunumu(motor.dunya())
    o = pb.optionlar
    o = o[o["sezon_kodu"].isin(kaynak.TAM_SEZONLAR)].set_index("option_id")
    oran = o["ilk_alim"] / o["plan_sezon"]
    # Yuvarlamasız taban: plan × 0,93 → 10'un ve MOQ'nun katına yukarı
    taban = np.maximum(np.ceil(o["plan_sezon"] * 0.93 / 10 - 1e-9) * 10, o["moq_option"])
    yuvarlandi = o["ilk_alim"] == taban
    print(f"\nilk alım / plan: medyan {oran.median():.4f}, %10 {oran.quantile(.1):.4f}, "
          f"%90 {oran.quantile(.9):.4f}; plan × 0,93 yuvarlamasıyla birebir "
          f"{int(yuvarlandi.sum())} / {len(o)}; MOQ tabanında {(taban == o['moq_option']).sum()}")
    assert 0.92 <= oran.median() <= 0.95
    assert yuvarlandi.mean() > 0.9

    con = kaynak.baglan()
    try:
        ilk = con.execute(
            "select option_id, sum(adet) as adet from siparis where tip = 'ilk' group by 1").df()
    finally:
        con.close()
    ilk = ilk.set_index("option_id")["adet"]
    ortak = o.index.intersection(ilk.index)
    assert len(ortak) == len(o)
    np.testing.assert_array_equal(ilk.loc[ortak].to_numpy(dtype=np.int64),
                                  o.loc[ortak, "ilk_alim"].to_numpy(dtype=np.int64))


@pytest.mark.veri
def test_mevcut_kol_yayimlanan_tablolarla_ayni():
    """Lumoda politikaları + varsayılan tohumlar `motor.kos`'tan geçince
    yayımlanan v4'tür: koşunun temiz tabloları `yayimlanan_bicim`le
    (yayımlamadaki aynı kirli kayıtlar) 18 yayımlanan tablonun her biriyle
    değer, tür ve sıra olarak aynı (Parquet dışa aktarımına karşı; DuckDB
    satır sayıları, Σ adet, günlük satış). Gizli gerçeğin `karsilanmayan > 0`
    alt kümesi hakemin önbelleğiyle aynı. Koşu `cikti/kosular/`'a yazılır."""
    from perakende_analitik import hakem

    from rpt import kaynak

    parquet = kaynak.VERITABANI.parent / "parquet"
    if not kaynak.VERITABANI.exists() or not parquet.exists():
        pytest.skip("yayımlanan v4 yok")
    k = motor.kos(ad="lumoda", parametreler={}, onbellek=motor.KOSU_DIZINI)
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; "
          f"{k.meta.get('sure_sn')} sn; tepe bellek {k.meta.get('tepe_bellek_gb')} GB")
    tablolar = motor.yayimlanan_bicim(k.tablolar, "tam")

    yayimlanan = sorted(p.stem for p in parquet.glob("*.parquet"))
    assert sorted(tablolar) == yayimlanan
    for ad in yayimlanan:
        pd.testing.assert_frame_equal(
            _parquet_turu(tablolar[ad]), pd.read_parquet(parquet / f"{ad}.parquet"), obj=ad)

    con = kaynak.baglan()
    try:
        for ad in yayimlanan:
            n = con.execute(f"select count(*) from {ad}").fetchone()[0]
            assert len(tablolar[ad]) == int(n), ad
        adet = con.execute("select sum(adet) from satis").fetchone()[0]
        db = con.execute("select tarih, sum(adet) as adet from satis group by tarih order by tarih").df()
    finally:
        con.close()
    assert int(tablolar["satis"]["adet"].sum()) == int(adet)
    yeni = tablolar["satis"].groupby("tarih", observed=True)["adet"].sum().sort_index()
    np.testing.assert_array_equal(pd.to_datetime(db["tarih"]).to_numpy(), pd.to_datetime(yeni.index).to_numpy())
    np.testing.assert_array_equal(db["adet"].to_numpy(dtype=np.int64), yeni.to_numpy(dtype=np.int64))

    g = k.gercek
    assert ((g["kendi_satis"] + g["karsilanmayan"]) == g["talep"]).all()
    assert ((g["ikameye_giden"] + g["kalici_kayip"]) == g["karsilanmayan"]).all()
    try:
        h = hakem.oku()
    except FileNotFoundError:
        return
    hk = h["karsilanmayan"]
    alt = g[g["karsilanmayan"] > 0].reset_index(drop=True)
    assert len(alt) == len(hk)
    np.testing.assert_array_equal(alt["tarih"].to_numpy(), hk["tarih"].to_numpy())
    for s in ("magaza_id", "urun_id"):
        np.testing.assert_array_equal(alt[s].astype(str).to_numpy(), hk[s].astype(str).to_numpy())
    for s in motor.GERCEK_SUTUNLARI:
        np.testing.assert_array_equal(alt[s].to_numpy(), hk[s].to_numpy(), err_msg=s)
