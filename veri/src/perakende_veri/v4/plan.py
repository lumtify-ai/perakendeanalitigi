"""v4 Lumoda planı: plan talebi (λ), ilk alım, ilk siparişler, plan tabloları.

Plan, Lumoda'nın **inandığı** taleptir, gizli gerçek değil; bilerek
naiftir (spec §4.3). Görev 8'in `Lambda`'sı Lumoda'nın bilgisiyle yeniden
kurulur (formül kopyalanmaz, `talep`'in yapı taşları çağrılır):

- sürpriz = line başına beklenen değeri E[S] = exp(σ²/2) (lognormal(0, σ)
  medyanı 1, ortalaması değil: zincir düzeyini geçmişten bilir, option
  düzeyinde "tutacak mı" bilgisi yoktur), sürüklenme = 1;
- mevsim: bütün mağazalarda iklimlerin fiziksel mağaza sayısıyla ağırlıklı
  zincir ortalaması (line üssü MEVSIM_LINE_USSU korunur);
- mağaza × alt kategori yerel gürültüsü = 1 (mağaza düzeyi hacim, gizli
  eksenler — kadın payı, genç eğilim, gelir, beden kayması — ve alt
  kategori yaşam eğrisi τ'su zincir geçmişinden bilinir sayılır);
- öznitelik etkisi: bir önceki **aynı tip** sezonun gerçek etkisi (AW23
  AW22'ninkini, SS25 SS24'ünkünü kullanır — trend gecikmesi); her tipin
  ilk sezonu (AW22, SS23) yürüyüşsüz başlangıç katsayısını (taban + o
  sezon tipinin düzey terimi) kullanır;
- olay kaymaları yok (kapanan mağazanın talebinin nereye gideceğini
  bilmez), ama kendi açılış/kapanış/tadilat takvimini bilir (kapalı gün 0);
- esneklik: sabit PLAN_ESNEKLIK = 1,7; indirim inancı indirimin ilk 28
  gününde %30, sonra çıkışa kadar %50 → `(1 − oran)^(−1,7)` plan λ'sına
  (option-gün çarpanına) katlanır;
- ONL kalibrasyonu gerçek λ'nınkiyle aynıdır (online payını bilir).

**Geçen yılın gerçekleşeni (spec'ten sapma):** plan tabloları simülasyon
çıktısından değil, bir önceki yılın aynı sezonunun **gizli gerçek beklenen
talebinden** (gerçek λ, planlanan indirim yolunda) × PLAN_BULUNABILIRLIK
(0,85) kurulur — simülasyon plana geri beslenmez, döngü olmasın diye. AW23
için önceki yıl ısınma dünyasının AW22'sidir. SS23 (ve pencereye hiç
önceki yılı girmeyen AW22) için önceki yıl yoktur: sezonun **kendi** gerçek
beklenen talebi 1/1,06 ile geri indirilir (bir yıl önceki aynı eğilim,
YIL_BUYUME ile tutarlı). Sonra × büyüme hedefi 1,06 × yönetim iyimserliği
(üst kategori başına U(1,03; 1,12), bir kez çekilir).

Sezon ataması (MFP ve mağaza planı): sezonluk option'ın bütün satışı
kendi sezonuna (outlet akışı dahil), DEVAMLI option'ınki günün sezonuna
(`talep.sezon_gun`; AW22'nin ilk dalgasından önceki ısınma günleri hiçbir
sezona yazılmaz) gider.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §4.3 (+ §3.2, §4.1)
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-10-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3'ün MOQ yuvarlama ve en
büyük kalan algoritmaları kopyalanmıştır).
"""

import dataclasses
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import sabitler
from .cesit import kanibalizasyon_payi
from .takvim import gun_indisi, simulasyon_takvimi
from .talep import (
    ALT_KATEGORILER,
    N_GUN,
    SEZON_KODLARI,
    Lambda,
    devamli_etki_kur,
    etki_katsayidan,
    katsayi_tablodan,
    magaza_gun_carpani,
    mevsim_ve_iklim_slotu,
    option_mevsim_idx,
    option_sezon_idx,
    oznitelik_duzeyi,
    sezon_gun,
    statik_taban,
    yasam_egrisi,
)
from .tedarik import hatali_adet, teslim_sapmasi

KANALLAR = ["Mağaza", "Online"]
UST_KATEGORILER = list(sabitler.KATEGORILER)
ZINCIR_SLOTU = 4  # talep.mevsim_ve_iklim_slotu: 4 = zincir ortalaması


