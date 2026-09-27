"""Tedarik: 18 tedarikçi, gizli profil, teslim sapması, kalite kontrol,
Lumoda tedarikçi seçimi.

v3'te tedarikçi ilk siparişin ne kadar önce verileceğini, RPT'nin kaç
haftada geleceğini ve MOQ'yu belirliyordu — bunlar yayımlanan (`tedarikciler`)
tabloda kalır. v4 buna bir **gizli profil** ekler (`gizli_tedarikci`):
gecikme, hatalı oran, maliyet çarpanı, kapasite — hiçbiri dışa aktarılan
tablolara girmez (global kısıt: "gizli gerçek ... tedarikçi profili ...
dışa aktarılan tablolara girmez"). Lumoda'nın alışılmış
birincil/ikincil tedarikçi seçimi bu gizli profile bakmadan (yalnız kamuya
açık menşe/uzmanlık bilgisiyle) yapılır — ileride yazılacak bir algoritmanın
"yenmesi" gereken referans budur.

v4 hiçbir v2/v3/kök modülünü içe aktarmaz.

Spec: docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md §4.1-4.2
Brief: .superpowers/sdd/2026-09-27-veri-v4-cekirdek/task-6-brief.md
"""

import numpy as np
import pandas as pd

from . import sabitler


# ---------------------------------------------------------------------------
# Tedarikçiler ve gizli profil
# ---------------------------------------------------------------------------


