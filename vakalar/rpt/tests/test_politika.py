"""Kollar (v4 `rpt` kancası) ve kâhin: KÜÇÜK motor koşularıyla.

Sızıntı kalkanı: kâhin dışındaki kollar gelecekteki talebi görmez — ne
içe aktarmayla (politika kâhini içe aktarmaz; tarama geçişli), ne argümanla
(kurucularında talep yok), ne görünümden (Görünüm'de bugün ve sonrası yok).
Kâhin ayrı modüldedir ve geleceği gördüğü sınanır (kalkanın sağlaması).
"""

import inspect

import numpy as np
import pandas as pd
import pytest
from conftest import SabitModel, kucuk_ogrenilen
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar

from rpt import kahin, motor, politika

GUN = 900      # KÜÇÜK: AW24 lansmanları 777, 812, 847; karar haftaları h = 2…6 → 791…889
OYUN = ("AW24", "SS25")


def _w():
    return motor.dunya("kucuk")


def _oyun(w):
    opt = w.optionlar
    return (opt["line"] == "Collection").to_numpy() & opt["sezon_kodu"].isin(OYUN).to_numpy()


def _rpt(ham, maske=None):
    return sorted((int(s["option"]), int(s["siparis_gun"]), int(np.sum(s["adetler"])))
                  for s in ham["siparis"] if s["tip"] == "rpt" and (maske is None or maske[s["option"]]))


def _kos(rpt, gun=GUN):
    return simule_et(_w(), Politikalar(rpt=rpt), gun_sayisi=gun,
                     gecmis_kaydi=bool(getattr(rpt, "gecmis_gerekir", False)))


@pytest.fixture(scope="module")
def lumoda():
    return simule_et(_w(), gun_sayisi=GUN)


@pytest.fixture(scope="module")
def ogrenilen():
    return kucuk_ogrenilen(_w())


@pytest.fixture(scope="module")
def oneri(ogrenilen):
    kol = politika.Oneri(motor.lumoda("rpt"), ogrenilen)
    return _kos(kol), kol


def test_kollar():
    assert set(politika.KOLLAR) == {"rpt_yok", "mevcut", "frr", "oneri"}
    assert not hasattr(politika, "Kahin")
    assert issubclass(kahin.Kahin, politika.KolRPT)


def test_mevcut_kol_lumoda_ile_ayni(lumoda):
    """`mevcut` = v4 `LumodaRPT`: varsayılan motorla birebir (yayımlanan dünya)."""
    kol = politika.Mevcut(motor.lumoda("rpt"))
    ham = _kos(kol)
    assert _rpt(ham) == _rpt(lumoda)
    for ad in ("satis", "sevkiyat", "gizli_kayip"):
        pd.testing.assert_frame_equal(ham[ad], lumoda[ad])
    k = kol.kayit_tablosu()
    oyun = _oyun(_w())
    assert sorted(zip(k["option"], k["gun"], k["adet"])) == _rpt(lumoda, oyun)


def test_rpt_yok_oyunda_rpt_vermez(lumoda):
    w = _w()
    oyun = _oyun(w)
    ham = _kos(politika.RPTYok(motor.lumoda("rpt")))
    assert _rpt(ham, oyun) == [] and _rpt(lumoda, oyun)
    # oyundan önce kapanan sezonlarda Lumoda'nın kararları aynen
    gecmis = w.optionlar["sezon_kodu"].isin(("SS24", "AW23")).to_numpy()
    assert _rpt(ham, gecmis) == _rpt(lumoda, gecmis) and _rpt(lumoda, gecmis)


def test_en_fazla_bir_rpt(oneri, ogrenilen, lumoda):
    """Her kol oyun option'ı başına en fazla bir RPT verir; öneri kolu yalnız karar
    haftalarında (h = 2…6) ve kendi kaydıyla tutarlı."""
    w = _w()
    oyun = _oyun(w)
    lansman = w.optionlar["lansman_gun"].to_numpy()
    ham_o, kol = oneri
    ham_f = _kos(politika.FRR(motor.lumoda("rpt"), ogrenilen))
    for ham in (ham_o, ham_f, lumoda):
        r = _rpt(ham, oyun)
        assert r and len({o for o, _, _ in r}) == len(r)
    r = _rpt(ham_o, oyun)
    h = [(g - lansman[o]) / 7 for o, g, _ in r]
    assert set(h) <= {2, 3, 4, 5, 6}
    k = kol.kayit_tablosu()
    assert sorted(zip(k["option"], k["gun"], k["adet"])) == r
    assert (k["p"] >= ogrenilen.esik).all() and (k["D"] >= k["x"]).all()


