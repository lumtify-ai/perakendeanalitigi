"""oyun.py: git'teki `kumeler.json`'un şeması (İlk Sevkiyat yol 0 okur), `kumeler_kaydi`, kod özeti, JSON
dönüşümü, ablasyon ailelerinin sütunları, şehir → iklim uyumu. Koşumun kendisi (gerçek veri, ~3-4 dk)
el ile: `python -m kumeleme.oyun`."""

import json

import numpy as np
import pandas as pd
import pytest

from kumeleme import kural, ogren, oyun, ozellikler
from tests import sahte_sonuc


def kumeler_semasi(k: dict) -> None:
    """`kumeler.json` sözleşmesi: kapsam, K1-K4 (kapsamın her mağazası), öneri (kümelenenler) + yeni mağaza
    ataması, gizli segment ayrı ve etiketli."""
    assert set(k) == {"surum", "karar_gunu", "kod", "kapsam", "kural", "ml", "olcum_gizli_segment"}
    assert k["surum"] == oyun.KAYIT_SURUMU
    kum, yeni = k["kapsam"]["kumelenen"], k["kapsam"]["yeni"]
    tum = set(kum) | set(yeni)
    assert kum == sorted(kum) and not set(kum) & set(yeni)
    assert set(k["kural"]) == set(oyun.KURALLAR)
    for ad, r in k["kural"].items():
        assert set(r) == {"ad", "etiket", "kimlik"} and set(r["etiket"]) == tum, ad
        assert r["kimlik"] == ogren.bolme_kimligi(pd.Series(r["etiket"]))
    assert all(k["kural"]["k2"]["etiket"][m] == "C" for m in yeni)
    ml = k["ml"]
    assert set(ml) == {"aile", "yontem", "k", "kimlik", "ozellik_kimligi", "etiket", "yeni_magaza"}
    assert ml["aile"] in ozellikler.AILELER and ml["yontem"] in ogren.YONTEMLER
    assert sorted(ml["etiket"]) == kum
    etiketler = set(ml["etiket"].values())
    assert etiketler == set(range(ml["k"]))                              # kanonik 0..k−1
    assert ml["kimlik"] == ogren.bolme_kimligi(pd.Series(ml["etiket"]))
    ym = ml["yeni_magaza"]
    assert ym["yontem"] == "knn" and sorted(ym["atama"]) == sorted(yeni) and set(ym["atama"].values()) <= etiketler
    g = k["olcum_gizli_segment"]
    assert "YALNIZ ÖLÇÜM" in g["not"] and set(g["etiket"]) == tum
    assert not {"outlet", "online"} & set(g["etiket"].values())


def test_kumeler_kaydi_semasi_sahte():
    s = sahte_sonuc.sonuc()
    k = oyun.kumeler_kaydi(s)
    kumeler_semasi(k)
    assert k["ml"]["yeni_magaza"]["atama"] == {"M09": 0}
    assert json.loads(oyun.metin(k)) == k


def test_kumeler_json_semasi():
    """Git'teki dosya (karar günü, gerçek veri)."""
    if not oyun.KUMELER.is_file():
        pytest.skip("kumeler.json henüz üretilmedi (python -m kumeleme.oyun)")
    k = json.loads(oyun.KUMELER.read_text(encoding="utf-8"))
    kumeler_semasi(k)
    assert k["karar_gunu"] == "2025-02-07"
    assert len(k["kapsam"]["kumelenen"]) == 67 and sorted(k["kapsam"]["yeni"]) == ["M027", "M041"]
    assert b"\r\n" not in oyun.KUMELER.read_bytes()


def test_kumeler_json_sonucla_ayni():
    """`cikti/sonuc.json` varsa git'teki dosya ondan üretilenle aynı (rapor korunumu da denetler)."""
    if not (oyun.SONUC.is_file() and oyun.KUMELER.is_file()):
        pytest.skip("koşum çıktısı yok")
    s = json.loads(oyun.SONUC.read_text(encoding="utf-8"))
    assert json.loads(oyun.KUMELER.read_text(encoding="utf-8")) == oyun.kumeler_kaydi(s)


def test_kod_ozeti_satir_sonundan_bagimsiz_icerige_bagli(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 1\ny = 2\n")
    (tmp_path / "b.py").write_bytes(b"z = 3\n")
    o = oyun.kod_ozeti(tmp_path)
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert oyun.kod_ozeti(tmp_path) == o
    (tmp_path / "b.py").write_bytes(b"z = 4\n")
    assert oyun.kod_ozeti(tmp_path) != o
    assert len(oyun.kod_ozeti()) == 64


def test_veri_parmak_izi(tmp_path):
    assert oyun.veri_parmak_izi(tmp_path / "yok.duckdb") == ["yok", "yok.duckdb"]
    (tmp_path / "v.duckdb").write_bytes(b"1234")
    iz = oyun.veri_parmak_izi(tmp_path / "v.duckdb")
    assert iz[:2] == ["v.duckdb", 4] and isinstance(iz[2], int)


def test_json_donusumu():
    x = oyun._j({"a": np.int64(3), "b": np.float64("nan"), "c": (1, np.bool_(True)), 4: pd.Timestamp("2025-02-07"),
                 "d": [np.float32(0.5)]})
    assert x == {"a": 3, "b": None, "c": [1, True], "4": "2025-02-07", "d": [0.5]}
    json.dumps(x)


def test_ablasyon_aileleri_blok_sutunlari():
    cols = (["karisim/Collection/kalip/regular", "beden/1", "mevsim/01", "olcek/log_m2"]
            + ["karisim_stoklu/Collection/kalip/regular", "beden_stoklu/1", "mevsim_stoklu/01"])
    X = {"S5": pd.DataFrame([[1.0] * 4], columns=cols[:4]), "S4": pd.DataFrame([[1.0] * 3], columns=cols[4:])}
    T, b = oyun.aile_tablosu(X, "S1+olcek")
    assert b == ("karisim", "olcek") and list(T.columns) == ["karisim/Collection/kalip/regular", "olcek/log_m2"]
    T, b = oyun.aile_tablosu(X, "S1_stoklu")
    assert b == ("karisim_stoklu",) and list(T.columns) == ["karisim_stoklu/Collection/kalip/regular"]
    for ad, (temel, bloklar) in oyun.ABLASYON_AILELERI.items():
        assert set(bloklar) <= set(ozellikler.AILELER[temel]), ad
    assert set(oyun.DEMO_AILELERI) <= set(oyun.ABLASYON_AILELERI)


def test_sehir_iklim_uyumu():
    m = pd.DataFrame({"magaza_id": ["A", "B", "C", "D", "ONL"], "sehir": ["İstanbul", "İstanbul", "İzmir", "Van", "x"],
                      "tip": ["AVM", "Outlet", "AVM", "Cadde", "Online"]})
    g = pd.DataFrame({"magaza_id": ["A", "B", "C", "D", "ONL"],
                      "iklim": ["ilıman", "ilıman", "ilıman", "soguk", "?"]})
    u = oyun.sehir_iklim_uyumu(m, g)
    assert (u["sehir"], u["ortusen"]) == (3, 2)
    assert u["farkli"] == [{"sehir": "İzmir", "vaka": "sicak_sahil", "simulator": ["ılıman"]}]


def test_kurallar_listesi_kural_modulu_ile():
    assert oyun.KURALLAR == ("k1", "k2", "k3", "k4")
    assert all(callable(getattr(kural, f)) for f in ("bolge", "ciro_sinifi", "bolge_ciro", "konum"))
