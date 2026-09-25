import numpy as np
import pandas as pd
import pytest

from rpt import hikaye


def test_bitis_haftasi():
    panel = pd.DataFrame({
        "option_id": ["A"] * 5 + ["B"] * 5,
        "h": list(range(5)) * 2,
        "depo_stok": [400, 300, 100, 5, 0, 400, 300, 200, 100, 50],
        "magaza_stok": [0, 500, 300, 150, 100, 0, 500, 400, 300, 200],
    })
    opt = pd.DataFrame({"option_id": ["A", "B"], "ilk_alim": [1000, 1000]})
    b = hikaye.bitis_haftasi(panel, opt)
    # A: h=3'te depo 5 ≤ 20 ve 155 ≤ 200 → 3; B hiç bitmez
    assert b["A"] == 3
    assert "B" not in b.index


@pytest.mark.veri
def test_rpt_akibeti_tutarli(veri):
    t, opt = veri["t"], veri["opt"]
    r = hikaye.rpt_siparisleri(t, opt)
    assert (r["adet"] > 0).all()
    for sezon in ("AW24", "SS25"):
        ak = hikaye.rpt_akibeti(t, opt, sezon)
        assert (ak["rpt_magazaya"] + ak["rpt_depoda_kalan"] == ak["rpt"]).all()
        assert (ak["rpt_depoda_kalan"] >= 0).all() and (ak["rpt_magazaya"] >= 0).all()
        assert ak["rpt"].sum() == r.loc[r["sezon_kodu"] == sezon, "adet"].sum()
    # Lumoda'nın kuralı: option başına en fazla bir RPT, yalnız Collection
    assert r.groupby("option_id").size().max() == 1
    assert set(opt.set_index("option_id").loc[r["option_id"], "line"]) == {"Collection"}
    # lansmandan 3–6 hafta sonra verilir
    assert r["siparis_h"].between(3, 6).all()
