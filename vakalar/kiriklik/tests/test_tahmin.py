"""`tahmin`: ufuk talebi (K9, Ruling R8). Hızlı testler elle kurulmuş `KararGirdisi` ve elle kurulmuş
`Ogrenilen` kullanır (öğrenme gerçek veride dakikalar sürer); `veri` işaretli testler öğrenmeyi gerçek v4'te
koşar (YAVAŞ: ilk koşu ~10-15 dk, önbellek `cikti/ogrenme`)."""

import ast
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import oyuncak_baglan, oyuncak_tablolar
from markdown.ogrenme import Ogrenilen

from kiriklik import kaynak, sabitler, tahmin, uygunluk

KARAR, INDIRIM, CIKIS = date(2024, 12, 9), date(2025, 1, 2), date(2025, 2, 24)
EVRE1_GUN, EVRE2_GUN = 21, 53          # [12-12, 01-02), [01-02, 02-24)
PAY = (1, 2, 2, 1, 1)                  # zincir beden payı (7'ye bölünür)
CIKTI = Path(__file__).resolve().parents[1] / "cikti"


def _og(eps=0.0, hafta_gunu=None, ozel_gun=None, islem=0.0, iade=0.0, yasam=None, bitis=KARAR, sezon="AW24",
        beden_payi=None):
    if beden_payi is None:
        beden_payi = pd.DataFrame([("*", "O1", f"O1-{i + 1}", p / 7) for i, p in enumerate(PAY)],
                                  columns=["magaza_id", "option_id", "urun_id", "pay"])
    if yasam is None:
        yasam = pd.DataFrame(columns=["sezon_tipi", "duzey", "grup", "dalga", "hafta", "carpan", "kaynak"])
    return Ogrenilen(test_sezonu=sezon, bitis=bitis, sezonlar=("AW23",), eps_kampanya={"Üst Giyim": eps},
                     eps_markdown={}, eps_saf=0.0, yasam=yasam, hafta_gunu=hafta_gunu or {},
                     ozel_gun=ozel_gun or {}, beden_payi=beden_payi, kalinti=0.1,
                     iade={"magaza": iade, "online": 0.0}, islem=islem)


def _girdi(magazalar, satis, stoklu, stoklar=None, uygun=None, tatil=(), bf=()) -> kaynak.KararGirdisi:
    """Tek option (`O1`, 5 beden, liste 100). `magazalar`: mağaza kimlikleri; `stoklar`: {magaza: 5'li stok}
    (verilmeyen mağaza kırık: ikinci beden 0, ötekiler 1); `satis`: (magaza, sıra, gün farkı, adet);
    `stoklu`: (magaza, sıra, karardan önce gün farkı, stoklu gün); `tatil`: tatil günleri; `bf`: (başlangıç, bitiş, oran)."""
    stoklar = stoklar or {}
    satir = []
    for m in magazalar:
        for i, s in enumerate(stoklar.get(m, (1, 0, 1, 1, 1))):
            satir.append((m, f"O1-{i + 1}", "O1", i + 1, s, 0, 0, 100.0, 40.0))
    hucre = pd.DataFrame(satir, columns=["magaza_id", "urun_id", "option_id", "beden_sira", "stok", "depo",
                                         "acik_siparis", "liste_fiyati", "alis_fiyati"])
    karar = pd.Timestamp(KARAR)
    sat = pd.DataFrame([(m, f"O1-{i}", karar - timedelta(days=d), a, a * 100.0) for m, i, d, a in satis],
                       columns=["magaza_id", "urun_id", "tarih", "adet", "tutar"])
    sto = pd.DataFrame([(m, f"O1-{i}", karar - timedelta(days=d), n) for m, i, d, n in stoklu],
                       columns=["magaza_id", "urun_id", "tarih", "stoklu_gun"])
    uygun = uygun or {}
    mag = pd.DataFrame({"magaza_id": list(magazalar), "ad": list(magazalar), "sehir": "X", "bolge": "Y",
                        "tip": "AVM", "uygun": [uygun.get(m, True) for m in magazalar]})
    opt = pd.DataFrame([("O1", "Tişört", "Üst Giyim", 1, pd.Timestamp("2024-08-19"), 100.0, 40.0)],
                       columns=["option_id", "alt_kategori", "ust_kategori", "dalga", "lansman_tarihi",
                                "liste_fiyati", "alis_fiyati"])
    gunler = pd.date_range("2024-10-01", "2025-03-31")
    takvim = pd.DataFrame({"tarih": gunler, "tatil_mi": gunler.isin([pd.Timestamp(t) for t in tatil])})
    black_friday = pd.DataFrame([(pd.Timestamp(b), pd.Timestamp(e), o) for b, e, o in bf],
                                columns=["baslangic", "bitis", "oran"])
    return kaynak.KararGirdisi(sezon="AW24", karar=KARAR, indirim=INDIRIM, cikis=CIKIS, hucre=hucre,
                               satis=sat, stoklu=sto, magaza=mag, optionlar=opt, takvim=takvim,
                               black_friday=black_friday)


