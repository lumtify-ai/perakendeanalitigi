"""Kolları aynı talep üzerinde koşturur.

    b   = hazirlik(dunya, talep)          # öğrenme: eğri, belirsizlik, aday
    ham = kos(b, "oneri", "c")            # kol × dağıtım kuralı
    tab = olcut_tablosu(b, {...})

HAZIRLIK (bir talep yolu için). Önce yolun "gerçekleşen tarihi" üretilir:
varsayılan politikalarla motor (Banu'nun RPT'leri + bugünkü dağıtım), her
pazartesi aday satırları kaydedilerek. Yol 0'da bu, v3'ün dışa aktarılan
tablolarının kendisidir (test_esdegerlik). Oyun sezonu G için bütün öğrenme
(eğri, belirsizlik, aday modeli) bu tarihin G'nin ilk lansman sabahına
kırpılmış hâlinden, yalnız G'den önce kapanmış sezonlardan yapılır.

BASİTLEŞTİRME. SS25'in öğrenmesi AW24'ün GERÇEKLEŞEN (Banu'lu) tarihini
kullanır, kolun kendi AW24'ünü değil: bir kol AW24'te farklı RPT verseydi
SS25'e giden geçmiş biraz farklı olurdu. Etkisi eğri şekli ve kalibrasyon
üzerinden ikinci derecededir.
"""

import numpy as np
import pandas as pd
from perakende_veri.v3.politika import LumodaRPT
from perakende_veri.v3.simulasyon import simule_et

from . import aday, anlik, dagitim, egri, kaynak, miktar, olcutler, politika

OYUN = kaynak.OYUN_SEZONLARI
KOLLAR = {
    "rpt_yok": politika.RPTYok,
    "mevcut": politika.Mevcut,
    "frr2": lambda b: politika.FRR(b, 2),
    "frr3": lambda b: politika.FRR(b, 3),
    "oneri": politika.Oneri,
    "oneri_lojistik": lambda b: politika.Oneri(b, "lojistik"),
    "kahin": politika.Kahin,
}


def _plan_ekle(opt_t, dunya):
    return kaynak.plan_ekle(opt_t, dunya)


def aday_tablolari(b, t, opt_t, kayit_mevcut, kayit_yok, ham_yok) -> dict:
    """Oyun sezonu başına eğitim (geçmiş sezonlar, gerçekleşen tarih) ve
    sınama (oyun sezonu, rpt_yok kolu) satırları, etiketleriyle."""
    w = b.dunya
    opt = w.optionlar
    sez = opt["sezon_kodu"].to_numpy()
    t_yok = kaynak.tablolar_ham(w, ham_yok)
    sonuc = {}
    for G in b.oyun_sezonlari:
        gecmis = egri.gecmis_sezonlar(t, G)
        kirpik = kaynak.tarihten_once(t, kaynak.sezon_baslangici(t, G))
        hh_g = kaynak.hucre_hafta(kirpik, opt_t, gecmis)
        cx_kendi = {P: egri.egri_ogren(hh_g, opt_t, [P], "duzeltilmis", hedef="cikis") for P in gecmis}
        km = kayit_mevcut[np.isin(sez[kayit_mevcut["option"]], gecmis) & (kayit_mevcut["rpt_sayisi"] == 0)]
        egitim = aday.ozellikler(km, w, b.egriler[G], b.belirsizlik[G], b.p_ind)
        egitim = aday.etiketle(egitim, w, aday.haftalik_duzeltilmis(hh_g, opt_t, cx_kendi), b.p_ind, "duz")
        egitim = aday.etiketle(egitim, w, aday.haftalik_gercek(hh_g), b.p_ind, "gercek")

        hh_s = kaynak.hucre_hafta(t_yok, opt_t, (G,))
        cx_s = {G: egri.egri_ogren(hh_s, opt_t, [G], "duzeltilmis", hedef="cikis")}
        ky = kayit_yok[(sez[kayit_yok["option"]] == G) & (kayit_yok["rpt_sayisi"] == 0)]
        sinama = aday.ozellikler(ky, w, b.egriler[G], b.belirsizlik[G], b.p_ind)
        sinama = aday.etiketle(sinama, w, aday.haftalik_duzeltilmis(hh_s, opt_t, cx_s), b.p_ind, "duz")
        sinama = aday.etiketle(sinama, w, aday.haftalik_gercek(hh_s), b.p_ind, "gercek")
        sonuc[G] = {"egitim": egitim, "sinama": sinama}
    return sonuc


