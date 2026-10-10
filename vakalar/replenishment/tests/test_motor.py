"""`replenishment.motor`: üretecin tek kapısı, kaydediciler, koşu önbelleği,
gizli gerçek.

Hızlı testler KÜÇÜK dünyada kısa koşu yapar (pencere 181. günde başlar;
`GUN` günlük koşu pencereye ~80 gün girer; bu sürede ilk dağıtım kararları ve
bir outlet akışı günü vardır). Yayımlanan v4 ile eşdeğerlik `test_esdegerlik.py`'de
(`veri` işaretli, bir TAM koşu).
"""

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from replenishment import motor

GUN = 260   # KÜÇÜK dünyada kısa koşu: [0, 260) günü, pencere 181'de başlar
KUCUK = {"olcek": "kucuk", "gun_sayisi": GUN}


# ---------------------------------------------------------------------------
# Önbellek anahtarı
# ---------------------------------------------------------------------------


def _kaynak_agaci(kok):
    """Üç kaynak kökünü taklit eden geçici ağaç. replenishment: listedeki
    (motor, politika) ve dışındaki (olcutler) modüller; ortak: tohumdan
    (kaynak, stok) ve vakanın içe aktarmasından (ekstra > derin) ulaşılanlar,
    ulaşılmayan hakem."""
    v = kok / "replenishment"
    v.mkdir(parents=True)
    (v / "motor.py").write_bytes(b"a = 1\n")
    (v / "politika.py").write_bytes(b"from perakende_analitik import ekstra\n")
    (v / "olcutler.py").write_bytes(b"h = 1\n")
    (v / "notlar.txt").write_bytes(b"py olmayan dosya\n")
    o = kok / "ortak"
    o.mkdir()
    (o / "kaynak.py").write_bytes(b"c = 3\n")
    (o / "stok.py").write_bytes(b"from perakende_analitik import kaynak\n")
    (o / "ekstra.py").write_bytes(b"def f():\n    from perakende_analitik.derin import x\n")
    (o / "derin.py").write_bytes(b"x = 1\n")
    (o / "hakem.py").write_bytes(b"import perakende_veri\n")
    (kok / "v4" / "motor").mkdir(parents=True)
    (kok / "v4" / "motor" / "dongu.py").write_bytes(b"d = 4\n")
    return {"replenishment": v, "ortak": o, "v4": kok / "v4"}


