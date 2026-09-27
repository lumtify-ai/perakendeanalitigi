"""Lumoda'nın bugünkü kararları — v4 motorunun varsayılan politikaları.

Dokuz politika vardır (spec §6.2) ve hepsi enjekte edilebilir
(`Politikalar`); arayüz ve günlük sıra için `motor.dongu`'nun belgesine
bakın. Her politika yalnız `Gorunum`'u okur (kamuya açık alanlar, bkz.
`motor.durum.Gorunum`); gizli gerçeğe (gerçek λ, esneklik, tedarikçi
profili, segment) bakmaz.

    ilk_dagitim(g, o)   -> [M] paket sayısı          (Görev 12, Lumoda)
    paket_secimi(g, o)  -> [M] paket indisi          (Görev 12, Lumoda)
    replenishment(g)    -> [C] depodan istenen adet  (Görev 12, Lumoda)
    rpt(g)              -> {option: adet}            (Görev 13; şimdilik boş)
    markdown(g)         -> [O, 3] indirim oranı      (Görev 13; şimdilik değişmez)
    acilis(g, m)        -> Transferler               (Görev 14; şimdilik boş)
    kapanis(g, m)       -> Transferler               (Görev 14; şimdilik boş)
    elle_transfer(g)    -> Transferler               (Görev 14; şimdilik boş)
    outlet_akisi(g, os) -> Transferler               (Görev 13; şimdilik boş)

Tedarikçi seçimi burada değildir: `dunya_kur(tedarikci_secimi=…)`
parametresidir (sipariş dünyada önceden kurulur).

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3 `mevcut_dagitim` kuralı
kopyalanmıştır).
"""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import sabitler
from .plan import en_buyuk_kalan


# ---------------------------------------------------------------------------
# Transferler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transferler:
    """Mal hareketi istekleri, satır başına: `kaynak` → `hedef` (mağaza
    satır indisi; −1 = depo), `sku`, `adet`. Motor kaynağın stoğuyla
    sınırlar, hedefte hücre yoksa satırı atar, yolda süreyi uygular."""

    kaynak: np.ndarray
    hedef: np.ndarray
    sku: np.ndarray
    adet: np.ndarray

    @staticmethod
    def bos() -> "Transferler":
        z = np.zeros(0, dtype=np.int64)
        return Transferler(z, z, z, z)


# ---------------------------------------------------------------------------
# Paket tablosu
# ---------------------------------------------------------------------------


def paket_tablosu(paketler: pd.DataFrame) -> tuple[np.ndarray, dict[str, int], np.ndarray]:
    """(`paket_idleri` [P], beden seti → standart paket indisi,
    `icerik` [P, K]: paket indisi × beden_sira → adet).

    Paket indisi `paket_idleri` sırasıdır (ilk görülme; `sevkiyat.paket_id`
    bu indisi taşır, −1 = paketsiz). `icerik[p, beden_sira]`; paketin
    taşımadığı beden 0."""
    ids = paketler["paket_id"].drop_duplicates().to_numpy()
    idx = {p: i for i, p in enumerate(ids)}
    K = int(paketler["beden_sira"].max()) + 1
    icerik = np.zeros((len(ids), K), dtype=np.int64)
    p = paketler["paket_id"].map(idx).to_numpy()
    icerik[p, paketler["beden_sira"].to_numpy()] = paketler["adet"].to_numpy()
    set_idx = {}
    for bs, pid in zip(paketler["beden_seti"], paketler["paket_id"]):
        set_idx.setdefault(bs, idx[pid])
    return ids, set_idx, icerik


# ---------------------------------------------------------------------------
# Lumoda: ilk dağıtım, paket, replenishment
# ---------------------------------------------------------------------------


def _option_magazalari(w, o: int) -> np.ndarray:
    """[M] bool: option'ın ilk dağıtım alabilecek hücresi olan mağazalar
    (fiziksel, outlet akışı olmayan hücre)."""
    maske = (w.hucre_option == o) & ~w.hucre_online & ~w.hucre_outlet_akisi
    sonuc = np.zeros(len(w.magazalar), dtype=bool)
    sonuc[w.hucre_magaza[maske]] = True
    return sonuc


