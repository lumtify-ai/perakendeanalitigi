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
def tam_crm(tam_kosu):
    """TAM A (`tam_kosu`, sabitler.TOHUM) üzerinde B'nin yayımlanan tohumla
    (CRM_TOHUM) tam koşusu: `tablolar` (yayımlanan altı tablo), `gizli`
    (`crm_gizli_gercek`), `girdi`, `olcut` (Görev 14 ölçütleri, ham
    sonuçtan hesaplanıp ham bırakılır), `sure_sn` (B, A ve yazma hariç).
    Yalnız `yavas` testler ister."""
    import gc
    import time

    from perakende_veri.v4.crm.girdi import girdi_hamdan
    from perakende_veri.v4.crm.uret import tablolari_uret_crm

    from .test_crm_kalibrasyon import a_satis_ozeti, kalibrasyon_olcutleri

    girdi = girdi_hamdan(tam_kosu["dunya"], tam_kosu["ham"])
    bas = time.perf_counter()
    tablolar, ham = tablolari_uret_crm(girdi=girdi, donus_ham=True)
    sure = time.perf_counter() - bas
    print(f"\ntablolari_uret_crm(TAM): {sure:.1f} sn")
    olcut = kalibrasyon_olcutleri(tablolar, ham, a_satis_ozeti(girdi))
    gizli = ham.gizli_gercek()
    del ham
    gc.collect()
    return {"girdi": girdi, "tablolar": tablolar, "gizli": gizli, "olcut": olcut, "sure_sn": sure}


@pytest.fixture(scope="session")
def kucuk_crm(kucuk_girdi):
    """KUCUK girdide B'nin tam koşusu (`crm_simule_et`, gün 0'dan D'ye;
    salt okunur kabul edilmelidir)."""
    from perakende_veri.v4.crm.dongu import crm_simule_et

    return crm_simule_et(kucuk_girdi)
