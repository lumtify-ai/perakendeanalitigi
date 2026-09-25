"""Hikâye yazısının (1. yazı) ve Lumoda'nın bugünkü RPT pratiğinin sayıları.

    bitis_haftasi     tutan bir option'ın zincirde "bittiği" ilk pazartesi
    hikaye_adaylari   SS25'in tutan option'ları, bitiş haftasıyla sıralı
    magaza_tablosu    seçilen pazartesi mağaza mağaza durum
    rpt_akibeti       Lumoda'nın verdiği RPT'ler: ne zaman geldi, ne kadarı
                      mağazaya gitti, ne kadarı depoda kaldı

"BİTTİ" TANIMI. Zincirin gözünden: pazartesi sabahı depoda ilk alımın
%2'sinden azı kalmış VE depo + mağaza stoğu ilk alımın %20'sinin altına
inmiş. Mağazada kalan birkaç yüz adet çoğunlukla kırık beden ve yavaş
mağazadadır; müşterinin gözünde ürün bitmiştir.

RPT AKIBETİ (atama kuralı). Depo SKU'yu ayırt eder ama partiyi etmez. RPT
adetlerinin kaderi option düzeyinde FIFO ile atanır: depoda önceden duran mal
önce çıkar, çıkışta depoda kalan adet (en fazla RPT adedi kadar) RPT'den
kalmış sayılır. Mağazaya giden RPT = RPT − depoda kalan. Bu, RPT'yi olduğundan
iyi gösteren (mağazaya gideni büyüten) atamadır.
"""

import numpy as np
import pandas as pd

BITTI_DEPO_PAYI = 0.02
BITTI_ZINCIR_PAYI = 0.20


def bitis_haftasi(panel: pd.DataFrame, opt: pd.DataFrame) -> pd.Series:
    """Option başına "bitti" koşulunun ilk sağlandığı h (pazartesi); yoksa NaN."""
    p = panel.merge(opt[["option_id", "ilk_alim"]], on="option_id")
    p = p[p["h"] >= 1]
    bitti = (p["depo_stok"] <= BITTI_DEPO_PAYI * p["ilk_alim"]) & (
        p["depo_stok"] + p["magaza_stok"] <= BITTI_ZINCIR_PAYI * p["ilk_alim"])
    return p[bitti].groupby("option_id")["h"].min().rename("bitti_h")


def hikaye_adaylari(panel: pd.DataFrame, opt: pd.DataFrame, gercek: pd.DataFrame,
                    sezon: str = "SS25", hit_esigi: float = 1.5) -> pd.DataFrame:
    """Sezonun tutan Collection option'ları; bitiş haftası ve 3. hafta durumu.

    Sıra: önce en erken biten, eşitlikte gerçek/plan oranı büyük olan.
    """
    o = opt[(opt["sezon_kodu"] == sezon) & (opt["line"] == "Collection")].merge(gercek, on="option_id")
    o["oran"] = o["gercek_io"] / o["plan_sezon"]
    o = o[o["oran"] >= hit_esigi]
    o = o.merge(bitis_haftasi(panel, opt).reset_index(), on="option_id", how="left")
    h3 = panel[panel["h"] == 3][["option_id", "depo_stok", "magaza_stok", "stoklu_magaza",
                                 "tasiyan_magaza"]].add_suffix("_h3").rename(
        columns={"option_id_h3": "option_id"})
    x3 = panel[panel["h"] < 3].groupby("option_id")["satis"].sum().rename("satis_h3")
    o = o.merge(h3, on="option_id", how="left").merge(x3.reset_index(), on="option_id", how="left")
    return o.sort_values(["bitti_h", "oran"], ascending=[True, False], na_position="last").reset_index(drop=True)