def test_oneri_esik_ustu_yoksa_rpt_yok(ogrenilen):
    o = politika.Ogrenilen(**{**ogrenilen.__dict__, "modeller": {s: SabitModel(0.0) for s in OYUN}})
    ham = _kos(politika.Oneri(motor.lumoda("rpt"), o), gun=830)
    assert _rpt(ham, _oyun(_w())) == []


def test_parametreler_ogrenileni_yansitir(ogrenilen):
    """Çevrimdışı öğrenilen her parça kolun `parametreler`ine (koşu önbelleği anahtarı) girer."""
    temel = motor.lumoda("rpt")
    p0 = politika.Oneri(temel, ogrenilen).parametreler()
    degisik = {
        "modeller": {s: SabitModel(0.9) for s in OYUN},
        "esik": 0.6,
        "p_ind": ogrenilen.p_ind * 0.9,
        "carpanlar": dict(list(ogrenilen.carpanlar.items())[:-1]),
        "belirsizlik": {**ogrenilen.belirsizlik, "AW24": ogrenilen.belirsizlik["SS25"].__class__(
            mu={2: 0.1}, sigma={2: 0.2}, n={2: 1}, sezonlar=())},
    }
    for ad, deger in degisik.items():
        o = politika.Ogrenilen(**{**ogrenilen.__dict__, ad: deger})
        assert politika.Oneri(temel, o).parametreler() != p0, ad
    assert politika.Oneri(temel, ogrenilen, model="lojistik").parametreler() != p0
    assert politika.Oneri(temel, ogrenilen).parametreler() == p0
    anahtar = lambda p: motor.onbellek_anahtari(  # noqa: E731
        ad="oneri", parametreler=p, talep_tohumu=None, operasyon_tohumu=motor.TOHUM, olcek="kucuk",
        gun_sayisi=GUN, turler={})
    o = politika.Ogrenilen(**{**ogrenilen.__dict__, "esik": 0.7})
    assert anahtar(p0) != anahtar(politika.Oneri(temel, o).parametreler())


def test_kahin_disi_kollar_gelecek_talebi_kullanmaz(ogrenilen, oneri):
    from test_sizinti import PAKET, ihlaller

    # 1) içe aktarma: politika (ve dağıtım) kâhine ne doğrudan ne geçişli ulaşır
    bulunan = ihlaller(PAKET, karar=("politika", "dagitim", "anlik"))
    assert not bulunan, bulunan
    # 2) argüman: kâhin dışı kolların kurucusunda talep yok
    for ad, kol in politika.KOLLAR.items():
        params = set(inspect.signature(kol.__init__).parameters)
        assert not {p for p in params if "talep" in p or "gercek" in p}, ad
    assert "gercek_talep" in inspect.signature(kahin.Kahin.__init__).parameters

    # 3) görünüm: her çağrıda geçmiş yalnız bugünden önce
    class Gozcu(politika.Oneri):
        def __call__(self, g):
            assert g.satis_gecmisi.shape[0] == g.gun == g.satis_oncesi_gecmisi.shape[0]
            assert g.stoklu_gecmisi.shape[0] == g.gun
            assert all(p[0] < g.gun for p in g.fiyat_gecmisi)
            assert all(p[0] <= g.gun for p in g.stok_fotograflari)
            return super().__call__(g)

    kesim = 840
    ham_kisa = _kos(Gozcu(motor.lumoda("rpt"), ogrenilen), gun=kesim)
    # 4) önek: kesime dek verilen kararlar, sonrası koşulsa da aynı
    ham_tam, _ = oneri
    assert _rpt(ham_kisa) == [r for r in _rpt(ham_tam) if r[1] < kesim]
    assert [r for r in _rpt(ham_kisa, _oyun(_w()))]


