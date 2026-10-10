"""`replenishment.politika`: v4 kolları (motorun `replenishment(Gorunum) -> [C]`
çağrılabilirleri) ve koşu sonrası denetim.

KÜÇÜK dünyada kısa koşular: oyun penceresi test için öne çekilir
(`Ayar.pencere`, 2023 sonbaharı; dokuz pazartesi) ve koşu pencereden bir hafta
sonra biter (~3 sn). Her kol bir kez koşar (modül önbelleği) ve bir denetçiyle
sarılır: pencere içinde motorun kesmeyeceğini (SKU başına istek ≤ depo, maske
dışı ve online hücre 0), pencere dışında Lumoda'yla aynı çıktıyı verdiğini koşu
sırasında sınar. Tahminci testte, pencerenin ilk pazartesisinin `Gorunum`
geçmişinden küçük bir modelle eğitilir (kimliği içerikten).

Testler motoru ve `perakende_veri`'yi içe aktarabilir; `politika` aktaramaz
(`test_kahin_alani_okunmaz`, `tests/test_sizinti.py`).
"""

import copy
import dataclasses
from datetime import date
from math import inf
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from perakende_analitik.carpanlar import Carpanlar
from test_sizinti import gizli_erisimler, ihlaller

from replenishment import kaynak, motor, politika, tahmin
from replenishment.dagitim import KISITSIZ, KOLI_KURALLARI, KoliKurali, motor_maskesi
from replenishment.ihtiyac import GuvenlikStoku
from replenishment.politika import KOLLAR, Ayar

PENCERE = (date(2023, 9, 4), date(2023, 10, 30))     # dokuz pazartesi
SONRA = date(2023, 11, 6)                            # pencereden sonraki pazartesi (son koşu günü)
TAHMIN_PARAMETRELERI = {**tahmin.PARAMETRELER, "n_estimators": 20}


def _gun(w, tarih) -> int:
    t0 = pd.Timestamp(w.takvim["tarih"].iloc[0])
    return int((pd.Timestamp(tarih) - t0).days)


@pytest.fixture(scope="module")
def w():
    return motor.dunya("kucuk")


class _Bitti(Exception):
    pass


@pytest.fixture(scope="module")
def tahminci(w):
    """Pencerenin ilk pazartesisindeki `Gorunum` geçmişiyle eğitilmiş küçük model."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.politika import Politikalar

    d0 = _gun(w, PENCERE[0])
    yakalanan = {}
    temel = motor.lumoda("replenishment")

    def yakala(g):
        if g.gun == d0:
            yakalanan["g"] = g
            raise _Bitti
        return temel(g)

    with pytest.raises(_Bitti):
        simule_et(w, Politikalar(replenishment=yakala), kayit_talep=False)
    g = yakalanan["g"]
    h = kaynak.harita_kur(w)
    X, y = tahmin.egitim_seti(g.satis_gecmisi, g.stoklu_gecmisi, h, tahmin.gorunum_oznitelik(w, h), d0)
    return tahmin.Tahminci.egit(X, y, TAHMIN_PARAMETRELERI).sabitle()


class _Denetci:
    """Kolu sarar; motorun gördüğü yöntemleri (`baglan`, `gecmis_gerekir`,
    `parametreler`, `kayit_tablosu`) geçirir. Pencere içinde: SKU başına istek ≤
    depo (motorun orantılı kesimi devreye girmez), motor maskesi dışı ve online
    hücre 0. Pencere dışında: çıktı Lumoda'nınkiyle birebir."""

    def __init__(self, kol):
        self.kol = self.temel = kol
        self.lumoda = motor.lumoda("replenishment")
        self.pencere_gunleri, self.disarida, self.ihlaller = [], 0, []

    @property
    def gecmis_gerekir(self):
        return self.kol.gecmis_gerekir

    def baglan(self, k):
        self.kol.baglan(k)

    def parametreler(self):
        return self.kol.parametreler()

    def kayit_tablosu(self):
        return self.kol.kayit_tablosu()

    def __call__(self, g):
        depo = np.array(g.depo)
        r = np.asarray(self.kol(g))
        w = g.dunya
        if PENCERE[0] <= pd.Timestamp(g.tarih).date() <= PENCERE[1]:
            self.pencere_gunleri.append(int(g.gun))
            hs = np.asarray(w.hucre_sku)
            if (np.bincount(hs, r, minlength=len(depo)) > depo).any():
                self.ihlaller.append((g.gun, "depo"))
            if r[~motor_maskesi(g)].any():
                self.ihlaller.append((g.gun, "maske"))
            if r[np.asarray(w.hucre_online)].any():
                self.ihlaller.append((g.gun, "online"))
            if (r < 0).any():
                self.ihlaller.append((g.gun, "negatif"))
        else:
            self.disarida += 1
            if not np.array_equal(r, np.asarray(self.lumoda(g))):
                self.ihlaller.append((g.gun, "pencere dışı Lumoda değil"))
        return r


