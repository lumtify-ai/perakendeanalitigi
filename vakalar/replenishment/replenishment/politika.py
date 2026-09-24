"""Politikalar: karar gününde hedef ve öngörü üretimi.

`Politika` protokolü `oyun.oyna` döngüsünün her karar gününde çağırdığı
arayüzdür: geçmişe sızmayan (`gozlenen`, karar günü dahil sonrası
sıfırlanmış) satış matrisinden hedef adet ile öngörüyü üretir.

`KuralPolitikasi` `ihtiyac.kural_ongorusu` ile güvenlik stokunun büyüğünü
alır (güvenlik stoku taban, eklenen tampon değil).
`TahminPolitikasi` Task 8'in `Tahminci`'sini kullanır; `tahmin` modülü
burada erken (eager) import edilmez — Task 8 henüz yokken bu modülün
testleri çalışabilsin diye tip yalnız `typing.TYPE_CHECKING` altında
görünür.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np

from .dunya import Dunya
from .ihtiyac import GuvenlikStoku, guvenlik_stoku, kural_ongorusu

if TYPE_CHECKING:
    from .tahmin import Tahminci


class Politika(Protocol):
    def hedef(
        self,
        gozlenen: np.ndarray,
        dunya: Dunya,
        karar_gunu: int,
        stok: np.ndarray,
        stoklu_gunluk: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """(hedef_oc float[OC], ongoru_oc float[OC]). `gozlenen` yalnız
        karar_gunu dahil öncesini içerir (sonrası sıfırlanmış kopya)."""
        ...


@dataclass
class KuralPolitikasi:
    ss: GuvenlikStoku
    katsayilar: dict[str, float]  # ust_kategori → gün katsayısı

    def hedef(
        self,
        gozlenen: np.ndarray,
        dunya: Dunya,
        karar_gunu: int,
        stok: np.ndarray,
        stoklu_gunluk: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        ongoru = kural_ongorusu(gozlenen, dunya, karar_gunu, self.katsayilar, stoklu_gunluk)
        ss = guvenlik_stoku(self.ss, gozlenen, dunya, karar_gunu, stoklu_gunluk)
        # Safety stock TABANDIR, öngörünün üstüne eklenen tampon değil:
        # sahadaki karşılığı "minimum sergileme"dir — raf hiç boşalmasın
        # diye konan alt sınır. Toplarsak hedef gerçek talebin belirgin
        # üstüne çıkar ve zincir her hafta fazla mal taşır.
        return np.maximum(ongoru, ss), ongoru


@dataclass
class TahminPolitikasi:
    tahminci: "Tahminci"  # Task 8

    def hedef(
        self,
        gozlenen: np.ndarray,
        dunya: Dunya,
        karar_gunu: int,
        stok: np.ndarray,
        stoklu_gunluk: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        # stoklu_gunluk yok sayılır: saf tahmin tanımı (LightGBM) değişmiyor.
        tahmin = self.tahminci.tahmin_et(gozlenen, dunya, karar_gunu)
        return tahmin, tahmin


@dataclass
class TahminTabanPolitikasi:
    """LightGBM öngörüsü + `KuralPolitikasi`'nin aynı taban kuralı.

    Var oluş sebebi karşılaştırmanın adil olması: `TahminPolitikasi`
    öngörüyü çıplak hedef yapar, `KuralPolitikasi` ise öngörünün altına
    bir taban koyar. İkisini kıyaslarsak politika farkını ölçeriz, öngörü
    farkını değil. Bu politika tabanı tahmin koluna da verir; geriye tek
    değişken kalır — öngörüyü kim üretiyor.
    """

    tahminci: "Tahminci"
    ss: GuvenlikStoku

    def hedef(
        self,
        gozlenen: np.ndarray,
        dunya: Dunya,
        karar_gunu: int,
        stok: np.ndarray,
        stoklu_gunluk: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        ongoru = self.tahminci.tahmin_et(gozlenen, dunya, karar_gunu)
        ss = guvenlik_stoku(self.ss, gozlenen, dunya, karar_gunu, stoklu_gunluk)
        return np.maximum(ongoru, ss), ongoru
