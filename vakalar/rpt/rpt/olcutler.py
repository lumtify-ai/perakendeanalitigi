"""Kol ölçütleri (spec 3.4), motorun ham çıktısından, option düzeyinde.

Değerleme: gelir = gerçekleşen satış tutarı (iadeler düşülmüş, indirimler
dahil); maliyet = (ilk alım + RPT) × alış fiyatı; çıkışta depoda ya da geri
toplanan stok 0 değerlidir (hurda değeri yok — sezon sonu stoğunun bir
sonraki sezonda outlet'te satılması modellenmez; kâr alt sınırdır).
Kayıp satışın TL karşılığı o günün fiyatıyla (liste × (1 − planlı indirim)).

Bağlam uyarısı (replenishment vakasının dersi): bir kol daha az mal
gönderdiği için de "iyi" görünebilir. Bu yüzden her tabloda mağazaya giden
adet ve tam fiyat döneminin stoklu gün payı da basılır.
"""

import numpy as np
import pandas as pd


def option_olcutleri(dunya, ham: dict, optionlar: np.ndarray) -> pd.DataFrame:
    """Verilen option indisleri için satır başına ölçütler."""
    w = dunya
    opt = w.optionlar
    O = len(opt)
    ho = w.hucre_option
    ind = opt["indirim_gun"].to_numpy()
    cik = opt["cikis_gun"].to_numpy()
    lan = opt["lansman_gun"].to_numpy()
    liste = opt["liste_fiyati"].to_numpy()
    alis = opt["alis_fiyati"].to_numpy()

    s = ham["satis"]
    so = ho[s["hucre"].to_numpy()]
    gun = s["gun"].to_numpy()
    adet = s["adet"].to_numpy()
    poz = adet > 0
    tf = gun < ind[so]
    satis_tf = np.bincount(so[poz & tf], adet[poz & tf], O)
    satis_ind = np.bincount(so[poz & ~tf], adet[poz & ~tf], O)
    iade = -np.bincount(so[~poz], adet[~poz], O)
    gelir = np.bincount(so, s["tutar"].to_numpy(), O)

    k = ham["kayip_satis"]
    ko = ho[k["hucre"].to_numpy()]
    kg = k["gun"].to_numpy()
    ka = k["kayip_adet"].to_numpy()
    ktf = kg < ind[ko]
    kayip_tf = np.bincount(ko[ktf], ka[ktf], O)
    kayip_ind = np.bincount(ko[~ktf], ka[~ktf], O)
    kayip_tl = np.bincount(ko, ka * liste[ko] * (1 - w.indirim_orani[kg, ko]), O)

    sv = ham["sevkiyat"]
    svo = ho[sv["hucre"].to_numpy()]
    giden = sv["tip"].to_numpy() != "geri_toplama"
    magazaya = np.bincount(svo[giden], sv["adet"].to_numpy()[giden], O)
    geri = -np.bincount(svo[~giden], sv["adet"].to_numpy()[~giden], O)

    ds = ham["depo_stok"]
    dso = w.sku_option[ds["sku"].to_numpy()]
    cikista = ds["gun"].to_numpy() == cik[dso]
    depo_cikis = np.bincount(dso[cikista], ds["adet"].to_numpy()[cikista], O)

    st = ham["stok"]
    sto = ho[st["hucre"].to_numpy()]
    sg = st["gun"].to_numpy()
    tfh = (sg > lan[sto]) & (sg <= ind[sto])
    stoklu_pay = np.divide(np.bincount(sto[tfh], st["stoklu_gun"].to_numpy()[tfh], O),
                           7.0 * np.bincount(sto[tfh], minlength=O), out=np.full(O, np.nan),
                           where=np.bincount(sto[tfh], minlength=O) > 0)

    rpt = np.zeros(O)
    rpt_gelen = np.zeros(O)
    rpt_gec = np.zeros(O)
    rpt_gun = np.full(O, -1)
    rpt_gelis = np.full(O, -1)
    son_gun = w.gun_sayisi - 1
    for sp in ham["siparis"]:
        if sp["tip"] != "rpt":
            continue
        o = sp["option"]
        a = float(np.sum(sp["adetler"]))
        rpt[o] += a
        if sp["gerceklesen_gun"] <= son_gun:
            rpt_gelen[o] += a
        if sp["gerceklesen_gun"] >= ind[o]:
            rpt_gec[o] += a
        rpt_gun[o] = sp["siparis_gun"] if rpt_gun[o] < 0 else rpt_gun[o]
        rpt_gelis[o] = sp["gerceklesen_gun"] if rpt_gelis[o] < 0 else rpt_gelis[o]
    ilk = w.ilk_alim.astype(float)
    rpt_depoda = np.minimum(rpt_gelen, depo_cikis)

    d = pd.DataFrame({
        "option": np.arange(O), "option_id": opt["option_id"], "sezon": opt["sezon_kodu"],
        "mense": opt["mense"], "moq": opt["moq_option"],
        "satis_tf": satis_tf, "satis_ind": satis_ind, "iade": iade, "gelir": gelir,
        "kayip_tf": kayip_tf, "kayip_ind": kayip_ind, "kayip_tl": kayip_tl,
        "magazaya": magazaya, "geri_toplama": geri, "depo_cikis": depo_cikis,
        "stoklu_pay_tf": stoklu_pay, "ilk_alim": ilk,
        "rpt": rpt, "rpt_gelen": rpt_gelen, "rpt_indirimden_sonra": rpt_gec,
        "rpt_depoda_kalan": rpt_depoda, "rpt_magazaya": rpt_gelen - rpt_depoda,
        "rpt_gun": rpt_gun, "rpt_gelis_gun": rpt_gelis,
        "maliyet": alis * (ilk + rpt),
    })
    d["kar"] = d["gelir"] - d["maliyet"]
    return d.iloc[np.asarray(optionlar)].reset_index(drop=True)


