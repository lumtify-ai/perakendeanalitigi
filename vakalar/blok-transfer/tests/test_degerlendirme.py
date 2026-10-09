from dataclasses import replace
from datetime import date

import duckdb
import pandas as pd
import pytest

from blok_transfer import degerlendirme
from blok_transfer.cekirdek.parametreler import Parametreler
from blok_transfer.cozuculer.tip import Plan

KARAR = date(2025, 12, 29)
P = Parametreler()


def ornek_plan():
    return Plan(
        hareketler=pd.DataFrame([
            dict(verici="MA", alici="MB", option_id="OPT1", adet=12, w=500.0),
            dict(verici="MA", alici="MC", option_id="OPT2", adet=8, w=600.0),
        ]),
        durum="optimal",
        sure_sn=0.01,
    )


def test_ozet_metikleri():
    ozet = degerlendirme.ozetle(ornek_plan(), P)
    assert ozet["option_sayisi"] == 2
    assert ozet["tasinan_adet"] == 20
    assert ozet["rota_sayisi"] == 2                          # MA->MB ve MA->MC
    assert ozet["bosalan_magaza"] == 1                       # tek verici: MA
    assert ozet["net_kazanc_tl"] == pytest.approx(1100 - 2 * 500)  # 2 rota sabiti
    assert ozet["sure_sn"] == pytest.approx(0.01)


def test_ozet_durum_tasir():
    assert degerlendirme.ozetle(ornek_plan(), P)["durum"] == "optimal"
    limitte = replace(ornek_plan(), durum="limit")
    assert degerlendirme.ozetle(limitte, P)["durum"] == "limit"


def test_boru_hatti_fiksturde_kapasiteye_uyar(con):
    # v4 fikstüründe kapasite boşluğu MB 5, MC 8 (tepe − karar günü stok).
    # OPT1 bloğu 12 adet: hiçbir alıcıya sığmaz. OPT2 (8) MC'ye sığar.
    # İki çözücü de tek hareketi seçer: 600 − 500 rota sabiti = 100.
    # (Rota birleştirmeyi test_mip'in küçük örnekleri sınar.)
    # Durum: MIP boşluk toleransı içinde "optimal"; açgözlü kanıt iddia etmez: "sezgisel".
    for yontem, durum in (("greedy", "sezgisel"), ("mip", "optimal")):
        plan, ozet = degerlendirme.boru_hatti(con, KARAR, P, yontem)
        assert plan.durum == durum
        assert set(zip(plan.hareketler.alici, plan.hareketler.option_id)) == {("MC", "OPT2")}
        assert ozet["net_kazanc_tl"] == pytest.approx(100.0)
        assert ozet["durum"] == durum


def test_boru_hatti_degeri_teraziye_gecirir(con):
    # deger="kar": OPT2→MC skoru 280 < 500 rota sabiti → MIP taşımaz.
    plan, ozet = degerlendirme.boru_hatti(con, KARAR, P, "mip", deger="kar")
    assert len(plan.hareketler) == 0
    assert plan.amac == pytest.approx(0.0)


def _sayacli(monkeypatch, yontem="mip"):
    """COZUCULER[yontem]'i çağrı sayan bir sarmalayıcıyla değiştirir."""
    sayac = {"n": 0}
    asil = degerlendirme.COZUCULER[yontem]

    def sayan(*args, **kwargs):
        sayac["n"] += 1
        return asil(*args, **kwargs)

    monkeypatch.setitem(degerlendirme.COZUCULER, yontem, sayan)
    return sayac


def test_onbellek_ikinci_cagrida_cozucuyu_cagirmaz(con, tmp_path, monkeypatch):
    sayac = _sayacli(monkeypatch)
    plan1, ozet1 = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
    plan2, ozet2 = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
    assert sayac["n"] == 1
    assert len(list(tmp_path.glob("*.parquet"))) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1
    pd.testing.assert_frame_equal(plan1.hareketler, plan2.hareketler)
    assert (plan1.durum, plan1.amac, plan1.sayaclar) == (plan2.durum, plan2.amac, plan2.sayaclar)
    assert plan2.sure_sn == pytest.approx(plan1.sure_sn)   # çözüm süresi, okuma süresi değil
    assert ozet1 == ozet2


