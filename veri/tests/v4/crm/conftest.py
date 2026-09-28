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
