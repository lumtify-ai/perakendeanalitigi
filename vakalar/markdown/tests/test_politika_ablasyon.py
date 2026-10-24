"""`markdown.politika_ablasyon` (Ruling R24): kuralın ayrıştırma kolları. `KuralTakvim` yalnız pencereyi (indirim
günü), `KuralDeposuz` yalnız stoğu (raf + yolda) değiştirir; ikisinin `parametreler()`'i kendi kod özetini taşır,
vakanın simülasyon kod özeti bu modülden bağımsızdır. Oyuncak `test_politika`'nınki."""

import pytest
from test_politika import CIK_SS, IND_SS, PEN, TEST, _dunya, _kos, _kural_g, _temel

from markdown import politika, politika_ablasyon, simulasyon


def test_kural_takvim_penceresi():
    """Pencere indirim günü: serbest pencerede (05-05) kural derinleşirken takvim kolu oran 0 tutar ve ilk kararı
    indirim gününde verir; tabanı yok (kip erken_yok)."""
    w = _dunya()
    k = politika_ablasyon.KuralTakvim(_temel, TEST, alfa=0.1)
    assert k.pencere == "takvim" and k.taban == 0.0
    assert k(_kural_g(w, PEN[0]))[0, 0] == 0.0
    assert politika.Kural(_temel, TEST, alfa=0.1)(_kural_g(w, PEN[0]))[0, 0] == 0.2
    k = politika_ablasyon.KuralTakvim(_temel, TEST, alfa=0.1)
    assert k(_kural_g(w, IND_SS))[0, 0] == 0.2
    assert set(k.kayit_tablosu()["gun"]) == {IND_SS}
    p = k.parametreler()
    assert (p["kol"], p["pencere"], p["taban"], p["alfa"]) == ("kural_takvim", "takvim", 0.0, 0.1)
    # karar yokken (oran yerinde) bütün pencere dışı günler 0
    k = politika_ablasyon.KuralTakvim(_temel, TEST, alfa=100.0)
    for d, y in _kos(k, w, range(PEN[0], IND_SS)).items():
        assert y[0, 0] == 0.0 and y[0, 2] == 0.0, d


def test_kural_deposuz_stogu():
    """Stok yalnız raf + yolda (10 + 5 + 10 = 25): depo (300) ve açık sipariş (100) sayılmaz. Kural 0,9'da derinleşir
    (kapsama 425 ÷ 4 ÷ kalan = 0,949), deposuz kol derinleşmez (25 ÷ 4 ÷ kalan küçük)."""
    w = _dunya()
    d = PEN[0]
    assert politika.Kural(_temel, TEST, alfa=0.9)(_kural_g(w, d))[0, 0] == 0.2
    k = politika_ablasyon.KuralDeposuz(_temel, TEST, alfa=0.9)
    assert k(_kural_g(w, d))[0, 0] == 0.0
    satir = k.kayit_tablosu().iloc[0]
    kalan = CIK_SS - d
    assert satir["satilabilir"] == 25 and satir["tahmini_satis"] == pytest.approx(min(25, 4.0 * kalan))
    # aynı stokta (depo ve sipariş yok) iki kol aynı kararı verir
    for alfa in (0.01, 0.1):
        g1, g2 = _kural_g(w, d, depo=0, siparis=0), _kural_g(w, d, depo=0, siparis=0)
        assert politika_ablasyon.KuralDeposuz(_temel, TEST, alfa)(g1)[0, 0] == \
            politika.Kural(_temel, TEST, alfa)(g2)[0, 0]
    p = k.parametreler()
    assert (p["kol"], p["pencere"], p["stok"]) == ("kural_deposuz", "serbest", "raf_yolda")


def test_kod_ozeti_anahtarda_vaka_ozeti_bagimsiz(tmp_path):
    """Kolların `kod`'u bu modülün ve politika/model/tahmin'in içerik özetidir: dosya değişince değişir; vakanın
    simülasyon kod özeti (koşan ızgaranın anahtarı) bu modülden bağımsızdır."""
    for sinif in politika_ablasyon.KOLLAR.values():
        assert sinif(_temel, TEST, 1.0).parametreler()["kod"] == politika_ablasyon.kod_ozeti()
    kopya = tmp_path / "markdown"
    kopya.mkdir()
    for y in simulasyon.PAKET_KOKU.glob("*.py"):
        (kopya / y.name).write_bytes(y.read_bytes())
    once, vaka = politika_ablasyon.kod_ozeti(kopya), simulasyon.vaka_kod_ozeti(kopya)
    assert once == politika_ablasyon.kod_ozeti() and vaka == simulasyon.vaka_kod_ozeti()
    for ad in politika_ablasyon.KOD_DOSYALARI:
        y = kopya / ad
        eski = y.read_bytes()
        y.write_bytes(eski + b"\n# degisti\n")
        assert politika_ablasyon.kod_ozeti(kopya) != once, ad
        if ad == "politika_ablasyon.py":
            assert simulasyon.vaka_kod_ozeti(kopya) == vaka
        y.write_bytes(eski)
    assert politika_ablasyon.kod_ozeti(kopya) == once
