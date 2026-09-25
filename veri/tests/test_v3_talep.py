import numpy as np
import pytest

from perakende_veri.v3 import sabitler
from perakende_veri.v3.talep import (
    indirim_durumu, mevsim_carpani, mevsim_egrisi, surpriz_beklenen, yasam_egrisi,
    yerel_carpan_beklenen,
)


def test_yasam_egrisi_tepesi_bir_ve_dorduncu_haftada():
    h = np.arange(0, 30)
    f = yasam_egrisi(h, 4.0)
    assert f.max() == pytest.approx(1.0)
    assert int(np.argmax(f)) == 3            # 4. hafta (h = aτ − 1)
    assert f[11] < 0.5 and f[11] > 0.3        # 12. hafta: tepenin ~%40'ı
    assert f[29] < 0.05


def test_yasam_egrisi_lansmandan_once_sifir():
    assert yasam_egrisi(-0.5, 4.0) == 0.0
    assert yasam_egrisi(0.0, 4.0) > 0


def test_yasam_egrisi_dizi_tau():
    f = yasam_egrisi(np.array([[3.0, 3.0]]), np.array([3.2, 4.8]))
    assert f.shape == (1, 2)
    assert (f <= 1.0 + 1e-12).all()


def test_mevsim_ortalamasi_bir():
    ay = np.linspace(1, 13, 1200, endpoint=False)
    for alt in sabitler.MEVSIM:
        assert mevsim_egrisi(alt, ay).mean() == pytest.approx(1.0, rel=0.01)


def test_mevsim_yonleri():
    assert mevsim_egrisi("Mont", 12.5) > 2 * mevsim_egrisi("Mont", 7.0)
    assert mevsim_egrisi("Şort", 6.5) > 3 * mevsim_egrisi("Şort", 12.5)


def test_line_mevsimi_yumusatir():
    kis = 12.5
    assert mevsim_carpani("Mont", "NOS", kis) < mevsim_carpani("Mont", "Collection", kis)
    assert mevsim_carpani("Mont", "Collection", kis) == pytest.approx(mevsim_egrisi("Mont", kis))


def test_indirim_takvimi():
    oran, carpan = indirim_durumu(np.array([-1, 0, 27, 28, 60]))
    assert list(oran) == [0.0, 0.30, 0.30, 0.50, 0.50]
    assert list(carpan) == [1.0, 1.6, 1.6, 2.2, 2.2]


def test_beklenen_carpanlar():
    assert surpriz_beklenen("Collection") == pytest.approx(np.exp(0.55**2 / 2))
    assert surpriz_beklenen("NOS") < surpriz_beklenen("Basic") < surpriz_beklenen("Collection")
    assert yerel_carpan_beklenen("Collection") > yerel_carpan_beklenen("NOS") > 0.9
