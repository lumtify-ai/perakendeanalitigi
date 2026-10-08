"""`hazirla` adımı: sıra, önbellek, kaynak parmak izi, bayat çıktı denetimi.

Ağır adımlar (ortak paketin `gunluk_yaz`/`carpanlar_yaz`/`kayip_yaz`ı) sahtelerle
değiştirilir: burada sınanan vakanın akış kuralıdır (hangi adım ne zaman koşar,
hangi argümanla, çıktı ne zaman geçersizdir). Ortak adımların kendisi
`vakalar/ortak/tests`ta sınanır; gerçek veride uçtan uca koşum README'dedir.
"""

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from blok_transfer import hazirla

KARAR = date(2025, 11, 3)


@pytest.fixture
def db(tmp_path) -> Path:
    """Küçük bir DuckDB dosyası (parmak izi için gerçek bir dosya yeter)."""
    yol = tmp_path / "perakende.duckdb"
    con = duckdb.connect(str(yol))
    con.execute("create table t as select 1 as x")
    con.close()
    return yol


@pytest.fixture
def sahte(monkeypatch):
    """Üç ortak adımı ve `karar_ani`yi sahtelerle değiştirir; çağrıları kaydeder."""
    cagrilar: list[tuple] = []
    durum = {"karar": KARAR}

    def gunluk_yaz(con, yol, pencere):
        cagrilar.append(("gunluk", pencere))
        yol.write_bytes(b"gunluk")
        return 7

    def carpanlar_yaz(con, gunluk, yol, ogrenme_bitis):
        cagrilar.append(("carpanlar", ogrenme_bitis))
        assert gunluk.exists()
        yol.write_bytes(b"carpanlar")
        return 5

    def kayip_yaz(con, ad, gunluk, carpan, yol, hedef_araligi=None, agacli=True):
        cagrilar.append(("kayip", ad, hedef_araligi, agacli))
        assert gunluk.exists() and carpan.exists()
        pd.DataFrame({"tarih": pd.to_datetime(["2025-11-04", "2025-11-05"]),
                      "magaza_id": ["A", "B"], "kayip": [1.5, 2.5]}).to_parquet(yol, index=False)
        return {"havuz_satir": 9, "hedef_satir": 2, "kuyruk_satir": 0, "toplam_kayip": 4.0}

    monkeypatch.setattr(hazirla, "gunluk_yaz", gunluk_yaz)
    monkeypatch.setattr(hazirla, "carpanlar_yaz", carpanlar_yaz)
    monkeypatch.setattr(hazirla, "kayip_yaz", kayip_yaz)
    monkeypatch.setattr(hazirla, "karar_ani", lambda con, *a, **k: durum["karar"])
    return cagrilar, durum


def _adlar(cagrilar):
    return [c[0] for c in cagrilar]


def test_pencere_karar_ve_sekiz_hafta():
    assert hazirla.pencere(date(2025, 11, 3), 8) == (date(2025, 11, 3), date(2025, 12, 29))
    assert hazirla.pencere(date(2025, 11, 3), 1) == (date(2025, 11, 3), date(2025, 11, 10))


def test_adimlar_sirayla_ve_onbellekli(tmp_path, db, sahte):
    cagrilar, _ = sahte
    cikti = tmp_path / "cikti"
    argv = ["--cikti", str(cikti), "--db", str(db)]
    hazirla.main(argv)
    assert _adlar(cagrilar) == ["gunluk", "carpanlar", "kayip"]
    # ortak adımlara vakanın değerleri gider
    assert cagrilar[0][1] == (date(2023, 1, 1), date(2025, 12, 31))
    assert cagrilar[1][1] == date(2024, 12, 31)
    assert cagrilar[2][1:] == ("basit", (date(2025, 11, 3), date(2025, 12, 29)), False)
    for ad in ("gunluk.parquet", "carpanlar.pkl", "kayip_basit.parquet", "kaynak.json", "sure.json"):
        assert (cikti / ad).exists(), ad
    kaynak = json.loads((cikti / "kaynak.json").read_text(encoding="utf-8"))
    assert kaynak["karar"] == "2025-11-03" and kaynak["olcum_hafta"] == 8
    assert kaynak["db"]["yol"] == str(db.resolve())
    sure = json.loads((cikti / "sure.json").read_text(encoding="utf-8"))
    assert set(sure["adimlar"]) == {"gunluk", "carpanlar", "basit"}
    assert sure["adimlar"]["basit"]["toplam_kayip"] == 4.0
    assert all(a["saniye"] >= 0 for a in sure["adimlar"].values())

    cagrilar.clear()
    hazirla.main(argv)                     # her şey hazır: hiçbir adım koşmaz
    assert cagrilar == []


