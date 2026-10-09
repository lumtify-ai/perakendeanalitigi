"""Politikanın gördüğü sabitlerin veri tipi (`PolitikaBilgisi`).

Tarafsız modül: hiçbir şey içe aktarmaz (pandas dışında). Karar modülleri
tipi buradan alır; nesneyi `rpt.motor.politika_gorunumu` doldurur. Karar
modülleri motoru içe aktarmaz (`tests/test_sizinti.py`).
"""

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class PolitikaBilgisi:
    """Lumoda'nın politikalarının gördüğü sabitler (`dunya`'nın kamuya açık
    yüzünden; `Gorunum` sözleşmesi). Karar modüllerine motor yerine bu verilir.

    optionlar   option başına (`dunya.optionlar` sırası): kimlik ve ürün
                alanları, `indirim_baslangic`; `plan_sezon` = zincir plan
                λ'sı [lansman, indirim) (ilk alımın tabanı, ×0,93),
                `plan_cikis` = [lansman, çıkış); `ilk_alim` (DEVAMLI 0);
                tedarikçi alanları (`mense`, `ulke`, `ilk_siparis_hafta`,
                `rpt_hafta`, `moq_option`, `uzmanlik`)
    plan_hafta  sezonluk option × lansmandan beri hafta h: [lansman + 7h,
                lansman + 7h + 7) ∩ [., çıkış) plan λ'sı, `plan_magaza`,
                `plan_online`, `plan` (toplam)
    plan_tablolari  yayımlanan `mfp_plan`, `range_plan`, `magaza_plan`

    Plan λ'sı Lumoda'nın planıdır (sürprizi, gerçek esnekliği bilmez;
    indirimden sonra planlanan indirim inancını taşır), gerçek talep değildir.
    Okunmayanlar: `lam`, `gizli_*`, `esneklik*`, `sapma_*`, `ilk_siparisler`
    (gerçekleşen teslim, hatalı adet), `gercek()`.
    """

    optionlar: pd.DataFrame
    plan_hafta: pd.DataFrame
    plan_tablolari: dict = field(repr=False)
