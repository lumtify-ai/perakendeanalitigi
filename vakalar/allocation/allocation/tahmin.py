"""LightGBM (Poisson) mağaza x option erken talep tahmincisi: geçmişi olmayan yeni bir option'ın her
mağazadaki ilk 6 haftalık talebi, option'ın açık öznitelikleri, mağazanın özellikleri ve mağazanın
geçmiş satış karışımından.

Kural: bu modül gizli gerçeğe (`perakende_veri`), motora (`allocation.motor`) ve hakeme dokunmaz;
girdisi `ogrenme.ogrenme_tablosu` (karar gününe kadar kapanmış sezonlar) ve dünyanın açık
`magazalar` tablosudur.

**Eğitim.** Hedef `talep` (sansür düzeltmeli erken talep, benzer ürün endeksindeki tanım);
`stoklu_gun = 0` satırı (talep NaN) eğitim dışıdır. Tablonun bütün kapanmış sezonları kullanılır:
mevsim (`sezon_tipi`: SS ya da AW) bir özelliktir, ayrı model yoktur. Nesne Poisson, hedef
kesirli olabilir (düzeltilmiş talep); iş parçacığı sayısı ve tohum sabit, `deterministic` açık.

**Özellikler** (`ozellikler`; eğitim ve tahmin satırı için aynı fonksiyon):

    option      ust_kategori, alt_kategori, fiyat_segmenti, kalip, kumas, renk, desen,
                cinsiyet (LightGBM kategorisi); dalga, liste_fiyati, ilk_alim (sayı);
                sezon_tipi (kategori)
    mağaza      magaza_tip, magaza_bolge, magaza_sehir (kategori); metrekare, kapasite (sayı)
    karışım     pay_alt_kategori, pay_kalip, pay_fiyat_segmenti: mağazanın geçmiş erken
                talebinin o option'ın alt kategorisine / kalıbına / fiyat segmentine düşen payı

**Karışım ve sızıntı.** `karisim(tablo)` her mağazanın erken talebinin payını (alt kategori, kalıp,
fiyat segmenti için ayrı) yalnız verilen öğrenme tablosundan hesaplar. Eğitim satırı için payı
doğrudan tüm tablodan almak, satırın kendi hedefini özelliğine karıştırır (tahmin anında yeni
option'ın talebi geçmişte yoktur). Bu yüzden eğitim özelliği option'a göre K katlamalıdır
(`egitim_ozellikleri`, K = `KARISIM_KATI`): option'lar tohumlu bir permütasyonla katlara bölünür
ve bir satırın payı, kendi katının option'ları dışında kalanlardan hesaplanır. Tahmin satırı
tüm tablonun karışımını kullanır (`Tahminci.gecmis_karisim`). Mağazanın geçmişi yoksa (yeni açılan)
pay eksik (NaN) kalır, mağaza biliniyor ama değer hiç görülmemişse 0'dır.

**Doğrulama** (`dogrula`; `Tahminci.dogrulama`): option'lara göre (satıra göre değil) tutulan
%20'lik kümede ortalama Poisson sapması, mağaza ortalaması taban çizgisiyle birlikte. Ayrıca
pay sapması: her option'ın tahmini, o option'ın gerçek toplam talebine ölçeklenerek (yalnız mağaza
paylarının kalitesini ölçer; kapsama tavanı için mutlak düzey ayrıca `sapma_model`'de).

**Kimlik** (`Tahminci.sabitle`, `kimlik`): `booster.model_to_string()`, kanonik JSON parametreler ve
geçmiş karışımın içeriğinin SHA-256'sı; pickle baytı değil (RPT'nin pickle kimliği dersi: süreçler
arasında koşu önbelleği kırılıyordu). Politika bu kimliği koşu parametrelerine koyar.
"""

import dataclasses
import hashlib
import json
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

OPTION_KATEGORIK = ("ust_kategori", "alt_kategori", "fiyat_segmenti", "kalip", "kumas", "renk", "desen",
                    "cinsiyet")