KOSULAR = {
    "lumoda": ("lumoda", {}),
    "kural": ("kural", {}),
    "kural_basit": ("kural_basit", {}),
    "tahmin": ("tahmin", {}),
    "tahmin_taban": ("tahmin_taban", {}),
    "kural_siki": ("kural", {"tavan": 40.0, "koli": "A"}),     # açık tavanı bağlar, koli gider
    "kural_kisitsiz": ("kural", {"kisitsiz": True}),
}


def _kol(ad, w, tahminci):
    tur, ayar = KOSULAR[ad]
    a = Ayar(pencere=PENCERE, **ayar)
    ek = {"kural_basit": {"carpanlar": Carpanlar()}, "tahmin": {"tahminci": tahminci},
          "tahmin_taban": {"tahminci": tahminci}}.get(tur, {})
    return KOLLAR[tur](motor.lumoda("replenishment"), a, **ek)


@pytest.fixture(scope="module")
def kosular(w, tahminci):
    onbellek = {}
    n = _gun(w, SONRA) + 1

    def al(ad):
        if ad not in onbellek:
            if ad == "referans":
                onbellek[ad] = (motor.kos(ad="referans", parametreler={}, onbellek=None, olcek="kucuk",
                                          gun_sayisi=n), None)
            else:
                den = _Denetci(_kol(ad, w, tahminci))
                k = motor.kos(den, ad=f"t_{ad}", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
                onbellek[ad] = (k, den)
        return onbellek[ad]

    return al


# ---------------------------------------------------------------- koşu testleri


@pytest.mark.parametrize("ad", ["kural", "kural_basit", "tahmin_taban"])
def test_oyun_oncesi_lumoda_ile_ayni(kosular, ad):
    """Pencereden önce kol Lumoda'dır: aynı tohumlarla Lumoda koşusunun tabloları
    pencere başına dek birebir (koşu sırasında da: pencere dışı çıktı = Lumoda)."""
    k, den = kosular(ad)
    ref, _ = kosular("referans")
    assert den.disarida > 0 and not den.ihlaller
    bas = pd.Timestamp(PENCERE[0])
    for t in ("sevkiyat", "satis", "stok", "depo_stok"):
        a = k.tablolar[t]
        b = ref.tablolar[t]
        pd.testing.assert_frame_equal(a[a["tarih"] < bas].reset_index(drop=True),
                                      b[b["tarih"] < bas].reset_index(drop=True))
    # pencere içinde kol gerçekten başka karar verdi
    sv, rv = k.tablolar["sevkiyat"], ref.tablolar["sevkiyat"]
    sec = lambda d: d[(d["tip"] == "replenishment") & (d["tarih"] >= bas)]["adet"].sum()   # noqa: E731
    assert sec(sv) != sec(rv)


@pytest.mark.parametrize("ad", list(KOSULAR))
def test_istekler_sevkiyatla_birebir(kosular, ad):
    """Politikanın kaydettiği istek = koşunun `replenishment` sevkiyatı (pazartesi,
    mağaza, ürün); dokuz pencere pazartesisi kayıtta."""
    k, den = kosular(ad)
    fark = politika.sevkiyatla_karsilastir(k)
    assert fark.empty, fark.head()
    ist = politika.istek_tablosu(k)
    assert len(ist) > 0 and (ist["adet"] > 0).all()
    hafta = politika.hafta_tablosu(k)
    assert len(hafta) == 9 == len(den.pencere_gunleri)
    assert hafta["gonderilen_adet"].sum() == ist["adet"].sum()


@pytest.mark.parametrize("ad", list(KOSULAR))
def test_kisitli_kolda_motor_kesmez(kosular, ad):
    """Pencere içinde her pazartesi SKU başına istek depo stoğunu aşmaz, motor
    maskesi dışına istek yok: motorun orantılı kesimi ve sıfırlaması devreye girmez."""
    _, den = kosular(ad)
    assert len(den.pencere_gunleri) == 9
    assert not den.ihlaller, den.ihlaller[:5]


def test_online_hucreye_istek_yok(kosular, w):
    for ad in ("kural", "tahmin", "lumoda"):
        k, _ = kosular(ad)
        ist = politika.istek_tablosu(k)
        online = set(w.magazalar.loc[w.magazalar["tip"] == "Online", "magaza_id"].astype(str))
        assert not set(ist["magaza_id"]) & online
        assert not np.asarray(w.hucre_online)[ist["hucre"].to_numpy()].any()


def test_tavan_ve_koli_kayitta(kosular):
    """Sıkı tavanda açık toplama tavanı bağlar (doluluk 1'e yakın) ve koli gider;
    tavansız varsayılanda doluluk 0; kısıtsızda koli yok."""
    siki = politika.hafta_tablosu(kosular("kural_siki")[0])
    assert (siki["acik_adet"] <= 40).all() and siki["tavan_dolulugu"].max() == pytest.approx(1.0)
    assert siki["koli_sayisi"].sum() > 0
    assert (siki["gonderilen_adet"] == siki["acik_adet"] + siki["koli_adet"]).all()
    varsayilan = politika.hafta_tablosu(kosular("kural")[0])
    assert (varsayilan["tavan_dolulugu"] == 0).all()
    kisitsiz = politika.hafta_tablosu(kosular("kural_kisitsiz")[0])
    assert (kisitsiz["koli_sayisi"] == 0).all()


def test_defter_kalemleri_kayitta(kosular):
    """Uzlaştırma kalemleri hafta tablosunda: ilk pazartesi başlangıç, sonra her
    pazartesi; kolun kendi sevki bir önceki pazartesinin gönderdiği."""
    hafta = politika.hafta_tablosu(kosular("kural")[0])
    assert hafta["uzl_baslangic"].tolist() == [1] + [0] * 8
    assert (hafta["uzl_kendi_sevk_adet"].iloc[1:].to_numpy()
            == hafta["gonderilen_adet"].iloc[:-1].to_numpy()).all()
    assert {"uzl_teslim_adet", "uzl_online_adet", "uzl_aciklanamayan_eksi_adet",
            "defter_kapali_adet", "defter_acik_adet"} <= set(hafta.columns)


def test_kural_basit_gecmis_ister_ve_kural_ile_ayni_degil(kosular):
    assert KOLLAR["kural_basit"].gecmis_gerekir and not KOLLAR["kural"].gecmis_gerekir
    a = politika.hafta_tablosu(kosular("kural")[0])
    b = politika.hafta_tablosu(kosular("kural_basit")[0])
    assert not np.array_equal(a["hedef_adet"].to_numpy(), b["hedef_adet"].to_numpy())


# ---------------------------------------------------------------- birim testleri


def test_kahin_alani_okunmaz():
    """Politika gizli alan (`lam`, `gizli_*`, …) okumaz; motoru, üreteci, hakemi
    (doğrudan ya da paket içinden) içe aktarmaz (Görev 3'ün tarayıcısı)."""
    yol = Path(politika.__file__)
    assert gizli_erisimler(yol) == []
    assert "politika" not in ihlaller(yol.parent)


def test_baglanmadan_pencerede_hata():
    kol = KOLLAR["kural"](motor.lumoda("replenishment"), Ayar(pencere=PENCERE))
    g = SimpleNamespace(tarih=pd.Timestamp(PENCERE[0]), gun=427)
    with pytest.raises(RuntimeError, match="baglan"):
        kol(g)


def test_pencere_disinda_temel_baglanti_istemez():
    cagri = []
    kol = KOLLAR["kural"](lambda g: cagri.append(g.gun) or np.array([7]), Ayar(pencere=PENCERE))
    g = SimpleNamespace(tarih=pd.Timestamp("2023-08-28"), gun=420)
    assert kol(g).tolist() == [7] and cagri == [420]


def test_baslangic_havuzu_denetimi():
    """Pencere başından (d0) önce ya da d0'da kararlaştırılıp lansmanı d0'dan sonra
    olan ilk dağıtım kaydı defterin havuzunu şişirir: hata."""
    lansman = np.array([10, 30])
    kayit = [{"gun": 5, "args": (0,), "cikti": np.array([2, 0])},
             {"gun": 18, "args": (1,), "cikti": np.array([0, 0])}]        # boş kayıt sayılmaz
    politika.baslangic_havuzu_denetimi(kayit, lansman, 20)
    kayit.append({"gun": 19, "args": (1,), "cikti": np.array([1, 0])})
    with pytest.raises(AssertionError, match="option 1"):
        politika.baslangic_havuzu_denetimi(kayit, lansman, 20)
    politika.baslangic_havuzu_denetimi(kayit, lansman, 30)               # lansman = d0: sorun yok


def test_ayar_dogrulama():
    assert Ayar().pencere[0].isoformat() == "2025-09-01"
    assert Ayar().kural() == KOLI_KURALLARI["A"]()
    assert Ayar(kisitsiz=True).kural() is KISITSIZ
    k = KoliKurali("B", gamma=0.5)
    assert Ayar(koli=k).kural() is k
    for hatali in ({"koli": "Z"}, {"oncelik": "rastgele"}, {"tavan": -1.0},
                   {"kisitsiz": True, "tavan": 100.0}, {"pencere": (date(2025, 9, 2), date(2025, 9, 1))},
                   {"koli": KISITSIZ}):
        with pytest.raises(ValueError):
            Ayar(**hatali)
    assert Ayar(koli=KISITSIZ, kisitsiz=True).kural() is KISITSIZ


def test_parametreler_davranisi_tasir(tahminci):
    """Davranışı değiştiren her şey `parametreler()`'de ve motorun anahtarına
    kanonik girer: Ayar alanları, kolun türü, tahmincinin içerik kimliği,
    çarpanların özeti."""
    lum = motor.lumoda("replenishment")
    taban = KOLLAR["kural"](lum, Ayar()).parametreler()
    motor._kanonik(taban)
    for degisik in (Ayar(tavan=500.0), Ayar(koli="B"), Ayar(oncelik="esit"), Ayar(kisitsiz=True),
                    Ayar(gs=GuvenlikStoku("ros", 7)), Ayar(pencere=PENCERE),
                    Ayar(koli=KoliKurali("A", alfa=0.4, beta=3))):
        assert KOLLAR["kural"](lum, degisik).parametreler() != taban
    t1 = KOLLAR["tahmin"](lum, Ayar(), tahminci=tahminci).parametreler()
    motor._kanonik(t1)
    assert t1["tahminci"] == tahminci.kimlik
    assert KOLLAR["tahmin_taban"](lum, Ayar(), tahminci=tahminci).parametreler() != t1
    b1 = KOLLAR["kural_basit"](lum, Ayar(), carpanlar=Carpanlar()).parametreler()
    b2 = KOLLAR["kural_basit"](lum, Ayar(), carpanlar=Carpanlar(ozel_gun={"tatil": 0.7})).parametreler()
    motor._kanonik(b1)
    assert b1 != b2 and b1 != taban
    # LumodaKol hep orantılı bölüştürür (Ayar.oncelik yerine)
    assert KOLLAR["lumoda"](lum, Ayar(oncelik="cover")).parametreler()["ayar"]["oncelik"] == "orantili"


def test_kol_yeniden_baglaninca_sifirlanir(kosular, w, tahminci):
    """Aynı kol nesnesi ikinci koşuda `baglan` ile sıfırdan başlar: kayıt ve
    sonuç ilk koşuyla birebir."""
    kol = _kol("kural", w, tahminci)
    n = _gun(w, PENCERE[0]) + 15
    k1 = motor.kos(kol, ad="t_tekrar", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
    k2 = motor.kos(kol, ad="t_tekrar", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
    pd.testing.assert_frame_equal(politika.istek_tablosu(k1), politika.istek_tablosu(k2))
    assert len(politika.hafta_tablosu(k2)) == 3


def test_kollar_listesi():
    assert set(KOLLAR) == {"lumoda", "kural", "kural_basit", "tahmin", "tahmin_taban"}
    assert Ayar().tavan == inf


def test_karsilastirma_farki_yakalar(kosular):
    """Kayıttaki bir istek bir adet fazla, bir başkası hiç yokmuş gibi: iki fark satırı."""
    k, _ = kosular("kural")
    kayit = k.kayitlar["replenishment"].copy()
    istek = np.flatnonzero((kayit["kalem"] == "istek").to_numpy())
    kayit.loc[istek[0], "deger"] += 1
    kayit = kayit.drop(index=istek[1])
    sahte = SimpleNamespace(kayitlar={"replenishment": kayit}, tablo=k.tablo)
    fark = politika.sevkiyatla_karsilastir(sahte)
    assert len(fark) == 2
    assert sorted((fark["istek"] - fark["sevk"]).tolist()) == sorted(
        [1, -int(k.kayitlar["replenishment"].loc[istek[1], "deger"])])


def test_lumoda_kisitsiz_motora_aynen_verir(kosular, w, tahminci):
    """Kısıtsız Lumoda kolu pencerede de Lumoda'nın isteğini aynen verir (motorun
    orantılı kesimi böler): koşu Lumoda koşusuyla birebir; kayıt maskeli istektir."""
    kol = KOLLAR["lumoda"](motor.lumoda("replenishment"), Ayar(pencere=PENCERE, kisitsiz=True))
    n = _gun(w, PENCERE[0]) + 15
    k = motor.kos(kol, ad="t_lumoda_kisitsiz", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
    ref = motor.kos(ad="referans", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
    for t in ("sevkiyat", "satis", "stok", "depo_stok"):
        pd.testing.assert_frame_equal(k.tablolar[t], ref.tablolar[t])
    assert len(politika.hafta_tablosu(k)) == 3 and len(politika.istek_tablosu(k)) > 0


# ---------------------------------------------------------------- düzeltme turu (R21)


def test_karsilastirma_pazartesisiz_hata(kosular):
    """Kayıtta pencere pazartesisi yoksa denetim boş dönmez (hiçbir şey denetlenmedi): hata."""
    k, _ = kosular("kural")
    bos = k.kayitlar["replenishment"].iloc[:0]
    with pytest.raises(ValueError, match="pazartesi"):
        politika.sevkiyatla_karsilastir(SimpleNamespace(kayitlar={"replenishment": bos}, tablo=k.tablo))
    sadece_istek = k.kayitlar["replenishment"]
    sadece_istek = sadece_istek[sadece_istek["kalem"] == "istek"]
    with pytest.raises(ValueError, match="pazartesi"):
        politika.sevkiyatla_karsilastir(SimpleNamespace(kayitlar={"replenishment": sadece_istek}, tablo=k.tablo))


def test_carpanlar_kopyalanir():
    """Çağıranın çarpan nesnesi sonradan değişirse kolun davranışı da anahtarı da değişmez."""
    c = Carpanlar(ozel_gun={"tatil": 0.7})
    kol = KOLLAR["kural_basit"](motor.lumoda("replenishment"), Ayar(), carpanlar=c)
    once = kol.parametreler()
    c.ozel_gun["tatil"] = 0.1
    c.hafta_gunu[("magaza", 0)] = 2.0
    assert kol.parametreler() == once
    assert kol.carpanlar.ozel_gun == {"tatil": 0.7} and kol.carpanlar.hafta_gunu == {}
    assert politika.carpan_ozeti(kol.carpanlar) == once["carpanlar"]


def test_lumoda_kaydinda_hedef_yok(kosular):
    """Lumoda kolu hedef kurmaz (isteği zaten eksik): `hedef_adet` sütunu yok, yanlış
    okunamaz; hedefli kollarda var ve hedef ≥ eksik değil, ayrı büyüklük."""
    lum = politika.hafta_tablosu(kosular("lumoda")[0])
    assert "hedef_adet" not in lum.columns and (lum["istek_adet"] > 0).all()
    assert "hedef_adet" in politika.hafta_tablosu(kosular("kural")[0]).columns


def test_lumoda_kisitsiz_kaydedicisiz_yeniden_kullanilir(w):
    """Kısıtsız Lumoda bağlantı istemez: `kaydedici=False` ile aynı nesne iki koşuda
    da çalışır (ikinci koşu durumunu sıfırlar), kayıtlar birebir. Defter tutan kol
    `kaydedici=False` ile pencereye girince açık hata verir."""
    kol = KOLLAR["lumoda"](motor.lumoda("replenishment"), Ayar(pencere=PENCERE, kisitsiz=True))
    n = _gun(w, PENCERE[0]) + 8
    a = [motor.kos(kol, ad="t_lk", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n,
                   kaydedici=False) for _ in range(2)]
    pd.testing.assert_frame_equal(politika.istek_tablosu(a[0]), politika.istek_tablosu(a[1]))
    assert len(politika.hafta_tablosu(a[1])) == 2
    kural = KOLLAR["kural"](motor.lumoda("replenishment"), Ayar(pencere=PENCERE))
    with pytest.raises(RuntimeError, match="kaydedici=True"):
        motor.kos(kural, ad="t_kk", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n,
                  kaydedici=False)


class _Sonda(_Denetci):
    """Seçili pazartesilerde kolun o anki durumunun kopyasını bozuk geleceği olan bir
    görünümle çağırır (dünya ve tahminci paylaşılır), sonra kolun kendisini gerçek
    görünümle; ikisinin çıktısını saklar."""

    def __init__(self, kol, gunler, paylas=()):
        super().__init__(kol)
        self.gunler, self.paylas, self.sonuc = set(gunler), list(paylas), {}

    def __call__(self, g):
        if g.gun not in self.gunler:
            return self.kol(g)
        bellek = {id(x): x for x in [g.dunya, *self.paylas]}
        klon = copy.deepcopy(self.kol, bellek)
        S, F = np.asarray(g.satis_gecmisi), np.asarray(g.stoklu_gecmisi)
        ek = 21                                           # t günü ve sonraki üç hafta
        bozuk = dataclasses.replace(
            g, satis_gecmisi=np.concatenate([S, np.full((ek, S.shape[1]), 99, dtype=S.dtype)]),
            stoklu_gecmisi=np.concatenate([F, np.ones((ek, F.shape[1]), dtype=F.dtype)]))
        r_bozuk = np.array(klon(bozuk))
        r = np.asarray(self.kol(g))
        self.sonuc[int(g.gun)] = (np.array(r), r_bozuk)
        return r


@pytest.mark.parametrize("ad", ["kural", "tahmin"])
def test_istek_gelecegi_gormez(w, tahminci, ad):
    """Spec §4.2: pencere pazartesisi t'nin isteği, Görünüm'e t günü ve sonrasının
    (bozuk) satış / stoklu satırları eklenince aynı durumdan birebir aynı; ilk
    pazartesi (bir kerelik hesaplar) ve sonraki bir pazartesi (uzlaştırma)."""
    d0 = _gun(w, PENCERE[0])
    gunler = (d0, d0 + 14)
    kol = _kol(ad, w, tahminci)
    sonda = _Sonda(kol, gunler, paylas=[tahminci])
    motor.kos(sonda, ad=f"t_sizinti_{ad}", parametreler={}, onbellek=None, olcek="kucuk",
              gun_sayisi=d0 + 15)
    assert set(sonda.sonuc) == set(gunler)
    for gun, (r, r_bozuk) in sonda.sonuc.items():
        assert r.sum() > 0
        assert np.array_equal(r, r_bozuk), gun


def test_kayit_onbellek_gidis_donusu(w, tahminci, tmp_path):
    """Kolun kaydı koşu önbelleğine yazılıp okunur (tam ve tembel `KosuKaydi`); okunan
    koşuda denetim 0 fark, istek ve hafta tabloları bellekteki koşuyla aynı."""
    kol = _kol("kural_siki", w, tahminci)
    n = _gun(w, PENCERE[0]) + 15
    bellekte = motor.kos(kol, ad="t_onbellek", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=n)
    yazilan = motor.kos(kol, ad="t_onbellek", parametreler={}, onbellek=tmp_path, olcek="kucuk", gun_sayisi=n)
    tembel = motor.kos(kol, ad="t_onbellek", parametreler={}, onbellek=tmp_path, olcek="kucuk", gun_sayisi=n,
                       tembel=True)
    assert not yazilan.onbellekten and tembel.onbellekten and isinstance(tembel, motor.KosuKaydi)
    for k in (yazilan, tembel):
        assert politika.sevkiyatla_karsilastir(k).empty
        pd.testing.assert_frame_equal(politika.istek_tablosu(k), politika.istek_tablosu(bellekte))
        pd.testing.assert_frame_equal(politika.hafta_tablosu(k), politika.hafta_tablosu(bellekte))
    assert len(politika.hafta_tablosu(tembel)) == 3
