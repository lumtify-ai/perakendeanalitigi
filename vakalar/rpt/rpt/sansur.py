"""Sansürlü talep: "daha olsaydı ne kadar satardı?"

Lansmandan h hafta sonraki pazartesi sabahı (karar anı), elde yalnız ilk h
haftanın satışı ve stoklu günleri vardır. Sezon talebini (lansman → indirim
başı; FRR'nin "sezon"u) dört katmanda kestiririz:

    a  çıplak       x_h: bugüne kadarki satış. Raporun gösterdiği sayı;
                    "sezonda bu kadar sattık" demenin karşılığı.
    b  stoklu gün   D_h / h · W: stoklu gün düzeltmeli bugüne kadarki talep,
                    haftalık hıza çevrilip planlı satış haftası (W) kadar
                    uzatılır. Sansürü görür, yaşam eğrisini görmez.
    c  eğri (FRR)   x_h / k_h: çıplak satış, geçmiş sezonların ÇIPLAK satış
                    eğrisiyle ölçeklenir (Fisher–Rajaram–Raman 2001'deki
                    perakendecinin kuralı). Eğriyi görür, sansürü görmez —
                    iki kez: hem bu sezonun satışında hem eğriyi veren geçmiş
                    satışta.
    d  b + c        D_h / k_h: düzeltilmiş talep, düzeltilmiş eğriyle.

Ek iki satır katmanları ayrıştırmak içindir: `a_hiz` (çıplak hız × W) ve
`c_duz_egri` (çıplak satış ÷ düzeltilmiş eğri).

STOKLU GÜN DÜZELTMESİ (hücre = mağaza × SKU). Hücrenin ilk h haftadaki
satışı s, stoklu günü st, açık günü g ise düzeltilmiş talep s · g / st.
Hiç stoklu günü olmayan hücrenin (st = 0) hızı yoktur; aynı SKU'nun
stoklu mağazalardaki birleşik hızından, hücrenin ilk dağıtım payına göre
ölçeklenerek atanır (ilk dağıtım plana göre yapıldı; plan zincirin bildiği
mağaza ağırlığıdır). SKU'nun hiçbir mağazada stoklu günü yoksa option'ın
birleşik hızı kullanılır.

Bilinen yanlılık: stoklu gün "gün açılışında stok > 0" demektir; gün içinde
tükenen hücrenin o günkü kaybı düzeltmeye girmez (aşağı yanlı).

SIZINTI. Kestirimler `kayip` kolonlarını hiç okumaz: `gozlenen()` onları
atar, testler kaybı değiştirip kestirimin değişmediğini sınar. Kestirim h.
hafta başından sonraki satırları da okumaz (kırpılmış veriyle aynı sonuç —
test).
"""

import numpy as np
import pandas as pd

from .egri import Egri

KATMANLAR = ("a", "b", "c", "d")
EK_KATMANLAR = ("a_hiz", "c_duz_egri")
KATMAN_ADI = {
    "a": "a  çıplak satış (rapor)",
    "b": "b  stoklu gün hızı × hafta",
    "c": "c  eğri ölçeği, çıplak (FRR)",
    "d": "d  stoklu gün + eğri",
    "a_hiz": "   çıplak hız × hafta",
    "c_duz_egri": "   çıplak satış ÷ düzeltilmiş eğri",
    "plan": "   buyer planı",
}
KARAR_HAFTALARI = (2, 3, 4, 6)
HIT_ESIGI = 1.5   # gerçek / plan ≥ 1,5: "tutan" ürün (spec 2.12)
GOZLENEN_KOLONLAR = ("magaza_id", "urun_id", "option_id", "h", "satis", "stoklu_gun",
                     "acik_gun", "ilk_dagitim")


def gozlenen(hh: pd.DataFrame) -> pd.DataFrame:
    """Hücre-hafta panelinin zincirin gördüğü kısmı (kayıp satış yok)."""
    return hh[list(GOZLENEN_KOLONLAR)]


