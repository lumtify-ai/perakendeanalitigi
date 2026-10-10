import numpy as np
import pandas as pd
import pytest

from rpt import dagitim, egri


def test_hiz_hedefi_son_stoklu_gunler():
    # İki hücre, 10 gün. Hücre 0: ilk 6 gün stoklu, günde 2 satar, sonra boş.
    # Hücre 1: hiç stoklu değil. Eğri düz (β = 1/7).
    S = np.zeros((10, 2))
    F = np.zeros((10, 2), dtype=bool)
    S[:6, 0], F[:6, 0] = 2, True
    beta = np.full(10, 1 / 7)
    hedef, var = dagitim.hiz_hedefi(S, F, beta, beta_ileri=28 / 7)
    # seviye = 12 / (6/7) = 14 ⇒ günlük 2 ⇒ 28 günde 56. Son 7 gün satış 0
    # olsa da hız sıfır görünmez (bugünkü kapının tersine).
    assert hedef[0] == pytest.approx(56)
    assert var.tolist() == [True, False]


def test_hiz_hedefi_pencere_en_son_stoklu_gunler():
    S = np.zeros((40, 1))
    F = np.ones((40, 1), dtype=bool)
    S[:10, 0] = 10    # eski yüksek satış
    S[10:, 0] = 1     # son 30 gün günde 1
    beta = np.full(40, 1 / 7)
    hedef, _ = dagitim.hiz_hedefi(S, F, beta, beta_ileri=4, pencere=28)
    assert hedef[0] == pytest.approx(28)   # yalnız son 28 stoklu gün


def test_hiz_hedefi_egriyle_tasir():
    # Geçmişte eğri ağırlığı 2, ileride 1: hız yarıya iner
    S = np.full((7, 1), 4.0)
    F = np.ones((7, 1), dtype=bool)
    hedef, _ = dagitim.hiz_hedefi(S, F, np.full(7, 2.0), beta_ileri=28 * 1.0)
    assert hedef[0] == pytest.approx(2 * 28)


def test_gunluk_agirlik():
    e = egri.Egri(paylar={(1,): np.array([0.7, 0.3])}, grup=("dalga",), yontem="x", hedef="cikis",
                  sezonlar=())
    b = dagitim.gunluk_agirlik(e, 1, 20)
    assert b[:7].sum() == pytest.approx(0.7) and b[7:14].sum() == pytest.approx(0.3)
    assert b[14:].sum() == 0


# ---------------------------------------------------------------------------
# v4 replenishment kancası (KÜÇÜK motor koşuları)
# ---------------------------------------------------------------------------

GUN = 870      # KÜÇÜK: AW24 lansmanı 777, Lumoda'nın AW24 RPT'leri 834'ten itibaren varır


def _cx(w):
    from conftest import duz_egri

    dalgalar = sorted(w.optionlar["dalga"].dropna().astype(int).unique())
    return {s: duz_egri("cikis", dalgalar) for s in ("AW24", "SS25")}


def _kos(rpt, kural):
    from perakende_veri.v4.motor import simule_et
    from perakende_veri.v4.politika import Politikalar

    from rpt import motor

    w = motor.dunya("kucuk")
    rep = dagitim.KURALLAR[kural](motor.lumoda("replenishment"), _cx(w))
    ham = simule_et(w, Politikalar(rpt=rpt, replenishment=rep), gun_sayisi=GUN)
    return ham, rep


@pytest.fixture(scope="module")
def rpt_yok_a():
    from rpt import motor, politika

    return _kos(politika.RPTYok(motor.lumoda("rpt")), "a")


@pytest.fixture(scope="module")
def mevcut_a():
    from rpt import motor, politika

    return _kos(politika.Mevcut(motor.lumoda("rpt")), "a")


def test_kurallar_v4_kancasi():
    assert set(dagitim.KURALLAR) == {"a", "b", "c", "d"}
    for k, kur in dagitim.KURALLAR.items():
        r = kur(lambda g: np.zeros(3, dtype=np.int64), {})
        assert isinstance(r, dagitim.RPTDagitim) and r.kural == k
        assert r.tutma == (0.30 if k == "d" else 0.0)
    with pytest.raises(ValueError):
        dagitim.RPTDagitim(None, {}, kural="mevcut")


