"""Tahmin: karar pazartesisinde bir test option'ının hücre × kalan hafta tam fiyat taban talebi,
satılabilir stoğu ve fiyat çarpanları (spec §3.2). `model.coz`un girdileri (`d`, `w`, `X0`, `carpan`,
`etkin_oran`, `iade`) buradan gelir.

Karar modülüdür: `perakende_veri`'yi ve ölçüm tarafını içe aktarmaz; `Gorunum`'ün alanlarını ve
dünyanın yalnız açık alanlarını okur (`perakende_veri/v4/motor/durum.py`, `Gorunum` belgesi):
`optionlar`, `urunler`, `magazalar`, `kampanya`, `takvim`, `hucre_magaza`, `hucre_sku`,
`hucre_option`, `hucre_online`, `hucre_outlet_akisi`, `sku_beden_payi`. Kampanya oranı açık `kampanya`
tablosundan motorun kuralıyla yeniden hesaplanır (`kampanya_oranlari`; testi motorunkiyle eşitler);
dünyanın önceden hesaplanmış takvimi (`kampanya_takvimi`) belgedeki açık listede olmadığı için okunmaz.

**Hücreler.** Option'ın bütün hücreleri, outlet akışı hücreleri (`hucre_outlet_akisi`; çıkıştan sonra
outlet hattında satar) hariç; ONL bir mağaza gibidir (stoğu depo). Hücre başına beden payı: öğrenilen
`beden_payi`nın mağaza satırı, yoksa zincir satırı (`"*"`), yoksa dünyanın `sku_beden_payi`; mağaza ×
option içinde 1'e normalize (hepsi 0'sa eşit).

**Taban talep** (`taban`). Geçmiş yalnız `g.gun`den önceki satırlardır (`satis_gecmisi[:gun]`;
bugünün ve sonrasının satırlarına bakılmaz). Stoklu gün: `satis_oncesi_gecmisi` kayıtlıysa satış
öncesi stok > 0 ve gün içinde bitmemiş (satış < satış öncesi; ortak günlük tablonun `stoklu`su), değilse
`stoklu_gecmisi`. Gözlenen satış günün çarpanına bölünür:

    f(gün, hücre) = hafta_gunu(kanal, haftanın günü) × ozel_gun(tür) × I(lansmandan hafta)
                    × (1 − max(md, kampanya))^(−ε̂)

md hücrenin hattının (fiziksel: normal, ONL: online) o günkü markdown oranıdır. Öncelik sırası:
(1) yapıcının `oran_gecmisi` verildiyse kolun kendi oran kaydı (Ruling R12: sarmalayıcı test
option'larının normal ve online sütununu baştan kendisi yazar, oran geçmişini bilir; iki hat aynı oran);
(2) `g.fiyat_gecmisi` kayıtlıysa değişim kaydından (o güne kadar son değer); (3) ikisi de yoksa bütün
geçmiş günler için bugünkü `g.fiyat_orani` (oran son 28 günde değiştiyse çevirme o günlerde yaklaşıktır).
Hangi kaynak olursa olsun yalnız `g.gun`den önceki günlerin oranı okunur.
ε̂ çevirme tablosundan (yapıcının `eps`i; varsayılan `eps_kampanya`), üst kategori, yoksa `"*"`.
Mağaza (ya da ONL) başına hız

    V_m = Σ_hücre Σ_stoklu gün satış ÷ f   ÷   Σ_hücre beden payı × stoklu gün

son `HIZ_GUN` günde, payda (option-gün eşdeğeri maruziyet) `HIZ_ESIGI`'nden azsa son `HIZ_GUN_UZUN`
günde, o da azsa **zincir hızı × mağaza payı**: V_m = Σ_{veri olan m'} V_m' × P_m ÷ Σ_{veri olan m'}
P_m'; P_m mağazanın son 28 günde servis edilen bütün option'ların satışındaki payı. Hiçbir mağazada
veri yoksa talep 0. İleriye `d[t, hücre] = Σ_{t haftasının günleri} V_m × pay × hafta_gunu × ozel_gun
× I(hafta)` (tam fiyat; I öğrenilen yaşam eğrisi, son haftanın ötesi son değer). `ufuk` gün dizisidir;
hafta t `ufuk[7t:7t+7]` (son hafta eksik olabilir).

**Satılabilir stok** (`satilabilir`). `X0 = Σ fiziksel hücre rafı + yolda + option'ın SKU'larının depo
stoğu`. Hücre payı `w = (kendi rafı + yolda + depo_s × D_hücre ÷ Σ_{s'nin hücreleri} D) ÷ X0`, D ufuk
talebi (`d`nin toplamı); ONL'nin rafı yok, payı yalnız depodan. SKU'nun hücrelerinde talep 0'sa depo
raf payıyla, raf da 0'sa eşit dağıtılır; X0 = 0'sa w eşit (NaN yok). Replenishment'ın yaklaşımı:
depo talebe göre hücrelere gider (iyimser, bilinerek; spec §3.2).

**Fiyat çarpanı** (`carpan`). Hafta t, basamak k: `carpan[t, k]` = Σ taban talep × (1 − max(r_k,
kampanya))^(−ε) ÷ Σ taban talep (hücre-günler üstünde; talep 0 haftada eşit ağırlık). `etkin[t, k]` =
satılan birim ağırlıklı etkin indirim: oran = max(r_k, kampanya), oran 0'sa öğrenilen işlem indirimi
beklentisi (`Ogrenilen.islem`).

**Hız.** Dünyaya özgü hücre dizileri ilk çağrıda bir kez kurulur (servis edilen option'lar için);
gün başına mağaza payı ve markdown geçmişi o günün ilk çağrısında; `carpan` aynı (gün, option, ufuk)
için `taban`ın günlük talebini yeniden kullanır.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from markdown import sabitler
from markdown.ogrenme import Ogrenilen, yasam_orani
from markdown.sabitler import HIZ_GUN, HIZ_GUN_UZUN, KADEMELER

HIZ_ESIGI = 7.0          # bir hız penceresinde en az beden payı × stoklu gün (option-gün eşdeğeri)
PAY_GUN = 28             # mağaza payının penceresi (gün)
_NORMAL, _ONLINE = 0, 2  # fiyat hattı sütunları
_KANALLAR = ("magaza", "online")
_OZEL = ("black_friday", "black_friday_devami", "tatil", "indirim_baslangici")   # öncelik sırası
_HAFTA_GUNU_0 = pd.Timestamp(sabitler.GUN_SIFIRI).weekday()      # gün 0'ın haftanın günü


def fiyat_carpani(oran: np.ndarray, eps: float) -> np.ndarray:
    """(1 − oran)^(−ε) (oran 0,99'da kırpılır)."""
    return np.exp(-float(eps) * np.log1p(-np.clip(oran, 0.0, 0.99)))


def _gun(tarih) -> int:
    return int((pd.Timestamp(tarih) - pd.Timestamp(sabitler.GUN_SIFIRI)).days)


def _dolu(kapsam) -> bool:
    """Kapsam dizgesi dolu mu (boş, None ya da NaN: hepsi)."""
    return not (kapsam is None or (isinstance(kapsam, float) and np.isnan(kapsam)) or not str(kapsam).strip())


def _kapsam(degerler: np.ndarray, kapsam) -> np.ndarray:
    """Boş kapsam = hepsi; aksi halde virgüllü listeye üyelik (motorun `_kapsam_maskesi`)."""
    if not _dolu(kapsam):
        return np.ones(len(degerler), dtype=bool)
    return np.isin(degerler, [k.strip() for k in str(kapsam).split(",")])


def _kampanya_kurallari(kampanya: pd.DataFrame, magazalar: pd.DataFrame, option) -> list:
    """Option'ı kapsayan kampanyalar: [(ilk gün, son gün (dahil), oran, [M] mağaza maskesi)]."""
    bolge = magazalar["bolge"].astype(str).to_numpy()
    online = (magazalar["tip"].astype(str) == "Online").to_numpy()
    ust, line = np.array([str(option["ust_kategori"])]), np.array([str(option["line"])])
    kurallar = []
    for k in kampanya.itertuples(index=False):
        if not (_kapsam(ust, k.kapsam_ust_kategori)[0] and _kapsam(line, k.kapsam_line)[0]):
            continue
        m = (_kapsam(bolge, k.kapsam_bolge) & ~online) if _dolu(k.kapsam_bolge) \
            else np.ones(len(bolge), dtype=bool)
        if m.any():
            kurallar.append((_gun(k.baslangic), _gun(k.bitis), float(k.oran), m))
    return kurallar


def _kampanya_uygula(kurallar: list, gunler: np.ndarray, M: int) -> np.ndarray:
    oran = np.zeros((len(gunler), M))
    for d0, d1, r, m in kurallar:
        aktif = (gunler >= d0) & (gunler <= d1)
        if aktif.any():
            oran[np.ix_(aktif, m)] = np.maximum(oran[np.ix_(aktif, m)], r)
    return oran


def kampanya_oranlari(kampanya: pd.DataFrame, magazalar: pd.DataFrame, option,
                      gunler: np.ndarray) -> np.ndarray:
    """[U, M] bir option'ın gün × mağaza kampanya oranı (en yüksek geçerli oran; bölgeli kampanya
    ONL'yi kapsamaz). `option` dünyanın `optionlar` satırı (`ust_kategori`, `line`)."""
    gunler = np.asarray(gunler, dtype=np.int64)
    return _kampanya_uygula(_kampanya_kurallari(kampanya, magazalar, option), gunler, len(magazalar))


@dataclass
class _Option:
    hucre: np.ndarray        # [N] dünya hücre indisi
    sku: np.ndarray          # [N] dünya SKU indisi
    sku_yerel: np.ndarray    # [N] option içi SKU sırası
    skular: np.ndarray       # [S_o] dünya SKU indisi
    yerel: np.ndarray        # [N] option içi mağaza sırası
    magazalar: np.ndarray    # [M_o] dünya mağaza indisi
    online: np.ndarray       # [N] bool
    pay: np.ndarray          # [N] beden payı (mağaza içinde 1)
    lansman: int
    indirim: int
    egri: np.ndarray         # yaşam çarpanı (hafta)
    kurallar: list           # kampanya kuralları (mağaza maskesi dünya mağazaları üstünde)
    eps: float               # çevirme ε̂'sı


class Tahminci:
    """Servis edilen option'lar (`optionlar`: dünya option indisleri) için taban talep, satılabilir
    stok ve fiyat çarpanı (modül docstring'i). `eps`: tam fiyata çevirmede kullanılan ε̂ tablosu
    (üst kategori -> ε̂, `"*"` havuz); verilmezse `ogrenilen.eps_kampanya`. `oran_gecmisi`: verilirse
    `oran_gecmisi(o) -> (gunler [n], oranlar [n])` option'ın normal ve online hattının oran değişim
    kaydı (gün sırasıyla; oran o günden itibaren geçerli, ilk değişimden önce 0); geçmiş günlerin
    markdown'ı `g.fiyat_gecmisi` yerine buradan okunur (Ruling R12)."""

    def __init__(self, ogrenilen: Ogrenilen, optionlar, eps: dict | None = None,
                 oran_gecmisi: Callable[[int], tuple[np.ndarray, np.ndarray]] | None = None):
        self.ogrenilen = ogrenilen
        self.optionlar = np.unique(np.asarray(optionlar, dtype=np.int64))
        self.eps_tablosu = dict(ogrenilen.eps_kampanya if eps is None else eps)
        self.oran_gecmisi = oran_gecmisi
        self._hg = np.array([[float(ogrenilen.hafta_gunu.get((k, g), 1.0)) for g in range(7)]
                             for k in _KANALLAR])
        self._oz = np.array([float(ogrenilen.ozel_gun.get(t, 1.0)) for t in _OZEL])
        self._dunya_id = None
        self._gun_anahtari = None
        self._son = None

    # ------------------------------------------------------------- hazırlık

    def _dunya(self, w) -> None:
        if self._dunya_id == id(w):
            return
        ho = np.asarray(w.hucre_option, dtype=np.int64)
        hm = np.asarray(w.hucre_magaza, dtype=np.int64)
        hs = np.asarray(w.hucre_sku, dtype=np.int64)
        on = np.asarray(w.hucre_online, dtype=bool)
        outlet = np.asarray(w.hucre_outlet_akisi, dtype=bool)
        opt = w.optionlar
        mag_id = w.magazalar["magaza_id"].astype(str).to_numpy()
        urun_id = w.urunler["urun_id"].astype(str).to_numpy()
        zincir_pay = np.asarray(w.sku_beden_payi, dtype=float)

        bp = self.ogrenilen.beden_payi
        b_mag, b_urun = bp["magaza_id"].astype(str).to_numpy(), bp["urun_id"].astype(str).to_numpy()
        b_pay, zin = bp["pay"].to_numpy(dtype=float), b_mag == "*"
        bp_magaza = pd.Series(b_pay[~zin], index=pd.MultiIndex.from_arrays([b_mag[~zin], b_urun[~zin]]))
        bp_zincir = pd.Series(b_pay[zin], index=pd.Index(b_urun[zin]))

        sira = np.argsort(ho, kind="stable")
        sirali = ho[sira]
        self._opt = {}
        for o in self.optionlar:
            c = sira[np.searchsorted(sirali, o, "left"):np.searchsorted(sirali, o, "right")]
            c = np.sort(c[~outlet[c]])
            magazalar, yerel = np.unique(hm[c], return_inverse=True)
            skular, sku_yerel = np.unique(hs[c], return_inverse=True)
            anahtar = pd.MultiIndex.from_arrays([mag_id[hm[c]], urun_id[hs[c]]])
            pay = bp_magaza.reindex(anahtar).to_numpy(dtype=float)
            z = bp_zincir.reindex(urun_id[hs[c]]).to_numpy(dtype=float)
            pay = np.where(np.isfinite(pay), pay, np.where(np.isfinite(z), z, zincir_pay[hs[c]]))
            pay = np.where(np.isfinite(pay) & (pay > 0), pay, 0.0)
            toplam = np.bincount(yerel, pay, minlength=len(magazalar))
            sayi = np.bincount(yerel, minlength=len(magazalar))
            pay = np.where(toplam[yerel] > 0, pay / np.where(toplam[yerel] > 0, toplam[yerel], 1.0),
                           1.0 / sayi[yerel])
            satir = opt.iloc[int(o)]
            self._opt[int(o)] = _Option(
                hucre=c, sku=hs[c], sku_yerel=sku_yerel, skular=skular, yerel=yerel, magazalar=magazalar,
                online=on[c], pay=pay, lansman=int(satir["lansman_gun"]), indirim=int(satir["indirim_gun"]),
                egri=self.ogrenilen.yasam_egrisi(satir["alt_kategori"], satir["ust_kategori"],
                                                 int(satir["dalga"])),
                kurallar=_kampanya_kurallari(w.kampanya, w.magazalar, satir),
                eps=float(self.eps_tablosu.get(str(satir["ust_kategori"]), self.eps_tablosu.get("*", 0.0))))
        self._servis_hucre = np.concatenate([v.hucre for v in self._opt.values()]) if self._opt \
            else np.zeros(0, np.int64)
        self._hm = hm
        self._M = len(mag_id)
        n = len(w.takvim)
        self._tatil = np.asarray(w.takvim["tatil_mi"], dtype=bool)
        self._bf = np.zeros(n, dtype=bool)
        k = w.kampanya
        for r in k[k["tip"].astype(str) == "black_friday"].itertuples(index=False):
            self._bf[max(_gun(r.baslangic), 0):max(min(_gun(r.bitis) + 1, n), 0)] = True
        self._dunya_id = id(w)
        self._gun_anahtari = None
        self._son = None

    def _gunluk_hazirlik(self, g) -> None:
        """Gün başına: mağaza payı (son 28 gün servis satışı) ve markdown geçmişi (olaylar)."""
        anahtar = (id(g.dunya), int(g.gun), id(g))
        if self._gun_anahtari == anahtar:
            return
        gun = int(g.gun)
        s = np.asarray(g.satis_gecmisi[max(0, gun - PAY_GUN):gun, self._servis_hucre], dtype=float).sum(0)
        p = np.bincount(self._hm[self._servis_hucre], s, minlength=self._M)
        self._pay_magaza = p / p.sum() if p.sum() > 0 else np.full(self._M, 1.0 / self._M)
        self._md_olay = None
        if g.fiyat_gecmisi is not None:
            olay: dict = {}
            for parca in g.fiyat_gecmisi:
                d = int(parca[0])
                if d >= gun:
                    continue
                oo, hh, rr = (np.asarray(x) for x in parca[1:4])
                sec = np.isin(oo, self.optionlar) & ((hh == _NORMAL) | (hh == _ONLINE))
                for o, h, r in zip(oo[sec], hh[sec], rr[sec]):
                    olay.setdefault((int(o), int(h)), []).append((d, float(r)))
            self._md_olay = {}
            for k, v in olay.items():
                gunler, oranlar = np.array([a for a, _ in v]), np.array([b for _, b in v])
                sira = np.argsort(gunler, kind="stable")      # aynı gün: kayıt sırasıyla son değer
                self._md_olay[k] = (gunler[sira], oranlar[sira])
        self._gun_anahtari = anahtar
        self._son = None

    def _hazir(self, g, o: int) -> _Option:
        self._dunya(g.dunya)
        self._gunluk_hazirlik(g)
        return self._opt[int(o)]

    # ------------------------------------------------------------- çarpanlar

    def _gun_carpani(self, b: _Option, gunler: np.ndarray) -> np.ndarray:
        """[U, N] hafta günü × özel gün × yaşam (fiyat hariç)."""
        hgun = (gunler + _HAFTA_GUNU_0) % 7                                # pazartesi 0
        hg = self._hg[b.online.astype(np.int64)[None, :], hgun[:, None]]
        n = len(self._tatil)
        i = np.clip(gunler, 0, n - 1)
        icinde = (gunler >= 0) & (gunler < n)
        bf = self._bf[i] & icinde
        cuma = hgun == 4
        tatil = self._tatil[i] & icinde
        ib = (gunler >= b.indirim) & (gunler < b.indirim + 7)
        oz = np.ones(len(gunler))
        alindi = np.zeros(len(gunler), dtype=bool)
        for f, t in zip(self._oz, (bf & cuma, bf & ~cuma, tatil, ib)):
            t = t & ~alindi
            oz[t] *= f
            alindi |= t
        yas = yasam_orani(b.egri, (gunler - b.lansman) // 7)
        return hg * (oz * yas)[:, None]

    def _md(self, g, o: int, b: _Option, gunler: np.ndarray) -> np.ndarray:
        """[U, N] geçmiş günlerin hücre hattı markdown oranı."""
        if self.oran_gecmisi is not None:
            gun, oran = (np.asarray(x) for x in self.oran_gecmisi(int(o)))
            gecmis = gun < int(g.gun)
            gun, oran = gun[gecmis].astype(np.int64), oran[gecmis].astype(float)
            i = np.searchsorted(gun, gunler, side="right") - 1
            md = np.where(i >= 0, oran[np.maximum(i, 0)] if len(oran) else 0.0, 0.0)
            return np.repeat(md[:, None], len(b.hucre), axis=1)
        sonuc = np.empty((len(gunler), 2))
        for j, h in enumerate((_NORMAL, _ONLINE)):
            if self._md_olay is None:
                sonuc[:, j] = float(g.fiyat_orani[o, h])
                continue
            gun, oran = self._md_olay.get((o, h), (np.zeros(0, np.int64), np.zeros(0)))
            i = np.searchsorted(gun, gunler, side="right") - 1
            sonuc[:, j] = np.where(i >= 0, oran[np.maximum(i, 0)] if len(oran) else 0.0, 0.0)
        return sonuc[:, b.online.astype(np.int64)]

    def _kampanya(self, b: _Option, gunler: np.ndarray) -> np.ndarray:
        """[U, N] hücrelerin kampanya oranı."""
        return _kampanya_uygula(b.kurallar, gunler, self._M)[:, self._hm[b.hucre]]

    # ------------------------------------------------------------- arayüz

    def option_eps(self, g, o: int) -> float:
        """Option'ın çevirme tablosundaki ε̂'sı (üst kategori, yoksa havuz)."""
        return self._hazir(g, o).eps

    def hucreler(self, g, o: int) -> np.ndarray:
        """Option'ın hücreleri (`taban`ın döndürdüğü sırayla; outlet akışı hariç)."""
        return self._hazir(g, o).hucre.copy()

    def _gunluk_talep(self, g, o: int, ufuk: np.ndarray) -> np.ndarray:
        anahtar = (id(g), int(g.gun), int(o), ufuk.tobytes())
        if self._son is not None and self._son[0] == anahtar:
            return self._son[1]
        self.taban(g, o, ufuk)
        return self._son[1]

    def taban(self, g, o: int, ufuk) -> tuple[np.ndarray, np.ndarray]:
        """(hücreler [N], d [T, N]): ufuk haftalarında hücre başına tam fiyat taban talep."""
        b = self._hazir(g, o)
        ufuk = np.asarray(ufuk, dtype=np.int64)
        gun = int(g.gun)
        bas = max(0, gun - HIZ_GUN_UZUN)
        gunler = np.arange(bas, gun)
        c = b.hucre
        s = np.asarray(g.satis_gecmisi[bas:gun, c], dtype=float)
        if g.satis_oncesi_gecmisi is not None:
            so = np.asarray(g.satis_oncesi_gecmisi[bas:gun, c], dtype=float)
            st = (so > 0) & (s < so)
        else:
            st = np.asarray(g.stoklu_gecmisi[bas:gun, c], dtype=bool)
        f = self._gun_carpani(b, gunler) * fiyat_carpani(
            np.maximum(self._md(g, int(o), b, gunler), self._kampanya(b, gunler)), b.eps)
        duz = np.where(st, s / f, 0.0)

        nm = len(b.magazalar)
        V = np.full(nm, np.nan)
        for W in (HIZ_GUN, HIZ_GUN_UZUN):
            son = slice(max(0, len(gunler) - W), None)
            S = np.bincount(b.yerel, duz[son].sum(0), minlength=nm)
            E = np.bincount(b.yerel, b.pay * st[son].sum(0), minlength=nm)
            yeni = np.isnan(V) & (E >= HIZ_ESIGI)
            V[yeni] = S[yeni] / E[yeni]
        var = np.isfinite(V)
        pm = self._pay_magaza[b.magazalar]
        if var.any() and pm[var].sum() > 0:
            V[~var] = V[var].sum() * pm[~var] / pm[var].sum()
        V = np.where(np.isfinite(V), V, 0.0)

        gunluk = (V[b.yerel] * b.pay)[None, :] * self._gun_carpani(b, ufuk)
        self._son = ((id(g), gun, int(o), ufuk.tobytes()), gunluk)
        return c.copy(), _haftalik(gunluk)

    def satilabilir(self, g, o: int, hucreler: np.ndarray, d: np.ndarray) -> tuple[float, np.ndarray]:
        """(X0, w [N]): satılabilir stok ve hücre payları (modül docstring'i)."""
        b = self._hazir(g, o)
        if not np.array_equal(hucreler, b.hucre):
            raise ValueError("hucreler bu option'ın `taban` hücreleri olmalı")
        D = np.asarray(d, dtype=float).sum(axis=0)
        raf = np.where(b.online, 0.0, np.maximum(np.asarray(g.magaza_stok[b.hucre], float), 0.0)
                       + np.maximum(np.asarray(g.yolda[b.hucre], float), 0.0))
        depo = np.maximum(np.asarray(g.depo[b.skular], dtype=float), 0.0)
        ns = len(b.skular)
        tD = np.bincount(b.sku_yerel, D, minlength=ns)
        tR = np.bincount(b.sku_yerel, raf, minlength=ns)
        sayi = np.bincount(b.sku_yerel, minlength=ns)
        j = b.sku_yerel
        with np.errstate(divide="ignore", invalid="ignore"):
            pay = np.where(tD[j] > 0, D / tD[j], np.where(tR[j] > 0, raf / tR[j], 1.0 / sayi[j]))
        dagit = raf + depo[j] * pay
        X0 = float(raf.sum() + depo.sum())
        toplam = dagit.sum()
        w = dagit / toplam if toplam > 0 else np.full(len(b.hucre), 1.0 / len(b.hucre))
        return X0, w

    def carpan(self, g, o: int, ufuk, eps,
               agirlik: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """(carpan [T, K], etkin [T, K]): hafta × basamak fiyat çarpanı ve etkin indirim oranı.

        `eps` tek sayı (option'ın ε̂'sı) ya da [N] hücre başına ε (ör. kahinin gerçek hücre esnekliği,
        `taban` hücre sırasıyla); hücre-gün çarpanı `(1 − max(r, kampanya))^(−ε_hücre)`, hafta başına
        ağırlıklı ortalaması alınır (ε'ler önce ortalanmaz: çarpan ε'de dışbükey). `agirlik` [U, N]
        verilirse hücre-gün ağırlığı odur (ör. kahinin gerçek taban talebi); verilmezse bu tahmincinin
        `taban` günlük talebi."""
        b = self._hazir(g, o)
        ufuk = np.asarray(ufuk, dtype=np.int64)
        if len(ufuk) == 0:
            return np.zeros((0, len(KADEMELER))), np.zeros((0, len(KADEMELER)))
        if agirlik is None:
            agirlik = self._gunluk_talep(g, o, ufuk)
        else:
            agirlik = np.asarray(agirlik, dtype=float)
            if agirlik.shape != (len(ufuk), len(b.hucre)):
                raise ValueError(f"agirlik [U, N] = {(len(ufuk), len(b.hucre))} olmalı: {agirlik.shape}")
        eps = np.asarray(eps, dtype=float)
        if eps.ndim == 0:
            eps_degerleri, eps_ters = eps[None], np.zeros(len(b.hucre), dtype=np.int64)
        elif eps.shape == (len(b.hucre),):
            eps_degerleri, eps_ters = np.unique(eps, return_inverse=True)
        else:
            raise ValueError(f"eps tek sayı ya da [N] = {len(b.hucre)} olmalı: {eps.shape}")
        bas = np.arange(0, len(ufuk), 7)
        hafta = np.repeat(np.arange(len(bas)), np.diff(np.append(bas, len(ufuk))))
        bos = np.add.reduceat(agirlik.sum(1), bas) <= 0
        agirlik = np.where(bos[hafta][:, None], 1.0, agirlik)
        # Kampanya oranı ve ε az sayıda farklı değer alır: ağırlık (hafta, kampanya değeri, ε değeri)
        # başına toplanır, çarpan (değer, ε) × basamak tablosundan ([V·E, K]); [U, N, K] küpü kurulmaz.
        kamp_gm = _kampanya_uygula(b.kurallar, ufuk, self._M)               # [U, M]
        degerler, ters = np.unique(kamp_gm, return_inverse=True)
        V, E, T = len(degerler), len(eps_degerleri), len(bas)
        grup = ters.reshape(kamp_gm.shape)[:, self._hm[b.hucre]] * E + eps_ters[None, :]   # [U, N]
        A = np.bincount((hafta[:, None] * (V * E) + grup).ravel(), weights=agirlik.ravel(),
                        minlength=T * V * E).reshape(T, V * E)
        K = np.asarray(KADEMELER, dtype=float)
        r = np.maximum(K[None, :], degerler[:, None])                       # [V, K]
        m = np.stack([fiyat_carpani(r, e) for e in eps_degerleri], axis=1).reshape(V * E, K.size)
        etkin = np.repeat(np.where(r > 0, r, self.ogrenilen.islem), E, axis=0)   # [V·E, K]
        pay = A @ m                                                        # [T, K]
        return pay / A.sum(1)[:, None], (A @ (m * etkin)) / pay

    def iade_payi(self, g, o: int, hucreler: np.ndarray, d: np.ndarray) -> float:
        """Ufuk talebi ağırlıklı iade payı (fiziksel / online); talep yoksa hücre sayısıyla."""
        b = self._hazir(g, o)
        D = np.asarray(d, dtype=float).sum(axis=0)
        a = D if D.sum() > 0 else np.ones(len(b.hucre))
        oran = np.where(b.online, self.ogrenilen.iade.get("online", 0.0),
                        self.ogrenilen.iade.get("magaza", 0.0))
        return float((a * oran).sum() / a.sum())


def _haftalik(x: np.ndarray) -> np.ndarray:
    """[U, ...] gün -> [T, ...] hafta (7 günlük ardışık bloklar)."""
    if len(x) == 0:
        return x[:0]
    return np.add.reduceat(x, np.arange(0, len(x), 7), axis=0)
