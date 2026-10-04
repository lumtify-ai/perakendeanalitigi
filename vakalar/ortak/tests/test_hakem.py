"""Hakem: gizli gerçeğin (karşılanmayan talep) tek kapısı.

Sahte `ham` + sahte `dunya` ile ayrışma kuralları elle sınanır; gerçek v4
koşusu (`veri` işaretli) yayımlanan veriyle aynı olduğunu doğrular.

SAHTE DÜNYA (3 gün x 3 hücre; pencere = bütün günler):

    hücre 0 = M001 x S1, hücre 1 = M001 x S2, hücre 2 = M002 x S1

    talep       g0 [5 0 3]   g1 [2 4 0]   g2 [0 3 0]
    satış (+)   g0: h0 3, h2 3 (1'i h0'dan gelen ikame)   g1: h0 2, h1 3
                g2: h0 1 (ikame; talebi 0), h1 1;  g1 h0'da 1 iade (negatif)
    ikame       g0 h2 1, g2 h0 1
    gizli kayıp g0 h0 1, g0 h2 1, g1 h1 1, g2 h1 1
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from perakende_analitik import hakem

SUTUNLAR = ["tarih", "magaza_id", "urun_id", "talep", "kendi_satis", "karsilanmayan",
            "ikameye_giden", "kalici_kayip"]


def _df(sutunlar, satirlar):
    return pd.DataFrame(satirlar, columns=sutunlar).astype("int64")


@pytest.fixture
def sahte(monkeypatch):
    dunya = SimpleNamespace(
        tohum=7,
        magazalar=pd.DataFrame({"magaza_id": ["M001", "M002"]}),
        urunler=pd.DataFrame({"urun_id": ["S1", "S2"]}),
        optionlar=pd.DataFrame({"option_id": ["O1"]}),
        hucre_magaza=np.array([0, 0, 1]),
        hucre_sku=np.array([0, 1, 0]),
    )
    ham = {
        "talep": np.array([[5, 0, 3], [2, 4, 0], [0, 3, 0]], dtype=np.int16),
        "satis": _df(["gun", "hucre", "adet"], [
            (0, 0, 3), (0, 2, 3), (1, 0, 2), (1, 1, 3), (1, 0, -1), (2, 0, 1), (2, 1, 1)]),
        "ikame_satis": _df(["gun", "hucre", "adet"], [(0, 2, 1), (2, 0, 1)]),
        "gizli_kayip": _df(["gun", "hucre", "adet"], [(0, 0, 1), (0, 2, 1), (1, 1, 1), (2, 1, 1)]),
    }
    monkeypatch.setattr("perakende_veri.v4.tablolar.pencere", lambda: (0, 2))
    return SimpleNamespace(dunya=dunya, ham=ham)


def test_ayrisim_kimligi(sahte):
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    assert (k.karsilanmayan == k.ikameye_giden + k.kalici_kayip).all()
    assert (k.karsilanmayan > 0).all() and (k.ikameye_giden >= 0).all()
    assert (k.talep - k.kendi_satis == k.karsilanmayan).all()


def test_elle_beklenen_satirlar(sahte):
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    t0 = k["tarih"].min()   # sahte günün 0'ı = takvimin ilk günü (ısınma başı)
    gun = [t0 + pd.Timedelta(days=g) for g in (0, 0, 1, 2)]
    beklenen = pd.DataFrame(
        {
            "tarih": gun,
            "magaza_id": ["M001", "M002", "M001", "M001"],
            "urun_id": ["S1", "S1", "S2", "S2"],
            "talep": [5, 3, 4, 3],
            "kendi_satis": [3, 2, 3, 1],
            "karsilanmayan": [2, 1, 1, 2],
            "ikameye_giden": [1, 0, 0, 1],
            "kalici_kayip": [1, 1, 1, 1],
        }
    )
    got = k.assign(magaza_id=k.magaza_id.astype(str), urun_id=k.urun_id.astype(str))
    got = got.astype({c: "int64" for c in SUTUNLAR[3:]})
    pd.testing.assert_frame_equal(got.reset_index(drop=True), beklenen)


def test_alinan_ikame_kendi_satistan_dusulur(sahte):
    """M002 x S1, gün 0: talep 3, pozitif satış 3 ama 1'i ikame; kendi satış 2,
    karşılanmayan 1. İkame düşülmeseydi bu satır hiç görünmezdi."""
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    s = k[(k.magaza_id == "M002") & (k.urun_id == "S1")]
    assert len(s) == 1
    assert s.iloc[0][["talep", "kendi_satis", "karsilanmayan", "kalici_kayip"]].tolist() == [3, 2, 1, 1]


def test_iade_ve_talepsiz_hucre_sayilmaz(sahte):
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    gun1 = k["tarih"].min() + pd.Timedelta(days=1)
    # g1 h0: talep 2, satış 2, iade -1 yok sayılır -> karşılanmayan 0, satır yok
    assert not ((k.tarih == gun1) & (k.magaza_id == "M001") & (k.urun_id == "S1")).any()
    # g2 h0: talep 0 (yalnız ikame aldı) -> satır yok
    assert len(k) == 4


def test_pencere_disi_gunler_atilir(sahte, monkeypatch):
    monkeypatch.setattr("perakende_veri.v4.tablolar.pencere", lambda: (1, 2))
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    assert len(k) == 2
    assert k["kalici_kayip"].sum() == 2


def test_sema_r9(sahte):
    k = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    assert list(k.columns) == SUTUNLAR
    assert str(k["tarih"].dtype) == "datetime64[ns]"
    for s in ("magaza_id", "urun_id"):
        assert isinstance(k[s].dtype, pd.CategoricalDtype)
    for s in SUTUNLAR[3:]:
        assert str(k[s].dtype) == "int32", s
    anahtar = list(zip(k["tarih"], k["magaza_id"].astype(str), k["urun_id"].astype(str)))
    assert anahtar == sorted(anahtar)


def test_kendi_satis_talebi_asarsa_hata(sahte):
    sahte.ham["ikame_satis"] = _df(["gun", "hucre", "adet"], [(0, 2, 1)])[:0]   # ikame düşmez
    with pytest.raises(RuntimeError, match="kendi_satis"):
        hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)


def test_kalici_kayip_karsilanmayani_asarsa_hata(sahte):
    sahte.ham["gizli_kayip"] = _df(["gun", "hucre", "adet"], [(0, 0, 3)])  # karşılanmayan 2
    with pytest.raises(RuntimeError, match="kalici_kayip"):
        hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)


def test_kalici_kayip_talepsiz_hucrede_hata(sahte):
    sahte.ham["gizli_kayip"] = _df(["gun", "hucre", "adet"], [(0, 1, 1)])  # talep 0
    with pytest.raises(RuntimeError, match="kalici_kayip"):
        hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)


# ---------------------------------------------------------------- doğrulama

def _yayimlanan(con):
    return {t: con.execute(f"select * from {t}").df() for t in ("satis", "stok", "sevkiyat")}


def test_dogrula_ayni_veride_hepsi_dogru(oyuncak_con):
    d = hakem.dogrula(_yayimlanan(oyuncak_con), oyuncak_con)
    assert d and all(d.values()), d


def test_dogrula_farki_yakalar(oyuncak_con):
    t = _yayimlanan(oyuncak_con)
    t["satis"].loc[t["satis"].index[0], "adet"] += 1          # toplam ve günlük toplam
    d = hakem.dogrula(t, oyuncak_con)
    assert not d["satis_adet"] and not d["gunluk_satis"] and d["satis_satir"]
    t = _yayimlanan(oyuncak_con)
    t["stok"] = t["stok"].iloc[:-1]
    t["sevkiyat"] = t["sevkiyat"].iloc[:-1]
    d = hakem.dogrula(t, oyuncak_con)
    assert not d["stok_satir"] and not d["sevkiyat_satir"] and d["satis_adet"]


def test_dogrulama_basarisizsa_yazmaz(tmp_path, monkeypatch, sahte):
    kars = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    monkeypatch.setattr(hakem, "_kos", lambda: (kars, kars.head(0), {}, 7))
    monkeypatch.setattr(hakem.kaynak, "baglan", lambda: None)
    monkeypatch.setattr(hakem, "dogrula", lambda t, con: {"satis_satir": True, "satis_adet": False})
    yol = tmp_path / "hakem"
    with pytest.raises(RuntimeError, match="satis_adet"):
        hakem.kur(yol)
    assert not yol.exists() or not any(yol.iterdir())


def test_kur_oku_gidis_donus(tmp_path, monkeypatch, sahte):
    from perakende_veri.v4.tablolar import hucre_tablosu

    kars = hakem.karsilanmayan_tablosu(sahte.dunya, sahte.ham)
    ikame = hucre_tablosu(sahte.dunya, sahte.ham["ikame_satis"])
    ikame["adet"] = ikame["adet"].astype("int32")
    monkeypatch.setattr(hakem, "_kos", lambda: (kars, ikame, {}, 7))
    monkeypatch.setattr(hakem.kaynak, "baglan", lambda: None)
    monkeypatch.setattr(hakem, "dogrula", lambda t, con: {"satis_satir": True})
    yol = tmp_path / "hakem"
    hakem.kur(yol)
    o = hakem.oku(yol)
    pd.testing.assert_frame_equal(o["karsilanmayan"], kars)
    assert o["meta"]["tohum"] == 7 and o["meta"]["dogrulama"] == {"satis_satir": True}
    assert o["meta"]["satir_sayilari"] == {"karsilanmayan": 4, "ikame_alinan": 2}
    assert o["meta"]["sure_sn"] >= 0
    assert json.loads((yol / "meta.json").read_text(encoding="utf-8"))["tohum"] == 7
    # ikame_alinan: pencereli ham ikame; tür R9
    assert list(o["ikame_alinan"].columns) == ["tarih", "magaza_id", "urun_id", "adet"]
    assert str(o["ikame_alinan"]["tarih"].dtype) == "datetime64[ns]"
    assert str(o["ikame_alinan"]["adet"].dtype) == "int32"
    assert o["ikame_alinan"]["adet"].tolist() == [1, 1]


def test_oku_yoksa_komutu_soyler(tmp_path):
    with pytest.raises(FileNotFoundError, match="python -m perakende_analitik.hakem"):
        hakem.oku(tmp_path / "yok")


@pytest.mark.veri
def test_gercek_hakem_yayimlananla_ayni(v4_con):   # yavaş: tam koşu
    hakem.kur()
    m = hakem.oku()["meta"]
    assert all(m["dogrulama"].values())