def test_onbellek_bos_plani_da_tutar(con, tmp_path, monkeypatch):
    sayac = _sayacli(monkeypatch)
    for _ in range(2):
        plan, _ozet = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path, deger="kar")
        assert len(plan.hareketler) == 0
    assert sayac["n"] == 1


def test_onbellek_anahtari_parametreye_duyarli(con, tmp_path, monkeypatch):
    sayac = _sayacli(monkeypatch)
    degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
    degerlendirme.boru_hatti(con, KARAR, replace(P, rota_sabiti_tl=100.0), "mip", onbellek=tmp_path)
    degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path, deger="kar")
    assert sayac["n"] == 3
    assert len(list(tmp_path.glob("*.parquet"))) == 3
    # yöntem ve karar anı da anahtarda
    g = _sayacli(monkeypatch, "greedy")
    degerlendirme.boru_hatti(con, KARAR, P, "greedy", onbellek=tmp_path)
    degerlendirme.boru_hatti(con, date(2025, 12, 22), P, "greedy", onbellek=tmp_path)
    assert g["n"] == 2
    assert len(list(tmp_path.glob("*.parquet"))) == 5


def test_onbellek_anahtari_veri_dosyasina_duyarli(tmp_path):
    # Anahtar v4 dosyasının yol + boyut + mtime'ını içerir: dosya yenilenirse
    # eski plan okunmaz.
    yol = tmp_path / "v4.duckdb"
    c = duckdb.connect(str(yol))
    c.execute("create table t as select 1 as a")
    a1 = degerlendirme.onbellek_anahtari(c, KARAR, P, "mip", "ciro")
    assert a1 == degerlendirme.onbellek_anahtari(c, KARAR, P, "mip", "ciro")
    c.execute("insert into t select range from range(100000)")
    c.execute("checkpoint")
    a2 = degerlendirme.onbellek_anahtari(c, KARAR, P, "mip", "ciro")
    c.close()
    assert a1 != a2


def test_onbellek_hatali_plani_saklamaz(con, tmp_path, monkeypatch):
    # "hata" (tam sayı çözüm yok) kalıcı bir sonuç değil: bir sonraki çağrı yeniden çözer.
    from blok_transfer.cozuculer.tip import bos_hareketler
    sayac = {"n": 0}

    def hatali(*args, **kwargs):
        sayac["n"] += 1
        return Plan(bos_hareketler(), "hata", 0.0)

    monkeypatch.setitem(degerlendirme.COZUCULER, "mip", hatali)
    for _ in range(2):
        plan, _ozet = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
        assert plan.durum == "hata"
    assert sayac["n"] == 2
    assert list(tmp_path.glob("*")) == []


def test_onbellek_anahtari_kod_ozetine_duyarli(con, monkeypatch):
    # Formülasyon, terazi ya da aday kodu değişirse eski plan okunmamalı.
    a1 = degerlendirme.onbellek_anahtari(con, KARAR, P, "mip", "ciro")
    monkeypatch.setattr(degerlendirme, "kod_ozeti", lambda: "baska-kod")
    assert degerlendirme.onbellek_anahtari(con, KARAR, P, "mip", "ciro") != a1


