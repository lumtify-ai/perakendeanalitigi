"""Kırıklık transferinin motor yuvası: karar gününde planın satırlarını `elle_transfer` yuvasına sokan politika.

    plan = simulasyon.transfer_plani(p, w)                    # Plan → motor satır indisleri
    kol  = KirikTransfer(LumodaElleTransfer(), plan, karar_gun)
    Politikalar(elle_transfer=kol, ...)

`KirikTransfer(temel, plan, karar_gun)`: motorun elle transfer adımı (günlük döngü adım 11) her pazartesi
`elle_transfer(g)` çağırır. Kol karar gününde (`g.gun == karar_gun`) planın satırlarını, **sonra** `temel(g)`'nin
(Lumoda'nın bölge müdürü transferleri) satırlarını tek `Transferler` olarak döndürür; başka günlerde yalnız
`temel(g)`. Sıra anlamlıdır: motor aynı kaynaktan birden çok satırı kaynağın stoğuna karşı sırayla keser
(`transfer_uygula`), yani plan Lumoda'nın elle transferinden önce stok tüketir. Plan karar günü sabahı yolun
Lumoda koşusunun stok fotoğrafına göre kurulduğu için (tasarım §0/7) planın satırları normalde kesilmez;
kesilen satır koşuyu geçersiz kılar (Görev 9 sınar).

Kural: bu modül yuva türünü (`Transferler`) `perakende_veri.v4.politika`'dan alır, başka hiçbir şeyi değil
(`tests/test_sizinti.py`). Gizli gerçeğe, motora ve hakeme dokunmaz.

**Kimlik.** `parametreler()` = `{"plan": kimlik, "karar_gun": gün}`; `temel`'in türü `motor.politika_kimligi`
ile anahtara kendiliğinden girer. Planın kimliği planın içeriğidir (`Plan.kimlik`); satır indisleri bundan
türetilir (`simulasyon.transfer_plani`), o yüzden ayrıca anahtara girmez.
"""

from dataclasses import dataclass

import numpy as np
from perakende_veri.v4.politika import Transferler


def _salt_okunur(a) -> np.ndarray:
    a = np.array(a, dtype=np.int64).ravel()          # kopya
    a.flags.writeable = False
    return a


@dataclass(frozen=True, eq=False)
class TransferPlani:
    """Bir planın motor satırları: `kaynak`, `hedef` mağaza satır indisi (`w.magazalar`), `sku` SKU satır
    indisi (`w.urunler`), `adet`; hepsi int64, aynı uzunlukta, salt okunur kopya. `kimlik` kaynak
    `Plan.kimlik`'idir (anahtara girer). Satır sırası motorun uyguladığı sıradır."""

    kaynak: np.ndarray
    hedef: np.ndarray
    sku: np.ndarray
    adet: np.ndarray
    kimlik: str

    def __post_init__(self):
        for ad in ("kaynak", "hedef", "sku", "adet"):
            object.__setattr__(self, ad, _salt_okunur(getattr(self, ad)))
        n = {len(getattr(self, ad)) for ad in ("kaynak", "hedef", "sku", "adet")}
        if len(n) != 1:
            raise ValueError(f"kaynak, hedef, sku, adet aynı uzunlukta olmalı: {sorted(n)}")
        if not isinstance(self.kimlik, str) or not self.kimlik:
            raise ValueError("kimlik boş olmayan metin olmalı (kaynak `Plan.kimlik`)")

    def __len__(self) -> int:
        return len(self.kaynak)

    def transferler(self) -> Transferler:
        """Planın satırları (yazılabilir kopyalar; motor kendi kopyasını alır)."""
        return Transferler(self.kaynak.copy(), self.hedef.copy(), self.sku.copy(), self.adet.copy())


class KirikTransfer:
    """`elle_transfer` yuvası: karar gününde önce plan, sonra `temel`; başka günlerde yalnız `temel` (modül notu)."""

    def __init__(self, temel, plan: TransferPlani, karar_gun: int):
        self.temel = temel
        self.plan = plan
        self.karar_gun = int(karar_gun)

    def parametreler(self) -> dict:
        return {"plan": self.plan.kimlik, "karar_gun": self.karar_gun}

    def __call__(self, g) -> Transferler:
        temel = self.temel(g)
        if int(g.gun) != self.karar_gun or len(self.plan) == 0:
            return temel
        p = self.plan
        return Transferler(*(np.concatenate([a, np.asarray(b, dtype=np.int64)]).astype(np.int64)
                             for a, b in ((p.kaynak, temel.kaynak), (p.hedef, temel.hedef),
                                          (p.sku, temel.sku), (p.adet, temel.adet))))
