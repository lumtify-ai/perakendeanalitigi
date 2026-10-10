"""`replenishment.defter`: gölge defter (spec §3.4; Ruling R8).

Oyuncak dünya: iki option (o0 Collection, açık payı %20; o1 NOS, %40), her
biri beş beden, paket [1, 2, 2, 1, 1] (koli 7 adet). SKU 0–4 o0'ın, 5–9
o1'in bedenleri (beden sırasıyla). Mağazalar M1 (fiziksel) ve ONL; her SKU'nun
bir M1 ve bir ONL hücresi var (hücre 2s M1, 2s+1 ONL).

Görünüm sahtedir (`_g`): defter yalnız `gun`, `depo`, `satis_gecmisi`,
`acik_siparisler` ve `dunya`'yı okur. KÜÇÜK dünya testleri gerçek
`Gorunum`'la koşar (testler `perakende_veri`'yi içe aktarabilir; modül
aktaramaz).
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from replenishment import defter, sabitler
from replenishment.defter import GolgeDefter, beden_skulari, bol, koli_icerigi

PAKET = np.array([1, 2, 2, 1, 1])
ACIK_PAYI = sabitler.ACIK_PAYI
O0, O1 = slice(0, 5), slice(5, 10)


def _dunya(lansman=(5, 5)):
    paketler = pd.DataFrame({
        "paket_id": ["PKT01"] * 5,
        "beden_seti": ["Harf"] * 5,
        "beden_sira": [1, 2, 3, 4, 5],
        "adet": PAKET,
    })
    optionlar = pd.DataFrame({"line": ["Collection", "NOS"], "beden_seti": ["Harf", "Harf"],
                              "lansman_gun": list(lansman)})
    urunler = pd.DataFrame({"beden_sira": [1, 2, 3, 4, 5] * 2})
    magazalar = pd.DataFrame({"magaza_id": ["M1", "ONL"], "tip": ["AVM", "Online"]})
    S = 10
    return SimpleNamespace(
        paketler=paketler, optionlar=optionlar, urunler=urunler, magazalar=magazalar,
        sku_option=np.repeat([0, 1], 5),
        hucre_sku=np.repeat(np.arange(S), 2), hucre_magaza=np.tile([0, 1], S),
        hucre_online=np.tile([False, True], S), hucre_option=np.repeat([0, 1], 10),
    )


def _vektor(o0=(), o1=()):
    """[S]: o0'ın ve o1'in beden adetleri (kısa verilen sağdan 0'la dolar)."""
    v = np.zeros(10, dtype=np.int64)
    v[:len(o0)] = o0
    v[5:5 + len(o1)] = o1
    return v


def _siparis(o, adetler, siparis_gun=-30, tip="rpt"):
    sk = np.arange(5) + 5 * o
    return {"tip": tip, "option": o, "siparis_gun": siparis_gun, "planlanan_gun": siparis_gun + 35,
            "skular": sk, "adetler": np.asarray(adetler, dtype=np.int64), "tedarikci": 0}


def _g(w, gun, depo, siparisler=(), online=None):
    """Sahte görünüm. `online`: {gün: [S] online satış} (ONL hücrelerine)."""
    C = len(w.hucre_sku)
    satis = np.zeros((gun, C), dtype=np.int16)
    for d, v in (online or {}).items():
        satis[d, 2 * np.arange(10) + 1] = v
    return SimpleNamespace(dunya=w, gun=gun, depo=np.asarray(depo, dtype=np.int64),
                           satis_gecmisi=satis, acik_siparisler=tuple(siparisler))


def _ilk(gun, o, paket_m1):
    return {"gun": gun, "args": (o,), "cikti": np.array([paket_m1, 0])}


def _outlet(gun, kaynak, hedef, sku, adet):
    tr = SimpleNamespace(kaynak=np.array(kaynak), hedef=np.array(hedef),
                         sku=np.array(sku), adet=np.array(adet))
    return {"gun": gun, "args": (np.array([0]),), "cikti": tr}


def _degismez(d, depo):
    assert np.array_equal(d.kapali_adet() + d.acik, depo)
    assert (d.kapali >= 0).all() and (d.acik >= 0).all()


# --------------------------------------------------------------- koli içeriği


def test_koli_icerigi_oyuncak():
    w = _dunya()
    icerik, koli_adedi = koli_icerigi(w)
    assert icerik.tolist() == [PAKET.tolist()] * 2
    assert koli_adedi.tolist() == [7, 7]
    assert beden_skulari(w).tolist() == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]


