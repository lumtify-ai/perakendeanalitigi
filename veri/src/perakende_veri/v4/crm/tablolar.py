"""Görev 13: B'nin yayımlanan tabloları ve gizli gerçeği (spec §7, §6).

`crm_tablolari(girdi, crm_ham, online, yorumlar)` altı tablo:

    musteri              musteri_id, kayit_tarihi, kayit_kanali, ev_magaza_id,
                         il, yas_grubu, cinsiyet
    fis                  fis_id, tarih, saat, magaza_id, musteri_id (anonimde
                         boş), kanal, fis_tipi, adet, tutar, teslim_tarihi
    fis_satir            fis_satir_id, fis_id, satir_no, urun_id, adet,
                         birim_fiyat, tutar, indirim_tutari, kampanya_id,
                         orijinal_fis_satir_id
    online_liste_gunluk  tarih, liste, sira, option_id, gosterim, tiklama,
                         sepete_ekleme, satin_alma
    online_olay          oturum_id, musteri_id, zaman, olay_tipi, liste, sira,
                         option_id, fis_id
    yorum                yorum_id, fis_satir_id, musteri_id, urun_id, tarih,
                         puan, metin

**Pencere.** Fiş ve satırları fiş günü 2023-01-01 – 2025-12-31 içindekiler;
ısınmadaki fişler yayımlanmaz. Penceredeki bir iadenin orijinal satışı
ısınmadaysa `orijinal_fis_satir_id` boştur (ilk ~10 gün). Olay kaydı
2025-09-01 – 2025-11-30 (`online_uret`), liste özeti bütün pencere.

**Tutarlılık sözleşmesi.** `fis_satir` (tarih, mağaza, SKU) toplamı A'nın
temiz `satis`'ini (iadeler dahil) adet, tutar ve indirim_tutari olarak
kuruşu kuruşuna verir. İade satırlarında adet, tutar ve indirim negatiftir
(A gibi); `birim_fiyat` = |tutar| / |adet| (2 ondalık, ödenen net birim
fiyat; tutar esastır, adet × birim_fiyat kuruş farkı verebilir).

**Belgelenecek durumlar** (README Görev 16):

- İade fişi kapanmış mağazada görünebilir: A kapanıştan önceki satışın
  iadesini mağazanın hücresine yazar, B orijinal mağazada iade fişi keser
  (A'nın yayımlanan satış satırlarıyla tutarlı).
- Terk eden müşterinin terkten önceki alışverişinin iadesi terk gününden
  sonra gelebilir; iade o müşteride kalır.
- `musteri.kayit_tarihi` / `kayit_kanali` (son inceleme): simülasyonda
  katılan müşteride ilk kimlikli fişin günü (`gorunur_gun`) ve o fişin
  kanalı (aynı gün birden çok kimlikli fişte saatçe ilki); CRM'in "üye
  oldu" anı budur. Başlangıç tabanı (ısınma öncesi geçmişli, katılış günü
  < 0) ısınma öncesi kıdem tarihini ve kanalını korur. Gizli
  `musteri_gizli` popülasyona katılış gününü ve kanalını taşır.
- `musteri` yalnız kimlikli (kart okutmuş ya da online sipariş vermiş)
  müşterileri taşır: ilk kimlikli olayı pencere sonuna kadar olanlar
  (ısınmada görünür olup pencereden önce terk edenler dahil; müşteri
  kaydı durur). Hiç fişi olmayan (boş ziyaret için eklenen yedek)
  müşteriler hiç görünür olmadığından tabloda yoktur.
- `fis.teslim_tarihi` yalnız online satış fişinde: B'nin kargo süresi
  (Görev 8); teslimi pencere sonrasına kalanın boştur (A'nın
  `gerceklesen_teslim` kuralı). Gecikme bayrağı gizlidir.
- `online_liste_gunluk`'te listede olmayan satın alınan option `arama:<alt>`
  listesinin 1. sırasına eklenir: aynı (tarih, liste, sıra 1)'de iki option
  olabilir, anahtar (tarih, liste, sira, option_id).

**Kimlikler.** Müşteri `K0000001…` (görünür müşteriler, nüfus sırasıyla),
fiş `F00000001…` (tarih, saat sırasıyla), satır `FS000000001…` (fiş, satır
sırasıyla), yorum `Y0000001…` (tarih, satır sırasıyla). Kimlik sütunları
`string[pyarrow]`, düşük kardinaliteli sütunlar `category` (A'nın kimlik
kümeleri, sözlük sırasıyla), tarihler `datetime64[ns]`.

`crm_gizli_gercek(...)` yayımlanmayan doğru (yazılmaz): müşteri tipi ve
parametreleri, anonim fişlerin sahibi, boş ziyaretler, terk, 2026 LTV,
tıklama modeli, yorum etiketleri, kargo gecikmesi, fiş satırı gizli
alanları. Gizli tablolarda `musteri` nüfus indisidir (her müşteri);
`musteri_id` yayımlanan kimlik ya da boş (hiç görünür olmamış).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from ..tablolar import _gun_tarihi, pencere
from . import sabitler as S
from .kargo import kargo_tablosu

TABLOLAR = ("musteri", "fis", "fis_satir", "online_liste_gunluk", "online_olay", "yorum")
GIZLI_TABLOLAR = (
    "musteri_gizli", "anonim_fis_sahibi", "bos_ziyaret", "terk", "ltv_2026", "tiklama_modeli",
    "yorum_etiket", "kargo_gecikme", "fis_satir_gizli",
)

# (önek, rakam sayısı)
MUSTERI_KIMLIK = ("K", 7)
FIS_KIMLIK = ("F", 8)
SATIR_KIMLIK = ("FS", 9)
YORUM_KIMLIK = ("Y", 7)

KANALLAR = ["magaza", "online"]
FIS_TIPLERI = ["satis", "iade"]
SAATLER = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(60)]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def kimlik_dizisi(kimlik: tuple[str, int], no: np.ndarray) -> pd.arrays.ArrowStringArray:
    """0 tabanlı sıra no → `önek + (no + 1)` sıfır dolgulu; no < 0 → boş."""
    onek, genislik = kimlik
    no = np.asarray(no, dtype=np.int64)
    assert not len(no) or no.max() + 1 < 10**genislik, f"{onek}: {genislik} hane yetmiyor"
    s = pc.utf8_lpad(pc.cast(pa.array(no + 1, mask=no < 0), pa.string()), genislik, "0")
    s = pc.binary_join_element_wise(pa.scalar(onek), s, pa.scalar(""))
    return pd.arrays.ArrowStringArray(s)


def _al(dizi: pd.arrays.ArrowStringArray, indis: np.ndarray) -> pd.arrays.ArrowStringArray:
    """`dizi[indis]`, indis < 0 → boş (Arrow `take`, kopyasız sözlük yok)."""
    indis = np.asarray(indis, dtype=np.int64)
    s = pc.take(pa.array(dizi), pa.array(indis, mask=indis < 0))
    return pd.arrays.ArrowStringArray(s)


def _kategori(kodlar: np.ndarray, kategoriler) -> pd.Categorical:
    return pd.Categorical.from_codes(np.asarray(kodlar, dtype=np.int64), categories=list(kategoriler))


class _Boyut:
    """A'nın kimlik kümeleri (sözlük sıralı kategori; indis → kod)."""

    def __init__(self, dunya):
        def kur(idler):
            idler = np.asarray(idler).astype(str)
            kat = pd.Index(sorted(idler))
            return kat, kat.get_indexer(idler)

        self.magaza_kat, self.magaza_kod = kur(dunya.magazalar["magaza_id"])
        self.urun_kat, self.urun_kod = kur(dunya.urunler["urun_id"])
        self.option_kat, self.option_kod = kur(dunya.optionlar["option_id"])
        self.kampanya_kat = pd.Index(dunya.kampanya["kampanya_id"].astype(str))
        self.urun_id = dunya.urunler["urun_id"].to_numpy().astype(str)

    def magaza(self, m):
        return _kategori(self.magaza_kod[np.asarray(m, dtype=np.int64)], self.magaza_kat)

    def urun(self, s):
        return _kategori(self.urun_kod[np.asarray(s, dtype=np.int64)], self.urun_kat)

    def option(self, o):
        o = np.asarray(o, dtype=np.int64)
        return _kategori(np.where(o >= 0, self.option_kod[np.maximum(o, 0)], -1), self.option_kat)

    def kampanya(self, k):
        return _kategori(k, self.kampanya_kat)


