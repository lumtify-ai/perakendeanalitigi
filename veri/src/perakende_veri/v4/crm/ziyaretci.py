"""Ziyaretçi seçimi (spec §3 adım 2): mağaza-gün başına `F_m` farklı,
hayatta müşteri, ağırlıkla ardışık (yerine koymadan) örnekleme.

Ağırlık (müşteri k, mağaza m)::

    fiziksel m:  hız_k × (1 − online_payi_k) × (1, ev_magaza_k = m; IL_ICI_AGIRLIK, aynı il)
    ONL:         hız_k × online_payi_k

Kapanmış ev mağazasının satışı (dolayısıyla ziyaretçi talebi) yoktur, bu
yüzden oraya ağırlık fiilen 0; o müşteriler ilindeki diğer mağazalara il içi
ağırlıkla gelmeye devam eder. Denetleyici kararındaki formülden tek fark
fiziksel mağazada `(1 − online_payi)` çarpanı: `nufus_baslat`'ın tabanı
aynı çarpanla boyutlandırılır; o olmadan online ağırlıklı müşteri iki
kanalda birden tam hızla sayılırdı.

**Yapı (artımlı).** Ağırlık `taban × (0,15 + 0,85 × [ev = m])` biçiminde
olduğundan fiziksel mağaza için iki listenin karışımından çekilir: ilin
bütün müşterileri (ağırlık 0,15 × taban) ve m'nin ev müşterileri (0,85 ×
taban). Her liste yalnız sona eklenen bir (müşteri, ağırlık, kümülatif)
tamponudur: yeni müşteri eklenince (`nufus.ekle`) listelerin sonuna eklenir.
Ölen müşteri ret ile elenir. Ev mağazası ya da online payı değişince
(`nufus.degisim_sayaci` arttığında; `yasam.ev_kapanisi` artırır), ya da
`ADAY_YENIDEN_KUR_GUN` günde bir, listeler baştan kurulur (ölüler atılır).

**Örnekleme.** Kümülatiften yerine koyarak çek, ölüyü ve tekrarı reddet,
ilk k farklı hayattaki aday: ağırlıkla ardışık örnekleme, Gumbel-top-k ile
aynı dağılım (O(k log n)). Çekiliş sınırı aşılırsa ya da k adayların
yarısından fazlaysa Gumbel-top-k (üstel yarış, bütün il listesi üzerinde
kesin ağırlıkla). Hayatta aday k'dan azsa eksik kadar yeni müşteri
(`nufus.ekle`, ev mağazası m, kayıt günü d; Review Focus 1).

**Cinsiyet kotası (Görev 5b).** `ziyaretci_sec`'e mağaza başına kadın
ziyaretçi hedefi verilirse (gün d'nin o mağazadaki satışının Kadın /
(Kadın + Erkek) birim payından, `ayristir.kadin_hedefi`) mağaza için
`ceil(KOTA_FAZLA × k) + KOTA_EK` aday çekilir (çekiliş sırasıyla, yani
ağırlıkla ardışık örnekleme) ve sıradaki ilk hedef kadar kadın ile ilk
k − hedef erkek alınır; bir cinsiyet yetmezse eksik öbüründen tamamlanır.
Ağırlıkla ardışık bir örneklemin cinsiyete göre ilk-n'i, o cinsiyet
içinde yine ağırlıkla ardışık örneklemdir: seçim cinsiyet sayıları
koşullu doğru dağılımdır. Kotasız seçimde mağaza-gün ziyaretçilerinin
cinsiyeti satılan ürünlerin cinsiyetinden bağımsız dalgalanır (küçük
mağazada binom gürültüsü) ve eşleştirme bu farkı çapraz cinsiyet alımına
zorlanarak kapatır (KUCUK: cezadan bağımsız ~%10 taban).
"""

import numpy as np

from . import sabitler as S