def duzeltilmis_talep(hh: pd.DataFrame, h: int) -> pd.DataFrame:
    """İlk h haftanın option başına çıplak satışı (x) ve düzeltilmiş talebi (D).

    Dönen tablo: option_id, x, D, stoklu_pay (hücre-gün olarak stoklu / açık).
    """
    g = gozlenen(hh)
    g = g[g["h"] < h]
    c = g.groupby(["option_id", "urun_id", "magaza_id"]).agg(
        s=("satis", "sum"), st=("stoklu_gun", "sum"), ac=("acik_gun", "sum"),
        w=("ilk_dagitim", "first"),
    ).reset_index()
    c["w"] = c["w"] + 1.0   # sıfır ilk dağıtımlı hücre de küçük bir ağırlık alır
    stoklu = c["st"] > 0
    c["hiz"] = np.where(stoklu, c["s"] / c["st"].where(stoklu, 1), np.nan)

    # Stoksuz hücrelere atama: SKU'nun stoklu hücrelerinin birleşik hızı
    # (Σs / Σst), hücrenin ilk dağıtım ağırlığının o hücrelerin ortalamasına
    # oranıyla ölçekli; SKU'da hiç stoklu hücre yoksa option düzeyinde aynısı.
    def _birlesik(anahtar):
        cs = c[stoklu].groupby(anahtar).agg(s=("s", "sum"), st=("st", "sum"), w=("w", "mean"))
        return (cs["s"] / cs["st"]).rename("r"), cs["w"].rename("wbar")

    r_sku, w_sku = _birlesik("urun_id")
    r_opt, w_opt = _birlesik("option_id")
    atanan_sku = c["urun_id"].map(r_sku) * c["w"] / c["urun_id"].map(w_sku)
    atanan_opt = c["option_id"].map(r_opt) * c["w"] / c["option_id"].map(w_opt)
    c["hiz"] = c["hiz"].fillna(atanan_sku).fillna(atanan_opt).fillna(0.0)
    c["D"] = c["hiz"] * c["ac"]
    o = c.groupby("option_id").agg(x=("s", "sum"), D=("D", "sum"), st=("st", "sum"), ac=("ac", "sum"))
    o["stoklu_pay"] = o["st"] / o["ac"].where(o["ac"] > 0, 1)
    return o[["x", "D", "stoklu_pay"]].reset_index()


def kestir(hh: pd.DataFrame, opt: pd.DataFrame, h: int, egri_ham: Egri, egri_duz: Egri) -> pd.DataFrame:
    """Karar haftası h için option başına sezon talebi kestirimleri."""
    k = duzeltilmis_talep(hh, h).merge(
        opt[["option_id", "dalga", "ust_kategori", "satis_hafta", "plan_sezon"]], on="option_id"
    )

    def _k(e: Egri, satir):
        anahtar = tuple(satir[g] for g in e.grup)
        return e.k(anahtar, h)

    k["k_ham"] = [_k(egri_ham, r) for _, r in k.iterrows()]
    k["k_duz"] = [_k(egri_duz, r) for _, r in k.iterrows()]
    W = k["satis_hafta"]
    k["a"] = k["x"].astype(float)
    k["b"] = k["D"] / h * W
    k["c"] = k["x"] / k["k_ham"]
    k["d"] = k["D"] / k["k_duz"]
    k["a_hiz"] = k["x"] / h * W
    k["c_duz_egri"] = k["x"] / k["k_duz"]
    k["plan"] = k["plan_sezon"]
    k["h"] = h
    return k


def gercek_talep(hh: pd.DataFrame) -> pd.DataFrame:
    """Doğruluk ölçüsü: option başına gerçek talep (satış + kayıp).

    gercek_io     lansman → indirim başı (kestirimlerin hedefi)
    gercek_cikis  lansman → çıkış
    satis_io      aynı pencerede gerçekleşen satış
    """
    g = hh.groupby("option_id").agg(
        satis_io=("satis_io", "sum"), kayip_io=("kayip_io", "sum"),
        satis=("satis", "sum"), kayip=("kayip", "sum"),
    )
    g["gercek_io"] = g["satis_io"] + g["kayip_io"]
    g["gercek_cikis"] = g["satis"] + g["kayip"]
    return g[["gercek_io", "gercek_cikis", "satis_io"]].reset_index()


def hata_olcutleri(tahmin: pd.Series, gercek: pd.Series) -> dict:
    """MAPE (option ortalaması), ağırlıklı APE (Σ|e| / Σgerçek), medyan APE,
    yanlılık (Σe / Σgerçek). Yüzde değil oran döner."""
    e = tahmin - gercek
    ape = (e.abs() / gercek).replace([np.inf, -np.inf], np.nan)
    return {
        "n": int(len(gercek)),
        "mape": float(ape.mean()),
        "wape": float(e.abs().sum() / gercek.sum()),
        "medyan_ape": float(ape.median()),
        "yanlilik": float(e.sum() / gercek.sum()),
    }


def hata_tablosu(kestirimler: pd.DataFrame, gercek: pd.DataFrame, hit_esigi: float = HIT_ESIGI,
                 katmanlar=KATMANLAR + EK_KATMANLAR + ("plan",)) -> pd.DataFrame:
    """Uzun tablo: h × katman × kesit (tümü / tutan / tutmayan) × ölçüt."""
    k = kestirimler.merge(gercek, on="option_id")
    k = k[k["gercek_io"] > 0]
    k["tutan"] = k["gercek_io"] / k["plan_sezon"] >= hit_esigi
    satirlar = []
    for h, kh in k.groupby("h"):
        for kesit, maske in (("tümü", slice(None)), ("tutan", kh["tutan"]), ("tutmayan", ~kh["tutan"])):
            kk = kh.loc[maske]
            if kk.empty:
                continue
            for kat in katmanlar:
                satirlar.append({"h": h, "katman": kat, "kesit": kesit,
                                 **hata_olcutleri(kk[kat], kk["gercek_io"])})
    return pd.DataFrame(satirlar)
