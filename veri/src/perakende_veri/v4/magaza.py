"""v4 mağazalar, gizli segmentler, mağaza olayları, ölçek.

84 fiziksel mağaza + online kanal (`ONL`). Dört gizli eksen (iklim, gelir,
müşteri profili, konum) altı gözlemlenebilir segmente toplanır; segment ve
eksenler hiçbir dışa aktarılan tabloya girmez (yalnız `gizli_magaza`).

**Segment latent sınıftır, eksenler onun gürültülü tezahürüdür** (spec
§8.3): metropol (İstanbul/Ankara/İzmir) mağazalarında `segment` önce
kotayla atanır (karıştırılmış sırayla ≥7 metropol_premium, ≥7
metropol_genc, kalanı anadolu_aile), gelir/genç-eğilim eksenleri SONRA bu
sınıfın örtüşen dağılımlarından çekilir. Eksenler segmentten türetilmez;
bu yüzden k-means gibi bir kümeleme segmentleri ancak kısmen geri kurar
(ARI ~0,4–0,8 hedeflenir, kusursuz ayrışma değil).

Olay seçimi (6 açılış, 4 kapanış, 2 tadilat) **tasarımla** yapılır, tohuma
göre yeniden denenmez: her kapanış profili şehir sayısı / haversine
uzaklığı gibi yapısal kurallarla bulunur (bkz. `_profil*_sec`), açılış ve
tadilat mağazaları şehirler arasında dönüşümlü (round-robin) seçilir ki
segmentler olay kümesinde de doğal olarak temsil edilsin.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §2.2, §2.3, §6.3
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-4-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from . import sabitler

# ---------------------------------------------------------------------------
# Ölçek
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Olcek:
    """Üretim ölçeği: `magaza=None` tam ölçek, aksi halde `alt_kume` fiziksel
    mağaza sayısını bu değere indirir. `option_carpani` ürün/tedarik
    görevlerinde (Görev 5+) option sayısını ölçekler; burada kullanılmaz."""

    magaza: int | None = None
    option_carpani: float = 1.0


Olcek.TAM = Olcek()
Olcek.KUCUK = Olcek(magaza=20, option_carpani=0.15)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Büyük çember uzaklığı, km (yarıçap 6371). Girdiler yayınlanır
    (broadcast): nokta × dizi ya da `lat1[:, None]`, `lat2[None, :]` ile
    matris. v4'ün tek haversine'i (mağaza üretimi, dünya mesafeleri, olay
    kaymaları, testler)."""
    r = 6371.0
    lat1r, lon1r = np.radians(np.asarray(lat1, dtype=float)), np.radians(np.asarray(lon1, dtype=float))
    lat2r = np.radians(np.asarray(lat2, dtype=float))
    lon2r = np.radians(np.asarray(lon2, dtype=float))
    dphi = lat2r - lat1r
    dl = lon2r - lon1r
    a = np.sin(dphi / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


# ---------------------------------------------------------------------------
# magazalari_uret
# ---------------------------------------------------------------------------


def _fiziksel_govde() -> pd.DataFrame:
    """84 fiziksel mağazanın şehir/bölge/koordinat/tip iskeleti.

    Sıra `SEHIRLER` sırasıyla, şehir içinde artan; bu sıra `magaza_id`
    sırasıdır (M001 İstanbul'un ilk mağazası, ...). Outlet konumu (şehir
    başına ilk N slot) rastgelelik gerektirmez: hangi şehirlerin kaç outlet
    aldığı zaten `OUTLET_SEHIRLERI` ile sabittir.
    """
    satirlar = []
    for sehir, bolge, enlem, boylam, iklim in sabitler.SEHIRLER:
        adet = sabitler.SEHIR_MAGAZA_SAYISI[sehir]
        outlet_adet = sabitler.OUTLET_SEHIRLERI.get(sehir, 0)
        for i in range(adet):
            satirlar.append(
                {
                    "sehir": sehir,
                    "bolge": bolge,
                    "enlem_sehir": enlem,
                    "boylam_sehir": boylam,
                    "iklim": iklim,
                    "_outlet_mi": i < outlet_adet,
                }
            )
    return pd.DataFrame(satirlar)


def _tip_ata(govde: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Outlet slotları sabit; kalan 74 slot 47 AVM / 27 Cadde'ye karıştırılarak
    dağıtılır (şehir sırasıyla örtüşmesin diye karıştırma şart)."""
    tipler = np.where(govde["_outlet_mi"].to_numpy(), "Outlet", "")
    bos = np.flatnonzero(tipler == "")
    karisik = bos[rng.permutation(len(bos))]
    tipler[karisik[:47]] = "AVM"
    tipler[karisik[47:]] = "Cadde"
    return tipler


def _metrekare_kat_kapasite(tipler: np.ndarray, rng: np.random.Generator):
    araliklar = {"AVM": (250, 1200), "Cadde": (150, 500), "Outlet": (400, 1000)}
    metrekare = np.array(
        [rng.integers(*araliklar[t], endpoint=True) for t in tipler], dtype=int
    )
    kat = np.empty(len(tipler), dtype=int)
    for i, m in enumerate(metrekare):
        if m < 400:
            kat[i] = 1
        elif m <= 800:
            kat[i] = rng.integers(1, 3, endpoint=True)
        else:
            kat[i] = rng.integers(2, 3, endpoint=True)
    yogunluk = np.array([sabitler.TIP_YOGUNLUK[t] for t in tipler])
    kapasite = (metrekare * yogunluk * (1 - 0.08 * (kat - 1))).astype(int)
    return metrekare, kat, kapasite


def _acilis_kapanis_tarihleri(
    n: int, magaza_id: np.ndarray, rng: np.random.Generator, acilis_plani, kapanis_plani
):
    """Varsayılan eski açılış tarihi (2012–2022-07-03) + olay mağazalarının
    gerçek açılış/kapanış tarihleriyle üzerine yazma."""
    gun_farki = rng.integers(0, (date(2022, 7, 3) - date(2012, 1, 1)).days, size=n)
    acilis = pd.Series(
        pd.Timestamp("2012-01-01") + pd.to_timedelta(gun_farki, unit="D")
    )
    kapanis = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")

    idx = {mid: i for i, mid in enumerate(magaza_id)}
    for mid, tarih in acilis_plani.items():
        acilis.iloc[idx[mid]] = pd.Timestamp(tarih)
    for mid, tarih in kapanis_plani.items():
        kapanis.iloc[idx[mid]] = pd.Timestamp(tarih)
    return acilis, kapanis


# --- Olay mağaza seçimi (tasarımla, yeniden deneme yok) --------------------


def _profil1_sec(df: pd.DataFrame, kullanilmis: set) -> str:
    """Çok mağazalı şehir (>= 5 fiziksel mağaza)."""
    uygun = {s for s, n in sabitler.SEHIR_MAGAZA_SAYISI.items() if n >= 5}
    aday = df[
        (df.tip != "Outlet") & df.sehir.isin(uygun) & ~df.magaza_id.isin(kullanilmis)
    ]
    return aday.sort_values("magaza_id").magaza_id.iloc[0]


def _profil2_sec(df: pd.DataFrame, kullanilmis: set) -> str:
    """150 km içinde başka fiziksel mağaza yok."""
    lat, lon = df.enlem.to_numpy(), df.boylam.to_numpy()
    en_yakin = np.empty(len(df))
    for i in range(len(df)):
        d = haversine_km(lat[i], lon[i], lat, lon)
        d[i] = np.inf
        en_yakin[i] = d.min()
    aday = df[
        (df.tip != "Outlet") & (en_yakin > 150) & ~df.magaza_id.isin(kullanilmis)
    ]
    return aday.sort_values("magaza_id").magaza_id.iloc[0]


def _profil3_sec(df: pd.DataFrame, kullanilmis: set) -> str:
    """100 km içinde bir outlet var."""
    outletler = df[df.tip == "Outlet"]
    lat_o, lon_o = outletler.enlem.to_numpy(), outletler.boylam.to_numpy()

    def yakin_mi(satir) -> bool:
        d = haversine_km(satir.enlem, satir.boylam, lat_o, lon_o)
        return bool(d.min() < 100)

    maske = df.apply(yakin_mi, axis=1) & (df.tip != "Outlet") & ~df.magaza_id.isin(
        kullanilmis
    )
    return df[maske].sort_values("magaza_id").magaza_id.iloc[0]


def _cesitli_sec(df: pd.DataFrame, kullanilmis: set, sayi: int) -> list[str]:
    """`sayi` kadar mağazayı şehirler arasında dönüşümlü (round-robin) seçer.

    Açılış ve tadilat mağazaları böylece tek bir şehirde yığılmaz; her
    segment (iklim/turistik şehirlerin karışımıyla) olay kümesinde de
    doğal olarak temsil edilir.
    """
    secilenler: list[str] = []
    kullanilmis = set(kullanilmis)
    sehir_sirasi = [s[0] for s in sabitler.SEHIRLER]
    ilerledi = True
    while len(secilenler) < sayi and ilerledi:
        ilerledi = False
        for sehir in sehir_sirasi:
            aday = df[
                (df.sehir == sehir)
                & (df.tip != "Outlet")
                & ~df.magaza_id.isin(kullanilmis)
            ]
            if len(aday):
                mid = aday.sort_values("magaza_id").magaza_id.iloc[0]
                secilenler.append(mid)
                kullanilmis.add(mid)
                ilerledi = True
                if len(secilenler) == sayi:
                    break
    return secilenler


# Açılışlar: sezon başına bir dalga1 ofseti; ilk ikisi tam dalga1 pazartesi
# (ofset 0), kalan dördü sezonun 5.–10. haftası (ofset 40 gün, [28,70) içinde).
_ACILIS_PLANI = [
    ("AW23", 0),
    ("SS25", 0),
    ("SS23", 40),
    ("SS24", 40),
    ("AW24", 40),
    ("AW25", 40),
]

# Kapanışlar: profil sırasıyla, her biri pencere içinde, dördüncüsü bir
# sezonun indirim döneminde ([indirim, çıkış)).
_KAPANIS_TARIHLERI = [
    date(2023, 9, 18),  # profil 1: çok mağazalı şehir
    date(2024, 4, 1),  # profil 2: izole (150 km)
    date(2025, 2, 3),  # profil 3: outlet yakın (100 km)
    date(2024, 7, 22),  # profil 4: SS24 indirimi [2024-07-01, 2024-08-26)
]

# Tadilatlar: her ikisi de pencere içinde, bitiş 2025-12-31'den çok önce
# (pencere sonunda "renovasyonlar bitmiş" varsayımı).
_TADILAT_TARIHLERI = [date(2023, 11, 6), date(2024, 9, 2)]
_TADILAT_SURESI_GUN = 35


def magazalari_uret(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`magazalar` ve `gizli_magaza` tablolarını üretir.

    Olay mağazalarının (açılış/kapanış) seçimi burada, tam koordinat/tip
    tablosu hazır olduğunda yapılır ki `acilis_tarihi`/`kapanis_tarihi`
    olaylarla tutarlı olsun; `olaylari_uret` bu tarihleri geri okuyup
    `magaza_olay` satırlarını (karar tarihiyle birlikte) üretir.
    """
    govde = _fiziksel_govde()
    n = len(govde)

    tipler = _tip_ata(govde, rng)
    govde["tip"] = tipler

    enlem = govde.enlem_sehir.to_numpy() + rng.normal(0, 0.01, n)
    boylam = govde.boylam_sehir.to_numpy() + rng.normal(0, 0.01, n)
    govde["enlem"] = enlem
    govde["boylam"] = boylam

    metrekare, kat, kapasite = _metrekare_kat_kapasite(tipler, rng)

    magaza_id = np.array([f"M{i:03d}" for i in range(1, n + 1)])
    govde["magaza_id"] = magaza_id

    # --- Olay mağazalarını tasarımla seç (kullanılmışları biriktirerek) ---
    kullanilmis: set[str] = set()
    profil1 = _profil1_sec(govde, kullanilmis)
    kullanilmis.add(profil1)
    profil2 = _profil2_sec(govde, kullanilmis)
    kullanilmis.add(profil2)
    profil3 = _profil3_sec(govde, kullanilmis)
    kullanilmis.add(profil3)
    kapanis_magazalari = [profil1, profil2, profil3]

    digerleri = _cesitli_sec(govde, kullanilmis, 1 + 6 + 2)
    profil4 = digerleri[0]
    acilis_magazalari = digerleri[1:7]
    # digerleri[7:9] (tadilat adayları) burada kullanılmaz: tadilat
    # mağazaları `olaylari_uret` içinde, açılış/kapanış kesinleştikten
    # sonra ayrıca seçilir (bkz. orada `_cesitli_sec` çağrısı).
    kapanis_magazalari.append(profil4)

    acilis_plani = {}
    for mid, (sezon, ofset) in zip(acilis_magazalari, _ACILIS_PLANI):
        dalga1 = sabitler.SEZONLAR[sezon]["dalgalar"][0]
        acilis_plani[mid] = pd.Timestamp(dalga1) + pd.Timedelta(int(ofset), unit="D")

    kapanis_plani = dict(zip(kapanis_magazalari, _KAPANIS_TARIHLERI))

    acilis, kapanis = _acilis_kapanis_tarihleri(
        n, magaza_id, rng, acilis_plani, kapanis_plani
    )

    ad = govde.groupby("sehir").cumcount().add(1)
    ad = [f"{s} {i}" for s, i in zip(govde.sehir, ad)]

    magazalar = pd.DataFrame(
        {
            "magaza_id": magaza_id,
            "ad": ad,
            "sehir": govde.sehir.to_numpy(),
            "bolge": govde.bolge.to_numpy(),
            "enlem": enlem,
            "boylam": boylam,
            "tip": tipler,
            "metrekare": metrekare,
            "kat_sayisi": kat,
            "kapasite": kapasite,
            "acilis_tarihi": acilis.to_numpy(),
            "kapanis_tarihi": kapanis.to_numpy(),
        }
    )

    # --- Online kanal (ONL): tek satır, depo koordinatları, olaysız ---
    onl = pd.DataFrame(
        {
            "magaza_id": ["ONL"],
            "ad": ["Online"],
            "sehir": ["Gebze"],
            "bolge": ["Marmara"],
            "enlem": [sabitler.GEBZE_DEPO[0]],
            "boylam": [sabitler.GEBZE_DEPO[1]],
            "tip": ["Online"],
            "metrekare": [0],
            "kat_sayisi": [0],
            "kapasite": [0],
            "acilis_tarihi": [pd.Timestamp("2012-01-01")],
            "kapanis_tarihi": [pd.NaT],
        }
    )
    magazalar = pd.concat([magazalar, onl], ignore_index=True)

    gizli = _gizli_segmentler_uret(govde, rng)
    gizli_onl = pd.DataFrame(
        {
            "magaza_id": ["ONL"],
            "iklim": ["ilıman"],
            "gelir": ["orta"],
            "kadin_payi": [0.5],
            "genc_egilim": [0.5],
            "beden_kayma": [0],
            "turistik": [False],
            "segment": ["online"],
            "yerel_gurultu": [0.0],
        }
    )
    gizli = pd.concat([gizli, gizli_onl], ignore_index=True)

    return magazalar, gizli


# Metropol kotaları: karıştırılmış (rng.permutation) sırayla ilk N_PREMIUM
# "metropol_premium", sonraki N_GENC "metropol_genc", kalanı "anadolu_aile".
# Kota tohumdan bağımsız ≥7/≥7 garantisi verir (25 metropol mağazasının
# tamamı bu üç gruba dağılır); dağılım rng'nin *hangi* mağazaları seçtiğini
# değiştirir, *kaç* mağaza seçildiğini değil.
_METROPOL_PREMIUM_KOTA = 9
_METROPOL_GENC_KOTA = 8


def _yapisal_segment(tip: str, iklim: str, turistik: bool) -> str | None:
    """Eksen gürültüsü olmadan, salt tip/iklim/turistikten kesin belirlenen
    segment: outlet, soguk_iklim, sicak_sahil. Metropol ve sade Anadolu
    mağazaları için `None` döner (onlar ayrıca çözülür)."""
    if tip == "Outlet":
        return "outlet"
    if iklim == "soguk":
        return "soguk_iklim"
    if iklim == "sicak_sahil" or turistik:
        return "sicak_sahil"
    return None


def _gizli_segmentler_uret(govde: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Dört gizli eksen + segment. Segment **latent sınıftır**: outlet,
    soğuk iklim ve sıcak sahil/turistik için tip/iklimden kesin (yapısal)
    belirlenir; metropol (İstanbul/Ankara/İzmir) mağazalarında ise önce
    kotayla atanır (bkz. `_METROPOL_PREMIUM_KOTA`/`_METROPOL_GENC_KOTA`),
    eksenler bu sınıfın SONRASINDA, örtüşen dağılımlardan çekilir — segment
    eksenlerden türetilmez, eksenler segmentin gürültülü tezahürüdür.
    Bu örtüşme (premium ve genç eğilimlerinin gelir/genç-eğilim aralıkları
    kesişir) k-means'in segmentleri yalnızca kısmen geri kurmasını sağlar
    (spec §8.3). ≥6 mağaza/segment garantisi tohumdan bağımsız, kotayla
    sağlanır (bkz. `SEHIR_MAGAZA_SAYISI`/`OUTLET_SEHIRLERI` yorumu)."""
    n = len(govde)
    magaza_id = govde.magaza_id.to_numpy()
    sehir = govde.sehir.to_numpy()
    tip = govde.tip.to_numpy()
    iklim = govde.iklim.to_numpy()
    metropol = np.isin(sehir, list(sabitler.METROPOL_SEHIRLERI))
    turistik = np.isin(sehir, list(sabitler.TURISTIK_SEHIRLER))

    segment = np.empty(n, dtype=object)
    yapisal = np.array(
        [_yapisal_segment(t, ik, tu) for t, ik, tu in zip(tip, iklim, turistik)],
        dtype=object,
    )
    yapisal_cozuldu = yapisal != None  # noqa: E711
    segment[yapisal_cozuldu] = yapisal[yapisal_cozuldu]

    # Genel (yapısal olmayan, metropol dışı) eksen dağılımı; metropol grubu
    # aşağıda üzerine yazılır.
    gelir = np.array(rng.choice(["dusuk", "orta", "yuksek"], size=n, p=[0.3, 0.5, 0.2]))
    genc_egilim = rng.uniform(0.0, 1.0, n)

    metropol_idx = np.flatnonzero(metropol & ~yapisal_cozuldu)
    karisik = rng.permutation(metropol_idx)
    premium_idx = karisik[: _METROPOL_PREMIUM_KOTA]
    genc_idx = karisik[_METROPOL_PREMIUM_KOTA : _METROPOL_PREMIUM_KOTA + _METROPOL_GENC_KOTA]
    kalan_idx = karisik[_METROPOL_PREMIUM_KOTA + _METROPOL_GENC_KOTA :]

    segment[premium_idx] = "metropol_premium"
    gelir[premium_idx] = rng.choice(
        ["yuksek", "orta", "dusuk"], size=len(premium_idx), p=[0.70, 0.25, 0.05]
    )
    genc_egilim[premium_idx] = rng.beta(3, 4, len(premium_idx))

    segment[genc_idx] = "metropol_genc"
    gelir[genc_idx] = rng.choice(
        ["orta", "dusuk", "yuksek"], size=len(genc_idx), p=[0.55, 0.25, 0.20]
    )
    genc_egilim[genc_idx] = rng.beta(5, 2.5, len(genc_idx))

    segment[kalan_idx] = "anadolu_aile"
    gelir[kalan_idx] = rng.choice(
        ["orta", "dusuk", "yuksek"], size=len(kalan_idx), p=[0.5, 0.35, 0.15]
    )
    genc_egilim[kalan_idx] = rng.beta(3, 3, len(kalan_idx))

    # Kalan (yapısal olmayan, metropol olmayan) mağazalar: anadolu_aile.
    kalan_genel = ~yapisal_cozuldu & ~metropol
    segment[kalan_genel] = "anadolu_aile"

    beden_kayma = rng.integers(-1, 2, n, endpoint=True)
    kadin_payi = rng.uniform(0.35, 0.75, n)
    yerel_gurultu = rng.normal(0.0, 1.0, n)

    return pd.DataFrame(
        {
            "magaza_id": magaza_id,
            "iklim": iklim,
            "gelir": gelir,
            "kadin_payi": kadin_payi,
            "genc_egilim": genc_egilim,
            "beden_kayma": beden_kayma,
            "turistik": turistik,
            "segment": segment,
            "yerel_gurultu": yerel_gurultu,
        }
    )


# ---------------------------------------------------------------------------
# olaylari_uret
# ---------------------------------------------------------------------------


def olaylari_uret(
    rng: np.random.Generator, magazalar: pd.DataFrame, gizli: pd.DataFrame
) -> pd.DataFrame:
    """`magaza_olay` tablosu: `magazalar`ın açılış/kapanış tarihlerini okur
    (kaynak tek yerdedir, bkz. `magazalari_uret`) ve karar tarihini üretir;
    ayrıca 2 tadilat mağazasını (açılış/kapanış olmayan, AVM/Cadde) seçer.
    """
    fiziksel = magazalar[magazalar.tip != "Online"]

    acilanlar = fiziksel[fiziksel.acilis_tarihi >= pd.Timestamp(sabitler.BASLANGIC)]
    kapananlar = fiziksel[fiziksel.kapanis_tarihi.notna()]

    satirlar = []

    for _, r in acilanlar.iterrows():
        olay_tarihi = pd.Timestamp(r.acilis_tarihi)
        lead = int(rng.integers(60, 121))
        satirlar.append(
            {
                "magaza_id": r.magaza_id,
                "olay": "acilis",
                "karar_tarihi": olay_tarihi - pd.Timedelta(int(lead), unit="D"),
                "olay_tarihi": olay_tarihi,
                "bitis_tarihi": pd.NaT,
            }
        )

    for _, r in kapananlar.iterrows():
        olay_tarihi = pd.Timestamp(r.kapanis_tarihi)
        gecikme = int(rng.integers(28, 43))
        satirlar.append(
            {
                "magaza_id": r.magaza_id,
                "olay": "kapanis",
                "karar_tarihi": olay_tarihi - pd.Timedelta(int(gecikme), unit="D"),
                "olay_tarihi": olay_tarihi,
                "bitis_tarihi": pd.NaT,
            }
        )

    kullanilmis = set(acilanlar.magaza_id) | set(kapananlar.magaza_id)
    aday_havuzu = fiziksel[
        (fiziksel.tip != "Outlet") & ~fiziksel.magaza_id.isin(kullanilmis)
    ]
    tadilat_magazalari = _cesitli_sec(
        aday_havuzu.rename(columns={}), kullanilmis, 2
    )
    for mid, tarih in zip(tadilat_magazalari, _TADILAT_TARIHLERI):
        olay_tarihi = pd.Timestamp(tarih)
        gecikme = int(rng.integers(21, 43))
        satirlar.append(
            {
                "magaza_id": mid,
                "olay": "tadilat",
                "karar_tarihi": olay_tarihi - pd.Timedelta(int(gecikme), unit="D"),
                "olay_tarihi": olay_tarihi,
                "bitis_tarihi": olay_tarihi + pd.Timedelta(int(_TADILAT_SURESI_GUN), unit="D"),
            }
        )

    df = pd.DataFrame(satirlar)
    for kol in ("karar_tarihi", "olay_tarihi", "bitis_tarihi"):
        df[kol] = pd.to_datetime(df[kol])
    return df.sort_values("olay_tarihi").reset_index(drop=True)


# ---------------------------------------------------------------------------
# alt_kume
# ---------------------------------------------------------------------------


def alt_kume(
    magazalar: pd.DataFrame, gizli: pd.DataFrame, olaylar: pd.DataFrame, olcek: Olcek
) -> np.ndarray:
    """Ölçek `olcek.magaza` fiziksel mağazaya indirildiğinde hangi satırların
    (ONL dahil) tutulacağını işaretleyen boolean dizi.

    Tam ölçekte (`olcek.magaza is None`) tüm satırlar tutulur. Küçük ölçekte
    önce **korumalı** küme kurulur (olay mağazaları, kapanan mağazaların en
    yakın komşusu, en az bir outlet, her segmentten ve her fiziksel tipten
    en az bir); bu küme asla budanmaz. Korumalı küme `olcek.magaza`'yı zaten
    aşıyorsa (ölçek çok küçükse) `ValueError` yükseltilir — budama yerine
    net bir hata, zorunlu kapsamdan sessizce ödün vermez. Kalan slotlar
    (korumalı olmayanlar arasından) `magaza_id` sırasıyla deterministik
    doldurulur.
    """
    if olcek.magaza is None:
        return np.ones(len(magazalar), dtype=bool)

    fiziksel = magazalar[magazalar.tip != "Online"]
    magazalar_idx = magazalar.set_index("magaza_id")
    gizli_idx = gizli.set_index("magaza_id")

    korumali: set[str] = set(olaylar.magaza_id.unique())

    # Kapanan mağazaların en yakın (fiziksel) komşusu
    kapananlar = olaylar.query("olay == 'kapanis'").magaza_id.tolist()
    for mid in kapananlar:
        lat0, lon0 = magazalar_idx.loc[mid, ["enlem", "boylam"]]
        digerleri = fiziksel[fiziksel.magaza_id != mid]
        d = haversine_km(lat0, lon0, digerleri.enlem.to_numpy(), digerleri.boylam.to_numpy())
        en_yakin = digerleri.magaza_id.to_numpy()[np.argmin(d)]
        korumali.add(en_yakin)

    def _segmentleri(kume: set[str]) -> set[str]:
        varsa = [mid for mid in kume if mid in gizli_idx.index]
        return set(gizli_idx.loc[varsa, "segment"]) if varsa else set()

    def _tipleri(kume: set[str]) -> set[str]:
        varsa = [mid for mid in kume if mid in magazalar_idx.index]
        return set(magazalar_idx.loc[varsa, "tip"]) if varsa else set()

    # En az bir outlet (segment + tip ihtiyacını birlikte karşılar)
    if "outlet" not in _segmentleri(korumali):
        outlet_id = fiziksel[fiziksel.tip == "Outlet"].magaza_id.iloc[0]
        korumali.add(outlet_id)

    # Her segmentten en az bir
    for seg in sabitler.SEGMENTLER:
        if seg in _segmentleri(korumali):
            continue
        aday = gizli_idx[
            (gizli_idx.segment == seg) & gizli_idx.index.isin(fiziksel.magaza_id)
        ].index
        if len(aday):
            korumali.add(aday[0])

    # Her fiziksel tipten en az bir
    for tip in ("AVM", "Cadde", "Outlet"):
        if tip in _tipleri(korumali):
            continue
        aday = fiziksel[fiziksel.tip == tip].magaza_id.iloc[0]
        korumali.add(aday)

    korumali_fiziksel = korumali & set(fiziksel.magaza_id)
    if len(korumali_fiziksel) > olcek.magaza:
        raise ValueError(
            f"alt_kume: zorunlu kapsam (olay mağazaları, komşuları, outlet, "
            f"segment ve tip temsilcileri) {len(korumali_fiziksel)} fiziksel "
            f"mağaza gerektiriyor ama olcek.magaza={olcek.magaza}; ölçek bu "
            f"kapsamı budamadan karşılayamayacak kadar küçük."
        )

    # Kalan slotları (korumalı olmayanlar arasından) magaza_id sırasıyla
    # deterministik doldur.
    secili = set(korumali)
    for mid in sorted(fiziksel.magaza_id):
        if len(secili & set(fiziksel.magaza_id)) >= olcek.magaza:
            break
        if mid not in korumali:
            secili.add(mid)

    secili.add("ONL")
    return magazalar.magaza_id.isin(secili).to_numpy()