def magaza_tablosu(t: dict, hh: pd.DataFrame, option_id: str, h: int) -> pd.DataFrame:
    """h. pazartesi sabahı mağaza başına: lansmandan beri satış, stoklu gün
    (bedenlerin ortalaması), stoklu beden / taşınan beden, o anki stok ve
    — yalnız doğruluk için — gerçek talep."""
    c = hh[(hh["option_id"] == option_id) & (hh["h"] < h)]
    m = c.groupby("magaza_id").agg(satis=("satis", "sum"), kayip=("kayip", "sum"))
    hucre = c.groupby(["magaza_id", "urun_id"])["stoklu_gun"].sum()
    m["stoklu_gun_ort"] = hucre.groupby("magaza_id").mean()
    m["acik_gun"] = 7 * h
    m["gercek_talep"] = m["satis"] + m["kayip"]
    lansman = pd.Timestamp(t["urun"].loc[t["urun"]["option_id"] == option_id, "lansman_tarihi"].iloc[0])
    gun = lansman + pd.Timedelta(days=7 * h)
    urunler = t["urun"].loc[t["urun"]["option_id"] == option_id, "urun_id"]
    st = t["stok"][(t["stok"]["tarih"] == gun) & t["stok"]["urun_id"].isin(urunler)]
    m["stok"] = st.groupby("magaza_id")["adet"].sum()
    m["stoklu_beden"] = st.groupby("magaza_id")["adet"].apply(lambda a: int((a > 0).sum()))
    m["beden"] = st.groupby("magaza_id")["adet"].size()
    m = m.join(t["magaza"].set_index("magaza_id")[["ad", "tip"]])
    return m.fillna(0).sort_values("satis", ascending=False).reset_index()


def rpt_siparisleri(t: dict, opt: pd.DataFrame) -> pd.DataFrame:
    """Option başına RPT siparişleri (SKU satırları toplanmış)."""
    r = t["siparis"].query("tip == 'rpt'").groupby(
        ["siparis_id", "option_id", "siparis_tarihi", "planlanan_teslim", "gerceklesen_teslim"],
        dropna=False)["adet"].sum().reset_index()
    r = r.merge(opt[["option_id", "sezon_kodu", "dalga", "mense", "rpt_hafta", "lansman_tarihi",
                     "indirim_baslangic", "cikis_tarihi", "ilk_alim"]], on="option_id")
    r["siparis_h"] = (r["siparis_tarihi"] - r["lansman_tarihi"]).dt.days / 7
    r["gelis_h"] = (r["gerceklesen_teslim"] - r["lansman_tarihi"]).dt.days / 7
    r["indirimden_sonra"] = r["gerceklesen_teslim"] >= r["indirim_baslangic"]
    r["indirime_kalan_hafta"] = (r["indirim_baslangic"] - r["gerceklesen_teslim"]).dt.days / 7
    return r


def rpt_akibeti(t: dict, opt: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Sezonun RPT'li option'ları: gelen, mağazaya giden, çıkışta depoda kalan.

    Depodaki adet: çıkış pazartesisinin fotoğrafı (geri toplamadan önce).
    Atama FIFO (modül belgesi).
    """
    r = rpt_siparisleri(t, opt)
    r = r[r["sezon_kodu"] == sezon]
    o = r.groupby("option_id").agg(rpt=("adet", "sum"), siparis=("siparis_id", "nunique"),
                                   indirimden_sonra=("indirimden_sonra", "any"),
                                   gelis=("gerceklesen_teslim", "min"))
    o = o.join(opt.set_index("option_id")[["cikis_tarihi", "ilk_alim"]])
    urun = t["urun"][["urun_id", "option_id"]]
    depo = t["depo_stok"].merge(urun, on="urun_id").merge(
        o[["cikis_tarihi"]].reset_index(), on="option_id")
    depo = depo[depo["tarih"] == depo["cikis_tarihi"]].groupby("option_id")["adet"].sum()
    o["depo_cikista"] = depo.reindex(o.index).fillna(0).astype(int)
    o["rpt_depoda_kalan"] = np.minimum(o["rpt"], o["depo_cikista"])
    o["rpt_magazaya"] = o["rpt"] - o["rpt_depoda_kalan"]
    geri = t["sevkiyat"].query("tip == 'geri_toplama'").merge(urun, on="urun_id")
    o["geri_toplama"] = (-geri.groupby("option_id")["adet"].sum()).reindex(o.index).fillna(0).astype(int)
    return o.reset_index()
