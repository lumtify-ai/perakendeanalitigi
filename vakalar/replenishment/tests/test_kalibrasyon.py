import json

import pytest

from replenishment import sabitler
from replenishment.dagitim import KoliKurali
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.kalibrasyon import Kalibrasyon, en_yakin, maliyet_secimi
from replenishment.kos import senaryo_anahtari, senaryolar


def test_en_yakin_esitlikte_kucuk_deger():
    assert en_yakin({2: 90.0, 3: 96.0, 4: 94.0}, hedef=95.0) == 3
    assert en_yakin({2: 94.0, 4: 96.0}, hedef=95.0) == 2


def test_maliyet_secimi_bulunabilirlik_esigini_korur():
    satirlar = [
        {"ad": "a", "bulunabilirlik": 95.0, "toplama_maliyeti_tl": 900},
        {"ad": "b", "bulunabilirlik": 94.5, "toplama_maliyeti_tl": 500},
        {"ad": "c", "bulunabilirlik": 93.0, "toplama_maliyeti_tl": 100},
    ]
    assert maliyet_secimi(satirlar)["ad"] == "b"


def test_senaryolar_36_senaryo_kural_ve_tahmin():
    liste = senaryolar()
    assert len(liste) == 36
    kural = [s for s in liste if s["yontem"] == "kural"]
    tahmin = [s for s in liste if s["yontem"] == "tahmin"]
    assert len(kural) == 27
    assert len(tahmin) == 9
    assert all(set(s) == {"yontem", "alim", "koli", "ss"} for s in kural)
    assert all(set(s) == {"yontem", "alim", "koli"} for s in tahmin)
    assert {s["koli"] for s in liste} == {"A", "B", "C"}
    assert {s["ss"] for s in kural} == {"sabit", "ros", "istatistik"}
    assert {round(s["alim"], 2) for s in liste} == set(sabitler.ALIM_ORANLARI)


def test_senaryolar_benzersiz_anahtar():
    liste = senaryolar()
    anahtarlar = [senaryo_anahtari(s) for s in liste]
    assert len(anahtarlar) == len(set(anahtarlar))


def test_senaryo_anahtari_bicimi():
    assert senaryo_anahtari({"yontem": "kural", "alim": 0.8, "koli": "A", "ss": "ros"}) == "kural|80|A|ros"
    assert senaryo_anahtari({"yontem": "tahmin", "alim": 0.6, "koli": "C"}) == "tahmin|60|C|-"


@pytest.mark.veri
def test_yol_calistir_var_olan_dosyayi_atlar(tmp_path, monkeypatch):
    """`kos.kos`, yolları ayrı süreçlerde (`ProcessPoolExecutor`) çalıştırır;
    `monkeypatch` çocuk süreçlere sızmaz. Kaldığı yerden sürme mantığının
    kendisi `_yol_calistir` içinde olduğundan onu doğrudan (aynı süreçte)
    çağırarak test ediyoruz — `kos` yalnızca bunu yollar üzerinde paralel
    dağıtan ince bir sarmalayıcıdır."""
    import replenishment.kos as kos_mod

    monkeypatch.setattr(sabitler, "CIKTI", tmp_path)
    monkeypatch.setattr(
        kos_mod, "senaryolar", lambda: [{"yontem": "kural", "alim": 0.6, "koli": "A", "ss": "sabit"}]
    )

    kal = Kalibrasyon(
        katsayilar={},
        ss={"sabit": GuvenlikStoku("sabit", 2), "ros": GuvenlikStoku("ros", 3), "istatistik": GuvenlikStoku("istatistik")},
        varsayilan_ss="sabit",
        koli={"A": KoliKurali("A"), "B": KoliKurali("B"), "C": KoliKurali("C")},
        hedef_bulunabilirlik=90.0,
        acik_kapasite=1000,
        tahmin_parametreleri={},
        tablo=[],
    )

    kos_mod._yol_calistir(0, kal)
    hedef = tmp_path / "yol0" / "kural_60_A_sabit.json"
    assert hedef.exists()

    # Dosyayı elle bozup tekrar koşuyoruz: var olan dosya atlanmalı, değişmemeli.
    hedef.write_text(json.dumps({"sentinel": True}), encoding="utf-8")
    kos_mod._yol_calistir(0, kal)
    assert json.loads(hedef.read_text(encoding="utf-8")) == {"sentinel": True}
