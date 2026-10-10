"""Karar anı Basit öngörüsü (`kural_basit` kolu): motorun `Gorunum`'ü üstünde,
ortak `talep.Basit(karar_ani=t)` ile son haftanın sansür düzeltmeli talebi.

RPT vakasının `rpt/anlik.py` (`GunlukKurucu`) ve `rpt/sansur.py`
(`havuz_satirlari`, `karar_ani_talep`) parçalarının kopyasıdır: `vakalar/rpt/` ve
`vakalar/ortak/` değişmez (RPT'nin koşu önbelleği onların kod özetine bağlı;
Ruling R1'in gerekçesi). Farklar: yalnız fiziksel mağaza hücreleri (kollar online'a
dokunmaz, R14); karar havuzu option başına pencere değil, ortak bir pencere
(`[t − PENCERE_GUN, t)`); satırlar hücre indisini (`hucre`) taşır.

    karar_ani_ongoru(g, carpanlar, harita)   float[OC]: [t−7, t−1] talep kestirimi

**Öngörü.** OC başına `[t−7, t−1]`'in brüt satışı (bütün fiziksel hücre-günler,
`satis_gecmisi`) + Basit'in kaybı (yalnız ortak günlük tablonun satırlarında: `bos`
gün λ̂, gün içinde `tukenen` gün E[D | D ≥ s] − s; ortak `kayip.kayip_yaz`).
Kuralın sansür düzeltmesinin (satış ÷ stoklu gün × 7) Basit karşılığıdır; hafta
katsayısı ve güvenlik stoku çağıranın (kolun) işidir. Online OC'ler 0.

**Havuz.** Basit'in öğrendiği stoklu günler: `[t − PENCERE_GUN, t)` içinde stoklu
günü ya da satışı olan fiziksel hücrelerin option'ları, aynı pencerede. 28 gün:
hedef günlerin (`[t−7, t−1]`) ±14 günlük komşuluğu (`Basit.komsu_gun`) karar anında
`t − 1`'de kesildiği için en erken `t − 21`'e iner; bir hafta da en yakın 28 gün
yedeği ve beden payı için.

**Günlük tablo** (`GunlukKurucu`; RPT `anlik` notu, ortak `stok.gunluk_magaza`
tanımı). Motor `gecmis_kaydi=True` ile koşmalıdır (politika `gecmis_gerekir = True`):
`Gorunum` o zaman satış öncesi stok geçmişini, fiyat değişim kaydını ve pazartesi
fotoğraflarını taşır. Mağaza hücre-günü: hücrenin o haftanın pazartesisinde ve
ertesi pazartesi fotoğrafı var (tam hafta), mağaza o gün açık (açılış ≤ gün <
kapanış, tadilat dışında), gün ≥ ürünün lansmanı, gün yayımlanan pencerede.
`satis_oncesi` motorun kaydından, `brut_satis` = `satis_gecmisi`; durum: bos
(satis_oncesi ≤ 0), tukenen (brut ≥ satis_oncesi), stoklu. Pencerede hiç
stoklanmamış hücre (bütün günleri `bos`, satışı yok) düşer (karar anında çeşit).
Özellikler ortak `ozellikler.ekle` ile, dünyanın kamuya açık boyut tablolarından
(`urun`, `sezon`, `magaza`, `takvim`, `kampanya`) ve fiyat değişim kaydından
yayımlanan tanımla kurulan `fiyat` panelinden (yalnız karar anına dek bitmiş
haftalar).

**Çarpanlar** (`Carpanlar`): karar anında bilinen, oyundan önce bir kez
`hazirlik.carpanlar_kapanmis(con, gunluk_parquet, OYUN_BAS)` ile (çağıranın işi).

SIZINTI. Yalnız `Gorunum`'ün alanlarını ve dünyanın kamuya açık alanlarını okur;
geçmiş dizilerinin `t` ve sonrası satırları, `t`'den sonraki fotoğraflar ve fiyat
kayıtları okunmaz (dizi uzun olsa da; `test_anlik_gelecegi_gormez`). Bu modül
`perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz.
"""