# ------------------------------------------------------------------- bölme


def test_bol_tam_koli_ve_acik_payi():
    w = _dunya()
    koli, acik = bol(_vektor(10 * PAKET, 10 * PAKET), w, ACIK_PAYI)
    # o0: 70 adet dengeli → 10 koli; %20 açık → 8 kapalı koli + 14 açık adet
    assert koli[0] == 8 and acik[O0].sum() == 14
    assert acik[O0].tolist() == (2 * PAKET).tolist()
    # o1 (NOS, %40): 10 koli → 6 kapalı + 28 açık
    assert koli[1] == 6 and acik[O1].sum() == 28


def test_bol_dengesiz_beden():
    w = _dunya()
    # o0'ın 4. bedeni 5 adet: koli sayısı onunla sınırlı (5); kapalı ⌊5 × 0,8⌋ = 4
    koli, acik = bol(_vektor([10, 20, 20, 5, 10]), w, ACIK_PAYI)
    assert koli[0] == 4
    assert acik[O0].tolist() == [6, 12, 12, 1, 6]
    # bir beden hiç yoksa hiç koli kurulmaz: hepsi açık
    koli, acik = bol(_vektor([10, 20, 20, 0, 10]), w, ACIK_PAYI)
    assert koli[0] == 0 and acik[O0].tolist() == [10, 20, 20, 0, 10]


def test_bol_kayan_nokta_yuvarlamasi():
    w = _dunya()
    # 5 koli × (1 − 0,4) = 3 tam (kayan noktada 2,999… olmamalı)
    koli, _ = bol(_vektor((), 5 * PAKET), w, ACIK_PAYI)
    assert koli[1] == 3
    # ⌊142 × 0,8⌋ = 113
    koli, _ = bol(_vektor([143, 286, 285, 143, 143]), w, ACIK_PAYI)
    assert koli[0] == 113


# -------------------------------------------------------------------- defter


def test_baslat_bol_ile_ve_depo_kopyalanir():
    w = _dunya()
    depo = _vektor(10 * PAKET, 10 * PAKET)
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    assert d.kapali.tolist() == [8, 6]
    _degismez(d, _vektor(10 * PAKET, 10 * PAKET))
    depo[:] = 0                       # görünümün dizisi sonradan değişse de defter aynı
    assert d.kapali.tolist() == [8, 6]
    _degismez(d, _vektor(10 * PAKET, 10 * PAKET))


def test_depo_salt_okunur_gorunumu_kopyalanir():
    w = _dunya()
    canli = _vektor(10 * PAKET)
    gorunum = canli.view()
    gorunum.flags.writeable = False   # motorun Gorunum.depo'su gibi
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, gorunum))
    d.dus_acik(_vektor([1]))          # defterin dizisi yazılabilir olmalı
    canli += 5                        # canlı dizi değişir, defter değişmez
    assert d.acik[O0].sum() == 13


def test_ilk_dagitim_brut_kapali_koliden():
    """Aynı aralıkta 1.000 adet gelir, 700'ü (100 paket) ilk dağıtımla çıkar:
    kapalı = ⌊(1.000 / 7) × 0,8⌋ − 100 = 13 koli; net +300'ü bölmek 33 verirdi."""
    w = _dunya()
    gelen = np.array([143, 286, 285, 143, 143])
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, np.zeros(10, dtype=np.int64), [_siparis(0, gelen)]))
    depo = _vektor(gelen - 100 * PAKET)
    u = d.uzlastir(_g(w, 7, depo), [_ilk(3, 0, 100)], [])
    assert d.kapali[0] == 13
    assert bol(depo, w, ACIK_PAYI)[0][0] == 33            # net bölme başka sonuç verirdi
    assert d.acik[O0].tolist() == (gelen - 113 * PAKET).tolist()
    assert (u.teslim_adet, u.teslim_kapali_koli, u.teslim_acik_adet) == (1000, 113, 209)
    assert (u.ilk_dagitim_kayit_koli, u.ilk_dagitim_kapali_koli, u.ilk_dagitim_acik_adet) == (100, 100, 0)
    assert u.aciklanamayan_eksi_adet == 0 and u.aciklanamayan_arti_adet == 0
    _degismez(d, depo)


