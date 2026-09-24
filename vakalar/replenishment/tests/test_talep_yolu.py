import numpy as np

from replenishment.dunya import dunya_kur
from replenishment.talep_yolu import talep_yolu


def test_talep_yolu_tohumla_tekrar_uretilir():
    d = dunya_kur()
    assert (talep_yolu(d, 3) == talep_yolu(d, 3)).all()
    assert not (talep_yolu(d, 3) == talep_yolu(d, 4)).all()


def test_talep_yolu_ortalamasi_beklenen_talebe_yakin():
    d = dunya_kur()
    t = talep_yolu(d, 1)
    g = d.gun("2025-10-01")
    beklenen = d.beklenen[d.sezon[g]].sum()
    assert abs(t[g - 30 : g].sum(axis=1).mean() / beklenen - 1) < 0.15


def test_talep_yolu_sekli_ve_tipi():
    d = dunya_kur()
    t = talep_yolu(d, 5)
    assert t.shape == (365, len(d.hucre_magaza))
    assert t.dtype == np.int32
    assert (t >= 0).all()