TOPLANAN = ["satis_tf", "satis_ind", "kayip_tf", "kayip_ind", "kayip_tl", "gelir", "maliyet", "kar",
            "magazaya", "depo_cikis", "geri_toplama", "rpt", "rpt_gelen", "rpt_indirimden_sonra",
            "rpt_magazaya", "rpt_depoda_kalan"]


def sezon_ozeti(kol: pd.DataFrame, taban: pd.DataFrame, kahin: pd.DataFrame | None = None) -> dict:
    """Bir kolun bir sezondaki toplamları ve rpt_yok'a (taban) göre farkları.

    Yanlış alarm: RPT'si olan option'ın tam fiyat satış artışı < MOQ/2.
    Kaçırılan fırsat: kolda RPT yok ama kâhinin kârı o option'da tabana göre
    arttı (sayı ve kâhinin TL kazancı).
    """
    k = kol.set_index("option")
    t = taban.set_index("option").loc[k.index]
    oz = {c: float(k[c].sum()) for c in TOPLANAN}
    oz["rpt_option"] = int((k["rpt"] > 0).sum())
    oz["stoklu_pay_tf"] = float(k["stoklu_pay_tf"].mean())
    oz["kurtarilan_kayip"] = float(t["kayip_tf"].sum() + t["kayip_ind"].sum() - k["kayip_tf"].sum() - k["kayip_ind"].sum())
    oz["kurtarilan_kayip_tf"] = float(t["kayip_tf"].sum() - k["kayip_tf"].sum())
    oz["kurtarilan_kayip_tl"] = float(t["kayip_tl"].sum() - k["kayip_tl"].sum())
    oz["delta_kar"] = float(k["kar"].sum() - t["kar"].sum())
    oz["delta_gelir"] = float(k["gelir"].sum() - t["gelir"].sum())
    rptli = k["rpt"] > 0
    d_tf = k["satis_tf"] - t["satis_tf"]
    oz["rpt_ek_tf"] = float(d_tf[rptli].sum())
    oz["rpt_ek_ind"] = float((k["satis_ind"] - t["satis_ind"])[rptli].sum())
    oz["rpt_str"] = (oz["rpt_ek_tf"] + oz["rpt_ek_ind"]) / oz["rpt"] if oz["rpt"] > 0 else np.nan
    oz["yanlis_alarm"] = int((rptli & (d_tf < k["moq"] / 2)).sum())
    if kahin is not None:
        kh = kahin.set_index("option").loc[k.index]
        kazanc = kh["kar"] - t["kar"]
        kacan = (~rptli) & (kazanc > 0) & (kh["rpt"] > 0)
        oz["kacirilan"] = int(kacan.sum())
        oz["kacirilan_tl"] = float(kazanc[kacan].sum())
    return oz