def _foto(magaza, bedenler, gun=7, fotolar=(21, 14, 7, 0)):
    """Pencerenin dört pazartesi fotoğrafı (karar − 21, −14, −7, karar): her biri `gun` stoklu gün."""
    return [(magaza, i, f, gun) for i in bedenler for f in fotolar]


def _hucre(df, magaza, sira):
    s = df[(df.magaza_id == magaza) & (df.urun_id == f"O1-{sira}")]
    assert len(s) == 1
    return s.iloc[0]


# ---------------------------------------------------------------- taban hız ve kırık beden


def test_kirik_beden_talebi_sifir_degil():
    """M1'in ikinci bedeni stoksuz (stoklu gün 0, satış 0); talebi yine de beden payı kadar pozitiftir."""
    sat = [("M1", i, 5, 4) for i in (1, 3, 4, 5)] + [("M2", i, 5, 2) for i in (1, 2, 3, 4, 5)]
    sto = _foto("M1", (1, 3, 4, 5)) + _foto("M2", (1, 2, 3, 4, 5)) + _foto("M1", (2,), gun=0)
    g = _girdi(("M1", "M2"), sat, sto, stoklar={"M2": (1, 1, 1, 1, 1)})
    t = tahmin.ufuk_talebi(g, _og())
    assert len(t) == 10 and list(t.columns) == tahmin.KOLONLAR
    # M1: Σ satış 16; Σ stoklu gün × pay = 28 × (1+2+1+1)/7 = 20 → r = 0,8
    r = 16 / (28 * 5 / 7)
    kirik = _hucre(t, "M1", 2)
    assert kirik.mu_tam == pytest.approx(r * 2 / 7 * EVRE1_GUN) and kirik.mu_tam > 0
    assert kirik.mu_ind == pytest.approx(r * 2 / 7 * EVRE2_GUN)          # eps 0: fiyat çarpanı 1
    assert _hucre(t, "M1", 1).mu_tam == pytest.approx(r * 1 / 7 * EVRE1_GUN)
    # kırık hücre de aynı option hızını taşır: bedenler toplamı = r × (1 − 0 kayıp) × gün
    assert t[t.magaza_id == "M1"].mu_tam.sum() == pytest.approx(r * EVRE1_GUN)


def test_stoklu_gun_siniri_pencere():
    """Fotoğraf `karar − 28` (önceki 7 günü pencereden önce) paydaya girmez; `karar` fotoğrafı girer."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    sto = _foto("M1", range(1, 6)) + [("M1", i, 28, 7) for i in range(1, 6)]
    g = _girdi(("M1",), sat, sto)
    t = tahmin.ufuk_talebi(g, _og())
    assert t.mu_tam.sum() == pytest.approx(20 / 28 * EVRE1_GUN)            # r = 20 / 28 (35 olsaydı 20 / 35)


def test_sansur_duzeltmesi_hizi_arttirir():
    """Aynı satış yarım stoklu günle iki kat hız verir."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    tam = tahmin.ufuk_talebi(_girdi(("M1",), sat, _foto("M1", range(1, 6))), _og())
    yarim = tahmin.ufuk_talebi(
        _girdi(("M1",), sat, _foto("M1", range(1, 6), gun=3.5)), _og())
    assert yarim.mu_tam.sum() == pytest.approx(2 * tam.mu_tam.sum())