class _Liste:
    """Sona eklenen (müşteri indisi, ağırlık, kümülatif ağırlık) tamponu."""

    __slots__ = ("aday", "w", "kum", "n")

    def __init__(self, kapasite: int = 256):
        self.aday = np.empty(kapasite, dtype=np.int32)
        self.w = np.empty(kapasite, dtype=np.float64)
        self.kum = np.empty(kapasite, dtype=np.float64)
        self.n = 0

    def ekle(self, idx: np.ndarray, w: np.ndarray) -> None:
        k = len(idx)
        if not k:
            return
        if self.n + k > len(self.aday):
            kap = max(len(self.aday), 1)
            while kap < self.n + k:
                kap *= 2
            for ad in ("aday", "w", "kum"):
                eski = getattr(self, ad)
                yeni = np.empty(kap, dtype=eski.dtype)
                yeni[: self.n] = eski[: self.n]
                setattr(self, ad, yeni)
        son = self.kum[self.n - 1] if self.n else 0.0
        s = slice(self.n, self.n + k)
        self.aday[s] = idx
        self.w[s] = w
        self.kum[s] = son + np.cumsum(w)
        self.n += k

    @property
    def toplam(self) -> float:
        return float(self.kum[self.n - 1]) if self.n else 0.0


def _gumbel_top_k(aday: np.ndarray, w: np.ndarray, hayatta: np.ndarray, k: int, rng) -> np.ndarray:
    """Gumbel-top-k (üstel yarış: E/w'nin en küçük k'sı); ölü ve sıfır
    ağırlıklı aday dışarıda. k'dan az geçerli aday varsa hepsi."""
    gecerli = hayatta[aday] & (w > 0)
    anahtar = np.full(len(aday), np.inf)
    anahtar[gecerli] = rng.standard_exponential(int(gecerli.sum())) / w[gecerli]
    k_al = min(k, int(gecerli.sum()))
    if k_al == 0:
        return np.zeros(0, dtype=np.int64)
    sec = np.argpartition(anahtar, k_al - 1)[:k_al]
    sec = sec[np.argsort(anahtar[sec], kind="stable")]   # yarış sırası = ardışık örnekleme sırası
    return aday[sec].astype(np.int64)


def _ret_ornekle(cek, hayatta: np.ndarray, k: int, rng) -> np.ndarray | None:
    """Ardışık yerine koymadan örnekleme: `cek(n)` yerine koyarak n müşteri
    indisi çeker; ölü ve tekrar reddedilir, ilk k farklı hayattaki aday
    (çekiliş sırasıyla). Çekiliş sınırı aşılırsa None."""
    akis = np.zeros(0, dtype=np.int64)
    cekilen = 0
    parti = int(k * 1.25) + 16
    while True:
        yeni = cek(parti)
        cekilen += parti
        akis = np.concatenate([akis, yeni[hayatta[yeni]]])
        _, ilk = np.unique(akis, return_index=True)
        if len(ilk) >= k:
            return akis[np.sort(ilk)[:k]]
        if cekilen > S.ZIYARET_RET_SINIRI * k + 64:
            return None
        parti = max(2 * (k - len(ilk)), 16)