# ---------------------------------------------------------------------------
# Ortak hazırlık (kimlik eşlemeleri; iki fonksiyonun paylaştığı büyük tablolar)
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class CrmHazir:
    """`crm_tablolari` ve `crm_gizli_gercek`'in ortak girdisi.

    fis, satir   `crm_ham.tablo("fis")` / `("fis_satir")` (bütün kayıt)
    kargo        `kargo_tablosu` (ONL satış fişleri; bir kez hesaplanır)
    fis_sira     yayımlanan fişlerin iç fis_id'leri, yayım sırasıyla
    fis_no       [iç fiş] yayım sırası, −1 yayımlanmaz
    satir_sira   yayımlanan satırların iç satir_id'leri, yayım sırasıyla
    satir_no     [iç satır] yayım sırası, −1 yayımlanmaz
    musteri_no   [K] `musteri` sırası, −1 yayımlanmaz
    musteri_id   [K] K… kimliği ya da boş
    """

    fis: pd.DataFrame
    satir: pd.DataFrame
    kargo: pd.DataFrame
    fis_sira: np.ndarray
    fis_no: np.ndarray
    satir_sira: np.ndarray
    satir_no: np.ndarray
    musteri_no: np.ndarray
    musteri_id: pd.arrays.ArrowStringArray
    boyut: _Boyut


