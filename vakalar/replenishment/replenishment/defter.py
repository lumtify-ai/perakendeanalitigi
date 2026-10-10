"""Gölge defter: depo stoğunun kapalı koli ve açık adet bölünmesi (spec §3.4).

Motor depoyu SKU başına adet olarak tutar; koli kısıtı politikanın içindedir.
Defter option başına kapalı koli sayısını (`kapali` [O]) ve SKU başına açık
adedi (`acik` [S]) izler. Değişmez, her `uzlastir` sonunda denetlenir:

    kapali_adet() + acik == Gorunum.depo   (SKU başına; hiçbiri negatif değil)

**Koli.** Option'ın beden setinin standart paketi (dünyanın açık `paketler`
tablosu; standart 7 adet [1, 2, 2, 1, 1], aksesuar 6): `koli_icerigi`.
Mağazaya gönderimde koli açılmaz (kullanıcı kararı); defterin kendisi yalnız
politika dışı çıkışları karşılamak için koli "açar" (online toplama, outlet,
açıklanamayan eksik), çünkü o mal depodan zaten çıkmıştır.

**Bölme (`bol`).** Gelen parti: option başına kurulabilen tam koli
`k = min_b ⌊adet_b / içerik_b⌋`; kapalı `⌊k × (1 − açık payı)⌋` koli, kalan
adetler açık. Açık payı line'dan (`sabitler.ACIK_PAYI`).

**Uzlaştırma (Ruling R8).** Pazartesi, son uzlaştırmadan (ya da `baslat`'tan)
bu yana akışlar brüt izlenir; sıra:

  1. Kendi sevki: kolun `dagit`'i `dus_acik` / `dus_koli` ile zaten düşmüştür
     (önceki görünümün deposu − defter toplamı; yalnız kayda girer).
  2. Teslim: önceki görünümün `acik_siparisler`'inde olup bugünkünde olmayan
     her sipariş (brüt `adetler`) ayrı parti olarak `bol`'la girer.
  3. Fark = bugünkü depo − (defter + teslim − online satış); online satış
     `satis_gecmisi`'nin ONL hücrelerinden (önceki pazartesi … dün).
     Farkın artısı (iade, kapanış dönüşü, stok devri…) açığa girer; sonra
     online satış önce açıktan, yetmezse kapalıdan düşülür.
  4. Farkın eksisi önce ilk dağıtım havuzundan kapalı koliyle: kayıt
     politikanın kararıdır, motorun gönderdiği değil (motor aday maskesi ve
     depoyla kırpar, sevki erteleyebilir), bu yüzden **üst sınırdır**.
     Option başına eşlenen paket = min(havuz, `min_b ⌊eksik_b / içerik_b⌋`)
     (her bedeni eksikte görünen paket); kapalı koli yettiğince koliden,
     kalanı açıktan. Eşlenmeyen kayıt sonraki pazartesilere taşınır, option'ın son
     olası sevk günü `max(lansman_gun, karar günü)` geçince düşer.
  5. Kalan eksik outlet akışı kaydının depodan çıkan satırlarına kadar (üst
     sınır; aynı gün uygulanır, taşınmaz) önce açıktan sonra kapalıdan.
  6. Kalan eksik açıklanamayan kalem: önce açıktan, sonra kapalıdan.

Her kalem `Uzlastirma` kaydına girer (`kayit_tablosu`).

Bu modül `perakende_veri`'yi, `replenishment.motor`'u ve hakemi içe aktarmaz
(`tests/test_sizinti.py`); kaydedici kayıtları düz liste olarak verilir
(`Kaydedici.kayit`, Ruling R3: `{"gun", "args", "cikti"}`) ve dünyanın yalnız
açık alanları okunur (`paketler`, `optionlar`, `urunler`, `magazalar`,
`sku_option`, `hucre_online`, `hucre_sku`).
"""

from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np

_BUYUK = np.iinfo(np.int64).max
_EPS = 1e-9   # ⌊k × (1 − p)⌋'de kayan nokta payı (ör. 5 × 0,6 = 2,999…)


# ---------------------------------------------------------------------------
# Koli tanımı
# ---------------------------------------------------------------------------