def test_yetersiz_kanit_zincir_hizina_duser():
    """M3'ün payda kanıtı < 7 (tek beden, tek fotoğraf): zincir hızı × (mağazanın sezon satış payı ÷ payda
    ağırlıklı ortalama mağazanın payı)."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)] + [("M2", i, 5, 2) for i in range(1, 6)] + [("M3", 1, 5, 1)] \
        + [("M1", 1, 40, 6)]                                              # M1'in sezon payı pencere dışı da sayar
    sto = _foto("M1", range(1, 6)) + _foto("M2", range(1, 6)) + [("M3", 1, 7, 7)]
    t = tahmin.ufuk_talebi(_girdi(("M1", "M2", "M3"), sat, sto), _og())
    # M3: payda 7 × 1/7 = 1 < 7. Zincir: Σ satış (20 + 10 + 1) ÷ Σ payda (28 + 28 + 1); sezon payları 26, 10, 1 (÷ 37);
    # payda ağırlıklı ortalama pay (28 × 26 + 28 × 10 + 1 × 1) ÷ 37 ÷ 57
    r_zincir = 31 / 57
    ortalama_pay = (28 * 26 + 28 * 10 + 1 * 1) / 37 / 57
    r_m3 = r_zincir * (1 / 37) / ortalama_pay
    assert t[t.magaza_id == "M3"].mu_tam.sum() == pytest.approx(r_m3 * EVRE1_GUN)
    # M1 kendi kanıtıyla: 26 satış değil, pencerede 20 satış (40 gün önceki satış pencere dışı)
    assert t[t.magaza_id == "M1"].mu_tam.sum() == pytest.approx(20 / 28 * EVRE1_GUN)


def test_sezon_satisi_yoksa_pay_esit():
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    sto = _foto("M1", range(1, 6)) + [("M2", 1, 7, 7)]
    t = tahmin.ufuk_talebi(_girdi(("M1", "M2"), sat, sto), _og())
    # M2'nin sezon satışı yok: pay 0 → talep 0 (sezonda hiç satmamış mağaza)
    assert t[t.magaza_id == "M2"].mu_tam.sum() == 0.0
    sat0 = []
    t0 = tahmin.ufuk_talebi(_girdi(("M1", "M2"), sat0, sto), _og())
    assert (t0.mu_tam == 0).all()                    # hiç satış yok: zincir hızı 0


# ---------------------------------------------------------------- gün çarpanları ve fiyat


def test_indirim_fiyati_yuzde_otuz():
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    g = _girdi(("M1",), sat, _foto("M1", range(1, 6)))
    og = _og(eps=1.5, islem=0.02, iade=0.05)
    t = tahmin.ufuk_talebi(g, og)
    assert t.fiyat_ind.to_numpy() == pytest.approx(np.full(5, 100.0 * 0.70 * 0.95))
    assert t.fiyat_tam.to_numpy() == pytest.approx(np.full(5, 100.0 * 0.98 * 0.95))
    # eps 1,5: indirimli evrenin talebi (1 − 0,30)^(−1,5) ile ölçeklenir; günler 53 ÷ 21
    oran = (t.mu_ind / t.mu_tam).to_numpy()
    assert oran == pytest.approx(np.full(5, EVRE2_GUN / EVRE1_GUN * 0.7 ** -1.5))


def test_gun_carpanlari_gun_gun():
    """Hafta günü, yaşam eğrisi, tatil, Black Friday (cuma, devam, fiyat) ve indirim başlangıcı, takvim günü günü."""
    hg = {("magaza", w): v for w, v in enumerate((0.9, 0.9, 0.9, 1.0, 1.2, 1.6, 1.4))}
    ozel = {"indirim_baslangici": 1.3, "tatil": 0.7, "black_friday": 1.8, "black_friday_devami": 1.1}
    yasam = pd.DataFrame({"sezon_tipi": "AW", "duzey": "alt_kategori", "grup": "Tişört", "dalga": 1,
                          "hafta": np.arange(30), "carpan": np.linspace(1.0, 0.4, 30), "kaynak": "alt_kategori"})
    og = _og(eps=1.0, hafta_gunu=hg, ozel_gun=ozel, yasam=yasam)
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    # BF cumada başlar (2024-11-29), pencerededir; tatil: BF cuması ve 2025-01-01 (ufukta, evre 1'in son günü)
    g = _girdi(("M1",), sat, _foto("M1", range(1, 6)), tatil=("2024-11-29", "2025-01-01"),
               bf=(("2024-11-29", "2024-12-02", 0.3),))
    t = tahmin.ufuk_talebi(g, og)

    lansman = pd.Timestamp("2024-08-19")
    egri = np.linspace(1.0, 0.4, 30)
    bf_gunler = pd.date_range("2024-11-29", "2024-12-02")

    def f(gun: pd.Timestamp, indirim: bool = False) -> float:
        tur = (ozel["black_friday"] if gun.weekday() == 4 else ozel["black_friday_devami"]) if gun in bf_gunler             else ozel["tatil"] if gun == pd.Timestamp("2025-01-01")             else ozel["indirim_baslangici"] if pd.Timestamp("2025-01-02") <= gun < pd.Timestamp("2025-01-09") else 1.0
        oran = max(0.3 if gun in bf_gunler else 0.0, 0.30 if indirim else 0.0)
        return hg[("magaza", gun.weekday())] * egri[min((gun - lansman).days // 7, 29)] * tur / (1 - oran)

    pencere = np.mean([f(pd.Timestamp(KARAR) - timedelta(days=k)) for k in range(1, 29)])
    s1 = sum(f(d) for d in pd.date_range("2024-12-12", "2025-01-01"))
    s2 = sum(f(d, True) for d in pd.date_range("2025-01-02", "2025-02-23"))
    r = 20 / 28
    assert t.mu_tam.sum() == pytest.approx(r / pencere * s1)
    assert t.mu_ind.sum() == pytest.approx(r / pencere * s2)


def test_black_friday_haftasi_tabani_sisirmez():
    """Aynı satış, Black Friday penceredeyse (takvim bilinirse) daha düşük taban hız verir; BF yoksa fark yoktur."""
    og = _og(eps=1.5, ozel_gun={"black_friday": 1.8, "black_friday_devami": 1.1})
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    sto = _foto("M1", range(1, 6))
    bf = (("2024-11-29", "2024-12-02", 0.3),)
    bf_var = tahmin.ufuk_talebi(_girdi(("M1",), sat, sto, bf=bf), og).mu_tam.sum()
    bf_yok = tahmin.ufuk_talebi(_girdi(("M1",), sat, sto), og).mu_tam.sum()
    assert bf_var < bf_yok
    # ortalama karakter: 24 gün 1,0; BF cuması 1,8 × 0,7^-1,5; devam 3 gün 1,1 × 0,7^-1,5
    bf_f = 0.7 ** -1.5
    beklenen = (1.0 * 24 + 1.8 * bf_f + 3 * 1.1 * bf_f) / 28
    assert bf_var / bf_yok == pytest.approx(1 / beklenen)


def test_takvim_kapsamiyorsa_hata():
    g = _girdi(("M1",), [], [])
    kisa = kaynak.KararGirdisi(**{**g.__dict__, "takvim": g.takvim[g.takvim.tarih < "2025-01-15"]})
    with pytest.raises(ValueError, match="takvim"):
        tahmin.ufuk_talebi(kisa, _og())


def test_yalniz_uygun_option_ve_magaza():
    """Uygun mağaza ve uygun adayı olan option; uygun olmayan mağaza çıkmaz."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    sto = _foto("M1", range(1, 6))
    g = _girdi(("M1", "M2"), sat, sto, {"M1": (1,) * 5}, uygun={"M2": False})
    t = tahmin.ufuk_talebi(g, _og())
    assert t.empty                                    # M1 tam set, M2 kırık ama mağaza uygun değil: aday yok
    g = _girdi(("M1", "M2", "M3"), sat, sto, {"M1": (1,) * 5, "M3": (1,) * 5}, uygun={"M2": False})
    assert uygunluk.adaylar(g).uygun.sum() == 0
    g = _girdi(("M1", "M2", "M3"), sat, sto)
    t = tahmin.ufuk_talebi(g, _og())
    assert set(t.magaza_id) == {"M1", "M2", "M3"} and len(t) == 15
    g = _girdi(("M1", "M2"), sat, sto, uygun={"M2": False})       # aday M1; uygun olmayan M2 hücreleri çıkmaz
    assert set(tahmin.ufuk_talebi(g, _og()).magaza_id) == {"M1"}