OPTION_SAYISAL = ("dalga", "liste_fiyati", "ilk_alim")
KARISIM_OZELLIKLERI = ("alt_kategori", "kalip", "fiyat_segmenti")
PAY_SUTUNLARI = [f"pay_{s}" for s in KARISIM_OZELLIKLERI]
OZELLIKLER = [
    *OPTION_KATEGORIK, "sezon_tipi", *OPTION_SAYISAL,
    "magaza_tip", "magaza_bolge", "magaza_sehir", "metrekare", "kapasite",
    *PAY_SUTUNLARI,
]
KATEGORIK = [*OPTION_KATEGORIK, "sezon_tipi", "magaza_tip", "magaza_bolge", "magaza_sehir"]

KARISIM_KATI = 5          # eğitim karışımının option'a göre kat sayısı
KATLAMA_TOHUMU = 20261019
DOGRULAMA_PAYI = 0.20     # doğrulamada tutulan option payı
DOGRULAMA_TOHUMU = 7
EN_AZ_DOGRULAMA_OPTION = 5

VARSAYILAN = {"num_leaves": 31, "learning_rate": 0.05, "n_estimators": 400, "min_child_samples": 20}
_LGBM_SABIT = {
    "objective": "poisson",
    "seed": 0,
    "deterministic": True,
    "num_threads": 4,
    "verbosity": -1,
    "force_row_wise": True,
}


# ---------------------------------------------------------------------------
# Karışım
# ---------------------------------------------------------------------------


def _kullanilabilir(tablo: pd.DataFrame) -> pd.DataFrame:
    """Eğitime ve karışıma girebilen satırlar: stoklu günü olan, talebi bilinen."""
    return tablo[(tablo["stoklu_gun"] > 0).to_numpy() & tablo["talep"].notna().to_numpy()]


def karisim(tablo: pd.DataFrame) -> pd.DataFrame:
    """Mağazanın erken talebinin alt kategori / kalıp / fiyat segmenti payları.

    `tablo` öğrenme tablosudur (yalnız stoklu günü olan satırlar sayılır; talep sansür düzeltmeli).
    Dönüş uzun biçim: `magaza, ozellik, deger, pay`; `pay` o mağazanın toplam talebi içinde
    (özellik, değer) kümesinin payı, mağaza ve özellik başına 1'e toplanır. Mağazanın toplam
    talebi 0 ise payı NaN'dır (bilgi yok)."""
    t = _kullanilabilir(tablo)
    parcalar = []
    for s in KARISIM_OZELLIKLERI:
        g = t.groupby(["magaza", s])["talep"].sum()
        toplam = g.groupby(level=0).transform("sum")
        pay = (g / toplam.where(toplam > 0)).rename("pay").reset_index().rename(columns={s: "deger"})
        pay.insert(1, "ozellik", s)
        parcalar.append(pay)
    df = pd.concat(parcalar, ignore_index=True) if parcalar else pd.DataFrame(
        columns=["magaza", "ozellik", "deger", "pay"])
    df["magaza"] = df["magaza"].astype(np.int64)
    df["deger"] = df["deger"].astype(str)
    return df.sort_values(["magaza", "ozellik", "deger"], ignore_index=True)[["magaza", "ozellik", "deger", "pay"]]


def _paylar(satirlar: pd.DataFrame, gecmis_karisim: pd.DataFrame) -> pd.DataFrame:
    """Satırların (mağaza, özellik değeri) payları: `PAY_SUTUNLARI`, satırlarla aynı sırada."""
    bilinen = set(gecmis_karisim.loc[gecmis_karisim["pay"].notna(), "magaza"].tolist())
    magaza = satirlar["magaza"].to_numpy().astype(np.int64)
    biliniyor = np.fromiter((m in bilinen for m in magaza), dtype=bool, count=len(magaza))
    cikti = {}
    for s, ad in zip(KARISIM_OZELLIKLERI, PAY_SUTUNLARI):
        k = gecmis_karisim[gecmis_karisim["ozellik"] == s].set_index(["magaza", "deger"])["pay"]
        anahtar = pd.MultiIndex.from_arrays([magaza, satirlar[s].astype(str).to_numpy()])
        pay = k.reindex(anahtar).to_numpy(dtype=np.float64)
        cikti[ad] = np.where(biliniyor & np.isnan(pay), 0.0, pay)
    return pd.DataFrame(cikti, index=satirlar.index)


