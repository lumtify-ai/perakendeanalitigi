import numpy as np
import pandas as pd
import pytest
from perakende_veri import sabitler
from perakende_veri.simulasyon import dunya_yeniden_kur, talep_dunyasi
from perakende_veri.uret import tablolari_uret

V2 = sabitler.CIKTI_DIZINI / "parquet"


@pytest.mark.skipif(not (V2 / "satis.parquet").exists(), reason="v2 çıktısı yok")
def test_yeniden_duzenleme_v2yi_bit_bit_korur():
    tablolar = tablolari_uret()
    for ad in ("satis", "stok", "sevkiyat", "kayip_satis"):
        kayitli = pd.read_parquet(V2 / f"{ad}.parquet")
        pd.testing.assert_frame_equal(
            tablolar[ad].reset_index(drop=True), kayitli.reset_index(drop=True),
            check_dtype=False,
        )


def test_dunya_simulasyonla_ayni_ceside_sahip():
    magazalar, urunler, takvim, dunya = dunya_yeniden_kur()
    assert len(dunya["cesit"]) == len(dunya["plan"]["Sonbahar/Kış"])
    assert set(dunya["plan"]) == {"İlkbahar/Yaz", "Sonbahar/Kış"}
    assert (dunya["gercek"]["Sonbahar/Kış"] >= 0).all()
