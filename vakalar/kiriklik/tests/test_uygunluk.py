"""`uygunluk`: kırık çiftin alıcı adaylığı (K4, K18) ve alıcının asorti ihtiyacı. Elle kurulmuş
`KararGirdisi`lerle sınanır; `veri` işaretli test yayımlanan v4'ün aday sayılarını doğrular."""

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from kiriklik import kaynak, uygunluk


def _girdi(satirlar, magazalar=None) -> kaynak.KararGirdisi:
    """`satirlar`: (magaza, option, beden_sira, stok, depo, acik_siparis). `magazalar`: {magaza: uygun}
    (verilmezse hepsi uygun)."""
    hucre = pd.DataFrame(satirlar, columns=["magaza_id", "option_id", "beden_sira", "stok", "depo", "acik_siparis"])
    hucre["urun_id"] = hucre.option_id + "-" + hucre.beden_sira.astype(str)
    hucre["liste_fiyati"], hucre["alis_fiyati"] = 100.0, 40.0
    if magazalar is None:
        magazalar = {m: True for m in hucre.magaza_id.unique()}
    magaza = pd.DataFrame({"magaza_id": list(magazalar), "ad": list(magazalar), "sehir": "X", "bolge": "Y",
                           "tip": "AVM", "uygun": list(magazalar.values())})
    bos = pd.DataFrame()
    return kaynak.KararGirdisi(sezon="AW24", karar=date(2024, 12, 9), indirim=date(2025, 1, 2),
                               cikis=date(2025, 2, 24), hucre=hucre, satis=bos, stoklu=bos, magaza=magaza,
                               optionlar=bos, takvim=bos, kampanya=bos)


def _cift(magaza, option, stoklar, depo=(0,) * 5, acik=(0,) * 5):
    return [(magaza, option, i + 1, s, d, a) for i, (s, d, a) in enumerate(zip(stoklar, depo, acik))]


def test_doldurulamaz_depo_ve_siparis():
    h = pd.DataFrame({"depo": [0, 3, 0, 2], "acik_siparis": [0, 0, 5, 1]}, index=[10, 11, 12, 13])
    s = uygunluk.doldurulamaz(h)
    assert s.tolist() == [True, False, False, False] and s.index.tolist() == [10, 11, 12, 13]


def test_uygun_kirik_cift_depo_ve_siparis_yok():
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1)))
    a = uygunluk.adaylar(g)
    assert len(a) == 1
    r = a.iloc[0]
    assert (r.magaza_id, r.option_id, r.kirik_beden, r.eksik_adet) == ("M1", "O1", 1, 2)
    assert r.net == pytest.approx(1 / 5) and r.brut == pytest.approx(2 / 7)
    assert bool(r.uygun) is True and r.neden == "uygun"
    assert list(a.columns) == ["magaza_id", "option_id", "kirik_beden", "eksik_adet", "net", "brut", "uygun",
                               "neden"]


def test_kirik_olmayan_cift_aday_degil():
    g = _girdi(_cift("M1", "O1", (1, 2, 2, 1, 1)) + _cift("M2", "O1", (0, 0, 0, 0, 0)))
    a = uygunluk.adaylar(g)
    assert a.empty
    # boş çıktı da aynı şemayı taşır (sütun adları ve bool `uygun`)
    assert list(a.columns) == ["magaza_id", "option_id", "kirik_beden", "eksik_adet", "net", "brut", "uygun",
                               "neden"]
    assert a.uygun.dtype == bool


def test_depoda_olan_beden_uygun_degil():
    # ikinci beden kırık ve depoda 6 adet var: replenishment kapatır, transfer adayı değil
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1), depo=(0, 6, 0, 0, 0)))
    r = uygunluk.adaylar(g).iloc[0]
    assert bool(r.uygun) is False and r.neden == "depoda_var"


def test_tek_kirik_bedenin_depolusu_cifti_eler():
    # iki kırık beden (2 ve 4); yalnız dördüncünün deposu var: çift yine uygun değil
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 0, 1), depo=(0, 0, 0, 4, 0)))
    assert uygunluk.adaylar(g).iloc[0].neden == "depoda_var"


def test_depolu_ama_kirik_olmayan_beden_eleme_yapmaz():
    # üçüncü bedenin deposu var ama stoğu dolu (kırık değil); kırık ikinci beden boş: uygun
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1), depo=(0, 0, 9, 0, 0)))
    assert uygunluk.adaylar(g).iloc[0].neden == "uygun"