def test_stoksuz_option_magazasi_hucre_degil():
    """Option'dan karar günü hiç stoğu olmayan mağaza (alıcı da verici de olamaz) çıkmaz; kanıtı yine de hıza girer."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)] + [("M4", i, 5, 4) for i in range(1, 6)]         + [("M2", 1, 40, 3)]                                           # M2: sezon satışı var, pencerede kanıt yok
    sto = _foto("M1", range(1, 6)) + _foto("M4", range(1, 6))
    g = _girdi(("M1", "M2", "M4"), sat, sto, {"M2": (1,) * 5, "M4": (0,) * 5})
    t = tahmin.ufuk_talebi(g, _og())
    assert set(t.magaza_id) == {"M1", "M2"} and len(t) == 10
    assert _hucre(t, "M2", 1).mu_tam > 0                               # stoklu mağaza yedek hızla talep alır


def test_bos_cikti_semasi():
    g = _girdi(("M1",), [], [], {"M1": (1,) * 5})                 # tam set: kırık çift yok
    t = tahmin.ufuk_talebi(g, _og())
    assert t.empty and t.dtypes.astype(str).tolist() == ["object", "object"] + ["float64"] * 4
    assert t.empty and list(t.columns) == tahmin.KOLONLAR


def test_ogrenme_karardan_sonrayi_gormus_reddedilir():
    g = _girdi(("M1", "M2"), [], [], {"M2": (1,) * 5})
    with pytest.raises(ValueError, match="karar gününden sonrasını"):
        tahmin.ufuk_talebi(g, _og(bitis=date(2024, 12, 10)))
    with pytest.raises(ValueError, match="sezon"):
        tahmin.ufuk_talebi(g, _og(sezon="SS25"))


def test_baska_sezon_ogrenilmez(con):
    with pytest.raises(ValueError, match="AW25"):
        tahmin.ogrenilen(con, "AW25")


def test_magaza_ozel_beden_payi_zincirden_once():
    """Mağazaya özgü beden payı satırı zincirinkinin yerine geçer; mağaza × option içinde 1'e normalize."""
    bp = pd.DataFrame([("*", "O1", f"O1-{i + 1}", p / 7) for i, p in enumerate(PAY)]
                      + [("M1", "O1", f"O1-{i + 1}", p) for i, p in enumerate((6, 0, 2, 1, 1))],
                      columns=["magaza_id", "option_id", "urun_id", "pay"])
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    g = _girdi(("M1", "M2"), sat, _foto("M1", range(1, 6)), {"M2": (1,) * 5})
    t = tahmin.ufuk_talebi(g, _og(beden_payi=bp))
    toplam = t[t.magaza_id == "M1"].mu_tam.sum()
    assert _hucre(t, "M1", 1).mu_tam == pytest.approx(toplam * 0.6)       # 6 / 10
    assert _hucre(t, "M1", 2).mu_tam == 0.0                               # mağazanın payı 0