def hazirla(girdi, crm_ham, kargo: pd.DataFrame | None = None) -> CrmHazir:
    bas, son = pencere()
    fis = crm_ham.tablo("fis")
    satir = crm_ham.tablo("fis_satir")
    assert (satir["satir_id"].to_numpy() == np.arange(len(satir))).all()
    if kargo is None:
        kargo = kargo_tablosu(crm_ham, girdi)

    gun = fis["gun"].to_numpy(dtype=np.int64)
    ic = np.flatnonzero((gun >= bas) & (gun <= son))
    fis_sira = ic[np.lexsort((ic, fis["saat"].to_numpy()[ic], gun[ic]))]
    fis_no = np.full(len(fis), -1, dtype=np.int64)
    fis_no[fis_sira] = np.arange(len(fis_sira))

    s_fis = fis_no[satir["fis_id"].to_numpy()]
    ic = np.flatnonzero(s_fis >= 0)
    satir_sira = ic[np.lexsort((satir["satir_no"].to_numpy()[ic], s_fis[ic]))]
    satir_no = np.full(len(satir), -1, dtype=np.int64)
    satir_no[satir_sira] = np.arange(len(satir_sira))

    n = crm_ham.nufus
    gor = n.gorunur_mu & (n.gorunur_gun <= son)
    musteri_no = np.where(gor, np.cumsum(gor) - 1, -1).astype(np.int64)
    return CrmHazir(fis=fis, satir=satir, kargo=kargo, fis_sira=fis_sira, fis_no=fis_no,
                    satir_sira=satir_sira, satir_no=satir_no, musteri_no=musteri_no,
                    musteri_id=kimlik_dizisi(MUSTERI_KIMLIK, musteri_no), boyut=_Boyut(girdi.dunya))


def _yorum_ciftini_ac(yorumlar):
    """(yorum_df, gizli_df) ya da `yorum.YorumSonucu`."""
    if hasattr(yorumlar, "yorum"):
        return yorumlar.yorum, yorumlar.gizli
    return yorumlar


# ---------------------------------------------------------------------------
# Yayımlanan tablolar
# ---------------------------------------------------------------------------


def ilk_kimlikli_fis(fis: pd.DataFrame, K: int) -> tuple[np.ndarray, np.ndarray]:
    """[K] müşterinin ilk kimlikli (`kart`) fişinin günü ve kanalı (0 mağaza,
    1 online); (gün, saat, fis_id) sırasıyla ilki. Kimlikli fişi yoksa −1."""
    kart = fis["kart"].to_numpy()
    mus = fis["musteri"].to_numpy()[kart].astype(np.int64)
    gun = fis["gun"].to_numpy()[kart].astype(np.int64)
    o = np.lexsort((fis["fis_id"].to_numpy()[kart], fis["saat"].to_numpy()[kart], gun, mus))
    ilk = o[np.r_[True, mus[o][1:] != mus[o][:-1]]] if len(o) else o
    g = np.full(K, -1, dtype=np.int64)
    kanal = np.full(K, -1, dtype=np.int64)
    g[mus[ilk]] = gun[ilk]
    kanal[mus[ilk]] = fis["kanal"].to_numpy()[kart][ilk]
    return g, kanal


