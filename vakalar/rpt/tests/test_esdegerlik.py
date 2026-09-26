"""Kilit: vakanın 'mevcut' kolu v3'ün dışa aktarılan tablolarını üretir."""

import numpy as np
import pandas as pd
import pytest
from perakende_veri.v3.simulasyon import simule_et

from rpt import dagitim, kaynak, oyun, politika


@pytest.mark.veri
def test_mevcut_kolu_disa_aktarilan_tablolar(veri, yol0):
    ham = yol0["ham"][("mevcut", "mevcut")]
    t = kaynak.tablolar_ham(veri["dunya"], ham)
    for ad, kolon in (("satis", "adet"), ("kayip_satis", "kayip_adet"), ("stok", "stoklu_gun"),
                      ("sevkiyat", "adet"), ("depo_stok", "adet")):
        anahtar = [k for k in ("tarih", "magaza_id", "urun_id", "tip") if k in t[ad].columns]
        a = t[ad][anahtar + [kolon]].sort_values(anahtar + [kolon]).reset_index(drop=True)
        b = veri["t"][ad][anahtar + [kolon]].sort_values(anahtar + [kolon]).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_dtype=False)


@pytest.mark.veri
def test_sarmalayicilar_motoru_bozmaz(yol0):
    """Mevcut kolu (Lumoda sarmalı + 'mevcut' dağıtım nesnesi) = varsayılan motor."""
    b = yol0["baglam"]
    ham, _, _ = oyun.kos(b, "mevcut", "mevcut")
    ref = simule_et(b.dunya, b.talep)
    for ad in ("satis", "kayip_satis", "sevkiyat"):
        pd.testing.assert_frame_equal(ham[ad], ref[ad])


@pytest.mark.veri
@pytest.mark.parametrize("kural", ["b", "c", "d"])
def test_kural_rptsiz_kolda_etkisiz(yol0, kural):
    """Kurallar yalnız RPT'si gelmiş option'a dokunur: rpt_yok kolunda fark yok."""
    b = yol0["baglam"]
    ham, _, _ = oyun.kos(b, "rpt_yok", kural)
    ref = yol0["ham"][("rpt_yok", "mevcut")]
    pd.testing.assert_frame_equal(ham["sevkiyat"], ref["sevkiyat"])
    pd.testing.assert_frame_equal(ham["kayip_satis"], ref["kayip_satis"])


@pytest.mark.veri
def test_rptsiz_optionlar_kollar_arasi_ayni(yol0):
    """v3 operasyon rastgeleliği politikadan bağımsız: RPT'siz option kolda aynen kalır."""
    from rpt import olcutler

    b = yol0["baglam"]
    ham, _, _ = oyun.kos(b, "oneri", "d")
    for G in b.oyun_sezonlari:
        ops = oyun.oyun_optionlari(b.dunya, G)
        a = olcutler.option_olcutleri(b.dunya, ham, ops).set_index("option")
        t = olcutler.option_olcutleri(b.dunya, yol0["ham"][("rpt_yok", "mevcut")], ops).set_index("option")
        r = a["rpt"] == 0
        assert r.sum() > 50
        pd.testing.assert_frame_equal(a[r], t[r])