# ---------------------------------------------------------------- karar anı kilidi (DuckDB)


def _aday_baglan(bozuk: bool = False):
    """Oyuncak dünya + kırık ikinci bedenin doldurulabilir olmadığı (depo ve açık sipariş 0) S1 çifti, S1 ve S2
    için karar öncesi satış. `bozuk`: karar günü ve sonrasındaki satış, karardan sonraki stok ve depo satırları
    abartılı değerlerle bozulur (karar gününün pazartesi fotoğrafı karar anında bilinen girdidir, bozulmaz)."""
    c = oyuncak_baglan(oyuncak_tablolar())
    c.execute("update depo_stok set adet = 0")
    c.execute("delete from siparis where option_id = 'AW24-a'")
    for m in ("S1", "S2"):
        for i in range(1, 6):
            for gun in ("2024-11-14", "2024-11-26", "2024-12-04"):
                c.execute("insert into satis values (?, ?, ?, 2, 1000.0, 0.0, NULL)", [gun, m, f"AW24-a-{i}"])
    if bozuk:
        c.execute("update satis set adet = 999, tutar = 99900.0 where tarih >= ?", [KARAR])
        c.execute("insert into satis select tarih + interval 3 day, 'S2', 'AW24-a-2', adet, tutar, 0.0, NULL "
                  "from satis where tarih = ?", [KARAR])
        c.execute("insert into stok select tarih + interval 14 day, magaza_id, urun_id, 50, 0 "
                  "from stok where tarih > ?", [KARAR])
        c.execute("update stok set adet = 50, stoklu_gun = 0 where tarih > ?", [KARAR])
        c.execute("update depo_stok set adet = 999 where tarih > ?", [KARAR])
    return c


