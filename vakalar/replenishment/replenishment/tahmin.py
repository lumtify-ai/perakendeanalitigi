"""LightGBM tahmincisi (v4): tek küresel Poisson modeli, oyun penceresinden önce
bir kez eğitilir, her karar pazartesisi kendi dünyasının geçmişinden kurulan
özelliklerle mağaza–option (OC) başına önümüzdeki haftanın satışını öngörür.

**Tek özellik fonksiyonu, iki yol.** `ozellik_tablosu(satis, stoklu, harita,
oznitelik, karar_gunu)` `[gün, C]` iki matris okur:

    çevrimdışı  `kaynak.gunluk_satis_matrisi` / `gunluk_stoklu_matrisi`; satır 0 =
                `CEVRIMDISI_BAS` (yayımlanan tabloların ilk günü, 2023-01-01)
    çevrimiçi   `Gorunum.satis_gecmisi` / `stoklu_gecmisi`; satır 0 = dünyanın
                günü 0 (`w.takvim` ilk satırı, 2022-07-04), satır sayısı = bugün

Aynı takvim günü iki yolda farklı satır indisidir (TAM ve KÜÇÜK dünyada fark 181
gün). Hizayı tek yer kurar: `oznitelik_kur(w, harita, bas)` matrisin satır 0'ının
tarihini (`bas`) alır, takvimi o günden keser ve `Oznitelik.satir(tarih)` ile tarih
→ satır çevirir. Çevrimiçi yol `gorunum_ozellikleri(g, ...)` üstünden gider ve
hizayı her çağrıda denetler (`satir(g.tarih) == g.gun`).

**Zaman** (`ihtiyac` ile aynı sözleşme, Ruling R14). Karar günü `k` (pazartesi
sabahı) ve sonrasındaki satırlar okunmaz; gözlem haftası `[k−7, k−1]`. Öngörülen
hafta, kuralın hafta katsayısının payıyla aynı: `[k+1, k+7]` (teslimden bir
sonraki teslime). Takvim (tatil, Black Friday) önceden ilan edildiği için
`[k+1, k+7]`'ye bakabilir.

**Özellikler** (v2'ninkiler, v4 alanlarıyla; OC başına bir satır, harita sırası):

    lag1..lag4    son 1..4 haftanın satışı (lag1 = [k−7, k−1])
    ort4, ort8    son 4 / 8 haftanın haftalık ortalaması
    zincir_lag1   bütün fiziksel OC'lerin lag1 toplamı (zincirin haftası)
    stoklu_gun    OC'nin [k−7, k−1]'deki stoklu günü (`ihtiyac.stoklu_gun`:
                  herhangi bir bedeni stoklu ya da satış yapmış gün). v2'de yoktu:
                  lag1 = 0'ın "talep yok" mu "raf boş" mu olduğunu ağaca söyler
    line, kategori, magaza_tipi
                  pandas `category`, kategori listeleri dünyanın bütün
                  değerlerinden sabit (çağrıdan çağrıya aynı kodlar)
    tatil_gunu    [k+1, k+7]'deki resmî tatil günü sayısı (BF hariç)
    bf_gunu       [k+1, k+7]'deki Black Friday günü sayısı (v4 takviminde BF de
                  `tatil_mi`; trafiği tatilin tersi, ayrı sayılır — Ruling R12)

**Eğitim** (`egitim_seti`, `cevrimdisi_egit`): `bit_gunu`'nden önceki her
pazartesi `k` (8 haftalık gecikme geçmişi olan ve hedef haftası `k+7 < bit_gunu`
olan); hedef = `[k+1, k+7]` satışı. Satırlar fiziksel OC'ler (online kollarda
maskelenir, R14) ve hedef haftasında en az bir stoklu günü olanlar: hiç stoklu
olmayan haftanın satışı talep hakkında bir şey söylemez (sansür). Hiperparametre
v2'nin seçtiği (`PARAMETRELER`: `num_leaves=31`, 400 ağaç); yeniden seçim yok.

**Kimlik** (`Tahminci.sabitle`, `kimlik`): `booster.model_to_string()` + kanonik
JSON parametrelerin SHA-256'sı; pickle baytı değil (RPT'nin pickle kimliği dersi:
süreçler arasında koşu önbelleği kırılıyordu). Politika bu kimliği
`parametreler()`ine koyar (motor anahtarı).

Bu modül `perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz;
dünyanın yalnız açık alanlarını (`takvim`, `magazalar`) okur.
"""