def test_acik_siparis_uygun_degil():
    # depo yok, ama indirimden önce teslim planlı açık sipariş var (kaynak bunu zaten süzmüş gelir)
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1), acik=(0, 10, 0, 0, 0)))
    r = uygunluk.adaylar(g).iloc[0]
    assert bool(r.uygun) is False and r.neden == "acik_siparis"


def test_neden_onceligi_magaza_depo_siparis():
    # depo ve açık sipariş SKU düzeyindedir: her durum kendi option'ında kurulur
    satir = (_cift("A", "O1", (1, 0, 2, 1, 1), depo=(0, 6, 0, 0, 0), acik=(0, 0, 0, 0, 0))
             + _cift("B", "O2", (1, 0, 2, 0, 1), depo=(0, 0, 0, 0, 0), acik=(0, 5, 0, 5, 0))
             + _cift("C", "O3", (1, 0, 2, 0, 1), depo=(0, 0, 0, 3, 0), acik=(0, 5, 0, 0, 0))
             + _cift("D", "O4", (1, 0, 2, 1, 1), depo=(0, 6, 0, 0, 0)))
    g = _girdi(satir, magazalar={"A": True, "B": True, "C": True, "D": False})
    n = uygunluk.adaylar(g).set_index("magaza_id").neden
    assert n["A"] == "depoda_var"
    assert n["B"] == "acik_siparis"
    assert n["C"] == "depoda_var"        # biri depolu, biri siparişli: depo önce
    assert n["D"] == "magaza"            # mağaza elenmişse depo ne olursa olsun


def test_neden_etiketleri_sabit_kumeden():
    satir = (_cift("A", "O1", (1, 0, 2, 1, 1), depo=(0, 6, 0, 0, 0))
             + _cift("B", "O2", (1, 0, 2, 0, 1), acik=(0, 5, 0, 5, 0))
             + _cift("C", "O3", (1, 0, 2, 1, 1))
             + _cift("D", "O4", (1, 0, 2, 1, 1)))
    g = _girdi(satir, magazalar={"A": True, "B": True, "C": True, "D": False})
    a = uygunluk.adaylar(g)
    assert set(a.neden) == set(uygunluk.NEDENLER)


def test_kapanis_kararli_magaza_disarida():
    # M2 kapanış kararlı (uygun=False): bedenleri depo ve siparişsiz de olsa aday değil, nedeni magaza
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1)) + _cift("M2", "O1", (1, 0, 2, 1, 1)),
               magazalar={"M1": True, "M2": False})
    a = uygunluk.adaylar(g).set_index("magaza_id")
    assert bool(a.loc["M1", "uygun"]) is True
    assert bool(a.loc["M2", "uygun"]) is False and a.loc["M2", "neden"] == "magaza"


def test_kapanis_kararli_magaza_kaynaktan_oyuncak(con):
    # oyuncak dünyada S5'in kapanış kararı karardan önce (kırık tek bedenli stoğu var)
    g = kaynak.karar_girdisi(con, "AW24")
    a = uygunluk.adaylar(g).set_index("magaza_id")
    assert a.loc["S5", "neden"] == "magaza" and bool(a.loc["S5", "uygun"]) is False
    assert "S3" not in a.index          # Outlet kapsamda değil


def test_magazasi_tabloda_olmayan_cift_uygun_degil():
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1)), magazalar={"M9": True})
    assert uygunluk.adaylar(g).iloc[0].neden == "magaza"