# ---------------------------------------------------------------------------
# Özellikler
# ---------------------------------------------------------------------------


def _kategori(degerler) -> pd.Categorical:
    return pd.Categorical(np.asarray(degerler).astype(str))


def ozellikler(tablo: pd.DataFrame, magazalar: pd.DataFrame, gecmis_karisim: pd.DataFrame) -> pd.DataFrame:
    """Satır başına özellikler (`OZELLIKLER`, `tablo`nun indeksiyle). Eğitim ve tahmin için aynı.

    tablo           `magaza` (mağaza indisi: `magazalar`ın satır konumu) ve option öznitelikleri
                    (`ogrenme.OZNITELIKLER`, `ilk_alim`) sütunları; talep gerekmez
    magazalar       dünyanın `magazalar` tablosu (`tip, bolge, sehir, metrekare, kapasite`)
    gecmis_karisim  `karisim(...)`; eğitim satırında `egitim_ozellikleri` option'a göre katlar

    Kategorikler `category` dtype (kategori listesi çağrıdaki değerlerden; LightGBM tahminde
    eğitimin listesine eşler, görülmemiş değer eksik sayılır)."""
    idx = tablo["magaza"].to_numpy().astype(np.int64)
    if len(idx) and (idx.min() < 0 or idx.max() >= len(magazalar)):
        raise ValueError(f"mağaza indisi 0..{len(magazalar) - 1} dışında")
    df = pd.DataFrame(index=tablo.index)
    for s in OPTION_KATEGORIK:
        df[s] = _kategori(tablo[s])
    df["sezon_tipi"] = _kategori(tablo["sezon_kodu"].astype(str).str[:2])
    for s in OPTION_SAYISAL:
        df[s] = tablo[s].to_numpy(dtype=np.float64)
    for s in ("tip", "bolge", "sehir"):
        df[f"magaza_{s}"] = _kategori(magazalar[s].to_numpy()[idx])
    for s in ("metrekare", "kapasite"):
        df[s] = magazalar[s].to_numpy(dtype=np.float64)[idx]
    df[PAY_SUTUNLARI] = _paylar(tablo, gecmis_karisim)
    return df[OZELLIKLER]


def option_katlari(optionlar: np.ndarray, kat: int = KARISIM_KATI, tohum: int = KATLAMA_TOHUMU) -> pd.Series:
    """option indisi -> kat (0..kat-1): tohumlu permütasyon, katlar dengeli (en çok bir fark)."""
    u = np.unique(np.asarray(optionlar, dtype=np.int64))
    kat = min(kat, len(u))
    sira = np.random.default_rng(tohum).permutation(len(u))
    k = np.empty(len(u), dtype=np.int64)
    k[sira] = np.arange(len(u)) % kat
    return pd.Series(k, index=u)


