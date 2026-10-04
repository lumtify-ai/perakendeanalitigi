"""Stoksuz günün talebi: kestiriciler (spec §4.4).

Satış kaybı geriye dönük bir ölçüdür: stoksuz günün (`bos`, `tukenen`) talebi,
aynı hücrenin ve option'ın stoklu günlerinden kurulur. Ortak arayüz:

    k.egit(gozlem)            gozlem = bütün pencerenin stoklu günleri +
                              `ozellikler.ekle` sütunları (komşu ve geçmiş havuzu)
    k.tahmin(hucre_gunler)    beklenen günlük talep (float64, >= 0, sonlu);
                              sıra ve indeks girdininkidir

Havuz yalnız `stoklu` günlerdir (`tukenen` sansürlü); hedef `brut_satis`.
Naif ve Basit parametre öğrenmez; Basit'in çarpanları (`carpanlar.ogren`,
2023–2024) kurucuya verilir. Beden payı ürüne özgüdür ve 2025'in yeni
option'ları 2023–2024'te olmadığından kestirici onu kendi havuzundan kurar
(`carpanlar.beden_payi_kod`; mağaza × option'da < 30 stoklu SKU-gün ise zincir).

**Beden.** Talep mağaza × option düzeyinde ölçülür. Bir günün option satışı
`s_j` (o gün stoklu bedenlerin satışı), payda `P_j` (o gün stoklu bedenlerin
payları toplamı); option hızı Σ s_j ÷ Σ P_j (Basit'te Σ karakter_j × P_j).
SKU'nun talebi hız × kendi payı. Yalnız M stoksuzken hız S ve L'den doğru kurulur.

**Naif** (`pencere_gun=28`, `asgari_stoklu=7`): hücrenin d'den önceki 28
takvim günündeki stoklu günlerinin ortalama satışı. 7'den az stoklu gün varsa
aynı 28 günde mağaza × option hızı × beden payı; option o 28 günde mağazada
hiç stoklu değilse zincir yedeği; zincirde de yoksa son yedek. Yalnız geriye.

**Basit** (`komsu_gun=14`): `λ_opt = Σ_j s_j / Σ_j (karakter_j × P_j)`, j
d'nin ±14 günü içinde (d dahil: kardeş bedenler o gün stokluysa) option'ın
en az bir stoklu bedeni olan günler; tahmin `λ_opt × karakter_d × pay_s`.
±14'te gün yoksa en yakın 28 stoklu option-günü (iki yandan, uzaklığa göre;
boşluğun bir ucu açıksa yalnız bir yandan — yaşam çarpanı uzatır). Option
mağazada hiç stoklu değilse zincir yedeği, o da yoksa son yedek.

**Zincir yedeği.** Mağazanın alt kategorideki satış payı `w_m` (havuzdaki
Σ satış; mağaza o alt kategoride hiç satmadıysa bütün satışlardaki payı; o
da yoksa 1 / mağaza sayısı). Zincir hızı `Σ s / Σ (karakter × P × w_m)`
bütün mağazaların option-günleri üzerinden (zincir toplam talebi); hedef
mağazanın tahmini zincir hızı × `w_m` × karakter_d × pay_s. Pencere Basit'te
±14 (yoksa en yakın 28 zincir option-günü), Naif'te geçmiş 28 gün.

**Son yedek** (option havuzda hiç yok): mağaza × alt kategorinin stoklu
SKU-gün ortalama satışı; yoksa alt kategorinin; yoksa havuzun.

**Vektörel.** Havuz (mağaza × SKU × gün, mağaza × option × gün, option × gün)
sıralı int64 anahtarlara ve kümülatif toplamlara indirgenir; her hedefin
penceresi `searchsorted` ile O(log n), en yakın 28 gün ikili aramayla.
Satır başına Python yok.
"""

from typing import Protocol

import numpy as np
import pandas as pd

from perakende_analitik import carpanlar as _c
from perakende_analitik.carpanlar import Carpanlar, gun_sayisi, kodlar, yalniz_stoklu

NGUN = 1 << 16          # anahtarın gün alanı: 1970'ten gün sayısı (2149'a dek)
YEDEK_GUN = 28          # Basit: ±komşulukta gün yoksa en yakın bu kadar stoklu gün