def test_parametreler_kurali_ve_egriyi_yansitir():
    from conftest import duz_egri

    cx = {"AW24": duz_egri("cikis", [1, 2, 3])}
    temel = lambda g: None  # noqa: E731
    p = {k: dagitim.KURALLAR[k](temel, cx).parametreler() for k in dagitim.KURALLAR}
    assert len({str(v) for v in p.values()}) == 4
    cx2 = {"AW24": duz_egri("cikis", [1, 2, 3], hafta=20)}
    assert dagitim.KURALLAR["b"](temel, cx2).parametreler() != p["b"]


def test_en_buyuk_kalan_v4_ile_ayni():
    from perakende_veri.v4.plan import en_buyuk_kalan

    rng = np.random.default_rng(0)
    for _ in range(200):
        p = rng.random(rng.integers(1, 8)) * (rng.random() > 0.1)
        n = int(rng.integers(0, 50))
        np.testing.assert_array_equal(dagitim.en_buyuk_kalan(n, p), en_buyuk_kalan(n, p))


@pytest.mark.parametrize("kural", ["b", "c", "d"])
def test_rpt_yokken_kurallar_etkisiz(rpt_yok_a, kural):
    """Kurallar yalnız RPT'si gelmiş oyun option'ına dokunur: RPT'siz kolda (b), (c),
    (d) bugünkü kuralla (a) birebir aynı sevkiyatı ve satışı üretir."""
    from rpt import motor, politika

    ref, _ = rpt_yok_a
    ham, rep = _kos(politika.RPTYok(motor.lumoda("rpt")), kural)
    assert len(ref["sevkiyat"]) > 0
    pd.testing.assert_frame_equal(ham["sevkiyat"], ref["sevkiyat"])
    pd.testing.assert_frame_equal(ham["satis"], ref["satis"])
    assert rep.gelen == set() and rep.kayit_tablosu().empty


def test_rpt_varisi_depodan_anlasilir(mevcut_a):
    """Görünüm teslim gününü taşımaz; kural varışı açık siparişin düşmesinden anlar:
    her oyun RPT'si teslim gününden sonraki ilk pazartesi (teslim pazartesiyse o gün)
    "varis" olur, (c) aynı gün yeniden lansman dağıtır. Sevkiyat ilk varıştan önce
    bugünkü kuralla aynı, sonra farklı."""
    from rpt import motor, politika

    ref, _ = mevcut_a
    ham, rep = _kos(politika.Mevcut(motor.lumoda("rpt")), "c")
    w = motor.dunya("kucuk")
    opt = w.optionlar
    oyun = set(np.flatnonzero((opt["line"] == "Collection").to_numpy()
                              & opt["sezon_kodu"].isin(("AW24", "SS25")).to_numpy()))
    olay = rep.kayit_tablosu()
    varis = olay[olay["olay"] == "varis"].set_index("option")["gun"]
    beklenen = {}
    for s in ham["siparis"]:
        if s["tip"] == "rpt" and s["option"] in oyun:
            g = int(s["gerceklesen_gun"])
            pzt = g + (-g) % 7
            if pzt < GUN:
                beklenen[int(s["option"])] = pzt
    assert len(beklenen) >= 3
    assert varis.to_dict() == beklenen
    lansman = olay[olay["olay"] == "lansman"]
    assert set(lansman["option"]) == set(beklenen) and (lansman["adet"] > 0).any()
    ilk = min(beklenen.values())
    sv, sv0 = ham["sevkiyat"], ref["sevkiyat"]
    pd.testing.assert_frame_equal(sv[sv["gun"] < ilk].reset_index(drop=True),
                                  sv0[sv0["gun"] < ilk].reset_index(drop=True))
    sonra = lambda s: s[s["gun"] >= ilk].reset_index(drop=True)  # noqa: E731
    assert not sonra(sv).equals(sonra(sv0))


def test_b_kurali_stoklu_gun_hizi(mevcut_a):
    """(b) RPT'si gelmiş option'larda bugünkü kuralın sıfır hızlı kapısını aşar: varıştan
    sonra o option'ların hücrelerine giden replenishment bugünkü kuraldan farklı."""
    from rpt import motor, politika

    ref, _ = mevcut_a
    ham, rep = _kos(politika.Mevcut(motor.lumoda("rpt")), "b")
    w = motor.dunya("kucuk")
    gelen = sorted(rep.gelen)
    assert gelen
    hc = np.isin(np.asarray(w.hucre_option), gelen)

    def repl(h):
        s = h["sevkiyat"]
        s = s[(s["tip"] == "replenishment") & (s["hedef_hucre"] >= 0)]
        return s[hc[s["hedef_hucre"].to_numpy()]]["adet"].sum()

    assert repl(ham) != repl(ref)
    assert (rep.kayit_tablosu()["olay"] == "lansman").sum() == 0
