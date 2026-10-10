"""Karar anının hesapları — motorun `Gorunum`u üstünde (motor içi ikiz).

İki iş:

    gunluk_gorunumden(g, havuz)   Gorunum (geçmiş kaydıyla) → ortak günlük tablo
                                  biçimi (`stok.gunluk_magaza` + `gunluk_online`)
                                  + Basit'in özellik sütunları. `sansur.karar_ani_talep`
                                  bunu, yayımlanan tablolardan kurulan günlük tabloyla
                                  aynı biçimde alır (Ruling R5: iki yol, tek fonksiyon).
    durum_gorunumden(g, ids)      karar sabahı zincir durumu (`aday.DURUM_KOLONLARI`),
                                  tablo yolundaki `aday.durum_tablodan`'ın karşılığı

ve dağıtım kurallarının yardımcıları (`Indeks`, `hucre_duzeltme`, `duzeltilmis`).

GÜNLÜK TABLO (R5). Motor `simule_et(..., gecmis_kaydi=True)` ile koşmalıdır (Ruling
R6; `rpt.motor.kos` politika `gecmis_gerekir` taşıyorsa açar): `Gorunum` o zaman
satış öncesi stok geçmişini, fiyat değişim kaydını ve pazartesi fotoğraflarını
taşır. Satırlar ortak tanımın aynısıdır:

  * mağaza hücre-günü: hücrenin o haftanın pazartesisinde ve ertesi pazartesi
    fotoğrafı var (tam hafta), mağaza o gün açık (açılış ≤ gün < kapanış, tadilat
    dışında; `magazalar`, `magaza_olay`), gün ≥ ürünün lansmanı. Ortak tablonun
    "hiç stoklanmamış hücre" kuralı (bütün pencere) burada yoktur; karar anındaki
    karşılığını `sansur.karar_ani_talep` iki yolda da uygular.
  * ONL SKU-günü: lansman ≤ gün < çıkış.
  * `satis_oncesi` motorun kaydından (fiziksel: satış öncesi raf; ONL: ertesi
    sabahın depo stoğu + günün net online satışı), `brut_satis` = `satis_gecmisi`;
    durum: bos (satis_oncesi ≤ 0), tukenen (brut ≥ satis_oncesi), stoklu.
  * pencere `PENCERE` (yayımlanan tabloların ve `hazirla`'nın penceresi); satır
    sırası `hazirla`'nın dosyasıyla aynı (yıl yıl; önce mağaza, sonra online; gün,
    mağaza, ürün); kimlikler dünyanın bütün kimlikleri üstünde `category`.
  * `net_satis` yoktur (iade geçmişi görünümde yok; kestirici okumaz).

Özellikler ortak `ozellikler.ekle` ile, yayımlanan tabloların aynısı bellek içi bir
DuckDB'ye konarak eklenir: boyut tabloları (`urun`, `sezon`, `magaza`, `takvim`,
`kampanya`) dünyanın kamuya açık alanlarıdır; `fiyat` paneli fiyat değişim
kaydından yayımlanan tanımla kurulur (option × hat × hafta: haftanın son
günündeki oran, yalnız hücre penceresiyle kesişen haftalar, 4 ondalık), yalnız
karar anına dek BİTMİŞ haftalar (hafta + 7 ≤ t). Karar anı pazartesi olmalıdır.

SIZINTI. Bu modül yalnız `Gorunum`un alanlarını ve dünyanın kamuya açık
alanlarını okur (`tests/test_sizinti.py` gizli alan listesi); bugünün ve sonrasının
hiçbir satırı görünümde yoktur.
"""

from dataclasses import dataclass
from datetime import date

import duckdb
import numpy as np
import pandas as pd
from perakende_analitik import hazirlik, ozellikler

from .aday import DURUM_KOLONLARI

PENCERE = (date(2023, 1, 1), date(2025, 12, 31))   # yayımlanan tablolar, hazirla.PENCERE
BASIT_OZELLIKLERI = list(hazirlik.KESTIRICI_OZELLIKLERI["basit"])
DURUMLAR = ["stoklu", "tukenen", "bos"]
HATLAR = ("normal", "outlet", "online")
ONLINE_TIP = "Online"
_YOK = np.iinfo(np.int64).max // 4