def test_ilk_dagitim_ust_sinir_tasinir_ve_suresi_dolunca_duser():
    """Kayıt politikanın kararıdır (üst sınır): motorun ertelediği sevk sonraki
    pazartesiye taşınır; option'ın son sevk günü (max(lansman, karar)) geçince
    kalan düşer."""
    w = _dunya(lansman=(10, 10))
    depo = _vektor(20 * PAKET)                            # 16 kapalı + 4 koli açık
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    kayit = [_ilk(3, 0, 10)]
    depo = depo - _vektor(6 * PAKET)                      # bu hafta 6 paket çıktı
    u = d.uzlastir(_g(w, 7, depo), kayit, [])
    assert d.kapali[0] == 10 and d.acik[O0].tolist() == (4 * PAKET).tolist()
    assert (u.ilk_dagitim_kapali_koli, u.ilk_dagitim_bekleyen_koli, u.ilk_dagitim_dusen_koli) == (6, 4, 0)
    depo = depo - _vektor(3 * PAKET)                      # ertelenen 3 paket (gün 9)
    u = d.uzlastir(_g(w, 14, depo), kayit, [])
    assert d.kapali[0] == 7
    assert (u.ilk_dagitim_kayit_koli, u.ilk_dagitim_kapali_koli) == (0, 3)
    assert (u.ilk_dagitim_bekleyen_koli, u.ilk_dagitim_dusen_koli) == (0, 1)
    depo = depo - _vektor(PAKET)                          # süre dolmuş: açıklanamayan, önce açıktan
    u = d.uzlastir(_g(w, 21, depo), kayit, [])
    assert d.kapali[0] == 7 and u.ilk_dagitim_kapali_koli == 0
    assert u.aciklanamayan_eksi_adet == 7 and d.acik[O0].tolist() == (3 * PAKET).tolist()
    _degismez(d, depo)


def test_ilk_dagitim_kapali_yetmezse_acikdan():
    w = _dunya()
    depo = _vektor(5 * PAKET)                             # 4 kapalı, 1 koli açık
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    depo = depo - _vektor(5 * PAKET)
    u = d.uzlastir(_g(w, 7, depo), [_ilk(2, 0, 5)], [])
    assert (u.ilk_dagitim_kapali_koli, u.ilk_dagitim_acik_adet) == (4, 7)
    assert d.kapali[0] == 0 and d.acik.sum() == 0


def test_online_satis_once_acik():
    w = _dunya()
    depo = _vektor(10 * PAKET)                            # 8 kapalı + açık [2,4,4,2,2]
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    sat = _vektor([0, 0, 3, 0, 0])
    depo = depo - sat
    u = d.uzlastir(_g(w, 7, depo, online={2: sat}), [], [])
    assert d.kapali[0] == 8 and d.acik[O0].tolist() == [2, 4, 1, 2, 2]
    assert u.online_adet == 3 and u.acilan_koli == 0
    # açık yetmeyince kapalıdan: bir koli açılır (M bedeninden 2 gelir)
    depo = depo - sat
    u = d.uzlastir(_g(w, 14, depo, online={10: sat}), [], [])
    assert d.kapali[0] == 7 and d.acik[O0].tolist() == [3, 6, 0, 3, 3]
    assert u.acilan_koli == 1
    _degismez(d, depo)


def test_online_satis_iadeyle_gelen_stoktan():
    """Aralıkta gelen artı (ör. kapanış dönüşü) online satıştan önce açığa
    girer: defter hiçbir adımda eksiye düşmez."""
    w = _dunya()
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, np.zeros(10, dtype=np.int64)))
    sat = _vektor([0, 0, 3, 0, 0])
    depo = _vektor([0, 0, 2, 0, 0])                       # +5 döndü, 3'ü online satıldı
    u = d.uzlastir(_g(w, 7, depo, online={4: sat}), [], [])
    assert u.aciklanamayan_arti_adet == 5 and u.online_adet == 3
    _degismez(d, depo)