def egitim_ozellikleri(tablo: pd.DataFrame, magazalar: pd.DataFrame,
                       kat: int = KARISIM_KATI) -> tuple[pd.DataFrame, np.ndarray]:
    """(X, y): eğitime girebilen satırların (stoklu günü olan) özellikleri ve hedefi (`talep`).

    Karışım özellikleri option'a göre katlamalıdır (modül notu): satırın payı, kendi katının
    option'ları dışındaki satırlardan hesaplanır. Satır sırası `tablo`nunki (kullanılabilir olanlar)."""
    t = _kullanilabilir(tablo).reset_index(drop=True)
    if len(t) == 0:
        return ozellikler(t, magazalar, karisim(t)), np.zeros(0)
    katlar = t["option"].map(option_katlari(t["option"].to_numpy(), kat)).to_numpy()
    X = ozellikler(t, magazalar, karisim(t))
    pay = np.full((len(t), len(PAY_SUTUNLARI)), np.nan)
    for k in np.unique(katlar):
        ic = katlar == k
        pay[ic] = _paylar(t[ic], karisim(t[~ic])).to_numpy()
    X[PAY_SUTUNLARI] = pay
    return X, t["talep"].to_numpy(dtype=np.float64)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def poisson_sapma(y: np.ndarray, tahmin: np.ndarray) -> float:
    """Ortalama Poisson sapması (deviance); tahmin 1e-6'dan aşağı kırpılır."""
    y = np.asarray(y, dtype=float)
    t = np.clip(np.asarray(tahmin, dtype=float), 1e-6, None)
    terim = np.where(y > 0, y * np.log(np.where(y > 0, y, 1.0) / t) - (y - t), t)
    return float(2.0 * terim.mean())


def _kanonik(parametreler: dict) -> str:
    return json.dumps(parametreler, sort_keys=True, separators=(",", ":"))


def _egit_model(tablo: pd.DataFrame, magazalar: pd.DataFrame,
                parametreler: dict) -> tuple[lgb.Booster, pd.DataFrame]:
    """(Booster, tablonun geçmiş karışımı); tablo boş ya da hedefi sıfırsa ValueError."""
    X, y = egitim_ozellikleri(tablo, magazalar)
    if len(y) == 0 or y.sum() <= 0:
        raise ValueError("eğitim hedefi boş ya da tamamı sıfır")
    p = {k: parametreler[k] for k in ("num_leaves", "learning_rate", "min_child_samples")}
    veri = lgb.Dataset(X, label=y, categorical_feature=KATEGORIK, free_raw_data=True)
    model = lgb.train({**p, **_LGBM_SABIT}, veri, num_boost_round=int(parametreler["n_estimators"]))
    return model, karisim(tablo)


