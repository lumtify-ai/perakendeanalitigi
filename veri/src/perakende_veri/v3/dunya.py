"""v3'ün gizli dünyası: çeşit, plan, gerçek beklenen talep, tedarik.

Simülasyonun karar vermeden ÖNCE bildiği ya da bilmediği her şey burada
kurulur ve hiçbiri politikaya bağlı değildir. Vakalar `dunya_kur()` ile
dünyanın aynısını simülasyonu koşmadan elde eder.

Rastgelelik dört bağımsız akıştan gelir (koordinasyon kararı):

    dunya      np.random.default_rng(TOHUM)       mağaza, tedarikçi, ürün, çeşit,
                                                  beden eğrisi, yerel sapma,
                                                  sürpriz, τ, sürüklenme,
                                                  teslim sapmaları
    talep      SeedSequence(TOHUM).spawn(3)[0]    günlük Poisson talebi
    operasyon  SeedSequence(TOHUM, spawn_key=     iade, işlem indirimi — GÜN
               (1, d)), gün başına ayrı üreteç    BAŞINA AYRI üreteç, bkz. aşağı
    kirli      SeedSequence(TOHUM).spawn(3)[2]    kirli kayıtlar

`dunya` akışı v2 ile aynı tohumla başlar ve önce `magazalari_uret`'i
çağırır: v3'ün 25 mağazası v2'ninkilerle birebir aynıdır.

Operasyon rastgeleliği (hücre, gün) başına politikadan bağımsızdır: d günü
için `operasyon_uretici(d)` kurulur ve her gün tam olarak iki C boyutlu
tekdüze dizi çeker (önce iade, sonra işlem indirimi), satış olsun olmasın.
Bir hücrenin iadesi ve indirimi yalnız kendi tekdüze sayısına ve kendi
satışına bağlıdır: karşı-olgusal bir politika bazı hücrelerin satışını
değiştirdiğinde diğer hücrelerin iade ve indirim kararları aynen kalır.
(Eski tasarımda tek paylaşılan akış satan hücre sayısı kadar tüketiliyordu;
bir hücrenin satışı değişince sonraki bütün çekilişler kayıyordu.)

Talep akışı her gün BÜTÜN hücreler için (aktif olmayanlar λ = 0) çekilir;
günlük talep matrisi politikadan bağımsızdır ve `talep_matrisi()` ile
önceden hesaplanabilir. Teslim sapmaları da siparişten önce, option ve
sipariş sırası başına çekilmiştir: farklı bir RPT politikası aynı option
için aynı gecikmeyi görür.

Beklenen talep ayrışabilir:

    E[talep(c, d)] = gercek_statik[c] · g_gercek[d, option(c)]
    plan(c, d)     = plan_statik[c]   · g_plan[d, option(c)]

g_plan = mevsim × yaşam eğrisi × indirim talep çarpanı × gün çarpanı ×
yıl büyümesi × aktiflik; g_gercek = g_plan × sürpriz × sürüklenme.
Statik kısım v2'nin çarpanlarıdır (plan: zincir beden eğrisi, yerel çarpan
ve sürprizin yalnız BEKLENEN değeri; gerçek: mağaza beden eğrisi × yerel
option çarpanı, g_gercek'te option'ın kendi sürprizi).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import talep as v2_talep
from ..magaza import magazalari_uret
from ..simulasyon import _magaza_beden_egrileri, _yerel_option_carpani, cesit_ata
from . import sabitler, talep
from .takvim import gun_indisi, sezon_tablosu, simulasyon_takvimi
from .tedarik import en_buyuk_kalan, moq_yuvarla, teslim_sapmasi, tedarikcileri_uret
from .urun import urunleri_uret

# İleriye bakan toplamlar (replenishment hedefi 28 gün, sürekli tedarikte
# tedarik süresi + gözden geçirme + emniyet ≤ 21 hafta) pencerenin sonunda
# kesilmesin diye çarpanlar pencereden bu kadar gün öteye hesaplanır.
UZATMA_GUN = 160
RPT_SAPMA_SAYISI = 4   # option başına önceden çekilen RPT teslim sapması


def akislar() -> dict[str, np.random.Generator]:
    """Dört bağımsız rastgele akış (modül belgesine bakın)."""
    # spawn(3) sırası korunur: [0] talep, [1] operasyon (gün başına, aşağıda),
    # [2] kirli. Operasyonun kendisi burada akış olarak verilmez.
    talep_ss, _, kirli_ss = np.random.SeedSequence(sabitler.TOHUM).spawn(3)
    return {
        "dunya": np.random.default_rng(sabitler.TOHUM),
        "talep": np.random.default_rng(talep_ss),
        "kirli": np.random.default_rng(kirli_ss),
    }


OPERASYON_ANAHTARI = 1   # SeedSequence(TOHUM).spawn(3) içindeki sırası


def operasyon_uretici(d: int, tohum: int = sabitler.TOHUM) -> np.random.Generator:
    """d günü için operasyon üreteci: SeedSequence(tohum, spawn_key=(1, d)).

    Sayaç tabanlıdır: d. günün üreteci önceki günlerde ne çekildiğinden
    bağımsızdır. Motor her gün bundan tam iki `random(C)` çeker.
    """
    return np.random.default_rng(
        np.random.SeedSequence(tohum, spawn_key=(OPERASYON_ANAHTARI, d))
    )


def binom_ters_cdf(u: np.ndarray, n: np.ndarray, p: float) -> np.ndarray:
    """Binomial(n, p)'nin ters dağılım fonksiyonu: en küçük k, F(k) ≥ u.

    Hücre başına kendi tekdüze sayısıyla çekilir; n'si değişmeyen hücrenin
    sonucu da değişmez. Kesin (olasılıklar yinelemeli çarpımla), bağımlılık
    yok; n küçük olduğu için döngü kısa. Sonuç [0, n] aralığına kırpılır
    (yuvarlama F(n)'yi 1'in hemen altında bırakabilir).
    """
    n = np.asarray(n, dtype=np.int64)
    u = np.asarray(u, dtype=float)
    k = np.zeros(n.shape, dtype=np.int64)
    if n.size == 0 or n.max() <= 0:
        return k
    pmf = (1.0 - p) ** n
    cdf = pmf.copy()
    oran = p / (1.0 - p)
    for j in range(int(n.max())):
        asan = u > cdf
        if not asan.any():
            break
        k += asan
        pmf = pmf * np.maximum(n - j, 0) / (j + 1) * oran
        cdf = cdf + pmf
    return np.minimum(k, n)


@dataclass
class Dunya:
    """Politikadan bağımsız dünya. Diziler salt okunur kabul edilmelidir.

    İndis sözleşmesi: c hücre (mağaza × SKU, `cesit` satır sırası), s SKU
    (`urunler` satır sırası), o option (`optionlar` satır sırası), d gün
    (0 = ISINMA_BASLANGIC; `takvim` satır sırası). g dizileri
    D + UZATMA_GUN satırlıdır; simülasyon ilk D gününü koşar.
    """

    magazalar: pd.DataFrame
    urunler: pd.DataFrame
    tedarikciler: pd.DataFrame
    sezon: pd.DataFrame
    takvim: pd.DataFrame          # simülasyon takvimi (ısınma dahil)
    optionlar: pd.DataFrame       # option başına öznitelik + gün indisleri
    cesit: pd.DataFrame           # (magaza_id, urun_id), hücre sırası

    hucre_magaza: np.ndarray      # [C] mağaza indisi
    hucre_sku: np.ndarray         # [C] SKU indisi
    hucre_option: np.ndarray      # [C] option indisi
    sku_option: np.ndarray        # [S]
    sku_beden_payi: np.ndarray    # [S] zincir beden eğrisi payı (option içinde)

    plan_statik: np.ndarray       # [C]
    gercek_statik: np.ndarray     # [C]
    yerel_option: np.ndarray      # [C] yerel (mağaza × option) çarpanı
    yerel_beden_payi: np.ndarray  # [C]
    surpriz: np.ndarray           # [O]
    tau: np.ndarray               # [O] yaşam eğrisi τ (hafta)
    suruklenme: np.ndarray        # [O, hafta] çarpımsal AR(1) çarpanı
    g_plan: np.ndarray            # [D+U, O]
    g_gercek: np.ndarray          # [D+U, O]
    indirim_orani: np.ndarray     # [D+U, O] planlı fiyat indirimi

    sapma_ilk: np.ndarray         # [O] gün
    sapma_rpt: np.ndarray         # [O, RPT_SAPMA_SAYISI]
    sapma_surekli: np.ndarray     # [O, SUREKLI_SAPMA_SAYISI]

    plan_sezon: np.ndarray        # [O] lansman → indirim başı plan talebi
    ilk_alim: np.ndarray          # [O] (sezonluklar; devamlı 0)
    ilk_alim_sku: np.ndarray      # [S]
    ilk_dagitim_hucre: np.ndarray  # [C] ilk dağıtımda hücreye giden adet
    ilk_siparisler: list = field(default_factory=list)

    @property
    def gun_sayisi(self) -> int:
        return len(self.takvim)

    def beklenen_talep(self, d: int) -> np.ndarray:
        """d günü için bütün hücrelerin gerçek beklenen talebi (λ)."""
        return self.gercek_statik * self.g_gercek[d, self.hucre_option]

    def plan_talep(self, d: int) -> np.ndarray:
        """d günü için bütün hücrelerin plan talebi."""
        return self.plan_statik * self.g_plan[d, self.hucre_option]

    def ileri_plan(self, d: int, gun: int) -> np.ndarray:
        """[d, d+gun) plan talebinin hücre bazında toplamı."""
        return self.plan_statik * (
            self._g_plan_kum[d + gun, self.hucre_option] - self._g_plan_kum[d, self.hucre_option]
        )

    def ileri_plan_option(self, d: int, gun: int) -> np.ndarray:
        """[d, d+gun) zincir plan talebi, option bazında."""
        g = self._g_plan_kum[d + gun] - self._g_plan_kum[d]
        return self._plan_statik_option * g

    def __post_init__(self):
        self._g_plan_kum = np.vstack(
            [np.zeros((1, self.g_plan.shape[1])), np.cumsum(self.g_plan, axis=0)]
        )
        self._plan_statik_option = np.bincount(
            self.hucre_option, self.plan_statik, minlength=len(self.optionlar)
        )


# --- Kurulum adımları ---------------------------------------------------

def _cesit(rng, magazalar, urunler) -> pd.DataFrame:
    """Çeşit: devamlılar bir kez, her sezon kendi içinde (v2 `cesit_ata`).

    Mağaza her sezon koleksiyondan kendi payını seçer; aynı mağaza AW24'te
    başka, SS25'te başka modeller taşır. Beden ve renk bütünlüğü v2'deki
    gibi model düzeyinde korunur.
    """
    parcalar = [cesit_ata(rng, magazalar, urunler[urunler["sezon_kodu"] == sabitler.DEVAMLI])]
    for kod in sabitler.SEZONLAR:
        parcalar.append(cesit_ata(rng, magazalar, urunler[urunler["sezon_kodu"] == kod]))
    return pd.concat(parcalar, ignore_index=True)


def _optionlar(urunler, tedarikciler) -> pd.DataFrame:
    opt = urunler.drop_duplicates("option_id").reset_index(drop=True)[
        ["option_id", "model_kodu", "line", "cinsiyet", "ust_kategori", "alt_kategori",
         "sezon_kodu", "dalga", "lansman_tarihi", "cikis_tarihi", "tedarikci_id",
         "alis_fiyati", "liste_fiyati"]
    ].copy()
    opt = opt.merge(
        tedarikciler[["tedarikci_id", "mense", "ilk_siparis_hafta", "rpt_hafta", "moq_option"]],
        on="tedarikci_id", how="left",
    )
    sezonluk = opt["sezon_kodu"] != sabitler.DEVAMLI
    indirim = opt["sezon_kodu"].map(
        {k: pd.Timestamp(s["indirim"]) for k, s in sabitler.SEZONLAR.items()}
    )
    opt["sezonluk"] = sezonluk
    opt["indirim_tarihi"] = indirim
    buyuk = 10**6
    opt["lansman_gun"] = [gun_indisi(t) if s else -buyuk for t, s in zip(opt["lansman_tarihi"], sezonluk)]
    opt["indirim_gun"] = [gun_indisi(t) if s else buyuk for t, s in zip(indirim, sezonluk)]
    opt["cikis_gun"] = [gun_indisi(t) if s else buyuk for t, s in zip(opt["cikis_tarihi"], sezonluk)]
    return opt


def _g_carpanlari(rng, optionlar, takvim_uzun):
    """g_plan, g_gercek ve indirim oranı (gün × option) + rastgele parçalar."""
    D, O = len(takvim_uzun), len(optionlar)

    # Yaşam eğrisi τ: alt kategori başına bir kez ±%20
    altlar = list(sabitler.MEVSIM)
    tau_alt = {
        alt: sabitler.YASAM_TAU_HAFTA
        * float(rng.uniform(1 - sabitler.YASAM_TAU_OYNAMA, 1 + sabitler.YASAM_TAU_OYNAMA))
        for alt in altlar
    }
    tau = optionlar["alt_kategori"].map(tau_alt).to_numpy(dtype=float)

    # Ürün sürprizi: zincir düzeyinde, plan bilmez
    sigma = optionlar["line"].map(sabitler.SURPRIZ_SIGMA).to_numpy(dtype=float)
    surpriz = rng.lognormal(0.0, sigma)

    # Sürüklenme: haftalık AR(1), log uzayında durağan başlangıç
    hafta_sayisi = D // 7 + 1
    rho, s = sabitler.SURUKLENME_RHO, sabitler.SURUKLENME_SIGMA
    x = np.empty((O, hafta_sayisi))
    x[:, 0] = rng.normal(0.0, s / np.sqrt(1 - rho**2), size=O)
    eps = rng.normal(0.0, s, size=(O, hafta_sayisi - 1))
    for w in range(1, hafta_sayisi):
        x[:, w] = rho * x[:, w - 1] + eps[:, w - 1]
    suruklenme = np.exp(x)

    # Deterministik parçalar
    tarihler = pd.DatetimeIndex(takvim_uzun["tarih"])
    ay_kesirli = (tarihler.month + (tarihler.day - 1) / tarihler.days_in_month).to_numpy()
    gun_c = np.array(
        [v2_talep.gun_carpani(t.dayofweek, bool(tt)) for t, tt in zip(tarihler, takvim_uzun["tatil_mi"])]
    )
    buyume = np.array([sabitler.YIL_BUYUME.get(y, sabitler.YIL_BUYUME[2025]) for y in tarihler.year])
    gun = np.arange(D)[:, None]

    mevsim = np.empty((D, O))
    for (alt, line), idx in optionlar.groupby(["alt_kategori", "line"]).indices.items():
        mevsim[:, idx] = talep.mevsim_carpani(alt, line, ay_kesirli)[:, None]

    lansman = optionlar["lansman_gun"].to_numpy()
    indirim_gun = optionlar["indirim_gun"].to_numpy()
    cikis = optionlar["cikis_gun"].to_numpy()
    sezonluk = optionlar["sezonluk"].to_numpy()

    yasam = np.where(sezonluk[None, :], talep.yasam_egrisi((gun - lansman[None, :]) / 7.0, tau[None, :]), 1.0)
    oran, talep_c = talep.indirim_durumu(gun - indirim_gun[None, :])
    aktif = (gun >= lansman[None, :]) & (gun < cikis[None, :])
    oran = np.where(aktif & sezonluk[None, :], oran, 0.0)
    talep_c = np.where(sezonluk[None, :], talep_c, 1.0)

    g_plan = mevsim * yasam * talep_c * (gun_c * buyume)[:, None] * aktif
    g_gercek = g_plan * surpriz[None, :] * suruklenme[:, np.arange(D) // 7].T
    return g_plan, g_gercek, oran, surpriz, tau, suruklenme


def _ilk_alim(optionlar, urunler, hucre_option, hucre_sku, plan_statik, g_plan, sku_option, sku_pay):
    """Plan talebi, ilk alım (option ve SKU) ve ilk dağıtım (hücre)."""
    O = len(optionlar)
    kum = np.vstack([np.zeros((1, O)), np.cumsum(g_plan, axis=0)])
    lansman = optionlar["lansman_gun"].to_numpy()
    indirim = optionlar["indirim_gun"].to_numpy()
    sezonluk = optionlar["sezonluk"].to_numpy()
    idx = np.arange(O)
    g_sezon = np.where(sezonluk, kum[np.clip(indirim, 0, len(kum) - 1), idx] - kum[np.clip(lansman, 0, len(kum) - 1), idx], 0.0)
    plan_statik_o = np.bincount(hucre_option, plan_statik, minlength=O)
    plan_sezon = plan_statik_o * g_sezon

    moq = optionlar["moq_option"].to_numpy()
    ilk_alim = np.array(
        [moq_yuvarla(p / sabitler.HEDEF_TAM_FIYAT_STR, m) if s else 0
         for p, m, s in zip(plan_sezon, moq, sezonluk)], dtype=np.int64,
    )

    ilk_alim_sku = np.zeros(len(urunler), dtype=np.int64)
    ilk_dagitim = np.zeros(len(hucre_sku), dtype=np.int64)
    sku_hucreleri = pd.Series(np.arange(len(hucre_sku))).groupby(hucre_sku).apply(np.asarray)
    option_skulari = pd.Series(np.arange(len(sku_option))).groupby(sku_option).apply(np.asarray)
    for o in np.flatnonzero(sezonluk):
        skular = option_skulari[o]
        ilk_alim_sku[skular] = en_buyuk_kalan(int(ilk_alim[o]), sku_pay[skular])
        for s in skular:
            hucreler = sku_hucreleri.get(s)
            if hucreler is None:
                continue
            magazaya = int(round(sabitler.ILK_DAGITIM_PAYI * ilk_alim_sku[s]))
            ilk_dagitim[hucreler] = en_buyuk_kalan(magazaya, plan_statik[hucreler])
    return plan_sezon, ilk_alim, ilk_alim_sku, ilk_dagitim


def dunya_kur(rng: np.random.Generator | None = None) -> Dunya:
    """Dünyayı kurar. Tohum sırası sabittir; sıra değişirse v3 değişir."""
    rng = rng if rng is not None else akislar()["dunya"]

    magazalar = magazalari_uret(rng)
    tedarikciler = tedarikcileri_uret(rng)
    urunler = urunleri_uret(rng, tedarikciler)
    cesit = _cesit(rng, magazalar, urunler)

    cesit_urun = urunler.set_index("urun_id").loc[cesit["urun_id"]]
    cesit_magaza = magazalar.set_index("magaza_id").loc[cesit["magaza_id"]]

    ortak = (
        cesit_urun["ust_kategori"].map(v2_talep.TABAN_TALEP).to_numpy()
        * cesit_urun["cinsiyet"].map(v2_talep.CINSIYET_CARPANLARI).to_numpy()
        * cesit_urun["line"].map(v2_talep.LINE_HACIM_CARPANLARI).to_numpy()
        * cesit_urun["line"].map(sabitler.SEZONLUK_TEPE_CARPANI).to_numpy()
        * cesit_magaza["tip"].map(v2_talep.MAGAZA_TIPI_CARPANLARI).to_numpy()
    )
    zincir_payi = v2_talep.beden_dagilimi()
    k = len(zincir_payi)
    # Plan "sürprizsiz BEKLENEN talep"tir: hangi mağazada ve hangi option'da
    # tutacağını bilmez ama zincir geçmişinden ortalamayı bilir. Yerel
    # çarpanın ve sürprizin ortalaması (lognormal: exp(σ²/2) > 1) plana
    # girer; tek tek değerleri girmez.
    beklenen = {
        line: talep.yerel_carpan_beklenen(line) * talep.surpriz_beklenen(line)
        for line in v2_talep.LINE_HACIM_CARPANLARI
    }
    plan_statik = (
        ortak * cesit_urun["beden_sira"].map(zincir_payi).to_numpy() * k
        * cesit_urun["line"].map(beklenen).to_numpy()
    )

    egriler = _magaza_beden_egrileri(rng, magazalar)
    yerel_beden = np.array(
        [egriler[m][b] for m, b in zip(cesit_magaza.index, cesit_urun["beden_sira"])]
    )
    yerel_option = _yerel_option_carpani(rng, cesit_magaza, cesit_urun)
    gercek_statik = ortak * yerel_beden * k * yerel_option

    optionlar = _optionlar(urunler, tedarikciler)
    takvim = simulasyon_takvimi()
    takvim_uzun = pd.concat(
        [takvim, _uzatma_takvimi(takvim["tarih"].iloc[-1])], ignore_index=True
    )
    g_plan, g_gercek, oran, surpriz, tau, suruklenme = _g_carpanlari(rng, optionlar, takvim_uzun)

    # Teslim sapmaları: menşe başına bütün option'lar için çekilir, seçilir
    O = len(optionlar)
    uzak = (optionlar["mense"] == "Uzak Doğu").to_numpy()

    def _sapma(boyut):
        y = teslim_sapmasi(rng, "Yerli", boyut)
        u = teslim_sapmasi(rng, "Uzak Doğu", boyut)
        maske = uzak if np.ndim(y) == 1 else uzak[:, None]
        return np.where(maske, u, y)

    sapma_ilk = _sapma(O)
    sapma_rpt = _sapma((O, RPT_SAPMA_SAYISI))
    sapma_surekli = _sapma((O, sabitler.SUREKLI_SAPMA_SAYISI))

    option_indis = pd.Series(np.arange(O), index=optionlar["option_id"])
    sku_option = option_indis.loc[urunler["option_id"]].to_numpy()
    sku_indis = pd.Series(np.arange(len(urunler)), index=urunler["urun_id"])
    hucre_sku = sku_indis.loc[cesit["urun_id"]].to_numpy()
    magaza_indis = pd.Series(np.arange(len(magazalar)), index=magazalar["magaza_id"])
    hucre_magaza = magaza_indis.loc[cesit["magaza_id"]].to_numpy()
    hucre_option = sku_option[hucre_sku]
    sku_pay = urunler["beden_sira"].map(zincir_payi).to_numpy()

    plan_sezon, ilk_alim, ilk_alim_sku, ilk_dagitim = _ilk_alim(
        optionlar, urunler, hucre_option, hucre_sku, plan_statik, g_plan, sku_option, sku_pay
    )

    # İlk siparişler: lansmandan ilk sipariş süresi kadar önce verilir,
    # lansmandan bir hafta önce depoda olması planlanır.
    ilk_siparisler = []
    for o in np.flatnonzero(optionlar["sezonluk"].to_numpy()):
        lansman = int(optionlar.at[o, "lansman_gun"])
        planlanan = lansman - 7 * sabitler.PLANLANAN_TESLIM_ONCE_HAFTA
        ilk_siparisler.append(
            {
                "tip": "ilk",
                "option": int(o),
                "siparis_gun": lansman - 7 * int(optionlar.at[o, "ilk_siparis_hafta"]),
                "planlanan_gun": planlanan,
                "gerceklesen_gun": planlanan + int(sapma_ilk[o]),
                "skular": np.flatnonzero(sku_option == o),
                "adetler": ilk_alim_sku[sku_option == o],
            }
        )
    optionlar["ilk_dagitim_gun"] = -1
    for s in ilk_siparisler:
        optionlar.at[s["option"], "ilk_dagitim_gun"] = max(
            int(optionlar.at[s["option"], "lansman_gun"]), s["gerceklesen_gun"]
        )
    # Devamlılar simülasyonun ilk günü "dağıtılmış" sayılır (ısınma)
    optionlar.loc[~optionlar["sezonluk"], "ilk_dagitim_gun"] = 0
    optionlar["plan_sezon"] = plan_sezon
    optionlar["ilk_alim"] = ilk_alim
    optionlar["surpriz"] = surpriz
    optionlar["tau"] = tau

    return Dunya(
        magazalar=magazalar, urunler=urunler, tedarikciler=tedarikciler,
        sezon=sezon_tablosu(), takvim=takvim, optionlar=optionlar, cesit=cesit,
        hucre_magaza=hucre_magaza, hucre_sku=hucre_sku, hucre_option=hucre_option,
        sku_option=sku_option, sku_beden_payi=sku_pay,
        plan_statik=plan_statik, gercek_statik=gercek_statik,
        yerel_option=yerel_option, yerel_beden_payi=yerel_beden,
        surpriz=surpriz, tau=tau, suruklenme=suruklenme,
        g_plan=g_plan, g_gercek=g_gercek, indirim_orani=oran,
        sapma_ilk=sapma_ilk, sapma_rpt=sapma_rpt, sapma_surekli=sapma_surekli,
        plan_sezon=plan_sezon, ilk_alim=ilk_alim, ilk_alim_sku=ilk_alim_sku,
        ilk_dagitim_hucre=ilk_dagitim, ilk_siparisler=ilk_siparisler,
    )


def _uzatma_takvimi(son_tarih) -> pd.DataFrame:
    tarihler = pd.date_range(pd.Timestamp(son_tarih), periods=UZATMA_GUN + 1, freq="D")[1:]
    return pd.DataFrame({"tarih": tarihler, "tatil_mi": False})


def talep_matrisi(dunya: Dunya, rng: np.random.Generator | None = None) -> np.ndarray:
    """Günlük talep [D, C] (int16). Politikadan bağımsız; simülasyonun
    kendi çektiğiyle birebir aynıdır (aynı akış, aynı sıra: gün gün, her
    gün bütün hücreler, aktif olmayanlar λ = 0)."""
    rng = rng if rng is not None else akislar()["talep"]
    D, C = dunya.gun_sayisi, len(dunya.cesit)
    matris = np.empty((D, C), dtype=np.int16)
    for d in range(D):
        matris[d] = rng.poisson(dunya.beklenen_talep(d))
    return matris


def dunya_yeniden_kur() -> Dunya:
    """v2'deki `dunya_yeniden_kur`un karşılığı: simülasyonu koşmadan dünya."""
    return dunya_kur()
