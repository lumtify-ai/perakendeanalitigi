"""v4 çeşit: mağaza × option ataması, hücre tablosu, kanibalizasyon payı.

Hücre = mağaza × SKU (online dahil). Çeşit atama kuralları (controller
kararı, spec §5.3 ve brief'in "Kurallar" paragrafının netleştirilmiş hâli):

- ONL bütün option'ları normal pencereyle taşır, hiçbir zaman outlet
  akışıyla değil.
- Outlet (fiziksel) mağazalar: bütün Collection option'larını yalnız
  **outlet akışıyla** (`outlet_akisi=True`, pencere [çıkış, çıkış+84))
  taşır — sezon sonu taşma stoğu; Outlet line option'larını ise normal
  pencereyle (`outlet_akisi=False`) taşır. Basic/NOS hiç almaz.
- AVM/Cadde (fiziksel, outlet olmayan) mağazalar: Collection'dan sezon
  başına genişlik formülüyle seçilmiş bir alt küme (segment-öznitelik
  uyum ağırlıklı, iadesiz çekiliş) + NOS'un tamamı + Basic'in tamamı
  (m² ≥ 250) ya da rastgele %70'i (m² < 250) taşır; Outlet line hiç
  almaz.

Kanibalizasyon payı (spec §5.3): mağaza × alt kategori grubunda o gün
açık (çeşide atanmış VE pencere içinde) option sayısı n; toplam talep
n^β ile büyür, çekicilik paylarıyla bölünür. Stok durumu n'yi değiştirmez
(hücre tablosunun kendi açık/kapalı penceresi yeterli, motor stoğu ayrı
işler, bkz. §5.4 ikame) — bu yüzden çeşit + pencere sabitken önceden
hesaplanabilir; gün değiştikçe yalnız pencere sınırı geçilince yeniden
hesaplanır.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §5.3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-7-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz.
"""

from typing import Callable

import numpy as np
import pandas as pd

from .takvim import gun_indisi

# Gün indisi sentinel'i (urun.py'nin DEVAMLI kuralıyla aynı biçim): devamlı
# (Basic/NOS) option'ların "çıkışı" yoktur, pencereleri pratikte hiç kapanmaz.
_BUYUK = 10**6

# Outlet akışı: sezon çıkışından sonra taşma stoğunun outlet mağazalarda
# satıldığı pencere uzunluğu (gün).
OUTLET_AKISI_GUN = 84

# Sezon başına Collection genişliği: clip(0.15 + 0.55·(m² − 150)/1050, 0.15, 0.70)
_GENISLIK_TABAN = 0.15
_GENISLIK_MAKS = 0.70
_GENISLIK_M2_REFERANS = 150.0
_GENISLIK_M2_OLCEK = 1050.0

# m² < 250 mağazalarda Basic'in rastgele taşınan oranı.
_BASIC_KUCUK_MAGAZA_ORANI = 0.70
_BASIC_M2_ESIGI = 250

# Segment-öznitelik uyum ağırlıkları (gizli öznitelik etkisi DEĞİL; segmentin
# bilinen tercihi): fiyat segmenti ↔ gelir eşleşme tablosu.
_FIYAT_GELIR_AGIRLIGI: dict[str, dict[str, float]] = {
    "giris": {"dusuk": 1.4, "orta": 1.0, "yuksek": 0.6},
    "orta": {"dusuk": 1.0, "orta": 1.2, "yuksek": 1.0},
    "premium": {"dusuk": 0.5, "orta": 1.0, "yuksek": 1.5},
}

KANIBALIZASYON_BETA = 0.6


# ---------------------------------------------------------------------------
# cesit_ata
# ---------------------------------------------------------------------------


def _kadin_payi_agirligi(cinsiyet: np.ndarray, kadin_payi: float) -> np.ndarray:
    """Kadın → kadın payı; Erkek → 1 − kadın payı; Unisex → 0,5."""
    return np.select(
        [cinsiyet == "Kadın", cinsiyet == "Erkek"],
        [kadin_payi, 1.0 - kadin_payi],
        default=0.5,
    )


def _fiyat_gelir_agirligi(fiyat_segmenti: np.ndarray, gelir: str) -> np.ndarray:
    return np.array([_FIYAT_GELIR_AGIRLIGI[fs][gelir] for fs in fiyat_segmenti], dtype=float)


