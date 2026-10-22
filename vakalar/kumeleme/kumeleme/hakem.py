"""Hakem: gizli segmentin tek kapısı (yalnız ölçüm).

`perakende_veri` (v4 üreteci) paketin yalnız bu modülünde içe aktarılır; karar modülleri bu modülü
ne doğrudan ne dolaylı içe aktarır (AST kilidi, `tests/test_sizinti.py`). Gizli segment
(`gizli_magaza.segment`: anadolu_aile, metropol_genc, metropol_premium, sicak_sahil, soguk_iklim,
outlet, online) yayımlanan hiçbir tabloda yoktur; v4 dünyası yayımlanan veriyle aynı tohumla
(`dunya_kur(Olcek.TAM)`, varsayılan tohum) yeniden kurulur ve tablo oradan okunur. Kurulum ~20-35
sn sürer; dünya süreç içinde bir kez kurulur (`functools.cache`). Simülasyon koşulmaz: mağaza
tablosu ve gizli eksenler dünyanın kuruluşunda belirlenir.

Hakem kararlara girmez; `olcutler` ve rapor kümelerin ve atamaların doğruluğunu onunla ölçer.
"""

import functools

import pandas as pd
from perakende_veri.v4.dunya import dunya_kur
from perakende_veri.v4.magaza import Olcek

_TABLO = "gizli_magaza"
_SUTUNLAR = ("magaza_id", "segment")


@functools.cache
def _dunya():
    return dunya_kur(Olcek.TAM)


def dunya():
    """Yayımlanan v4 dünyası (TAM, varsayılan tohum; süreç içi önbellek)."""
    return _dunya()


def gizli_segment(w_ya_da_tablo=None) -> pd.Series:
    """Mağaza → gizli segment (`magaza_id` dizinli, ada göre sıralı, adı `segment`).

    w_ya_da_tablo   None: yayımlanan dünya (`dunya()`); `gizli_magaza` özniteliği olan bir dünya;
                    ya da `magaza_id` ve `segment` sütunlu tablo (testlerdeki fikstür)."""
    if w_ya_da_tablo is None:
        w_ya_da_tablo = dunya()
    t = w_ya_da_tablo if isinstance(w_ya_da_tablo, pd.DataFrame) else getattr(w_ya_da_tablo, _TABLO)
    eksik = [s for s in _SUTUNLAR if s not in t.columns]
    if eksik:
        raise KeyError(f"gizli tablo sütunları eksik: {eksik}")
    ids = t["magaza_id"].astype(str)
    if ids.duplicated().any():
        raise ValueError("gizli tabloda mağaza kimliği tekrarlı")
    s = pd.Series(t["segment"].astype(str).to_numpy(), index=pd.Index(ids.to_numpy(), name="magaza_id"),
                  name="segment")
    return s.sort_index()