import dataclasses
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import kaynak
from .ihtiyac import haftalik, stoklu_gun
from .kaynak import Harita
from .sabitler import EGITIM_BIT

# Yayımlanan tabloların (ve `kaynak` matrislerinin çevrimdışı yolda) ilk günü
CEVRIMDISI_BAS = date(2023, 1, 1)

OZELLIKLER = [
    "lag1", "lag2", "lag3", "lag4", "ort4", "ort8", "zincir_lag1", "stoklu_gun",
    "line", "kategori", "magaza_tipi", "tatil_gunu", "bf_gunu",
]
KATEGORIK = ["line", "kategori", "magaza_tipi"]
GECMIS_HAFTA = 8          # en uzun gecikme penceresi (ort8)

# v2'nin ızgarasından seçilen (num_leaves {15, 31} × ağaç {200, 400}); yeniden seçilmez
PARAMETRELER = {"num_leaves": 31, "n_estimators": 400, "learning_rate": 0.05, "min_child_samples": 50}
_LGBM_SABIT = {
    "objective": "poisson",
    "seed": 0,
    "deterministic": True,
    "num_threads": 1,
    "verbosity": -1,
    "force_row_wise": True,
}


# ---------------------------------------------------------------------------
# Öznitelikler ve takvim hizası
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Oznitelik:
    """OC'nin sabit öznitelikleri ve matrisin satırlarıyla hizalı takvim.

    bas          matrisin satır 0'ının tarihi (Timestamp)
    line, kategori, magaza_tipi
                 [OC] pandas Categorical, kategori listesi dünyanın bütün değerleri
    tatil, bf    [gün] bool, satır `i` = `bas + i` günü (tatil: resmî tatil, BF hariç)
    """

    bas: pd.Timestamp
    line: pd.Categorical
    kategori: pd.Categorical
    magaza_tipi: pd.Categorical
    tatil: np.ndarray
    bf: np.ndarray

    def satir(self, tarih) -> int:
        """Tarihin bu matristeki satır indisi."""
        return int((pd.Timestamp(tarih).normalize() - self.bas).days)


def _sabit_kategorik(degerler: np.ndarray, evren) -> pd.Categorical:
    return pd.Categorical(np.asarray(degerler).astype(str),
                          categories=sorted(set(np.asarray(evren).astype(str))))


def oznitelik_kur(w, harita: Harita, bas) -> Oznitelik:
    """`w` dünyasının açık alanlarından (`takvim`, `magazalar`) ve haritadan
    öznitelikler; takvim satır 0'ı `bas` (matrisin ilk günü) olacak biçimde kesilir.

    Çevrimdışı matris için `bas = CEVRIMDISI_BAS`; `Gorunum` için dünyanın günü 0
    (`w.takvim.tarih` ilk değeri; `gorunum_oznitelik`)."""
    bas = pd.Timestamp(bas).normalize()
    takvim = w.takvim
    tarih = pd.DatetimeIndex(takvim["tarih"]).normalize()
    if (tarih[1:] - tarih[:-1] != pd.Timedelta(days=1)).any():
        raise ValueError("takvim ardışık günler olmalı")
    i0 = int((bas - tarih[0]).days)
    if not 0 <= i0 < len(tarih):
        raise ValueError(f"takvim {tarih[0].date()}..{tarih[-1].date()} matris başını ({bas.date()}) kapsamıyor")
    bf = takvim["black_friday_mi"].to_numpy(dtype=bool)[i0:]
    tatil = takvim["tatil_mi"].to_numpy(dtype=bool)[i0:] & ~bf
    tip = w.magazalar["tip"].to_numpy().astype(str)
    return Oznitelik(
        bas=bas,
        line=_sabit_kategorik(harita.line[harita.oc_option], harita.line),
        kategori=_sabit_kategorik(harita.option_kategori[harita.oc_option], harita.option_kategori),
        magaza_tipi=_sabit_kategorik(tip[harita.oc_magaza], tip),
        tatil=tatil, bf=bf,
    )


