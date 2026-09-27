"""Motorun ham çıktısından yayımlanan tablolar ve gizli gerçek sözlüğü.

`hareket_tablolari(dunya, ham)` spec §7.1'in 18 tablosunu TEMİZ olarak
üretir (kirli kayıtlar `kirlet.py`, montaj `uret.py`); `gizli_gercek`
yayımlanmayan doğruyu (kayıp satış, ikame, segment, ε, öznitelik etkisi,
tedarikçi profili) aynı kimliklerle verir.

**Pencere.** Hareket tabloları yalnız 2023-01-01 – 2025-12-31'i taşır:
`satis`, `stok`, `depo_stok` gününe; `sevkiyat` çıkış gününe; `fiyat`
hafta başına (pencere içindeki pazartesiler); `kalite_kontrol` teslim
gününe göre. `siparis`: pencerede verilen ya da pencerede teslim edilen
sipariş (ısınmada verilip pencerede gelen ilk siparişler dahil); teslimi
pencereden sonraya kalanın `gerceklesen_teslim`'i boştur (veri
2025-12-31'de kesilir, zincir henüz gelmemiş malın ne zaman geleceğini
bilmez; planlananı bilir). Aynı kural `sevkiyat.varis_tarihi` için de
geçerlidir: pencere sonrası varış boş. Boyut tabloları tamdır (`sezon`
AW22 dahil 21 satır, `urun` AW22 ürünleri dahil, `kampanya` ısınmadakiler
dahil).

**Kimlikler.** Mağaza `magaza_id` (online `ONL`, depo `DEPO`), SKU
`urun_id`, kampanya `kampanya.kampanya_id` (ham satır konumundan; −1 →
boş), paket `paket.paket_id` (ham paket indisinden; −1 → boş), sipariş
`SP00001…` (sipariş günü, tip, option sırasıyla).

**Tipler.** Büyük tablolarda kimlikler `category` (kategoriler sözlük
sırasıyla ve dünyanın bütün kimlikleri: kirli satırlar eklenince tip
korunur; `DEPO` yalnız sevkiyat uçlarının kümesinde), adet `int32`, `stoklu_gun` `int8`; para `float64`, 2 ondalık.

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3 `uret.hucre_tablosu` ve
`siparis_tablosu` kalıbı fikir olarak alınmıştır).
"""

import numpy as np
import pandas as pd

from . import sabitler
from .motor.satis import hat_indisi
from .politika import paket_tablosu
from .takvim import gun_indisi, takvim_tablosu

# Yayımlanan sevkiyat tipleri (motorun `baslangic`ı yayımlanmaz: ısınmanın
# ilk günü rafa konan mal, pencereden 181 gün önce).
YAYIMLANAN_SEVK_TIPLERI = (
    "ilk_dagitim",
    "replenishment",
    "outlet_akisi",
    "stok_devri",
    "elle_transfer",
    "acilis_transferi",
    "kapanis_transferi",
    "geri_yonlendirme",
    "iade_depoya",
)
SIPARIS_TIPLERI = ("ilk", "rpt", "surekli")
_TIP_SIRASI = {"ilk": 0, "surekli": 1, "rpt": 2}
HATLAR = ("normal", "outlet", "online")
DEPO = "DEPO"
SIRALAMA = ["tarih", "magaza_id", "urun_id"]


def pencere() -> tuple[int, int]:
    """(ilk, son) gün indisi, ikisi de dahil."""
    return gun_indisi(sabitler.BASLANGIC), gun_indisi(sabitler.BITIS)


def _gun_tarihi(gun) -> np.ndarray:
    """Gün indisi (negatif ya da uzatma ötesi olabilir) → datetime64[ns]."""
    bas = np.datetime64(sabitler.ISINMA_BASLANGIC, "D")
    return (bas + np.asarray(gun, dtype=np.int64).astype("timedelta64[D]")).astype("datetime64[ns]")


# ---------------------------------------------------------------------------
# Ortak kategoriler
# ---------------------------------------------------------------------------


