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
(`carpanlar.beden_payi_kod`; mağaza × option'da < 30 stoklu SKU-gün ise zincir);
`Carpanlar.beden_payi` hiçbir kestiricide okunmaz (ML de payı kendi havuzundan kurar).
Mağazada hiç stoklanmamış bir SKU zincir payını alır ve aynı mağaza × option'ın
payları yeniden 1'e ölçeklenir (kardeşlerin payı 1 iken toplam 1'i aşmasın).

**Beden.** Talep mağaza × option düzeyinde ölçülür. Bir günün option satışı
`s_j` (o gün stoklu bedenlerin satışı), payda `P_j` (o gün stoklu bedenlerin
payları toplamı); option hızı Σ s_j ÷ Σ P_j (Basit'te Σ karakter_j × P_j).
SKU'nun talebi hız × kendi payı. Yalnız M stoksuzken hız S ve L'den doğru kurulur.

**Naif** (`pencere_gun=28`, `asgari_stoklu=7`): hücrenin d'den önceki 28
takvim günündeki stoklu günlerinin ortalama satışı. 7'den az stoklu gün varsa
aynı 28 günde mağaza × option hızı × beden payı; option o 28 günde mağazada
stoklu değilse aynı mağaza × option'ın d'den önceki son 28 stoklu option-günü
(eski kendi geçmişi); hiç yoksa zincir yedeği (geçmiş 28 gün, yoksa zincirin
son 28 option-günü); o da yoksa son yedek. Yalnız geriye.

**Basit** (`komsu_gun=14`): `λ_opt = Σ_j s_j / Σ_j (karakter_j × P_j)`, j
d'nin ±14 günü içinde (d dahil: kardeş bedenler o gün stokluysa) option'ın
en az bir stoklu bedeni olan günler; tahmin `λ_opt × karakter_d × pay_s`.
±14'te gün yoksa en yakın 28 stoklu option-günü (iki yandan, uzaklığa göre;
boşluğun bir ucu açıksa yalnız bir yandan — yaşam çarpanı uzatır). Option
mağazada hiç stoklu değilse zincir yedeği, o da yoksa son yedek.

**Basit, karar anı** (`karar_ani=t`, karar pazartesisi): `t`'de ve sonrasındaki
satırlar hiçbir şeyi etkilemez. Havuz (beden payı, göreli hız, son yedek, option
ve zincir dizinleri) yalnız `tarih < t` stoklu satırlarıdır; komşuluk
`[d − 14, min(d + 14, t − 1)]`, en yakın 28 gün yalnız geriden. Yalnız `t`'den
önceki hücre-günler kestirilir (`tarih >= t` hedef: ValueError). Çarpanlar
kurucuya karar anında bilinenlerden verilir (`hazirlik.carpanlar_kapanmis`).
`None` bugünkü Basit'tir (geriye dönük; yok-satma sayıları).

**Zincir yedeği.** Mağazanın göreli hızı `r_m`: bir option'ın orada stoklu
bir günde ne hızla sattığı, zincirinkine oranla — `(Σ s ÷ Σ karakter × P)`
mağazanın line × alt kategori segmentinde ÷ aynısı zincirin segmentinde
(havuzun bütün stoklu günleri; Naif'te karakter 1). Mağazanın satış payı
değil: çok option taşıyan bir kanal (online) payı büyük diye bir option'ı daha
hızlı satmaz; line ayrımı Outlet option'larını Outlet mağazalarının hızıyla
ölçer. Mağazanın segmentte stoklu günü yoksa alt kategorideki göreli hızı, o
da yoksa bütün satışlarınınki; bilinmeyen mağaza 1. Zincir hızı
`Σ s / Σ (karakter × P × r_m)` option'ı stoklayan mağazaların option-günleri
üzerinden: zincir ortalaması hızında bir mağazanın option-günü başına hızı
(stoklayan az mağazanın satışı zincir toplamına büyütülmez). Hedefin tahmini
zincir hızı × `r_hedef` × karakter_d × pay_s. Pencere Basit'te ±14 (yoksa en
yakın 28 zincir option-günü), Naif'te geçmiş 28 gün (yoksa son 28 option-günü).