def _musteri(crm_ham, h: CrmHazir) -> pd.DataFrame:
    n = crm_ham.nufus
    k = np.flatnonzero(h.musteri_no >= 0)
    ilk_gun, ilk_kanal = ilk_kimlikli_fis(h.fis, n.K)
    taban = n.kayit_gun[k] < 0                   # başlangıç tabanı: eski anlam
    assert (ilk_gun[k] >= 0).all(), "yayımlanan müşterinin kimlikli fişi olmalı"
    assert (ilk_gun[k] == n.gorunur_gun[k]).all()
    kayit_gun = np.where(taban, n.kayit_gun[k], ilk_gun[k])
    kayit_kanal = np.where(taban, n.kayit_kanali[k], ilk_kanal[k])
    return pd.DataFrame({
        "musteri_id": _al(h.musteri_id, k),
        "kayit_tarihi": _gun_tarihi(kayit_gun),
        "kayit_kanali": _kategori(kayit_kanal, S.KAYIT_KANALLARI),
        "ev_magaza_id": h.boyut.magaza(n.ev_magaza[k]),
        "il": _kategori(n.il[k], n.il_adlari),
        "yas_grubu": _kategori(n.yas_grubu[k], S.YAS_GRUPLARI),
        "cinsiyet": _kategori(n.cinsiyet[k], S.CINSIYETLER),
    })


def _fis(crm_ham, h: CrmHazir) -> pd.DataFrame:
    _, son = pencere()
    f = h.fis
    i = h.fis_sira
    s_fis = h.satir["fis_id"].to_numpy()
    yay = h.satir_no >= 0
    adet = np.bincount(s_fis[yay], h.satir["adet"].to_numpy()[yay].astype(np.float64), minlength=len(f))
    tutar = np.bincount(s_fis[yay], h.satir["tutar"].to_numpy()[yay], minlength=len(f))
    musteri = np.where(f["kart"].to_numpy()[i], f["musteri"].to_numpy()[i], -1)

    teslim = np.full(len(f), np.iinfo(np.int64).max, dtype=np.int64)
    kf = h.kargo["fis_id"].to_numpy()
    teslim[kf] = f["gun"].to_numpy(dtype=np.int64)[kf] + h.kargo["teslim_gun"].to_numpy()   # süre (gün)
    t = teslim[i]
    teslim_tarihi = np.where(t <= son, _gun_tarihi(np.minimum(t, son)), np.datetime64("NaT", "ns"))
    return pd.DataFrame({
        "fis_id": kimlik_dizisi(FIS_KIMLIK, np.arange(len(i))),
        "tarih": _gun_tarihi(f["gun"].to_numpy()[i]),
        "saat": _kategori(f["saat"].to_numpy()[i], SAATLER),
        "magaza_id": h.boyut.magaza(f["magaza"].to_numpy()[i]),
        "musteri_id": _al(h.musteri_id, musteri),
        "kanal": _kategori(f["kanal"].to_numpy()[i], KANALLAR),
        "fis_tipi": _kategori(f["tip"].to_numpy()[i], FIS_TIPLERI),
        "adet": adet[i].astype(np.int32),
        "tutar": tutar[i].round(2),
        "teslim_tarihi": teslim_tarihi,
    })


def _fis_satir(h: CrmHazir) -> pd.DataFrame:
    s = h.satir
    j = h.satir_sira
    adet = s["adet"].to_numpy()[j].astype(np.int32)
    tutar = s["tutar"].to_numpy()[j].round(2)
    orj = s["orijinal_satir"].to_numpy()[j]
    orj_no = np.where(orj >= 0, h.satir_no[np.maximum(orj, 0)], -1)
    return pd.DataFrame({
        "fis_satir_id": kimlik_dizisi(SATIR_KIMLIK, np.arange(len(j))),
        "fis_id": kimlik_dizisi(FIS_KIMLIK, h.fis_no[s["fis_id"].to_numpy()[j]]),
        "satir_no": s["satir_no"].to_numpy()[j].astype(np.int16),
        "urun_id": h.boyut.urun(s["sku"].to_numpy()[j]),
        "adet": adet,
        "birim_fiyat": (np.abs(tutar) / np.abs(adet)).round(2),
        "tutar": tutar,
        "indirim_tutari": s["indirim_tutari"].to_numpy()[j].round(2),
        "kampanya_id": h.boyut.kampanya(s["kampanya_id"].to_numpy()[j]),
        "orijinal_fis_satir_id": kimlik_dizisi(SATIR_KIMLIK, orj_no),
    })