class _Kimlik:
    """Dünyanın kimlik sözlükleri: indis → sözlük sıralı kategori kodu."""

    def __init__(self, dunya):
        m = dunya.magazalar["magaza_id"].to_numpy().astype(str)
        self.magaza_kat = pd.Index(sorted(m))
        self.magaza_kod = self.magaza_kat.get_indexer(m)
        self.yer_kat = pd.Index(sorted([*m, DEPO]))     # sevkiyat: mağaza + depo
        self.yer_kod = self.yer_kat.get_indexer(m)
        self.depo_kod = int(self.yer_kat.get_loc(DEPO))
        u = dunya.urunler["urun_id"].to_numpy().astype(str)
        self.urun_kat = pd.Index(sorted(u))
        self.urun_kod = self.urun_kat.get_indexer(u)
        o = dunya.optionlar["option_id"].to_numpy().astype(str)
        self.option_kat = pd.Index(sorted(o))
        self.option_kod = self.option_kat.get_indexer(o)

    def magaza(self, m_idx: np.ndarray) -> pd.Categorical:
        """Mağaza indisi → kategori (kümede `DEPO` yok)."""
        kod = self.magaza_kod[np.asarray(m_idx, dtype=np.int64)]
        return pd.Categorical.from_codes(kod, self.magaza_kat)

    def yer(self, m_idx: np.ndarray) -> pd.Categorical:
        """Sevkiyat ucu: mağaza indisi, −1 = `DEPO`."""
        m_idx = np.asarray(m_idx, dtype=np.int64)
        kod = np.where(m_idx >= 0, self.yer_kod[np.maximum(m_idx, 0)], self.depo_kod)
        return pd.Categorical.from_codes(kod, self.yer_kat)

    def urun(self, s_idx: np.ndarray) -> pd.Categorical:
        return pd.Categorical.from_codes(self.urun_kod[np.asarray(s_idx, dtype=np.int64)], self.urun_kat)

    def option(self, o_idx: np.ndarray) -> pd.Categorical:
        return pd.Categorical.from_codes(self.option_kod[np.asarray(o_idx, dtype=np.int64)], self.option_kat)


def _pencereli(ham: pd.DataFrame, sutun: str = "gun") -> pd.DataFrame:
    bas, son = pencere()
    g = ham[sutun].to_numpy()
    return ham[(g >= bas) & (g <= son)]


def hucre_tablosu(dunya, ham: pd.DataFrame, kimlik: _Kimlik | None = None) -> pd.DataFrame:
    """Ham (gun, hucre, …) → pencereli (tarih, magaza_id, urun_id, …)."""
    k = kimlik or _Kimlik(dunya)
    ham = _pencereli(ham)
    h = ham["hucre"].to_numpy(dtype=np.int64)
    df = pd.DataFrame(
        {
            "tarih": _gun_tarihi(ham["gun"].to_numpy()),
            "magaza_id": k.magaza(np.asarray(dunya.hucre_magaza)[h]),
            "urun_id": k.urun(np.asarray(dunya.hucre_sku)[h]),
        }
    )
    for kolon in ham.columns.drop(["gun", "hucre"]):
        df[kolon] = ham[kolon].to_numpy()
    return df


