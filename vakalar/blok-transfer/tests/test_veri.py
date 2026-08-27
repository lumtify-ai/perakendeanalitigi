from datetime import date
from pathlib import Path

import pytest

from blok_transfer.cekirdek import veri
from blok_transfer.cekirdek.parametreler import Parametreler


def test_varsayilan_parametreler():
    p = Parametreler()
    assert p.hiz_penceresi_hafta == 8
    assert p.ufuk_hafta == 8
    assert p.soguma_hafta == 2
    assert p.min_koli == 6
    assert p.adet_maliyeti_tl == 25.0
    assert p.rota_sabiti_tl == 500.0
    assert p.buyuk_cover == 999.0
    assert p.mip_zaman_limiti_sn == 60
    assert p.verici_cover_esigi == 6.0
    assert p.min_satis == 1.0


def test_gercek_veriye_baglanir_ve_karar_tarihini_bulur():
    con = veri.baglan()
    assert veri.karar_tarihi(con) == date(2025, 12, 29)


def test_dosya_yoksa_acik_hata():
    with pytest.raises(FileNotFoundError, match="perakende_veri.uret"):
        veri.baglan(Path("yok/boyle/bir.duckdb"))
