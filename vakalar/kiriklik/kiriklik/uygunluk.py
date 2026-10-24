"""Alıcı uygunluğu ve alıcının asorti ihtiyacı (tasarım §0, K4 ve K18). Karar modülü: saf pandas/numpy.

**Doldurulamaz beden (K18).** Karar anında deposu da indirimden önce teslim planlı açık siparişi de sıfır olan
SKU'dur; replenishment onu kapatamaz, ancak transfer kapatabilir. Depoda ya da yolda malı olan beden
replenishment'ın işidir (Lumoda'nın kuralı her pazartesi sürer), kırık bile olsa transfer adayı sayılmaz.

**Uygun alıcı adayı (K4).** Kırık (mağaza, option) çifti, mağaza `uygun` (açık, kapanış kararsız, tadilatta
değil) ve bütün kırık bedenleri doldurulamazsa adaydır. Elenen çiftin nedeni tek etikettir; öncelik sırası:
`magaza`, sonra `depoda_var`, sonra `acik_siparis`.

**İhtiyaç.** Alıcıda doldurulamaz bedenlerin `asorti − stok` açığı; asortinin altındaki ama sıfır olmayan bedenler
de buna girer, ancak deposu ya da açık siparişi olan beden (kırık olsa da) girmez.

`depo` ve `acik_siparis` SKU düzeyindedir (her mağaza satırında aynı değer tekrarlanır); bu modül SKU değerini
(option, beden) başına bir kez okur, böylece bir mağazanın o beden satırı eksik olsa da SKU'nun deposu bilinir.
"""

import numpy as np
import pandas as pd

from kiriklik import olcu, sabitler
from kiriklik.kaynak import KararGirdisi

_SIRALAR = (1, 2, 3, 4, 5)
NEDENLER = ("uygun", "depoda_var", "acik_siparis", "magaza")


def doldurulamaz(hucre: pd.DataFrame) -> pd.Series:
    """SKU satırı başına: replenishment bu bedeni kapatamaz (`depo == 0 and acik_siparis == 0`; K18).
    Dizin `hucre`'ninkiyle aynıdır."""
    return (hucre.depo == 0) & (hucre.acik_siparis == 0)


def _sku_durumu(hucre: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(option × beden_sira 1–5) `depo` ve `acik_siparis` çerçeveleri (SKU düzeyi; hiç satırı olmayan beden 0)."""
    sku = hucre.groupby(["option_id", "beden_sira"])[["depo", "acik_siparis"]].max()
    depo = sku.depo.unstack(fill_value=0).reindex(columns=list(_SIRALAR), fill_value=0)
    acik = sku.acik_siparis.unstack(fill_value=0).reindex(columns=list(_SIRALAR), fill_value=0)
    return depo, acik


def adaylar(g: KararGirdisi) -> pd.DataFrame:
    """Kırık (mağaza, option) çifti başına [magaza_id, option_id, kirik_beden, eksik_adet, net, brut, uygun,
    neden]; `neden` ∈ {"uygun", "depoda_var", "acik_siparis", "magaza"} (öncelik: magaza, depoda_var,
    acik_siparis). Kırık olmayan ve stoksuz çift çıkmaz."""
    cift = olcu.cift_tablosu(g.hucre)
    cift = cift[cift.kirik].reset_index(drop=True)
    cikti = cift[["magaza_id", "option_id", "kirik_beden", "eksik_adet", "net", "brut"]].copy()
    if cift.empty:
        cikti["uygun"] = pd.Series(dtype=bool)
        cikti["neden"] = pd.Series(dtype=object)
        return cikti
    stok = (g.hucre.pivot_table(index=["magaza_id", "option_id"], columns="beden_sira", values="stok",
                                aggfunc="sum", fill_value=0)
            .reindex(columns=list(_SIRALAR), fill_value=0))
    kirik = stok.reindex(pd.MultiIndex.from_frame(cift[["magaza_id", "option_id"]])).to_numpy() == 0
    depo, acik = _sku_durumu(g.hucre)
    opt = cift.option_id
    depo_var = (kirik & (depo.reindex(opt).to_numpy() > 0)).any(axis=1)
    acik_var = (kirik & (acik.reindex(opt).to_numpy() > 0)).any(axis=1)
    magaza_uygun = cift.magaza_id.isin(g.magaza.loc[g.magaza.uygun.astype(bool), "magaza_id"]).to_numpy()
    neden = np.select([~magaza_uygun, depo_var, acik_var], ["magaza", "depoda_var", "acik_siparis"], "uygun")
    cikti["uygun"] = neden == "uygun"
    cikti["neden"] = neden
    return cikti


def ihtiyac(g: KararGirdisi, magaza_id: str, option_id: str) -> dict[int, int]:
    """Alıcı (mağaza, option) çiftinin beden_sira → `asorti − stok` ihtiyacı (yalnız `doldurulamaz` bedenler,
    yalnız pozitif açık; kırık beden en az 1). Sıra küçükten büyüğe. Çift kırık olmasa ya da aday olmasa da
    anlamlıdır; hücrede çifti olmayan için `{}`."""
    h = g.hucre[g.hucre.option_id == option_id]
    satir = h[h.magaza_id == magaza_id]
    if satir.empty:
        return {}
    stok = satir.groupby("beden_sira").stok.sum().reindex(list(_SIRALAR), fill_value=0)
    depo, acik = _sku_durumu(h)
    dold = (depo.loc[option_id] == 0) & (acik.loc[option_id] == 0)
    eksik = np.asarray(sabitler.ASORTI) - stok.to_numpy()
    return {s: int(a) for s, a, d in zip(_SIRALAR, eksik, dold.to_numpy()) if d and a > 0}