**Son yedek** (option havuzda hiç yok): mağaza × alt kategorinin stoklu
SKU-gün ortalama satışı; yoksa alt kategorinin; yoksa havuzun.

**ML** (`ornek=4_000_000`, `tohum=20261004`): LightGBM Poisson, sabit
hiperparametreler (ayar araması yok). Eğitim satırları 2023–2024'ün stoklu
SKU-günlerinden tohumla `ornek` tanedir (az ise hepsi); havuz bütün pencerenin
stoklu günleridir ve yalnız özellik hesabı içindir. Özellikler: `ozellikler`'in
sayısal ve bayrak sütunları; kategorikler `line, alt_kategori, fiyat_segmenti,
magaza_tipi, sehir, kanal`; komşu özellikleri `komsu_hizlar` düzeyinde ±14
gündür: hücre sütunları hedef günü hariç; mağaza × option sütunları hedef günü
DAHİL eder (aynı gün stoklu kardeş bedenler görünür, Basit'le aynı bilgi) ve
havuzdaki satırın (`durum == "stoklu"`, eğitim satırları dahil) kendi SKU-gününün
satışını ve gününü düşer, bu yüzden hedefin kendi satışı sızmaz; stoksuz hedef
satırı havuzda olmadığından bir şey düşülmez. Havuz bütün pencerenin simetrik
havuzudur (Basit'le aynı): 2024 sonu eğitim satırlarının ±14 komşuları 2025
başı günlerini de içerir (hedef sızıntısı değil, komşu bilgisi). Beden payı
(Basit'le aynı, havuzdan); bunlardan türeyen üç özellik (`hucre_hiz`,
`opsiyon_hiz` = satış ÷ gün, `opsiyon_pay` = option komşu satışı × beden payı ÷
28). Hedef `brut_satis`. Yalnız gözlenebilir sütunları okur (`hakem` ve
`kayip` değil; stoklu satırın kendi `brut_satis`'ı yalnız havuzdan düşülmek
için okunur). Tahmin parça parça yapılır; bellek float32 özellik matrisiyle
sınırlıdır. LightGBM `deterministic` ve `force_row_wise` ile tekrarlanabilir.

**Vektörel.** Havuz (mağaza × SKU × gün, mağaza × option × gün, option × gün)
sıralı int64 anahtarlara ve kümülatif toplamlara indirgenir; her hedefin
penceresi `searchsorted` ile O(log n), en yakın 28 gün ikili aramayla.
Satır başına Python yok.
"""

from datetime import date
from typing import Protocol

import lightgbm as lgb
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

    def son_k(self, grup: np.ndarray, gun: np.ndarray, k: int):
        """Grubun `gun`den önceki (gün hariç) son k anahtarı: [lo, hi)."""
        taban = np.where(grup >= 0, grup, -1).astype(np.int64) * NGUN
        bas = np.searchsorted(self.anahtar, taban, "left")
        hi = np.searchsorted(self.anahtar, taban + gun, "left")
        hi = np.where(grup >= 0, hi, bas)
        return np.maximum(bas, hi - k), hi

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
    """Havuzun kimlik evrenleri (mağaza, SKU, option, alt kategori, line)."""

    def __init__(self, df: pd.DataFrame, alt: bool = True):
        self.m, self.magazalar = kodlar(df["magaza_id"])
        self.u, self.urunler = kodlar(df["urun_id"])
        self.o, self.opsiyonlar = kodlar(df["option_id"])
        if alt:
            self.a, self.altlar = kodlar(df["alt_kategori"])
            self.l, self.lines = kodlar(df["line"])
        self.gun = gun_sayisi(df["tarih"])
        self.nm, self.nu, self.no = len(self.magazalar), len(self.urunler), len(self.opsiyonlar)

    def birak(self) -> None:
        """Havuzun satır dizilerini bırakır (kategori evrenleri kalır)."""
        self.m = self.u = self.o = self.a = self.l = self.gun = None

    @property
    def nseg(self) -> int:
        return len(self.lines) * len(self.altlar)

    def segment(self, l, a):
        """line × alt kategori kodu (-1 bilinmeyen)."""
        return np.where((l >= 0) & (a >= 0), l.astype(np.int64) * len(self.altlar) + a, -1)

    def hedef_segment(self, df: pd.DataFrame):
        return self.segment(_esle(df["line"], self.lines), _esle(df["alt_kategori"], self.altlar))

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


class _Komsu:
    """Havuzun mağaza × SKU ve mağaza × option dizinleri; komşu toplamları.

    Bir kez kurulur, her hedef kümesi için `hesapla` çağrılır (ML parça parça
    tahmin eder, dizinler yeniden kurulmaz)."""

    def __init__(self, k: _Kodlar, s: np.ndarray, komsu_gun: int):
        self.k, self.komsu_gun = k, komsu_gun
        bir = np.ones(len(s))
        self.hucre = _Dizin(k.hucre(k.m, k.u), k.gun, s=s, n=bir)
        self.opsiyon = _Dizin(k.mo(k.m, k.o), k.gun, s=s, n=bir)

    def hesapla(self, hedef: pd.DataFrame, havuzda: np.ndarray | None = None) -> dict[str, np.ndarray]:
        """Komşu toplamları (int32). `havuzda` verilmezse iki düzey de d günü hariç
        (`komsu_hizlar`). Verilirse (bool, hedef satırı havuzun stoklu satırı mı):
        hücre d hariç; mağaza × option penceresi [d − k, d + k] d DAHİL, havuzdaki
        satırların kendi SKU-günü (satışı ve 1 gün) düşülür. Böylece aynı gün stoklu
        kardeş bedenler görünür (Basit'le aynı bilgi); havuzda olmayan stoksuz hedef
        satırından bir şey düşülmez."""
        m, u, o, _, gun = self.k.hedef(hedef, alt=False)
        cikti = {}
        for ad, dizin, grup in (("hucre", self.hucre, self.k.hucre(m, u)),
                                ("opsiyon", self.opsiyon, self.k.mo(m, o))):
            toplam = {"satis": 0.0, "gun": 0.0}
            if ad == "opsiyon" and havuzda is not None:
                lo, hi = dizin.aralik(grup, gun - self.komsu_gun, gun + self.komsu_gun)
                kendi = havuzda.astype(np.float64)
                toplam["satis"] = (dizin.toplam("s", lo, hi)
                                   - kendi * hedef["brut_satis"].to_numpy(np.float64))
                toplam["gun"] = dizin.toplam("n", lo, hi) - kendi
            else:
                for alt, ust in ((gun - self.komsu_gun, gun - 1), (gun + 1, gun + self.komsu_gun)):
                    lo, hi = dizin.aralik(grup, alt, ust)
                    toplam["satis"] = toplam["satis"] + dizin.toplam("s", lo, hi)
                    toplam["gun"] = toplam["gun"] + dizin.toplam("n", lo, hi)
            for b, v in toplam.items():
                cikti[f"komsu_{ad}_{b}"] = np.rint(
                    np.broadcast_to(v, (len(hedef),))).astype(np.int32)
        return cikti


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
    komsu = _Komsu(_Kodlar(havuz, alt=False), havuz["brut_satis"].to_numpy(np.float64), komsu_gun)
    return pd.DataFrame(komsu.hesapla(hedef), index=hedef.index)[KOMSU_SUTUNLARI]


# ------------------------------------------------------------------ havuz

class _Havuz:
    """Kestiricilerin ortak havuz tabloları: beden payı, göreli hız, son yedek."""

    def __init__(self, gozlem: pd.DataFrame):
        df = yalniz_stoklu(gozlem)
        k = self.k = _Kodlar(df)
        s = df["brut_satis"].to_numpy(np.float64)
        self.s = s

        # beden payı (mağaza × SKU, zincir SKU, option başına SKU sayısı)
        self.pm_anahtar, self.pm_pay, self.pz, osayi = _c.beden_payi_kod(k.m, k.u, k.o, s, k.nu)
        self.osayi = np.zeros(k.no)
        self.osayi[:len(osayi)] = osayi
        # mağaza × option payı toplamı: mağazada stoklanmamış SKU'lar zincir payını
        # alınca toplam 1 + (onların zincir payı) olur; paylar buna bölünür
        opt_u = np.full(k.nu, -1, dtype=np.int64)
        opt_u[k.u] = k.o
        self.opt_u = opt_u
        zpay = np.where(np.isfinite(self.pz), self.pz, 0.0)
        zop = np.bincount(np.maximum(opt_u, 0), weights=np.where(opt_u >= 0, zpay, 0.0),
                          minlength=k.no)
        pm_m, pm_u = self.pm_anahtar // k.nu, self.pm_anahtar % k.nu
        mo, ters = np.unique(pm_m * k.no + opt_u[pm_u], return_inverse=True)
        mevcut = np.bincount(ters, weights=zpay[pm_u], minlength=len(mo))
        self.mo_anahtar = mo
        self.mo_toplam = 1.0 + np.maximum(zop[mo % k.no] - mevcut, 0.0)

        # son yedek hızları: mağaza × alt kategorinin stoklu SKU-gün ortalaması
        na = len(k.altlar)
        ok = (k.m >= 0) & (k.a >= 0)
        i = k.m[ok] * na + k.a[ok]
        S = np.bincount(i, weights=s[ok], minlength=k.nm * na).reshape(k.nm, na)
        N = np.bincount(i, minlength=k.nm * na).reshape(k.nm, na).astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            self.hiz_ma = np.where(N > 0, S / N, np.nan)
            self.hiz_a = np.where(N.sum(0) > 0, S.sum(0) / N.sum(0), np.nan)
        self.hiz_genel = float(s.sum() / len(s)) if len(s) else 0.0

    def goreli_hiz_kur(self, payda: np.ndarray) -> None:
        """Göreli hız: (Σ s ÷ Σ payda) mağazada ÷ aynısı zincirde; üç düzey:
        line × alt kategori, alt kategori, mağazanın bütünü.

        payda satır başına karakter × beden payı (Σ payda = Σ_j karakter_j × P_j)."""
        k = self.k

        def oran(grup, ng):
            ok = (k.m >= 0) & (grup >= 0)
            i = k.m[ok].astype(np.int64) * ng + grup[ok]
            S = np.bincount(i, weights=self.s[ok], minlength=k.nm * ng).reshape(k.nm, ng)
            D = np.bincount(i, weights=payda[ok], minlength=k.nm * ng).reshape(k.nm, ng)
            with np.errstate(divide="ignore", invalid="ignore"):
                return (S / D) / (S.sum(0) / D.sum(0))[None, :]

        r_m = oran(np.zeros(len(k.m), dtype=np.int64), 1)[:, 0]
        self.r_m = np.where(np.isfinite(r_m), r_m, 1.0)
        r_a = oran(k.a, len(k.altlar))
        self.r_a = np.where(np.isfinite(r_a), r_a, self.r_m[:, None])
        r_s = oran(k.segment(k.l, k.a), k.nseg)
        a_s = np.arange(k.nseg) % len(k.altlar)           # segmentin alt kategorisi
        self.r_s = np.where(np.isfinite(r_s), r_s, self.r_a[:, a_s])

    def goreli_hiz(self, m, sg, a) -> np.ndarray:
        """Mağazanın segmentteki (line × alt kategori) göreli hızı; segment yoksa alt
        kategori, o da yoksa mağaza; bilinmeyen mağaza 1."""
        sonuc = np.ones(len(m))
        bilinen = (m >= 0) & (sg >= 0)
        sonuc[bilinen] = self.r_s[m[bilinen], sg[bilinen]]
        alt = (m >= 0) & (sg < 0) & (a >= 0)
        sonuc[alt] = self.r_a[m[alt], a[alt]]
        yok = (m >= 0) & (sg < 0) & (a < 0)
        sonuc[yok] = self.r_m[m[yok]]
        return sonuc

    def birak(self) -> None:
        """Dizinler kurulduktan sonra satır dizilerini bırakır."""
        self.s = None
        self.k.birak()

    def pay(self, m, u, o) -> np.ndarray:
        """SKU'nun beden payı: mağaza payı; yoksa zincir; yoksa 1 / option'ın SKU sayısı;
        yoksa 1. Mağaza × option'ın kendi payları varsa toplam 1'e ölçeklenir."""
        k = self.k
        sonuc = np.full(len(m), np.nan)

        def bul(anahtarlar, aranan):
            if len(anahtarlar) == 0:
                return np.zeros(len(aranan), dtype=np.int64), np.zeros(len(aranan), dtype=bool)
            j = np.minimum(np.searchsorted(anahtarlar, aranan), len(anahtarlar) - 1)
            return j, (aranan >= 0) & (anahtarlar[j] == aranan)

        j, var = bul(self.pm_anahtar, np.where((m >= 0) & (u >= 0),
                                               m.astype(np.int64) * k.nu + u, -1))
        sonuc[var] = self.pm_pay[j[var]]
        bos = np.isnan(sonuc) & (u >= 0)
        sonuc[bos] = self.pz[u[bos]]
        bos = np.isnan(sonuc) & (o >= 0)
        with np.errstate(divide="ignore"):
            sonuc[bos] = np.where(self.osayi[o[bos]] > 0, 1.0 / self.osayi[o[bos]], np.nan)
        sonuc = np.where(np.isnan(sonuc), 1.0, sonuc)
        j, var = bul(self.mo_anahtar, np.where((m >= 0) & (o >= 0),
                                               m.astype(np.int64) * k.no + o, -1))
        sonuc[var] /= self.mo_toplam[j[var]]
        return sonuc

    def son_yedek(self, m, a) -> np.ndarray:
        sonuc = np.full(len(m), np.nan)
        ok = (m >= 0) & (a >= 0)
        sonuc[ok] = self.hiz_ma[m[ok], a[ok]]
        bos = np.isnan(sonuc) & (a >= 0)
        sonuc[bos] = self.hiz_a[a[bos]]
        return np.where(np.isnan(sonuc), self.hiz_genel, sonuc)


_KIMLIK = ("magaza_id", "urun_id", "option_id", "alt_kategori", "line")   # `_Kodlar`ın evrenleri


def _karar_oncesi(df: pd.DataFrame, karar_ani: pd.Timestamp) -> pd.DataFrame:
    """`tarih < karar_ani` satırları; kimlik sütunlarının kullanılmayan kategorileri
    atılır (havuzun kod evreni yalnız karar anından önceki satırlardan gelir)."""
    sec = (df["tarih"] < karar_ani).to_numpy()
    df = df[sec].copy(deep=False)          # süzme kopyalar; sığ kopya yalnız bayrağı temizler
    for c in _KIMLIK:
        if c in df.columns and isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].cat.remove_unused_categories()
    return df


def _sonlu(ad: str, x: np.ndarray) -> np.ndarray:
    """NaN/inf kümülatif toplamı zehirler ve sessizce yedeğe düşürür: açık hata."""
    if not np.isfinite(x).all():
        n = int((~np.isfinite(x)).sum())
        raise ValueError(f"{ad}: {n} satırda sonlu olmayan değer (girdi sütunlarını denetleyin: "
                         "oran, hafta_gunu, kanal, yas_gun ...)")
    return x


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
        pay = _sonlu("beden payı", h.pay(k.m, k.u, k.o))
        h.goreli_hiz_kur(pay)
        self._hucre = _Dizin(k.hucre(k.m, k.u), k.gun, s=h.s)
        self._mo = _Dizin(k.mo(k.m, k.o), k.gun, s=h.s, p=pay)
        self._zincir = _Dizin(k.o, k.gun, s=h.s, p=pay * h.goreli_hiz(k.m, k.segment(k.l, k.a), k.a))
        h.birak()

    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series:
        h = self._havuz
        m, u, o, a, gun = h.k.hedef(hucre_gunler)
        alt, ust = gun - self.pencere_gun, gun - 1

        lo, hi = self._hucre.aralik(h.k.hucre(m, u), alt, ust)
        n = hi - lo
        tahmin = _bolum(self._hucre.toplam("s", lo, hi), n.astype(np.float64),
                        n >= self.asgari_stoklu)
        kalan = np.flatnonzero(np.isnan(tahmin))
        if len(kalan) == 0:
            return _seri(tahmin, hucre_gunler)

        pay = h.pay(m[kalan], u[kalan], o[kalan])
        mk, ok_, ak, gk = m[kalan], o[kalan], a[kalan], gun[kalan]
        sk = h.k.hedef_segment(hucre_gunler)[kalan]

        def hiz(dizin, lo, hi):
            return _bolum(dizin.toplam("s", lo, hi), dizin.toplam("p", lo, hi), hi > lo)

        # mağaza × option: geçmiş 28 gün, yoksa son 28 stoklu option-günü
        grup = h.k.mo(mk, ok_)
        v = hiz(self._mo, *self._mo.aralik(grup, gk - self.pencere_gun, gk - 1))
        yok = np.isnan(v)
        v[yok] = hiz(self._mo, *self._mo.son_k(grup[yok], gk[yok], YEDEK_GUN))
        # zincir: geçmiş 28 gün, yoksa zincirin son 28 option-günü; × göreli hız
        yok = np.flatnonzero(np.isnan(v))
        if len(yok):
            z = hiz(self._zincir, *self._zincir.aralik(ok_[yok], gk[yok] - self.pencere_gun,
                                                         gk[yok] - 1))
            zy = np.isnan(z)
            z[zy] = hiz(self._zincir, *self._zincir.son_k(ok_[yok][zy], gk[yok][zy], YEDEK_GUN))
            v[yok] = z * h.goreli_hiz(mk[yok], sk[yok], ak[yok])
        t = v * pay
        yok = np.isnan(t)
        t[yok] = h.son_yedek(mk[yok], ak[yok])
        tahmin[kalan] = t
        return _seri(tahmin, hucre_gunler)


# ------------------------------------------------------------------ Basit

class Basit:
    """Stoksuz günün ±`komsu_gun` içindeki stoklu option-günleri, karakterle düzeltilmiş.

    `karar_ani=t` (karar pazartesisi): `t`'de ve sonrasındaki hiçbir satır
    kestirimi etkilemez. `egit` havuzu `tarih < t` stoklu satırlarıyla kurar (beden
    payı, göreli hız, son yedek, option ve zincir dizinleri); kimlik sütunlarının
    kullanılmayan kategorileri atılır, yani yalnız `t`'den sonra görünen mağaza ya da
    option havuzun kod evrenine de girmez. `tahmin` komşuluğu
    `[d − komsu_gun, min(d + komsu_gun, t − 1)]` ile keser; en yakın 28 gün yedeği
    havuzdan, yani yalnız `t`'den öncekilerden seçilir. Yalnız `t`'den önceki
    hücre-günler kestirilir: hedefte `tarih >= t` satırı varsa ValueError.
    Çarpanlar kurucuya verilir; karar anında bilinenlerden öğrenilmesi
    (`hazirlik.carpanlar_kapanmis`) çağıranın işidir. `None`: bütün havuz, iki yan
    (bugünkü davranış, birebir)."""

    def __init__(self, komsu_gun: int = 14, *, carpanlar: Carpanlar,
                 karar_ani: date | pd.Timestamp | None = None):
        self.komsu_gun = komsu_gun
        self.carpanlar = carpanlar
        self.karar_ani = None if karar_ani is None else pd.Timestamp(karar_ani).normalize()
        self._t_gun = (None if karar_ani is None
                       else int(gun_sayisi(pd.Series([self.karar_ani]))[0]))

    def egit(self, gozlem: pd.DataFrame) -> None:
        df = yalniz_stoklu(gozlem)
        if self.karar_ani is not None:
            df = _karar_oncesi(df, self.karar_ani)
        h = self._havuz = _Havuz(df)
        k = h.k
        payda = (_sonlu("karakter", _c.karakter(df, self.carpanlar).to_numpy())
                 * _sonlu("beden payı", h.pay(k.m, k.u, k.o)))
        h.goreli_hiz_kur(payda)
        self._mo = _Dizin(k.mo(k.m, k.o), k.gun, s=h.s, p=payda)
        self._zincir = _Dizin(k.o, k.gun, s=h.s, p=payda * h.goreli_hiz(k.m, k.segment(k.l, k.a), k.a))
        h.birak()

    def _hiz(self, dizin: _Dizin, grup: np.ndarray, gun: np.ndarray) -> np.ndarray:
        """±komsu_gun (karar anında üst uç t − 1'de kesilir); yoksa en yakın YEDEK_GUN
        anahtar. Grup havuzda yoksa NaN."""
        ust = gun + self.komsu_gun
        if self._t_gun is not None:
            ust = np.minimum(ust, self._t_gun - 1)
        lo, hi = dizin.aralik(grup, gun - self.komsu_gun, ust)
        hiz = _bolum(dizin.toplam("s", lo, hi), dizin.toplam("p", lo, hi), hi > lo)
        kalan = np.flatnonzero(np.isnan(hiz))
        if len(kalan):
            lo, hi = dizin.en_yakin(grup[kalan], gun[kalan], YEDEK_GUN)
            hiz[kalan] = _bolum(dizin.toplam("s", lo, hi), dizin.toplam("p", lo, hi), hi > lo)
        return hiz

    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series:
        h = self._havuz
        m, u, o, a, gun = h.k.hedef(hucre_gunler)
        if self._t_gun is not None and (gun >= self._t_gun).any():
            n = int((gun >= self._t_gun).sum())
            raise ValueError(f"Basit: {n} hedef satırı karar_ani ({self.karar_ani.date()}) "
                             "gününde ya da sonrasında; karar anında yalnız öncesi kestirilir")
        olcek = _sonlu("karakter", _c.karakter(hucre_gunler, self.carpanlar).to_numpy())
        olcek = olcek * h.pay(m, u, o)
        hiz = self._hiz(self._mo, h.k.mo(m, o), gun)
        kalan = np.flatnonzero(np.isnan(hiz))
        if len(kalan):
            sk = h.k.hedef_segment(hucre_gunler)[kalan]
            hiz[kalan] = (self._hiz(self._zincir, o[kalan], gun[kalan])
                          * h.goreli_hiz(m[kalan], sk, a[kalan]))
        tahmin = hiz * olcek
        kalan = np.isnan(tahmin)
        tahmin[kalan] = h.son_yedek(m[kalan], a[kalan])
        return _seri(tahmin, hucre_gunler)


# --------------------------------------------------------------------- ML

ML_SAYISAL = ["hafta_gunu", "tatil", "black_friday", "indirim_baslangici", "markdown_orani",
              "kampanya_orani", "oran", "yas_gun", "beden_sira", "metrekare", "liste_fiyati",
              "alis_fiyati"]
ML_KATEGORIK = ["line", "alt_kategori", "fiyat_segmenti", "magaza_tipi", "sehir", "kanal"]
ML_EGITIM_YILLARI = (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-31"))
ML_PARCA = 2_000_000    # tahmin parçası (satır): float32 matris + komşu dizilerini sınırlar


class ML:
    """LightGBM (Poisson): 2023–2024 stoklu SKU-günlerinden öğrenir, her günü kestirir."""

    def __init__(self, ornek: int = 4_000_000, tohum: int = 20261004, komsu_gun: int = 14):
        self.ornek, self.tohum, self.komsu_gun = ornek, tohum, komsu_gun

    def egit(self, gozlem: pd.DataFrame) -> None:
        df = yalniz_stoklu(gozlem)
        h = self._havuz = _Havuz(df)
        k = h.k
        gun = k.gun
        bas, bit = (int(gun_sayisi(pd.Series([t]))[0]) for t in ML_EGITIM_YILLARI)
        aday = np.flatnonzero((gun >= bas) & (gun <= bit))
        del gun
        if len(aday) == 0:
            raise ValueError("ML: 2023–2024 stoklu satır yok (eğitim yalnız bu dönemde yapılır)")
        if len(aday) > self.ornek:
            aday = np.sort(np.random.default_rng(self.tohum).choice(aday, self.ornek, replace=False))
        self._komsu = _Komsu(k, h.s, self.komsu_gun)
        h.birak()
        egitim = df.iloc[aday]
        self._kategoriler = {c: pd.Index(egitim[c].astype("category").cat.remove_unused_categories()
                                         .cat.categories) for c in ML_KATEGORIK}
        x = self._matris(egitim)
        self._sutunlar = list(x.columns)
        self._egitim_satir = len(x)
        y = egitim["brut_satis"].to_numpy(np.float64)
        self._model = None
        if y.sum() == 0:                  # Poisson hedefi sıfır toplamı kabul etmez: talep 0
            return
        self._model = lgb.LGBMRegressor(
            objective="poisson", num_leaves=63, learning_rate=0.05, n_estimators=400,
            min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            random_state=self.tohum, n_jobs=-1, verbose=-1,
            deterministic=True, force_row_wise=True)
        self._model.fit(x, y)

    def _matris(self, df: pd.DataFrame) -> pd.DataFrame:
        """Satırların özellik matrisi (float32 + kategorik); komşu özellikleri ve beden payı
        havuzdan. Stoklu satır havuzdadır (kendi SKU-günü komşu option toplamından
        düşülür); üyelik `durum == "stoklu"` ile belirlenir (sütun yoksa hepsi stoklu)."""
        h = self._havuz
        m, u, o, _, _ = h.k.hedef(df, alt=False)
        havuzda = (df["durum"] == "stoklu").to_numpy() if "durum" in df.columns else np.ones(len(df), bool)
        sutun = self._komsu.hesapla(df, havuzda)
        sutun["beden_payi"] = h.pay(m, u, o).astype(np.float32)
        # türev özellikler: Poisson ağacı oranı ve çarpımı kendi bulamaz (gün sayısı 0: NaN)
        for ad in ("hucre", "opsiyon"):
            satis = sutun[f"komsu_{ad}_satis"].astype(np.float32)
            gun = sutun[f"komsu_{ad}_gun"].astype(np.float32)
            sutun[f"{ad}_hiz"] = np.divide(satis, gun, out=np.full(len(df), np.nan, np.float32),
                                           where=gun > 0)
        sutun["opsiyon_pay"] = (sutun["komsu_opsiyon_satis"].astype(np.float32)
                                * sutun["beden_payi"] / np.float32(2 * self.komsu_gun))
        for c in ML_SAYISAL:
            sutun[c] = df[c].to_numpy().astype(np.float32)
        for c in ML_KATEGORIK:
            sutun[c] = pd.Categorical(df[c], categories=self._kategoriler[c])
        return pd.DataFrame(sutun)

    def tahmin(self, hucre_gunler: pd.DataFrame) -> pd.Series:
        sonuc = np.zeros(len(hucre_gunler))
        if self._model is None:
            return _seri(sonuc, hucre_gunler)
        for i in range(0, len(hucre_gunler), ML_PARCA):
            x = self._matris(hucre_gunler.iloc[i:i + ML_PARCA])
            sonuc[i:i + ML_PARCA] = self._model.predict(x[self._sutunlar])
        return _seri(sonuc, hucre_gunler)