def _og_oyuncak():
    bp = pd.DataFrame([("*", "AW24-a", f"AW24-a-{i + 1}", p / 7) for i, p in enumerate(PAY)],
                      columns=["magaza_id", "option_id", "urun_id", "pay"])
    og = _og(eps=1.2, islem=0.01, iade=0.04, beden_payi=bp)
    return og


def test_oyuncak_dunya_hucre_ve_talep():
    c = _aday_baglan()
    g = kaynak.karar_girdisi(c, "AW24")
    t = tahmin.ufuk_talebi(g, _og_oyuncak())
    c.close()
    assert set(t.magaza_id) == {"S1", "S2"} and len(t) == 10             # S6 uygun ama option'dan stoğu yok
    assert (t.mu_tam >= 0).all() and t[t.magaza_id == "S1"].mu_tam.sum() > 0


def test_karar_ani_kilidi():
    """Karar günü ve sonrasındaki `satis`, karardan sonraki `stok` ve `depo_stok` satırlarını bozmak
    çıktıyı değiştirmez."""
    og = _og_oyuncak()
    ciktilar, satis_sayisi = [], []
    for bozuk in (False, True):
        c = _aday_baglan(bozuk)
        satis_sayisi.append(c.execute("select count(*) from satis where tarih >= ?", [KARAR]).fetchone()[0])
        ciktilar.append(tahmin.ufuk_talebi(kaynak.karar_girdisi(c, "AW24"), og))
        c.close()
    assert not ciktilar[0].empty and ciktilar[0].mu_tam.sum() > 0       # kilit anlamlı: çıktı sıfır değil
    assert satis_sayisi[1] > satis_sayisi[0]                             # bozma gerçekten satır ekledi
    pd.testing.assert_frame_equal(ciktilar[0], ciktilar[1])


def test_karar_ani_kilidi_modul_kendisi_de_keser():
    """`kaynak` kesimini aşan satırlar (elle kurulmuş girdi) modülün kendi pencere süzgecinde de tutulur."""
    sat = [("M1", i, 5, 4) for i in range(1, 6)]
    sto = _foto("M1", range(1, 6))
    g = _girdi(("M1",), sat, sto)
    temiz = tahmin.ufuk_talebi(g, _og())
    sizan = [("M1", i, -2, 500) for i in range(1, 6)]            # karardan 2 gün SONRA (gün farkı negatif)
    sizan_foto = [("M1", i, -7, 7) for i in range(1, 6)]
    g2 = _girdi(("M1",), sat + sizan, sto + sizan_foto)
    pd.testing.assert_frame_equal(temiz, tahmin.ufuk_talebi(g2, _og()))


# ---------------------------------------------------------------- AST kilidi


