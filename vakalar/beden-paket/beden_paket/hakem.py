"""Hakem: gizli beden kaymasının ve gerçek beden payının tek kapısı (yalnız ölçüm).

`perakende_veri` (v4 üreteci) paketin yalnız bu modülünde içe aktarılır; karar modülleri bu modülü
ne doğrudan ne dolaylı içe aktarır (AST kilidi, `tests/test_sizinti.py`). Mağazanın gizli
`beden_kayma`'sı (`gizli_magaza` tablosu) yayımlanan hiçbir tabloda yoktur. Üreteç kaymayı
`integers(-1, 2, endpoint=True)` ile çeker (−1, 0, +1, +2; `magaza.py:442`), talep modeli ise
[−1, +1]'e kırpar (`talep.py:545`): +2 ile +1 talepte aynıdır. `kayma` bu yüzden varsayılan olarak
**etkin** (kırpılmış) kaymayı verir (−1 küçüğe, 0 zincir, +1 büyüğe); ham çekiliş `kirp=False`.
Dünya Kümeleme hakeminin süreç içi önbelleğinden alınır (`kumeleme.hakem.dunya`:
`dunya_kur(Olcek.TAM)`, varsayılan tohum, ~20-35 sn, bir kez); simülasyon koşulmaz.

**Gerçek beden payı** (`gercek_pay`). Talep modelinde fiziksel mağazanın beş bedenli SKU'sunun
statik tabanı `talep._beden_tablosu()[kayma + 1, beden_sira − 1]` ile çarpılır (ortalama 1); öteki
çarpanlar bir option'ın bütün bedenlerinde aynıdır. Mağazanın gerçek beden payı bu satırın beşte
biridir (satır toplamı 5). Beden ikamesi (karşılanmayan talebin %5'i komşu bedene) satışı bu
paydan biraz ayırır; hakem talebin payını verir.

Hakem kararlara girmez; `olcutler_egri` ve rapor eğrilerin doğruluğunu onunla ölçer.
"""

import numpy as np
import pandas as pd
from kumeleme import hakem as kumeleme_hakem
from perakende_veri.v4 import talep

_TABLO = "gizli_magaza"
_SUTUNLAR = ("magaza_id", "beden_kayma")
SUTUNLAR = ["b1", "b2", "b3", "b4", "b5"]


def dunya():
    """Yayımlanan v4 dünyası (TAM, varsayılan tohum; süreç içi önbellek)."""
    return kumeleme_hakem.dunya()


def kayma(w_ya_da_tablo=None, *, kirp: bool = True) -> pd.Series:
    """Mağaza → gizli beden kayması (int; `magaza_id` dizinli, ada göre sıralı, adı `beden_kayma`);
    `kirp` ise talepteki etkin değer ([−1, +1]'e kırpılmış; modül notu).

    w_ya_da_tablo   None: yayımlanan dünya; `gizli_magaza` özniteliği olan bir dünya; ya da
                    `magaza_id` ve `beden_kayma` sütunlu tablo (testlerdeki fikstür)."""
    if w_ya_da_tablo is None:
        w_ya_da_tablo = dunya()
    t = w_ya_da_tablo if isinstance(w_ya_da_tablo, pd.DataFrame) else getattr(w_ya_da_tablo, _TABLO)
    eksik = [s for s in _SUTUNLAR if s not in t.columns]
    if eksik:
        raise KeyError(f"gizli tablo sütunları eksik: {eksik}")
    ids = t["magaza_id"].astype(str)
    if ids.duplicated().any():
        raise ValueError("gizli tabloda mağaza kimliği tekrarlı")
    v = t["beden_kayma"].to_numpy(dtype="int64")
    s = pd.Series(np.clip(v, -1, 1) if kirp else v, index=pd.Index(ids.to_numpy(), name="magaza_id"),
                  name="beden_kayma")
    return s.sort_index()


def gercek_pay(w_ya_da_tablo=None) -> pd.DataFrame:
    """Mağaza × beden (b1..b5) gerçek talep payı (modül notu); `kayma` sırasıyla, satırlar bire."""
    k = kayma(w_ya_da_tablo)
    tablo = talep._beden_tablosu()
    P = tablo[k.to_numpy() + 1] / tablo.shape[1]
    return pd.DataFrame(P, index=k.index, columns=SUTUNLAR)