def gorunum_oznitelik(w, harita: Harita) -> Oznitelik:
    """`Gorunum` matrislerinin (satır 0 = dünyanın günü 0) öznitelikleri."""
    return oznitelik_kur(w, harita, w.takvim["tarih"].iloc[0])


# ---------------------------------------------------------------------------
# Özellikler
# ---------------------------------------------------------------------------


def ozellik_tablosu(
    satis: np.ndarray, stoklu: np.ndarray, harita: Harita, oznitelik: Oznitelik, karar_gunu: int
) -> pd.DataFrame:
    """OC başına bir satır (harita sırası), sütunlar `OZELLIKLER`.

    `satis` / `stoklu` `[gün, C]`; satır `karar_gunu` ve sonrası okunmaz (yoksa
    da olur: `Gorunum` geçmişi tam `karar_gunu` satırdır). Takvim özellikleri
    `[karar+1, karar+7]`."""
    if karar_gunu + 8 > len(oznitelik.tatil):
        raise ValueError(f"takvim karar_gunu+7 ({karar_gunu + 7}) gününü kapsamıyor")
    hafta = haftalik(satis, harita, karar_gunu, GECMIS_HAFTA)   # (8, OC), en yeni son satırda
    lag1 = hafta[-1]
    OC = len(lag1)
    ileri = slice(karar_gunu + 1, karar_gunu + 8)
    df = pd.DataFrame({
        "lag1": lag1,
        "lag2": hafta[-2],
        "lag3": hafta[-3],
        "lag4": hafta[-4],
        "ort4": hafta[-4:].mean(axis=0),
        "ort8": hafta.mean(axis=0),
        "zincir_lag1": np.full(OC, lag1[~harita.oc_online].sum()),
        "stoklu_gun": stoklu_gun(stoklu, satis, harita, karar_gunu, 7),
        "line": oznitelik.line,
        "kategori": oznitelik.kategori,
        "magaza_tipi": oznitelik.magaza_tipi,
        "tatil_gunu": np.full(OC, float(oznitelik.tatil[ileri].sum())),
        "bf_gunu": np.full(OC, float(oznitelik.bf[ileri].sum())),
    })
    return df[OZELLIKLER]


def gorunum_ozellikleri(g, harita: Harita, oznitelik: Oznitelik) -> pd.DataFrame:
    """Çevrimiçi yol: `Gorunum`'ün geçmişinden `ozellik_tablosu` (karar günü `g.gun`).
    `oznitelik` `gorunum_oznitelik(w, harita)` olmalı; hiza denetlenir."""
    if oznitelik.satir(g.tarih) != int(g.gun):
        raise ValueError(f"öznitelik takvimi Görünüm'le hizalı değil: {pd.Timestamp(g.tarih).date()} "
                         f"satır {oznitelik.satir(g.tarih)}, görünüm günü {g.gun}")
    return ozellik_tablosu(g.satis_gecmisi, g.stoklu_gecmisi, harita, oznitelik, int(g.gun))


def hedef_haftasi(satis: np.ndarray, harita: Harita, karar_gunu: int) -> np.ndarray:
    """float[OC]: `[karar+1, karar+7]` satışı (eğitim ve doğrulama hedefi)."""
    return haftalik(satis, harita, karar_gunu + 8, 1)[0]


def egitim_pazartesileri(oznitelik: Oznitelik, bit_gunu: int) -> list[int]:
    """Eğitim karar günleri: pazartesi, `GECMIS_HAFTA` haftalık geçmişi matriste
    olan (`k ≥ 56`), hedef haftası `bit_gunu`'nden önce biten (`k + 7 < bit_gunu`)."""
    ilk = GECMIS_HAFTA * 7
    pzt0 = (-oznitelik.bas.dayofweek) % 7               # matrisin ilk pazartesisi
    ilk += (pzt0 - ilk) % 7
    return list(range(ilk, bit_gunu - 7, 7))