def _tahmin(model: lgb.Booster, X: pd.DataFrame) -> np.ndarray:
    t = np.asarray(model.predict(X), dtype=float)
    return np.clip(np.nan_to_num(t, nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)


def dogrula(tablo: pd.DataFrame, magazalar: pd.DataFrame, parametreler: dict = VARSAYILAN,
            dislanan: np.ndarray | None = None) -> dict:
    """Option'lara göre doğrulama: `dislanan` option'lar (yoksa tohumlu %20) eğitimden tutulur,
    kalanlarla eğitilen model tutulanların satırlarında sınanır. Çok az option varsa `{}`.

    Sapmalar ortalama Poisson sapmasıdır (düşük iyi):
      sapma_model / sapma_taban   mağaza ortalaması taban çizgisine karşı (taban: eğitim kümesinde
                                  mağazanın ortalama talebi; mağaza yoksa genel ortalama)
      sapma_pay_model / _taban    her tutulan option'ın tahmini o option'ın gerçek toplamına
                                  ölçeklenmiş (yalnız mağaza payları)
    ayrıca satır / option sayıları ve ortalama hedef / tahmin."""
    t = _kullanilabilir(tablo).reset_index(drop=True)
    optionlar = np.unique(t["option"].to_numpy())
    if dislanan is None:
        n = int(round(DOGRULAMA_PAYI * len(optionlar)))
        dis = np.random.default_rng(DOGRULAMA_TOHUMU).permutation(optionlar)[:n]
    else:
        dis = np.intersect1d(np.asarray(dislanan, dtype=np.int64), optionlar)
    tutulan = np.isin(t["option"].to_numpy(), dis)
    if len(dis) < 1 or len(optionlar) - len(dis) < EN_AZ_DOGRULAMA_OPTION:
        return {}
    egitim, sinama = t[~tutulan], t[tutulan]
    model, gecmis = _egit_model(egitim, magazalar, parametreler)
    y = sinama["talep"].to_numpy(dtype=np.float64)
    tahmin = _tahmin(model, ozellikler(sinama, magazalar, gecmis))

    ort = egitim.groupby("magaza")["talep"].mean()
    taban = sinama["magaza"].map(ort).fillna(egitim["talep"].mean()).to_numpy(dtype=np.float64)

    def pay_olcekli(oneri: np.ndarray) -> np.ndarray:
        o = sinama["option"].to_numpy()
        gercek = pd.Series(y).groupby(o).transform("sum").to_numpy()
        toplam = pd.Series(oneri).groupby(o).transform("sum").to_numpy()
        return np.where(toplam > 0, oneri * gercek / np.where(toplam > 0, toplam, 1.0), 0.0)

    return {
        "n_egitim": int(len(egitim)), "n_dogrulama": int(len(sinama)),
        "n_egitim_option": int(len(optionlar) - len(dis)), "n_dogrulama_option": int(len(dis)),
        "sapma_model": poisson_sapma(y, tahmin), "sapma_taban": poisson_sapma(y, taban),
        "sapma_pay_model": poisson_sapma(y, pay_olcekli(tahmin)),
        "sapma_pay_taban": poisson_sapma(y, pay_olcekli(taban)),
        "ortalama_hedef": float(y.mean()), "ortalama_tahmin": float(tahmin.mean()),
    }


@dataclass(frozen=True, eq=False)
class Tahminci:
    """Eğitilmiş model, parametreleri ve eğitim tablosunun geçmiş karışımı. `kimlik` içerikten.

    gecmis_karisim  tüm eğitim tablosunun `karisim`ı: tahmin satırlarının `ozellikler`ine verilir
    dogrulama       `dogrula`nın özeti (`{}`: doğrulamaya yetecek option yok)"""

    model: lgb.Booster
    parametreler: dict
    gecmis_karisim: pd.DataFrame
    dogrulama: dict
    _kimlik: str | None = None

    @classmethod
    def egit(cls, tablo: pd.DataFrame, magazalar: pd.DataFrame,
             parametreler: dict = VARSAYILAN) -> "Tahminci":
        """`tablo` öğrenme tablosu (karar gününe kadar kapanmış sezonlar); `stoklu_gun = 0` satırı
        eğitim dışı. Hedef boş ya da tamamı sıfırsa ValueError (Poisson reddeder)."""
        model, gecmis = _egit_model(tablo, magazalar, parametreler)
        return cls(model=model, parametreler=dict(parametreler), gecmis_karisim=gecmis,
                   dogrulama=dogrula(tablo, magazalar, parametreler))

    def tahmin(self, oznitelik_satirlari: pd.DataFrame) -> np.ndarray:
        """Adet: float[len] >= 0, sonlu. Sütunlar `OZELLIKLER` olmalı (`ozellikler`in çıktısı)."""
        if list(oznitelik_satirlari.columns) != OZELLIKLER:
            raise ValueError(f"sütunlar OZELLIKLER olmalı: {list(oznitelik_satirlari.columns)}")
        return _tahmin(self.model, oznitelik_satirlari)

    def _ozet(self) -> str:
        h = hashlib.sha256()
        h.update(self.model.model_to_string().encode("utf-8"))
        h.update(b"\0")
        h.update(_kanonik(self.parametreler).encode("utf-8"))
        h.update(b"\0")
        k = self.gecmis_karisim
        h.update(k[["magaza", "ozellik", "deger"]].to_csv(index=False).encode("utf-8"))
        h.update(np.round(k["pay"].to_numpy(dtype=np.float64), 12).tobytes())
        return h.hexdigest()

    @property
    def kimlik(self) -> str:
        """İçerik özeti (SHA-256 hex): sabitlenmişse saklanan, değilse hesaplanan."""
        return self._kimlik if self._kimlik is not None else self._ozet()

    def sabitle(self) -> "Tahminci":
        """Kimliği bir kez hesaplayıp saklayan kopya (zaten sabitse kendisi)."""
        if self._kimlik is not None:
            return self
        return dataclasses.replace(self, _kimlik=self._ozet())