def _liste_gunluk(online, h: CrmHazir) -> pd.DataFrame:
    g = online.gunluk
    return pd.DataFrame({
        "tarih": _gun_tarihi(g["gun"].to_numpy()),
        "liste": g["liste"].array,
        "sira": g["sira"].to_numpy().astype(np.int16),
        "option_id": h.boyut.option(g["option"].to_numpy()),
        "gosterim": g["gosterim"].to_numpy().astype(np.int32),
        "tiklama": g["tiklama"].to_numpy().astype(np.int32),
        "sepete_ekleme": g["sepete_ekleme"].to_numpy().astype(np.int32),
        "satin_alma": g["satin_alma"].to_numpy().astype(np.int32),
    })


def _olay(online, h: CrmHazir) -> pd.DataFrame:
    o = online.olay
    fis = o["fis_id"].to_numpy()
    fis_no = np.where(fis >= 0, h.fis_no[np.maximum(fis, 0)], -1)
    assert (fis_no[fis >= 0] >= 0).all(), "sipariş olayının fişi pencerede olmalı"
    mus = o["musteri"].to_numpy()
    mus_no = np.where(mus >= 0, h.musteri_no[np.maximum(mus, 0)], -1)
    assert (mus_no[mus >= 0] >= 0).all(), "olaydaki müşteri görünür olmalı"
    sira = o["sira"].to_numpy()
    return pd.DataFrame({
        "oturum_id": o["oturum_id"].to_numpy().astype(np.int64),
        "musteri_id": _al(h.musteri_id, mus),
        "zaman": o["zaman"].to_numpy(),
        "olay_tipi": o["olay_tipi"].array,
        "liste": o["liste"].array,
        "sira": pd.arrays.IntegerArray(sira.astype(np.int16), sira < 0),
        "option_id": h.boyut.option(o["option"].to_numpy()),
        "fis_id": kimlik_dizisi(FIS_KIMLIK, fis_no),
    }, copy=False)


def _yorum(yorum_df: pd.DataFrame, h: CrmHazir) -> pd.DataFrame:
    y = yorum_df
    satir = y["fis_satir_id"].to_numpy()
    satir_no = h.satir_no[satir]
    assert (satir_no >= 0).all(), "yorumun satırı yayımlanmalı"
    mus = y["musteri_id"].to_numpy()
    assert (h.musteri_no[mus] >= 0).all(), "yorum yazan görünür olmalı"
    urun = pd.Index(h.boyut.urun_id).get_indexer(y["urun_id"].to_numpy().astype(str))
    assert (urun == h.satir["sku"].to_numpy()[satir]).all()
    return pd.DataFrame({
        "yorum_id": kimlik_dizisi(YORUM_KIMLIK, y["yorum_id"].to_numpy()),
        "fis_satir_id": kimlik_dizisi(SATIR_KIMLIK, satir_no),
        "musteri_id": _al(h.musteri_id, mus),
        "urun_id": h.boyut.urun(urun),
        "tarih": y["tarih"].to_numpy().astype("datetime64[ns]"),
        "puan": y["puan"].to_numpy().astype(np.int8),
        "metin": pd.array(y["metin"].to_numpy().astype(str), dtype="string[pyarrow]"),
    })


def crm_tablolari(girdi, crm_ham, online, yorumlar, kargo: pd.DataFrame | None = None,
                  hazir: CrmHazir | None = None) -> dict[str, pd.DataFrame]:
    """Spec §7'nin altı tablosu (modül docstring'i). `online` `online_uret`
    çıktısı, `yorumlar` (yorum_df, gizli_df) ya da `YorumSonucu`; `kargo`
    ya da `hazir` verilirse yeniden hesaplanmaz."""
    h = hazir or hazirla(girdi, crm_ham, kargo)
    yorum_df, _ = _yorum_ciftini_ac(yorumlar)
    return {
        "musteri": _musteri(crm_ham, h),
        "fis": _fis(crm_ham, h),
        "fis_satir": _fis_satir(h),
        "online_liste_gunluk": _liste_gunluk(online, h),
        "online_olay": _olay(online, h),
        "yorum": _yorum(yorum_df, h),
    }


