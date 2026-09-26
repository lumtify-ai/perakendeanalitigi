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