def _collection_genislik_orani(metrekare: float) -> float:
    ham = _GENISLIK_TABAN + 0.55 * (metrekare - _GENISLIK_M2_REFERANS) / _GENISLIK_M2_OLCEK
    return float(np.clip(ham, _GENISLIK_TABAN, _GENISLIK_MAKS))


def _collection_sec(
    rng: np.random.Generator,
    magaza_idx: int,
    m2: float,
    kadin_payi: float,
    gelir: str,
    collection_opt: pd.DataFrame,
) -> list[tuple[int, int]]:
    """Bir (outlet olmayan fiziksel) mağazanın Collection seçimi; sezon
    başına ayrı çekiliş (genişlik sezona özgüdür)."""
    satirlar: list[tuple[int, int]] = []
    for _, grp in collection_opt.groupby("sezon_kodu"):
        idxs = grp.index.to_numpy()
        n_sezon = len(idxs)
        if n_sezon == 0:
            continue
        genislik_orani = _collection_genislik_orani(m2)
        secim_n = int(round(genislik_orani * n_sezon))
        secim_n = min(max(secim_n, 0), n_sezon)
        if secim_n == 0:
            continue
        agirlik = _kadin_payi_agirligi(
            grp["cinsiyet"].to_numpy(), kadin_payi
        ) * _fiyat_gelir_agirligi(grp["fiyat_segmenti"].to_numpy(), gelir)
        toplam = agirlik.sum()
        if toplam <= 0:
            p = None
        else:
            p = agirlik / toplam
        secilen = rng.choice(idxs, size=secim_n, replace=False, p=p)
        satirlar.extend((magaza_idx, int(o)) for o in secilen)
    return satirlar


def cesit_ata(
    rng: np.random.Generator,
    magazalar: pd.DataFrame,
    gizli: pd.DataFrame,
    optionlar: pd.DataFrame,
) -> pd.DataFrame:
    """`cesit` (option düzeyi) tablosu: `magaza_idx`, `option_idx`,
    `outlet_akisi`. İndisler `magazalar`/`optionlar`'ın satır sırasıdır
    (bkz. yapı sözleşmesi: m, o)."""
    magazalar = magazalar.reset_index(drop=True)
    optionlar = optionlar.reset_index(drop=True)
    gizli_idx = gizli.set_index("magaza_id")

    onl_pozisyon = magazalar.index[magazalar["tip"] == "Online"].to_numpy()
    outlet_pozisyon = magazalar.index[magazalar["tip"] == "Outlet"].to_numpy()
    fiziksel_diger = magazalar.index[
        ~magazalar["tip"].isin(["Online", "Outlet"])
    ].to_numpy()

    n_opt = len(optionlar)
    collection_opt = optionlar[optionlar["line"] == "Collection"]
    outlet_line_opt_idx = optionlar.index[optionlar["line"] == "Outlet"].to_numpy()
    basic_opt_idx = optionlar.index[optionlar["line"] == "Basic"].to_numpy()
    nos_opt_idx = optionlar.index[optionlar["line"] == "NOS"].to_numpy()
    collection_opt_idx = collection_opt.index.to_numpy()

    magaza_idx_liste: list[int] = []
    option_idx_liste: list[int] = []
    outlet_akisi_liste: list[bool] = []

    def _ekle(magaza_idx: int, option_idxs, outlet_akisi: bool) -> None:
        option_idxs = np.asarray(option_idxs, dtype=int)
        if option_idxs.size == 0:
            return
        magaza_idx_liste.extend([magaza_idx] * len(option_idxs))
        option_idx_liste.extend(option_idxs.tolist())
        outlet_akisi_liste.extend([outlet_akisi] * len(option_idxs))

    # --- ONL: her şey, normal pencere, hiçbir zaman outlet akışı --------
    for m in onl_pozisyon:
        _ekle(int(m), np.arange(n_opt), False)

    # --- Outlet mağazalar: Collection (outlet akışı) + Outlet line (normal) ---
    for m in outlet_pozisyon:
        _ekle(int(m), collection_opt_idx, True)
        _ekle(int(m), outlet_line_opt_idx, False)

    # --- AVM/Cadde: Collection seçimi + Basic + NOS ----------------------
    for m in fiziksel_diger:
        magaza_id = magazalar.at[m, "magaza_id"]
        m2 = float(magazalar.at[m, "metrekare"])
        kadin_payi = float(gizli_idx.at[magaza_id, "kadin_payi"])
        gelir = str(gizli_idx.at[magaza_id, "gelir"])

        secim = _collection_sec(rng, int(m), m2, kadin_payi, gelir, collection_opt)
        if secim:
            _, opt_idxs = zip(*secim)
            _ekle(int(m), opt_idxs, False)

        _ekle(int(m), nos_opt_idx, False)

        if m2 >= _BASIC_M2_ESIGI:
            basic_secilen = basic_opt_idx
        else:
            maske = rng.random(len(basic_opt_idx)) < _BASIC_KUCUK_MAGAZA_ORANI
            basic_secilen = basic_opt_idx[maske]
        _ekle(int(m), basic_secilen, False)

    return pd.DataFrame(
        {
            "magaza_idx": np.asarray(magaza_idx_liste, dtype=int),
            "option_idx": np.asarray(option_idx_liste, dtype=int),
            "outlet_akisi": np.asarray(outlet_akisi_liste, dtype=bool),
        }
    )


