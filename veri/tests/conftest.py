import pytest


@pytest.fixture(scope="session")
def v3_kosu():
    """v3 dünyası, talep matrisi ve varsayılan politikalarla motor çıktısı.

    Bir kez kurulur (~5 sn); v3 birim testleri paylaşır. Akışlar
    `tablolari_uret` ile aynı sırayla tüketilir.
    """
    from perakende_veri.v3.dunya import akislar, dunya_kur, talep_matrisi
    from perakende_veri.v3.simulasyon import simule_et

    rng = akislar()
    dunya = dunya_kur(rng["dunya"])
    talep = talep_matrisi(dunya, rng["talep"])
    ham = simule_et(dunya, talep)
    return {"dunya": dunya, "talep": talep, "ham": ham}
