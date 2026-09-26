import contextlib
import io

import pytest

import rapor_b
from rpt import oyun


@pytest.mark.veri
def test_rapor_b_duman(yol0):
    v = rapor_b.VeriB(yol0, oyun.tum_kollar(yol0))
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        rapor_b.aday_bolumu(v)
        rapor_b.miktar_bolumu(v)
        rapor_b.sonuc_bolumu(v)
    cikti = tampon.getvalue()
    for bolum in ("ADAY (4. yazı)", "MİKTAR (5. yazı)", "SONUÇ (6. yazı)", "MDL169-EKR", "MDL190-HAK"):
        assert bolum in cikti
    assert v.K["en_iyi"] in ("b", "c", "d")
