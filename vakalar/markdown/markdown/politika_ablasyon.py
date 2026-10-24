"""Kapsama kuralının ayrıştırma kolları (Ruling R24; spec §4.6 SORU 2: kuralın kazancı nereden?).

Karar modülüdür: `politika` ile aynı içe aktarma kısıtları (`perakende_veri`, hakem, simülasyon, ölçütler yok;
dünyanın gizli alanları okunmaz; `tests/test_sizinti.py` `ABLASYON_MODULLERI`). İki kol `politika.Kural`'ın
alt sınıfıdır, yalnız bir şeyi değiştirir:

- `KuralTakvim(temel, test_idx, alfa)`: karar penceresi indirim günü (takvim penceresi), taban yok. Kuralın
  erken başlamasının değeri = `kural − kural_takvim` ("ne zaman"); korunum kipi `erken_yok`.
- `KuralDeposuz(temel, test_idx, alfa)`: satılabilir stok yalnız fiziksel raf + yolda (depo ve açık sipariş
  yok; Lumoda'nın STR'yi mağazaya gidenle ölçmesinin, yani depoyu ve geç gelen RPT'yi görmemesinin
  yaklaşığı). Depoyu görmenin değeri = `kural − kural_deposuz`; korunum kipi `serbest`. Hız `Kural`'ınki
  (ONL dahil): ONL'nin satışı hızda sayılır, stoğu (depo) sayılmaz.

**Anahtar.** Bu modül `simulasyon.SIMULASYON_MODULLERI`'nde değildir (vakanın kod özeti, dolayısıyla koşan
ızgaranın önbelleği değişmez). Onun yerine her kolun `parametreler()`'i `kod`: bu dosyanın ve üstüne kurulduğu
`politika.py`, `model.py`, `tahmin.py`'nin içerik özetini (satır sonları LF) taşır; kodları değişince bu iki
kolun koşu anahtarı değişir (testli).
"""

import hashlib
from pathlib import Path

import numpy as np

from markdown.politika import _K, _PAY, Kural

KOD_DOSYALARI = ("politika_ablasyon.py", "politika.py", "model.py", "tahmin.py")


def kod_ozeti(kok: Path | None = None) -> str:
    """`KOD_DOSYALARI`'nın ad + içerik sha256'sı (LF), ilk 16 hane. `kok`: paket dizini (testler için)."""
    kok = Path(__file__).resolve().parent if kok is None else Path(kok)
    h = hashlib.sha256()
    for ad in KOD_DOSYALARI:
        h.update(ad.encode("utf-8") + b"\0" + (kok / ad).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


KOD = kod_ozeti()


class KuralTakvim(Kural):
    """Kapsama kuralı, karar penceresi indirim günü (modül notu)."""

    ad = "kural_takvim"

    def __init__(self, temel, test_idx, alfa: float):
        super().__init__(temel, test_idx, alfa)
        self.pencere = "takvim"

    def parametreler(self) -> dict:
        return {**super().parametreler(), "kod": KOD}


def raf_yolda(kol, g) -> np.ndarray:
    """[len(test_idx)] fiziksel raf + yolda (depo ve açık sipariş yok; ONL'nin rafı yok)."""
    c, konum, online, _s, _sk = kol._hucre_yapisi(g.dunya)
    raf = np.where(online, 0.0, np.maximum(np.asarray(g.magaza_stok, float)[c], 0)
                   + np.maximum(np.asarray(g.yolda, float)[c], 0))
    return np.bincount(konum, raf, minlength=len(kol.test_idx))


class KuralDeposuz(Kural):
    """Kapsama kuralı, satılabilir stok yalnız raf + yolda (modül notu). Karar `Kural._karar`'ın aynısı, stok
    dışında."""

    ad = "kural_deposuz"

    def _karar(self, g, oo, oran):
        j = np.searchsorted(self.test_idx, oo)
        X = raf_yolda(self, g)[j]
        v = self.hiz(g)[j]
        kalan = (self._cikis[j] - int(g.gun)).astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            kapsama = np.where(v > 0, X / v, np.where(X > 0, np.inf, 0.0))
        derin = kapsama > self.alfa * kalan
        sonraki = _K[np.minimum(np.searchsorted(_K, oran + _PAY, side="left"), len(_K) - 1)]
        tahmini = np.minimum(X, v * kalan)
        return np.where(derin, sonraki, oran), {"tahmini_satis": tahmini, "satilabilir": X,
                                                "beklenen_kalan": X - tahmini}

    def parametreler(self) -> dict:
        return {**super().parametreler(), "stok": "raf_yolda", "kod": KOD}


KOLLAR = {"kural_takvim": KuralTakvim, "kural_deposuz": KuralDeposuz}
