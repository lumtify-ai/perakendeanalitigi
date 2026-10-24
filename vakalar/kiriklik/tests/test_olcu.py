"""`olcu`: kırıklık (net, brüt, dar) ve atıl stok sınıfları. Saf pandas/numpy; oyuncak çiftlerle sınanır,
`veri` işaretli test yayımlanan v4'ün AW24 keşif sayılarını doğrular."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kiriklik import kaynak, olcu


def _hucre(*stoklar, magaza="M1", option="O1") -> pd.DataFrame:
    """(magaza, option) başına beş beden satırı; `stoklar` her biri bir çiftin 5 bedenlik stoğu."""
    satir = []
    for k, st in enumerate(stoklar):
        for i, a in enumerate(st):
            satir.append((f"{magaza}{k}", f"{option}{k}", i + 1, a))
    return pd.DataFrame(satir, columns=["magaza_id", "option_id", "beden_sira", "stok"])


def test_kullanici_ornegi_net_brut():
    # Kullanıcının örneği: asorti 1-1-2-2-1, stok 1-0-0-1-1 -> net 2/5, brüt 4/7
    c = olcu.cift_tablosu(_hucre((1, 0, 0, 1, 1)), asorti=(1, 1, 2, 2, 1))
    r = c.iloc[0]
    assert r.kirik_beden == 2 and r.beden == 5 and r.net == pytest.approx(2 / 5)
    assert r.eksik_adet == 4 and r.asorti_top == 7 and r.brut == pytest.approx(4 / 7)
    assert bool(r.kirik) is True


def test_lumoda_asortisi():
    c = olcu.cift_tablosu(_hucre((1, 0, 0, 1, 1), (1, 1, 2, 1, 1)))
    a, b = c.iloc[0], c.iloc[1]
    assert a.brut == pytest.approx(4 / 7) and a.net == pytest.approx(2 / 5)
    # 1-1-2-1-1: ikinci bedende asortinin altında ama sıfır değil: net 0, brüt 1/7, kırık değil
    assert b.net == 0 and b.brut == pytest.approx(1 / 7) and b.eksik_adet == 1
    assert bool(b.kirik) is False and bool(b.dar_kirik) is False


def test_dar_tanim_uc_beden():
    # 0-1-1-1-1: ilk beden sıfır -> kırık; ara bedenler (2-4) dolu -> dar tanımda kırık değil
    c = olcu.cift_tablosu(_hucre((0, 1, 1, 1, 1), (1, 1, 0, 1, 1), (1, 1, 1, 1, 0)))
    assert c.kirik.tolist() == [True, True, True]
    assert c.dar_kirik.tolist() == [False, True, False]


def test_stoksuz_cift_paydada_yok():
    c = olcu.cift_tablosu(_hucre((0, 0, 0, 0, 0), (1, 2, 2, 1, 1)))
    assert len(c) == 1 and c.iloc[0].magaza_id == "M11"
    assert c.iloc[0].stok == 7


def test_eksik_beden_satiri_sifir_sayilir():
    h = _hucre((1, 2, 2, 1, 1))
    h = h[h.beden_sira != 3]   # üçüncü beden satırı hiç yok
    r = olcu.cift_tablosu(h).iloc[0]
    assert r.kirik_beden == 1 and r.eksik_adet == 2 and r.stok == 5


def test_ozet_toplu_oran():
    c = olcu.cift_tablosu(_hucre((1, 0, 0, 1, 1), (1, 2, 2, 1, 1)))
    o = olcu.ozet(c)
    assert o["stoklu_cift"] == 2 and o["kirik_cift"] == 1 and o["dar_kirik_cift"] == 1
    assert o["kirik_beden"] == 2 and o["beden"] == 10
    assert o["net_oran"] == pytest.approx(2 / 10)          # Σ kırık beden ÷ Σ beden (çift oranlarının ortalaması değil)
    assert o["eksik_adet"] == 4 and o["asorti"] == 14 and o["brut_oran"] == pytest.approx(4 / 14)
    assert o["kirik_cift_oran"] == pytest.approx(1 / 2)


def test_ozet_bos():
    o = olcu.ozet(olcu.cift_tablosu(_hucre((0, 0, 0, 0, 0))))
    assert o["stoklu_cift"] == 0 and o["net_oran"] == 0.0 and o["brut_oran"] == 0.0 and o["kirik_cift_oran"] == 0.0


def test_atil_siniflari():
    satis = np.array([0, 2, 3, 0, 1])
    rafta = np.array([40, 40, 40, 20, 27])
    s = olcu.atil_sinifi(satis, rafta, esik=2)
    assert s.tolist() == ["satmayan", "atil", "satan", "yeni", "yeni"]
    # eşik 1: 2 adet artık satan
    assert olcu.atil_sinifi(satis, rafta, esik=1).tolist() == ["satmayan", "satan", "satan", "yeni", "yeni"]
    # rafta tam 28 gün: yeni değil
    assert olcu.atil_sinifi(np.array([0]), np.array([28]), esik=2).tolist() == ["satmayan"]


def test_karar_modulu_ice_aktarma_kilidi():
    kaynak_ast = ast.parse(Path(olcu.__file__).read_text(encoding="utf-8"))
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
def test_kesif_kirik_aw24(veri_con):
    c = olcu.cift_tablosu(kaynak.karar_girdisi(veri_con, "AW24").hucre)
    o = olcu.ozet(c)
    assert o["stoklu_cift"] == 4051
    assert o["kirik_cift"] == 1873 and o["dar_kirik_cift"] == 1407
    assert round(100 * o["net_oran"], 1) == 20.2 and round(100 * o["brut_oran"], 1) == 21.0