# ---------------------------------------------------------------------------
# hucreleri_kur
# ---------------------------------------------------------------------------


def _gun_indisi_guvenli(tarih) -> int:
    """`gun_indisi`'nin NaT-güvenli hâli: NaT için büyük sentinel döner
    (devamlı — Basic/NOS — option'ların pratikte hiç kapanmayan penceresi)."""
    if pd.isna(tarih):
        return _BUYUK
    return gun_indisi(tarih)


def hucreleri_kur(cesit_opt: pd.DataFrame, urunler: pd.DataFrame) -> pd.DataFrame:
    """`cesit` (hücre düzeyi) tablosu: `magaza_idx`, `sku_idx`, `option_idx`,
    `outlet_akisi`, `acilis_gun`, `kapanis_gun`.

    `sku_idx` `urunler`'in satır sırasıdır. `option_idx`, `cesit_opt`'un
    üretildiği `optionlar`'ın satır sırasıyla aynıdır: `urunler` bu
    sıradaki option'ları sırayla, her birinin bütün SKU'larıyla art arda
    içerir (bkz. `urun._urunleri_kur`), bu yüzden `option_id`'nin `urunler`
    içindeki ilk görülme sırası `option_idx`'i doğru şekilde geri verir —
    `optionlar` tablosunun kendisi burada parametre olarak alınmaz.
    """
    urunler = urunler.reset_index(drop=True)

    option_ids_sirali = urunler["option_id"].drop_duplicates().to_numpy()
    option_idx_map = {oid: i for i, oid in enumerate(option_ids_sirali)}

    option_idx = urunler["option_id"].map(option_idx_map).to_numpy()
    sku_idx = np.arange(len(urunler))
    lansman_gun = urunler["lansman_tarihi"].apply(_gun_indisi_guvenli).to_numpy()
    cikis_gun = urunler["cikis_tarihi"].apply(_gun_indisi_guvenli).to_numpy()

    urun_tablosu = pd.DataFrame(
        {
            "option_idx": option_idx,
            "sku_idx": sku_idx,
            "_lansman_gun": lansman_gun,
            "_cikis_gun": cikis_gun,
        }
    )

    birlesik = cesit_opt.merge(urun_tablosu, on="option_idx", how="left")

    outlet_akisi = birlesik["outlet_akisi"].to_numpy()
    lansman = birlesik["_lansman_gun"].to_numpy()
    cikis = birlesik["_cikis_gun"].to_numpy()

    acilis_gun = np.where(outlet_akisi, cikis, lansman)
    kapanis_gun = np.where(outlet_akisi, cikis + OUTLET_AKISI_GUN, cikis)

    return pd.DataFrame(
        {
            "magaza_idx": birlesik["magaza_idx"].to_numpy(dtype=int),
            "sku_idx": birlesik["sku_idx"].to_numpy(dtype=int),
            "option_idx": birlesik["option_idx"].to_numpy(dtype=int),
            "outlet_akisi": outlet_akisi,
            "acilis_gun": acilis_gun.astype(int),
            "kapanis_gun": kapanis_gun.astype(int),
        }
    )


# ---------------------------------------------------------------------------
# kanibalizasyon_payi
# ---------------------------------------------------------------------------