# ---------------------------------------------------------------------------
# Gizli gerçek
# ---------------------------------------------------------------------------


def _musteri_gizli(crm_ham, h: CrmHazir) -> pd.DataFrame:
    n, t = crm_ham.nufus, crm_ham.tetik
    t.uzat(n.K)
    K = n.K
    df = {
        "musteri": np.arange(K, dtype=np.int64),
        "musteri_id": h.musteri_id,
        "arketip": _kategori(n.arketip, S.ARKETIPLER),
        "ev_magaza_id": h.boyut.magaza(n.ev_magaza),
        "il": _kategori(n.il, n.il_adlari),
        "yas_grubu": _kategori(n.yas_grubu, S.YAS_GRUPLARI),
        "cinsiyet": _kategori(n.cinsiyet, S.CINSIYETLER),
        "kayit_tarihi": _gun_tarihi(n.kayit_gun),
        "kayit_kanali": _kategori(n.kayit_kanali, S.KAYIT_KANALLARI),
    }
    for c in ("kart_olasiligi", "ziyaret_hizi", "sepet_ort", "online_payi", "terk_p", "indirim_duyarlilik",
              "beden_ust", "beden_alt", "beden_dagin"):
        df[c] = getattr(n, c).copy()
    for c, eksen in (("tercih_kat", S.ALT_KATEGORILER), ("tercih_kalip", S.KALIPLAR),
                     ("tercih_desen", S.DESENLER), ("fiyat_segment_egilim", S.FIYAT_SEGMENTLERI)):
        m = getattr(n, c)
        for j, ad in enumerate(eksen):
            df[f"{c}_{ad}"] = m[:, j].copy()
    df["hayatta"] = n.hayatta.copy()
    df["terk_tarihi"] = np.where(n.terk_gun >= 0, _gun_tarihi(np.maximum(n.terk_gun, 0)),
                                 np.datetime64("NaT", "ns"))
    df["gorunur_mu"] = n.gorunur_mu.copy()
    df["gorunur_tarihi"] = np.where(n.gorunur_gun >= 0, _gun_tarihi(np.maximum(n.gorunur_gun, 0)),
                                    np.datetime64("NaT", "ns"))
    for c in t.SUTUNLAR:
        df[f"tetik_{c}"] = getattr(t, c).copy()
    df["fiyat_ort"] = np.asarray(crm_ham.fiyat_ort, dtype=np.float64)
    return pd.DataFrame(df)


def _tiklama_modeli(online, h: CrmHazir) -> dict:
    g = online.gizli
    b = h.boyut
    out = {}
    for ad, v in g.items():
        if not isinstance(v, pd.DataFrame):
            out[ad] = v
            continue
        v = v.copy()
        if "option" in v:
            v.insert(list(v.columns).index("option"), "option_id", b.option(v.pop("option").to_numpy()))
        for gun_ad, tarih_ad in (("gun", "tarih"), ("adim_gun", "adim_tarihi")):
            if gun_ad in v:
                v.insert(list(v.columns).index(gun_ad), tarih_ad, _gun_tarihi(v.pop(gun_ad).to_numpy()))
        out[ad] = v
    return out


