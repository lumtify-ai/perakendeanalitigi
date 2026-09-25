"""v2 kilidi: v2 veri seti dondurulmuştur.

`vakalar/blok-transfer` ve `vakalar/replenishment` v2'yi okur ve
yayımlanmış yazıların sayıları v2'den gelir. v3 işi v2'nin modüllerine,
tohum sırasına ya da sabitlerine dokunursa bu test düşer.

Özet, her tablonun metne çevrilip BÜTÜN kolonlara göre sıralanmış CSV
serileştirmesinin sha256'sıdır: satır sırasından bağımsız, içerikten
bağımlı. Değerler v3 işine başlanmadan önce (2026-09-26) kaydedildi.
"""

import hashlib

import pandas as pd
import pytest

from perakende_veri.uret import tablolari_uret

BEKLENEN = {
    "magaza": (25, "5b515d8b50ba18171c9bdfa322f0008dcaf45dd5756d0b5b1ba514589742ed5f"),
    "urun": (1200, "7ec794fd3b855302f58bf452d9f23bff11dbf70b2133dacccee1d0d212de44c8"),
    "takvim": (365, "5972aceb471c7904628fd54793f264ee90a2fe5d883d09e915c21dfc134c2bc8"),
    "satis": (532121, "4115bac0961b2765ca9c7029de38168143a9a2f834b2e8182eae66a223922699"),
    "stok": (642750, "cdea7281497baa88d90a0952c741a8866bd294a958d918fad54fb33441795130"),
    "sevkiyat": (179131, "023e0f311e349706568422213ff36064de5c49e688981805b5d5842e37f8f332"),
    "kayip_satis": (46384, "b6e1456116fca024aeb68e35302e969464a68054190a5c14dfd4cabd20b2a017"),
}


def _ozet(df: pd.DataFrame) -> str:
    kanonik = df.astype(str)
    kanonik = kanonik.sort_values(list(kanonik.columns)).reset_index(drop=True)
    metin = kanonik.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def tablolar():
    return tablolari_uret()


def test_v2_tablo_kumesi_degismedi(tablolar):
    assert set(tablolar) == set(BEKLENEN)


@pytest.mark.parametrize("ad", list(BEKLENEN))
def test_v2_tablo_bayt_bayt_ayni(tablolar, ad):
    satir, ozet = BEKLENEN[ad]
    assert len(tablolar[ad]) == satir
    assert _ozet(tablolar[ad]) == ozet, f"v2 '{ad}' tablosu değişti"
