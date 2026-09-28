"""v4 ortak fixture'ları.

`kucuk_dunya`: `dunya_kur(Olcek.KUCUK)` bir kez kurulur, oturum boyunca
paylaşılır (salt okunur kabul edilmelidir). `kucuk_kosu`: o dünyada
varsayılan (Lumoda) politikalarla tam motor koşusu (Görev 12), oturum
boyunca paylaşılır.

`tam_kosu` (Görev 17): TAM ölçekte `tablolari_uret(donus_ham=True)` bir
kez koşar (`pytest -m yavas` TAM'ı tek kez kurar); sözlük: `dunya`, `ham`,
`tablolar` (yayımlanan, kirli), `gizli` (`gizli_gercek`), `sure_sn`
(`tablolari_uret`'in duvar saati süresi; yazma hariç). Yalnız `yavas`
işaretli testler ister.
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


@pytest.fixture(scope="session")
def tam_kosu():
    import time

    from perakende_veri.v4.magaza import Olcek
    from perakende_veri.v4.tablolar import gizli_gercek
    from perakende_veri.v4.uret import tablolari_uret

    bas = time.perf_counter()
    tablolar, dunya, ham = tablolari_uret(Olcek.TAM, donus_ham=True)
    sure = time.perf_counter() - bas
    print(f"\ntablolari_uret(TAM): {sure:.1f} sn")
    return {
        "dunya": dunya,
        "ham": ham,
        "tablolar": tablolar,
        "gizli": gizli_gercek(dunya, ham),
        "sure_sn": sure,
    }
