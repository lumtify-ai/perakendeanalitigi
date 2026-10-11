"""`replenishment.oyun` (asgari: kalibrasyon alt komutu, Ruling R24).

Kalibrasyon koşucusunun (`kalibrasyon_kosucusu`: `KuralKol` + motor + ölçütler)
bağlantısı KÜÇÜK dünyada kısa koşularla sınanır: pencere test için 2023
sonbaharına çekilir (`Ayar.pencere`; kalibrasyonun kendisi hep KAL_* verir,
`tests/test_kalibrasyon.py`)."""

from datetime import date

import pandas as pd
import pytest

from replenishment import oyun
from replenishment.dagitim import KoliKurali
from replenishment.politika import Ayar

PENCERE = (date(2023, 9, 4), date(2023, 10, 1))     # dört pazartesi
SON = date(2023, 10, 2)                             # koşunun son günü (fotoğraf 10-02 sabahı)


def _n():
    from replenishment import motor

    w = motor.dunya("kucuk")
    return int((pd.Timestamp(SON) - pd.Timestamp(w.takvim["tarih"].iloc[0])).days) + 1


@pytest.fixture(scope="module")
def kos_fn():
    return oyun.kalibrasyon_kosucusu(olcek="kucuk", onbellek=None, gun_sayisi=_n(), ilerleme=None)


@pytest.mark.parametrize("ayar", [
    Ayar(kisitsiz=True, pencere=PENCERE),
    Ayar(koli=KoliKurali("A", alfa=0.6, beta=2), tavan=40.0, pencere=PENCERE),
], ids=["kisitsiz", "kisitli"])
def test_kalibrasyon_kosucusu_olcer(kos_fn, ayar):
    o = kos_fn("t_kal", ayar)
    assert set(o) >= {"bulunabilirlik", "toplama_maliyeti_tl", "magaza_stok_son", "acik_adet", "koli_sayisi"}
    assert 0 < o["bulunabilirlik"] <= 100
    assert o["magaza_stok_son"] > 0
    assert o["gonderilen_adet"] > 0
    assert o["toplama_maliyeti_tl"] == o["acik_adet"] * 10 + o["koli_sayisi"] * 20
    if not ayar.kisitsiz:
        assert o["koli_sayisi"] > 0


def test_bilinmeyen_alt_komut():
    with pytest.raises(SystemExit):
        oyun.main(["bilinmeyen"])
