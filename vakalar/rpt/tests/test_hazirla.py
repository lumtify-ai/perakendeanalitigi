import json
from pathlib import Path

import pytest

from rpt import hazirla


def test_gunluk_yolu_yoksa_komut_soyler(tmp_path):
    with pytest.raises(RuntimeError, match="rpt.hazirla"):
        hazirla.gunluk_yolu(tmp_path)


def test_gunluk_yolu_bayat_pencere(tmp_path):
    (tmp_path / hazirla.GUNLUK).write_bytes(b"")
    (tmp_path / hazirla.KAYNAK).write_text(json.dumps({"pencere": ["2024-01-01", "2024-12-31"]}),
                                           encoding="utf-8")
    with pytest.raises(RuntimeError, match="pencere"):
        hazirla.gunluk_yolu(tmp_path)
    (tmp_path / hazirla.KAYNAK).write_text(
        json.dumps({"pencere": hazirla._iz_pencere(), "kod": hazirla.kod_ozeti()}), encoding="utf-8")
    assert hazirla.gunluk_yolu(tmp_path) == tmp_path / hazirla.GUNLUK


@pytest.mark.veri
def test_carpan_bulucu_kapanmis_sezon_yoksa_notr():
    import pandas as pd
    from perakende_analitik.carpanlar import Carpanlar

    from rpt import kaynak

    if not kaynak.VERITABANI.exists():
        pytest.skip("v4 verisi yok")
    con = kaynak.baglan()
    try:
        try:
            yol = hazirla.gunluk_yolu(con=con)
        except RuntimeError as e:
            pytest.skip(str(e))
        bul = hazirla.carpan_bulucu(con, yol)
        n = bul(pd.Timestamp("2023-03-13"))                           # SS23 1. dalga, h = 4
        bos = Carpanlar()
        assert (n.hafta_gunu, n.ozel_gun, n.esneklik_kampanya) == (bos.hafta_gunu, bos.ozel_gun, {})
        assert n.yasam.empty and n.beden_payi.empty
        t = pd.Timestamp("2024-09-02")                                # AW24 1. dalga, h = 2
        c = bul(t)
        assert c is bul(pd.Timestamp("2024-12-09"))                   # aynı küme: SS23, AW23, SS24
        assert c.hafta_gunu == hazirla.carpanlar(con, yol, t).hafta_gunu and c.hafta_gunu
    finally:
        con.close()


# --- önbellek koda ve içeriğe bağlı (son inceleme, madde 1) ---------------------------

class _Baglanti:
    def close(self):
        pass


@pytest.fixture
def sahte_kurulum(tmp_path, monkeypatch):
    """`main`i gerçek veri olmadan koşturur: günlük tabloyu `durum["icerik"]` baytlarıyla
    yazar, kod özetini `durum["kod"]`dan okur."""
    durum = {"icerik": b"tablo-1", "kod": "kod-1", "kurulum": 0}

    def yaz(con, yol, pencere):
        durum["kurulum"] += 1
        yol.write_bytes(durum["icerik"])
        return 1

    monkeypatch.setattr(hazirla.ortak, "baglan", lambda db: _Baglanti())
    monkeypatch.setattr(hazirla.hazirlik, "gunluk_yaz", yaz)
    monkeypatch.setattr(hazirla, "kod_ozeti", lambda: durum["kod"])
    db = tmp_path / "v4.duckdb"
    db.write_bytes(b"v4")
    cikti = tmp_path / "cikti"

    def kos():
        return hazirla.main(["--cikti", str(cikti), "--db", str(db)])

    return durum, cikti, kos


def test_kod_kapanisi_motorunkiyle_ayni():
    from rpt import motor

    beklenen = motor.ortak_kapanisi([Path(hazirla.__file__)], hazirla.ORTAK_KOKU, tohum=())
    assert hazirla.ortak_kapanisi() == beklenen
    assert {"hazirlik", "ozellikler", "kaynak"} <= set(beklenen)
    assert set(hazirla.kod_dosyalari()) == {"rpt/hazirla.py"} | {f"ortak/{m}.py" for m in beklenen}


def test_kod_ozeti_icerige_bagli(tmp_path, monkeypatch):
    a = tmp_path / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(hazirla, "kod_dosyalari", lambda: {"rpt/hazirla.py": a})
    o1 = hazirla.kod_ozeti()
    a.write_bytes(b"x = 1\r\n")                                   # satır sonu özeti değiştirmez
    assert hazirla.kod_ozeti() == o1
    a.write_text("x = 2\n", encoding="utf-8")
    assert hazirla.kod_ozeti() != o1


def test_kod_degisince_gunluk_yeniden_kurulur_carpanlar_silinir(sahte_kurulum):
    durum, cikti, kos = sahte_kurulum
    kos()
    assert durum["kurulum"] == 1
    kayit = json.loads((cikti / hazirla.KAYNAK).read_text(encoding="utf-8"))
    assert kayit["kod"] == "kod-1" and kayit["gunluk_sha256"] == hazirla.icerik_ozeti(cikti / hazirla.GUNLUK)
    carpan = cikti / "carpanlar_SS23.pkl"
    carpan.write_bytes(b"c")
    kos()                                                         # aynı kod, aynı v4: dokunulmaz
    assert durum["kurulum"] == 1 and carpan.exists()
    assert hazirla.gunluk_yolu(cikti) == cikti / hazirla.GUNLUK

    durum["kod"] = "kod-2"
    with pytest.raises(RuntimeError, match="kodla"):
        hazirla.gunluk_yolu(cikti)
    kos()
    assert durum["kurulum"] == 2 and not carpan.exists()
    assert json.loads((cikti / hazirla.KAYNAK).read_text(encoding="utf-8"))["kod"] == "kod-2"
    assert hazirla.gunluk_yolu(cikti) == cikti / hazirla.GUNLUK


def test_ayni_icerikte_eski_dosya_korunur_farklida_degisir(sahte_kurulum):
    import os

    durum, cikti, kos = sahte_kurulum
    kos()
    gunluk = cikti / hazirla.GUNLUK
    os.utime(gunluk, ns=(10**18, 10**18))                         # eski bir mtime
    durum["kod"] = "kod-2"                                        # kod değişti, çıktı aynı
    sonuc = kos()
    assert durum["kurulum"] == 2 and sonuc["ayni_icerik"] is True
    assert gunluk.stat().st_mtime_ns == 10**18                    # öğrenme önbelleği geçersizlenmez
    assert not (cikti / ("yeni_" + hazirla.GUNLUK)).exists()

    durum["kod"], durum["icerik"] = "kod-3", b"tablo-2"           # kod değişti, çıktı değişti
    sonuc = kos()
    assert sonuc["ayni_icerik"] is False and gunluk.read_bytes() == b"tablo-2"
    assert gunluk.stat().st_mtime_ns != 10**18
    kayit = json.loads((cikti / hazirla.KAYNAK).read_text(encoding="utf-8"))
    assert kayit["gunluk_sha256"] == hazirla.icerik_ozeti(gunluk)


def test_v4_dosyasi_degisince_yeniden_kurulur(sahte_kurulum, tmp_path):
    durum, cikti, kos = sahte_kurulum
    kos()
    (tmp_path / "v4.duckdb").write_bytes(b"v4 yeni surum")
    durum["icerik"] = b"tablo-yeni"
    kos()
    assert durum["kurulum"] == 2 and (cikti / hazirla.GUNLUK).read_bytes() == b"tablo-yeni"