@dataclass
class Indeks:
    """Dünyanın option → hücre / SKU dizinleri (bir kez hesaplanır)."""

    hucre: list          # option → hücre indisleri (cesit sırası)
    sku: list            # option → SKU indisleri

    @classmethod
    def kur(cls, dunya) -> "Indeks":
        O = len(dunya.optionlar)
        ho = np.asarray(dunya.hucre_option)
        sira = np.argsort(ho, kind="stable")
        sinir = np.searchsorted(ho[sira], np.arange(O + 1))
        hucre = [sira[sinir[o]:sinir[o + 1]] for o in range(O)]
        so = np.asarray(dunya.sku_option)
        sira_s = np.argsort(so, kind="stable")
        sinir_s = np.searchsorted(so[sira_s], np.arange(O + 1))
        sku = [sira_s[sinir_s[o]:sinir_s[o + 1]] for o in range(O)]
        return cls(hucre=hucre, sku=sku)


# ---------------------------------------------------------------------------
# Günlük tablo (Ruling R5)
# ---------------------------------------------------------------------------


def _gun(tarih, gun0: pd.Timestamp) -> np.ndarray:
    """Tarih(ler) → motor gün indisi (NaT → _YOK)."""
    t = pd.to_datetime(pd.Series(np.atleast_1d(tarih)))
    g = ((t - gun0).dt.days).to_numpy(dtype=float)
    return np.where(np.isnan(g), _YOK, g).astype(np.int64)