def _sirala(df: pd.DataFrame, sutunlar: list[str]) -> pd.DataFrame:
    return df.sort_values(sutunlar, kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Hareket tabloları
# ---------------------------------------------------------------------------


def satis_tablosu(dunya, ham: dict, k: _Kimlik) -> pd.DataFrame:
    df = hucre_tablosu(dunya, ham["satis"], k)
    kamp = df.pop("kampanya_id").to_numpy(dtype=np.int64)
    df["adet"] = df["adet"].astype(np.int32)
    df["tutar"] = df["tutar"].astype(np.float64).round(2)
    df["indirim_tutari"] = df["indirim_tutari"].astype(np.float64).round(2)
    df["kampanya_id"] = pd.Categorical.from_codes(
        kamp, pd.Index(dunya.kampanya["kampanya_id"].astype(str))
    )
    return _sirala(df, SIRALAMA)


def stok_tablosu(dunya, ham: dict, k: _Kimlik) -> pd.DataFrame:
    df = hucre_tablosu(dunya, ham["stok"], k)
    df["adet"] = df["adet"].astype(np.int32)
    df["stoklu_gun"] = df["stoklu_gun"].astype(np.int8)
    return _sirala(df, SIRALAMA)


def depo_stok_tablosu(dunya, ham: dict, k: _Kimlik) -> pd.DataFrame:
    d = _pencereli(ham["depo_stok"])
    df = pd.DataFrame(
        {
            "tarih": _gun_tarihi(d["gun"].to_numpy()),
            "urun_id": k.urun(d["sku"].to_numpy()),
            "adet": d["adet"].to_numpy().astype(np.int32),
        }
    )
    return _sirala(df, ["tarih", "urun_id"])


def sevkiyat_tablosu(dunya, ham: dict, k: _Kimlik) -> pd.DataFrame:
    """Çıkışı pencerede olan, `baslangic` dışı bütün sevkler. Varışı pencere
    sonrasına kalanın `varis_tarihi` boştur."""
    _, son = pencere()
    sv = _pencereli(ham["sevkiyat"])
    sv = sv[sv["tip"].isin(YAYIMLANAN_SEVK_TIPLERI)]
    varis = sv["varis_gun"].to_numpy()
    paket_idleri, _, _ = paket_tablosu(dunya.paketler)
    df = pd.DataFrame(
        {
            "tarih": _gun_tarihi(sv["gun"].to_numpy()),
            "varis_tarihi": np.where(varis <= son, _gun_tarihi(varis), np.datetime64("NaT", "ns")),
            "kaynak": k.yer(sv["kaynak"].to_numpy()),
            "hedef": k.yer(sv["hedef"].to_numpy()),
            "urun_id": k.urun(sv["sku"].to_numpy()),
            "adet": sv["adet"].to_numpy().astype(np.int32),
            "tip": pd.Categorical(sv["tip"].to_numpy(), categories=list(YAYIMLANAN_SEVK_TIPLERI)),
            "paket_id": pd.Categorical.from_codes(
                sv["paket_id"].to_numpy(dtype=np.int64), pd.Index(paket_idleri.astype(str))
            ),
        }
    )
    return _sirala(df, ["tarih", "tip", "kaynak", "hedef", "urun_id"])


def fiyat_tablosu(dunya, ham: dict, k: _Kimlik) -> pd.DataFrame:
    """Option × hafta × hat paneli: (option, hat) çiftinin hücre penceresiyle
    (en erken açılış – en geç kapanış) kesişen her pencere pazartesisi için
    haftanın son günündeki indirim oranı (ham `fiyat` değişim kaydının
    o güne kadarki son satırı). Pazartesi değişimleri bütün haftayı, hafta
    ortası lansman satırı lansman haftasını belirler."""
    bas, son = pencere()
    hat_c = hat_indisi(np.asarray(dunya.hucre_online), np.asarray(dunya.hucre_outlet_akisi))
    O = len(dunya.optionlar)
    cift_c = np.asarray(dunya.hucre_option, dtype=np.int64) * 3 + hat_c
    ciftler, ters = np.unique(cift_c, return_inverse=True)
    acilis = np.full(len(ciftler), np.iinfo(np.int64).max)
    kapanis = np.full(len(ciftler), np.iinfo(np.int64).min)
    np.minimum.at(acilis, ters, np.asarray(dunya.hucre_acilis, dtype=np.int64))
    np.maximum.at(kapanis, ters, np.asarray(dunya.hucre_kapanis, dtype=np.int64))

    # Gün 0 (ISINMA_BASLANGIC) pazartesidir: pazartesiler 7'nin katları.
    pazartesi = np.arange(bas + (-bas) % 7, son + 1, 7, dtype=np.int64)
    # (çift, hafta) kesişimi: [pzt, pzt+7) ∩ [acilis, kapanis)
    ic = (pazartesi[None, :] + 7 > acilis[:, None]) & (pazartesi[None, :] < kapanis[:, None])
    ci, wi = np.nonzero(ic)
    sorgu_gun = pazartesi[wi] + 6

    f = ham["fiyat"]
    anahtar_f = f["option"].to_numpy(dtype=np.int64) * 3 + f["hat"].to_numpy(dtype=np.int64)
    fg = f["gun"].to_numpy(dtype=np.int64)
    BUYUK = 10_000_000
    sira = np.lexsort((np.arange(len(f)), fg, anahtar_f))  # aynı gün: kayıt sırası, sonuncu geçerli
    kf = anahtar_f[sira] * BUYUK + fg[sira]
    oran_f = f["oran"].to_numpy(dtype=float)[sira]
    sorgu = ciftler[ci] * BUYUK + sorgu_gun
    j = np.searchsorted(kf, sorgu, side="right") - 1
    gecerli = (j >= 0) & (kf[np.maximum(j, 0)] // BUYUK == ciftler[ci])
    oran = np.where(gecerli, oran_f[np.maximum(j, 0)], 0.0)

    o_idx, h_idx = ciftler[ci] // 3, ciftler[ci] % 3
    assert (o_idx < O).all()
    df = pd.DataFrame(
        {
            "hafta_baslangic": _gun_tarihi(pazartesi[wi]),
            "option_id": k.option(o_idx),
            "hat": pd.Categorical.from_codes(h_idx, list(HATLAR)),
            "indirim_orani": np.round(oran, 4),
        }
    )
    return _sirala(df, ["hafta_baslangic", "option_id", "hat"])


def siparis_tablolari(dunya, ham: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(`siparis`, `kalite_kontrol`). `siparis` SKU düzeyinde, v3 sütunları
    + `tip`; kimlik (sipariş günü, tip, option_id) sırasıyla atanır."""
    bas, son = pencere()
    opt_id = dunya.optionlar["option_id"].to_numpy().astype(str)
    urun_id = dunya.urunler["urun_id"].to_numpy().astype(str)
    ted_id = dunya.tedarikciler["tedarikci_id"].to_numpy().astype(str)

    secili = [
        s for s in ham["siparis"]
        if s["tip"] in SIPARIS_TIPLERI
        and (bas <= s["siparis_gun"] <= son or bas <= s["gerceklesen_gun"] <= son)
    ]
    secili.sort(key=lambda s: (int(s["siparis_gun"]), _TIP_SIRASI[s["tip"]], opt_id[s["option"]]))
    no_id: dict[int, str] = {}
    parca = {a: [] for a in ("siparis_id", "tip", "option", "sku", "tedarikci",
                             "siparis_gun", "planlanan_gun", "gerceklesen_gun", "adet")}
    for i, s in enumerate(secili, start=1):
        sid = f"SP{i:05d}"
        no_id[int(s["no"])] = sid
        sk = np.asarray(s["skular"], dtype=np.int64)
        ad = np.asarray(s["adetler"], dtype=np.int64)
        g = ad > 0
        n = int(g.sum())
        parca["siparis_id"].append(np.full(n, sid, dtype=object))
        parca["tip"].append(np.full(n, s["tip"], dtype=object))
        parca["sku"].append(sk[g])
        parca["adet"].append(ad[g])
        for a in ("option", "tedarikci", "siparis_gun", "planlanan_gun", "gerceklesen_gun"):
            parca[a].append(np.full(n, int(s[a]), dtype=np.int64))
    c = {a: (np.concatenate(v) if v else np.array([], dtype=np.int64)) for a, v in parca.items()}
    gerc = c["gerceklesen_gun"]
    siparis = pd.DataFrame(
        {
            "siparis_id": c["siparis_id"].astype(str),
            "tip": c["tip"].astype(str),
            "option_id": opt_id[c["option"]],
            "urun_id": urun_id[c["sku"]],
            "tedarikci_id": ted_id[c["tedarikci"]],
            "siparis_tarihi": _gun_tarihi(c["siparis_gun"]),
            "planlanan_teslim": _gun_tarihi(c["planlanan_gun"]),
            "gerceklesen_teslim": np.where(gerc <= son, _gun_tarihi(gerc), np.datetime64("NaT", "ns")),
            "adet": c["adet"].astype(np.int32),
        }
    )

    kal = _pencereli(ham["kalite"])
    kal = kal[kal["tip"].isin(SIPARIS_TIPLERI)]
    sid = kal["siparis"].map(no_id)
    assert sid.notna().all(), "pencerede teslim edilen her sipariş yayımlanır"
    kalite = pd.DataFrame(
        {
            "siparis_id": sid.to_numpy().astype(str),
            "teslim_tarihi": _gun_tarihi(kal["gun"].to_numpy()),
            "numune": kal["numune"].to_numpy().astype(np.int32),
            "hatali": kal["hatali"].to_numpy().astype(np.int32),
        }
    )
    return siparis, _sirala(kalite, ["teslim_tarihi", "siparis_id"])


# ---------------------------------------------------------------------------
# Bütün tablolar (temiz)
# ---------------------------------------------------------------------------


def boyut_tablolari(dunya) -> dict[str, pd.DataFrame]:
    """Boyut ve plan tabloları (tam, pencere uygulanmaz). Yalnız yayımlanan
    sütunlar: gizli mağaza eksenleri ve tedarikçi profili (kapasite dahil)
    ayrı tablolardadır ve buraya girmez."""
    return {
        "magaza": dunya.magazalar.copy(),
        "magaza_olay": dunya.magaza_olay.copy(),
        "urun": dunya.urunler.copy(),
        "paket": dunya.paketler.copy(),
        "tedarikci": dunya.tedarikciler.copy(),
        "sezon": dunya.sezon.copy(),
        "takvim": takvim_tablosu(),
        "kampanya": dunya.kampanya.copy(),
        "mfp_plan": dunya.plan_tablolari["mfp_plan"].copy(),
        "range_plan": dunya.plan_tablolari["range_plan"].copy(),
        "magaza_plan": dunya.plan_tablolari["magaza_plan"].copy(),
    }


def hareket_tablolari(dunya, ham: dict) -> dict[str, pd.DataFrame]:
    """Spec §7.1'in 18 tablosu, pencereli ve temiz (kirli kayıtsız)."""
    k = _Kimlik(dunya)
    siparis, kalite = siparis_tablolari(dunya, ham)
    tablolar = boyut_tablolari(dunya)
    tablolar.update(
        {
            "siparis": siparis,
            "kalite_kontrol": kalite,
            "satis": satis_tablosu(dunya, ham, k),
            "fiyat": fiyat_tablosu(dunya, ham, k),
            "stok": stok_tablosu(dunya, ham, k),
            "depo_stok": depo_stok_tablosu(dunya, ham, k),
            "sevkiyat": sevkiyat_tablosu(dunya, ham, k),
        }
    )
    return tablolar


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def gizli_gercek(dunya, ham: dict) -> dict[str, pd.DataFrame]:
    """Yayımlanmayan doğru (spec §7.2); `uret.main` yazmaz, vakalar çağırır.

    kayip_satis        tarih, magaza_id, urun_id, kayip_adet (pencereli;
                       ikameden sonra kalan kalıcı kayıp)
    ikame_satis        tarih, magaza_id, urun_id, adet (alıcı hücre; bu adet
                       `satis`'te zaten vardır)
    segment            magaza_id + segment + bütün gizli eksenler
    esneklik           magaza_id, option_id, esneklik (yalnız taşınan çiftler)
    oznitelik_etkisi   sezon_kodu, segment, option_id, etki (log-etki)
    trend_tablosu      sezon_kodu, segment, anahtar, katsayi
    surpriz            option_id, surpriz
    tedarikci_profili  gizli tedarikçi profilinin tamamı
    """
    k = _Kimlik(dunya)
    g = dunya.gercek()
    kayip = hucre_tablosu(dunya, ham["gizli_kayip"], k).rename(columns={"adet": "kayip_adet"})
    ikame = hucre_tablosu(dunya, ham["ikame_satis"], k)

    m_c = np.asarray(dunya.hucre_magaza, dtype=np.int64)
    o_c = np.asarray(dunya.hucre_option, dtype=np.int64)
    cift = np.unique(m_c * len(dunya.optionlar) + o_c)
    m, o = cift // len(dunya.optionlar), cift % len(dunya.optionlar)
    eps = pd.DataFrame(
        {
            "magaza_id": dunya.magazalar["magaza_id"].to_numpy()[m],
            "option_id": dunya.optionlar["option_id"].to_numpy()[o],
            "esneklik": np.asarray(g["esneklik"])[m, o],
        }
    )

    trend = g["trend_tablosu"].copy()
    etki = np.asarray(g["oznitelik_etkisi"])
    sezonlar = trend["sezon_kodu"].unique()
    segmentler = trend["segment"].unique()
    S, G, O = etki.shape
    assert (S, G) == (len(sezonlar), len(segmentler))
    ss, gg, oo = np.meshgrid(np.arange(S), np.arange(G), np.arange(O), indexing="ij")
    oznitelik = pd.DataFrame(
        {
            "sezon_kodu": sezonlar[ss.ravel()],
            "segment": segmentler[gg.ravel()],
            "option_id": dunya.optionlar["option_id"].to_numpy()[oo.ravel()],
            "etki": etki.ravel(),
        }
    )
    return {
        "kayip_satis": _sirala(kayip, SIRALAMA),
        "ikame_satis": _sirala(ikame, SIRALAMA),
        "segment": g["segment"].copy(),
        "esneklik": eps,
        "oznitelik_etkisi": oznitelik,
        "trend_tablosu": trend,
        "surpriz": pd.DataFrame(
            {"option_id": dunya.optionlar["option_id"].to_numpy(), "surpriz": np.asarray(g["surpriz"])}
        ),
        "tedarikci_profili": g["tedarikci_profili"].copy(),
    }
