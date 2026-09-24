"""Alternatif talep yolları.

`talep_yolu(dunya, yol)` v2'nin kendisinin ürettiği talebin (yol 0,
`kaynak.kahin_talep`) yanına, aynı beklenen talep dağılımından ama farklı
bir Poisson çekilişiyle üretilmiş alternatif yollar ekler — karşılaştırmalar
tek bir çekilişe değil bir aralığa dayansın diye. Her yol kendi sabit
tohumuyla tekrar üretilebilir.
"""

import numpy as np
import pandas as pd
from perakende_veri import talep

from . import sabitler
from .dunya import Dunya


def talep_yolu(dunya: Dunya, yol: int) -> np.ndarray:
    """int32[365, H]. Her gün: rng.poisson(beklenen[sezon(g)] × gun_carpani(hafta_günü, tatil)),
    rng = default_rng(YOL_TOHUM_TABANI + yol)."""
    rng = np.random.default_rng(sabitler.YOL_TOHUM_TABANI + yol)

    hafta_gunleri = pd.DatetimeIndex(dunya.tarihler).dayofweek.to_numpy()
    gun_carpanlari = np.array(
        [
            talep.gun_carpani(int(hg), bool(t))
            for hg, t in zip(hafta_gunleri, dunya.tatil)
        ]
    )

    H = len(dunya.hucre_magaza)
    lam = np.empty((365, H), dtype=float)
    for sezon in np.unique(dunya.sezon):
        maske = dunya.sezon == sezon
        lam[maske] = dunya.beklenen[sezon][None, :] * gun_carpanlari[maske, None]

    return rng.poisson(lam).astype(np.int32)