class GunlukKurucu:
    """Bir dünyanın sabit parçaları (kimlik evrenleri, hücre dizinleri, mağaza
    takvimi, boyut tabloları) ve onlarla `__call__(g, havuz)` → günlük tablo."""

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
        self.online_m = (mag["tip"].astype(str) == ONLINE_TIP).to_numpy()
        onl_c = np.flatnonzero(self.onl)
        self.onl_hucre = np.full(len(urun), -1, dtype=np.int64)
        self.onl_hucre[self.hs[onl_c]] = onl_c
        self.idx = Indeks.kur(w)
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
        kap = _gun(mag["kapanis_tarihi"], gun0)
        self.kapanis = kap                                                  # NaT: _YOK
        ol = w.magaza_olay
        td = ol[ol["olay"].astype(str) == "tadilat"]
        harita = {m: i for i, m in enumerate(self.magaza_id)}
        self.tadilat = [(harita[str(m)], int(b), int(e)) for m, b, e in zip(
            td["magaza_id"], _gun(td["olay_tarihi"], gun0), _gun(td["bitis_tarihi"], gun0))]
        urun = w.urunler
        self.u_lansman = _gun(urun["lansman_tarihi"], gun0)
        self.u_cikis = _gun(urun["cikis_tarihi"], gun0)
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
        for ad, df in (("urun", urun), ("sezon", w.sezon), ("magaza", mag),
                       ("takvim", w.takvim), ("kampanya", w.kampanya)):
            con.register(ad, df)
        self._con = con

    def acik(self, m: np.ndarray, d: np.ndarray) -> np.ndarray:
        """Mağaza `m` gün `d`'de açık mı (ortak `gunluk_magaza`'nın c kuralı)."""
        ok = (self.acilis[m] <= d) & (d < self.kapanis[m])
        for tm, b, e in self.tadilat:
            ok &= ~((m == tm) & (d >= b) & (d < e))
        return ok

    # --- havuz ---------------------------------------------------------------
    def _havuz(self, havuz: pd.DataFrame, t: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(option indisi, bas günü, son günü) — son ≤ t; havuzda olmayan kimlik ValueError."""
        h = havuz.drop_duplicates("option_id")
        harita = pd.Index(self.option_id)
        o = harita.get_indexer(h["option_id"].astype(str))
        if (o < 0).any():
            raise ValueError(f"havuzda dünyada olmayan option: {list(h['option_id'][o < 0][:5])}")
        bas = _gun(h["bas"], self._gun0)
        son = _gun(h["son"], self._gun0) if "son" in h.columns else np.full(len(h), _YOK)
        return o, bas, np.minimum(son, t)

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

    def _satirlar(self, g, havuz: pd.DataFrame):
        t = int(g.gun)
        o, bas, son = self._havuz(havuz, t)
        p_bas, p_son = self.pencere
        bas = np.maximum(bas, p_bas)
        son = np.minimum(son, p_son + 1)
        secili = np.zeros(len(self.w.optionlar), dtype=bool)
        secili[o] = True
        o_bas = np.full(len(secili), _YOK, dtype=np.int64)
        o_son = np.full(len(secili), -_YOK, dtype=np.int64)
        o_bas[o], o_son[o] = bas, son

        # Mağaza hücreleri
        c = np.flatnonzero(secili[self.ho] & ~self.onl)
        cb = np.maximum(o_bas[self.ho[c]], self.u_lansman[self.hs[c]])
        cs = o_son[self.ho[c]]
        i, d = self._aralik(cb, cs)
        c_r = c[i]
        if len(d):
            p = d - d % 7
            p0 = int(p.min())
            F = self._fotograflar(g, p0, t)
            w0, w1 = (p - p0) // 7, (p - p0) // 7 + 1
            tam = (w1 < F.shape[0])
            tam[tam] = F[w0[tam], c_r[tam]] & F[w1[tam], c_r[tam]]
            m = self.hm[c_r]
            sec = tam & self.acik(m, d)
            c_r, d = c_r[sec], d[sec]
        magaza = (d, c_r)

        # Online SKU'lar
        sk = np.flatnonzero(secili[np.asarray(self.w.sku_option)])
        oc = self.onl_hucre[sk]
        if (oc < 0).any():
            raise ValueError("ONL hücresi olmayan SKU var (ortak tablo her SKU'yu online sayar)")
        so_ = np.asarray(self.w.sku_option)[sk]
        ob = np.maximum(o_bas[so_], self.u_lansman[sk])
        os_ = np.minimum(o_son[so_], self.u_cikis[sk])
        i, d2 = self._aralik(ob, os_)
        online = (d2, oc[i])
        return magaza, online

    def _fiyat(self, g, havuz_o: np.ndarray) -> pd.DataFrame:
        """Havuz option'larının fiyat paneli: karar anına dek biten pencere haftaları."""
        t = int(g.gun)
        p_bas, p_son = self.pencere
        pzt = np.arange(p_bas + (-p_bas) % 7, p_son + 1, 7, dtype=np.int64)
        pzt = pzt[pzt + 7 <= t]
        ci = np.flatnonzero(np.isin(self.ciftler // 3, havuz_o))
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

    def __call__(self, g, havuz: pd.DataFrame, ozellik: bool = True) -> pd.DataFrame:
        if g.satis_oncesi_gecmisi is None:
            raise ValueError("gunluk_gorunumden: Gorunum geçmiş taşımıyor; motoru "
                             "simule_et(..., gecmis_kaydi=True) ile koşun (rpt.motor.kos: "
                             "politikada gecmis_gerekir = True)")
        if int(g.gun) % 7 != 0:
            raise ValueError(f"gunluk_gorunumden: karar anı pazartesi olmalı (gün {g.gun})")
        self._hazirla(g)
        (dm, cm), (do, co) = self._satirlar(g, havuz)
        SO = np.asarray(g.satis_oncesi_gecmisi)
        SA = np.asarray(g.satis_gecmisi)
        gun = np.concatenate([dm, do])
        hucre = np.concatenate([cm, co])
        kanal = np.concatenate([np.zeros(len(dm), np.int8), np.ones(len(do), np.int8)])
        mk, uk = self.mag_kod[self.hm[hucre]], self.urun_kod[self.hs[hucre]]
        tarih = (self._gun0 + pd.to_timedelta(gun, unit="D"))
        yil = tarih.year.to_numpy()
        sira = np.lexsort((uk, mk, gun, kanal, yil))
        gun, hucre, mk, uk = gun[sira], hucre[sira], mk[sira], uk[sira]
        so = SO[gun, hucre].astype(np.int32)
        brut = SA[gun, hucre].astype(np.int32)
        durum = np.where(so <= 0, 2, np.where(brut >= so, 1, 0)).astype(np.int8)
        df = pd.DataFrame({
            "tarih": tarih.to_numpy("datetime64[ns]")[sira],
            "magaza_id": pd.Categorical.from_codes(mk, categories=self.mag_kat),
            "urun_id": pd.Categorical.from_codes(uk, categories=self.urun_kat),
            "option_id": pd.Categorical.from_codes(self.opt_kod[self.ho[hucre]], categories=self.opt_kat),
            "satis_oncesi": so,
            "brut_satis": brut,
            "durum": pd.Categorical.from_codes(durum, categories=DURUMLAR),
        })
        if not ozellik:
            return df
        o, _, _ = self._havuz(havuz, int(g.gun))
        self._con.register("fiyat", self._fiyat(g, o))
        return ozellikler.ekle(self._con, df, BASIT_OZELLIKLERI)


def gunluk_gorunumden(g, havuz: pd.DataFrame, kurucu: GunlukKurucu | None = None,
                      ozellik: bool = True) -> pd.DataFrame:
    """Karar havuzunun (`option_id, bas[, son]`) ortak günlük tablo satırları,
    `[bas, min(son, g.gun))`, Basit'in özellikleriyle (modül notu). `kurucu`
    aynı dünyanın sabitlerini çağrılar arasında saklar."""
    kurucu = kurucu if kurucu is not None else GunlukKurucu(g.dunya)
    return kurucu(g, havuz, ozellik=ozellik)


# ---------------------------------------------------------------------------
# Karar sabahı durumu
# ---------------------------------------------------------------------------


def durum_gorunumden(g, option_ids, idx: Indeks | None = None) -> pd.DataFrame:
    """Karar sabahı option'ların zincir durumu (`DURUM_KOLONLARI`), Gorunum'dan.

    Tablo yolu (`aday.durum_tablodan`) ile aynı tanımlar: satilan (dünkü akşama dek
    brüt satış, ONL dahil), gonderilen (depodan mağazalara), str, rpt_sayisi; stoklu
    ve kırık mağaza payı bu sabahın pazartesi fotoğrafından (fotoğrafta görünen
    mağazalar). Envanter bileşenleri karar anındaki sırayla: magaza ve yolda bu
    sabahın varışlarından sonra (`magaza_stok`, `yolda`), depo bu sabahın
    teslimlerinden sonra, acik henüz teslim edilmemiş siparişler. Toplamları (envanter
    pozisyonu, ip) tablo yolununkinden yalnız iki nedenle küçük kalır (testte adet
    adet bağlanır):
      * bu sabah teslim edilen siparişin kalite reddi: tablo yolunda sipariş açık
        sayılır (tam adet), görünümde depoya ret düşülmüş girer;
      * bu sabah RPT kararından önce mağazadan depoya yola çıkan mal (4. adım
        kapanış transferi, 6. adım stok devri): tablo yolunda sabah fotoğrafında,
        görünümde ne mağazada ne mağaza yoldasında (`yolda` yalnız mağazaya giden)
        ne depoda.
    Option'ın çıkış günü bunlara bir üçüncüsü eklenir (penceresi kapanan hücre o
    sabahın fotoğrafında yoktur); çıkış günü karar haftası (h ≤ 6) değildir."""
    w = g.dunya
    idx = idx or Indeks.kur(w)
    harita = pd.Index(w.optionlar["option_id"].astype(str))
    ids = pd.Index(pd.unique(pd.Series(list(option_ids), dtype=object).astype(str)), name="option_id")
    o = harita.get_indexer(ids)
    if (o < 0).any():
        raise ValueError(f"dünyada olmayan option: {list(ids[o < 0][:5])}")
    foto = next((p for p in reversed(g.stok_fotograflari or ()) if p[0] == g.gun), None)
    stok_foto = np.full(len(w.hucre_option), -1, dtype=np.int64)
    if foto is not None:
        stok_foto[np.asarray(foto[1])] = np.asarray(foto[2])
    hm = np.asarray(w.hucre_magaza)
    acik = {}
    for s in g.acik_siparisler:
        acik[s["option"]] = acik.get(s["option"], 0) + int(np.sum(s["adetler"]))
    satir = []
    for oi in o:
        c = idx.hucre[oi]
        fc = c[stok_foto[c] >= 0]
        if len(fc):
            mu, ters = np.unique(hm[fc], return_inverse=True)
            dolu = np.bincount(ters, stok_foto[fc] > 0, len(mu)) > 0
            bos = np.bincount(ters, stok_foto[fc] == 0, len(mu)) > 0
            stoklu_pay, kirik_pay = float(dolu.mean()), float((dolu & bos).mean())
        else:
            stoklu_pay = kirik_pay = 0.0
        satilan = float(g.satilan_option[oi])
        gonderilen = float(g.gonderilen_option[oi])
        satir.append({
            "satilan": satilan, "gonderilen": gonderilen,
            "str": satilan / gonderilen if gonderilen > 0 else 0.0,
            "depo": float(np.asarray(g.depo)[idx.sku[oi]].sum()),
            "magaza": float(np.asarray(g.magaza_stok)[c].sum()),
            "yolda": float(np.asarray(g.yolda)[c].sum()),
            "acik": float(acik.get(int(oi), 0)),
            "stoklu_magaza_payi": stoklu_pay, "kirik_magaza_payi": kirik_pay,
            "rpt_sayisi": int(g.rpt_sayisi[oi]),
        })
    r = pd.DataFrame(satir, columns=list(DURUM_KOLONLARI))
    r.insert(0, "option_id", ids.to_numpy())
    return r


# ---------------------------------------------------------------------------
# Dağıtım yardımcıları (stoklu gün düzeltmeli hücre hızı)
# ---------------------------------------------------------------------------


def hucre_duzeltme(s: np.ndarray, st: np.ndarray, sku: np.ndarray, agirlik: np.ndarray) -> np.ndarray:
    """Hücre başına günlük hız (stoklu gün düzeltmeli, stoksuza atamalı).

    s, st     hücrenin penceredeki satışı ve stoklu günü
    Stoksuz hücre: aynı SKU'nun stoklu hücrelerinin birleşik hızı × ağırlık /
    o hücrelerin ortalama ağırlığı; SKU'da stoklu hücre yoksa option düzeyinde
    aynısı. Dağıtım payları içindir (yeniden lansman, `dagitim`); talep
    kestirimi değildir (o `sansur.karar_ani_talep`)."""
    s = s.astype(float)
    st = st.astype(float)
    stoklu = st > 0
    hiz = np.full(len(s), np.nan)
    hiz[stoklu] = s[stoklu] / st[stoklu]
    if (~stoklu).any():
        if stoklu.any():
            sk_u, ters = np.unique(sku, return_inverse=True)
            n = len(sk_u)
            ss = np.bincount(ters, np.where(stoklu, s, 0.0), n)
            sst = np.bincount(ters, np.where(stoklu, st, 0.0), n)
            sw = np.bincount(ters, np.where(stoklu, agirlik, 0.0), n)
            sn = np.bincount(ters, stoklu.astype(float), n)
            r_sku = np.divide(ss, sst, out=np.full(n, np.nan), where=sst > 0)
            wbar = np.divide(sw, sn, out=np.full(n, np.nan), where=sn > 0)
            atanan = r_sku[ters] * agirlik / wbar[ters]
            r_opt = s[stoklu].sum() / st[stoklu].sum()
            atanan_o = r_opt * agirlik / max(agirlik[stoklu].mean(), 1e-12)
            atanan = np.where(np.isnan(atanan), atanan_o, atanan)
            hiz[~stoklu] = atanan[~stoklu]
        else:
            hiz[~stoklu] = 0.0
    return hiz


def duzeltilmis(g, hucreler: np.ndarray, agirlik: np.ndarray, bas: int, son: int):
    """`hucreler`in [bas, son) penceresinde çıplak satış x, düzeltilmiş talep D ve
    hücre hızları (`hucre_duzeltme`; `agirlik` stoksuz hücre ataması)."""
    if son <= bas:
        return 0.0, 0.0, np.zeros(len(hucreler))
    S = np.asarray(g.satis_gecmisi)[bas:son, hucreler]
    F = np.asarray(g.stoklu_gecmisi)[bas:son, hucreler]
    s, st = S.sum(axis=0), F.sum(axis=0)
    hiz = hucre_duzeltme(s, st, np.asarray(g.dunya.hucre_sku)[hucreler], agirlik)
    return float(s.sum()), float((hiz * (son - bas)).sum()), hiz
