"""`allocation.motor`: üretecin tek kapısı, kaydediciler, takvim, kırpma tablosu, koşu
önbelleği, gizli gerçek.

Hızlı testler KÜÇÜK dünyada kısa koşu yapar (pencere 181. günde başlar; `GUN` günlük koşu
pencereye ~120 gün girer; bu sürede SS23'ün ilk dalgasının ilk dağıtımı, RPT kararları ve
markdown kademeleri vardır). Yayımlanan v4 ile eşdeğerlik `test_esdegerlik.py`'de (`veri`
işaretli, bir TAM koşu).
"""

import os
import pickle
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from allocation import motor

GUN = 300   # KÜÇÜK dünyada kısa koşu: [0, 300) günü, pencere 181'de başlar
KUCUK = {"olcek": "kucuk", "gun_sayisi": GUN}
YUVALAR = ("ilk_dagitim", "replenishment", "rpt", "markdown")


@pytest.fixture(scope="module")
def lumoda_kucuk():
    """Varsayılan Lumoda koşusu (KÜÇÜK, `GUN` gün, önbelleksiz); modülde bir kez."""
    return motor.kos(ad="lumoda", parametreler={}, onbellek=None, **KUCUK)


# ---------------------------------------------------------------------------
# Önbellek anahtarı
# ---------------------------------------------------------------------------


def _kaynak_agaci(kok):
    """Üç kaynak kökünü taklit eden geçici ağaç. allocation: listedeki (motor, politika)
    ve dışındaki (olcutler) modüller; ortak: tohumdan (kaynak, stok) ve vakanın içe
    aktarmasından (ekstra > derin) ulaşılanlar, ulaşılmayan hakem."""
    v = kok / "allocation"
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
    return {"allocation": v, "ortak": o, "v4": kok / "v4"}


