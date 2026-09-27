"""Motor durumu: `Durum` (değişen diziler), `Gorunum` (politikaya verilen
salt okunur karar anı), yolda kuyruğu, kayıt tamponları, `orantili_kes`,
mağaza açık/kapanacak takvimi, paket sığdırma, Basic/NOS sürekli tedarik.

v3 `simulasyon` kalıbının kopyası (içe aktarılmaz); v4 eklentileri: yolda
kuyruğu (mağazaya/depoya varış günü), fiyat hattı oranları, mağaza açık /
kapanacak maskeleri.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import sabitler
from ..plan import en_buyuk_kalan, moq_yuvarla
from ..takvim import gun_indisi


def topla(indis: np.ndarray, deger: np.ndarray, n: int) -> np.ndarray:
    """Tam sayı bincount (np.bincount ağırlıkla float döndürür)."""
    return np.bincount(indis, deger, minlength=n).astype(np.int64)


def salt_okunur(a: np.ndarray) -> np.ndarray:
    v = a.view()
    v.flags.writeable = False
    return v


# ---------------------------------------------------------------------------
# Görünüm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gorunum:
    """Politikanın karar anı (salt okunur diziler; geçmiş yalnız bugünden
    önceki satırlar). Bugünün talebi, satışı ve gelecekteki teslimler
    görünmez.

    **Politikalar `dunya`'nın yalnız kamuya açık alanlarını okuyabilir:**
    `magazalar`, `magaza_olay`, `urunler`, `optionlar`, `paketler`,
    `tedarikciler`, `kampanya`, `takvim`, `sezon`, `plan` / `ileri_plan` /
    `ileri_plan_option`, `plan_tablolari`, `ilk_alim`, `mesafe_km`,
    `depo_mesafe_km`, çeşit yapısı (`cesit`, `hucre_*`, `sku_option`,
    `sku_beden_payi`). **Asla** `lam`, `gizli_*` (`gizli_magaza`,
    `gizli_tedarikci`, `gizli_talep`), `esneklik`, `esneklik_hucre`,
    `sapma_*`, `ilk_siparisler` (gerçekleşen teslim günü, hatalı adet,
    numune: teslimden önce bilinemeyen gerçekleşme) ve `gercek()` okunmaz —
    bunlar motorun gizli gerçeğidir. Açık siparişlerin kamuya açık hâli
    `acik_siparisler`'dedir (gerçekleşen gün ve kalite çıkarılmış).
    (Sözleşmedir; `dunya` v3'teki gibi nesnenin kendisidir.)

    Alanlar: `gun`, `tarih`; `magaza_stok` [C] (o anki), `depo` [S] (o
    anki), `yolda` [C] (mağaza hücresine yolda olan), `satis_gecmisi`
    [gun, C] brüt satış (fiziksel: raftan; ONL: depodan), `stoklu_gecmisi`
    [gun, C] bool, `satis_28` [C] son 28 gün, `gonderilen_option` [O]
    mağazalara giden kümülatif, `satilan_option` [O] dünkü akşama kadar brüt
    satış (ONL dahil), `rpt_sayisi` [O], `ilk_dagitim_gun` [O] (option'ın
    son ilk dağıtım sevki; henüz yoksa çok büyük), `fiyat_orani` [O, 3]
    (normal / outlet / online hattının güncel markdown oranı), `acik_magaza`
    [M] bool (bugün açık), `kapanacak` [M] bool (kapanış kararı verilmiş),
    `acik_siparisler` (henüz teslim edilmemiş siparişlerin kopyaları).
    """

    dunya: object
    gun: int
    tarih: pd.Timestamp
    magaza_stok: np.ndarray
    depo: np.ndarray
    yolda: np.ndarray
    satis_gecmisi: np.ndarray
    stoklu_gecmisi: np.ndarray
    satis_28: np.ndarray
    gonderilen_option: np.ndarray
    satilan_option: np.ndarray
    rpt_sayisi: np.ndarray
    ilk_dagitim_gun: np.ndarray
    fiyat_orani: np.ndarray
    acik_magaza: np.ndarray
    kapanacak: np.ndarray
    acik_siparisler: tuple


# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------


YOK_GUN = 10**6  # "henüz olmadı" günü


class Durum:
    """Motorun değişen durumu (hepsi tam sayı; satış geçmişi int16)."""

    def __init__(self, D: int, C: int, S: int, O: int, M: int):
        self.stok = np.zeros(C, dtype=np.int64)
        self.depo = np.zeros(S, dtype=np.int64)
        self.yolda_hucre = np.zeros(C, dtype=np.int64)
        self.yolda_depo = np.zeros(S, dtype=np.int64)
        self.satis_gecmisi = np.zeros((D, C), dtype=np.int16)
        self.stoklu_gecmisi = np.zeros((D, C), dtype=bool)
        self.satis_28 = np.zeros(C, dtype=np.int64)
        self.gonderilen_option = np.zeros(O, dtype=np.int64)
        self.satilan_option = np.zeros(O, dtype=np.int64)
        self.satilan_option_kum = np.zeros((D + 1, O), dtype=np.int64)  # [d] = d'den önceki toplam
        self.rpt_sayisi = np.zeros(O, dtype=np.int64)
        self.surekli_sayisi = np.zeros(O, dtype=np.int64)
        self.acik_sku = np.zeros(S, dtype=np.int64)          # açık sipariş (SKU)
        self.ilk_dagitim_gun = np.full(O, YOK_GUN, dtype=np.int64)
        self.fiyat_orani = np.zeros((O, 3), dtype=float)
        self.siparisler: list[dict] = []
        self.teslim_takvimi: dict[int, list[dict]] = {}
        # Yolda kuyruğu: varış günü → [(hedef_hucre [n] (−1 = depo), sku [n], adet [n])]
        self.yolda: dict[int, list[tuple]] = {}

    # --- Sipariş --------------------------------------------------------
    def siparis_ekle(self, s: dict) -> None:
        self.siparisler.append(s)
        self.teslim_takvimi.setdefault(max(int(s["gerceklesen_gun"]), 0), []).append(s)
        self.acik_sku[s["skular"]] += s["adetler"]

    # --- Yolda ----------------------------------------------------------
    def yola_cikar(self, varis: np.ndarray, hedef_hucre: np.ndarray, sku: np.ndarray, adet: np.ndarray) -> None:
        """Satır başına varış günüyle kuyruğa ekler (hedef_hucre −1 = depo)."""
        for v in np.unique(varis):
            m = varis == v
            self.yolda.setdefault(int(v), []).append((hedef_hucre[m], sku[m], adet[m]))
        h = hedef_hucre >= 0
        np.add.at(self.yolda_hucre, hedef_hucre[h], adet[h])
        np.add.at(self.yolda_depo, sku[~h], adet[~h])

    def varanlar(self, d: int):
        """d günü varan partiler (kuyruktan çıkarılır)."""
        partiler = self.yolda.pop(d, [])
        for hh, sk, ad in partiler:
            h = hh >= 0
            np.subtract.at(self.yolda_hucre, hh[h], ad[h])
            np.subtract.at(self.yolda_depo, sk[~h], ad[~h])
        return partiler


# ---------------------------------------------------------------------------
# Kayıt tamponları
# ---------------------------------------------------------------------------


SEVKIYAT_SUTUNLARI = [
    "gun", "varis_gun", "kaynak", "hedef", "kaynak_hucre", "hedef_hucre",
    "sku", "adet", "tip", "paket_id",
]


class Kayit:
    """Günlük parçalar; sonunda tek DataFrame'e birleşir."""

    def __init__(self):
        self.satis, self.kayip, self.stok, self.depo = [], [], [], []
        self.sevkiyat, self.fiyat = [], []
        self.kalite: list[dict] = []

    def sevk(self, gun, varis, kaynak, hedef, kaynak_hucre, hedef_hucre, sku, adet, tip, paket=-1):
        n = len(adet)
        if n == 0:
            return
        b = lambda x: np.broadcast_to(np.asarray(x, dtype=np.int64), n)  # noqa: E731
        self.sevkiyat.append(
            (b(gun), b(varis), b(kaynak), b(hedef), b(kaynak_hucre), b(hedef_hucre),
             b(sku), b(adet), tip, b(paket))
        )

    def sevkiyat_tablosu(self) -> pd.DataFrame:
        if not self.sevkiyat:
            return pd.DataFrame({k: pd.Series(dtype=np.int64) for k in SEVKIYAT_SUTUNLARI})
        sut = {}
        for i, ad in enumerate(SEVKIYAT_SUTUNLARI):
            if ad == "tip":
                sut[ad] = np.concatenate([np.full(len(p[7]), p[8], dtype=object) for p in self.sevkiyat])
            else:
                sut[ad] = np.concatenate([p[i] for p in self.sevkiyat])
        return pd.DataFrame(sut)

    @staticmethod
    def tablo(parcalar, indis_adi, degerler) -> pd.DataFrame:
        """v3 `_tablo`: parça = (gun, indis [n], değer_1, değer_2, …)."""
        if not parcalar:
            return pd.DataFrame(columns=["gun", indis_adi, *degerler])
        tablo = {
            "gun": np.concatenate([np.full(len(p[1]), p[0], dtype=np.int64) for p in parcalar]),
            indis_adi: np.concatenate([p[1] for p in parcalar]).astype(np.int64),
        }
        for i, ad in enumerate(degerler):
            tablo[ad] = np.concatenate(
                [np.broadcast_to(np.asarray(p[2 + i]), len(p[1])) for p in parcalar]
            )
        return pd.DataFrame(tablo)


# ---------------------------------------------------------------------------
# Orantılı kesme (v3 kopyası)
# ---------------------------------------------------------------------------


def orantili_kes(istek: np.ndarray, hucre_sku: np.ndarray, depo: np.ndarray) -> np.ndarray:
    """Depo yetmeyen SKU'larda istekleri orantılı keser (v3 algoritması).

    Her hücre floor(istek · depo/toplam) alır; SKU'da artan adetler
    kesri en büyük hücrelere birer birer verilir (eşitlikte küçük indis).
    Deterministiktir; gönderilen toplam hiçbir SKU'da depoyu aşmaz.
    """
    S = len(depo)
    toplam = topla(hucre_sku, istek, S)
    kisitli = toplam > depo
    if not kisitli.any():
        return istek.astype(np.int64)
    oran = np.where(kisitli, depo / np.maximum(toplam, 1), 1.0)
    hedef = istek * oran[hucre_sku]
    taban = np.where(kisitli[hucre_sku], np.floor(hedef + 1e-9), istek).astype(np.int64)
    taban = np.minimum(taban, istek)
    kalan = depo - topla(hucre_sku, taban, S).astype(np.int64)
    kesir = np.where(kisitli[hucre_sku] & (istek > taban), hedef - taban, -1.0)
    sira = np.lexsort((np.arange(len(istek)), -kesir, hucre_sku))
    sku_sirali = hucre_sku[sira]
    grup_basi = np.searchsorted(sku_sirali, sku_sirali, side="left")
    rutbe = np.arange(len(sira)) - grup_basi
    ver = (kesir[sira] > 0) & (rutbe < np.maximum(kalan, 0)[sku_sirali])
    sonuc = taban.copy()
    sonuc[sira[ver]] += 1
    return sonuc


# ---------------------------------------------------------------------------
# Mağaza takvimi, paket sığdırma, sürekli tedarik
# ---------------------------------------------------------------------------


def magaza_takvimi(w, D: int) -> tuple[np.ndarray, np.ndarray]:
    """([D, M] açık, [D, M] kapanış kararı verilmiş). Açık = açılış ≤ d <
    kapanış ve tadilatta değil (ONL hep açık)."""
    mag = w.magazalar
    M = len(mag)
    d = np.arange(D)[:, None]
    acilis = np.array([gun_indisi(t) for t in mag["acilis_tarihi"]])
    kapanis = np.array([YOK_GUN if pd.isna(t) else gun_indisi(t) for t in mag["kapanis_tarihi"]])
    acik = (acilis[None, :] <= d) & (d < kapanis[None, :])
    kapanacak = np.zeros((D, M), dtype=bool)
    idx = {mid: i for i, mid in enumerate(mag["magaza_id"])}
    for r in w.magaza_olay.itertuples():
        m = idx[r.magaza_id]
        if r.olay == "tadilat":
            acik[gun_indisi(r.olay_tarihi):max(gun_indisi(r.bitis_tarihi), 0), m] = False
        elif r.olay == "kapanis":
            kapanacak[max(gun_indisi(r.karar_tarihi), 0):, m] = True
    acik[:, (mag["tip"] == "Online").to_numpy()] = True
    return acik, kapanacak


def paketleri_sigdir(ns: np.ndarray, icerik: np.ndarray, depo: np.ndarray) -> np.ndarray:
    """Paket sayılarını [n_m] depoya sığdırır (`icerik` [n_m, n_s], `depo`
    [n_s]). Tek paket tipinde max paket = min_s ⌊depo[s] ÷ içerik[s]⌋;
    aşarsa mağazalar en büyük kalanla orantılı küçülür (karışık paketlerde
    sığana dek birer azaltılır)."""
    ns = np.asarray(ns, dtype=np.int64)
    toplam = int(ns.sum())
    if toplam == 0:
        return ns
    ihtiyac = ns @ icerik
    if (ihtiyac <= depo).all():
        return ns
    # Paket başına ortalama içerikle üst sınır, sonra sığana dek azalt.
    ort = np.maximum(ihtiyac / toplam, 1e-12)
    ust = int(min(toplam, np.floor(np.min(np.where(ihtiyac > 0, depo / ort, np.inf)))))
    while ust >= 0:
        aday = en_buyuk_kalan(ust, ns.astype(float)) if ust > 0 else np.zeros_like(ns)
        if ((aday @ icerik) <= depo).all():
            return aday
        ust -= 1
    return np.zeros_like(ns)


def surekli_tedarik(w, z, d, sezonluk, L_o, moq_o, ted, option_skulari, siparis_ekle) -> None:
    """Basic/NOS sürekli tedarik: v3'ün SKU düzeyindeki (s, S) kuralı.

    Bir bedenin envanter pozisyonu (depo + açık sipariş) tedarik süresi +
    emniyet kadar planın altına düşerse option sipariş verir; miktar her
    bedeni tedarik süresi + gözden geçirme + emniyet planına tamamlar, en az
    MOQ. Plan düzeltmesi: son 8 haftanın zincir satışı ÷ aynı dönemin planı
    (sansürlü satışla — stoksuz kalınca düzeltme de düşük kalır)."""
    O = len(w.optionlar)
    opt = w.optionlar
    p = sabitler.SUREKLI_DUZELTME_GUN
    if d >= p:
        gecmis_plan = w.ileri_plan_option(d - p, p)
        gecmis_satis = z.satilan_option_kum[d] - z.satilan_option_kum[d - p]
        duzeltme = np.clip(
            np.divide(gecmis_satis, gecmis_plan, out=np.ones(O), where=gecmis_plan > 0),
            *sabitler.SUREKLI_DUZELTME_SINIR,
        )
    else:
        duzeltme = np.ones(O)
    for o in np.flatnonzero(~sezonluk):
        emniyet = sabitler.SUREKLI_EMNIYET_HAFTA[opt.at[o, "line"]]
        L = int(L_o[o])
        sk = option_skulari[o]
        pay = w.sku_beden_payi[sk] * duzeltme[o]
        s_nokta = w.ileri_plan_option(d, 7 * (L + emniyet))[o] * pay
        S_nokta = w.ileri_plan_option(d, 7 * (L + sabitler.SUREKLI_GOZDEN_GECIRME_HAFTA + emniyet))[o] * pay
        pozisyon = z.depo[sk] + z.acik_sku[sk]
        if not (pozisyon < s_nokta).any():
            continue
        eksik = np.maximum(S_nokta - pozisyon, 0.0)
        taban = en_buyuk_kalan(int(np.ceil(eksik.sum())), eksik)
        miktar = int(moq_yuvarla(np.array([taban.sum()]), np.array([int(moq_o[o])]))[0])
        adetler = taban + en_buyuk_kalan(miktar - int(taban.sum()), w.sku_beden_payi[sk])
        k = int(z.surekli_sayisi[o]) % w.sapma_surekli.shape[1]
        planlanan = d + 7 * L
        siparis_ekle({
            "tip": "surekli", "option": int(o), "siparis_gun": d, "planlanan_gun": planlanan,
            "gerceklesen_gun": planlanan + int(w.sapma_surekli[o, k]),
            "skular": sk, "adetler": adetler, "tedarikci": int(ted[o]),
        })
        z.surekli_sayisi[o] += 1
