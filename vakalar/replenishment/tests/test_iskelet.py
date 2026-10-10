"""v4 geçişinin iskeleti: geçici v2 atlama listesi yalnız küçülür."""

from pathlib import Path

from conftest import GECICI_V2, GECICI_V2_ILK


def test_gecici_v2_yalniz_kucullur():
    assert set(GECICI_V2) <= GECICI_V2_ILK


def test_gecici_v2_modulleri_dosya_olarak_var():
    # listede kalan modülün eski testi diskte durur (taşınınca satır da dosyadaki atlama da kalkar)
    for ad in GECICI_V2:
        assert (Path(__file__).parent / f"{ad}.py").exists(), ad