def test_onbellek_anahtari_duyarli(tmp_path, monkeypatch):
    """Anahtarın her bileşeni anahtarı değiştirir: ad, parametreler, iki tohum, ölçek,
    gün sayısı, dört politika yuvasının her birinin türü ve kimliği, koşuyu etkileyen her
    kaynak (vaka listesi, ortak kapanış, v4), v4 dosyasının parmak izi. Değiştirmeyenler:
    parametre sözlüğünün sırası, satır sonları (CRLF/LF), `.py` dışı dosya, koşu dışı vaka
    modülü (olcutler; listede olmayan yeni modül), ortak kapanışa girmeyen modül (hakem)."""
    monkeypatch.setattr(motor, "KOD_KOKLERI", _kaynak_agaci(tmp_path / "kod"))
    db = tmp_path / "v4.duckdb"
    db.write_bytes(b"0" * 100)
    monkeypatch.setattr(motor, "VERI_YOLU", db)

    temel = dict(ad="kol", parametreler={"tutma": 0.3, "hafta": [3, 6]}, talep_tohumu=None,
                 operasyon_tohumu=motor.TOHUM, olcek="tam", gun_sayisi=None, turler={})
    a0 = motor.onbellek_anahtari(**temel)
    assert a0 == motor.onbellek_anahtari(**temel)
    assert sorted(motor.kod_dosyalari()) == [
        "allocation/motor.py", "allocation/politika.py", "ortak/derin.py", "ortak/ekstra.py",
        "ortak/kaynak.py", "ortak/stok.py", "v4/motor/dongu.py"]

    degisik = {
        "ad": "baska_kol",
        "parametreler": {"tutma": 0.15, "hafta": [3, 6]},
        "talep_tohumu": 20261019,
        "operasyon_tohumu": motor.TOHUM + 1,
        "olcek": "kucuk",
        "gun_sayisi": 100,
    }
    for alan, deger in degisik.items():
        assert motor.onbellek_anahtari(**{**temel, alan: deger}) != a0, alan
    # Her yuvanın türü ve kimliği ayrı ayrı; aynı tür başka yuvada başka anahtar
    anahtarlar = {a0}
    for yuva in YUVALAR:
        tur = {**temel, "turler": {yuva: "allocation.politika.Kol"}}
        kim = {**tur, "politikalar": {yuva: {"parametreler": {"tutma": 0.3}}}}
        kim2 = {**tur, "politikalar": {yuva: {"parametreler": {"tutma": 0.45}}}}
        for alanlar in (tur, kim, kim2):
            a = motor.onbellek_anahtari(**alanlar)
            assert a not in anahtarlar, (yuva, alanlar)
            anahtarlar.add(a)
    yeni = {"tutma": 0.3, "hafta": [3, 6], "yeni": 1}
    assert motor.onbellek_anahtari(**{**temel, "parametreler": yeni}) != a0
    # Sözlük sırası anahtarı değiştirmez; boş politika kimliği içeriğe girmez
    assert motor.onbellek_anahtari(**{**temel, "parametreler": {"hafta": [3, 6], "tutma": 0.3}}) == a0
    assert motor.onbellek_anahtari(**{**temel, "politikalar": {}}) == a0
    # JSON'a dönmeyen parametre (ör. çağrılabilir) açıkça reddedilir
    with pytest.raises(TypeError):
        motor.onbellek_anahtari(**{**temel, "parametreler": {"f": len}})

    kod = tmp_path / "kod"
    for dosya, icerik in (                                    # değiştirmeyenler
        (kod / "allocation" / "notlar.txt", b"degisti\n"),
        (kod / "allocation" / "motor.py", b"a = 1\r\n"),
        (kod / "allocation" / "olcutler.py", b"h = 2\n"),
        (kod / "allocation" / "yeni.py", b"y = 1\n"),
        (kod / "ortak" / "hakem.py", b"import perakende_veri.v4\n"),
    ):
        dosya.write_bytes(icerik)
        assert motor.onbellek_anahtari(**temel) == a0, dosya
    for dosya, icerik in (                                    # değiştirenler
        (kod / "allocation" / "politika.py", b"from perakende_analitik import ekstra\nk = 1\n"),
        (kod / "allocation" / "paylastir.py", b""),           # listede, sonradan yazılan modül
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
    """Gerçek kaynaklar: koşu modülleri ve ortak kapanış girer; ölçüm, kalibrasyon ve
    hakem girmez; sürümler lightgbm ve scikit-learn'ü taşır."""
    adlar = motor.kod_dosyalari()
    for a in ("allocation/motor.py", "allocation/kaynak.py", "allocation/sabitler.py",
              "ortak/kaynak.py", "ortak/stok.py", "v4/motor/dongu.py", "v4/politika.py"):
        assert a in adlar, a
    for a in ("allocation/__init__.py", "ortak/hakem.py", "ortak/sayi_denetimi.py"):
        assert a not in adlar, a
    surum = motor.anahtar_icerigi(ad="a", parametreler={}, talep_tohumu=None, operasyon_tohumu=1,
                                  olcek="tam", gun_sayisi=None, turler={})["surumler"]
    assert surum["lightgbm"] and surum["scikit-learn"] and surum["numpy"]


def _vaka_kapanisi(baslangic):
    """allocation paketi içinde `baslangic` modüllerinden içe aktarmayla ulaşılanlar."""
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
    """allocation/'daki her modül ya koşuyu etkiler (KOSU_MODULLERI) ya etkilemez
    (KOSU_DISI), ikisinde birden değil. Kalibrasyon koşu dışıdır (sonucu `parametreler`
    üstünden girer). Koşu tarafının (motor ve politika zinciri) içe aktardığı her vaka
    modülü listededir."""
    liste, disi = set(motor.KOSU_MODULLERI), set(motor.KOSU_DISI)
    assert liste == {"motor", "sabitler", "kaynak", "ogrenme", "benzer", "tahmin", "paylastir",
                     "politika"}
    assert disi == {"olcutler", "oyun", "yollar", "hikaye_sec", "senaryolar", "kalibrasyon"}
    assert not liste & disi
    var = {y.stem for y in motor.PAKET_KOKU.glob("*.py")} - {"__init__"}
    assert {"motor", "kaynak", "sabitler"} <= var          # tarama boş dönmüyor
    assert var <= liste | disi, f"sınıflandırılmamış modül: {var - liste - disi}"
    kosu_tarafi = _vaka_kapanisi(("motor", "politika", "paylastir", "tahmin", "benzer", "ogrenme"))
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
    """Kaydedici sardığını aynen çağırır ve aynı nesneyi döndürür; kayda (`{"gun",
    "args", "cikti"}`) çıktının kopyası girer: dönen dizi sonradan değişse de kayıt
    değişmez."""
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
    """Transferler gibi dizi alanlı çıktı satır başına; dizi argüman kayıtta kalır,
    tabloda yer almaz. Boş kayıt `gun` sütunlu boş tablo verir."""
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


def test_kaydedici_rpt_sozlugu_ve_markdown_matrisi():
    """RPT çıktısı (sözlük, option → adet ya da SKU dizisi) satır başına bir option
    (`indis`, `deger`; SKU dizisi `alt` sırasıyla); markdown çıktısı ([O, 3] oran)
    sıfırdan farklı öğeleri (`indis`, `sutun`, `deger` float). Boş sözlük ve sıfır matris
    satır vermez; kayıtta kalırlar."""
    cevaplar = iter([{3: 40, 1: 20}, {}, {2: 10}])
    r = motor.Kaydedici(lambda g: next(cevaplar))
    for d in (7, 14, 21):
        r(_G(d))
    assert len(r.kayit) == 3 and r.kayit[1]["cikti"] == {}
    t = r.kayit_tablosu()
    assert list(t.columns) == ["gun", "indis", "deger"]
    assert t.to_dict("list") == {"gun": [7, 7, 21], "indis": [3, 1, 2], "deger": [40, 20, 10]}
    assert all(t[s].dtype == np.int64 for s in t.columns)

    dizili = motor.Kaydedici(lambda g: {4: np.array([1, 0, 2]), 6: 5})
    dizili(_G(7))
    assert dizili.kayit_tablosu().to_dict("list") == {
        "gun": [7, 7, 7, 7], "indis": [4, 4, 4, 6], "alt": [0, 1, 2, -1], "deger": [1, 0, 2, 5]}

    oranlar = iter([np.zeros((4, 3)), np.array([[0, 0, 0], [0.2, 0, 0.2], [0, 0.5, 0], [0, 0, 0]])])
    m = motor.Kaydedici(lambda g: next(oranlar))
    m(_G(7))
    m(_G(14))
    t = m.kayit_tablosu()
    assert list(t.columns) == ["gun", "indis", "sutun", "deger"]
    assert t.to_dict("list") == {"gun": [14, 14, 14], "indis": [1, 1, 2], "sutun": [0, 2, 1],
                                 "deger": [0.2, 0.2, 0.5]}
    assert t["deger"].dtype == np.float64 and t["indis"].dtype == np.int64


def test_kaydedici_sardiginin_kimligini_ve_yontemlerini_tasir():
    """Vakanın verdiği kaydedici sardığı politikanın türünü ve kimliğini `temel` ile
    anahtara taşır; `gecmis_gerekir` ve `baglan` sardığına geçer."""
    class Kol:
        gecmis_gerekir = True

        def __init__(self, tutma):
            self.tutma = tutma
            self.baglanan = None

        def __call__(self, g, o):
            return np.zeros(3, dtype=np.int64)

        def parametreler(self):
            return {"tutma": self.tutma}

        def baglan(self, kaydediciler):
            self.baglanan = kaydediciler

    a, b = motor.Kaydedici(Kol(0.15)), motor.Kaydedici(Kol(0.30))
    assert motor.politika_kimligi(a) != motor.politika_kimligi(b)
    assert motor.politika_kimligi(a)["temel"]["tur"].endswith("Kol")
    assert a.gecmis_gerekir and not motor.Kaydedici(lambda g: 0).gecmis_gerekir
    d = {"rpt": object()}
    a.baglan(d)
    assert a.temel.baglanan is d
    motor.Kaydedici(lambda g: 0).baglan(d)          # sardığında yöntem yoksa sessiz


# ---------------------------------------------------------------------------
# Dünya, Lumoda
# ---------------------------------------------------------------------------


def test_dunya_onbellekli_ve_lumoda():
    """`dunya(olcek)` süreç içi önbellekli; `lumoda(ad)` v4'ün Lumoda politikası."""
    from perakende_veri.v4 import politika as v4p

    assert motor.dunya("kucuk") is motor.dunya("kucuk")
    with pytest.raises(ValueError, match="ölçek"):
        motor.dunya("orta")
    assert motor.lumoda("ilk_dagitim") is v4p.lumoda_ilk_dagitim
    assert motor.lumoda("rpt") is v4p.lumoda_rpt and motor.lumoda("markdown") is v4p.lumoda_markdown
    with pytest.raises(ValueError, match="Lumoda"):
        motor.lumoda("yok")
    assert motor.KAYDEDILENLER == ("ilk_dagitim", "rpt", "markdown")


# ---------------------------------------------------------------------------
# Koşu ve kaydediciler
# ---------------------------------------------------------------------------


def _parquet_turu(df):
    """Parquet gidiş-dönüşü bellekte (koşu tabloları da Parquet'ten döner)."""
    import io

    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    tampon.seek(0)
    return pd.read_parquet(tampon)


def _ayni_kosu(a, b, kayitlar=True):
    assert sorted(a.tablolar) == sorted(b.tablolar)
    for ad in a.tablolar:
        pd.testing.assert_frame_equal(a.tablolar[ad], b.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(a.gercek, b.gercek, obj="gercek")
    if kayitlar:
        assert sorted(a.kayitlar) == sorted(b.kayitlar)
        for ad in a.kayitlar:
            pd.testing.assert_frame_equal(a.kayitlar[ad], b.kayitlar[ad], obj=ad)


def test_kaydedici_ciktiyi_degistirmez(lumoda_kucuk):
    """Lumoda'nın ilk dağıtım, RPT ve markdown kararları her koşuda kaydedicilerle sarılı;
    kaydediciler çıktıyı değiştirmez: tablolar kaydedicisiz `simule_et`'in
    `hareket_tablolari`'nın Parquet gidiş-dönüşüyle birebir. Üç kayıt dolu; penceredeki
    her ilk dağıtım sevkinin option'ı kayıtta bir paket kararı taşır; kayıttaki markdown
    oranları motorun `fiyat` kaydıyla tutar. Talep tohumu talebi değiştirir."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.tablolar import hareket_tablolari

    a = lumoda_kucuk
    w = motor.dunya("kucuk")
    ham = simule_et(w, gun_sayisi=GUN)
    beklenen = hareket_tablolari(w, ham)
    assert sorted(a.tablolar) == sorted(beklenen)
    for ad in beklenen:
        pd.testing.assert_frame_equal(a.tablolar[ad], _parquet_turu(beklenen[ad]), obj=ad)

    assert sorted(a.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    assert a.meta["turler"] == {} and "politikalar" not in a.meta
    ilk, rpt, md = (a.kayitlar[k] for k in ("ilk_dagitim", "rpt", "markdown"))
    assert list(ilk.columns) == ["gun", "arg0", "indis", "deger"] and len(ilk) > 0
    assert list(rpt.columns) == ["gun", "indis", "deger"] and len(rpt) > 0
    assert list(md.columns) == ["gun", "indis", "sutun", "deger"] and len(md) > 0
    s = a.tablolar["sevkiyat"]
    s = s[s["tip"].astype(str) == "ilk_dagitim"]
    assert len(s) > 0
    sevk_opt = set(s["urun_id"].astype(str).map(w.urunler.set_index("urun_id")["option_id"]))
    karar_opt = set(w.optionlar["option_id"].to_numpy()[ilk.loc[ilk["deger"] > 0, "arg0"].to_numpy()])
    assert sevk_opt <= karar_opt
    # RPT kararı motorun siparişine dönüşür (aynı option, aynı gün, aynı toplam adet)
    rs = [x for x in ham["siparis"] if x["tip"] == "rpt"]
    assert sorted((int(x["siparis_gun"]), int(x["option"]), int(np.sum(x["adetler"]))) for x in rs) == \
        sorted(zip(rpt["gun"], rpt["indis"], rpt["deger"]))
    # Markdown: motorun fiyat kaydındaki her (gün, option, hat) değişimi kayıttaki oranla aynı
    f = ham["fiyat"]
    kayit = md.set_index(["gun", "indis", "sutun"])["deger"]
    degisim = f[f["oran"] > 0].set_index(["gun", "option", "hat"])["oran"]
    ortak = degisim.index.intersection(kayit.index)
    assert len(ortak) > 0
    np.testing.assert_array_equal(degisim.loc[ortak].to_numpy(), kayit.loc[ortak].to_numpy())

    b = motor.kos(ad="lumoda", parametreler={}, talep_tohumu=20261019, onbellek=None, **KUCUK)
    assert int(b.gercek["talep"].sum()) != int(a.gercek["talep"].sum())


class _Izleyen:
    """Lumoda RPT'sini aynen çağıran, kendi kaydını tutan enjekte politika."""

    def __init__(self):
        self.gunler = []
        self.kd = None

    def baglan(self, kaydediciler):
        self.kd = kaydediciler

    def __call__(self, g):
        self.gunler.append(int(g.gun))
        return motor.lumoda("rpt")(g)

    def kayit_tablosu(self):
        return pd.DataFrame({"gun": np.asarray(self.gunler, dtype=np.int64)})


def test_enjekte_politika_kendi_kaydini_verir(lumoda_kucuk):
    """Enjekte edilen politika Lumoda kaydedicisinin yerine geçer: kayıt tablosu kendi
    `kayit_tablosu()`'ndan gelir; öteki iki Lumoda kararı yine kaydedilir ve politikaya
    `baglan` ile verilir. Lumoda'yı aynen çağıran politika aynı tabloları üretir."""
    p = _Izleyen()
    k = motor.kos(rpt=p, ad="izleyen", parametreler={}, onbellek=None, **KUCUK)
    _ayni_kosu(k, lumoda_kucuk, kayitlar=False)
    assert sorted(k.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    pd.testing.assert_frame_equal(k.kayitlar["rpt"], _parquet_turu(p.kayit_tablosu()))
    assert len(p.gunler) > 0 and all(d % 7 == 0 for d in p.gunler)   # pazartesi (gün 0 pazartesi)
    for ad in ("ilk_dagitim", "markdown"):
        pd.testing.assert_frame_equal(k.kayitlar[ad], lumoda_kucuk.kayitlar[ad], obj=ad)
    assert set(p.kd) == {"ilk_dagitim", "markdown"}
    assert all(isinstance(v, motor.Kaydedici) for v in p.kd.values())
    assert k.meta["turler"] == {"rpt": f"{__name__}._Izleyen"}


# ---------------------------------------------------------------------------
# Takvim
# ---------------------------------------------------------------------------


class _OynatRPT:
    """Testin yeniden oynatıcısı (Görev 6'nın `TakvimRPT`'si değil)."""

    def __init__(self, takvim):
        self.takvim = takvim

    def __call__(self, g):
        return self.takvim.rpt_gunu(g.gun)

    def parametreler(self):
        return {"takvim": self.takvim.kimlik}


class _OynatMarkdown(_OynatRPT):
    def __call__(self, g):
        return self.takvim.markdown_gunu(g.gun)


def test_takvim_kucuk_yeniden_oynatma(lumoda_kucuk, tmp_path):
    """`takvim(kosu)` Lumoda'nın kayıtlı RPT ve markdown kararlarından kurulur; o takvimi
    oynatan `rpt=` ve `markdown=` koşusu Lumoda koşusunun tablolarını ve gizli gerçeğini
    birebir üretir. Takvim pickle'lanır; kimliği içerikten (`sabitle`), gidiş-dönüşte
    aynı, içerik değişince başka. Kayıtsız gün boş sözlük / sıfır matristir."""
    t = motor.takvim(lumoda_kucuk)
    O = len(motor.dunya("kucuk").optionlar)
    assert t.option_sayisi == O
    assert len(t.rpt) > 0 and len(t.markdown) > 0
    assert t.rpt_gunu(-5) == {} and not t.markdown_gunu(-5).any()
    assert t.markdown_gunu(-5).shape == (O, 3)
    gun = max(t.markdown)
    m = t.markdown_gunu(gun)
    m[:] = 0.9                                         # dönen kopya; takvim değişmez
    assert t.markdown_gunu(gun).max() < 0.9

    s = t.sabitle()
    assert s.kimlik == t.kimlik and s.sabitle() is s
    yol = tmp_path / "takvim.pkl"
    yol.write_bytes(pickle.dumps(s))
    geri = pickle.loads(yol.read_bytes())
    assert geri.kimlik == s.kimlik and geri._ozet() == s.kimlik
    baska = motor.Takvim(rpt={k: dict(v) for k, v in t.rpt.items()} | {0: {1: 10}},
                         markdown=t.markdown, option_sayisi=O)
    assert baska.kimlik != t.kimlik

    k = motor.kos(rpt=_OynatRPT(t), markdown=_OynatMarkdown(t), ad="takvimli", parametreler={},
                  onbellek=None, **KUCUK)
    _ayni_kosu(k, lumoda_kucuk, kayitlar=False)
    assert sorted(k.kayitlar) == ["ilk_dagitim"]
    pd.testing.assert_frame_equal(k.kayitlar["ilk_dagitim"], lumoda_kucuk.kayitlar["ilk_dagitim"])


# ---------------------------------------------------------------------------
# Kırpma tablosu
# ---------------------------------------------------------------------------


def _oyuncak_kosu(w):
    """Oyuncak dünyada elle kurulmuş koşu: A (indis 2, lansman 2025-02-10) dört mağazaya
    istenir, motor M2'yi 2'den 1'e, M4'ü 1'den 0'a kırpar; M1 ve M3 tam gider. B (indis 3)
    lansmanı takvim sonrası: kıyasa girmez. Replenishment satırı sayılmaz."""
    G = w.takvim["tarih"]
    kayit = pd.DataFrame({
        "gun": [1, 1, 1, 1, 2],
        "arg0": [2, 2, 2, 2, 3],
        "indis": [0, 1, 2, 3, 0],          # M1 M2 M3 M4 ; B → M1
        "deger": [3, 2, 1, 1, 4],
    })
    paket = w.paketler.copy()
    urun = w.urunler.set_index("urun_id")
    sevk = []
    for m, n in (("M1", 3), ("M2", 1), ("M3", 1)):
        for u in urun.index[urun["option_id"] == "OPT-A"]:
            satir = (paket["paket_id"] == "PKT01") & (paket["beden_sira"] == urun.at[u, "beden_sira"])
            ic = int(paket.loc[satir, "adet"].sum())
            sevk.append((G.iloc[5], G.iloc[7], "DEPO", m, u, n * ic, "ilk_dagitim", "PKT01"))
    sevk.append((G.iloc[9], G.iloc[10], "DEPO", "M4", "OPT-A-1", 4, "replenishment", None))
    sevkiyat = pd.DataFrame(sevk, columns=["tarih", "varis_tarihi", "kaynak", "hedef", "urun_id", "adet",
                                           "tip", "paket_id"])
    return motor.Kosu(tablolar={"sevkiyat": sevkiyat, "paket": paket}, gercek=pd.DataFrame(),
                      meta={"olcek": "oyuncak", "gun_sayisi": None}, kayitlar={"ilk_dagitim": kayit})


def test_kirpma_tablosu_oyuncak(dunya):
    """Kayıttaki paket kararı ↔ `sevkiyat`'taki ilk dağıtım (paket sayısı = beden adedi ÷
    paketin o bedendeki içeriği): yalnız farklı (option, mağaza) satırları; kıyas yalnız
    sevkleri koşuda ve pencerede kalan option'larda. Beden adetleri paketle tutmazsa hata."""
    k = _oyuncak_kosu(dunya)
    t = motor.kirpma_tablosu(k, w=dunya)
    assert list(t.columns) == ["option_id", "magaza_id", "istenen_paket", "giden_paket"]
    assert t.to_dict("list") == {"option_id": ["OPT-A", "OPT-A"], "magaza_id": ["M2", "M4"],
                                 "istenen_paket": [2, 1], "giden_paket": [1, 0]}
    assert all(t[s].dtype == np.int64 for s in ("istenen_paket", "giden_paket"))

    s = k.tablolar["sevkiyat"]
    bozuk = s.copy()
    i = bozuk.index[(bozuk["hedef"] == "M1") & (bozuk["tip"] == "ilk_dagitim")][0]
    bozuk.loc[i, "adet"] += 1
    with pytest.raises(RuntimeError, match="paket"):
        motor.kirpma_tablosu(motor.Kosu(tablolar={**k.tablolar, "sevkiyat": bozuk}, gercek=k.gercek,
                                        meta=k.meta, kayitlar=k.kayitlar), w=dunya)


def test_kirpma_tablosu_kucuk(lumoda_kucuk):
    """KÜÇÜK koşuda: motor yalnız kırpar (giden ≤ istenen); pencere öncesi kararlar
    (ısınma sezonu) kıyasa girmez; tablo yalnız penceredeki sezonların option'larını taşır."""
    w = motor.dunya("kucuk")
    t = motor.kirpma_tablosu(lumoda_kucuk)
    assert len(t) > 0                                  # kalite reddi Lumoda'yı kırpar
    assert (t["giden_paket"] <= t["istenen_paket"]).all()
    assert (t["giden_paket"] != t["istenen_paket"]).all()
    lansman = pd.to_datetime(w.optionlar.set_index("option_id")["lansman_tarihi"])
    assert (lansman.loc[t["option_id"]] >= pd.Timestamp("2023-01-01")).all()


# ---------------------------------------------------------------------------
# Önbellek
# ---------------------------------------------------------------------------


def _kayitli_lumoda():
    return motor.Kaydedici(motor.lumoda("replenishment"))


def test_onbellek_ikinci_cagrida_kosmaz(tmp_path, monkeypatch):
    """İlk çağrı koşar ve yazar; aynı anahtarla ikinci çağrı motoru hiç çağırmadan aynı
    koşuyu (tablolar, gizli gerçek, kayıtlar) döndürür. Başka anahtar (talep tohumu,
    başka yuvaya enjeksiyon) yeniden koşar; yarım yazılmış kayıt okunmaz."""
    ilk = motor.kos(replenishment=_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={},
                    onbellek=tmp_path, **KUCUK)
    assert not ilk.onbellekten
    assert ilk.meta["ad"] == "lumoda_kayitli" and ilk.meta["gun_sayisi"] == GUN
    assert sorted(ilk.kayitlar) == ["ilk_dagitim", "markdown", "replenishment", "rpt"]
    assert len(ilk.kayitlar["replenishment"]) > 0
    assert ilk.meta["turler"] == {"replenishment": "allocation.motor.Kaydedici"}
    assert ilk.meta["politikalar"]["replenishment"]["temel"]["tur"].endswith("lumoda_replenishment")
    if sys.platform == "win32":
        assert ilk.meta["tepe_bellek_gb"] > 0
    assert len(list(tmp_path.iterdir())) == 1

    def yasak(*a, **k):
        raise AssertionError("önbellekteki koşu yeniden koşturuldu")

    monkeypatch.setattr(motor, "simule_et", yasak)
    ikinci = motor.kos(replenishment=_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={},
                       onbellek=tmp_path, **KUCUK)
    assert ikinci.onbellekten
    _ayni_kosu(ilk, ikinci)
    assert ikinci.meta == ilk.meta

    for ek in ({"talep_tohumu": 7}, {"rpt": motor.Kaydedici(motor.lumoda("rpt"))},
               {"ilk_dagitim": motor.lumoda("ilk_dagitim")}):
        with pytest.raises(AssertionError, match="yeniden"):
            motor.kos(replenishment=_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={},
                      onbellek=tmp_path, **ek, **KUCUK)

    # meta.json yazımın son adımıdır: o yoksa kayıt yarımdır ve okunmaz
    (dizin,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    (dizin / "meta.json").unlink()
    with pytest.raises(AssertionError, match="yeniden"):
        motor.kos(replenishment=_kayitli_lumoda(), ad="lumoda_kayitli", parametreler={},
                  onbellek=tmp_path, **KUCUK)


def test_bozuk_kayit_ve_artiklar(tmp_path):
    """Meta'sı tam ama Parquet'i bozuk ya da eksik kayıt silinir ve yeniden koşulur; bu
    süreçten eski `.yaziliyor-*` artığı silinir, yenisi kalır."""
    ilk = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    (dizin,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    (dizin / "tablo_satis.parquet").write_bytes(b"bozuk")
    with pytest.warns(UserWarning, match="bozuk"):
        ikinci = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    assert not ikinci.onbellekten
    _ayni_kosu(ilk, ikinci)
    (dizin / "kayit_markdown.parquet").unlink()
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
    (`KosuKaydi`); okunan her tablo ve süzülen satırlar tam koşununkiyle aynı; takvim ve
    kırpma tablosu tembel kayıttan da kurulur. Önbelleksiz tembel koşu yoktur; eksik
    Parquet'li kayıt yeniden koşulur."""
    tam = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, **KUCUK)
    k = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, tembel=True, **KUCUK)
    assert isinstance(k, motor.KosuKaydi) and k.onbellekten and k.meta == tam.meta
    assert sorted(k.tablolar) == sorted(tam.tablolar)
    for ad in ("satis", "urun", "sevkiyat"):
        pd.testing.assert_frame_equal(k.tablolar[ad], tam.tablolar[ad], obj=ad)
    pd.testing.assert_frame_equal(k.gercek, tam.gercek)
    for ad in tam.kayitlar:
        pd.testing.assert_frame_equal(k.kayitlar[ad], tam.kayitlar[ad], obj=ad)
    assert motor.takvim(k).kimlik == motor.takvim(tam).kimlik
    pd.testing.assert_frame_equal(motor.kirpma_tablosu(k), motor.kirpma_tablosu(tam))
    urunler = sorted(set(tam.tablolar["satis"]["urun_id"].astype(str)))[:7]
    for kosu in (k, tam):
        s = kosu.tablo("satis", sutunlar=["tarih", "urun_id", "adet"], urunler=urunler)
        assert list(s.columns) == ["tarih", "urun_id", "adet"] and len(s) > 0
        assert set(s["urun_id"].astype(str)) <= set(urunler)
        g = kosu.tablo("gercek", urunler=urunler)
        assert set(g["urun_id"].astype(str)) <= set(urunler)
    pd.testing.assert_frame_equal(k.yukle().tablolar["stok"], tam.tablolar["stok"])

    with pytest.raises(ValueError, match="tembel"):
        motor.kos(ad="lumoda", parametreler={}, onbellek=None, tembel=True, **KUCUK)

    (k.dizin / "tablo_stok.parquet").unlink()
    with pytest.warns(UserWarning, match="eksik"):
        yeni = motor.kos(ad="lumoda", parametreler={}, onbellek=tmp_path, tembel=True, **KUCUK)
    assert not yeni.onbellekten and (yeni.dizin / "tablo_stok.parquet").exists()


def test_kos_girdi_denetimi():
    with pytest.raises(ValueError, match="dosya adı"):
        motor.kos(ad="kötü ad", parametreler={}, onbellek=None, **KUCUK)
    with pytest.raises(ValueError, match="ölçek"):
        motor.kos(ad="lumoda", parametreler={}, onbellek=None, olcek="orta", gun_sayisi=GUN)


def test_yayimlanan_bicim_yayimla_ile_ayni():
    """KÜÇÜK dünyada tam koşu: `yayimlanan_bicim(hareket_tablolari)` = `uret.yayimla`
    (kirletme adımı birebir)."""
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


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def test_gercek_kimlikleri(lumoda_kucuk):
    """Hücre-gün kimlikleri (hakem tanımı): kendi_satis + karsilanmayan = talep,
    ikameye_giden + kalici_kayip = karsilanmayan; hepsi ≥ 0; satırlar pencerede talebi olan
    hücre-günler. `karsilanmayan > 0` alt kümesi hakemin tablosunun kendisidir; toplamlar
    ham koşuyla tutar."""
    from perakende_analitik import hakem
    from perakende_veri.v4 import tablolar as v4t
    from perakende_veri.v4.motor import simule_et

    g = lumoda_kucuk.gercek
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