def crm_gizli_gercek(girdi, crm_ham, online, yorumlar, kargo: pd.DataFrame | None = None,
                     hazir: CrmHazir | None = None) -> dict:
    """Yayımlanmayan doğru (modül docstring'i); `uret.main` yazmaz.

    musteri_gizli      her müşteri (nüfus satırı): arketip, bütün gizli
                       parametreler ve tercih vektörleri (geniş), hayatta,
                       terk/görünür tarihi, tetik durumu, fiyat_ort
    anonim_fis_sahibi  fis_id (anonim yayımlanan fiş), musteri, musteri_id
                       (sahip görünürse)
    bos_ziyaret        tarih, magaza_id, musteri, musteri_id, urun_id, adet
                       (pencere; stoksuzluk yüzünden alınamayan birimler)
    terk               musteri, musteri_id, terk_tarihi (bütün koşu)
    ltv_2026           `yasam.ltv_2026` + musteri_id
    tiklama_modeli     sözlük: bakılma eğrisi, option × arketip ilgisi,
                       günlük ilgi, arketip ağırlığı, enjekte hücreler,
                       tıklama sabiti ve parametreler
    yorum_etiket       yorum_id + kütüphane kimliği, konular, duygu,
                       nedenler, üslup, gevşeme basamağı
    kargo_gecikme      fis_id, teslim_tarihi (kesilmemiş), teslim_suresi
                       (gün), gecikme
    fis_satir_gizli    fis_satir_id, beden_uyumsuz_adet, islem_adet
                       (yalnız ikisinden biri sıfır olmayan satırlar)
    """
    h = hazir or hazirla(girdi, crm_ham, kargo)
    bas, son = pencere()
    _, yorum_gizli = _yorum_ciftini_ac(yorumlar)
    b = h.boyut

    f = h.fis
    i = h.fis_sira
    anonim = ~f["kart"].to_numpy()[i]
    sahip = f["musteri"].to_numpy()[i][anonim]
    anonim_fis = pd.DataFrame({
        "fis_id": kimlik_dizisi(FIS_KIMLIK, np.flatnonzero(anonim)),
        "musteri": sahip.astype(np.int64),
        "musteri_id": _al(h.musteri_id, sahip),
    })

    bz = crm_ham.tablo("bos_ziyaret")
    g = bz["gun"].to_numpy(dtype=np.int64)
    bz = bz[(g >= bas) & (g <= son)]
    bz_m = bz["musteri"].to_numpy(dtype=np.int64)
    bos = pd.DataFrame({
        "tarih": _gun_tarihi(bz["gun"].to_numpy()),
        "magaza_id": b.magaza(bz["magaza"].to_numpy()),
        "musteri": bz_m,
        "musteri_id": _al(h.musteri_id, bz_m),
        "urun_id": b.urun(bz["sku"].to_numpy()),
        "adet": bz["adet"].to_numpy().astype(np.int32),
    })

    n = crm_ham.nufus
    tk = np.flatnonzero(n.terk_gun >= 0)
    terk = pd.DataFrame({
        "musteri": tk.astype(np.int64),
        "musteri_id": _al(h.musteri_id, tk),
        "terk_tarihi": _gun_tarihi(n.terk_gun[tk]),
    })

    ltv = crm_ham.ltv.rename(columns={"musteri_id": "musteri"}).copy()
    ltv.insert(1, "musteri_id", _al(h.musteri_id, ltv["musteri"].to_numpy()))

    ye = yorum_gizli.copy()
    ye["yorum_id"] = kimlik_dizisi(YORUM_KIMLIK, ye["yorum_id"].to_numpy())

    k = h.kargo
    k_no = h.fis_no[k["fis_id"].to_numpy()]
    ks = np.flatnonzero(k_no >= 0)
    ks = ks[np.argsort(k_no[ks], kind="stable")]
    kargo_g = pd.DataFrame({
        "fis_id": kimlik_dizisi(FIS_KIMLIK, k_no[ks]),
        "teslim_tarihi": _gun_tarihi(h.fis["gun"].to_numpy(dtype=np.int64)[k["fis_id"].to_numpy()[ks]]
                                     + k["teslim_gun"].to_numpy()[ks]),
        "teslim_suresi": k["teslim_gun"].to_numpy()[ks].astype(np.int16),
        "gecikme": k["gecikme"].to_numpy()[ks].astype(bool),
    })

    s = h.satir
    j = h.satir_sira
    bu = s["beden_uyumsuz_adet"].to_numpy()[j]
    ia = s["islem_adet"].to_numpy()[j]
    dolu = np.flatnonzero((bu != 0) | (ia != 0))
    satir_g = pd.DataFrame({
        "fis_satir_id": kimlik_dizisi(SATIR_KIMLIK, dolu),
        "beden_uyumsuz_adet": bu[dolu].astype(np.int16),
        "islem_adet": ia[dolu].astype(np.int16),
    })

    return {
        "musteri_gizli": _musteri_gizli(crm_ham, h),
        "anonim_fis_sahibi": anonim_fis,
        "bos_ziyaret": bos,
        "terk": terk,
        "ltv_2026": ltv,
        "tiklama_modeli": _tiklama_modeli(online, h),
        "yorum_etiket": ye,
        "kargo_gecikme": kargo_g,
        "fis_satir_gizli": satir_g,
    }