# ---------------------------------------------------------------------------
# Yardımcılar (v3 kopyaları)
# ---------------------------------------------------------------------------


def moq_yuvarla(miktar: np.ndarray, moq: np.ndarray) -> np.ndarray:
    """En az MOQ, üstü 10'un katına yukarı (MOQ bir alt sınırdır, kat değil)."""
    y = sabitler.YUVARLAMA_ADET
    return np.maximum(moq, np.ceil(np.asarray(miktar) / y - 1e-9) * y).astype(np.int64)


def en_buyuk_kalan(toplam: int, paylar: np.ndarray) -> np.ndarray:
    """`toplam` adedi paylara göre tam sayılara böler (en büyük kalan;
    eşitlikte önce gelen indis kazanır)."""
    paylar = np.asarray(paylar, dtype=float)
    if toplam <= 0 or paylar.sum() <= 0:
        return np.zeros(len(paylar), dtype=np.int64)
    hedef = toplam * paylar / paylar.sum()
    tam = np.floor(hedef).astype(np.int64)
    kalan = int(toplam - tam.sum())
    if kalan > 0:
        sira = np.lexsort((np.arange(len(paylar)), -(hedef - tam)))
        tam[sira[:kalan]] += 1
    return tam


def _onceki_ayni_tip(s: int) -> int | None:
    """SEZON_KODLARI'nda s'den önceki aynı tip (AW/SS) sezonun indisi."""
    for i in range(s - 1, -1, -1):
        if SEZON_KODLARI[i][:2] == SEZON_KODLARI[s][:2]:
            return i
    return None


def _gun_sezonu() -> np.ndarray:
    """`[N_GUN]` günün sezonu (`talep.sezon_gun`); AW22'nin ilk dalgasından
    önceki ısınma günleri −1 (hiçbir sezona yazılmaz)."""
    gs = sezon_gun().copy()
    ilk = gun_indisi(sabitler.SEZONLAR[SEZON_KODLARI[0]]["dalgalar"][0])
    gs[:ilk] = -1
    return gs


# ---------------------------------------------------------------------------
# Plan λ
# ---------------------------------------------------------------------------


def plan_katsayisi(gizli_talep: dict) -> np.ndarray:
    """`[S, G, K]` Lumoda'nın öznitelik katsayısı inancı: s sezonunda bir
    önceki aynı tip sezonun gerçek katsayısı; her tipin ilk sezonunda
    yürüyüşsüz başlangıç (taban + o sezonun düzey terimi)."""
    segmentler = list(sabitler.SEGMENTLER)
    gercek = katsayi_tablodan(gizli_talep["trend_tablosu"], segmentler)
    duzey = oznitelik_duzeyi(segmentler)
    taban = gercek[0] - duzey[0]
    plan = np.empty_like(gercek)
    for s in range(len(SEZON_KODLARI)):
        onceki = _onceki_ayni_tip(s)
        plan[s] = gercek[onceki] if onceki is not None else taban + duzey[s]
    return plan


def plan_oznitelik_etkisi(gizli_talep: dict, optionlar: pd.DataFrame) -> np.ndarray:
    """`[S, G, O]` planın öznitelik etkisi (gerçek etkiyle aynı ortalama
    kuralı, `talep.etki_katsayidan`)."""
    return etki_katsayidan(plan_katsayisi(gizli_talep), optionlar.reset_index(drop=True))