from datetime import date

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import hazirlik, ozellikler
from perakende_analitik import kayip as ortak_kayip
from perakende_analitik.carpanlar import Carpanlar, kodlar
from perakende_analitik.talep import Basit

from .kaynak import Harita

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))   # yayımlanan tablolar (RPT `anlik.PENCERE`)
PENCERE_GUN = 28                                   # Basit havuzu: [t − 28, t)
KOMSU_GUN = 14                                     # Basit'in komşuluğu (ortak varsayılan)
BASIT_OZELLIKLERI = list(hazirlik.KESTIRICI_OZELLIKLERI["basit"])
GOZLENEN = ("tarih", "magaza_id", "urun_id", "option_id", "satis_oncesi", "brut_satis", "durum")
DURUMLAR = ["stoklu", "tukenen", "bos"]
HATLAR = ("normal", "outlet", "online")
_YOK = np.iinfo(np.int64).max // 4


def _gun(tarih, gun0: pd.Timestamp) -> np.ndarray:
    """Tarih(ler) → motor gün indisi (NaT → _YOK)."""
    t = pd.to_datetime(pd.Series(np.atleast_1d(tarih)))
    g = ((t - gun0).dt.days).to_numpy(dtype=float)
    return np.where(np.isnan(g), _YOK, g).astype(np.int64)


# ---------------------------------------------------------------------------
# Günlük tablo (RPT `anlik.GunlukKurucu`, yalnız mağaza hücreleri)
# ---------------------------------------------------------------------------