def test_onbellek_anahtari_duyarli(tmp_path, monkeypatch):
    """Anahtarın her bileşeni anahtarı değiştirir: ad, parametreler, iki
    tohum, ilk alım oranı, kaydedici bayrağı, ölçek, gün sayısı, politika
    türü ve kimliği, koşuyu etkileyen her kaynak (vaka listesi, ortak
    kapanış, v4), v4 dosyasının parmak izi. Değiştirmeyenler: parametre
    sözlüğünün sırası, satır sonları (CRLF/LF), `.py` dışı dosya, koşu dışı
    vaka modülü (olcutler; listede olmayan yeni modül), ortak kapanışa
    girmeyen modül (hakem)."""
    monkeypatch.setattr(motor, "KOD_KOKLERI", _kaynak_agaci(tmp_path / "kod"))
    db = tmp_path / "v4.duckdb"
    db.write_bytes(b"0" * 100)
    monkeypatch.setattr(motor, "VERI_YOLU", db)

    temel = dict(ad="kol", parametreler={"esik": 0.55, "hafta": [3, 6]}, ilk_alim_orani=1.0,
                 kaydedici=True, talep_tohumu=None, operasyon_tohumu=motor.TOHUM, olcek="tam",
                 gun_sayisi=None, turler={})
    a0 = motor.onbellek_anahtari(**temel)
    assert a0 == motor.onbellek_anahtari(**temel)
    assert sorted(motor.kod_dosyalari()) == [
        "ortak/derin.py", "ortak/ekstra.py", "ortak/kaynak.py", "ortak/stok.py",
        "replenishment/motor.py", "replenishment/politika.py", "v4/motor/dongu.py"]

    degisik = {
        "ad": "baska_kol",
        "parametreler": {"esik": 0.56, "hafta": [3, 6]},
        "ilk_alim_orani": 0.7,
        "kaydedici": False,
        "talep_tohumu": 20261010,
        "operasyon_tohumu": motor.TOHUM + 1,
        "olcek": "kucuk",
        "gun_sayisi": 100,
        "turler": {"replenishment": "replenishment.politika.KuralKol"},
        "politikalar": {"replenishment": {"parametreler": {"tavan": 0.6}}},
    }
    for alan, deger in degisik.items():
        assert motor.onbellek_anahtari(**{**temel, alan: deger}) != a0, alan
    assert motor.onbellek_anahtari(**{**temel, "parametreler": {"esik": 0.55, "hafta": [3, 6], "yeni": 1}}) != a0
    # Sözlük sırası anahtarı değiştirmez; 1 ve 1.0 aynı oran
    assert motor.onbellek_anahtari(**{**temel, "parametreler": {"hafta": [3, 6], "esik": 0.55}}) == a0
    assert motor.onbellek_anahtari(**{**temel, "ilk_alim_orani": 1}) == a0
    # JSON'a dönmeyen parametre (ör. çağrılabilir) açıkça reddedilir
    with pytest.raises(TypeError):
        motor.onbellek_anahtari(**{**temel, "parametreler": {"f": len}})

    kod = tmp_path / "kod"
    for dosya, icerik in (                                    # değiştirmeyenler
        (kod / "replenishment" / "notlar.txt", b"degisti\n"),
        (kod / "replenishment" / "motor.py", b"a = 1\r\n"),
        (kod / "replenishment" / "olcutler.py", b"h = 2\n"),
        (kod / "replenishment" / "yeni.py", b"y = 1\n"),
        (kod / "ortak" / "hakem.py", b"import perakende_veri.v4\n"),
    ):
        dosya.write_bytes(icerik)
        assert motor.onbellek_anahtari(**temel) == a0, dosya
    for dosya, icerik in (                                    # değiştirenler
        (kod / "replenishment" / "politika.py", b"from perakende_analitik import ekstra\nk = 1\n"),
        (kod / "replenishment" / "defter.py", b""),           # listede, sonradan yazılan modül
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
    kalibrasyon ve hakem girmez; sürümler lightgbm ve scikit-learn'ü taşır."""
    adlar = motor.kod_dosyalari()
    for a in ("replenishment/motor.py", "replenishment/kaynak.py", "replenishment/sabitler.py",
              "ortak/kaynak.py", "ortak/stok.py", "ortak/ozellikler.py", "ortak/carpanlar.py",
              "ortak/talep.py", "ortak/hazirlik.py", "v4/motor/dongu.py", "v4/politika.py"):
        assert a in adlar, a
    for a in ("replenishment/olcutler.py", "replenishment/kalibrasyon.py", "replenishment/__init__.py",
              "ortak/hakem.py", "ortak/sayi_denetimi.py"):
        assert a not in adlar, a
    surum = motor.anahtar_icerigi(ad="a", parametreler={}, ilk_alim_orani=1.0, kaydedici=True,
                                  talep_tohumu=None, operasyon_tohumu=1, olcek="tam",
                                  gun_sayisi=None, turler={})["surumler"]
    assert surum["lightgbm"] and surum["scikit-learn"] and surum["numpy"]


def _vaka_kapanisi(baslangic):
    """replenishment paketi içinde `baslangic` modüllerinden içe aktarmayla ulaşılanlar."""
    var = {y.stem for y in motor.PAKET_KOKU.glob("*.py")}
    gorulen, sira = set(), [m for m in baslangic if m in var]
    while sira:
        m = sira.pop()
        if m in gorulen:
            continue
        gorulen.add(m)
        for ad in motor.ice_aktarimlar(motor.PAKET_KOKU / f"{m}.py", motor.PAKET_ADI):
            parca = ad.split(".")
            if parca[0] == motor.PAKET_ADI and len(parca) > 1 and parca[1] in var:
                sira.append(parca[1])
    return gorulen


def test_her_modul_bir_listede():
    """replenishment/'deki her modül ya koşuyu etkiler (KOSU_MODULLERI) ya
    etkilemez (KOSU_DISI), ikisinde birden değil. Kalibrasyon koşu dışıdır
    (Ruling R5: sonucu `parametreler` üstünden girer). Koşu tarafının
    (motor, politika, dagitim, defter) içe aktardığı her vaka modülü listededir."""
    liste, disi = set(motor.KOSU_MODULLERI), set(motor.KOSU_DISI)
    assert not liste & disi
    assert "kalibrasyon" in disi and "kalibrasyon" not in liste
    var = {y.stem for y in motor.PAKET_KOKU.glob("*.py")} - {"__init__"}
    assert {"motor", "kaynak", "sabitler"} <= var          # tarama boş dönmüyor
    assert var <= liste | disi, f"sınıflandırılmamış modül: {var - liste - disi}"
    kosu_tarafi = _vaka_kapanisi(("motor", "politika", "dagitim", "defter"))
    assert "motor" in kosu_tarafi
    assert kosu_tarafi <= liste, kosu_tarafi - liste


# ---------------------------------------------------------------------------
# Kaydedici
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Transfer:
    kaynak: np.ndarray
    hedef: np.ndarray
    sku: np.ndarray
    adet: np.ndarray


class _G:
    def __init__(self, gun):
        self.gun = gun


def test_kaydedici_aynen_cagirir_ve_kopyalar():
    """Kaydedici sardığını aynen çağırır ve aynı nesneyi döndürür; kayda
    (R3: `{"gun", "args", "cikti"}`) çıktının kopyası girer: dönen dizi
    sonradan değişse de kayıt değişmez."""
    def ilk(g, o):
        return np.array([0, 2, 0, 1], dtype=np.int64) * (o + 1)

    k = motor.Kaydedici(ilk)
    g = _G(5)
    c = k(g, np.int64(3))
    np.testing.assert_array_equal(c, [0, 8, 0, 4])
    c[1] = 99                                   # motor çıktıyı sonradan değiştirse bile
    k(_G(12), 0)
    assert [e["gun"] for e in k.kayit] == [5, 12]
    assert k.kayit[0]["args"] == (3,) and type(k.kayit[0]["args"][0]) is int
    np.testing.assert_array_equal(k.kayit[0]["cikti"], [0, 8, 0, 4])
    assert k.temel is ilk

    t = k.kayit_tablosu()
    assert list(t.columns) == ["gun", "arg0", "indis", "deger"]
    assert t.to_dict("list") == {"gun": [5, 5, 12, 12], "arg0": [3, 3, 0, 0],
                                 "indis": [1, 3, 1, 3], "deger": [8, 4, 2, 1]}
    assert all(t[s].dtype == np.int64 for s in t.columns)


def test_kaydedici_transfer_ve_dizi_argumani():
    """Transferler gibi dizi alanlı çıktı satır başına; dizi argüman (outlet
    akışının `os`'u) kayıtta kalır, tabloda yer almaz. Boş kayıt `gun`
    sütunlu boş tablo verir."""
    def outlet(g, os):
        n = len(os)
        return _Transfer(np.full(n, -1), np.arange(n) + 10, np.asarray(os) * 2, np.full(n, 3))

    k = motor.Kaydedici(outlet)
    assert list(k.kayit_tablosu().columns) == ["gun"] and len(k.kayit_tablosu()) == 0
    os_ = np.array([4, 7])
    k(_G(30), os_)
    os_[0] = 0
    np.testing.assert_array_equal(k.kayit[0]["args"][0], [4, 7])
    t = k.kayit_tablosu()
    assert list(t.columns) == ["gun", "kaynak", "hedef", "sku", "adet"]
    assert t.to_dict("list") == {"gun": [30, 30], "kaynak": [-1, -1], "hedef": [10, 11],
                                 "sku": [8, 14], "adet": [3, 3]}


def test_kaydedici_sardiginin_kimligini_ve_yontemlerini_tasir():
    """Vakanın verdiği kaydedici (Ruling R4) sardığı politikanın türünü ve
    kimliğini `temel` ile anahtara taşır; `gecmis_gerekir` ve `baglan`
    sardığına geçer."""
    class Kol:
        gecmis_gerekir = True

        def __init__(self, tavan):
            self.tavan = tavan
            self.baglanan = None

        def __call__(self, g):
            return np.zeros(3, dtype=np.int64)

        def parametreler(self):
            return {"tavan": self.tavan}

        def baglan(self, kaydediciler):
            self.baglanan = kaydediciler

    a, b = motor.Kaydedici(Kol(0.6)), motor.Kaydedici(Kol(1.6))
    assert motor.politika_kimligi(a) != motor.politika_kimligi(b)
    assert motor.politika_kimligi(a)["temel"]["tur"].endswith("Kol")
    assert a.gecmis_gerekir and not motor.Kaydedici(lambda g: 0).gecmis_gerekir
    d = {"ilk_dagitim": object()}
    a.baglan(d)
    assert a.temel.baglanan is d
    motor.Kaydedici(lambda g: 0).baglan(d)          # sardığında yöntem yoksa sessiz


# ---------------------------------------------------------------------------
# Dünya
# ---------------------------------------------------------------------------


def test_dunya_alim_orani_anahtarda():
    """`dunya(olcek, ilk_alim_orani)` süreç içi önbellekli; oran anahtardadır
    ve yalnız AW25'in ilk alımını değiştirir."""
    w1, w07 = motor.dunya("kucuk"), motor.dunya("kucuk", 0.7)
    assert motor.dunya("kucuk", 1.0) is w1 and motor.dunya("kucuk", 0.7) is w07
    fark = np.asarray(w1.ilk_alim) != np.asarray(w07.ilk_alim)
    assert fark.any()
    assert set(w1.optionlar.loc[fark, "sezon_kodu"]) == {"AW25"}
    assert (np.asarray(w07.ilk_alim)[fark] < np.asarray(w1.ilk_alim)[fark]).all()


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


def _kayitli_lumoda():
    return motor.Kaydedici(motor.lumoda("replenishment"))


def test_kaydedici_ciktiyi_degistirmez():
    """`kaydedici=True` (varsayılan; ilk dağıtım ve outlet akışı Lumoda'yı
    saran kaydedicilerle) ve `kaydedici=False` koşularının tabloları ve gizli
    gerçeği birebir; yalnız birincisinde kayıt vardır. Kayıtlar boş değil:
    kısa koşuda ilk dağıtım kararları ve bir outlet akışı günü var."""
    a = motor.kos(ad="lumoda", parametreler={}, onbellek=None, **KUCUK)
    b = motor.kos(ad="lumoda", parametreler={}, onbellek=None, kaydedici=False, **KUCUK)
    assert sorted(a.tablolar) == sorted(b.tablolar)
    for ad in a.tablolar:
        pd.testing.assert_frame_equal(a.tablolar[ad], b.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(a.gercek, b.gercek, obj="gercek")
    assert sorted(a.kayitlar) == ["ilk_dagitim", "outlet_akisi"] and b.kayitlar == {}
    ilk = a.kayitlar["ilk_dagitim"]
    assert list(ilk.columns) == ["gun", "arg0", "indis", "deger"] and len(ilk) > 0
    assert len(a.kayitlar["outlet_akisi"]) > 0
    # Penceredeki her ilk dağıtım sevkinin option'ı kayıtta bir paket kararı taşır
    w = motor.dunya("kucuk")
    s = a.tablolar["sevkiyat"]
    s = s[s["tip"].astype(str) == "ilk_dagitim"]
    assert len(s) > 0
    sevk_opt = set(s["urun_id"].astype(str).map(w.urunler.set_index("urun_id")["option_id"]))
    karar_opt = set(w.optionlar["option_id"].to_numpy()[ilk.loc[ilk["deger"] > 0, "arg0"].to_numpy()])
    assert sevk_opt <= karar_opt
    assert a.meta["kaydedici"] is True and b.meta["kaydedici"] is False
    assert a.meta["anahtar"] != b.meta["anahtar"]


def test_baglan_canli_kaydi_verir():
    """`kos` aynı kaydedici nesnelerini replenishment politikasına
    `baglan(kaydediciler)` ile verir: politika koşu sırasında kaydın canlı
    büyüdüğünü görür; koşunun kayıt tabloları o nesnelerinkidir."""
    class Izleyen:
        def __init__(self):
            self.kd = None
            self.boylar = []

        def baglan(self, kaydediciler):
            self.kd = kaydediciler

        def __call__(self, g):
            self.boylar.append((g.gun, len(self.kd["ilk_dagitim"].kayit), len(self.kd["outlet_akisi"].kayit)))
            return motor.lumoda("replenishment")(g)

    p = Izleyen()
    k = motor.kos(p, ad="izleyen", parametreler={}, onbellek=None, **KUCUK)
    assert set(p.kd) == {"ilk_dagitim", "outlet_akisi"}
    assert all(isinstance(v, motor.Kaydedici) for v in p.kd.values())
    ilk = [b for _, b, _ in p.boylar]
    assert ilk == sorted(ilk) and ilk[0] < ilk[-1]            # canlı büyüyor
    assert p.boylar[-1][2] > 0
    pd.testing.assert_frame_equal(k.kayitlar["ilk_dagitim"], p.kd["ilk_dagitim"].kayit_tablosu(),
                                  check_dtype=False)
    # kaydedici=False iken bağlanmaz
    q = Izleyen()
    q.kd = {"ilk_dagitim": motor.Kaydedici(None), "outlet_akisi": motor.Kaydedici(None)}
    once = q.kd
    motor.kos(q, ad="izleyen", parametreler={}, onbellek=None, kaydedici=False, **KUCUK)
    assert q.kd is once


def test_onbellek_ikinci_cagrida_kosmaz(tmp_path, monkeypatch):
    """İlk çağrı koşar ve yazar; aynı anahtarla ikinci çağrı motoru hiç
    çağırmadan aynı koşuyu (tablolar, gizli gerçek, kaydedici kayıtları)
    döndürür. Başka anahtar (talep tohumu, alım oranı) yeniden koşar; yarım
    yazılmış kayıt okunmaz."""
    ilk = motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert not ilk.onbellekten
    assert ilk.meta["ad"] == "lumoda_kayitli" and ilk.meta["gun_sayisi"] == GUN
    assert ilk.meta["ilk_alim_orani"] == 1.0
    assert sorted(ilk.kayitlar) == ["ilk_dagitim", "outlet_akisi", "replenishment"]
    assert len(ilk.kayitlar["replenishment"]) > 0
    assert ilk.meta["turler"] == {"replenishment": "replenishment.motor.Kaydedici"}
    assert ilk.meta["politikalar"]["replenishment"]["temel"]["tur"].endswith("lumoda_replenishment")
    if sys.platform == "win32":
        assert ilk.meta["tepe_bellek_gb"] > 0
    assert len(list(tmp_path.iterdir())) == 1

    def yasak(*a, **k):
        raise AssertionError("önbellekteki koşu yeniden koşturuldu")

    monkeypatch.setattr(motor, "simule_et", yasak)
    ikinci = motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert ikinci.onbellekten
    _ayni_kosu(ilk, ikinci)
    assert ikinci.meta == ilk.meta

    for ek in ({"talep_tohumu": 7}, {"ilk_alim_orani": 0.7}, {"kaydedici": False}):
        with pytest.raises(AssertionError, match="yeniden"):
            motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path,
                      **ek, **KUCUK)

    # meta.json yazımın son adımıdır: o yoksa kayıt yarımdır ve okunmaz
    (dizin,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    (dizin / "meta.json").unlink()
    with pytest.raises(AssertionError, match="yeniden"):
        motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)


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


def test_tembel_kosu_kaydi(tmp_path):
    """`tembel=True`: büyük tablolar bellekte değil, istendikçe diskten okunur
    (`KosuKaydi`); okunan her tablo ve süzülen satırlar tam koşununkiyle aynı.
    Önbelleksiz tembel koşu yoktur; eksik Parquet'li kayıt yeniden koşulur."""
    tam = motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path, **KUCUK)
    k = motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path,
                  tembel=True, **KUCUK)
    assert isinstance(k, motor.KosuKaydi) and k.onbellekten and k.meta == tam.meta
    assert sorted(k.tablolar) == sorted(tam.tablolar)
    for ad in ("satis", "urun", "sevkiyat"):
        pd.testing.assert_frame_equal(k.tablolar[ad], tam.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(k.gercek, tam.gercek)
    for ad in tam.kayitlar:
        pd.testing.assert_frame_equal(k.kayitlar[ad], tam.kayitlar[ad], obj=ad)
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
        yeni = motor.kos(_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={}, onbellek=tmp_path,
                         tembel=True, **KUCUK)
    assert not yeni.onbellekten and (yeni.dizin / "tablo_stok.parquet").exists()


def test_kos_girdi_denetimi():
    for kotu in (0.0, -0.5, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="alım oranı"):
            motor.kos(ad="lumoda", parametreler={}, onbellek=None, ilk_alim_orani=kotu, **KUCUK)
    with pytest.raises(ValueError, match="dosya adı"):
        motor.kos(ad="kötü ad", parametreler={}, onbellek=None, **KUCUK)
    with pytest.raises(ValueError, match="ölçek"):
        motor.kos(ad="lumoda", parametreler={}, onbellek=None, olcek="orta", gun_sayisi=GUN)


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
    """Parquet gidiş-dönüşü bellekte (koşu tabloları da Parquet'ten döner)."""
    import io

    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


def test_kos_varsayilan_lumoda_ve_tohum():
    """Politika verilmezse Lumoda: tablolar `hareket_tablolari`'nın Parquet
    gidiş-dönüşü (kaydediciler çıktıyı değiştirmez); talep tohumu talebi
    değiştirir."""
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
