"""v4 dünya montajı: bütün bileşenler tek, değişmez bir `Dunya` nesnesinde.

`dunya_kur(olcek)` günlük motorun (Görev 12–14) ve vakaların tek giriş
noktasıdır. Politikadan bağımsızdır: tedarikçi seçimi dışında hiçbir
Lumoda kararı burada verilmez (o da `tedarikci_secimi` ile enjekte
edilebilir).

**Rastgelelik: bileşen başına bağımsız çocuk üreteç.** Tek sıralı dünya
akışı yerine `np.random.SeedSequence(tohum).spawn(15)` ile aşağıdaki SABİT
sırada çocuk üreteçler açılır (controller kararı). Bir bileşenin kaç sayı
çektiği diğerlerini etkilemez; böylece tedarikçi seçimi plan λ'sından
SONRA (ona ihtiyaç duyduğu için) çalışabilir ve başka bir tedarikçi
politikası enjekte edildiğinde mağaza, ürün, çeşit, λ ve kampanya aynı
kalır. Sıra değiştirilmez; yeni bileşen yedeklerden birini alır.

    #   ad                tüketen
    0   magaza            magazalari_uret (tip, koordinat, m², gizli eksenler)
    1   olay              olaylari_uret (karar tarihleri)
    2   tedarikci         tedarikcileri_uret (yayımlanan + gizli profil)
    3   urun              urunleri_uret (modeller, öznitelikler, ham alış)
    4   tedarikci_secimi  tedarikci_secimi politikası (varsayılan Lumoda)
    5   cesit             cesit_ata (84 fiziksel mağazanın tamamı için)
    6   talep             lambda_kur: öznitelik → sürpriz → sürüklenme → τ →
                          yerel gürültü (talep.py'nin belgelediği sırayla)
    7   kampanya          kampanyalari_uret (talepten bağımsız, dışsal)
    8   siparis           ilk_siparisler: teslim sapması [O,1] → hatalı adet
    9   plan_tablolari    plan_tablolari: iyimserlik → range gürültüsü
    10  sapma             teslim_sapmasi: RPT [O,4] → sürekli [O,128]
    11–14 yedek           kullanılmıyor (ileride eklenecek bileşenler)

Günlük motor akışı ayrıdır ve dokunulmaz: `rastgele.sayac_uretici(d, amac)`.

**Montaj sırası:** mağazalar → olaylar → tedarikçiler → ürünler → çeşit
(tam zincir) → ölçek alt kümesi → hücreler → gerçek λ → plan λ (+ tek
geçişlik özeti) → talep tahmini → tedarikçi seçimi → tedarikçi maliyeti
(alış, liste fiyatı, `tedarikci_id`) → ilk alım → ilk siparişler →
kampanya → hücre esnekliği → plan tabloları → RPT/sürekli sapmaları →
mesafeler.

**Ölçek:** her şey tam zincir (84 fiziksel + ONL) için çekilir, sonra
`alt_kume` uygulanır ve diğer mağazaların çeşit satırları atılır; KÜÇÜK
dünyanın mağaza satırları TAM'dakilerle birebir aynıdır. Option sayısı
`Olcek.option_carpani` ile `urunleri_uret` içinde ölçeklenir (yalnız mağaza
kimliğinin eşitliği sözleşmedir). λ ve plan alt kümedeki mağazalarla
kurulur (ONL'nin statiği o zincirin fiziksel toplamından türer).
Kampanya takvimi bütün zincirin bölgeleriyle çekilir (ölçekten bağımsız).

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §6, §7.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-11-brief.md

v4 hiçbir v2/v3/kök modülünü içe aktarmaz (v3'ün `Dunya` kalıbı fikir
olarak alınmıştır).
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import sabitler
from .cesit import cesit_ata, hucreleri_kur
from .kampanya import esneklik, kampanya_takvimi, kampanyalari_uret
from .magaza import Olcek, alt_kume, magazalari_uret, olaylari_uret
from .plan import (
    LambdaOzeti,
    ilk_alim,
    ilk_siparisler,
    lambda_ozeti,
    plan_lambda,
    plan_tablolari,
    talep_tahmini,
)
from .takvim import D, sezon_tablosu, simulasyon_takvimi
from .talep import Lambda, lambda_kur
from .tedarik import (
    alis_fiyati_uygula,
    lumoda_tedarikci_secimi,
    tedarikcileri_uret,
    teslim_sapmasi,
)
from .urun import liste_fiyati, paketleri_uret, urunleri_uret

# Çocuk üreteç sırası (modül docstring'indeki tablo). Sıra sözleşmedir.
AKIS_SIRASI = [
    "magaza",
    "olay",
    "tedarikci",
    "urun",
    "tedarikci_secimi",
    "cesit",
    "talep",
    "kampanya",
    "siparis",
    "plan_tablolari",
    "sapma",
    "yedek_1",
    "yedek_2",
    "yedek_3",
    "yedek_4",
]

RPT_SAPMA_SAYISI = 4
SUREKLI_SAPMA_SAYISI = 128

# ileri_plan hafta blok önbelleği (hücre düzeyi haftalık toplam, LRU).
_HAFTA_ONBELLEK_BOYUTU = 16

TedarikciSecimi = Callable[
    [np.random.Generator, pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray], np.ndarray
]


def akislar(tohum: int = sabitler.TOHUM) -> dict[str, np.random.Generator]:
    """`SeedSequence(tohum).spawn(len(AKIS_SIRASI))` → ad → üreteç."""
    cocuklar = np.random.SeedSequence(tohum).spawn(len(AKIS_SIRASI))
    return {ad: np.random.default_rng(ss) for ad, ss in zip(AKIS_SIRASI, cocuklar)}


# ---------------------------------------------------------------------------
# Mesafe, yolda süre
# ---------------------------------------------------------------------------


def _haversine_matris(lat1, lon1, lat2, lon2) -> np.ndarray:
    """`[len(lat1), len(lat2)]` büyük çember uzaklığı, km."""
    r = 6371.0
    p1, l1 = np.radians(np.asarray(lat1, float))[:, None], np.radians(np.asarray(lon1, float))[:, None]
    p2, l2 = np.radians(np.asarray(lat2, float))[None, :], np.radians(np.asarray(lon2, float))[None, :]
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin((l2 - l1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def yolda_gun(km: np.ndarray, depo: bool = True) -> np.ndarray:
    """Yolda süre (gün, tam sayı). Depo → mağaza: `1 + (km>300) + (km>800)`
    (1–3); mağaza → mağaza: `1 + (km>150) + (km>500) + (km>1000)` (1–4)."""
    km = np.asarray(km, dtype=float)
    if depo:
        return (1 + (km > 300) + (km > 800)).astype(np.int64)
    return (1 + (km > 150) + (km > 500) + (km > 1000)).astype(np.int64)


# ---------------------------------------------------------------------------
# Dunya
# ---------------------------------------------------------------------------


def _salt_okunur(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    a.setflags(write=False)
    return a


@dataclass(frozen=True, eq=False)
class Dunya:
    """Politikadan bağımsız dünya (değişmez: alanlar yeniden atanamaz,
    kendi numpy dizileri salt okunurdur; DataFrame'ler de salt okunur
    kabul edilmelidir).

    İndis sözleşmesi: `m` mağaza (`magazalar` satır sırası, ONL son satır),
    `o` option (`optionlar`), `s` SKU (`urunler`), `c` hücre (`cesit` satır
    sırası; ONL hücreleri dahil), `d` gün (0 = ISINMA_BASLANGIC; `takvim`
    satır sırası). `takvim` simülasyon takvimidir: `D + UZATMA_GUN` satır;
    motor ilk `gun_sayisi = D` günü koşar, λ dizileri uzatmayı da kapsar.
    """

    # --- Tablolar ----------------------------------------------------------
    magazalar: pd.DataFrame
    gizli_magaza: pd.DataFrame      # segment + dört eksen (gizli)
    magaza_olay: pd.DataFrame
    urunler: pd.DataFrame           # SKU; tedarikçi maliyeti uygulanmış fiyatlar
    optionlar: pd.DataFrame
    paketler: pd.DataFrame
    tedarikciler: pd.DataFrame
    gizli_tedarikci: pd.DataFrame   # tedarikçi profili (gizli)
    kampanya: pd.DataFrame
    cesit: pd.DataFrame             # hücre tablosu (magaza_idx, sku_idx, option_idx, ...)
    sezon: pd.DataFrame
    takvim: pd.DataFrame            # simülasyon takvimi (ısınma + uzatma)

    # --- Hücre / SKU dizileri ------------------------------------------------
    hucre_magaza: np.ndarray        # [C]
    hucre_sku: np.ndarray           # [C]
    hucre_option: np.ndarray        # [C]
    hucre_online: np.ndarray        # [C] bool
    hucre_acilis: np.ndarray        # [C] pencere başı (gün)
    hucre_kapanis: np.ndarray       # [C] pencere sonu (gün, hariç)
    hucre_outlet_akisi: np.ndarray  # [C] bool
    sku_option: np.ndarray          # [S]
    sku_beden_payi: np.ndarray      # [S] zincir beden eğrisi payı (option içinde toplam 1)

    # --- Talep ---------------------------------------------------------------
    lam: Lambda                     # gerçek λ (gizli)
    plan: Lambda                    # Lumoda'nın plan λ'sı (indirim inancı dahil)
    plan_ozeti: LambdaOzeti         # plan λ'nın tek geçişlik özeti
    gizli_talep: dict               # lambda_kur'un gizli iç parçaları
    esneklik: np.ndarray            # [M, O] gizli ε
    esneklik_hucre: np.ndarray      # [C] = esneklik[m(c), o(c)]
    kampanya_takvimi: Callable[[int], np.ndarray]  # d → [M, O] kampanya oranı

    # --- Tedarik, plan -------------------------------------------------------
    tedarikci_idx: np.ndarray       # [O] `tedarikciler` satır indisi
    ilk_alim: np.ndarray            # [O] (DEVAMLI 0)
    ilk_siparisler: list
    plan_tablolari: dict            # mfp_plan, range_plan, magaza_plan
    sapma_rpt: np.ndarray           # [O, 4] gün
    sapma_surekli: np.ndarray       # [O, 128] gün

    # --- Coğrafya ------------------------------------------------------------
    mesafe_km: np.ndarray           # [M, M] haversine
    depo_mesafe_km: np.ndarray      # [M] Gebze deposuna (ONL 0)

    gun_sayisi: int                 # motorun koştuğu gün sayısı (D)
    olcek: Olcek = Olcek.TAM
    tohum: int = sabitler.TOHUM

    _onbellek: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        O = len(self.optionlar)
        kum = np.vstack(
            [np.zeros((1, O)), np.cumsum(self.plan_ozeti.gunluk.sum(axis=1), axis=0)]
        )
        self._onbellek["option_kum"] = _salt_okunur(kum)
        self._onbellek["hafta"] = OrderedDict()

    # --- Plan ufku -----------------------------------------------------------

    def _hafta_plani(self, w: int) -> np.ndarray:
        """[7w, 7w+7) plan λ toplamı `[C]` (LRU önbellekli)."""
        lru: OrderedDict = self._onbellek["hafta"]
        if w in lru:
            lru.move_to_end(w)
            return lru[w]
        toplam = np.zeros(len(self.hucre_option))
        for x in range(7 * w, 7 * w + 7):
            toplam += self.plan.gun(x)
        toplam.setflags(write=False)
        lru[w] = toplam
        if len(lru) > _HAFTA_ONBELLEK_BOYUTU:
            lru.popitem(last=False)
        return toplam

    def ileri_plan(self, d: int, gun: int) -> np.ndarray:
        """`[C]` [d, d+gun) plan λ toplamı (λ ufkunun sonunda kesilir).
        Tam haftalar (d=0 pazartesi, 7'nin katları) önbellekten, kenar
        günler doğrudan toplanır; her pazartesi çağrılması ucuzdur."""
        bit = min(d + gun, self.plan.gun_sayisi)
        toplam = np.zeros(len(self.hucre_option))
        x = max(d, 0)
        while x < bit:
            if x % 7 == 0 and x + 7 <= bit:
                toplam += self._hafta_plani(x // 7)
                x += 7
            else:
                toplam += self.plan.gun(x)
                x += 1
        return toplam

    def ileri_plan_option(self, d: int, gun: int) -> np.ndarray:
        """`[O]` [d, d+gun) zincir plan λ toplamı (bütün hücreler)."""
        kum = self._onbellek["option_kum"]
        n = kum.shape[0] - 1
        bas, bit = min(max(d, 0), n), min(d + gun, n)
        return kum[max(bit, bas)] - kum[bas]

    # --- Gizli gerçek --------------------------------------------------------

    def gercek(self) -> dict:
        """Gizli gerçek (hiçbir yayımlanan tabloya girmez): segment ve
        eksenler (`gizli_magaza`), esneklik `[M, O]`, öznitelik etkisi
        `[S, G, O]` + trend tablosu, sürpriz `[O]`, sürüklenme `[N, O]`,
        τ oynaması, tedarikçi profili (`gizli_tedarikci`)."""
        gt = self.gizli_talep
        return {
            "segment": self.gizli_magaza,
            "esneklik": self.esneklik,
            "oznitelik_etkisi": gt["oznitelik_etkisi"],
            "trend_tablosu": gt["trend_tablosu"],
            "surpriz": gt["surpriz"],
            "suruklenme": gt["suruklenme"],
            "tau_oynama": gt["tau_oynama"],
            "tedarikci_profili": self.gizli_tedarikci,
        }


# ---------------------------------------------------------------------------
# Montaj yardımcıları
# ---------------------------------------------------------------------------


def _olcege_indir(magazalar, gizli, olaylar, cesit_opt, olcek):
    """`alt_kume` maskesini uygular; çeşit satırlarının `magaza_idx`'ini
    yeni satır sırasına eşler, dışarıda kalan mağazaların satırlarını atar."""
    maske = alt_kume(magazalar, gizli, olaylar, olcek)
    yeni_idx = np.full(len(magazalar), -1, dtype=np.int64)
    yeni_idx[maske] = np.arange(int(maske.sum()))
    magazalar = magazalar[maske].reset_index(drop=True)
    gizli = gizli[maske].reset_index(drop=True)
    olaylar = olaylar[olaylar.magaza_id.isin(magazalar.magaza_id)].reset_index(drop=True)
    m = yeni_idx[cesit_opt["magaza_idx"].to_numpy()]
    cesit_opt = cesit_opt[m >= 0].assign(magaza_idx=m[m >= 0]).reset_index(drop=True)
    return magazalar, gizli, olaylar, cesit_opt


def _tedarikci_maliyeti(urunler, optionlar, tedarikciler, gizli_ted, ted_idx):
    """Seçilen tedarikçinin maliyet çarpanını (uzmanlık uyumunda ×0,93)
    ham alışa uygular, liste fiyatını yeniden hesaplar, `tedarikci_id`'yi
    yazar (option ve SKU)."""
    alan = optionlar["alt_kategori"].map(sabitler.ALT_KATEGORI_ALAN).to_numpy()
    uyum = alan == tedarikciler["uzmanlik"].to_numpy()[ted_idx]
    alis = alis_fiyati_uygula(
        optionlar["alis_fiyati"].to_numpy(dtype=float),
        gizli_ted["maliyet_carpani"].to_numpy(dtype=float)[ted_idx],
        uyum,
    ).round(2)
    liste = liste_fiyati(alis, optionlar["fiyat_segmenti"].to_numpy())
    tid = tedarikciler["tedarikci_id"].to_numpy()[ted_idx]

    optionlar = optionlar.copy()
    optionlar["alis_fiyati"] = alis
    optionlar["liste_fiyati"] = liste
    optionlar["tedarikci_id"] = tid

    o_s = pd.Series(np.arange(len(optionlar)), index=optionlar["option_id"])
    o_s = o_s.loc[urunler["option_id"]].to_numpy()
    urunler = urunler.copy()
    urunler["alis_fiyati"] = alis[o_s]
    urunler["liste_fiyati"] = liste[o_s]
    urunler["tedarikci_id"] = tid[o_s]
    return urunler, optionlar


def _sku_beden_payi(urunler: pd.DataFrame, sku_option: np.ndarray) -> np.ndarray:
    """Zincir beden eğrisi (BEDEN_PAYLARI_ZINCIR) option içinde toplam 1'e
    normalize; tek bedenli option'da 1."""
    zincir = np.asarray(sabitler.BEDEN_PAYLARI_ZINCIR, dtype=float)
    sira = urunler["beden_sira"].to_numpy(dtype=int)
    ham = zincir[np.clip(sira - 1, 0, len(zincir) - 1)]
    toplam = np.bincount(sku_option, weights=ham)
    return ham / toplam[sku_option]


# ---------------------------------------------------------------------------
# dunya_kur
# ---------------------------------------------------------------------------


def dunya_kur(
    olcek: Olcek = Olcek.TAM,
    tedarikci_secimi: TedarikciSecimi = lumoda_tedarikci_secimi,
    tohum: int = sabitler.TOHUM,
) -> Dunya:
    """Dünyayı kurar (bkz. modül docstring'i: akış tablosu, montaj sırası).

    `tedarikci_secimi(rng, optionlar, tedarikciler, gizli_tedarikci,
    talep_tahmini) -> [O]` (tedarikçi satır indisi) politikası enjekte
    edilebilir; kendi çocuk üretecini (`tedarikci_secimi`) alır, bu yüzden
    başka bir politika diğer bileşenlerin çekilişlerini değiştirmez.
    """
    rng = akislar(tohum)

    # --- Tam zincir çekilişleri ----------------------------------------------
    magazalar_tam, gizli_tam = magazalari_uret(rng["magaza"])
    olaylar_tam = olaylari_uret(rng["olay"], magazalar_tam, gizli_tam)
    tedarikciler, gizli_ted = tedarikcileri_uret(rng["tedarikci"])
    urunler, optionlar = urunleri_uret(rng["urun"], olcek)
    cesit_opt_tam = cesit_ata(rng["cesit"], magazalar_tam, gizli_tam, optionlar)

    # --- Ölçek alt kümesi (çekilişlerden sonra) ------------------------------
    magazalar, gizli, olaylar, cesit_opt = _olcege_indir(
        magazalar_tam, gizli_tam, olaylar_tam, cesit_opt_tam, olcek
    )
    hucre = hucreleri_kur(cesit_opt, urunler)

    # hucreleri_kur option_idx'i urunler'deki ilk görülme sırasından türetir:
    # optionlar satır sırasıyla aynı olmalı.
    assert np.array_equal(
        optionlar["option_id"].to_numpy()[hucre["option_idx"].to_numpy()],
        urunler["option_id"].to_numpy()[hucre["sku_idx"].to_numpy()],
    ), "hucreleri_kur option_idx sözleşmesi bozuldu"

    # --- Talep: gerçek λ, plan λ ---------------------------------------------
    lam, gizli_talep = lambda_kur(
        rng["talep"], magazalar, gizli, olaylar, optionlar, urunler, hucre
    )
    plan = plan_lambda(magazalar, gizli, olaylar, optionlar, urunler, hucre, gizli_talep)
    plan_oz = lambda_ozeti(plan, magazalar, optionlar)
    tahmin = talep_tahmini(plan_oz, optionlar)

    # --- Tedarikçi seçimi ve maliyeti ----------------------------------------
    ted_idx = np.asarray(
        tedarikci_secimi(rng["tedarikci_secimi"], optionlar, tedarikciler, gizli_ted, tahmin),
        dtype=np.int64,
    )
    assert ted_idx.shape == (len(optionlar),), "tedarikci_secimi [O] döndürmeli"
    urunler, optionlar = _tedarikci_maliyeti(urunler, optionlar, tedarikciler, gizli_ted, ted_idx)

    # --- İlk alım, ilk siparişler --------------------------------------------
    alim = ilk_alim(plan_oz, optionlar, ted_idx, gizli_ted)
    siparisler = ilk_siparisler(
        rng["siparis"], optionlar, urunler, alim, ted_idx, tedarikciler, gizli_ted
    )

    # --- Kampanya, esneklik --------------------------------------------------
    kampanya = kampanyalari_uret(rng["kampanya"], magazalar_tam, optionlar)
    takvim = simulasyon_takvimi()
    kamp_takvim = kampanya_takvimi(kampanya, magazalar, optionlar, lam.gun_sayisi)

    m_c = hucre["magaza_idx"].to_numpy().astype(np.intp)
    o_c = hucre["option_idx"].to_numpy().astype(np.intp)
    s_c = hucre["sku_idx"].to_numpy().astype(np.intp)
    eps = esneklik(gizli, optionlar)
    eps_hucre = eps[m_c, o_c]

    # --- Plan tabloları, sapmalar --------------------------------------------
    tablolar = plan_tablolari(rng["plan_tablolari"], plan_oz, lam, magazalar, optionlar, alim)
    sapma_rpt = teslim_sapmasi(rng["sapma"], gizli_ted, ted_idx, RPT_SAPMA_SAYISI)
    sapma_surekli = teslim_sapmasi(rng["sapma"], gizli_ted, ted_idx, SUREKLI_SAPMA_SAYISI)

    # --- Coğrafya ------------------------------------------------------------
    lat, lon = magazalar["enlem"].to_numpy(), magazalar["boylam"].to_numpy()
    mesafe = _haversine_matris(lat, lon, lat, lon)
    np.fill_diagonal(mesafe, 0.0)
    mesafe = (mesafe + mesafe.T) / 2
    depo_lat, depo_lon = sabitler.GEBZE_DEPO
    depo_mesafe = _haversine_matris([depo_lat], [depo_lon], lat, lon)[0]
    depo_mesafe[(magazalar["tip"] == "Online").to_numpy()] = 0.0

    # --- İndis dizileri ------------------------------------------------------
    option_sira = pd.Series(np.arange(len(optionlar)), index=optionlar["option_id"])
    sku_option = option_sira.loc[urunler["option_id"]].to_numpy().astype(np.intp)
    online_m = (magazalar["tip"] == "Online").to_numpy()

    return Dunya(
        magazalar=magazalar,
        gizli_magaza=gizli,
        magaza_olay=olaylar,
        urunler=urunler,
        optionlar=optionlar,
        paketler=paketleri_uret(),
        tedarikciler=tedarikciler,
        gizli_tedarikci=gizli_ted,
        kampanya=kampanya,
        cesit=hucre,
        sezon=sezon_tablosu(),
        takvim=takvim,
        hucre_magaza=_salt_okunur(m_c),
        hucre_sku=_salt_okunur(s_c),
        hucre_option=_salt_okunur(o_c),
        hucre_online=_salt_okunur(online_m[m_c]),
        hucre_acilis=_salt_okunur(hucre["acilis_gun"].to_numpy()),
        hucre_kapanis=_salt_okunur(hucre["kapanis_gun"].to_numpy()),
        hucre_outlet_akisi=_salt_okunur(hucre["outlet_akisi"].to_numpy(dtype=bool)),
        sku_option=_salt_okunur(sku_option),
        sku_beden_payi=_salt_okunur(_sku_beden_payi(urunler, sku_option)),
        lam=lam,
        plan=plan,
        plan_ozeti=plan_oz,
        gizli_talep=gizli_talep,
        esneklik=_salt_okunur(eps),
        esneklik_hucre=_salt_okunur(eps_hucre),
        kampanya_takvimi=kamp_takvim,
        tedarikci_idx=_salt_okunur(ted_idx),
        ilk_alim=_salt_okunur(np.asarray(alim)),
        ilk_siparisler=siparisler,
        plan_tablolari=tablolar,
        sapma_rpt=_salt_okunur(sapma_rpt),
        sapma_surekli=_salt_okunur(sapma_surekli),
        mesafe_km=_salt_okunur(mesafe),
        depo_mesafe_km=_salt_okunur(depo_mesafe),
        gun_sayisi=D,
        olcek=olcek,
        tohum=tohum,
    )