class Adaylar:
    """Mağaza başına aday yapısı (modül docstring'i). `guncelle(nufus, d)`
    her gün seçimden önce çağrılır."""

    def __init__(self, nufus, d: int):
        self.kur(nufus, d)

    # --- kurulum --------------------------------------------------------------

    def _taban(self, nufus, idx):
        hiz = nufus.ziyaret_hizi[idx]
        onl = nufus.online_payi[idx]
        return hiz * (1.0 - onl), hiz * onl

    def _ekle(self, nufus, idx: np.ndarray) -> None:
        if not len(idx):
            return
        mb = nufus.magaza
        fiz_w, onl_w = self._taban(nufus, idx)
        il = nufus.il[idx].astype(np.int64)
        ev = nufus.ev_magaza[idx].astype(np.int64)
        idx32 = idx.astype(np.int32)
        for i in np.unique(il):
            s = il == i
            self.il_liste[i].ekle(idx32[s], fiz_w[s])
        fiz = ev != mb.onl
        for m in np.unique(ev[fiz]):
            s = ev == m
            self.ev_liste[m].ekle(idx32[s], fiz_w[s])
        self.onl_liste.ekle(idx32, onl_w)

    def kur(self, nufus, d: int) -> None:
        """Baştan kur: yalnız hayattakiler (ölüler atılır)."""
        mb = nufus.magaza
        self.il_liste = [_Liste() for _ in range(len(mb.il_adlari))]
        self.ev_liste = [_Liste() for _ in range(mb.M)]
        self.onl_liste = _Liste(max(nufus.K, 256))
        self._ekle(nufus, np.flatnonzero(nufus.hayatta))
        self.K = nufus.K
        self.kurulus_gun = d
        self.surum = nufus.degisim_sayaci
        self.kurulus_sayisi = getattr(self, "kurulus_sayisi", 0) + 1

    def guncelle(self, nufus, d: int) -> None:
        """Gün d öncesi: değişen ev/online payı ya da süre dolduysa baştan
        kur; değilse yalnız yeni müşterileri sona ekle."""
        K0 = self.K
        if nufus.degisim_sayaci != self.surum or d - self.kurulus_gun >= S.ADAY_YENIDEN_KUR_GUN:
            self.kur(nufus, d)
            return
        if nufus.K > K0:
            yeni = np.arange(K0, nufus.K)
            yeni = yeni[nufus.hayatta[yeni]]
            self._ekle(nufus, yeni)
            self.K = nufus.K

    # --- örnekleme -------------------------------------------------------------

    def _cekici(self, nufus, m: int, rng):
        """(çekiş fonksiyonu, aday sayısı) ya da toplam ağırlık 0 ise None."""
        mb = nufus.magaza
        if m == mb.onl:
            L = self.onl_liste
            if L.toplam <= 0:
                return None

            def cek(n):
                pos = np.searchsorted(L.kum[: L.n], rng.random(n) * L.toplam, side="right")
                return L.aday[np.minimum(pos, L.n - 1)].astype(np.int64)

            return cek, L.n
        il, ev = self.il_liste[mb.il[m]], self.ev_liste[m]
        a = S.IL_ICI_AGIRLIK * il.toplam
        b = (1.0 - S.IL_ICI_AGIRLIK) * ev.toplam
        if a + b <= 0:
            return None

        def cek(n):
            u = rng.random(n) * (a + b)
            evden = u >= a
            out = np.empty(n, dtype=np.int64)
            if (~evden).any():
                p = np.searchsorted(il.kum[: il.n], u[~evden] / S.IL_ICI_AGIRLIK, side="right")
                out[~evden] = il.aday[np.minimum(p, il.n - 1)]
            if evden.any():
                p = np.searchsorted(ev.kum[: ev.n], (u[evden] - a) / (1.0 - S.IL_ICI_AGIRLIK), side="right")
                out[evden] = ev.aday[np.minimum(p, ev.n - 1)]
            return out

        return cek, il.n

    def kesin_agirlik(self, nufus, m: int) -> tuple[np.ndarray, np.ndarray]:
        """Mağaza m'nin bütün adayları ve kesin ağırlıkları (Gumbel yedeği ve
        testler için)."""
        mb = nufus.magaza
        if m == mb.onl:
            L = self.onl_liste
            return L.aday[: L.n].astype(np.int64), L.w[: L.n].copy()
        L = self.il_liste[mb.il[m]]
        aday = L.aday[: L.n].astype(np.int64)
        ev = nufus.ev_magaza[aday] == m
        return aday, L.w[: L.n] * np.where(ev, 1.0, S.IL_ICI_AGIRLIK)

    def sec(self, nufus, m: int, k: int, rng, sayac: dict | None = None) -> np.ndarray:
        """Mağaza m için en çok k farklı hayattaki müşteri (eksikse daha az),
        çekiliş sırasıyla (ağırlıkla ardışık örnekleme sırası).

        Not: ret örneklemesi ve Gumbel-top-k yedeği ayrı ayrı hedef dağılımı
        (ağırlıkla ardışık örnekleme) verir, ama yedek ret çekilişi
        başarısız olduğunda devreye girdiğinden karışımları tam hedef
        dağılım değildir (başarısızlığa koşullanma küçük bir sapma yaratır).
        Yedek TAM'da hiç (0 mağaza-gün) çalışmadı; yalnız k > aday/2
        durumunda (küçük/yeni il) ve aday yetmezken önemlidir."""
        hayatta = nufus.hayatta
        c = self._cekici(nufus, m, rng)
        sec = None
        if c is not None and 2 * k <= c[1]:
            sec = _ret_ornekle(c[0], hayatta, k, rng)
        if sec is None:
            if sayac is not None:
                sayac["gumbel_yedek"] = sayac.get("gumbel_yedek", 0) + 1
            aday, w = self.kesin_agirlik(nufus, m)
            sec = _gumbel_top_k(aday, w, hayatta, k, rng)
        return sec


