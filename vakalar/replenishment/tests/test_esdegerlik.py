import numpy as np
import pytest

from replenishment import kaynak
from replenishment.dunya import dunya_kur
from replenishment.motor import baslangic_durumu, gunu_isle

pytestmark = pytest.mark.veri


def test_kayitli_sevkiyat_ve_iadeyle_v2_birebir_uretilir():
    d = dunya_kur()
    con = kaynak.baglan()
    talep = kaynak.kahin_talep(con, d)
    gelen = kaynak.sevkiyat(con, d)
    iade = kaynak.iade(con, d)
    satis_v2 = kaynak.gozlenen_satis(con, d)
    kayip_v2 = kaynak.kayip(con, d)
    bas = d.gun("2025-09-01")
    durum = baslangic_durumu(kaynak.stok_fotografi(con, d, "2025-09-01"), [])
    for g in range(bas, 365):
        s, k = gunu_isle(durum, g, talep[g], gelen[g], iade[g], None)
        assert (s == satis_v2[g]).all(), f"gün {g} satış farklı"
        assert (k == kayip_v2[g]).all(), f"gün {g} kayıp farklı"
