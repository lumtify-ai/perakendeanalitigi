import pytest

from replenishment import kaynak
from replenishment.dunya import dunya_kur

pytestmark = pytest.mark.veri


@pytest.fixture(scope="module")
def ortam():
    d = dunya_kur()
    return d, kaynak.baglan()


def test_gozlenen_satis_toplami_mukerrersiz(ortam):
    d, con = ortam
    s = kaynak.gozlenen_satis(con, d)
    (ham,) = con.execute("select sum(adet) from satis where adet > 0").fetchone()
    # mükerrer 40 satır ayıklandı: toplam ham toplamdan küçük, fark pozitif
    assert 0 < ham - int(s.sum()) < 40 * 20


def test_kahin_talep_satis_arti_kayip(ortam):
    d, con = ortam
    assert (kaynak.kahin_talep(con, d) == kaynak.gozlenen_satis(con, d) + kaynak.kayip(con, d)).all()


def test_stok_fotografi_hayalet_satir_icermez(ortam):
    d, con = ortam
    st = kaynak.stok_fotografi(con, d, "2025-09-01")
    assert st.shape == (len(d.hucre_urun),)
    assert (st >= 0).all()