def test_kahin_gelecegi_gorur(ogrenilen):
    """Kalkanın sağlaması: kâhinin kararı kesimden sonraki talebe bağlıdır."""
    k = motor.kos(ad="lumoda", parametreler={}, onbellek=None, olcek="kucuk", gun_sayisi=GUN)
    talep = k.gercek[["tarih", "urun_id", "talep"]]
    kesim = pd.Timestamp(motor._gun_tarihi([800])[0])
    bozuk = talep.copy()
    bozuk.loc[bozuk["tarih"] >= kesim, "talep"] *= 3
    temel = motor.lumoda("rpt")
    k1, k2 = kahin.Kahin(talep, temel, ogrenilen), kahin.Kahin(bozuk, temel, ogrenilen)
    assert k1.parametreler() != k2.parametreler()
    oyun = _oyun(_w())
    r1, r2 = _rpt(_kos(k1), oyun), _rpt(_kos(k2), oyun)
    assert r1 and len({o for o, _, _ in r1}) == len(r1)
    assert r1 != r2
    assert _rpt(_kos(k1), oyun) == r1          # aynı nesne ikinci koşuda: plan sıfırlanır
    # kesimden önce verilen kararlar da değişir: kâhin geleceği görür
    assert [r for r in r1 if r[1] < 805] != [r for r in r2 if r[1] < 805]


def test_kos_anahtari_politikanin_kendi_kimligini_gorur(tmp_path, ogrenilen):
    """`motor.kos` anahtarı çağıranın `parametreler`ine güvenmez: enjekte edilen
    politikanın `parametreler()`i ve sardığı `temel`in türü/kimliği de girer. Dağıtım
    kuralı, `temel` kuralı ya da öğrenilen bir parça değişince anahtar değişir; aynısı
    önbellekten okunur."""
    from conftest import duz_egri

    from rpt import dagitim

    temel_r, temel_d = motor.lumoda("rpt"), motor.lumoda("replenishment")

    def baska_temel(g):
        return temel_d(g)

    cx = {s: duz_egri("cikis", [1, 2, 3]) for s in OYUN}

    def kos(rpt, rep):
        return motor.kos(rpt=rpt, replenishment=rep, ad="kimlik", parametreler={}, onbellek=tmp_path,
                         olcek="kucuk", gun_sayisi=40)

    ogr2 = politika.Ogrenilen(**{**ogrenilen.__dict__, "modeller": {s: SabitModel(0.3) for s in OYUN}})
    durumlar = {
        "taban": (politika.Oneri(temel_r, ogrenilen), dagitim.KURALLAR["b"](temel_d, cx)),
        "kural": (politika.Oneri(temel_r, ogrenilen), dagitim.KURALLAR["c"](temel_d, cx)),
        "temel": (politika.Oneri(temel_r, ogrenilen), dagitim.KURALLAR["b"](baska_temel, cx)),
        "ogrenilen": (politika.Oneri(temel_r, ogr2), dagitim.KURALLAR["b"](temel_d, cx)),
    }
    anahtar = {ad: kos(*p).meta["anahtar"] for ad, p in durumlar.items()}
    assert len(set(anahtar.values())) == len(anahtar), anahtar
    tekrar = kos(politika.Oneri(temel_r, ogrenilen), dagitim.KURALLAR["b"](temel_d, cx))
    assert tekrar.onbellekten and tekrar.meta["anahtar"] == anahtar["taban"]
    k = tekrar.meta["politikalar"]
    assert k["replenishment"]["temel"]["tur"].endswith("lumoda_replenishment")
    assert k["rpt"]["parametreler"]["ogrenilen"] == ogrenilen.parametreler()
    # Lumoda'nın varsayılan koşusunun içeriğinde politika kimliği yok (anahtarı değişmez)
    assert "politikalar" not in motor.kos(ad="lumoda", parametreler={}, onbellek=None, olcek="kucuk",
                                          gun_sayisi=20).meta