def hazirlik(dunya, talep, oyun_sezonlari=OYUN, modeller: bool = True) -> dict:
    """Bir talep yolunun bütün öğrenmesi. Sözlük: baglam, tablolar, kayıtlar."""
    idx = anlik.Indeks.kur(dunya)
    kaydedici = anlik.Kaydedici(LumodaRPT(), dunya, idx)
    ham_mevcut = simule_et(dunya, talep, rpt_politikasi=kaydedici)
    t = kaynak.tablolar_ham(dunya, ham_mevcut)
    opt_t = _plan_ekle(kaynak.optionlar(t), dunya)

    egriler, belirsizlik = {}, {}
    for G in oyun_sezonlari:
        egriler[G] = egri.oyun_egrileri(t, opt_t, G)
        belirsizlik[G] = miktar.kalibrasyon(t, opt_t, G)
    b = politika.Baglam(dunya=dunya, talep=talep, idx=idx, oyun_sezonlari=tuple(oyun_sezonlari),
                        egriler=egriler, belirsizlik=belirsizlik, p_ind=miktar.indirim_fiyatlari(dunya))

    # rpt_yok kolu, aday sınama satırları için kaydederek
    kayit_yok = anlik.Kaydedici(politika.RPTYok(b), dunya, idx)
    ham_yok = simule_et(dunya, talep, rpt_politikasi=kayit_yok)
    sonuc = {"baglam": b, "t": t, "opt_t": opt_t, "ham": {("mevcut", "mevcut"): ham_mevcut,
                                                          ("rpt_yok", "mevcut"): ham_yok}}
    if modeller:
        at = aday_tablolari(b, t, opt_t, kaydedici.tablo(), kayit_yok.tablo(), ham_yok)
        for G in oyun_sezonlari:
            b.modeller[G] = aday.Modeller(at[G]["egitim"])
        sonuc["aday"] = at
    return sonuc


def egriler_cx(b) -> dict:
    return {G: b.egriler[G][("duzeltilmis", "cikis")] for G in b.oyun_sezonlari}


def kos(b, kol: str, kural: str = "mevcut", kayit: bool = False):
    """Kolu verilen dağıtım kuralıyla koşar. (ham, rpt politikası, dağıtım)."""
    rp = KOLLAR[kol](b)
    dp = dagitim.RPTDagitim(b.dunya, egriler_cx(b), kural, b.oyun_sezonlari, idx=b.idx)
    ham = simule_et(b.dunya, b.talep, rpt_politikasi=rp, dagitim_politikasi=dp)
    return ham, rp, dp


def dagitim_secimi(dunya, talep, t, opt_t, idx=None) -> pd.DataFrame:
    """Dağıtım kuralını oyundan ÖNCE seçmek için: Banu'nun RPT'leri, kural
    yalnız SS24'e uygulanır, SS24 Collection kârı ve kayıp satışı. SS24'ün
    kendi çıkış eğrisi kullanılır (sezon kapandıktan sonra öğrenilebilir;
    SS24'ün son haftası AW24 lansmanından bir hafta sonradır — önemsiz)."""
    hh = kaynak.hucre_hafta(t, opt_t, ("SS24",))
    cx = {"SS24": egri.egri_ogren(hh, opt_t, ["SS24"], "duzeltilmis", hedef="cikis")}
    opt = dunya.optionlar
    ss24 = np.flatnonzero(((opt["sezon_kodu"] == "SS24") & (opt["line"] == "Collection")).to_numpy())
    satir = []
    for kural in dagitim.KURALLAR:
        dp = dagitim.RPTDagitim(dunya, cx, kural, ("SS24",), idx=idx)
        ham = simule_et(dunya, talep, dagitim_politikasi=dp)
        o = olcutler.option_olcutleri(dunya, ham, ss24)
        satir.append({"kural": kural, "kar": o["kar"].sum(), "kayip": o["kayip_tf"].sum() + o["kayip_ind"].sum(),
                      "rpt_magazaya": o["rpt_magazaya"].sum(), "rpt_depoda_kalan": o["rpt_depoda_kalan"].sum(),
                      "satis_tf": o["satis_tf"].sum()})
    return pd.DataFrame(satir)


def oyun_optionlari(dunya, sezon: str) -> np.ndarray:
    opt = dunya.optionlar
    return np.flatnonzero(((opt["sezon_kodu"] == sezon) & (opt["line"] == "Collection")).to_numpy())
