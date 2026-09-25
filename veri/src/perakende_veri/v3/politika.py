"""Lumoda'nın bugünkü kararları — simülasyonun varsayılan politikaları.

İki politika vardır ve ikisi de değiştirilebilir (arayüz için
`simulasyon` modülünün belgesine bakın):

    LumodaRPT        Banu'nun elle yürüttüğü RPT kuralı (spec 2.8)
    mevcut_dagitim   haftalık replenishment: plan hedefi + ölü stok kapısı
                     (spec 2.7)

İkisi de yalnız `Gorunum`u okur; gün içinde o ana kadar olmuş olandan
fazlasını göremez. Bilinen kusurları kasıtlıdır (dizinin konusu).
"""

import numpy as np

from . import sabitler
from .tedarik import moq_yuvarla


class LumodaRPT:
    """Her pazartesi, lansmandan 3–6 hafta sonraki Collection option'ları.

    Tetik    zincir STR'si (brüt satış ÷ mağazalara giden) ≥ %55
    Yetişme  lansman + 3 hafta + RPT süresi < indirim başı
             (siparişin verildiği güne değil lansmana bakar; teslim
             sapmasını görmez — kasıtlı kusur)
    Miktar   ilk alımın %50'si, en az MOQ (10'un katına yukarı)
    Sınır    option başına en fazla bir RPT

    STR'nin payı dünkü akşama kadarki satış, paydası bu sabaha kadar
    mağazalara giden (ilk dağıtım + replenishment; geri toplama hariç).
    """

    def __init__(
        self,
        str_esigi: float = sabitler.RPT_STR_ESIGI,
        ilk_hafta: int = sabitler.RPT_ILK_HAFTA,
        son_hafta: int = sabitler.RPT_SON_HAFTA,
        miktar_orani: float = sabitler.RPT_MIKTAR_ORANI,
    ):
        self.str_esigi = str_esigi
        self.ilk_hafta = ilk_hafta
        self.son_hafta = son_hafta
        self.miktar_orani = miktar_orani

    def __call__(self, g) -> dict[int, int]:
        opt = g.dunya.optionlar
        d = g.gun
        h = d - opt["lansman_gun"].to_numpy()
        pencere = (h >= 7 * self.ilk_hafta) & (h <= 7 * self.son_hafta)
        aday = (
            (opt["line"].to_numpy() == "Collection")
            & pencere
            & (g.rpt_sayisi == 0)
            & (g.gonderilen_option > 0)
        )
        if not aday.any():
            return {}
        str_ = np.divide(
            g.satilan_option, g.gonderilen_option,
            out=np.zeros(len(opt)), where=g.gonderilen_option > 0,
        )
        yetisir = (
            opt["lansman_gun"].to_numpy() + 7 * self.ilk_hafta
            + 7 * opt["rpt_hafta"].to_numpy()
        ) < opt["indirim_gun"].to_numpy()
        secilen = np.flatnonzero(aday & (str_ >= self.str_esigi) & yetisir)
        return {
            int(o): moq_yuvarla(self.miktar_orani * g.dunya.ilk_alim[o], int(opt.at[o, "moq_option"]))
            for o in secilen
        }


def mevcut_dagitim(g) -> np.ndarray:
    """Haftalık replenishment isteği, hücre başına adet.

    Hedef    önümüzdeki 28 günün PLAN talebi (sürprizi ve yerel sapmayı
             bilmez; planlı indirimin talep artışını bilir)
    İstek    max(hedef − mağaza stoğu, 0)
    Kapı     hücre yeni değilse (ilk dağıtımdan beri ≥ 28 gün) ve son 28
             günlük satış hızıyla zaten 4 haftalık stoğu varsa mal gitmez —
             hız sıfırsa HİÇ gitmez (0 < 0 yanlış). Stoksuz kalan hücre
             satamaz, satamayınca hızı sıfır görünür, RPT gelse de mal almaz.

    Depo yetmezse motor istekleri SKU içinde orantılı keser; dağıtılamaz
    hücreleri (henüz ilk dağıtımı yapılmamış ya da çıkmış) motor sıfırlar.
    """
    d = g.dunya
    hedef = np.rint(d.ileri_plan(g.gun, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    eksik = np.maximum(hedef - g.magaza_stok, 0)
    ilk_gun = d.optionlar["ilk_dagitim_gun"].to_numpy()[d.hucre_option]
    yeni = (g.gun - ilk_gun) < sabitler.OLU_STOK_PENCERESI_GUN
    haftalik_hiz = g.satis_28 / sabitler.OLU_STOK_PENCERESI_GUN * 7.0
    uygun = yeni | (g.magaza_stok < haftalik_hiz * sabitler.OLU_STOK_HEDEF_HAFTA)
    return np.where(uygun, eksik, 0)