def test_kod_ozeti_yalniz_cozucuye_giren_kaynaklari_sayar(tmp_path):
    # Çözücüye giren: cekirdek/**, cozuculer/**, degerlendirme.py. Ölçüm, hikâye
    # seçimi, ön hazırlık ve notlar MIP önbelleğini geçersiz kılmamalı.
    (tmp_path / "cekirdek").mkdir()
    (tmp_path / "cozuculer" / "ic").mkdir(parents=True)
    (tmp_path / "cekirdek" / "a.py").write_bytes(b"x = 1\n")
    (tmp_path / "cozuculer" / "ic" / "b.py").write_bytes(b"y = 2\n")
    (tmp_path / "degerlendirme.py").write_bytes(b"z = 3\n")
    (tmp_path / "olcum.py").write_bytes(b"o = 1\n")
    (tmp_path / "hikaye_sec.py").write_bytes(b"h = 1\n")
    (tmp_path / "cekirdek" / "notlar.txt").write_bytes(b"sayilmaz")
    o1 = degerlendirme.kod_ozeti(tmp_path)
    (tmp_path / "olcum.py").write_bytes(b"o = 2\n")                   # çözücü dışı
    (tmp_path / "hikaye_sec.py").write_bytes(b"h = 2\n")
    (tmp_path / "hazirla.py").write_bytes(b"yeni dosya\n")
    (tmp_path / "cekirdek" / "notlar.txt").write_bytes(b"degisti")      # .py değil
    (tmp_path / "cekirdek" / "a.py").write_bytes(b"x = 1\r\n")          # yalnız satır sonu
    assert degerlendirme.kod_ozeti(tmp_path) == o1
    for yol, icerik in [("cekirdek/a.py", b"x = 9\n"), ("cozuculer/ic/b.py", b"y = 9\n"),
                        ("degerlendirme.py", b"z = 9\n")]:
        eski = (tmp_path / yol).read_bytes()
        (tmp_path / yol).write_bytes(icerik)
        assert degerlendirme.kod_ozeti(tmp_path) != o1, yol
        (tmp_path / yol).write_bytes(eski)
    assert degerlendirme.kod_ozeti(tmp_path) == o1
    assert degerlendirme.kod_ozeti() == degerlendirme.kod_ozeti()   # paketin kendisi, kararlı


def test_kod_ozeti_ortak_kaynagi_sayar(tmp_path):
    # Ruling R6: ortak `kaynak.py` (çeşit hücreleri, temiz satış) adaylara girer;
    # değişirse plan önbelleği geçersizlenmeli. Varsayılan `ek` gerçekten o dosya.
    assert [y.name for y in degerlendirme.ORTAK_KAYNAKLARI] == ["kaynak.py"]
    assert all(y.exists() for y in degerlendirme.ORTAK_KAYNAKLARI)
    (tmp_path / "cekirdek").mkdir()
    (tmp_path / "cekirdek" / "a.py").write_bytes(b"x = 1\n")
    ortak = tmp_path / "disari" / "kaynak.py"
    ortak.parent.mkdir()
    ortak.write_bytes(b"k = 1\n")
    o1 = degerlendirme.kod_ozeti(tmp_path, ek=(ortak,))
    assert o1 != degerlendirme.kod_ozeti(tmp_path, ek=())
    ortak.write_bytes(b"k = 1\r\n")                                   # yalnız satır sonu
    assert degerlendirme.kod_ozeti(tmp_path, ek=(ortak,)) == o1
    ortak.write_bytes(b"k = 2\n")
    assert degerlendirme.kod_ozeti(tmp_path, ek=(ortak,)) != o1


def test_ozet_bosluk_yuzdesi():
    plan = replace(ornek_plan(), amac=1000.0, sinir=1012.345)
    assert degerlendirme.ozetle(plan, P)["bosluk_yuzde"] == 1.23
    assert degerlendirme.ozetle(ornek_plan(), P)["bosluk_yuzde"] is None     # greedy / bilinmiyor
    assert degerlendirme.ozetle(replace(ornek_plan(), amac=0.0, sinir=5.0), P)["bosluk_yuzde"] is None


def test_onbellek_siniri_saklar(con, tmp_path):
    p1, _ = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
    p2, o2 = degerlendirme.boru_hatti(con, KARAR, P, "mip", onbellek=tmp_path)
    assert p1.sinir is not None
    assert p2.sinir == p1.sinir
    assert o2["bosluk_yuzde"] is not None
