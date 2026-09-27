"""v4 ortak fixture'ları.

`kucuk_dunya`: `dunya_kur(Olcek.KUCUK)` bir kez kurulur, oturum boyunca
paylaşılır (salt okunur kabul edilmelidir). `kucuk_kosu`: o dünyada
varsayılan (Lumoda) politikalarla tam motor koşusu (Görev 12), oturum
boyunca paylaşılır.
"""

import pytest


@pytest.fixture(scope="session")
def kucuk_dunya():
    from perakende_veri.v4.dunya import dunya_kur
    from perakende_veri.v4.magaza import Olcek

    return dunya_kur(Olcek.KUCUK)


@pytest.fixture(scope="session")
def kucuk_kosu(kucuk_dunya):
    from perakende_veri.v4.motor import simule_et

    return simule_et(kucuk_dunya)