def lumoda_paket_secimi(g, o: int) -> np.ndarray:
    """[M] paket indisi: her mağazaya option'ın beden setinin tek standart
    paketi (Lumoda'da set başına bir paket)."""
    w = g.dunya
    _, set_idx, _ = paket_tablosu(w.paketler)
    return np.full(len(w.magazalar), set_idx[w.optionlar.at[o, "beden_seti"]], dtype=np.int64)


def lumoda_ilk_dagitim(g, o: int) -> np.ndarray:
    """[M] paket sayısı.

    Toplam paket = ⌊ilk alım × ILK_DAGITIM_PAYI ÷ paket adedi⌋; mağazalara
    `magaza_plan`'daki (option'ın sezonu × üst kategorisi) satış hedefi
    payıyla, en büyük kalanla bölünür. Aday mağaza: option'ın fiziksel,
    outlet akışı olmayan hücresi var; kapanış kararı verilmemiş; bugün açık
    ya da lansmana kadar açılacak (yayımlanan `acilis_tarihi`) ve lansmandan
    önce kapanmıyor. Kalan ilk alım depoda kalır (online + replenishment).
    """
    w = g.dunya
    opt = w.optionlar
    mag = w.magazalar
    lansman_t = opt.at[o, "lansman_tarihi"]
    aday = _option_magazalari(w, o) & ~np.asarray(g.kapanacak)
    acilis_t = pd.to_datetime(mag["acilis_tarihi"])
    kapanis_t = pd.to_datetime(mag["kapanis_tarihi"])
    aday &= np.asarray(g.acik_magaza) | (acilis_t <= lansman_t).to_numpy()
    aday &= ~(kapanis_t.notna() & (kapanis_t <= lansman_t)).to_numpy()
    if not aday.any():
        return np.zeros(len(mag), dtype=np.int64)

    mp = w.plan_tablolari["magaza_plan"]
    sec = mp[(mp.sezon_kodu == opt.at[o, "sezon_kodu"]) & (mp.ust_kategori == opt.at[o, "ust_kategori"])]
    hedef = (
        sec.set_index("magaza_id")["satis_hedefi"]
        .reindex(mag["magaza_id"]).fillna(0).to_numpy(dtype=float)
    )
    pay = np.where(aday, hedef, 0.0)
    if pay.sum() <= 0:
        pay = aday.astype(float)

    _, set_idx, icerik = paket_tablosu(w.paketler)
    paket_adedi = int(icerik[set_idx[opt.at[o, "beden_seti"]]].sum())
    toplam = int(w.ilk_alim[o] * sabitler.ILK_DAGITIM_PAYI // paket_adedi)
    return en_buyuk_kalan(toplam, pay)


def lumoda_replenishment(g) -> np.ndarray:
    """[C] haftalık replenishment isteği (v3 `mevcut_dagitim` kuralı).

    Hedef    önümüzdeki 28 günün PLAN talebi (sürprizi, yerel sapmayı
             bilmez; planlı indirimin talep artışını bilir)
    İstek    max(hedef − mağaza stoğu − yolda, 0) (v4: yoldaki mal sayılır)
    Kapı     hücre yeni değilse (option'ın ilk dağıtımından beri ≥ 28 gün)
             ve son 28 günlük satış hızıyla zaten 4 haftalık stoğu varsa mal
             gitmez — hız sıfırsa HİÇ gitmez (kasıtlı v3 kusuru).
    Sıfır    ONL hücreleri (online depodan satar), kapalı ve kapanış kararı
             verilmiş mağazalar.

    Depo yetmezse motor istekleri SKU içinde orantılı keser; dağıtılamaz
    hücreleri (ilk dağıtımı bitmemiş, çıkmış, outlet akışı) motor sıfırlar.
    """
    w = g.dunya
    hedef = np.rint(w.ileri_plan(g.gun, sabitler.REPL_HEDEF_GUN)).astype(np.int64)
    eksik = np.maximum(hedef - g.magaza_stok - g.yolda, 0)
    ilk_gun = g.ilk_dagitim_gun[w.hucre_option]
    yeni = (g.gun - ilk_gun) < sabitler.OLU_STOK_PENCERESI_GUN
    haftalik_hiz = g.satis_28 / sabitler.OLU_STOK_PENCERESI_GUN * 7.0
    uygun = yeni | (g.magaza_stok < haftalik_hiz * sabitler.OLU_STOK_HEDEF_HAFTA)
    magaza_uygun = np.asarray(g.acik_magaza) & ~np.asarray(g.kapanacak)
    uygun &= magaza_uygun[w.hucre_magaza] & ~w.hucre_online
    return np.where(uygun, eksik, 0)


# ---------------------------------------------------------------------------
# Yer tutucular (Görev 13–14 doldurur; imzalar sabit)
# ---------------------------------------------------------------------------


def lumoda_rpt(g) -> dict[int, int]:
    """Görev 13: Banu'nun RPT kuralı. Şimdilik sipariş yok."""
    return {}


def lumoda_markdown(g) -> np.ndarray:
    """Görev 13: STR'ye bağlı kademeli markdown, [O, 3] (normal / outlet /
    online hattı). Şimdilik değişiklik yok (güncel oranlar)."""
    return np.array(g.fiyat_orani, copy=True)


def lumoda_acilis(g, m: int) -> Transferler:
    """Görev 14: yeni mağazanın açılış transferi. Şimdilik boş."""
    return Transferler.bos()


def lumoda_kapanis(g, m: int) -> Transferler:
    """Görev 14: kapanan mağazanın stoğu. Şimdilik boş."""
    return Transferler.bos()


def lumoda_elle_transfer(g) -> Transferler:
    """Görev 14: bölge müdürünün haftalık elle transferleri. Şimdilik boş."""
    return Transferler.bos()


def lumoda_outlet_akisi(g, os: np.ndarray) -> Transferler:
    """Görev 13: sezon çıkışında kalan stok outlet mağazalarına ve depoya.
    `os` bugün çıkan option indisleri. Şimdilik boş."""
    return Transferler.bos()


def lumoda_politikalari() -> dict[str, Callable]:
    """Dokuz politikanın Lumoda karşılıkları (`Politikalar` alan sırası)."""
    return dict(_LUMODA)


_LUMODA: dict[str, Callable] = {
    "ilk_dagitim": lumoda_ilk_dagitim,
    "paket_secimi": lumoda_paket_secimi,
    "replenishment": lumoda_replenishment,
    "rpt": lumoda_rpt,
    "markdown": lumoda_markdown,
    "acilis": lumoda_acilis,
    "kapanis": lumoda_kapanis,
    "elle_transfer": lumoda_elle_transfer,
    "outlet_akisi": lumoda_outlet_akisi,
}


def _varsayilan(ad: str):
    return field(default_factory=lambda: _LUMODA[ad])


@dataclass
class Politikalar:
    """Motorun enjekte edilebilir kararları; her alan varsayılan olarak
    Lumoda'nın bugünkü pratiğidir. Vaka yalnız değiştirdiği alanı verir:
    `Politikalar(replenishment=benim_kuralim)`."""

    ilk_dagitim: Callable = _varsayilan("ilk_dagitim")
    paket_secimi: Callable = _varsayilan("paket_secimi")
    replenishment: Callable = _varsayilan("replenishment")
    rpt: Callable = _varsayilan("rpt")
    markdown: Callable = _varsayilan("markdown")
    acilis: Callable = _varsayilan("acilis")
    kapanis: Callable = _varsayilan("kapanis")
    elle_transfer: Callable = _varsayilan("elle_transfer")
    outlet_akisi: Callable = _varsayilan("outlet_akisi")
