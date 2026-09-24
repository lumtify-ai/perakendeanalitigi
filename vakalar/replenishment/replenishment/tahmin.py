"""LightGBM tahmincisi: tek küresel model, her karar gününde genişleyen
pencereyle yeniden eğitilir, option-mağaza (OC) başına önümüzdeki 7 günün
satış toplamını öngörür.

`ozellik_tablosu` yalnız `karar_gunu` dahil geçmişi ve önceden bilinen
takvimi (tatil günleri) kullanır — hiçbir özellik gelecekteki satışa
dokunmaz. `egitim_seti` her eğitim örneğinin hedefini `son_karar_gunu`'nü
aşmayan bir pencereye kırpar; böylece `tahmin_et`'in her çağrıda yaptığı
yeniden eğitim de sızıntısız kalır.

Kategorik sütunlar (`line`, `kategori`, `magaza_tipi`) `dunya`'nın tüm
option-mağaza hücrelerindeki benzersiz değerlerinden türetilen SABİT bir
kategori listesiyle kodlanır (`_kategori_listeleri`) — çağrıdan çağrıya
farklı bir alt küme görülse bile aynı kategori kodları üretilir.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import lightgbm as lgb

from .dunya import Dunya
from .ihtiyac import haftalik

OZELLIKLER = [
    "lag1", "lag2", "lag3", "lag4", "ort4", "ort8", "zincir_lag1",
    "line", "kategori", "magaza_tipi", "tatil_gunu",
]

_LGBM_SABIT = {
    "objective": "poisson",
    "random_state": 0,
    "deterministic": True,
    "num_threads": 1,
    "verbosity": -1,
    "force_row_wise": True,
}


def _kategori_listeleri(dunya: Dunya) -> dict[str, list]:
    return {
        "line": sorted(np.unique(dunya.oc_line).tolist()),
        "kategori": sorted(np.unique(dunya.oc_kategori).tolist()),
        "magaza_tipi": sorted(np.unique(dunya.oc_magaza_tipi).tolist()),
    }


def ozellik_tablosu(satis: np.ndarray, dunya: Dunya, karar_gunu: int) -> pd.DataFrame:
    """OC başına bir satır; karar_gunu itibarıyla özellikler. line/kategori/
    magaza_tipi pandas 'category' (sabit kategori listesiyle)."""
    OC = dunya.oc_hucre.shape[0]
    hafta8 = haftalik(satis, dunya, karar_gunu, 8)  # (8, OC), en yeni son satırda

    lag1, lag2, lag3, lag4 = hafta8[-1], hafta8[-2], hafta8[-3], hafta8[-4]
    ort4 = hafta8[-4:].mean(axis=0)
    ort8 = hafta8.mean(axis=0)
    zincir_lag1 = np.full(OC, lag1.sum(), dtype=float)

    bas = karar_gunu + 1
    bit = karar_gunu + 7
    tatil_sayisi = float(dunya.tatil[bas : bit + 1].sum())
    tatil_gunu = np.full(OC, tatil_sayisi, dtype=float)

    kategoriler = _kategori_listeleri(dunya)

    df = pd.DataFrame(
        {
            "lag1": lag1,
            "lag2": lag2,
            "lag3": lag3,
            "lag4": lag4,
            "ort4": ort4,
            "ort8": ort8,
            "zincir_lag1": zincir_lag1,
            "line": pd.Categorical(dunya.oc_line, categories=kategoriler["line"]),
            "kategori": pd.Categorical(dunya.oc_kategori, categories=kategoriler["kategori"]),
            "magaza_tipi": pd.Categorical(dunya.oc_magaza_tipi, categories=kategoriler["magaza_tipi"]),
            "tatil_gunu": tatil_gunu,
        }
    )
    return df[OZELLIKLER]


def egitim_seti(
    satis: np.ndarray, dunya: Dunya, son_karar_gunu: int, ilk_karar_gunu: int
) -> tuple[pd.DataFrame, np.ndarray]:
    """ilk_karar_gunu'nden son_karar_gunu − 7'ye kadar her pazartesi t' için
    özellikler(t') ve hedef = satış(t'+1 .. t'+7) option-mağaza toplamı.
    Hedef penceresi son_karar_gunu'nü aşmaz (sızıntı yok)."""
    pazartesiler = list(range(ilk_karar_gunu, son_karar_gunu - 7 + 1, 7))

    if not pazartesiler:
        return pd.DataFrame(columns=OZELLIKLER), np.zeros(0, dtype=float)

    X_parcalar = []
    y_parcalar = []
    for t in pazartesiler:
        X_parcalar.append(ozellik_tablosu(satis, dunya, t))
        y_parcalar.append(haftalik(satis, dunya, t + 7, 1)[0])

    X = pd.concat(X_parcalar, ignore_index=True)
    for sutun in ("line", "kategori", "magaza_tipi"):
        X[sutun] = X[sutun].astype(X_parcalar[0][sutun].dtype)
    y = np.concatenate(y_parcalar)
    return X, y


_KATEGORIK_SUTUNLAR = ["line", "kategori", "magaza_tipi"]


def _model_egit(parametreler: dict, X: pd.DataFrame, y: np.ndarray) -> lgb.Booster:
    """Yerel (native) LightGBM API — scikit-learn sarmalayıcısı (`LGBMRegressor`)
    scikit-learn'e bağımlıdır ve bu ortamda mevcut değil; `Dataset`/`train`
    hiçbir ek bağımlılık gerektirmeden aynı determinizm garantilerini verir."""
    parametreler_lgbm = {
        "num_leaves": parametreler["num_leaves"],
        "learning_rate": parametreler["learning_rate"],
        "min_child_samples": parametreler["min_child_samples"],
        **_LGBM_SABIT,
    }
    veri = lgb.Dataset(X, label=y, categorical_feature=_KATEGORIK_SUTUNLAR, free_raw_data=False)
    return lgb.train(parametreler_lgbm, veri, num_boost_round=parametreler["n_estimators"])


def _poisson_sapma(y: np.ndarray, tahmin: np.ndarray) -> float:
    """Ortalama Poisson sapması (deviance); tahmin sıfıra kırpılmış olabileceği
    için pay sıfıra bölünmesin diye küçük bir taban (eps) uygulanır."""
    eps = 1e-6
    t = np.clip(tahmin, eps, None)
    terim = np.where(y > 0, y * np.log(y / t) - (y - t), t)
    return float(2.0 * terim.mean())


@dataclass
class Tahminci:
    parametreler: dict  # num_leaves, n_estimators, learning_rate, min_child_samples
    ilk_karar_gunu: int  # eğitimde kullanılan ilk pazartesi (2025-02-03 → gün 33)

    def tahmin_et(self, satis: np.ndarray, dunya: Dunya, karar_gunu: int) -> np.ndarray:
        """Eğitim örneği yoksa veya hedefin tamamı sıfırsa (LightGBM'in
        'poisson' objective'i bunu `LightGBMError("sum of labels is
        zero")` ile reddeder) sabit 0 döner — bu iki durum açıkça
        kontrol edilir, genel bir `except` ile *herhangi* bir eğitim
        hatası (özellik/dtype uyuşmazlığı, bellek hatası, LightGBM API
        değişikliği) yutulmaz; öyle bir hata gerçek bir istisna olarak
        yükselir."""
        OC = dunya.oc_hucre.shape[0]
        X_egit, y_egit = egitim_seti(satis, dunya, karar_gunu, self.ilk_karar_gunu)

        if len(y_egit) == 0 or y_egit.sum() == 0:
            return np.zeros(OC, dtype=float)

        X_tahmin = ozellik_tablosu(satis, dunya, karar_gunu)
        model = _model_egit(self.parametreler, X_egit, y_egit)
        tahmin = model.predict(X_tahmin)

        tahmin = np.asarray(tahmin, dtype=float)
        tahmin = np.nan_to_num(tahmin, nan=0.0, posinf=0.0, neginf=0.0)
        return np.clip(tahmin, 0, None)


def hiperparametre_sec(satis: np.ndarray, dunya: Dunya, bit_gunu: int) -> dict:
    """Izgara: num_leaves {15, 31} × n_estimators {200, 400}, lr 0.05,
    min_child_samples 50, objective 'poisson'. Zaman sıralı doğrulama:
    bit_gunu'nden önceki son 8 pazartesi doğrulama, öncesi eğitim.
    Ölçüt: ortalama Poisson sapması. En küçüğü döner."""
    adim = 7
    ilk_pazartesi = bit_gunu % adim
    pazartesiler = list(range(ilk_pazartesi, bit_gunu, adim))
    if len(pazartesiler) < 9:
        raise ValueError("hiperparametre_sec icin yeterli pazartesi yok (en az 9 gerekir)")

    dogrulama = pazartesiler[-8:]
    egitim_ilk = pazartesiler[0]
    egitim_son = dogrulama[0]

    X_egit, y_egit = egitim_seti(satis, dunya, egitim_son, egitim_ilk)

    izgara = [
        {"num_leaves": nl, "n_estimators": ne, "learning_rate": 0.05, "min_child_samples": 50}
        for nl in (15, 31)
        for ne in (200, 400)
    ]

    en_iyi_parametreler = izgara[0]
    en_iyi_skor = np.inf
    for parametreler in izgara:
        model = _model_egit(parametreler, X_egit, y_egit)
        skorlar = []
        for t in dogrulama:
            X_val = ozellik_tablosu(satis, dunya, t)
            y_val = haftalik(satis, dunya, t + 7, 1)[0]
            tahmin = np.clip(np.asarray(model.predict(X_val), dtype=float), 0, None)
            skorlar.append(_poisson_sapma(y_val, tahmin))
        skor = float(np.mean(skorlar))
        if skor < en_iyi_skor:
            en_iyi_skor = skor
            en_iyi_parametreler = parametreler

    return en_iyi_parametreler