def test_ust_adim_yeniden_kurulunca_alttakiler_de_kurulur(tmp_path, db, sahte):
    cagrilar, _ = sahte
    cikti = tmp_path / "cikti"
    argv = ["--cikti", str(cikti), "--db", str(db)]
    hazirla.main(argv)
    cagrilar.clear()
    (cikti / "carpanlar.pkl").unlink()     # ortadaki eksik: kendisi ve basit kurulur
    hazirla.main(argv)
    assert _adlar(cagrilar) == ["carpanlar", "kayip"]
    cagrilar.clear()
    (cikti / "gunluk.parquet").unlink()    # en üstteki eksik: hepsi
    hazirla.main(argv)
    assert _adlar(cagrilar) == ["gunluk", "carpanlar", "kayip"]
    cagrilar.clear()
    hazirla.main(argv + ["--yeniden"])
    assert _adlar(cagrilar) == ["gunluk", "carpanlar", "kayip"]


@pytest.mark.parametrize("degisim", ["karar", "db"])
def test_kaynak_degisince_cikti_silinir(tmp_path, db, sahte, degisim):
    cagrilar, durum = sahte
    cikti = tmp_path / "cikti"
    hazirla.main(["--cikti", str(cikti), "--db", str(db)])
    cagrilar.clear()
    if degisim == "karar":
        durum["karar"] = date(2025, 10, 27)
    else:
        con = duckdb.connect(str(db))
        con.execute("insert into t values (2)")
        con.close()
    hazirla.main(["--cikti", str(cikti), "--db", str(db)])
    assert _adlar(cagrilar) == ["gunluk", "carpanlar", "kayip"]    # hepsi baştan
    kaynak = json.loads((cikti / "kaynak.json").read_text(encoding="utf-8"))
    assert kaynak["karar"] == durum["karar"].isoformat()


def test_baska_karar_icin_kurulmus_cikti_hata(tmp_path, db, sahte):
    _, durum = sahte
    cikti = tmp_path / "cikti"
    hazirla.main(["--cikti", str(cikti), "--db", str(db)])
    con = duckdb.connect(str(db), read_only=True)
    try:
        k = hazirla.oku_kayip(cikti, con, KARAR, 8)
        assert list(k["kayip"]) == [1.5, 2.5]
        with pytest.raises(RuntimeError, match="python -m blok_transfer.hazirla"):
            hazirla.oku_kayip(cikti, con, date(2025, 10, 27), 8)    # başka karar
        with pytest.raises(RuntimeError, match="python -m blok_transfer.hazirla"):
            hazirla.oku_kayip(cikti, con, KARAR, 4)                  # başka ölçüm haftası
    finally:
        con.close()
    # db değişti (başka bir v4 dosyası): aynı karar ve hafta olsa da bayat
    con = duckdb.connect(str(db))
    con.execute("insert into t values (2)")
    con.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        with pytest.raises(RuntimeError, match="python -m blok_transfer.hazirla"):
            hazirla.oku_kayip(cikti, con, KARAR, 8)
    finally:
        con.close()


def test_cikti_yoksa_komutu_soyler(tmp_path, db):
    con = duckdb.connect(str(db), read_only=True)
    try:
        with pytest.raises(RuntimeError, match=r"python -m blok_transfer\.hazirla"):
            hazirla.oku_kayip(tmp_path / "yok", con, KARAR, 8)
        (tmp_path / "bos").mkdir()
        with pytest.raises(RuntimeError, match=r"python -m blok_transfer\.hazirla"):
            hazirla.oku_kayip(tmp_path / "bos", con, KARAR, 8)
    finally:
        con.close()