def test_aciklanamayan_fark_kalemi():
    w = _dunya()
    depo = _vektor(10 * PAKET, 10 * PAKET)
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    # o0 S bedeni +4 (iade/devir: açığa), o1 XS bedeni −5 (kalite reddi vb.: önce açık, sonra kapalı)
    depo = depo + _vektor([0, 4], [-5])
    u = d.uzlastir(_g(w, 7, depo), [], [])
    assert (u.aciklanamayan_arti_adet, u.aciklanamayan_eksi_adet) == (4, 5)
    assert d.acik[1] == 4 + 4                             # o0 S: 4 açık + 4 artı
    # o1 XS: 4 açık vardı, 1 eksik kaldı → bir koli açıldı
    assert d.kapali[1] == 5 and d.acik[5] == 0 and u.acilan_koli == 1
    _degismez(d, depo)


def test_kendi_sevki_dagitta_dusulur():
    w = _dunya()
    depo = _vektor(10 * PAKET)
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    d.dus_acik(_vektor([1, 2, 0, 0, 0]))
    d.dus_koli(np.array([2, 0]))
    depo = depo - _vektor([1, 2]) - 2 * _vektor(PAKET)
    u = d.uzlastir(_g(w, 7, depo), [], [])
    assert u.kendi_sevk_adet == 3 + 14
    assert u.aciklanamayan_arti_adet == 0 and u.aciklanamayan_eksi_adet == 0
    assert d.kapali[0] == 6
    _degismez(d, depo)


def test_outlet_ust_sinir_once_acik():
    w = _dunya()
    depo = _vektor(10 * PAKET)                            # 8 kapalı + açık [2,4,4,2,2]
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, depo))
    # depodan M1'e (0) XS 3 ve S 10 istendi; depodan ONL'ye (1) ve depo→depo satırı
    # motorca düşer; mağazadan mağazaya satır depoyu ilgilendirmez
    kayit = [_outlet(4, [-1, -1, -1, -1, 0], [0, 0, 1, -1, 0], [0, 1, 2, 3, 4], [3, 10, 4, 2, 9])]
    depo = depo - _vektor([3, 6])                         # motor S'yi 6'ya kırptı
    u = d.uzlastir(_g(w, 7, depo), [], kayit)
    assert u.outlet_adet == 9 and u.aciklanamayan_eksi_adet == 0
    # XS: 2 açık + 1 koli açıldı; S: 4 açık + 2 (aynı koliden) → açık S 0
    assert d.kapali[0] == 7 and d.acik[O0].tolist() == [0, 0, 6, 3, 3]
    _degismez(d, depo)


def test_teslim_yalniz_dusen_siparis():
    w = _dunya()
    a, b = _siparis(0, 10 * PAKET, siparis_gun=-30), _siparis(1, 10 * PAKET, siparis_gun=-20)
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, np.zeros(10, dtype=np.int64), [a, b]))
    yeni = _siparis(0, 99 * PAKET, siparis_gun=0)       # aralıkta verilen: teslim değil
    depo = _vektor(10 * PAKET)
    u = d.uzlastir(_g(w, 7, depo, [b, yeni]), [], [])
    assert u.teslim_adet == 70 and d.kapali.tolist() == [8, 0]
    _degismez(d, depo)