class Kestirici(Protocol):
    def egit(self, gozlem: pd.DataFrame) -> None: ...
    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series: ...


# ------------------------------------------------------------------ dizin

class _Dizin:
    """(grup, gün) anahtarlı sıralı tablo; değerlerin kümülatif toplamları.

    Aynı anahtarın satırları toplanır. `aralik` bir gün aralığının [lo, hi)
    konumlarını, `toplam` o aralığın toplamını verir."""

    def __init__(self, grup: np.ndarray, gun: np.ndarray, **degerler: np.ndarray):
        anahtar = grup.astype(np.int64) * NGUN + gun.astype(np.int64)
        sira = np.argsort(anahtar, kind="stable")
        a = anahtar[sira]
        del anahtar
        yeni = np.ones(len(a), dtype=bool)
        yeni[1:] = a[1:] != a[:-1]
        bas = np.flatnonzero(yeni)
        self.anahtar = a[bas]
        del a, yeni
        self.kum = {}
        for ad, v in degerler.items():
            t = (np.add.reduceat(np.asarray(v, dtype=np.float64)[sira], bas) if len(bas)
                 else np.zeros(0))
            self.kum[ad] = np.concatenate([[0.0], np.cumsum(t)])

    def aralik(self, grup: np.ndarray, alt: np.ndarray, ust: np.ndarray):
        """Gün aralığı [alt, ust] (ikisi dahil); grup < 0 boş aralık."""
        taban = np.where(grup >= 0, grup, -1).astype(np.int64) * NGUN
        lo = np.searchsorted(self.anahtar, taban + alt, "left")
        hi = np.searchsorted(self.anahtar, taban + ust, "right")
        hi = np.where(grup >= 0, hi, lo)
        return lo, hi

    def toplam(self, ad: str, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        return self.kum[ad][hi] - self.kum[ad][lo]

    def en_yakin(self, grup: np.ndarray, gun: np.ndarray, k: int):
        """Grubun `gun`e en yakın k anahtarı (iki yandan, uzaklığa göre; eşitlikte
        geçmiş): [lo, lo + kk), kk = min(k, grubun anahtar sayısı)."""
        A = self.anahtar
        taban = np.where(grup >= 0, grup, -1).astype(np.int64) * NGUN
        bas = np.searchsorted(A, taban, "left")
        son = np.searchsorted(A, taban + NGUN, "left")
        son = np.where(grup >= 0, son, bas)
        kk = np.minimum(k, son - bas)
        if len(A) == 0:
            return bas, bas
        t = taban + gun
        lo, hi = bas.copy(), son - kk
        son_i = len(A) - 1
        while True:
            aktif = lo < hi
            if not aktif.any():
                break
            mid = (lo + hi) // 2
            sol = t - A[np.minimum(mid, son_i)]
            sag = A[np.minimum(mid + kk, son_i)] - t
            ileri = aktif & (sol > sag)
            lo = np.where(ileri, mid + 1, lo)
            hi = np.where(aktif & ~ileri, mid, hi)
        return lo, lo + kk


# ------------------------------------------------------------------ kodlar

def _esle(seri: pd.Series, kategoriler: pd.Index) -> np.ndarray:
    """Sütunu havuzun kategori sırasına çevirir (int64; bilinmeyen / boş -1)."""
    if isinstance(seri.dtype, pd.CategoricalDtype):
        harita = kategoriler.get_indexer(seri.cat.categories)
        kod = seri.cat.codes.to_numpy()
        return np.where(kod >= 0, harita[np.maximum(kod, 0)], -1).astype(np.int64)
    return kategoriler.get_indexer(seri).astype(np.int64)


class _Kodlar:
    """Havuzun kimlik evrenleri (mağaza, SKU, option, alt kategori)."""

    def __init__(self, df: pd.DataFrame, alt: bool = True):
        self.m, self.magazalar = kodlar(df["magaza_id"])
        self.u, self.urunler = kodlar(df["urun_id"])
        self.o, self.opsiyonlar = kodlar(df["option_id"])
        if alt:
            self.a, self.altlar = kodlar(df["alt_kategori"])
        self.gun = gun_sayisi(df["tarih"])
        self.nm, self.nu, self.no = len(self.magazalar), len(self.urunler), len(self.opsiyonlar)

    def birak(self) -> None:
        """Havuzun satır dizilerini bırakır (kategori evrenleri kalır)."""
        self.m = self.u = self.o = self.a = self.gun = None

    def hedef(self, df: pd.DataFrame, alt: bool = True):
        """Hedef satırlarının havuz kodları: (m, u, o, a, gun)."""
        m = _esle(df["magaza_id"], self.magazalar)
        u = _esle(df["urun_id"], self.urunler)
        o = _esle(df["option_id"], self.opsiyonlar)
        a = _esle(df["alt_kategori"], self.altlar) if alt else None
        return m, u, o, a, gun_sayisi(df["tarih"]).astype(np.int64)

    def hucre(self, m, u):
        return np.where((m >= 0) & (u >= 0), m.astype(np.int64) * self.nu + u, -1)

    def mo(self, m, o):
        return np.where((m >= 0) & (o >= 0), m.astype(np.int64) * self.no + o, -1)


# --------------------------------------------------------------- komşular

KOMSU_SUTUNLARI = ["komsu_hucre_satis", "komsu_hucre_gun", "komsu_opsiyon_satis",
                   "komsu_opsiyon_gun"]


def komsu_hizlar(gunluk: pd.DataFrame, komsu_gun: int,
                 hedef: pd.DataFrame | None = None) -> pd.DataFrame:
    """Her hücre-gün için iki yanlı (gün hariç) stoklu satış toplamı ve stoklu gün sayısı.

    Havuz `gunluk`un stoklu satırlarıdır (`durum` yoksa hepsi). Pencere
    [d − komsu_gun, d + komsu_gun], d hariç. Sütunlar (int32):
    `komsu_hucre_satis`, `komsu_hucre_gun` (aynı mağaza × SKU),
    `komsu_opsiyon_satis`, `komsu_opsiyon_gun` (aynı mağaza × option, bütün
    bedenler; gün = stoklu SKU-gün). `hedef` verilmezse `gunluk`un satırları
    için; verilirse onun satırları için (sıra ve indeks hedefinki)."""
    havuz = yalniz_stoklu(gunluk)
    hedef = gunluk if hedef is None else hedef
    k = _Kodlar(havuz, alt=False)
    s = havuz["brut_satis"].to_numpy(np.float64)
    bir = np.ones(len(s))
    hucre = _Dizin(k.hucre(k.m, k.u), k.gun, s=s, n=bir)
    opsiyon = _Dizin(k.mo(k.m, k.o), k.gun, s=s, n=bir)
    m, u, o, _, gun = k.hedef(hedef, alt=False)
    cikti = {}
    for ad, dizin, grup in (("hucre", hucre, k.hucre(m, u)), ("opsiyon", opsiyon, k.mo(m, o))):
        toplam = {"satis": 0.0, "gun": 0.0}
        for alt, ust in ((gun - komsu_gun, gun - 1), (gun + 1, gun + komsu_gun)):
            lo, hi = dizin.aralik(grup, alt, ust)
            toplam["satis"] = toplam["satis"] + dizin.toplam("s", lo, hi)
            toplam["gun"] = toplam["gun"] + dizin.toplam("n", lo, hi)
        for b, v in toplam.items():
            cikti[f"komsu_{ad}_{b}"] = np.rint(np.broadcast_to(v, (len(hedef),))).astype(np.int32)
    return pd.DataFrame(cikti, index=hedef.index)[KOMSU_SUTUNLARI]


# ------------------------------------------------------------------ havuz

class _Havuz:
    """Kestiricilerin ortak havuz tabloları: beden payı, alt kategori payı, son yedek."""

    def __init__(self, gozlem: pd.DataFrame):
        df = yalniz_stoklu(gozlem)
        k = self.k = _Kodlar(df)
        s = df["brut_satis"].to_numpy(np.float64)
        self.s = s

        # beden payı (mağaza × SKU, zincir SKU, option başına SKU sayısı)
        self.pm_anahtar, self.pm_pay, self.pz, osayi = _c.beden_payi_kod(k.m, k.u, k.o, s, k.nu)
        self.osayi = np.zeros(k.no)
        self.osayi[:len(osayi)] = osayi

        # alt kategori payı w[m, a] ve son yedek hızları
        na = len(k.altlar)
        ok = (k.m >= 0) & (k.a >= 0)
        i = k.m[ok] * na + k.a[ok]
        S = np.bincount(i, weights=s[ok], minlength=k.nm * na).reshape(k.nm, na)
        N = np.bincount(i, minlength=k.nm * na).reshape(k.nm, na).astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            w = S / S.sum(0, keepdims=True)
            magaza_payi = S.sum(1) / S.sum()
            magaza_payi = np.where(np.isfinite(magaza_payi) & (magaza_payi > 0), magaza_payi,
                                   1.0 / max(k.nm, 1))
            self.w = np.where(np.isfinite(w) & (w > 0), w, magaza_payi[:, None])
            self.magaza_payi = magaza_payi
            self.w_bilinmeyen = 1.0 / max(k.nm, 1)
            self.hiz_ma = np.where(N > 0, S / N, np.nan)
            self.hiz_a = np.where(N.sum(0) > 0, S.sum(0) / N.sum(0), np.nan)
            self.hiz_genel = float(s.sum() / len(s)) if len(s) else 0.0

    def birak(self) -> None:
        """Dizinler kurulduktan sonra satır dizilerini bırakır."""
        self.s = None
        self.k.birak()

    def pay(self, m, u, o) -> np.ndarray:
        """SKU'nun beden payı: mağaza payı; yoksa zincir; yoksa 1 / option'ın SKU sayısı; yoksa 1."""
        k = self.k
        sonuc = np.full(len(m), np.nan)
        anahtar = np.where((m >= 0) & (u >= 0), m.astype(np.int64) * k.nu + u, -1)
        j = np.minimum(np.searchsorted(self.pm_anahtar, anahtar), max(len(self.pm_anahtar) - 1, 0))
        if len(self.pm_anahtar):
            bulundu = (anahtar >= 0) & (self.pm_anahtar[j] == anahtar)
            sonuc[bulundu] = self.pm_pay[j[bulundu]]
        bos = np.isnan(sonuc) & (u >= 0)
        sonuc[bos] = self.pz[u[bos]]
        bos = np.isnan(sonuc) & (o >= 0)
        with np.errstate(divide="ignore"):
            sonuc[bos] = np.where(self.osayi[o[bos]] > 0, 1.0 / self.osayi[o[bos]], np.nan)
        return np.where(np.isnan(sonuc), 1.0, sonuc)

    def alt_payi(self, m, a) -> np.ndarray:
        """Mağazanın alt kategorideki satış payı w_m (yedekleriyle)."""
        sonuc = np.full(len(m), self.w_bilinmeyen)
        ok = m >= 0
        aa = np.where(a >= 0, a, 0)
        bilinen = ok & (a >= 0)
        sonuc[bilinen] = self.w[m[bilinen], aa[bilinen]]
        bilinmeyen_alt = ok & (a < 0)
        sonuc[bilinmeyen_alt] = self.magaza_payi[m[bilinmeyen_alt]]
        return sonuc

    def son_yedek(self, m, a) -> np.ndarray:
        sonuc = np.full(len(m), np.nan)
        ok = (m >= 0) & (a >= 0)
        sonuc[ok] = self.hiz_ma[m[ok], a[ok]]
        bos = np.isnan(sonuc) & (a >= 0)
        sonuc[bos] = self.hiz_a[a[bos]]
        return np.where(np.isnan(sonuc), self.hiz_genel, sonuc)


def _seri(deger: np.ndarray, df: pd.DataFrame) -> pd.Series:
    deger = np.where(np.isfinite(deger), np.maximum(deger, 0.0), 0.0)
    return pd.Series(deger.astype(np.float64), index=df.index, name="tahmini_talep")


def _bolum(pay: np.ndarray, payda: np.ndarray, ok: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok & (payda > 0), pay / payda, np.nan)


# ------------------------------------------------------------------- Naif

class Naif:
    """Hücrenin son `pencere_gun` takvim günündeki stoklu günlerinin ortalaması."""

    def __init__(self, pencere_gun: int = 28, asgari_stoklu: int = 7):
        self.pencere_gun = pencere_gun
        self.asgari_stoklu = asgari_stoklu

    def egit(self, gozlem: pd.DataFrame) -> None:
        h = self._havuz = _Havuz(gozlem)
        k = h.k
        pay = h.pay(k.m, k.u, k.o)
        self._hucre = _Dizin(k.hucre(k.m, k.u), k.gun, s=h.s)
        self._mo = _Dizin(k.mo(k.m, k.o), k.gun, s=h.s, p=pay)
        self._zincir = _Dizin(k.o, k.gun, s=h.s, p=pay * h.alt_payi(k.m, k.a))
        h.birak()

    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series:
        h = self._havuz
        m, u, o, a, gun = h.k.hedef(hucre_gunler)
        alt, ust = gun - self.pencere_gun, gun - 1

        lo, hi = self._hucre.aralik(h.k.hucre(m, u), alt, ust)
        n = hi - lo
        tahmin = _bolum(self._hucre.toplam("s", lo, hi), n.astype(np.float64),
                        n >= self.asgari_stoklu)

        kalan = np.isnan(tahmin)
        if kalan.any():
            pay = h.pay(m, u, o)
            lo, hi = self._mo.aralik(h.k.mo(m, o), alt, ust)
            hiz = _bolum(self._mo.toplam("s", lo, hi), self._mo.toplam("p", lo, hi), hi > lo)
            tahmin = np.where(kalan, hiz * pay, tahmin)
            kalan = np.isnan(tahmin)
            if kalan.any():
                lo, hi = self._zincir.aralik(o, alt, ust)
                hiz = _bolum(self._zincir.toplam("s", lo, hi), self._zincir.toplam("p", lo, hi),
                             hi > lo)
                tahmin = np.where(kalan, hiz * h.alt_payi(m, a) * pay, tahmin)
                kalan = np.isnan(tahmin)
                tahmin[kalan] = h.son_yedek(m[kalan], a[kalan])
        return _seri(tahmin, hucre_gunler)


# ------------------------------------------------------------------ Basit

class Basit:
    """Stoksuz günün ±`komsu_gun` içindeki stoklu option-günleri, karakterle düzeltilmiş."""

    def __init__(self, komsu_gun: int = 14, *, carpanlar: Carpanlar):
        self.komsu_gun = komsu_gun
        self.carpanlar = carpanlar

    def egit(self, gozlem: pd.DataFrame) -> None:
        df = yalniz_stoklu(gozlem)
        h = self._havuz = _Havuz(df)
        k = h.k
        payda = _c.karakter(df, self.carpanlar).to_numpy() * h.pay(k.m, k.u, k.o)
        self._mo = _Dizin(k.mo(k.m, k.o), k.gun, s=h.s, p=payda)
        self._zincir = _Dizin(k.o, k.gun, s=h.s, p=payda * h.alt_payi(k.m, k.a))
        h.birak()

    def _hiz(self, dizin: _Dizin, grup: np.ndarray, gun: np.ndarray) -> np.ndarray:
        """±komsu_gun; yoksa en yakın YEDEK_GUN anahtar. Grup havuzda yoksa NaN."""
        lo, hi = dizin.aralik(grup, gun - self.komsu_gun, gun + self.komsu_gun)
        hiz = _bolum(dizin.toplam("s", lo, hi), dizin.toplam("p", lo, hi), hi > lo)
        kalan = np.flatnonzero(np.isnan(hiz))
        if len(kalan):
            lo, hi = dizin.en_yakin(grup[kalan], gun[kalan], YEDEK_GUN)
            hiz[kalan] = _bolum(dizin.toplam("s", lo, hi), dizin.toplam("p", lo, hi), hi > lo)
        return hiz

    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series:
        h = self._havuz
        m, u, o, a, gun = h.k.hedef(hucre_gunler)
        olcek = _c.karakter(hucre_gunler, self.carpanlar).to_numpy() * h.pay(m, u, o)
        hiz = self._hiz(self._mo, h.k.mo(m, o), gun)
        kalan = np.flatnonzero(np.isnan(hiz))
        if len(kalan):
            mk, ak = m[kalan], a[kalan]
            hiz[kalan] = self._hiz(self._zincir, o[kalan], gun[kalan]) * h.alt_payi(mk, ak)
        tahmin = hiz * olcek
        kalan = np.isnan(tahmin)
        tahmin[kalan] = h.son_yedek(m[kalan], a[kalan])
        return _seri(tahmin, hucre_gunler)
