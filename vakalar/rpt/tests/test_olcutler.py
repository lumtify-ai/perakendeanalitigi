import pandas as pd

from rpt import olcutler


def test_gercek_gunluk_elle():
    d = pd.Timestamp("2025-02-10")
    satis = pd.DataFrame({"tarih": [d, d, d], "magaza_id": ["M1", "M1", "M2"],
                          "urun_id": ["A-S", "A-S", "B-S"], "adet": [3, -1, 2]})
    ikame = pd.DataFrame({"tarih": [d], "magaza_id": ["M1"], "urun_id": ["A-S"], "adet": [1]})
    kars = pd.DataFrame({"tarih": [d, d], "magaza_id": ["M1", "M3"], "urun_id": ["A-S", "A-S"],
                         "talep": [6, 4], "kendi_satis": [2, 0], "karsilanmayan": [4, 4]})
    urun = pd.DataFrame({"urun_id": ["A-S", "B-S"], "option_id": ["A", "B"]})
    g = olcutler.gercek_gunluk(satis, kars, ikame, urun).set_index(["magaza_id", "urun_id"])
    assert g.loc[("M1", "A-S"), "talep"] == 3 - 1 + 4      # = hakemin talebi (6)
    assert g.loc[("M3", "A-S"), "talep"] == 4
    assert g.loc[("M2", "B-S"), "talep"] == 2
    assert len(olcutler.gercek_gunluk(satis, kars, ikame, urun, opsiyonlar=["B"])) == 1