def test_defter_degismezi_her_pazartesi():
    """Teslim, online satış, ilk dağıtım, kendi sevki ve açıklanamayan fark
    karışık haftalar: her uzlaştırma sonunda değişmez tutar."""
    w = _dunya(lansman=(12, 30))
    rng = np.random.default_rng(7)
    d = GolgeDefter(w, ACIK_PAYI)
    depo = _vektor(30 * PAKET, 12 * PAKET)
    acik_sip = [_siparis(0, 40 * PAKET + np.array([0, 1, 3, 0, 2]), siparis_gun=-40),
                _siparis(1, 25 * PAKET, siparis_gun=-10)]
    d.baslat(_g(w, 0, depo, acik_sip))
    kayit = [_ilk(10, 0, 12)]
    for hafta in range(1, 7):
        gun = 7 * hafta
        if hafta == 2:                                    # o0 teslim + ilk dağıtım (12 paket)
            depo = depo + _vektor(acik_sip[0]["adetler"]) - _vektor(12 * PAKET)
            acik_sip = acik_sip[1:]
        if hafta == 4:
            depo = depo + _vektor((), 25 * PAKET)
            acik_sip = []
        online = np.minimum(rng.integers(0, 3, 10), depo)
        depo = depo - online
        gurultu = rng.integers(-2, 3, 10)
        depo = np.maximum(depo + gurultu, 0)
        d.uzlastir(_g(w, gun, depo, acik_sip, online={gun - 3: online}), kayit, [])
        _degismez(d, depo)
        sevk = np.minimum(d.acik, rng.integers(0, 3, 10))
        d.dus_acik(sevk)
        depo = depo - sevk
    assert len(d.kayit_tablosu()) == 7                    # başlangıç + 6 hafta
    assert d.kayit_tablosu()[0]["baslangic"] is True


def test_stoktan_fazla_dusum_hata():
    w = _dunya()
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, _vektor(10 * PAKET)))
    once_acik, once_kapali = d.acik.copy(), d.kapali.copy()
    with pytest.raises(ValueError):
        d.dus_acik(_vektor([3]))                          # açık XS 2
    with pytest.raises(ValueError):
        d.dus_koli(np.array([9, 0]))                      # kapalı 8
    with pytest.raises(ValueError):
        d.dus_acik(_vektor([-1]))
    with pytest.raises(ValueError):
        d.dus_koli(np.array([0, -1]))
    assert np.array_equal(d.acik, once_acik) and np.array_equal(d.kapali, once_kapali)


def test_uzlastirma_sirasi_denetlenir():
    w = _dunya()
    d = GolgeDefter(w, ACIK_PAYI)
    with pytest.raises(RuntimeError):
        d.uzlastir(_g(w, 7, np.zeros(10, dtype=np.int64)), [], [])   # baslat'tan önce
    d.baslat(_g(w, 7, np.zeros(10, dtype=np.int64)))
    with pytest.raises(ValueError):
        d.uzlastir(_g(w, 7, np.zeros(10, dtype=np.int64)), [], [])   # aynı gün


def test_kayit_tablosu_kalemleri():
    w = _dunya()
    d = GolgeDefter(w, ACIK_PAYI)
    d.baslat(_g(w, 0, _vektor(10 * PAKET)))
    d.uzlastir(_g(w, 7, _vektor(10 * PAKET)), [], [])
    t = d.kayit_tablosu()
    assert [r["gun"] for r in t] == [0, 7]
    assert t[0]["kapali_koli"] == 8 and t[0]["acik_adet"] == 14
    assert {"teslim_adet", "online_adet", "ilk_dagitim_kapali_koli", "outlet_adet",
            "aciklanamayan_arti_adet", "aciklanamayan_eksi_adet", "kendi_sevk_adet"} <= set(t[1])


def test_modul_gizli_gercegi_ice_aktarmaz():
    import ast
    agac = ast.parse(open(defter.__file__, encoding="utf-8").read())
    adlar = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            adlar |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            adlar.add(n.module or "")
    assert not any(a.startswith(("perakende_veri", "perakende_analitik.hakem", "replenishment.motor"))
                   or a == "motor" for a in adlar)


# -------------------------------------------------------- gerçek KÜÇÜK dünya


def test_koli_icerigi_gercek_dunya():
    from perakende_veri.v4.politika import paket_tablosu

    from replenishment import motor

    w = motor.dunya("kucuk")
    icerik, koli_adedi = koli_icerigi(w)
    skular = beden_skulari(w)
    _, set_idx, ic = paket_tablosu(w.paketler)
    beden_sira = w.urunler["beden_sira"].to_numpy()
    for o in range(len(w.optionlar)):
        p = set_idx[w.optionlar.at[o, "beden_seti"]]
        sk = skular[o][skular[o] >= 0]
        assert np.array_equal(np.sort(sk), np.flatnonzero(np.asarray(w.sku_option) == o))
        assert np.array_equal(icerik[o, :len(sk)], ic[p, beden_sira[sk]])
        assert koli_adedi[o] == ic[p].sum()
    aksesuar = (w.optionlar["beden_seti"] == "Standart").to_numpy()
    assert set(koli_adedi[aksesuar]) == {6} and set(koli_adedi[~aksesuar]) == {7}