def test_ihtiyac_kirik_beden_en_az_bir():
    g = _girdi(_cift("M1", "O1", (1, 0, 2, 1, 1)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {2: 2}   # ikinci beden: asorti 2 - stok 0


def test_ihtiyac_asorti_alti_ama_depolu_beden_yok():
    # asorti 1-2-2-1-1, stok 0-1-2-1-1: ilk beden kırık (ihtiyaç 1), ikinci beden 1 < 2 ama deposu var
    # (K18 ikinci cümle): replenishment'a kalır, ihtiyaçta yok
    g = _girdi(_cift("M1", "O1", (0, 1, 2, 1, 1), depo=(0, 8, 0, 0, 0)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {1: 1}
    # aynı beden açık siparişle de dışarıda kalır
    g = _girdi(_cift("M1", "O1", (0, 1, 2, 1, 1), acik=(0, 4, 0, 0, 0)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {1: 1}
    # ikisi de yoksa asorti altı beden de ihtiyaçtır
    g = _girdi(_cift("M1", "O1", (0, 1, 2, 1, 1)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {1: 1, 2: 1}


def test_ihtiyac_depolu_kirik_beden_cikar():
    # kırık beden depolu ise (çift aday olmasa da) ihtiyaçta yok; ihtiyac aday olmayan çift için de anlamlı
    g = _girdi(_cift("M1", "O1", (0, 0, 2, 1, 1), depo=(5, 0, 0, 0, 0)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {2: 2}


def test_ihtiyac_sirasi_ve_tam_cift_bos():
    g = _girdi(_cift("M1", "O1", (1, 2, 2, 1, 1)) + _cift("M2", "O1", (0, 0, 0, 0, 0)))
    assert uygunluk.ihtiyac(g, "M1", "O1") == {}
    assert uygunluk.ihtiyac(g, "M2", "O1") == {1: 1, 2: 2, 3: 2, 4: 1, 5: 1}
    assert list(uygunluk.ihtiyac(g, "M2", "O1")) == [1, 2, 3, 4, 5]
    assert uygunluk.ihtiyac(g, "YOK", "O1") == {}


def test_depo_sku_duzeyinde_baska_magazadan_okunur():
    # M1'in ikinci beden satırı yok; deposu başka mağazanın satırından (SKU düzeyi, tekrarlı) okunur
    m1 = [r for r in _cift("M1", "O1", (1, 0, 2, 1, 1)) if r[2] != 2]
    m2 = _cift("M2", "O1", (1, 2, 2, 1, 1), depo=(0, 6, 0, 0, 0))
    g = _girdi(m1 + m2)
    assert uygunluk.adaylar(g).set_index("magaza_id").loc["M1", "neden"] == "depoda_var"
    assert uygunluk.ihtiyac(g, "M1", "O1") == {}


def test_ihtiyac_tablosu_ihtiyac_ile_ayni():
    # her (mağaza, option) çifti için tablo ile tek tek `ihtiyac` aynı sonucu verir; tabloda yalnız ihtiyaç > 0 var
    satir = (_cift("M1", "O1", (1, 0, 2, 1, 1)) + _cift("M2", "O1", (1, 2, 2, 1, 1))
             + _cift("M3", "O1", (0, 1, 2, 1, 1), depo=(0, 8, 0, 0, 0))
             + _cift("M4", "O1", (0, 0, 0, 0, 0))
             + _cift("M1", "O2", (0, 0, 2, 0, 1), depo=(5, 0, 0, 0, 0), acik=(0, 0, 0, 3, 0))
             + _cift("M2", "O2", (1, 1, 1, 1, 1)))
    # M3'ün beşinci beden satırı eksik: o beden stok 0 sayılır
    satir = [r for r in satir if not (r[0] == "M3" and r[2] == 5)]
    g = _girdi(satir)
    t = uygunluk.ihtiyac_tablosu(g)
    assert list(t.columns) == ["magaza_id", "option_id", "beden_sira", "ihtiyac"]
    assert (t.ihtiyac > 0).all()
    ciftler = g.hucre[["magaza_id", "option_id"]].drop_duplicates()
    for m, o in ciftler.itertuples(index=False):
        beklenen = uygunluk.ihtiyac(g, m, o)
        alt = t[(t.magaza_id == m) & (t.option_id == o)].sort_values("beden_sira")
        assert dict(zip(alt.beden_sira, alt.ihtiyac)) == beklenen, (m, o)
    assert len(t) == sum(len(uygunluk.ihtiyac(g, m, o)) for m, o in ciftler.itertuples(index=False))


def test_ihtiyac_tablosu_bos_girdi():
    g = _girdi(_cift("M1", "O1", (1, 2, 2, 1, 1)))
    t = uygunluk.ihtiyac_tablosu(g)
    assert t.empty and list(t.columns) == ["magaza_id", "option_id", "beden_sira", "ihtiyac"]


def test_karar_modulu_ice_aktarma_kilidi():
    kaynak_ast = ast.parse(Path(uygunluk.__file__).read_text(encoding="utf-8"))
    alinan = set()
    for n in ast.walk(kaynak_ast):
        if isinstance(n, ast.Import):
            alinan |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            alinan.add(n.module or "")
            alinan |= {f"{n.module}.{a.name}" for a in n.names}
    yasak = ("perakende_veri", "allocation", "kiriklik.hakem", "kiriklik.simulasyon", "kiriklik.olcutler",
             "kiriklik.oyun")
    assert not [a for a in alinan if any(a == y or a.startswith(y + ".") for y in yasak)]


@pytest.mark.veri
@pytest.mark.parametrize("sezon, kirik, uygun", [("AW24", 1873, 819), ("SS25", 1985, 651)])
def test_uygun_aday_sayisi(veri_con, sezon, kirik, uygun):
    a = uygunluk.adaylar(kaynak.karar_girdisi(veri_con, sezon))
    assert len(a) == kirik
    assert int(a.uygun.sum()) == uygun, a.neden.value_counts().to_dict()
