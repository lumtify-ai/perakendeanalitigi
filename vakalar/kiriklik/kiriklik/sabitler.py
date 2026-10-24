"""Vaka sabitleri (tasarım §0, Global Constraints). Karar modülüdür: `perakende_veri`'yi içe aktarmaz.

Ölçüme göre bir Ruling'le değişebilir; değiştiren görev sabiti burada değiştirir ve kayıt defterine
Ruling yazar.
"""

from dataclasses import dataclass
from datetime import date

# Test sezonları ve tek karar anı (tasarım §0/5): sezon başına indirimden önceki son ~4 haftadaki ilk
# pazartesi. Başka sezon `ValueError` (yayımlanan veri 2025-12-29'da biter; AW25'in indirimi veride yok).
TEST_SEZONLARI = ("AW24", "SS25")
KARAR = {"AW24": date(2024, 12, 9), "SS25": date(2025, 6, 2)}
LINE = "Collection"

# Asorti: her beş bedenli setin tek standart paketi (`paket` tablosu). Beden sırası küçükten büyüğe.
# Standart (aksesuar) tek bedendir, kırıklığı tanımsızdır ve kapsam dışıdır.
ASORTI = (1, 2, 2, 1, 1)
STANDART_BEDEN_SETI = "Standart"

# Fiziksel mağaza tipleri (Outlet ve Online kapsam dışı).
FIZIKSEL_TIPLER = ("AVM", "Cadde")

# Atıl stok (tasarım §0/2): pencere 28 gün, çift ya da hücre en az 28 gündür rafta olmalı (Lumoda'nın elle
# transfer kuralıyla aynı koşul). Satmayan = pencerede satış 0; atıl = 1 ile x arası. x şirkete göre değişir:
# option × mağaza düzeyinde 2, SKU düzeyinde 1; rapor x ∈ ATIL_DUYARLILIK duyarlılığını basar.
ATIL_PENCERE_GUN = 28
ATIL_ESIK_OPTION = 2
ATIL_ESIK_SKU = 1
ATIL_DUYARLILIK = (1, 2, 3)


@dataclass(frozen=True)
class Paket:
    """Bir transferin birim maliyetleri.

    Toplama ve kargo varsayımdır (veride karşılığı yok, okuyucu kadrandan seçer). Yıpranma oranı
    maliyet değerinin oranıdır. Blok Transfer'in `getiri.MALIYET_PAKETLERI`'nin kopyasıdır (o vaka salt
    okunur; değerlerin eşitliği testle sınanır).
    """
    toplama_birim_tl: float     # adet başı
    kargo_rota_tl: float        # rota başı; rota = tekil (verici, alıcı) mağaza çifti, bütün option'lar üzerinden
    yipranma_orani: float       # maliyet değerinin oranı


MALIYET_PAKETLERI = {
    "dusuk": Paket(5.0, 300.0, 0.03),
    "orta": Paket(10.0, 500.0, 0.05),
    "yuksek": Paket(20.0, 900.0, 0.08),
}
KARAR_PAKETI = "orta"        # `opt` ailesi bu paketle karar verir; ölçüm üç paketle basar

# Tahminde varış varsayımı (gün): transferin alıcıya vardığı gün karar gününden sonra bu kadar gündür.
VARIS_GUN = 3

# Programlar (tasarım §0/19): kanıtlı optimuma varmazsa gapRel ile durur, düğüm sınırı yalnız güvenlik içindir.
GAP_REL = 0.0005
DUGUM_SINIRI = 200_000