def tedarikcileri_uret(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """18 tedarikçi: yayımlanan `tedarikciler` + gizli `gizli_tedarikci`.

    `tedarikciler`: tedarikci_id (T01…T18), ad, ulke, mense, ilk_siparis_hafta,
    rpt_hafta, moq_option, uzmanlik — hepsi kamuya açık (Lumoda'nın plan
    yaparken bildiği şeyler).

    `gizli_tedarikci`: tedarikci_id, mense (kolaylık için tekrar; zaten
    kamuya açık), gecikme_parametre_t (mense'e göre anlamı değişir: Yakın/
    Uzak Doğu'da beta ölçeği `olcek_t`, Yerli'de sabit kayma `bias_t` —
    bkz. `teslim_sapmasi`), gecikme_beklenen_gun (bunun analitik beklenen
    değeri), hatali_orani, maliyet_carpani, kapasite_sezon_adet —
    bunların hiçbiri Lumoda'nın plan aşamasında bildiği şeyler değildir;
    yalnız gerçekleşen teslimatlarda ortaya çıkar (bkz. `teslim_sapmasi`,
    `hatali_adet`).
    """
    beta_ortalama = sabitler.SAPMA_BETA[0] / sum(sabitler.SAPMA_BETA)

    tedarikci_satirlari = []
    gizli_satirlari = []
    for sira, (ad, ulke, mense, uzmanlik) in enumerate(sabitler.TEDARIKCI_TANIMLARI, start=1):
        m = sabitler.MENSE_V4[mense]
        tedarikci_id = f"T{sira:02d}"
        tedarikci_satirlari.append(
            {
                "tedarikci_id": tedarikci_id,
                "ad": ad,
                "ulke": ulke,
                "mense": mense,
                "ilk_siparis_hafta": int(rng.integers(m["ilk"][0], m["ilk"][1] + 1)),
                "rpt_hafta": int(rng.integers(m["rpt"][0], m["rpt"][1] + 1)),
                "moq_option": m["moq"],
                "uzmanlik": uzmanlik,
            }
        )

        hatali_orani = sabitler.HATALI_ORANI_ARALIGI[0] + rng.beta(
            *sabitler.HATALI_ORANI_BETA
        ) * (sabitler.HATALI_ORANI_ARALIGI[1] - sabitler.HATALI_ORANI_ARALIGI[0])

        if mense == "Yerli":
            parametre = float(rng.uniform(*sabitler.YERLI_BIAS_ARALIGI))
            beklenen = parametre
        else:
            parametre = float(rng.uniform(*sabitler.OLCEK_T_ARALIGI))
            beklenen = parametre * m["sapma_maks"] * beta_ortalama

        gizli_satirlari.append(
            {
                "tedarikci_id": tedarikci_id,
                "mense": mense,
                "gecikme_parametre_t": parametre,
                "gecikme_beklenen_gun": float(beklenen),
                "hatali_orani": float(hatali_orani),
                "maliyet_carpani": float(rng.uniform(*sabitler.MALIYET_CARPANI_ARALIGI[mense])),
                "kapasite_sezon_adet": int(
                    rng.uniform(*sabitler.KAPASITE_SEZON_ARALIGI[mense]) // 100 * 100
                ),
            }
        )

    tedarikciler = pd.DataFrame(tedarikci_satirlari)
    gizli_tedarikci = pd.DataFrame(gizli_satirlari)
    return tedarikciler, gizli_tedarikci


# ---------------------------------------------------------------------------
# Lumoda tedarikçi seçimi
# ---------------------------------------------------------------------------


def lumoda_tedarikci_secimi(
    rng: np.random.Generator,
    optionlar: pd.DataFrame,
    tedarikciler: pd.DataFrame,
    gizli: pd.DataFrame,
    talep_tahmini: np.ndarray,
) -> np.ndarray:
    """Option başına tedarikçi indisi (0-tabanlı, `tedarikciler` satır sırası).

    Politika olarak enjekte edilebilir imza (`dunya.TedarikciSecimi`):
    `Callable[[rng, optionlar, tedarikciler, kapasite, talep_tahmini],
    np.ndarray]`. `dunya_kur` üçüncü tablo olarak gizli profilin yalnız
    **kapasite görünümünü** verir (`tedarikci_id`, `kapasite_sezon_adet`;
    alıcının bildiği bilgi) — gecikme, hatalı oran, maliyet çarpanı
    politikaya hiç ulaşmaz. Bu fonksiyon da yalnız `kapasite_sezon_adet`'i
    okur.

    Alt kategori başına **bir kez** (rng ile, gizli profile hiç bakmadan)
    sabit bir birincil ve ikincil tedarikçi çekilir: mont/jean/ceket/
    trençkot'ta %60 olasılıkla havuz yalnız Uzak Doğu'dur; kamuya açık
    uzmanlık alanı alt kategoriyle eşleşen tedarikçiye ağırlık verilir
    (bu da kamu bilgisidir — gizli performansa bakmak değildir).

    Sonra her option birincile gider; birincinin o sezon için kapasitesi
    (`gizli.kapasite_sezon_adet`, `talep_tahmini` ile ölçülür) dolarsa
    ikinciye taşar. Kapasite kontrolü kümülatiftir: aynı birincile atanan
    farklı alt kategorilerin talebi aynı havuzu paylaşır.

    Taşma zinciri (fix round 1 — controller kararı): ikincil de dolarsa,
    önce kamuya açık uzmanlık alanı alt kategoriyle eşleşen tedarikçiler
    arasında o sezon için en çok kalan kapasitesi olana, orada da yer
    yoksa herhangi bir tedarikçide kalan kapasitesi olana taşar. Hepsi
    doluysa ikincilde kalır (aşım kabul edilir — üçüncü bir "sabit" taşma
    hedefi yok, çünkü Lumoda'nın gerçek hayattaki alışkanlığı budur: en
    kötü ihtimalde alışılmış ikinci tedarikçiye fazladan sipariş vermek).

    Tasarım kararı: DEVAMLI (sürekli) option'lar kapasiteye tabi değildir
    (her zaman birincile gider) — "yıllık kapasiteyi iki sezona eşit
    bölme" yerine seçilen basit alternatif; DEVAMLI zaten sürekli küçük
    partiler halinde sipariş edilir, sezonluk kapasite baskısı NOS/Basic
    için ayrı bir kavram gerektirir ki spec bunu istemez.
    """
    O = len(optionlar)
    alt_arr = optionlar["alt_kategori"].to_numpy()
    sezon_arr = optionlar["sezon_kodu"].to_numpy()
    talep = np.asarray(talep_tahmini)

    mense_arr = tedarikciler["mense"].to_numpy()
    uzmanlik_arr = tedarikciler["uzmanlik"].to_numpy()
    tum_idx = np.arange(len(tedarikciler))

    birincil: dict[str, int] = {}
    ikincil: dict[str, int] = {}
    for alt in sorted(pd.unique(alt_arr)):
        alan = sabitler.ALT_KATEGORI_ALAN.get(alt)
        havuz = tum_idx
        if (
            alt in sabitler.LUMODA_UZAK_DOGU_ALT_KATEGORILERI
            and rng.random() < sabitler.LUMODA_UZAK_DOGU_HAVUZ_OLASILIGI
        ):
            havuz = tum_idx[mense_arr == "Uzak Doğu"]

        agirlik = np.where(
            uzmanlik_arr[havuz] == alan, sabitler.LUMODA_UZMANLIK_AGIRLIGI, 1.0
        )
        agirlik = agirlik / agirlik.sum()

        n_sec = min(2, len(havuz))
        secilen = rng.choice(havuz, size=n_sec, replace=False, p=agirlik)
        birincil[alt] = int(secilen[0])
        ikincil[alt] = int(secilen[1]) if n_sec > 1 else int(secilen[0])

    kapasite = gizli["kapasite_sezon_adet"].to_numpy()
    kullanim: dict[tuple[int, str], float] = {}
    secim = np.empty(O, dtype=np.int64)

    def _kalan(aday: int, sezon: str) -> float:
        return kapasite[aday] - kullanim.get((aday, sezon), 0.0)

    def _en_bos(havuz: np.ndarray, sezon: str) -> int | None:
        kalanlar = [(_kalan(a, sezon), a) for a in havuz]
        kalanlar = [x for x in kalanlar if x[0] > 0]
        if not kalanlar:
            return None
        kalanlar.sort(key=lambda x: x[0], reverse=True)
        return kalanlar[0][1]

    for o in range(O):
        alt = alt_arr[o]
        b = birincil[alt]
        if sezon_arr[o] == sabitler.DEVAMLI:
            secim[o] = b
            continue

        sezon = sezon_arr[o]
        ik = ikincil[alt]
        secildi = None
        for aday in (b, ik):
            if _kalan(aday, sezon) >= talep[o]:
                secildi = aday
                break

        if secildi is None:
            alan = sabitler.ALT_KATEGORI_ALAN.get(alt)
            uzmanlik_havuzu = tum_idx[uzmanlik_arr == alan] if alan else tum_idx[:0]
            secildi = _en_bos(uzmanlik_havuzu, sezon)
            if secildi is None:
                secildi = _en_bos(tum_idx, sezon)
            if secildi is None:
                secildi = ik  # hepsi dolu: alışılmış ikincilde kal (aşım kabul)

        secim[o] = secildi
        anahtar = (secildi, sezon)
        kullanim[anahtar] = kullanim.get(anahtar, 0.0) + talep[o]

    return secim


# ---------------------------------------------------------------------------
# Teslim sapması
# ---------------------------------------------------------------------------


def teslim_sapmasi(
    rng: np.random.Generator, gizli: pd.DataFrame, tedarikci_idx: np.ndarray, n: int
) -> np.ndarray:
    """Option başına `n` adet önceden çekilen sapma (gerçekleşen − planlanan,
    gün); v3'ün sayıları çağıran tarafça verilir (ilk: n=1, RPT: n=4,
    sürekli: n=128).

    Şekil brief'in beta biçimini korur (v3'ün UZAK_DOGU_SAPMA_BETA'sıyla
    aynı Beta(1,3; 3,5)); tedarikçi düzeyinde farklılaşma yalnız gizli
    `gecikme_parametre_t`'den gelen bir ölçek/kayma ile eklenir, sonra
    menşenin ilan edilmiş sınırına (`MENSE_V4` sapma_min/maks) kırpılır:

    - Uzak Doğu / Yakın: `round(olcek_t × sapma_maks × Beta(1.3, 3.5))`,
      sağa çarpık (çoğu teslim birkaç gün, bazen üç hafta gecikir),
      kırpma 0…sapma_maks'ı garanti eder (hiç erken gelmez).
    - Yerli: `round(bias_t + tam sayı gürültü [-2, +2])`, kırpma ±3'ü
      garanti eder (simetrik, ±3 gün).
    """
    tedarikci_idx = np.asarray(tedarikci_idx)
    O = len(tedarikci_idx)
    mense = gizli["mense"].to_numpy()[tedarikci_idx]
    parametre = gizli["gecikme_parametre_t"].to_numpy()[tedarikci_idx]
    sapma = np.zeros((O, n), dtype=np.int64)

    yerli = mense == "Yerli"
    if yerli.any():
        bias = parametre[yerli][:, None]
        gurultu = rng.integers(
            -sabitler.YERLI_GURULTU_MAKS_GUN, sabitler.YERLI_GURULTU_MAKS_GUN + 1,
            size=(int(yerli.sum()), n),
        )
        m = sabitler.MENSE_V4["Yerli"]
        ham = np.rint(bias + gurultu)
        sapma[yerli] = np.clip(ham, m["sapma_min"], m["sapma_maks"]).astype(np.int64)

    for mense_adi in ("Yakın", "Uzak Doğu"):
        maske = mense == mense_adi
        if not maske.any():
            continue
        m = sabitler.MENSE_V4[mense_adi]
        olcek = parametre[maske][:, None]
        beta = rng.beta(*sabitler.SAPMA_BETA, size=(int(maske.sum()), n))
        ham = np.rint(olcek * m["sapma_maks"] * beta)
        sapma[maske] = np.clip(ham, m["sapma_min"], m["sapma_maks"]).astype(np.int64)

    return sapma


# ---------------------------------------------------------------------------
# Kalite kontrol
# ---------------------------------------------------------------------------


def hatali_adet(
    rng: np.random.Generator,
    gizli: pd.DataFrame,
    tedarikci_idx: np.ndarray,
    adet: np.ndarray,
    uyum: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Her teslimat için (numune, hatalı) adedi.

    Numune = min(adet, 32 + adet // 50); hatalı oran numunede Binomial ile
    çekilir (`gizli.hatali_orani`, uzmanlıkta `uyum` ile ×0,7), teslimatın
    tamamına aynı oranla uygulanır (yuvarlama aşağı) — `kalite_kontrol`
    mantığı (spec §4.2): hatalı adet satışa çıkmaz, depoya giren = adet −
    hatalı.
    """
    tedarikci_idx = np.asarray(tedarikci_idx)
    adet = np.asarray(adet)
    numune = np.minimum(adet, sabitler.NUMUNE_TABAN + adet // sabitler.NUMUNE_BOLEN)

    oran = gizli["hatali_orani"].to_numpy()[tedarikci_idx]
    if uyum is not None:
        oran = np.where(np.asarray(uyum, dtype=bool), oran * sabitler.UZMANLIK_HATALI_CARPANI, oran)

    hatali_numune = rng.binomial(numune, oran)
    hatali_oran_gozlenen = np.divide(
        hatali_numune, numune, out=np.zeros(numune.shape, dtype=float), where=numune > 0
    )
    hatali = np.floor(adet * hatali_oran_gozlenen).astype(np.int64)
    return numune, hatali


# ---------------------------------------------------------------------------
# Fiyat (Görev 11 için saf yardımcı)
# ---------------------------------------------------------------------------


def alis_fiyati_uygula(
    alis: np.ndarray, maliyet_carpani: np.ndarray, uzmanlik_uyumu: np.ndarray
) -> np.ndarray:
    """Alış fiyatına tedarikçi çarpanını (ve uzmanlık eşleşmesinde %7
    indirimi) uygular: `alis × maliyet_carpani × (0.93 if uyum else 1.0)`.

    Saf fonksiyon — Görev 11 `urunler`/`optionlar` alış fiyatını burada
    değil kendi montaj adımında günceller (bu görev yalnız yardımcıyı
    sağlar, uygulamaz)."""
    alis = np.asarray(alis, dtype=float)
    maliyet_carpani = np.asarray(maliyet_carpani, dtype=float)
    uyum_carpani = np.where(
        np.asarray(uzmanlik_uyumu, dtype=bool), sabitler.UZMANLIK_MALIYET_CARPANI, 1.0
    )
    return alis * maliyet_carpani * uyum_carpani