def test_karar_modulu_ice_aktarma_ve_ad_kilidi():
    agac = ast.parse(Path(tahmin.__file__).read_text(encoding="utf-8"))
    alinan = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            alinan |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            alinan.add(n.module or "")
            alinan |= {f"{n.module}.{a.name}" for a in n.names}
    yasak = ("perakende_veri", "allocation", "kiriklik.hakem", "kiriklik.simulasyon", "kiriklik.olcutler",
             "kiriklik.oyun")
    assert not [a for a in alinan if any(a == y or a.startswith(y + ".") for y in yasak)]
    assert "markdown.ogrenme" in alinan                           # Ruling R8: çarpanlar buradan
    # gizli gerçek adları (`lam`, `esneklik*`, `gercek*`, `gizli_*`) ne ad ne öznitelik ne metin olarak geçer
    kalip = ("lam", "esneklik", "gercek", "gizli_")
    for d in ast.walk(agac):
        if isinstance(d, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(d):
            d.body = d.body[1:]
    adlar = [d.id for d in ast.walk(agac) if isinstance(d, ast.Name)] \
        + [d.attr for d in ast.walk(agac) if isinstance(d, ast.Attribute)] \
        + [d.value for d in ast.walk(agac) if isinstance(d, ast.Constant) and isinstance(d.value, str)]
    assert not [a for a in adlar if any(a == k or a.startswith(k) for k in kalip)]


# ---------------------------------------------------------------- gerçek veri (YAVAŞ)


@pytest.fixture(scope="module", params=sabitler.TEST_SEZONLARI)
def talep(request, veri_con):
    """(girdi, öğrenilen, ufuk talebi) her test sezonu için; önbellek `cikti/ogrenme` (git dışı).
    İlk koşu: AW24 ~5 dk, SS25 ~8 dk; önbellekle ~20 sn."""
    g = kaynak.karar_girdisi(veri_con, request.param)
    og = tahmin.ogrenilen(veri_con, request.param, onbellek=CIKTI / "ogrenme")
    return g, og, tahmin.ufuk_talebi(g, og)


# `markdown.ogrenme` (salt okunur kardeş vaka) pandas 2.3 + numpy 2.5 "generic unit" uyarısı verir; yalnız bu iki
# öğrenmeli testte, o uyarıya özgü süzgeçle sessizleştirilir
UYARI = pytest.mark.filterwarnings("ignore:.*generic.*unit:DeprecationWarning")


@pytest.mark.veri
@UYARI
def test_ufuk_sema_ve_isaretler(talep):
    g, og, t = talep
    assert list(t.columns) == tahmin.KOLONLAR and len(t) > 0
    assert np.isfinite(t[["mu_tam", "mu_ind", "fiyat_tam", "fiyat_ind"]].to_numpy()).all()
    assert (t.mu_tam >= 0).all() and (t.mu_ind >= 0).all() and (t.fiyat_ind < t.fiyat_tam).all()
    assert og.bitis == g.karar
    h = g.hucre.merge(t[["magaza_id", "urun_id", "mu_tam"]], on=["magaza_id", "urun_id"])
    assert len(h) == len(t)
    # R10: her (mağaza, option) çiftinde option stoğu var; kırık beden hücreleri pozitif talep taşır
    assert (h.groupby(["magaza_id", "option_id"]).stok.transform("sum") > 0).all()
    assert len(h[(h.stok == 0) & (h.mu_tam > 0)]) > 0


@pytest.mark.veri
@UYARI
def test_ufuk_toplami_makul(veri_con, talep):
    """R9: stoklu hücrelerde Σ min(mu_tam, stok) ÷ yayımlanan brüt fiziksel satış [karar + 3, indirim) ∈ [0,8; 1,25].
    (Satış stokla kısıtlıdır; talep kısıtsızdır, o yüzden mu stokla kırpılarak kıyaslanır.)"""
    g, _, t = talep
    h = g.hucre.merge(t[["magaza_id", "urun_id", "mu_tam"]], on=["magaza_id", "urun_id"])
    h = h[h.stok > 0]
    veri_con.register("_hucre", h[["magaza_id", "urun_id"]])
    gercek = veri_con.execute("""
        select coalesce(sum(adet), 0) from (select distinct * from satis) s
        join _hucre h using (magaza_id, urun_id)
        where s.adet > 0 and s.tarih >= ? and s.tarih < ?""",
                              [pd.Timestamp(g.karar) + timedelta(days=sabitler.VARIS_GUN),
                               pd.Timestamp(g.indirim)]).fetchone()[0]
    veri_con.unregister("_hucre")
    oran = np.minimum(h.mu_tam, h.stok).sum() / gercek
    print(f"\n{g.sezon}: Σ min(mu_tam, stok) = {np.minimum(h.mu_tam, h.stok).sum():.1f}, "
          f"satış = {gercek}, oran = {oran:.3f}; Σ mu_tam = {h.mu_tam.sum():.1f}")
    assert 0.8 <= oran <= 1.25, (g.sezon, oran)