def kanibalizasyon_payi(
    cesit_hucre: pd.DataFrame,
    optionlar: pd.DataFrame,
    cekicilik: np.ndarray,
    beta: float = KANIBALIZASYON_BETA,
) -> Callable[[int], np.ndarray]:
    """Gün `d` için hücre başına kanibalizasyon çarpanını veren kapanış.

    Grup = (mağaza, alt kategori); n = grupta gün `d`'de penceresi açık
    (`acilis_gun ≤ d < kapanis_gun`) **DİSTİNCT option** sayısı — aynı
    option'ın birden çok SKU hücresi bir kez sayılır, stok durumu hiç
    girmez. Çarpan = n^β / n × (option çekiciliği / grubun açık
    option'larının ortalama çekiciliği); pencere dışı hücreler 0 alır.

    Önbellek: yalnız pencere sınırlarından biri geçildiğinde yeniden
    hesaplanır (`acilis_gun`/`kapanis_gun` değerlerinin birleşik sıralı
    kümesi böler); arada aynı dizi (salt okunur) döner.
    """
    optionlar = optionlar.reset_index(drop=True)
    cekicilik = np.asarray(cekicilik, dtype=float)
    n_option_toplam = len(optionlar)

    magaza_idx = cesit_hucre["magaza_idx"].to_numpy()
    option_idx = cesit_hucre["option_idx"].to_numpy()
    acilis_c = cesit_hucre["acilis_gun"].to_numpy()
    kapanis_c = cesit_hucre["kapanis_gun"].to_numpy()
    alt_kategori_opt = optionlar["alt_kategori"].to_numpy()

    # --- Hücreleri option düzeyine indir (aynı option'ın SKU'ları aynı
    # pencereyi/grubu paylaşır; n option başına bir kez sayılmalı). -------
    anahtar = magaza_idx.astype(np.int64) * n_option_toplam + option_idx.astype(np.int64)
    anahtar_tekil, ilk_gorulme = np.unique(anahtar, return_index=True)
    hucre_option_pozisyonu = np.searchsorted(anahtar_tekil, anahtar)

    o_magaza = magaza_idx[ilk_gorulme]
    o_option = option_idx[ilk_gorulme]
    o_acilis = acilis_c[ilk_gorulme]
    o_kapanis = kapanis_c[ilk_gorulme]
    o_alt_kategori = alt_kategori_opt[o_option]
    o_cekicilik = cekicilik[o_option]

    # Grup kodu: (mağaza, alt kategori) → tamsayı; tuple factorize yerine
    # alt kategoriyi önce kodlayıp birleşik anahtarla (hız için).
    alt_kat_kod, alt_kat_essiz = pd.factorize(o_alt_kategori)
    grup_anahtari_ham = o_magaza.astype(np.int64) * len(alt_kat_essiz) + alt_kat_kod
    grup_kodu, _ = pd.factorize(grup_anahtari_ham)
    n_grup = int(grup_kodu.max()) + 1 if len(grup_kodu) else 0

    sinirlar = np.unique(np.concatenate([o_acilis, o_kapanis]))

    onbellek: dict = {"segment": None, "sonuc": None}

    def _option_carpanlari(d: int) -> np.ndarray:
        acik = (o_acilis <= d) & (d < o_kapanis)
        n_per_grup = np.bincount(grup_kodu[acik], minlength=n_grup)
        cekicilik_toplam = np.bincount(
            grup_kodu[acik], weights=o_cekicilik[acik], minlength=n_grup
        )
        n_hucre = n_per_grup[grup_kodu]
        with np.errstate(divide="ignore", invalid="ignore"):
            ortalama_hucre = np.where(
                n_hucre > 0,
                cekicilik_toplam[grup_kodu] / np.maximum(n_hucre, 1),
                1.0,
            )
            carpan = np.where(
                acik & (n_hucre > 0) & (ortalama_hucre > 0),
                (n_hucre.astype(float) ** beta / np.maximum(n_hucre, 1))
                * (o_cekicilik / np.where(ortalama_hucre > 0, ortalama_hucre, 1.0)),
                0.0,
            )
        return carpan

    def payi(d: int) -> np.ndarray:
        segment = int(np.searchsorted(sinirlar, d, side="right"))
        if onbellek["segment"] != segment:
            carpan_opt = _option_carpanlari(d)
            sonuc = carpan_opt[hucre_option_pozisyonu]
            sonuc.setflags(write=False)
            onbellek["segment"] = segment
            onbellek["sonuc"] = sonuc
        return onbellek["sonuc"]

    return payi