def indirim_inanci(optionlar: pd.DataFrame, n_gun: int = N_GUN) -> tuple[np.ndarray, np.ndarray]:
    """(`carpan[n_gun, O]`, `oran[n_gun, O]`): planlanan indirim yolu.

    Sezonluk option'da [indirim, indirim + 28) %30, [indirim + 28, çıkış)
    %50, diğer günler 0; çarpan `(1 − oran)^(−PLAN_ESNEKLIK)`. DEVAMLI'da
    indirim yok (çarpan 1)."""
    ind = optionlar["indirim_gun"].to_numpy(dtype=np.int64)[None, :]
    cik = optionlar["cikis_gun"].to_numpy(dtype=np.int64)[None, :]
    d = np.arange(n_gun, dtype=np.int64)[:, None]
    sez = (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()[None, :]
    ilk = sez & (d >= ind) & (d < ind + sabitler.PLAN_INDIRIM_ILK_GUN) & (d < cik)
    sonra = sez & (d >= ind + sabitler.PLAN_INDIRIM_ILK_GUN) & (d < cik)
    oran = np.where(ilk, sabitler.PLAN_INDIRIM_ILK_ORAN, np.where(sonra, sabitler.PLAN_INDIRIM_SONRA_ORAN, 0.0))
    carpan = np.power(1.0 - oran, -sabitler.PLAN_ESNEKLIK)
    return carpan, oran


def indirim_yolunda(lam: Lambda, optionlar: pd.DataFrame) -> Lambda:
    """λ'nın planlanan indirim yolundaki hâli (option-gün çarpanına indirim
    inancı katlanır); gerçek λ'yı "geçen yılın gerçekleşeni" için planın
    fiyat varsayımına getirir."""
    carpan, _ = indirim_inanci(optionlar, lam.gun_sayisi)
    return dataclasses.replace(lam, g_option=lam.g_option * carpan)


def plan_lambda(
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    olaylar: pd.DataFrame,
    optionlar: pd.DataFrame,
    urunler: pd.DataFrame,
    cesit_hucre: pd.DataFrame,
    gizli_talep: dict,
    indirim: bool = True,
) -> Lambda:
    """Lumoda'nın plan λ'sı (`talep.Lambda`; `gun(d)` → `[C]`). Rastgelelik
    yok: gerçek dünyadan yalnız `gizli_talep`'in Lumoda'nın bilebileceği
    parçalarını (önceki sezonların öznitelik katsayıları, alt kategori τ'su,
    ONL kalibrasyonu) okur; tek tek sürpriz ve sürüklenme okunmaz (sürprizin
    yalnız line başına beklenen değeri, SURPRIZ_SIGMA'dan).

    `indirim=True` (varsayılan): planlanan indirim inancı option-gün
    çarpanına katlıdır (plan tabloları, ilk alım ve replenishment hedefi
    bu λ'yı kullanır). `False`: liste fiyatında plan talebi."""
    magazalar = magazalar.reset_index(drop=True)
    optionlar = optionlar.reset_index(drop=True)
    urunler = urunler.reset_index(drop=True)
    M, O = len(magazalar), len(optionlar)

    etki = plan_oznitelik_etkisi(gizli_talep, optionlar)
    statik = statik_taban(
        None, cesit_hucre, magazalar, gizli, urunler, optionlar, etki,
        yerel=np.ones((M, len(ALT_KATEGORILER))),
    )
    m_c = cesit_hucre["magaza_idx"].to_numpy().astype(np.intp)
    o_c = cesit_hucre["option_idx"].to_numpy().astype(np.intp)
    fiz_c = (magazalar["tip"] != "Online").to_numpy()[m_c]
    kalib = gizli_talep["onl_kalibrasyonu"]
    kalib_o = np.array(
        [kalib.get(gr, 1.0) for gr in zip(optionlar["ust_kategori"], optionlar["line"])]
    )
    statik = statik * np.where(fiz_c, 1.0, kalib_o[o_c])

    sigma = optionlar["line"].map(sabitler.SURPRIZ_SIGMA).to_numpy(dtype=float)
    g_option = yasam_egrisi(optionlar, gizli_talep["tau_oynama"]) * np.exp(sigma**2 / 2)[None, :]
    if indirim:
        g_option = g_option * indirim_inanci(optionlar)[0]

    mevsim5, _ = mevsim_ve_iklim_slotu(magazalar, gizli)
    devamli_etki = devamli_etki_kur(etki, magazalar, gizli, optionlar, cesit_hucre)
    return Lambda(
        statik=statik,
        statik_sezon=statik[None, :] * devamli_etki,
        hucre_option=o_c,
        hucre_magaza=m_c,
        magaza_iklim=np.full(M, ZINCIR_SLOTU, dtype=np.intp),
        option_mevsim=option_mevsim_idx(optionlar),
        g_option=g_option,
        mevsim_tablosu=mevsim5,
        magaza_gun=magaza_gun_carpani(magazalar, gizli, olaylar, magaza_toplam=None),
        sezon_gun=sezon_gun(),
        kanib=kanibalizasyon_payi(cesit_hucre, optionlar, np.ones(O)),
    )


# ---------------------------------------------------------------------------
# λ özeti (tek geçiş)
# ---------------------------------------------------------------------------


@dataclass
class LambdaOzeti:
    """Bir λ'nın bütün günler üzerinden tek geçişte toplanmış hâli.

    `gunluk[d, k, o]`: gün × kanal (0 Mağaza, 1 Online) × option toplamı;
    `magaza_sezon[s, m, o]`: günün sezonu s (`gun_sezonu`) olan günlerin
    mağaza × option toplamı; `gun_sezonu[d]` (−1 = hiçbir sezon)."""

    gunluk: np.ndarray
    magaza_sezon: np.ndarray
    gun_sezonu: np.ndarray


def lambda_ozeti(
    lam: Lambda, magazalar: pd.DataFrame, optionlar: pd.DataFrame, indirimli: bool = False
) -> LambdaOzeti:
    """λ'yı bütün günler boyunca bir kez gezer (`indirimli=True`: önce
    planlanan indirim yolu uygulanır — gerçek λ için)."""
    if indirimli:
        lam = indirim_yolunda(lam, optionlar.reset_index(drop=True))
    magazalar = magazalar.reset_index(drop=True)
    M, O, N = len(magazalar), lam.g_option.shape[1], lam.gun_sayisi
    fiz = (magazalar["tip"] != "Online").to_numpy()
    gs = _gun_sezonu()[:N]
    gunluk = np.zeros((N, 2, O))
    magaza_sezon = np.zeros((len(SEZON_KODLARI), M, O))
    for d in range(N):
        mo = np.bincount(lam.hucre_mo, weights=lam.gun(d), minlength=M * O).reshape(M, O)
        gunluk[d, 0] = mo[fiz].sum(axis=0)
        gunluk[d, 1] = mo[~fiz].sum(axis=0)
        if gs[d] >= 0:
            magaza_sezon[gs[d]] += mo
    return LambdaOzeti(gunluk=gunluk, magaza_sezon=magaza_sezon, gun_sezonu=gs)


def _option_gunluk_toplam(plan) -> np.ndarray:
    """`[N, O]` option başına günlük toplam (iki kanal)."""
    if isinstance(plan, LambdaOzeti):
        return plan.gunluk.sum(axis=1)
    O = plan.g_option.shape[1]
    sonuc = np.zeros((plan.gun_sayisi, O))
    for d in range(plan.gun_sayisi):
        sonuc[d] = np.bincount(plan.hucre_option, weights=plan.gun(d), minlength=O)
    return sonuc


# ---------------------------------------------------------------------------
# Talep tahmini, ilk alım
# ---------------------------------------------------------------------------


def talep_tahmini(plan: Lambda | LambdaOzeti, optionlar: pd.DataFrame) -> np.ndarray:
    """`[O]` sezon planı (plan λ'nın option'ın bütün hücreleri üzerinden
    [lansman, indirim) toplamı) ÷ HEDEF_TAM_FIYAT_STR; MOQ/kapasite öncesi.
    DEVAMLI option'da 0 (sürekli tedarik motorda). Görev 11 bunu tedarikçi
    seçiminden önce `lumoda_tedarikci_secimi`'ne verir."""
    optionlar = optionlar.reset_index(drop=True)
    toplam = _option_gunluk_toplam(plan)
    N, O = toplam.shape
    kum = np.vstack([np.zeros((1, O)), np.cumsum(toplam, axis=0)])
    idx = np.arange(O)
    lansman = np.clip(optionlar["lansman_gun"].to_numpy(dtype=np.int64), 0, N)
    indirim = np.clip(optionlar["indirim_gun"].to_numpy(dtype=np.int64), 0, N)
    sezonluk = (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()
    sezon_plani = np.where(sezonluk, kum[indirim, idx] - kum[lansman, idx], 0.0)
    return sezon_plani / sabitler.HEDEF_TAM_FIYAT_STR


def ilk_alim(
    plan: Lambda | LambdaOzeti,
    optionlar: pd.DataFrame,
    tedarikci_idx: np.ndarray,
    gizli_tedarikci: pd.DataFrame,
    teshis: bool = False,
):
    """`[O]` ilk alım adedi (DEVAMLI 0).

    `talep_tahmini` → en az tedarikçinin MOQ'su (menşe tablosu), 10'un
    katına yukarı → tedarikçinin o sezon **kalan** kapasitesiyle sınırlı
    (option'lar indis sırasıyla kapasiteyi tüketir; kırpılan adet 10'un
    katına aşağı). Kalan kapasite MOQ'nun altındaysa MOQ sipariş edilir
    (MOQ'nun altına inilmez) ve `kapasite_asimi` işaretlenir.

    `teshis=True`: `(adet, DataFrame)` döner; DataFrame option başına
    `talep_tahmini`, `yuvarlanmis`, `ilk_alim`, `kapasite_kirpildi`,
    `kapasite_asimi` taşır (gizli kapasiteye dayanır: dışa aktarılmaz).
    """
    optionlar = optionlar.reset_index(drop=True)
    tedarikci_idx = np.asarray(tedarikci_idx)
    tahmin = talep_tahmini(plan, optionlar)
    sezonluk = (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()
    mense = gizli_tedarikci["mense"].to_numpy()[tedarikci_idx]
    moq = np.array([sabitler.MENSE_V4[m]["moq"] for m in mense], dtype=np.int64)
    yuvarlanmis = np.where(sezonluk, moq_yuvarla(tahmin, moq), 0)

    kapasite = gizli_tedarikci["kapasite_sezon_adet"].to_numpy(dtype=np.int64)
    sezon = optionlar["sezon_kodu"].to_numpy()
    y = sabitler.YUVARLAMA_ADET
    adet = np.zeros(len(optionlar), dtype=np.int64)
    kirpildi = np.zeros(len(optionlar), dtype=bool)
    asimi = np.zeros(len(optionlar), dtype=bool)
    kullanim: dict[tuple[int, str], int] = {}
    for o in np.flatnonzero(sezonluk):
        t = int(tedarikci_idx[o])
        anahtar = (t, sezon[o])
        kalan = int(kapasite[t]) - kullanim.get(anahtar, 0)
        if yuvarlanmis[o] <= kalan:
            a = int(yuvarlanmis[o])
        elif kalan >= moq[o]:
            a, kirpildi[o] = kalan // y * y, True
        else:
            a, kirpildi[o], asimi[o] = int(moq[o]), True, True
        adet[o] = a
        kullanim[anahtar] = kullanim.get(anahtar, 0) + a
    if not teshis:
        return adet
    return adet, pd.DataFrame(
        {
            "option_id": optionlar["option_id"].to_numpy(),
            "talep_tahmini": tahmin,
            "yuvarlanmis": yuvarlanmis,
            "ilk_alim": adet,
            "kapasite_kirpildi": kirpildi,
            "kapasite_asimi": asimi,
        }
    )


# ---------------------------------------------------------------------------
# İlk siparişler
# ---------------------------------------------------------------------------


def ilk_siparisler(
    rng: np.random.Generator,
    optionlar: pd.DataFrame,
    urunler: pd.DataFrame,
    ilk_alim_adet: np.ndarray,
    tedarikci_idx: np.ndarray,
    tedarikciler: pd.DataFrame,
    gizli_tedarikci: pd.DataFrame,
) -> list[dict]:
    """Sezonluk option başına bir ilk sipariş (v3 sözlük biçimi + `tedarikci`,
    `hatali`, `numune`).

    `planlanan_gun` = lansman − 7; `siparis_gun` = planlanan − 7 ×
    `ilk_siparis_hafta`; `gerceklesen_gun` = planlanan + önceden çekilmiş
    sapma (`teslim_sapmasi`, n=1). `adetler` ilk alımın SKU'lara zincir
    beden eğrisiyle (en büyük kalan) bölüşümü; `hatali` (SKU başına,
    `skular` hizalı) = `hatali_adet`'in option düzeyindeki hatalısının
    adetlere en büyük kalanla bölüşümü (uzmanlık uyumuyla), `numune`
    option düzeyinde. `tedarikci` = `tedarikciler` satır indisi.

    Çekiliş sırası (sabit sayıda, bütün O option için): 1. teslim_sapmasi
    [O, 1], 2. hatali_adet [O]. Görev 11 bir alt üreteç verir.
    """
    optionlar = optionlar.reset_index(drop=True)
    urunler = urunler.reset_index(drop=True)
    tedarikci_idx = np.asarray(tedarikci_idx)
    ilk_alim_adet = np.asarray(ilk_alim_adet, dtype=np.int64)

    sapma = teslim_sapmasi(rng, gizli_tedarikci, tedarikci_idx, 1)[:, 0]
    alan = optionlar["alt_kategori"].map(sabitler.ALT_KATEGORI_ALAN).to_numpy()
    uyum = alan == tedarikciler["uzmanlik"].to_numpy()[tedarikci_idx]
    numune, hatali = hatali_adet(rng, gizli_tedarikci, tedarikci_idx, ilk_alim_adet, uyum)

    option_idx = pd.Series(np.arange(len(optionlar)), index=optionlar["option_id"])
    sku_option = option_idx.loc[urunler["option_id"]].to_numpy()
    beden_sayisi = urunler.groupby("option_id")["beden_sira"].transform("size").to_numpy()
    zincir = np.asarray(sabitler.BEDEN_PAYLARI_ZINCIR)
    sku_pay = np.where(
        beden_sayisi > 1, zincir[np.clip(urunler["beden_sira"].to_numpy() - 1, 0, len(zincir) - 1)], 1.0
    )
    option_skulari = pd.Series(np.arange(len(urunler))).groupby(sku_option).apply(np.asarray)
    ilk_hafta = tedarikciler["ilk_siparis_hafta"].to_numpy()

    siparisler = []
    sezonluk = (optionlar["sezon_kodu"] != sabitler.DEVAMLI).to_numpy()
    for o in np.flatnonzero(sezonluk & (ilk_alim_adet > 0)):
        t = int(tedarikci_idx[o])
        skular = option_skulari[o]
        adetler = en_buyuk_kalan(int(ilk_alim_adet[o]), sku_pay[skular])
        planlanan = int(optionlar.at[o, "lansman_gun"]) - sabitler.PLANLANAN_TESLIM_ONCE_GUN
        siparisler.append(
            {
                "tip": "ilk",
                "option": int(o),
                "siparis_gun": planlanan - 7 * int(ilk_hafta[t]),
                "planlanan_gun": planlanan,
                "gerceklesen_gun": planlanan + int(sapma[o]),
                "skular": skular,
                "adetler": adetler,
                "tedarikci": t,
                "hatali": en_buyuk_kalan(int(hatali[o]), adetler),
                "numune": int(numune[o]),
            }
        )
    return siparisler


# ---------------------------------------------------------------------------
# Plan tabloları
# ---------------------------------------------------------------------------


def _ay_indisi(n_gun: int) -> tuple[np.ndarray, np.ndarray]:
    """(`[n_gun]` mutlak ay indisi yıl·12 + ay − 1, sıralı benzersiz aylar)."""
    tarih = pd.DatetimeIndex(simulasyon_takvimi()["tarih"])[:n_gun]
    ay = (tarih.year * 12 + tarih.month - 1).to_numpy()
    return ay, np.unique(ay)


def _ay_metni(ay_mutlak: np.ndarray) -> np.ndarray:
    return np.array([f"{a // 12:04d}-{a % 12 + 1:02d}" for a in ay_mutlak])


def _sezon_anahtari(ozet: LambdaOzeti, optionlar: pd.DataFrame) -> np.ndarray:
    """`[N, O]` (gün, option) satışının yazıldığı sezon (−1 = hiçbiri)."""
    sezon_o = option_sezon_idx(optionlar)
    return np.where(sezon_o[None, :] >= 0, sezon_o[None, :], ozet.gun_sezonu[:, None])


def _mfp_plan(ozet: LambdaOzeti, optionlar: pd.DataFrame, iyimserlik: dict[str, float]) -> pd.DataFrame:
    N, _, O = ozet.gunluk.shape
    S, U = len(SEZON_KODLARI), len(UST_KATEGORILER)
    _, oran = indirim_inanci(optionlar, N)
    fiyat = optionlar["liste_fiyati"].to_numpy(dtype=float)[None, :] * (1.0 - oran)
    alis = optionlar["alis_fiyati"].to_numpy(dtype=float)[None, :]
    ust_o = optionlar["ust_kategori"].map({u: i for i, u in enumerate(UST_KATEGORILER)}).to_numpy()
    ay_d, aylar = _ay_indisi(N)
    ay_rel = np.searchsorted(aylar, ay_d)
    A = len(aylar)

    sezon = _sezon_anahtari(ozet, optionlar)
    gecerli = sezon >= 0
    anahtar = (ay_rel[:, None] * S + np.maximum(sezon, 0)) * U + ust_o[None, :]
    boyut = A * S * U
    parcalar = []
    for k, kanal in enumerate(KANALLAR):
        adet = ozet.gunluk[:, k, :]
        topla = lambda w: np.bincount(anahtar[gecerli], weights=w[gecerli], minlength=boyut)
        a = topla(adet)
        tutar = topla(adet * fiyat)
        maliyet = topla(adet * alis)
        ai, si, ui = np.unravel_index(np.arange(boyut), (A, S, U))
        parcalar.append(
            pd.DataFrame(
                {"sezon": si, "ay": aylar[ai], "kanal": kanal, "ust": ui,
                 "adet": a, "tutar": tutar, "maliyet": maliyet}
            )
        )
    ham = pd.concat(parcalar, ignore_index=True)
    ham = ham[ham.adet > 0]

    satirlar = []
    for s in range(S):
        onceki = _onceki_ayni_tip(s)
        if onceki is not None:
            gecen = ham[ham.sezon == onceki].copy()
            gecen["ay"] = gecen["ay"] + 12
            carpan = 1.0
        else:  # önceki yıl dünyada yok: sezonun kendi gerçeği, bir yıl geri
            gecen = ham[ham.sezon == s].copy()
            carpan = 1.0 / sabitler.PLAN_BUYUME_HEDEFI
        gecen["sezon"] = s
        iyim = gecen["ust"].map(lambda u: iyimserlik[UST_KATEGORILER[u]]).to_numpy()
        f = carpan * sabitler.PLAN_BULUNABILIRLIK * sabitler.PLAN_BUYUME_HEDEFI * iyim
        for kol in ("adet", "tutar", "maliyet"):
            gecen[kol] = gecen[kol] * f
        satirlar.append(gecen)
    mfp = pd.concat(satirlar, ignore_index=True)

    mfp = pd.DataFrame(
        {
            "sezon_kodu": np.array(SEZON_KODLARI)[mfp.sezon.to_numpy()],
            "_ay": mfp.ay.to_numpy(),
            "kanal": mfp.kanal.to_numpy(),
            "ust_kategori": np.array(UST_KATEGORILER)[mfp.ust.to_numpy()],
            "adet": np.rint(mfp.adet.to_numpy()).astype(np.int64),
            "satis_tutari": np.round(mfp.tutar.to_numpy(), 2),
            "brut_marj": np.round(mfp.tutar.to_numpy() - mfp.maliyet.to_numpy(), 2),
        }
    )
    mfp = mfp[mfp.adet > 0]
    mfp = mfp.sort_values(["sezon_kodu", "kanal", "ust_kategori", "_ay"], kind="stable")
    mfp["_sira"] = mfp.sezon_kodu.map({k: i for i, k in enumerate(SEZON_KODLARI)})
    grup = mfp.groupby(["sezon_kodu", "kanal", "ust_kategori"], sort=False)["adet"]
    sonraki = grup.shift(-1).fillna(0).to_numpy()
    mfp["donem_sonu_stok"] = np.rint(sonraki * sabitler.MFP_STOK_KAPSAMA_AY).astype(np.int64)
    baslangic = mfp.groupby(["sezon_kodu", "kanal", "ust_kategori"], sort=False)["donem_sonu_stok"].shift(1)
    mfp["otb"] = mfp["adet"] + mfp["donem_sonu_stok"] - baslangic.fillna(0).astype(np.int64)
    mfp["ay"] = _ay_metni(mfp["_ay"].to_numpy())
    mfp = mfp.sort_values(["_sira", "_ay", "kanal", "ust_kategori"], kind="stable")
    return mfp[
        ["sezon_kodu", "ay", "kanal", "ust_kategori", "satis_tutari", "adet",
         "brut_marj", "donem_sonu_stok", "otb"]
    ].reset_index(drop=True)


def _range_plan(
    rng: np.random.Generator, optionlar: pd.DataFrame, ilk_alim_adet: np.ndarray
) -> pd.DataFrame:
    sez = optionlar[optionlar["sezon_kodu"] != sabitler.DEVAMLI].copy()
    sez["_alim"] = np.asarray(ilk_alim_adet)[sez.index.to_numpy()]
    sez["_sira"] = sez.sezon_kodu.map({k: i for i, k in enumerate(SEZON_KODLARI)})
    anahtar = ["sezon_kodu", "alt_kategori", "fiyat_segmenti", "line"]
    g = (
        sez.groupby(["_sira"] + anahtar)
        .agg(sayi=("option_id", "size"), fiyat=("liste_fiyati", "mean"), alim=("_alim", "sum"))
        .reset_index()
        .sort_values(["_sira", "alt_kategori", "fiyat_segmenti", "line"], kind="stable")
    )
    gurultu = rng.lognormal(0.0, sabitler.PLAN_RANGE_SIGMA, size=len(g))
    sayi = np.maximum(1, np.rint(g.sayi.to_numpy() * gurultu)).astype(np.int64)
    return pd.DataFrame(
        {
            "sezon_kodu": g.sezon_kodu.to_numpy(),
            "alt_kategori": g.alt_kategori.to_numpy(),
            "fiyat_segmenti": g.fiyat_segmenti.to_numpy(),
            "line": g.line.to_numpy(),
            "option_sayisi": sayi,
            "ortalama_fiyat": np.round(g.fiyat.to_numpy(), 2),
            "derinlik": np.rint(g.alim.to_numpy() / sayi).astype(np.int64),
        }
    )


def _magaza_plan(ozet: LambdaOzeti, magazalar: pd.DataFrame, optionlar: pd.DataFrame) -> pd.DataFrame:
    S, M, O = ozet.magaza_sezon.shape
    U = len(UST_KATEGORILER)
    ust_o = optionlar["ust_kategori"].map({u: i for i, u in enumerate(UST_KATEGORILER)}).to_numpy()
    tek = np.zeros((O, U))
    tek[np.arange(O), ust_o] = 1.0
    sezon_o = option_sezon_idx(optionlar)
    toplam = ozet.magaza_sezon.sum(axis=0)  # sezonluk: bütün ömrü kendi sezonuna
    hedef = np.zeros((S, M, U))
    for s in range(S):
        kendi = sezon_o == s
        dev = sezon_o < 0
        hedef[s] = toplam[:, kendi] @ tek[kendi] + ozet.magaza_sezon[s][:, dev] @ tek[dev]
    si, mi, ui = np.unravel_index(np.arange(S * M * U), (S, M, U))
    return pd.DataFrame(
        {
            "sezon_kodu": np.array(SEZON_KODLARI)[si],
            "magaza_id": magazalar["magaza_id"].to_numpy()[mi],
            "ust_kategori": np.array(UST_KATEGORILER)[ui],
            "satis_hedefi": np.rint(hedef.ravel()).astype(np.int64),
        }
    )


def plan_tablolari(
    rng: np.random.Generator,
    plan: Lambda | LambdaOzeti,
    gercek: Lambda | LambdaOzeti,
    magazalar: pd.DataFrame,
    optionlar: pd.DataFrame,
    ilk_alim_adet: np.ndarray,
) -> dict[str, pd.DataFrame]:
    """Yayımlanan plan tabloları (spec §4.3):

    - `mfp_plan` (sezon × ay × kanal × üst kategori): `satis_tutari`, `adet`,
      `brut_marj` (TL, tutar − alış maliyeti), `donem_sonu_stok` (adet;
      sonraki ayın satış planı × MFP_STOK_KAPSAMA_AY, sezonun son ayında 0),
      `otb` (adet) = satış + dönem sonu stok − dönem başı stok (bir önceki
      ayın dönem sonu; sezonun ilk ayında 0). Kaynak: geçen yılın
      gerçekleşeni (modül docstring'i) × 1,06 × iyimserlik. `ay` "YYYY-MM".
    - `range_plan` (sezon × alt kategori × fiyat segmenti × line; yalnız
      sezonluk Collection/Outlet): `option_sayisi` = gerçekleşen sayı ×
      lognormal(0, 0,05) (≥ 1), `ortalama_fiyat` (liste), `derinlik` = ilk
      alım toplamı ÷ option sayısı.
    - `magaza_plan` (sezon × mağaza × üst kategori, ONL dahil):
      `satis_hedefi` (adet) = plan λ toplamı (Görev 12 ilk dağıtım payı).

    `gercek` gerçek λ ise planlanan indirim yolunda özetlenir; `LambdaOzeti`
    verilirse zaten o yolda sayılır. Çekiliş sırası: 1. iyimserlik (üst
    kategori başına, KATEGORILER sırası), 2. range gürültüsü (satır başına).
    """
    magazalar = magazalar.reset_index(drop=True)
    optionlar = optionlar.reset_index(drop=True)
    lo, hi = sabitler.PLAN_IYIMSERLIK_ARALIGI
    iyimserlik = {u: float(rng.uniform(lo, hi)) for u in UST_KATEGORILER}
    plan_oz = plan if isinstance(plan, LambdaOzeti) else lambda_ozeti(plan, magazalar, optionlar)
    gercek_oz = (
        gercek if isinstance(gercek, LambdaOzeti)
        else lambda_ozeti(gercek, magazalar, optionlar, indirimli=True)
    )
    return {
        "mfp_plan": _mfp_plan(gercek_oz, optionlar, iyimserlik),
        "range_plan": _range_plan(rng, optionlar, ilk_alim_adet),
        "magaza_plan": _magaza_plan(plan_oz, magazalar, optionlar),
    }
