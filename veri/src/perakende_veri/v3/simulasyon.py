"""v3 stok-satış motoru.

Talep stoktan bağımsızdır (dünya + talep akışı); motor yalnızca o talebi
stok kısıtı altında satışa çevirir. Gerçek talep = satış + kayıp satış
özdeşliği bu yüzden kurulum gereği tutar ve aynı talep farklı RPT ve
dağıtım politikalarıyla yeniden oynatılabilir:

    dunya = dunya_kur()
    talep = talep_matrisi(dunya)
    sonuc = simule_et(dunya, talep)                        # v3'ün kendisi
    kol   = simule_et(dunya, talep, rpt_politikasi=...,    # karşı-olgusal
                      dagitim_politikasi=...)

Varsayılan politikalarla ve `talep_matrisi(dunya)` ile koşulan motor,
dışa aktarılan v3 tablolarını birebir üretir (test_v3_esdegerlik.py).

GÜNLÜK İŞLEM SIRASI
===================

d = 0 (2023-07-03, pazartesi) döngüden önce: devamlı (Basic/NOS)
hücrelere 28 günlük plan hedefi kadar stok (`sevkiyat` tip ilk_dagitim,
ısınmada kalır), depoya option başına (RPT süresi + 2 + emniyet) haftalık
zincir planı konur. Sezonluk ürünlerin stoğu yoktur; ilk siparişleri
dünyada hazırdır.

Her gün d için, bu sırayla:

 1. FOTOĞRAF (yalnız pazartesi). Mağaza stoğu, açık hücreler için
    (lansman_gun ≤ d ≤ cikis_gun; devamlılar hep açık) ve `stoklu_gun`
    = d−7 … d−1 günlerinde 9. adımdaki bayrağın toplamı. Depo stoğu,
    görünür SKU'lar için (devamlılar hep; sezonluklar ilk teslimattan
    cikis_gun + 7'ye kadar). Fotoğraf günün hiçbir hareketinden önce
    çekilir: dünkü kapanış = bugünkü açılış.
 2. TESLİM. gerceklesen_gun == d olan bütün siparişler (ilk, rpt, surekli)
    depoya girer.
 3. İLK DAĞITIM. ilk_dagitim_gun == d olan option'lar (= max(lansman,
    ilk siparişin gerçekleşen teslimi); gecikirse geliş günü, pazartesi
    olmayabilir): `ilk_dagitim_hucre` adetleri depodan mağazalara.
 4. ÇIKIŞ. cikis_gun == d olan option'ların mağaza stoğu depoya döner
    (`sevkiyat` tip geri_toplama, negatif adet). Hücre bugünden itibaren
    kapalıdır: talebi 0, dağıtılamaz, iadesi yazılmaz.
 5. RPT KARARI (pazartesi). `rpt_politikasi(gorunum)` → {option: adet}.
    Sipariş RPT süresi sonra planlanır, önceden çekilmiş sapmayla gelir.
 6. SÜREKLİ TEDARİK (d % 14 == 0). Devamlı option'lar, SKU düzeyinde
    (s, S): plan × düzeltme (son 56 günün zincir brüt satışı ÷ aynı dönemin
    planı, [0,7; 1,6] ile kırpılmış) üzerinden; herhangi bir bedenin
    envanter pozisyonu (depo + açık sipariş) (L + emniyet) haftalık planın
    altındaysa her beden (L + 2 + emniyet) haftaya tamamlanır, toplam en
    az MOQ (L = tedarikçinin RPT süresi; emniyet Basic 2, NOS 3 hafta).
    Sipariş option başına k. sürekli siparişin önceden çekilmiş sapmasıyla
    gelir. Politika değildir; vakada da sabittir.
 7. DAĞITIM (pazartesi). `dagitim_politikasi(gorunum)` → hücre başına
    istek. Motor dağıtılamaz hücreleri sıfırlar (ilk_dagitim_gun ≥ d ya
    da çıkmış), depo yetmeyen SKU'larda istekleri orantılı keser (taban +
    en büyük kesir, eşitlikte küçük hücre indisi) ve sevk eder
    (`sevkiyat` tip replenishment). Aynı gün ilk dağıtımı yapılan option
    ilk replenishment'ını bir sonraki pazartesi alır.
 8. İADE. n = d−7 günündeki brüt satış (hücre bugün açıksa, değilse 0);
    iade = Binomial(n, 0,06) — operasyon akışı, BÜTÜN hücreler için tek
    çağrı. Mağaza stoğuna döner; `satis`e negatif satır.
 9. STOKLU BAYRAĞI. stoklu[d, c] = mağaza_stok[c] > 0 (satış öncesi,
    teslim/dağıtım/iade sonrası: müşterinin rafta bulduğu).
10. TALEP → SATIŞ. satış = min(talep[d], stok); kayıp = talep − satış.
    Satan hücreler için operasyon akışından tek `random(n)` çağrısı:
    < 0,08 ise %30 işlem indirimi (yalnız planlı indirim yoksa uygulanır).

Rastgele akış tüketimi: talep akışı yalnız `talep_matrisi`'nde (gün
başına C Poisson, hücre sırasıyla). Operasyon akışı gün başına en fazla
iki çağrı: 8. adımda binomial (C boyutlu), 10. adımda random (satan hücre
sayısı kadar). Teslim sapmaları dünyada önceden çekilmiştir.

POLİTİKA ARAYÜZÜ
================

    rpt_politikasi(g: Gorunum) -> dict[int, int | np.ndarray]
        option indisi → adet (option toplamı; motor zincir beden eğrisine
        böler) ya da option'ın SKU'ları sırasıyla adet dizisi. Boş sözlük =
        sipariş yok. Aynı option'a birden çok RPT verilebilir (her biri
        kendi önceden çekilmiş sapmasını kullanır, en fazla 4 farklı).
        None verilirse hiç RPT yok.

    dagitim_politikasi(g: Gorunum) -> np.ndarray[C]  (int ≥ 0)
        Hücre başına depodan istenen adet. Depoyu aşan istek motorca kesilir.

`Gorunum` salt okunur dizilerle karar anını verir: gün, tarih, dünya,
mağaza stoğu (o anki), depo (o anki), açık siparişler, geçmiş satış ve
stoklu matrisleri (yalnız d'den önceki satırlar), son 28 günlük satış,
option başına mağazalara giden kümülatif adet (o ana kadar) ve brüt satış
(dünkü akşama kadar), option başına verilmiş RPT sayısı. Bugünün talebi,
satışı ve gelecekteki teslimler görünmez.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import sabitler
from .dunya import Dunya, akislar, talep_matrisi
from .politika import LumodaRPT, mevcut_dagitim
from .tedarik import en_buyuk_kalan, moq_yuvarla


def _topla(indis: np.ndarray, deger: np.ndarray, n: int) -> np.ndarray:
    """Tam sayı bincount (np.bincount ağırlıkla float döndürür)."""
    return np.bincount(indis, deger, minlength=n).astype(np.int64)


def _salt_okunur(a: np.ndarray) -> np.ndarray:
    v = a.view()
    v.flags.writeable = False
    return v


@dataclass(frozen=True)
class Gorunum:
    dunya: Dunya
    gun: int
    tarih: pd.Timestamp
    magaza_stok: np.ndarray        # [C]
    depo: np.ndarray               # [S]
    satis_gecmisi: np.ndarray      # [gun, C] brüt satış
    stoklu_gecmisi: np.ndarray     # [gun, C] bool
    satis_28: np.ndarray           # [C] [gun−28, gun) brüt satış
    gonderilen_option: np.ndarray  # [O]
    satilan_option: np.ndarray     # [O]
    rpt_sayisi: np.ndarray         # [O]
    acik_siparisler: tuple         # sipariş sözlüklerinin kopyaları


def orantili_kes(istek: np.ndarray, hucre_sku: np.ndarray, depo: np.ndarray) -> np.ndarray:
    """Depo yetmeyen SKU'larda istekleri orantılı keser.

    Her hücre floor(istek · depo/toplam) alır; SKU'da artan adetler
    kesri en büyük hücrelere birer birer verilir (eşitlikte küçük indis).
    Deterministiktir; gönderilen toplam hiçbir SKU'da depoyu aşmaz.
    """
    S = len(depo)
    toplam = _topla(hucre_sku, istek, S)
    kisitli = toplam > depo
    if not kisitli.any():
        return istek.astype(np.int64)
    oran = np.where(kisitli, depo / np.maximum(toplam, 1), 1.0)
    hedef = istek * oran[hucre_sku]
    taban = np.where(kisitli[hucre_sku], np.floor(hedef + 1e-9), istek).astype(np.int64)
    taban = np.minimum(taban, istek)
    kalan = depo - _topla(hucre_sku, taban, S).astype(np.int64)
    kesir = np.where(kisitli[hucre_sku] & (istek > taban), hedef - taban, -1.0)
    sira = np.lexsort((np.arange(len(istek)), -kesir, hucre_sku))
    sku_sirali = hucre_sku[sira]
    grup_basi = np.searchsorted(sku_sirali, sku_sirali, side="left")
    rutbe = np.arange(len(sira)) - grup_basi
    ver = (kesir[sira] > 0) & (rutbe < np.maximum(kalan, 0)[sku_sirali])
    sonuc = taban.copy()
    sonuc[sira[ver]] += 1
    return sonuc


def simule_et(
    dunya: Dunya,
    talep: np.ndarray | None = None,
    rpt_politikasi=None,
    dagitim_politikasi=None,
    rng_operasyon: np.random.Generator | None = None,
    varsayilan_rpt: bool = True,
    gun_sayisi: int | None = None,
) -> dict:
    """Motoru koşar; ham sonuçları (gün ve hücre/SKU indisli) döndürür.

    talep               [D, C] günlük talep; None ise `talep_matrisi(dunya)`
    rpt_politikasi      None ve varsayilan_rpt ise LumodaRPT(); hiç RPT
                        istemeyen çağıran varsayilan_rpt=False verir
    dagitim_politikasi  None ise mevcut_dagitim
    gun_sayisi          yalnız ilk n günü koş (test ve hızlı deneme için);
                        ilk n gün, tam koşunun ilk n günüyle birebir aynıdır
    """
    if talep is None:
        talep = talep_matrisi(dunya)
    if rpt_politikasi is None and varsayilan_rpt:
        rpt_politikasi = LumodaRPT()
    if dagitim_politikasi is None:
        dagitim_politikasi = mevcut_dagitim
    rng = rng_operasyon if rng_operasyon is not None else akislar()["operasyon"]

    w = dunya
    D = w.gun_sayisi if gun_sayisi is None else gun_sayisi
    C, S, O = len(w.cesit), len(w.urunler), len(w.optionlar)
    if len(talep) < D:
        raise ValueError(f"talep matrisi {len(talep)} gün, {D} gerekli")
    opt = w.optionlar
    ho, hs = w.hucre_option, w.hucre_sku
    lansman = opt["lansman_gun"].to_numpy()
    cikis = opt["cikis_gun"].to_numpy()
    ilk_gun = opt["ilk_dagitim_gun"].to_numpy()
    sezonluk = opt["sezonluk"].to_numpy()
    moq = opt["moq_option"].to_numpy()
    rpt_hafta = opt["rpt_hafta"].to_numpy()
    liste = w.urunler["liste_fiyati"].to_numpy()[hs]
    tarihler = pd.DatetimeIndex(w.takvim["tarih"])
    option_skulari = [np.flatnonzero(w.sku_option == o) for o in range(O)]
    hucre_lansman, hucre_cikis, hucre_ilk = lansman[ho], cikis[ho], ilk_gun[ho]

    # --- Durum --------------------------------------------------------
    stok = np.zeros(C, dtype=np.int64)
    depo = np.zeros(S, dtype=np.int64)
    satis_gecmisi = np.zeros((D, C), dtype=np.int16)
    stoklu_gecmisi = np.zeros((D, C), dtype=bool)
    satis_28 = np.zeros(C, dtype=np.int64)
    gonderilen_option = np.zeros(O, dtype=np.int64)
    satilan_option = np.zeros(O, dtype=np.int64)
    satilan_option_kum = np.zeros((D + 1, O), dtype=np.int64)   # [d] = d'den önceki toplam
    rpt_sayisi = np.zeros(O, dtype=np.int64)
    surekli_sayisi = np.zeros(O, dtype=np.int64)
    acik_sku = np.zeros(S, dtype=np.int64)

    siparisler: list[dict] = []
    teslim_takvimi: dict[int, list[dict]] = {}

    def _siparis_ekle(s: dict) -> None:
        siparisler.append(s)
        teslim_takvimi.setdefault(s["gerceklesen_gun"], []).append(s)
        acik_sku[s["skular"]] += s["adetler"]

    for s in w.ilk_siparisler:
        _siparis_ekle(dict(s))

    satis_p, kayip_p, sevk_p, stok_p, depo_p = [], [], [], [], []

    def _sevk(d, hucreler, adet, tip):
        if hucreler.size:
            sevk_p.append((d, hucreler, adet, tip))

    # --- Isınma başlangıcı: devamlılar --------------------------------
    devamli_hucre = np.flatnonzero(~sezonluk[ho])
    baslangic = np.rint(w.ileri_plan(0, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    stok[devamli_hucre] = baslangic[devamli_hucre]
    _sevk(0, devamli_hucre, baslangic[devamli_hucre], "ilk_dagitim")
    gonderilen_option += _topla(ho[devamli_hucre], baslangic[devamli_hucre], O)
    for o in np.flatnonzero(~sezonluk):
        hafta = int(rpt_hafta[o]) + sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA + sabitler.SUREKLI_EMNIYET_HAFTA[opt.at[o, "line"]]
        miktar = int(round(w.ileri_plan_option(0, 7 * hafta)[o]))
        sk = option_skulari[o]
        depo[sk] += en_buyuk_kalan(miktar, w.sku_beden_payi[sk])

    # Depo fotoğrafında görünür SKU: devamlı hep; sezonluk ilk teslimden
    # çıkış + 7'ye kadar
    ilk_teslim = np.full(O, 10**6)
    for s in w.ilk_siparisler:
        ilk_teslim[s["option"]] = s["gerceklesen_gun"]
    depo_gorunur_bas = np.where(sezonluk, ilk_teslim, -1)[w.sku_option]
    depo_gorunur_son = np.where(sezonluk, cikis + 7, 10**6)[w.sku_option]

    dagitim_gunleri: dict[int, list[int]] = {}
    for o in np.flatnonzero(sezonluk):
        dagitim_gunleri.setdefault(int(ilk_gun[o]), []).append(o)
    cikis_gunleri: dict[int, list[int]] = {}
    for o in np.flatnonzero(sezonluk):
        cikis_gunleri.setdefault(int(cikis[o]), []).append(o)

    hucre_maskesi_option = lambda os_: np.isin(ho, os_)  # noqa: E731

    def _gorunum(d):
        return Gorunum(
            dunya=w, gun=d, tarih=tarihler[d],
            magaza_stok=_salt_okunur(stok), depo=_salt_okunur(depo),
            satis_gecmisi=_salt_okunur(satis_gecmisi[:d]),
            stoklu_gecmisi=_salt_okunur(stoklu_gecmisi[:d]),
            satis_28=_salt_okunur(satis_28),
            gonderilen_option=_salt_okunur(gonderilen_option),
            satilan_option=_salt_okunur(satilan_option),
            rpt_sayisi=_salt_okunur(rpt_sayisi),
            acik_siparisler=tuple(
                dict(s) for s in siparisler if s["gerceklesen_gun"] > d
            ),
        )

    for d in range(D):
        pazartesi = tarihler[d].dayofweek == 0

        # 1) Fotoğraf
        if pazartesi:
            acik = np.flatnonzero((hucre_lansman <= d) & (d <= hucre_cikis))
            stoklu_gun = stoklu_gecmisi[max(d - 7, 0):d, acik].sum(axis=0)
            stok_p.append((d, acik, stok[acik].copy(), stoklu_gun.astype(np.int64)))
            gorunur = np.flatnonzero((depo_gorunur_bas <= d) & (d <= depo_gorunur_son))
            depo_p.append((d, gorunur, depo[gorunur].copy()))

        # 2) Teslim
        for s in teslim_takvimi.get(d, []):
            depo[s["skular"]] += s["adetler"]
            acik_sku[s["skular"]] -= s["adetler"]

        # 3) İlk dağıtım
        if d in dagitim_gunleri:
            hucreler = np.flatnonzero(hucre_maskesi_option(dagitim_gunleri[d]))
            adet = w.ilk_dagitim_hucre[hucreler]
            depo -= _topla(hs[hucreler], adet, S)
            stok[hucreler] += adet
            gonderilen_option += _topla(ho[hucreler], adet, O)
            dolu = adet > 0
            _sevk(d, hucreler[dolu], adet[dolu], "ilk_dagitim")

        # 4) Çıkış — geri toplama
        if d in cikis_gunleri:
            hucreler = np.flatnonzero(hucre_maskesi_option(cikis_gunleri[d]))
            hucreler = hucreler[stok[hucreler] > 0]
            adet = stok[hucreler].copy()
            depo += _topla(hs[hucreler], adet, S)
            stok[hucreler] = 0
            _sevk(d, hucreler, -adet, "geri_toplama")

        # 5) RPT kararı
        if pazartesi and rpt_politikasi is not None:
            for o, miktar in sorted(rpt_politikasi(_gorunum(d)).items()):
                sk = option_skulari[o]
                adetler = (
                    en_buyuk_kalan(int(miktar), w.sku_beden_payi[sk])
                    if np.ndim(miktar) == 0 else np.asarray(miktar, dtype=np.int64)
                )
                if adetler.sum() <= 0:
                    continue
                k = min(int(rpt_sayisi[o]), w.sapma_rpt.shape[1] - 1)
                planlanan = d + 7 * int(rpt_hafta[o])
                _siparis_ekle({
                    "tip": "rpt", "option": int(o), "siparis_gun": d,
                    "planlanan_gun": planlanan,
                    "gerceklesen_gun": planlanan + int(w.sapma_rpt[o, k]),
                    "skular": sk, "adetler": adetler,
                })
                rpt_sayisi[o] += 1

        # 6) Sürekli tedarik — SKU düzeyinde (s, S): bir bedenin envanter
        # pozisyonu (depo + açık sipariş) tedarik süresi + emniyet kadar
        # planın altına düşerse option sipariş verir; miktar her bedeni
        # tedarik süresi + gözden geçirme + emniyet planına tamamlar, en az
        # MOQ. Option düzeyinde bakmak, satmayan bedenin yığını satan bedenin
        # bitişini gizlediği için depoyu sık sık boşaltıyordu.
        if pazartesi and d % (7 * sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA) == 0:
            # Plan düzeltmesi: son 8 haftanın zincir satışı ÷ aynı dönemin planı.
            # Sürekli ürünü planlayan kişi planı satışla günceller; sürprizi
            # böyle yakalar (sansürlü satışla — stoksuz kalınca düzeltme de
            # düşük kalır).
            p = sabitler.SUREKLI_DUZELTME_GUN
            if d >= p:
                gecmis_plan = w.ileri_plan_option(d - p, p)
                gecmis_satis = satilan_option_kum[d] - satilan_option_kum[d - p]
                duzeltme = np.clip(
                    np.divide(gecmis_satis, gecmis_plan, out=np.ones(O), where=gecmis_plan > 0),
                    *sabitler.SUREKLI_DUZELTME_SINIR,
                )
            else:
                duzeltme = np.ones(O)
            for o in np.flatnonzero(~sezonluk):
                emniyet = sabitler.SUREKLI_EMNIYET_HAFTA[opt.at[o, "line"]]
                L = int(rpt_hafta[o])
                sk = option_skulari[o]
                pay = w.sku_beden_payi[sk] * duzeltme[o]
                s_nokta = w.ileri_plan_option(d, 7 * (L + emniyet))[o] * pay
                S_nokta = w.ileri_plan_option(
                    d, 7 * (L + sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA + emniyet))[o] * pay
                pozisyon = depo[sk] + acik_sku[sk]
                if not (pozisyon < s_nokta).any():
                    continue
                eksik = np.maximum(S_nokta - pozisyon, 0.0)
                taban = en_buyuk_kalan(int(np.ceil(eksik.sum())), eksik)
                miktar = moq_yuvarla(taban.sum(), int(moq[o]))
                adetler = taban + en_buyuk_kalan(miktar - int(taban.sum()), w.sku_beden_payi[sk])
                k = int(surekli_sayisi[o]) % w.sapma_surekli.shape[1]
                planlanan = d + 7 * L
                _siparis_ekle({
                    "tip": "surekli", "option": int(o), "siparis_gun": d,
                    "planlanan_gun": planlanan,
                    "gerceklesen_gun": planlanan + int(w.sapma_surekli[o, k]),
                    "skular": sk, "adetler": adetler,
                })
                surekli_sayisi[o] += 1

        # 7) Dağıtım
        if pazartesi:
            istek = np.asarray(dagitim_politikasi(_gorunum(d)), dtype=np.int64)
            dagitilabilir = (hucre_ilk < d) & (d < hucre_cikis)
            istek = np.where(dagitilabilir, np.maximum(istek, 0), 0)
            gonder = orantili_kes(istek, hs, depo)
            hucreler = np.flatnonzero(gonder > 0)
            if hucreler.size:
                adet = gonder[hucreler]
                depo -= _topla(hs[hucreler], adet, S)
                stok[hucreler] += adet
                gonderilen_option += _topla(ho[hucreler], adet, O)
                _sevk(d, hucreler, adet, "replenishment")

        # 8) İade
        acik_bugun = (hucre_lansman <= d) & (d < hucre_cikis)
        if d >= sabitler.IADE_GECIKME_GUN:
            n = np.where(acik_bugun, satis_gecmisi[d - sabitler.IADE_GECIKME_GUN], 0)
            iade = rng.binomial(n, sabitler.IADE_ORANI)
            donen = np.flatnonzero(iade > 0)
            if donen.size:
                stok[donen] += iade[donen]
                fiyat = liste[donen] * (
                    1 - w.indirim_orani[d - sabitler.IADE_GECIKME_GUN, ho[donen]]
                )
                satis_p.append((d, donen, -iade[donen],
                                -np.round(fiyat * iade[donen], 2), np.zeros(donen.size)))

        # 9) Stoklu bayrağı
        stoklu_gecmisi[d] = stok > 0

        # 10) Talep → satış
        istenen = talep[d].astype(np.int64)
        satilan = np.minimum(istenen, stok)
        kayip = istenen - satilan
        stok -= satilan

        satan = np.flatnonzero(satilan > 0)
        if satan.size:
            islem = rng.random(satan.size) < sabitler.ISLEM_INDIRIM_OLASILIGI
            md = w.indirim_orani[d, ho[satan]]
            birim = liste[satan] * (1 - md) * np.where(
                islem & (md == 0), 1 - sabitler.ISLEM_INDIRIM_ORANI, 1.0
            )
            satis_p.append((d, satan, satilan[satan],
                            np.round(birim * satilan[satan], 2),
                            np.round((liste[satan] - birim) * satilan[satan], 2)))
        kayip_olan = np.flatnonzero(kayip > 0)
        if kayip_olan.size:
            kayip_p.append((d, kayip_olan, kayip[kayip_olan]))

        satis_gecmisi[d] = satilan
        satis_28 += satilan
        if d >= sabitler.OLU_STOK_PENCERESI_GUN:
            satis_28 -= satis_gecmisi[d - sabitler.OLU_STOK_PENCERESI_GUN]
        satilan_option += _topla(ho, satilan, O)
        satilan_option_kum[d + 1] = satilan_option

    def _tablo(parcalar, indis_adi, degerler):
        if not parcalar:
            return pd.DataFrame(columns=["gun", indis_adi, *degerler])
        tablo = {
            "gun": np.concatenate([np.full(len(p[1]), p[0]) for p in parcalar]),
            indis_adi: np.concatenate([p[1] for p in parcalar]),
        }
        for i, ad in enumerate(degerler):
            tablo[ad] = np.concatenate(
                [np.broadcast_to(np.asarray(p[2 + i]), len(p[1])) for p in parcalar]
            )
        return pd.DataFrame(tablo)

    return {
        "satis": _tablo(satis_p, "hucre", ["adet", "tutar", "indirim_tutari"]),
        "kayip_satis": _tablo(kayip_p, "hucre", ["kayip_adet"]),
        "sevkiyat": _tablo(sevk_p, "hucre", ["adet", "tip"]),
        "stok": _tablo(stok_p, "hucre", ["adet", "stoklu_gun"]),
        "depo_stok": _tablo(depo_p, "sku", ["adet"]),
        "siparis": siparisler,
        "son_durum": {"magaza_stok": stok, "depo": depo},
    }