class GunlukKurucu:
    """Bir dünyanın sabit parçaları (kimlik evrenleri, mağaza takvimi, boyut
    tabloları) ve onlarla `__call__(g, optionlar, bas)` → günlük tablo."""

    def __init__(self, dunya):
        w = dunya
        self.w = w
        self.ho = np.asarray(w.hucre_option, dtype=np.int64)
        self.hs = np.asarray(w.hucre_sku, dtype=np.int64)
        self.hm = np.asarray(w.hucre_magaza, dtype=np.int64)
        self.onl = np.asarray(w.hucre_online, dtype=bool)
        self.outlet = np.asarray(w.hucre_outlet_akisi, dtype=bool)
        self.hat = np.where(self.onl, 2, np.where(self.outlet, 1, 0))
        mag = w.magazalar
        urun = w.urunler
        self.magaza_id = mag["magaza_id"].astype(str).to_numpy()
        self.urun_id = urun["urun_id"].astype(str).to_numpy()
        self.option_id = w.optionlar["option_id"].astype(str).to_numpy()
        # Kategori evrenleri ve kodları (ortak `stok._kategoriler`: sözlük sıralı, bütün tablo)
        self.mag_kat = pd.Index(sorted(self.magaza_id))
        self.urun_kat = pd.Index(sorted(self.urun_id))
        self.opt_kat = pd.Index(sorted(set(urun["option_id"].astype(str))))
        self.mag_kod = self.mag_kat.get_indexer(self.magaza_id)
        self.urun_kod = self.urun_kat.get_indexer(self.urun_id)
        self.opt_kod = self.opt_kat.get_indexer(self.option_id)
        self._gun0 = None
        self._con = None

    # --- sabitler (ilk görünümde, gün indisi ekseniyle) ---------------------
    def _hazirla(self, g) -> None:
        gun0 = pd.Timestamp(g.tarih).normalize() - pd.Timedelta(days=int(g.gun))
        if self._gun0 is not None:
            if gun0 != self._gun0:
                raise ValueError("GunlukKurucu: görünümün takvimi değişti")
            return
        if gun0.dayofweek != 0:
            raise ValueError(f"motor günü 0 pazartesi olmalı: {gun0.date()}")
        self._gun0 = gun0
        w = self.w
        mag = w.magazalar
        self.acilis = _gun(mag["acilis_tarihi"], gun0)                       # NaT: hiç açık değil
        self.kapanis = _gun(mag["kapanis_tarihi"], gun0)                     # NaT: _YOK
        ol = w.magaza_olay
        td = ol[ol["olay"].astype(str) == "tadilat"]
        sira = {m: i for i, m in enumerate(self.magaza_id)}
        self.tadilat = [(sira[str(m)], int(b), int(e)) for m, b, e in zip(
            td["magaza_id"], _gun(td["olay_tarihi"], gun0), _gun(td["bitis_tarihi"], gun0))]
        self.u_lansman = _gun(w.urunler["lansman_tarihi"], gun0)
        self.pencere = (int(_gun(pd.Timestamp(PENCERE[0]), gun0)[0]),
                        int(_gun(pd.Timestamp(PENCERE[1]), gun0)[0]))
        # (option, hat) çiftlerinin hücre penceresi (yayımlanan `fiyat` tablosunun tanımı)
        cift = self.ho * 3 + self.hat
        self.ciftler, ters = np.unique(cift, return_inverse=True)
        self.cift_acilis = np.full(len(self.ciftler), _YOK, dtype=np.int64)
        self.cift_kapanis = np.full(len(self.ciftler), -_YOK, dtype=np.int64)
        np.minimum.at(self.cift_acilis, ters, np.asarray(w.hucre_acilis, dtype=np.int64))
        np.maximum.at(self.cift_kapanis, ters, np.asarray(w.hucre_kapanis, dtype=np.int64))
        con = duckdb.connect()
        for ad, df in (("urun", w.urunler), ("sezon", w.sezon), ("magaza", mag),
                       ("takvim", w.takvim), ("kampanya", w.kampanya)):
            con.register(ad, df)
        self._con = con

    def acik(self, m: np.ndarray, d: np.ndarray) -> np.ndarray:
        """Mağaza `m` gün `d`'de açık mı (ortak `gunluk_magaza`'nın c kuralı)."""
        ok = (self.acilis[m] <= d) & (d < self.kapanis[m])
        for tm, b, e in self.tadilat:
            ok &= ~((m == tm) & (d >= b) & (d < e))
        return ok

    @staticmethod
    def _aralik(bas: np.ndarray, son: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Satır başına [bas, son) günleri: (satır sahibi indisi, gün)."""
        n = np.maximum(son - bas, 0)
        sahip = np.repeat(np.arange(len(n)), n)
        bas_r = np.repeat(bas, n)
        ofset = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
        return sahip, bas_r + ofset

    def _fotograflar(self, g, p0: int, p1: int) -> np.ndarray:
        """[hafta, C] bool: p0..p1 pazartesilerinde hücrenin fotoğrafı var mı."""
        F = np.zeros(((p1 - p0) // 7 + 1, len(self.ho)), dtype=bool)
        for gun, hucre, *_ in g.stok_fotograflari:
            if p0 <= gun <= p1 and gun % 7 == 0:
                F[(gun - p0) // 7, np.asarray(hucre)] = True
        return F

    def _satirlar(self, g, optionlar: np.ndarray, bas: int) -> tuple[np.ndarray, np.ndarray]:
        """(gün, hücre): `optionlar`ın mağaza hücrelerinin `[bas, t)` günleri (modül notu)."""
        t = int(g.gun)
        p_bas, p_son = self.pencere
        secili = np.zeros(len(self.w.optionlar), dtype=bool)
        secili[optionlar] = True
        c = np.flatnonzero(secili[self.ho] & ~self.onl)
        cb = np.maximum(max(bas, p_bas), self.u_lansman[self.hs[c]])
        cs = np.full(len(c), min(t, p_son + 1), dtype=np.int64)
        i, d = self._aralik(cb, cs)
        c_r = c[i]
        if len(d):
            p = d - d % 7
            p0 = int(p.min())
            F = self._fotograflar(g, p0, t)
            w0, w1 = (p - p0) // 7, (p - p0) // 7 + 1
            tam = (w1 < F.shape[0])
            tam[tam] = F[w0[tam], c_r[tam]] & F[w1[tam], c_r[tam]]
            sec = tam & self.acik(self.hm[c_r], d)
            c_r, d = c_r[sec], d[sec]
        return d, c_r

    def _fiyat(self, g, optionlar: np.ndarray) -> pd.DataFrame:
        """Option'ların fiyat paneli: karar anına dek biten pencere haftaları."""
        t = int(g.gun)
        p_bas, p_son = self.pencere
        pzt = np.arange(p_bas + (-p_bas) % 7, p_son + 1, 7, dtype=np.int64)
        pzt = pzt[pzt + 7 <= t]
        ci = np.flatnonzero(np.isin(self.ciftler // 3, optionlar))
        ic = ((pzt[None, :] + 7 > self.cift_acilis[ci, None])
              & (pzt[None, :] < self.cift_kapanis[ci, None]))
        a, b = np.nonzero(ic)
        cift = self.ciftler[ci[a]]
        sorgu = pzt[b] + 6
        parca = [p for p in g.fiyat_gecmisi if len(p[1])]
        oran = np.zeros(len(cift))
        if parca:
            fg = np.concatenate([np.full(len(p[1]), p[0], dtype=np.int64) for p in parca])
            fo = np.concatenate([np.asarray(p[1], dtype=np.int64) for p in parca])
            fh = np.concatenate([np.asarray(p[2], dtype=np.int64) for p in parca])
            fr = np.concatenate([np.asarray(p[3], dtype=float) for p in parca])
            anahtar = fo * 3 + fh
            BUYUK = 10_000_000
            # aynı gün: kayıt sırası, sonuncu geçerli
            sira = np.lexsort((np.arange(len(fg)), fg, anahtar))
            kf = anahtar[sira] * BUYUK + fg[sira]
            j = np.searchsorted(kf, cift * BUYUK + sorgu, side="right") - 1
            gecerli = (j >= 0) & (kf[np.maximum(j, 0)] // BUYUK == cift)
            oran = np.where(gecerli, fr[sira][np.maximum(j, 0)], 0.0)
        return pd.DataFrame({
            "hafta_baslangic": (self._gun0 + pd.to_timedelta(pzt[b], unit="D")).to_numpy("datetime64[ns]"),
            "option_id": self.option_id[cift // 3],
            "hat": np.array(HATLAR)[cift % 3],
            "indirim_orani": np.round(oran, 4),
        })

    def __call__(self, g, optionlar: np.ndarray, bas: int) -> pd.DataFrame:
        """`optionlar`ın (option indisleri) mağaza hücre-günleri `[bas, g.gun)`:
        `hucre` + `GOZLENEN` + Basit'in özellikleri; satırlar (gün, mağaza, ürün) sırasıyla."""
        if g.satis_oncesi_gecmisi is None:
            raise ValueError("karar anı Basit'i: Gorunum geçmiş taşımıyor; motoru "
                             "simule_et(..., gecmis_kaydi=True) ile koşun (politikada "
                             "gecmis_gerekir = True)")
        if int(g.gun) % 7 != 0:
            raise ValueError(f"karar anı pazartesi olmalı (gün {g.gun})")
        self._hazirla(g)
        gun, hucre = self._satirlar(g, np.asarray(optionlar, dtype=np.int64), bas)
        mk, uk = self.mag_kod[self.hm[hucre]], self.urun_kod[self.hs[hucre]]
        sira = np.lexsort((uk, mk, gun))
        gun, hucre, mk, uk = gun[sira], hucre[sira], mk[sira], uk[sira]
        so = np.asarray(g.satis_oncesi_gecmisi)[gun, hucre].astype(np.int32)
        brut = np.asarray(g.satis_gecmisi)[gun, hucre].astype(np.int32)
        durum = np.where(so <= 0, 2, np.where(brut >= so, 1, 0)).astype(np.int8)
        df = pd.DataFrame({
            "hucre": hucre,
            "tarih": (self._gun0 + pd.to_timedelta(gun, unit="D")).to_numpy("datetime64[ns]"),
            "magaza_id": pd.Categorical.from_codes(mk, categories=self.mag_kat),
            "urun_id": pd.Categorical.from_codes(uk, categories=self.urun_kat),
            "option_id": pd.Categorical.from_codes(self.opt_kod[self.ho[hucre]], categories=self.opt_kat),
            "satis_oncesi": so,
            "brut_satis": brut,
            "durum": pd.Categorical.from_codes(durum, categories=DURUMLAR),
        })
        self._con.register("fiyat", self._fiyat(g, np.asarray(optionlar, dtype=np.int64)))
        return ozellikler.ekle(self._con, df, BASIT_OZELLIKLERI)


# ---------------------------------------------------------------------------
# Kestirim (RPT `sansur.havuz_satirlari` + `karar_ani_talep`)
# ---------------------------------------------------------------------------


def _stoklanmis(gunluk: pd.DataFrame) -> pd.DataFrame:
    """Pencerede en az bir stoklu / tükenen günü ya da satışı olan hücrelerin satırları."""
    m, _ = kodlar(gunluk["magaza_id"])
    u, urunler = kodlar(gunluk["urun_id"])
    anahtar = m.astype(np.int64) * (len(urunler) + 1) + u
    ters = pd.factorize(anahtar)[0]
    acik = ((gunluk["durum"] != "bos").to_numpy() | (gunluk["brut_satis"].to_numpy() > 0)).astype(float)
    stoklanmis = np.bincount(ters, acik, ters.max() + 1 if len(ters) else 0) > 0
    return gunluk[stoklanmis[ters]].reset_index(drop=True)


def karar_ani_kaybi(gunluk: pd.DataFrame, t, carpanlar: Carpanlar) -> pd.DataFrame:
    """`hucre, tarih, kayip`: `gunluk`ün (`GunlukKurucu` çıktısı) `t`'den önceki,
    stoklanmış hücrelerinin satırları; `bos` / `tukenen` satırda Basit kaybı, stoklu
    satırda 0. Havuzda stoklu gün yoksa boş tablo (Basit'in öğreneceği bir şey yok)."""
    t = pd.Timestamp(t).normalize()
    g = _stoklanmis(gunluk[(gunluk["tarih"] < t).to_numpy()].reset_index(drop=True))
    sonuc = g[["hucre", "tarih"]].copy()
    sonuc["kayip"] = 0.0
    if not (g["durum"] == "stoklu").any():
        return sonuc.iloc[:0]
    k = Basit(KOMSU_GUN, carpanlar=carpanlar, karar_ani=t)
    k.egit(g)
    hedef = np.flatnonzero((g["durum"] != "stoklu").to_numpy())
    if len(hedef):
        h = g.iloc[hedef]
        kd = ortak_kayip.kayip_yaz(h[list(GOZLENEN)], k.tahmin(h))
        sonuc.iloc[hedef, sonuc.columns.get_loc("kayip")] = kd["kayip"].to_numpy()
    return sonuc


def karar_ani_ongoru(g, carpanlar: Carpanlar, harita: Harita, *,
                     kurucu: GunlukKurucu | None = None) -> np.ndarray:
    """float[OC]: `[t−7, t−1]` talep kestirimi = brüt satış + Basit kaybı (modül notu);
    online OC'ler 0. `kurucu` aynı dünyanın sabitlerini çağrılar arasında saklar."""
    t = int(g.gun)
    if t < PENCERE_GUN:
        raise ValueError(f"karar anı Basit'i {PENCERE_GUN} günlük geçmiş ister (gün {t})")
    kurucu = kurucu if kurucu is not None else GunlukKurucu(g.dunya)
    if kurucu.w is not g.dunya:
        raise ValueError("kurucu başka bir dünyanın (koşu başında yeniden kurun)")
    S = np.asarray(g.satis_gecmisi)
    F = np.asarray(g.stoklu_gecmisi)
    fiziksel = ~harita.hucre_online
    OC = len(harita.oc_magaza)
    brut = np.where(fiziksel, S[t - 7:t].sum(axis=0, dtype=np.int64), 0)
    ongoru = np.bincount(harita.oc, weights=brut, minlength=OC)

    bas = t - PENCERE_GUN
    aktif = fiziksel & ((S[bas:t] > 0).any(axis=0) | F[bas:t].any(axis=0))
    optionlar = np.unique(harita.hucre_option[aktif])
    if not optionlar.size:
        return ongoru
    tarih = pd.Timestamp(g.tarih).normalize()
    kayip = karar_ani_kaybi(kurucu(g, optionlar, bas), tarih, carpanlar)
    son = kayip[(kayip["tarih"] >= tarih - pd.Timedelta(days=7)).to_numpy()]
    return ongoru + np.bincount(harita.oc[son["hucre"].to_numpy()], weights=son["kayip"].to_numpy(),
                                minlength=OC)