def egitim_seti(
    satis: np.ndarray, stoklu: np.ndarray, harita: Harita, oznitelik: Oznitelik, bit_gunu: int
) -> tuple[pd.DataFrame, np.ndarray]:
    """(X, y): `egitim_pazartesileri`'nin her `k`'sında fiziksel OC'lerin
    özellikleri ve `[k+1, k+7]` satışı; hedef haftasında stoklu günü olmayan satır
    düşer. `bit_gunu` ve sonrasının hiçbir satırı okunmaz."""
    fiziksel = ~harita.oc_online
    X_parca, y_parca = [], []
    for k in egitim_pazartesileri(oznitelik, bit_gunu):
        gozlenebilir = fiziksel & (stoklu_gun(stoklu, satis, harita, k + 8, 7) > 0)
        X_parca.append(ozellik_tablosu(satis, stoklu, harita, oznitelik, k)[gozlenebilir])
        y_parca.append(hedef_haftasi(satis, harita, k)[gozlenebilir])
    if not X_parca:
        return ozellik_tablosu(satis, stoklu, harita, oznitelik, 0).iloc[:0], np.zeros(0)
    return pd.concat(X_parca, ignore_index=True), np.concatenate(y_parca)


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


@dataclass(frozen=True, eq=False)
class Tahminci:
    """Eğitilmiş model ve parametreleri. `kimlik` içerikten (modül notu)."""

    model: lgb.Booster
    parametreler: dict
    _kimlik: str | None = None

    @classmethod
    def egit(cls, X: pd.DataFrame, y: np.ndarray, parametreler: dict = PARAMETRELER) -> "Tahminci":
        """`X`'in sütunları `OZELLIKLER` olmalı; hedef toplamı 0 ise (Poisson
        reddeder) ValueError."""
        if list(X.columns) != OZELLIKLER:
            raise ValueError(f"X sütunları OZELLIKLER olmalı: {list(X.columns)}")
        y = np.asarray(y, dtype=float)
        if len(y) == 0 or y.sum() <= 0:
            raise ValueError("eğitim hedefi boş ya da tamamı sıfır")
        p = {k: parametreler[k] for k in ("num_leaves", "learning_rate", "min_child_samples")}
        veri = lgb.Dataset(X, label=y, categorical_feature=KATEGORIK, free_raw_data=True)
        model = lgb.train({**p, **_LGBM_SABIT}, veri, num_boost_round=int(parametreler["n_estimators"]))
        return cls(model=model, parametreler=dict(parametreler))

    def tahmin(self, X: pd.DataFrame) -> np.ndarray:
        """float[len(X)] ≥ 0, sonlu."""
        if list(X.columns) != OZELLIKLER:
            raise ValueError(f"X sütunları OZELLIKLER olmalı: {list(X.columns)}")
        t = np.asarray(self.model.predict(X), dtype=float)
        return np.clip(np.nan_to_num(t, nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)

    def _ozet(self) -> str:
        h = hashlib.sha256()
        h.update(self.model.model_to_string().encode("utf-8"))
        h.update(b"\0")
        h.update(_kanonik(self.parametreler).encode("utf-8"))
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

    def kaydet(self, yol: Path | str) -> None:
        """Model metni + parametreler + kimlik tek JSON dosyasına (atomik)."""
        yol = Path(yol)
        sabit = self.sabitle()
        icerik = {"parametreler": sabit.parametreler, "kimlik": sabit.kimlik,
                  "model": sabit.model.model_to_string()}
        gecici = yol.with_suffix(yol.suffix + ".yaziliyor")
        gecici.write_text(json.dumps(icerik), encoding="utf-8")
        gecici.replace(yol)

    @classmethod
    def yukle(cls, yol: Path | str) -> "Tahminci":
        """`kaydet`'in dosyasından; içerik kimliği tutmazsa ValueError."""
        icerik = json.loads(Path(yol).read_text(encoding="utf-8"))
        t = cls(model=lgb.Booster(model_str=icerik["model"]), parametreler=icerik["parametreler"])
        if t.kimlik != icerik["kimlik"]:
            raise ValueError(f"{yol}: model içeriği kayıtlı kimlikle tutmuyor")
        return t.sabitle()


# ---------------------------------------------------------------------------
# Çevrimdışı eğitim (yolun kendi geçmişinden)
# ---------------------------------------------------------------------------


def cevrimdisi_egit(
    con, w, harita: Harita, bit=EGITIM_BIT, parametreler: dict = PARAMETRELER, dogrulama_hafta: int = 8
) -> tuple[Tahminci, dict]:
    """`con`'un tablolarından (yol 0: yayımlanan DuckDB; yol p: o yolun Lumoda
    koşusunun tabloları) `[CEVRIMDISI_BAS, bit)` matrisleriyle eğitilmiş, sabitlenmiş
    `Tahminci` ve özet.

    Özet: süreler (matris, set, doğrulama eğitimi, son eğitim; sn), satır sayıları,
    doğrulama sapması. Doğrulama: son `dogrulama_hafta` eğitim pazartesisi dışarıda
    bırakılarak (hedefleri bit'ten önce) eğitilen modelin o haftalardaki ortalama
    Poisson sapması; karşılaştırma için aynı satırlarda `lag1` ve `ort4`
    öngörülerinin sapması. Son model bütün pazartesilerle eğitilir."""
    t0 = time.perf_counter()
    bit = pd.Timestamp(bit).date()
    son = bit - pd.Timedelta(days=1)
    anahtar = kaynak.hucre_anahtari(w)
    satis = kaynak.gunluk_satis_matrisi(con, anahtar, CEVRIMDISI_BAS, son)
    stoklu = kaynak.gunluk_stoklu_matrisi(con, anahtar, CEVRIMDISI_BAS, son)
    oz = oznitelik_kur(w, harita, CEVRIMDISI_BAS)
    bit_gunu = oz.satir(bit)
    t1 = time.perf_counter()

    pazartesiler = egitim_pazartesileri(oz, bit_gunu)
    if len(pazartesiler) <= dogrulama_hafta:
        raise ValueError(f"{len(pazartesiler)} eğitim pazartesisi; doğrulama için yetmez")
    ayrim = pazartesiler[-dogrulama_hafta]                 # doğrulamanın ilk pazartesisi
    X, y = egitim_seti(satis, stoklu, harita, oz, bit_gunu)
    X_d, y_d = egitim_seti(satis, stoklu, harita, oz, ayrim + 7)    # ayrımdan önceki pazartesiler
    n_d = len(y_d)
    t2 = time.perf_counter()

    model_d = Tahminci.egit(X_d, y_d, parametreler)
    X_v, y_v = X.iloc[n_d:], y[n_d:]
    sapma = poisson_sapma(y_v, model_d.tahmin(X_v))
    t3 = time.perf_counter()

    tahminci = Tahminci.egit(X, y, parametreler).sabitle()
    t4 = time.perf_counter()
    ozet = {
        "bas": CEVRIMDISI_BAS.isoformat(), "bit": bit.isoformat(),
        "pazartesi": len(pazartesiler), "dogrulama_pazartesi": dogrulama_hafta,
        "satir": int(len(y)), "dogrulama_satir": int(len(y_v)),
        "dogrulama_sapma": sapma,
        "dogrulama_sapma_lag1": poisson_sapma(y_v, X_v["lag1"].to_numpy()),
        "dogrulama_sapma_ort4": poisson_sapma(y_v, X_v["ort4"].to_numpy()),
        "dogrulama_ortalama_y": float(np.mean(y_v)), "dogrulama_ortalama_tahmin": float(model_d.tahmin(X_v).mean()),
        "sure_matris_sn": round(t1 - t0, 1), "sure_set_sn": round(t2 - t1, 1),
        "sure_dogrulama_sn": round(t3 - t2, 1), "sure_egitim_sn": round(t4 - t3, 1),
        "kimlik": tahminci.kimlik,
    }
    return tahminci, ozet