def cinsiyet_kotasi(aday: np.ndarray, kadin: np.ndarray, k: int, hedef: int) -> np.ndarray:
    """Çekiliş sırasıyla `aday`dan (kadın bayrağı `kadin`) ilk `hedef` kadın
    ve ilk `k − hedef` erkek; bir cinsiyet yetmezse eksik öbür cinsiyetin
    sıradakilerinden. En çok k aday, çekiliş sırası korunur."""
    k = min(k, len(aday))
    hedef = min(max(hedef, 0), k)
    kad_sira = np.cumsum(kadin)            # adayın kendi cinsiyetindeki sırası (1'den)
    erk_sira = np.cumsum(~kadin)
    kf = min(hedef, int(kadin.sum()))
    ke = min(k - kf, int((~kadin).sum()))
    kf = k - ke                            # erkek yetmediyse kadınla tamamla
    al = np.where(kadin, kad_sira <= kf, erk_sira <= ke)
    return aday[al]


def ziyaretci_sec(adaylar: Adaylar, nufus, d: int, F_m: np.ndarray, rng,
                  sayac: dict | None = None, kadin_hedef: np.ndarray | None = None) -> np.ndarray:
    """Mağaza sırasıyla fiş başına müşteri `[Σ F_m]` (mağaza m'nin fişleri
    bitişik). Hayatta aday yetmezse eksik kadar yeni müşteri eklenir (ev
    mağazası m, kayıt günü d); `sayac["yeni"]` sayısı. `kadin_hedef` [M]
    verilirse mağaza başına kadın ziyaretçi kotası (modül docstring'i).
    `nufus.ekle`'den sonra çağıran sütun referanslarını yeniden
    okumalıdır."""
    F_m = np.asarray(F_m, dtype=np.int64)
    f_bas = np.cumsum(F_m) - F_m
    musteri = np.full(int(F_m.sum()), -1, dtype=np.int64)
    eksik_m, eksik_n = [], []
    for m in np.flatnonzero(F_m > 0):
        k = int(F_m[m])
        if kadin_hedef is None:
            sec = adaylar.sec(nufus, int(m), k, rng, sayac)
        else:
            genis = adaylar.sec(nufus, int(m), int(np.ceil(S.KOTA_FAZLA * k)) + S.KOTA_EK, rng, sayac)
            kadin = nufus.cinsiyet[genis] == 0
            sec = cinsiyet_kotasi(genis, kadin, k, int(kadin_hedef[m]))
            if sayac is not None:   # kotadan sapan fiş (bir cinsiyetin adayı yetmedi)
                sayac["kota_sapma"] = sayac.get("kota_sapma", 0) + abs(
                    int((nufus.cinsiyet[sec] == 0).sum()) - min(int(kadin_hedef[m]), len(sec)))
                sayac["kota_fis"] = sayac.get("kota_fis", 0) + len(sec)
        musteri[f_bas[m]:f_bas[m] + len(sec)] = sec
        if len(sec) < k:
            eksik_m.append(int(m))
            eksik_n.append(k - len(sec))
    if eksik_m:
        ev = np.repeat(np.array(eksik_m), eksik_n)
        yeni = nufus.ekle(rng, len(ev), ev_magaza=ev, kayit_gun=d)
        musteri[musteri < 0] = yeni   # mağaza sırası korunur (−1'ler mağaza bloklarının sonunda)
        if sayac is not None:
            sayac["yeni"] = sayac.get("yeni", 0) + len(yeni)
    return musteri
