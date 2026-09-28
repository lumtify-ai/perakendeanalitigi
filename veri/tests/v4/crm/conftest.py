"""v4 CRM (B) ortak fixture'ları.

`kucuk_girdi`: `girdi_kur(Olcek.KUCUK)` bir kez kurulur, oturum boyunca
paylaşılır (salt okunur kabul edilmelidir).
"""

import pytest


@pytest.fixture(scope="session")
def kucuk_girdi():
    from perakende_veri.v4.crm.girdi import girdi_kur
    from perakende_veri.v4.magaza import Olcek

    return girdi_kur(Olcek.KUCUK)


@pytest.fixture(scope="session")
def kucuk_crm(kucuk_girdi):
    """KUCUK girdide B'nin tam koşusu (`crm_simule_et`, gün 0'dan D'ye;
    salt okunur kabul edilmelidir)."""
    from perakende_veri.v4.crm.dongu import crm_simule_et

    return crm_simule_et(kucuk_girdi)