def beden_skulari(w) -> np.ndarray:
    """[O, B_max] option'ın SKU indisleri beden sırasıyla (`urunler.beden_sira`);
    eksik yer −1. `koli_icerigi`'nin sütunları bu sıradadır."""
    so = np.asarray(w.sku_option, dtype=np.int64)
    bs = w.urunler["beden_sira"].to_numpy()
    O = len(w.optionlar)
    sira = np.lexsort((bs, so))
    adet = np.bincount(so, minlength=O)
    bas = np.concatenate([[0], np.cumsum(adet)[:-1]])
    yer = np.arange(len(so)) - bas[so[sira]]
    sonuc = np.full((O, max(int(adet.max()), 1) if O else 1), -1, dtype=np.int64)
    sonuc[so[sira], yer] = sira
    return sonuc


def koli_icerigi(w) -> tuple[np.ndarray, np.ndarray]:
    """(`icerik` [O, B_max], `koli_adedi` [O]).

    `icerik[o, j]`: option'ın koli içindeki j. bedeninin adedi; sütun j'nin
    SKU'su `beden_skulari(w)[o, j]` (−1 olan yerde 0). Koli, option'ın beden
    setinin standart paketidir: `paketler`'de o set için ilk görülen
    `paket_id` (üretecin `paket_tablosu` kuralı). `koli_adedi` paketin
    toplam adedi (standart 7, aksesuar 6)."""
    pk = w.paketler
    standart: dict[str, str] = {}
    for bs, pid in zip(pk["beden_seti"], pk["paket_id"]):
        standart.setdefault(bs, pid)
    adet = {(p, int(b)): int(a) for p, b, a in zip(pk["paket_id"], pk["beden_sira"], pk["adet"])}
    toplam = pk.groupby("paket_id", sort=False)["adet"].sum().to_dict()

    skular = beden_skulari(w)
    beden_sira = w.urunler["beden_sira"].to_numpy()
    setler = w.optionlar["beden_seti"].to_numpy()
    icerik = np.zeros(skular.shape, dtype=np.int64)
    koli_adedi = np.zeros(len(setler), dtype=np.int64)
    for o, bs in enumerate(setler):
        if bs not in standart:
            raise KeyError(f"option {o}: beden seti {bs!r} için paket yok")
        p = standart[bs]
        koli_adedi[o] = int(toplam[p])
        for j, s in enumerate(skular[o]):
            if s >= 0:
                icerik[o, j] = adet.get((p, int(beden_sira[s])), 0)
    return icerik, koli_adedi