def test_kucuk_dunya_kosusu_gercek_akislarla():
    """KÜÇÜK dünyada gerçek `Gorunum`'la: oyun başlangıcından sonra kol hiç
    göndermez (kendi sevki 0), defter her pazartesi uzlaştırır. Teslim ve
    online satış motorun kaydıyla birebir; ilk dağıtımın kapalıdan düşülen
    kısmı motorun ilk dağıtım sevkini aşmaz ve onu büyük ölçüde açıklar."""
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.politika import Politikalar

    from replenishment import motor

    w = motor.dunya("kucuk")
    tarih = pd.DatetimeIndex(w.takvim["tarih"])
    bas = int(np.flatnonzero(tarih == pd.Timestamp(sabitler.OYUN_BAS))[0])
    son = bas + 12 * 7
    k_ilk = motor.Kaydedici(motor.lumoda("ilk_dagitim"))
    k_out = motor.Kaydedici(motor.lumoda("outlet_akisi"))
    temel = motor.lumoda("replenishment")
    df = GolgeDefter(w, ACIK_PAYI)

    def kol(g):
        if g.gun < bas:
            return temel(g)
        if g.gun == bas:
            df.baslat(g)
        else:
            df.uzlastir(g, k_ilk.kayit, k_out.kayit)
        return np.zeros(len(w.cesit), dtype=np.int64)

    ham = simule_et(w, Politikalar(replenishment=kol, ilk_dagitim=k_ilk, outlet_akisi=k_out),
                    gun_sayisi=son + 1)
    t = pd.DataFrame(df.kayit_tablosu())
    assert len(t) == 13 and t["baslangic"].iloc[0]
    hafta = t.iloc[1:]
    assert (hafta["kendi_sevk_adet"] == 0).all()

    # Teslim: (önceki pazartesi, pazartesi] aralığında gerçekleşen siparişlerin brüt adedi
    sip = ham["siparis"]
    for _, r in hafta.iterrows():
        dogru = sum(int(np.sum(s["adetler"])) for s in sip
                    if r["onceki_gun"] < s["gerceklesen_gun"] <= r["gun"])
        assert r["teslim_adet"] == dogru

    # Online: [önceki pazartesi, pazartesi) günlerinin brüt online satışı
    satis = ham["satis"]
    onl = np.asarray(w.hucre_online)
    pozitif = satis[(satis["adet"] > 0) & onl[satis["hucre"].to_numpy()]]
    for _, r in hafta.iterrows():
        g_ = pozitif[(pozitif["gun"] >= r["onceki_gun"]) & (pozitif["gun"] < r["gun"])]
        assert r["online_adet"] == int(g_["adet"].sum())

    # İlk dağıtım: eşlenen (kapalıdan + açıktan) motorun gerçek sevkine yakın. Kayıt
    # üst sınır olduğu için fazlası olabilir: motor kalite reddiyle küçülen depoya
    # paketleri sığdırırken kırpar, kalan kayıt aynı haftanın kalite reddi eksiğini
    # eşler (Ruling R8'in bedeli); fazla, penceredeki kalite reddini aşamaz.
    sv = ham["sevkiyat"]
    ilk = int(sv[(sv["tip"] == "ilk_dagitim") & (sv["gun"] > bas) & (sv["gun"] <= son)]["adet"].sum())
    kalite = ham["kalite"]
    hatali = int(kalite[(kalite["gun"] > bas) & (kalite["gun"] <= son)]["hatali"].sum())
    eslenen = int((hafta["ilk_dagitim_kapali_adet"] + hafta["ilk_dagitim_acik_adet"]).sum())
    assert ilk > 0
    assert 0.98 * ilk <= eslenen <= ilk + hatali
    # Kayıt üst sınırdır: kaydedilen paket ≥ eşlenen + düşen + bekleyen
    assert (hafta["ilk_dagitim_kayit_koli"].sum()
            >= hafta["ilk_dagitim_kapali_koli"].sum() + hafta["ilk_dagitim_dusen_koli"].sum())