class _KoliTanimi:
    """Dünyadan bir kez kurulan koli indisleri (defter ve `bol` için)."""

    def __init__(self, w, acik_payi: dict):
        self.skular = beden_skulari(w)
        self.icerik, self.koli_adedi = koli_icerigi(w)
        self.sku_option = np.asarray(w.sku_option, dtype=np.int64)
        self.S, self.O = len(self.sku_option), len(self.koli_adedi)
        self.icerik_sku = np.zeros(self.S, dtype=np.int64)
        var = self.skular >= 0
        self.icerik_sku[self.skular[var]] = self.icerik[var]
        line = w.optionlar["line"].to_numpy()
        eksik = sorted(set(line) - set(acik_payi))
        if eksik:
            raise KeyError(f"açık payı tanımsız line: {eksik}")
        self.pay = np.array([float(acik_payi[x]) for x in line], dtype=float)

    def tam_koli(self, adet_sku: np.ndarray) -> np.ndarray:
        """[O] kurulabilen tam koli: min_b ⌊adet_b / içerik_b⌋ (içerik > 0 bedenler)."""
        a = adet_sku[np.maximum(self.skular, 0)]
        oran = np.where(self.icerik > 0, a // np.maximum(self.icerik, 1), _BUYUK)
        k = oran.min(axis=1)
        return np.where(k == _BUYUK, 0, k)

    def bol(self, adet_sku) -> tuple[np.ndarray, np.ndarray]:
        a = _sku_dizisi(adet_sku, self.S, "adet")
        k = self.tam_koli(a)
        kapali = np.floor(k * (1.0 - self.pay) + _EPS).astype(np.int64)
        return kapali, a - kapali[self.sku_option] * self.icerik_sku


def _sku_dizisi(x, n: int, ad: str) -> np.ndarray:
    a = np.asarray(x)
    if a.shape != (n,):
        raise ValueError(f"{ad}: boy {a.shape}, beklenen ({n},)")
    if a.dtype.kind == "f" and not np.array_equal(a, np.round(a)):
        raise ValueError(f"{ad}: tam sayı olmalı")
    a = a.astype(np.int64)
    if (a < 0).any():
        raise ValueError(f"{ad}: negatif öğe")
    return a


def bol(adet_sku: np.ndarray, w, acik_payi: dict) -> tuple[np.ndarray, np.ndarray]:
    """Gelen partiyi böler: (`koli` [O] kapalı koli, `acik` [S] açık adet).

    Option başına tam koli `k = min_b ⌊adet_b / içerik_b⌋`; kapalı
    `⌊k × (1 − açık payı[line])⌋` koli; kalan adetler (koli kurulamayan
    bedenlerin fazlası dahil) açık. `kapali[sku_option] × içerik + acik = adet`."""
    return _KoliTanimi(w, acik_payi).bol(adet_sku)


# ---------------------------------------------------------------------------
# Defter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Uzlastirma:
    """Bir pazartesinin uzlaştırma kalemleri (adet; `_koli` olanlar koli).

    gun, onceki_gun              bu ve önceki uzlaştırma (ya da başlangıç) günü
    baslangic                    `baslat` kaydı (akış kalemleri 0)
    kendi_sevk_adet              kolun önceki pazartesi `dagit`'te düştüğü
    teslim_sayisi, teslim_adet   teslim edilen sipariş sayısı ve brüt adedi
    teslim_kapali_koli,          teslimin `bol`'la kapalıya ve açığa giden kısmı
      teslim_acik_adet
    online_adet                  ONL hücrelerinin brüt satışı (önce açıktan)
    ilk_dagitim_kayit_koli       aralıkta kaydedilen ilk dağıtım paketleri (karar)
    ilk_dagitim_kapali_koli,     eşlenen paketlerin kapalı koliden düşülen kısmı
      ilk_dagitim_kapali_adet
    ilk_dagitim_acik_adet        eşlenen ama kapalı koli kalmadığı için açıktan
    ilk_dagitim_dusen_koli       son sevk günü geçmiş, eşlenmemiş kayıt (motor kırptı)
    ilk_dagitim_bekleyen_koli    sonraki pazartesiye taşınan kayıt
    outlet_kayit_adet            outlet kaydının depodan çıkan satırları (üst sınır)
    outlet_adet                  eşlenen outlet çıkışı (önce açıktan)
    aciklanamayan_arti_adet      açığa giren artı fark (iade, kapanış, devir…)
    aciklanamayan_eksi_adet      kalan eksi fark (kalite reddi…; önce açıktan)
    acilan_koli                  politika dışı çıkışlar için defterde açılan koli
    kapali_koli, kapali_adet,    uzlaştırmadan sonraki durum
      acik_adet
    """

    gun: int
    onceki_gun: int
    baslangic: bool = False
    kendi_sevk_adet: int = 0
    teslim_sayisi: int = 0
    teslim_adet: int = 0
    teslim_kapali_koli: int = 0
    teslim_acik_adet: int = 0
    online_adet: int = 0
    ilk_dagitim_kayit_koli: int = 0
    ilk_dagitim_kapali_koli: int = 0
    ilk_dagitim_kapali_adet: int = 0
    ilk_dagitim_acik_adet: int = 0
    ilk_dagitim_dusen_koli: int = 0
    ilk_dagitim_bekleyen_koli: int = 0
    outlet_kayit_adet: int = 0
    outlet_adet: int = 0
    aciklanamayan_arti_adet: int = 0
    aciklanamayan_eksi_adet: int = 0
    acilan_koli: int = 0
    kapali_koli: int = 0
    kapali_adet: int = 0
    acik_adet: int = 0


def _siparis_anahtari(s: dict) -> tuple:
    """Açık siparişin kimliği (görünümde sipariş numarası yok): bütün alanlar."""
    return (str(s["tip"]), int(s["option"]), int(s["siparis_gun"]), int(s["planlanan_gun"]),
            int(s["tedarikci"]), tuple(np.asarray(s["skular"]).tolist()),
            tuple(np.asarray(s["adetler"]).tolist()))


class GolgeDefter:
    """Kapalı koli [O] ve açık adet [S] defteri (bkz. modül belgesi).

    Kullanım (kol içinde): pencerenin ilk pazartesisi `baslat(g)`; sonraki her
    pazartesi `uzlastir(g, ilk_dagitim_kaydi, outlet_kaydi)`, ardından
    `dagit` gönderdiğini `dus_acik` / `dus_koli` ile düşer. Kayıtlar
    kaydedicilerin canlı `kayit` listeleridir (her çağrıda aynı liste; defter
    nereye kadar okuduğunu tutar).
    """

    def __init__(self, w, acik_payi: dict):
        self._k = _KoliTanimi(w, acik_payi)
        S, O = self._k.S, self._k.O
        self.kapali = np.zeros(O, dtype=np.int64)
        self.acik = np.zeros(S, dtype=np.int64)
        onl = np.asarray(w.hucre_online, dtype=bool)
        self._onl_hucre = np.flatnonzero(onl)
        self._onl_sku = np.asarray(w.hucre_sku, dtype=np.int64)[self._onl_hucre]
        self._online_magaza = np.flatnonzero((w.magazalar["tip"] == "Online").to_numpy())
        self._lansman = w.optionlar["lansman_gun"].to_numpy().astype(np.int64)
        # İlk dağıtım havuzu: option başına eşlenmemiş paket ve son olası sevk günü
        self._havuz = np.zeros(O, dtype=np.int64)
        self._havuz_bitis = np.full(O, -1, dtype=np.int64)
        self._ilk_okunan = 0
        self._outlet_okunan = 0
        self._gun: int | None = None
        self._depo: np.ndarray | None = None
        self._siparisler: list[tuple] = []
        self._kayitlar: list[Uzlastirma] = []

    # --- Durum -----------------------------------------------------------
    @property
    def icerik_sku(self) -> np.ndarray:
        """[S] SKU'nun option kolisindeki adedi."""
        return self._k.icerik_sku

    def kapali_adet(self) -> np.ndarray:
        """[S] kapalı kolilerdeki adet."""
        return self.kapali[self._k.sku_option] * self._k.icerik_sku

    def kayit_tablosu(self) -> list[dict]:
        """Başlangıç ve her pazartesi için `Uzlastirma` kalemleri (sözlük)."""
        return [asdict(u) for u in self._kayitlar]

    # --- Kolun kendi sevki -----------------------------------------------
    def dus_acik(self, sku_adet) -> None:
        a = _sku_dizisi(sku_adet, self._k.S, "sku_adet")
        if (a > self.acik).any():
            raise ValueError("açık stoktan fazla düşüm")
        self.acik -= a

    def dus_koli(self, option_koli) -> None:
        a = _sku_dizisi(option_koli, self._k.O, "option_koli")
        if (a > self.kapali).any():
            raise ValueError("kapalı koliden fazla düşüm")
        self.kapali -= a

    # --- Başlangıç ve uzlaştırma -----------------------------------------
    def baslat(self, g) -> Uzlastirma:
        """Oyunun ilk pazartesisi: depo stoğu `bol` ile bölünür."""
        depo = np.array(g.depo, dtype=np.int64)            # salt okunur görünüm: kopya
        self.kapali, self.acik = self._k.bol(depo)
        self._depo, self._gun = depo, int(g.gun)
        self._siparisler = [_siparis_anahtari(s) for s in g.acik_siparisler]
        self._degismez(depo)
        return self._kaydet(Uzlastirma(gun=self._gun, onceki_gun=self._gun, baslangic=True))

    def uzlastir(self, g, ilk_dagitim_kaydi: list, outlet_kaydi: list) -> Uzlastirma:
        """Son uzlaştırmadan bu yana akışları işler (bkz. modül belgesi, adım 1–6)."""
        if self._gun is None:
            raise RuntimeError("önce baslat(g)")
        d, onceki = int(g.gun), self._gun
        if d <= onceki:
            raise ValueError(f"uzlaştırma günü {d} son günden ({onceki}) sonra olmalı")
        k = self._k
        so, ic = k.sku_option, k.icerik_sku
        depo = np.array(g.depo, dtype=np.int64)            # salt okunur görünüm: kopya

        # 1) Kendi sevki (dagit'te düşüldü)
        defter = self.kapali_adet() + self.acik
        kendi = int((self._depo - defter).sum())

        # 2) Teslim: düşen siparişler, parti parti
        teslimler = self._dusen_siparisler(g.acik_siparisler)
        gelen = np.zeros(k.S, dtype=np.int64)
        teslim_koli = teslim_acik = 0
        for sk, ad in teslimler:
            v = np.zeros(k.S, dtype=np.int64)
            np.add.at(v, sk, ad)
            koli, acik = k.bol(v)
            self.kapali += koli
            self.acik += acik
            gelen += v
            teslim_koli += int(koli.sum())
            teslim_acik += int(acik.sum())

        # 3) Fark; artısı açığa, sonra online satış
        online = self._online_satis(g, onceki, d)
        fark = depo - (defter + gelen - online)
        arti = np.maximum(fark, 0)
        self.acik += arti
        acilan = self._cikar(online)
        eksik = np.maximum(-fark, 0)

        # 4) İlk dağıtım havuzu (üst sınır) → kapalı koliden
        kayit_koli = self._ilk_kayitlari_al(ilk_dagitim_kaydi, onceki, d)
        oran = np.where(ic > 0, eksik // np.maximum(ic, 1), _BUYUK)
        olabilir = np.full(k.O, _BUYUK, dtype=np.int64)
        np.minimum.at(olabilir, so, oran)
        olabilir = np.where(olabilir == _BUYUK, 0, olabilir)
        eslenen = np.minimum(self._havuz, olabilir)
        kapalidan = np.minimum(eslenen, self.kapali)
        self.kapali -= kapalidan
        acikdan = (eslenen - kapalidan)[so] * ic
        eksik -= kapalidan[so] * ic
        acilan += self._cikar(acikdan)
        eksik -= acikdan
        self._havuz -= eslenen
        bitti = self._havuz_bitis <= d
        dusen = int(self._havuz[bitti].sum())
        self._havuz[bitti] = 0
        self._havuz_bitis[self._havuz == 0] = -1

        # 5) Outlet akışı (üst sınır, aynı gün) → önce açık
        ust = self._outlet_ust_siniri(outlet_kaydi, onceki, d)
        outlet = np.minimum(ust, eksik)
        acilan += self._cikar(outlet)
        eksik -= outlet

        # 6) Açıklanamayan eksik → önce açık
        acilan += self._cikar(eksik)

        self._depo, self._gun = depo, d
        self._siparisler = [_siparis_anahtari(s) for s in g.acik_siparisler]
        self._degismez(depo)
        return self._kaydet(Uzlastirma(
            gun=d, onceki_gun=onceki, kendi_sevk_adet=kendi,
            teslim_sayisi=len(teslimler), teslim_adet=int(gelen.sum()),
            teslim_kapali_koli=teslim_koli, teslim_acik_adet=teslim_acik,
            online_adet=int(online.sum()),
            ilk_dagitim_kayit_koli=kayit_koli, ilk_dagitim_kapali_koli=int(kapalidan.sum()),
            ilk_dagitim_kapali_adet=int((kapalidan * k.icerik.sum(axis=1)).sum()),
            ilk_dagitim_acik_adet=int(acikdan.sum()), ilk_dagitim_dusen_koli=dusen,
            ilk_dagitim_bekleyen_koli=int(self._havuz.sum()),
            outlet_kayit_adet=int(ust.sum()), outlet_adet=int(outlet.sum()),
            aciklanamayan_arti_adet=int(arti.sum()), aciklanamayan_eksi_adet=int(eksik.sum()),
            acilan_koli=acilan,
        ))

    # --- İç adımlar --------------------------------------------------------
    def _kaydet(self, u: Uzlastirma) -> Uzlastirma:
        u = Uzlastirma(**{**asdict(u), "kapali_koli": int(self.kapali.sum()),
                          "kapali_adet": int(self.kapali_adet().sum()),
                          "acik_adet": int(self.acik.sum())})
        self._kayitlar.append(u)
        return u

    def _degismez(self, depo: np.ndarray) -> None:
        if (self.kapali < 0).any() or (self.acik < 0).any():
            raise AssertionError("gölge defter negatif")
        fark = np.flatnonzero(self.kapali_adet() + self.acik != depo)
        if fark.size:
            raise AssertionError(f"gölge defter depoyla tutmuyor: {fark.size} SKU (ilk {fark[:5].tolist()})")

    def _cikar(self, adet: np.ndarray) -> int:
        """Politika dışı çıkış: önce açıktan; yetmeyen SKU'da option'ın kolisi
        gerektiği kadar açılır (içeriği açığa geçer). Açılan koli sayısını döndürür."""
        k = self._k
        ic = k.icerik_sku
        kisa = np.maximum(adet - self.acik, 0)
        if (kisa[ic == 0] > 0).any():
            raise AssertionError("kolide olmayan SKU'da açık stoktan fazla çıkış")
        gerek = -(-kisa // np.maximum(ic, 1))
        koli = np.zeros(k.O, dtype=np.int64)
        np.maximum.at(koli, k.sku_option, gerek)
        if (koli > self.kapali).any():
            raise AssertionError("çıkış defterdeki stoğu aşıyor")
        self.kapali -= koli
        self.acik += koli[k.sku_option] * ic - adet
        return int(koli.sum())

    def _dusen_siparisler(self, acik_siparisler) -> list[tuple[np.ndarray, np.ndarray]]:
        """Önceki görünümde olup bugünkünde olmayan siparişler: (skular, adetler).
        Aralıkta verilip aralıkta teslim edilen sipariş görülemez; v4'te
        siparişler yalnız pazartesi verilir ve en kısa teslim 26 gündür."""
        simdi = Counter(_siparis_anahtari(s) for s in acik_siparisler)
        dusen = []
        for a in self._siparisler:
            if simdi[a] > 0:
                simdi[a] -= 1
            else:
                dusen.append((np.asarray(a[5], dtype=np.int64), np.asarray(a[6], dtype=np.int64)))
        return dusen

    def _online_satis(self, g, onceki: int, d: int) -> np.ndarray:
        """[S] ONL hücrelerinin [onceki, d) günlerindeki brüt satışı."""
        satis = np.asarray(g.satis_gecmisi[onceki:d][:, self._onl_hucre]).sum(axis=0, dtype=np.int64)
        return np.bincount(self._onl_sku, satis, minlength=self._k.S).astype(np.int64)

    def _ilk_kayitlari_al(self, kayit: list, onceki: int, d: int) -> int:
        """Yeni ilk dağıtım kayıtlarını (karar günü ≤ d) havuza ekler; aralıkta
        (onceki, d] kaydedilen paket sayısını döndürür. Son olası sevk günü
        onceki'den önce olan (başlangıçtan önceki, bitmiş) kayıt eklenmez."""
        yeni = 0
        while self._ilk_okunan < len(kayit) and int(kayit[self._ilk_okunan]["gun"]) <= d:
            e = kayit[self._ilk_okunan]
            self._ilk_okunan += 1
            gun, o = int(e["gun"]), int(e["args"][0])
            paket = int(np.maximum(np.asarray(e["cikti"], dtype=np.int64), 0).sum())
            bitis = max(int(self._lansman[o]), gun)
            if gun > onceki:
                yeni += paket
            if bitis <= onceki or paket == 0:
                continue
            self._havuz[o] += paket
            self._havuz_bitis[o] = max(self._havuz_bitis[o], bitis)
        return yeni

    def _outlet_ust_siniri(self, kayit: list, onceki: int, d: int) -> np.ndarray:
        """[S] (onceki, d] outlet kayıtlarının depodan mağazaya satırları (motor
        kaynağın stoğuyla kırpar; hedefi depo ya da ONL olan satırı atar)."""
        ust = np.zeros(self._k.S, dtype=np.int64)
        while self._outlet_okunan < len(kayit) and int(kayit[self._outlet_okunan]["gun"]) <= d:
            e = kayit[self._outlet_okunan]
            self._outlet_okunan += 1
            if int(e["gun"]) <= onceki:
                continue
            tr = e["cikti"]
            kaynak, hedef = np.asarray(tr.kaynak).ravel(), np.asarray(tr.hedef).ravel()
            sku, adet = np.asarray(tr.sku).ravel(), np.asarray(tr.adet).ravel()
            m = (kaynak < 0) & (hedef >= 0) & ~np.isin(hedef, self._online_magaza) & (adet > 0)
            np.add.at(ust, sku[m].astype(np.int64), adet[m].astype(np.int64))
        return ust
