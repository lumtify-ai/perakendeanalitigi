"""`kiriklik.politika` ve `kiriklik.simulasyon`: yuva (`KirikTransfer`), plan → motor satırı, anahtar, kod özeti,
KÜÇÜK dünyada korunum, karar veritabanı, yayımlanan v4 ile TAM eşdeğerlik.

Hızlı testler motor koşmaz (KÜÇÜK dünya yalnız kurulur, ~3 sn). `veri` işaretli KÜÇÜK testler motoru AW24 karar
gününden 8 gün sonrasına kadar koşar (`GUN_SAYISI`; yolun Lumoda'sı ve oyuncak planlı koşu, geçici önbellekte,
~10 sn'şer). `test_esdegerlik_tam` `veri` ve `yavas` işaretlidir (TAM koşu ~4 dk, ~8 GB): varsayılanda atlanır,
`-m "veri and yavas"` ile koşulur (`conftest.py`).
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from allocation import motor
from perakende_veri.v4.politika import LumodaElleTransfer, Transferler

import kiriklik
from kiriklik import kaynak, plan as plan_modulu, sabitler, simulasyon
from kiriklik.plan import Plan
from kiriklik.politika import KirikTransfer, TransferPlani

KUCUK = {"olcek": "kucuk"}
SEZON = "AW24"
PAKET = Path(kiriklik.__file__).resolve().parent
KARAR_GUNU = simulasyon.karar_gun(SEZON)
GUN_SAYISI = KARAR_GUNU + 8


# ---------------------------------------------------------------------------
# Yuva: KirikTransfer (motor koşmaz)
# ---------------------------------------------------------------------------


def _tr(*satirlar) -> Transferler:
    """(kaynak, hedef, sku, adet) satırlarından `Transferler`."""
    a = np.array(satirlar, dtype=np.int64).reshape(-1, 4)
    return Transferler(a[:, 0], a[:, 1], a[:, 2], a[:, 3])


def _satirlar(t: Transferler) -> list[tuple]:
    return list(zip(t.kaynak.tolist(), t.hedef.tolist(), t.sku.tolist(), t.adet.tolist(), strict=True))


class _Temel:
    """Lumoda'nın elle transferinin yerine geçen sahte: her gün aynı iki satır; çağrı günlerini tutar."""

    def __init__(self):
        self.cagrilar = []

    def __call__(self, g):
        self.cagrilar.append(int(g.gun))
        return _tr((7, 8, 9, 1), (7, 6, 5, 2))


def _plan_satirlari() -> TransferPlani:
    return TransferPlani(kaynak=[1, 1], hedef=[2, 3], sku=[10, 11], adet=[4, 5], kimlik="p" * 64)


def _g(gun: int):
    return SimpleNamespace(gun=gun)


def test_kirik_transfer_yalniz_karar_gunu():
    """Karar gününden başka her günde yalnız `temel(g)` (aynı satırlar); karar gününde planın satırları da var."""
    temel = _Temel()
    kol = KirikTransfer(temel, _plan_satirlari(), karar_gun=100)
    for gun in (0, 99, 101, 107, 1000):
        assert _satirlar(kol(_g(gun))) == [(7, 8, 9, 1), (7, 6, 5, 2)], gun
    karar = _satirlar(kol(_g(100)))
    assert len(karar) == 4 and (1, 2, 10, 4) in karar and (1, 3, 11, 5) in karar
    assert temel.cagrilar == [0, 99, 101, 107, 1000, 100]            # temel her gün çağrılır (aynı çekiliş)


def test_plan_satirlari_once():
    """Karar gününde sıra: önce plan, sonra `temel` (motor aynı kaynağın stoğunu sırayla tüketir); tür `Transferler`,
    dizi türü int64."""
    kol = KirikTransfer(_Temel(), _plan_satirlari(), karar_gun=100)
    t = kol(_g(100))
    assert isinstance(t, Transferler)
    assert _satirlar(t) == [(1, 2, 10, 4), (1, 3, 11, 5), (7, 8, 9, 1), (7, 6, 5, 2)]
    assert all(a.dtype == np.int64 for a in (t.kaynak, t.hedef, t.sku, t.adet))
    # numpy tamsayı karar günü ve gün de eşleşir
    assert len(KirikTransfer(_Temel(), _plan_satirlari(), np.int64(100))(_g(np.int64(100))).kaynak) == 4


def test_bos_plan_temeli_degistirmez():
    kol = KirikTransfer(_Temel(), TransferPlani([], [], [], [], kimlik="b" * 64), karar_gun=100)
    assert _satirlar(kol(_g(100))) == [(7, 8, 9, 1), (7, 6, 5, 2)]


def test_parametreler_plan_kimligi():
    """`parametreler()` yalnız planın kimliği ve karar günü; `temel` kimlikte türüyle görünür."""
    kol = KirikTransfer(LumodaElleTransfer(), _plan_satirlari(), karar_gun=100)
    assert kol.parametreler() == {"plan": "p" * 64, "karar_gun": 100}
    k = motor.politika_kimligi(kol)
    assert k["parametreler"] == {"plan": "p" * 64, "karar_gun": 100}
    assert k["temel"]["tur"].endswith("LumodaElleTransfer")
    farkli = KirikTransfer(LumodaElleTransfer(), _plan_satirlari(), karar_gun=101)
    assert motor.politika_kimligi(farkli) != k


def test_transfer_plani_yapisi():
    """int64, salt okunur kopya; uzunluklar eşit; kimlik boş olamaz."""
    kaynak_ = np.array([1, 2], dtype=np.int32)
    p = TransferPlani(kaynak_, [3, 4], [5, 6], [7, 8], kimlik="k")
    assert all(a.dtype == np.int64 and not a.flags.writeable for a in (p.kaynak, p.hedef, p.sku, p.adet))
    kaynak_[0] = 99
    assert p.kaynak.tolist() == [1, 2]                                 # savunma kopyası
    assert len(p) == 2
    with pytest.raises(ValueError, match="aynı uzunlukta"):
        TransferPlani([1], [2, 3], [4], [5], kimlik="k")
    with pytest.raises(ValueError, match="kimlik"):
        TransferPlani([], [], [], [], kimlik="")


# ---------------------------------------------------------------------------
# Plan → motor satırı
# ---------------------------------------------------------------------------


def _hareketler(*satirlar) -> pd.DataFrame:
    """(option_id, urun_id, beden_sira, verici, alici, adet) satırlarından `Plan.hareketler`."""
    return pd.DataFrame(satirlar, columns=plan_modulu.KOLONLAR)


def _oyuncak_dunya() -> SimpleNamespace:
    return SimpleNamespace(
        magazalar=pd.DataFrame({"magaza_id": ["M001", "M002", "M003", "ONL"]}),
        urunler=pd.DataFrame({"urun_id": ["U1", "U2", "U3"]}))


def test_transfer_plani_esler_ve_sirayi_sabitler():
    """magaza_id → `w.magazalar` satırı, urun_id → `w.urunler` satırı; kimlik planınki; satırlar planın kimlik
    sırasında (option_id, alici, verici, beden_sira), girdi sırasından bağımsız."""
    w = _oyuncak_dunya()
    satirlar = [("O1", "U3", 3, "M001", "M003", 2), ("O1", "U1", 1, "M002", "M001", 1),
                ("O1", "U2", 2, "M002", "M003", 4), ("O2", "U1", 1, "M003", "M002", 7)]
    p = Plan(kol="kural", sezon=SEZON, hareketler=_hareketler(*satirlar))
    tp = simulasyon.transfer_plani(p, w)
    assert tp.kimlik == p.kimlik
    # sıra: (option_id, alici, verici, beden_sira)
    assert _satirlar(Transferler(tp.kaynak, tp.hedef, tp.sku, tp.adet)) == [
        (1, 0, 0, 1), (0, 2, 2, 2), (1, 2, 1, 4), (2, 1, 0, 7)]
    ters = Plan(kol="kural", sezon=SEZON, hareketler=_hareketler(*satirlar[::-1]))
    assert ters.kimlik == p.kimlik
    tt = simulasyon.transfer_plani(ters, w)
    for a in ("kaynak", "hedef", "sku", "adet"):
        np.testing.assert_array_equal(getattr(tt, a), getattr(tp, a))


def test_transfer_plani_bos_plan():
    tp = simulasyon.transfer_plani(plan_modulu.bos("kural", SEZON, {}), _oyuncak_dunya())
    assert len(tp) == 0 and tp.kimlik


def test_transfer_plani_bilinmeyen_kimlik():
    w = _oyuncak_dunya()
    for satir, ad in ((("O1", "U1", 1, "M999", "M001", 1), "verici"), (("O1", "U1", 1, "M001", "M999", 1), "alici"),
                      (("O1", "U9", 1, "M001", "M002", 1), "urun_id")):
        p = Plan(kol="kural", sezon=SEZON, hareketler=_hareketler(satir))
        with pytest.raises(ValueError, match=ad):
            simulasyon.transfer_plani(p, w)


# ---------------------------------------------------------------------------
# Kod özeti, karar günü, anahtar (KÜÇÜK dünya yalnız kurulur)
# ---------------------------------------------------------------------------


def test_karar_gun():
    from perakende_veri.v4.takvim import gun_indisi
    assert simulasyon.karar_gun("AW24") == gun_indisi(sabitler.KARAR["AW24"])
    assert simulasyon.karar_gun("SS25") == gun_indisi(sabitler.KARAR["SS25"]) > simulasyon.karar_gun("AW24")
    with pytest.raises(ValueError, match="AW25"):
        simulasyon.karar_gun("AW25")


def test_kod_ozeti_listeleri(tmp_path):
    """Her modül `SIMULASYON_MODULLERI` ya da `KOSU_DISI`'ndadır, ikisinde birden değil; vaka özeti yalnız simülasyon
    modüllerinin baytına bağlıdır: karar ve ölçüm modülü (`kural`, `model`, `hakem`) değişince aynı kalır, `politika`
    ya da `simulasyon` değişince değişir."""
    var = {y.stem for y in PAKET.glob("*.py")}
    ic, dis = set(simulasyon.SIMULASYON_MODULLERI), set(simulasyon.KOSU_DISI)
    assert simulasyon.SIMULASYON_MODULLERI == ("__init__", "politika", "simulasyon")
    assert not ic & dis and var <= ic | dis, sorted(var - ic - dis)
    assert ic <= var
    dosyalar = simulasyon.vaka_kod_dosyalari()
    assert {f"kiriklik/{m}.py" for m in ic} <= set(dosyalar)
    assert not any(f"kiriklik/{m}.py" in dosyalar for m in dis)

    kopya = tmp_path / "kiriklik"
    kopya.mkdir()
    for y in PAKET.glob("*.py"):
        (kopya / y.name).write_bytes(y.read_bytes())
    once = simulasyon.vaka_kod_ozeti(kopya)
    assert once == simulasyon.vaka_kod_ozeti()
    for ad in ("kural", "model", "hakem", "tahmin", "plan"):
        y = kopya / f"{ad}.py"
        y.write_bytes(y.read_bytes() + b"\n# karar\n")
    assert simulasyon.vaka_kod_ozeti(kopya) == once
    for ad in ("politika", "simulasyon", "__init__"):
        y = kopya / f"{ad}.py"
        eski = y.read_bytes()
        y.write_bytes(eski + b"\n# simulasyon\n")
        assert simulasyon.vaka_kod_ozeti(kopya) != once, ad
        y.write_bytes(eski)
    # satır sonları LF'e çevrilir
    y = kopya / "politika.py"
    y.write_bytes(y.read_bytes().replace(b"\n", b"\r\n"))
    assert simulasyon.vaka_kod_ozeti(kopya) == once


@pytest.fixture(scope="module")
def w():
    return motor.dunya("kucuk")


def _oyuncak_plan_kucuk(w, satir=2) -> TransferPlani:
    """KÜÇÜK dünyada geçerli, motor koşmadan kurulan plan: AW24 Collection SKU'sunun hücresi olan iki fiziksel mağaza
    arasında 1'er adet (hücre: `w.hucre_magaza`/`w.hucre_sku`)."""
    urun = w.urunler
    sku = np.flatnonzero((urun["sezon_kodu"] == SEZON).to_numpy() & (urun["line"] == sabitler.LINE).to_numpy())
    fiz = np.flatnonzero(w.magazalar["tip"].isin(sabitler.FIZIKSEL_TIPLER).to_numpy())
    hm, hs = np.asarray(w.hucre_magaza), np.asarray(w.hucre_sku)
    k, h, s = [], [], []
    for u in sku:
        m = np.intersect1d(hm[hs == u], fiz)
        if len(m) >= 2:
            k.append(m[0]), h.append(m[1]), s.append(u)
        if len(k) == satir:
            break
    assert len(k) == satir
    return TransferPlani(k, h, s, [1] * satir, kimlik="oyuncak-" + "0" * 56)


def _hazirla(w, plan=None, kimlik=None, karar=KARAR_GUNU, sezon=SEZON, kol="kural", **ek):
    tp = _oyuncak_plan_kucuk(w) if plan is None else plan
    if kimlik is not None:
        tp = TransferPlani(tp.kaynak, tp.hedef, tp.sku, tp.adet, kimlik=kimlik)
    tk = motor.Takvim(rpt={1036: {0: 10}}, markdown={}, option_sayisi=len(w.optionlar)).sabitle()
    return simulasyon.hazirla("k", 0, plan=tp, takvim=ek.pop("takvim", tk), karar_gun=karar,
                              parametreler={"sezon": sezon, "kol": kol}, **KUCUK, **ek)


def test_anahtar_bilesenleri(w):
    """Anahtar planın kimliğini, karar gününü, takvimin kimliğini, `temel`'in türünü, kolun adını, yolu ve vaka
    özetini taşır; yuvalar elle_transfer, rpt, markdown."""
    h = _hazirla(w)
    assert sorted(h.politikalar) == ["elle_transfer", "markdown", "rpt"]
    assert h.icerik["turler"]["elle_transfer"].endswith("KirikTransfer")
    et = h.icerik["politikalar"]["elle_transfer"]
    assert et["parametreler"] == {"plan": "oyuncak-" + "0" * 56, "karar_gun": KARAR_GUNU}
    assert et["temel"]["tur"].endswith("LumodaElleTransfer")
    tk = h.icerik["politikalar"]["rpt"]["temel"]["parametreler"]
    assert tk["takvim"] == h.politikalar["rpt"].temel.takvim.kimlik and tk["optionlar"] == list(range(len(w.optionlar)))
    assert h.icerik["politikalar"]["markdown"]["temel"]["parametreler"]["takvim"] == tk["takvim"]
    assert h.icerik["parametreler"] == {"sezon": SEZON, "kol": "kural", "yol": 0}
    assert h.icerik["vaka"] == simulasyon.vaka_kod_ozeti()
    assert h.talep_tohumu is None
    y1 = simulasyon.hazirla("k", 1, plan=h.politikalar["elle_transfer"].plan, takvim=h.politikalar["rpt"].temel.takvim,
                            karar_gun=KARAR_GUNU, parametreler={"sezon": SEZON, "kol": "kural"}, **KUCUK)
    assert y1.talep_tohumu == 20261020 and y1.anahtar != h.anahtar and y1.icerik["parametreler"]["yol"] == 1


def test_lumoda_hazirlik_yuvasiz(w):
    h = simulasyon.hazirla("lumoda", 0, parametreler={}, **KUCUK)
    assert h.politikalar == {} and h.icerik["turler"] == {} and "politikalar" not in h.icerik
    assert h.icerik["vaka"] == simulasyon.vaka_kod_ozeti()
    assert simulasyon.lumoda_adi(0) == "lumoda" and simulasyon.lumoda_adi(3) == "y3_lumoda"
    assert simulasyon.hazirla("lumoda", 2, parametreler={}, **KUCUK).anahtar != h.anahtar


def test_anahtar_plan_degisince_degisir(w):
    """Planın kimliği, karar günü (sezon), takvimin içeriği, yol, kolun adı ve gün sayısı anahtarı değiştirir; aynı
    girdi aynı anahtarı verir."""
    temel = _hazirla(w)
    assert _hazirla(w).anahtar == temel.anahtar
    tk2 = motor.Takvim(rpt={1036: {0: 11}}, markdown={}, option_sayisi=len(w.optionlar)).sabitle()
    farkli = [_hazirla(w, kimlik="baska-" + "1" * 58), _hazirla(w, takvim=tk2), _hazirla(w, kol="opt"),
              _hazirla(w, sezon="SS25", karar=simulasyon.karar_gun("SS25")), _hazirla(w, gun_sayisi=GUN_SAYISI)]
    assert len({temel.anahtar} | {x.anahtar for x in farkli}) == 6
    # kimlik aynı, satırlar farklı: anahtar aynı (kimlik içeriğin sözü; satırlar kimlikten türetilir)
    bos = TransferPlani([], [], [], [], kimlik="oyuncak-" + "0" * 56)
    assert _hazirla(w, plan=bos).anahtar == temel.anahtar


def test_anahtar_karar_modulu_degisince_degismez(w, monkeypatch, tmp_path):
    """Karar modülü (`kural.py` baytı) değişince vaka özeti ve anahtar aynı kalır: karar değişikliği planın
    kimliğiyle girer. Simülasyon modülü (`politika.py`) değişince anahtar değişir."""
    kopya = tmp_path / "kiriklik"
    kopya.mkdir()
    for y in PAKET.glob("*.py"):
        (kopya / y.name).write_bytes(y.read_bytes())
    temel = _hazirla(w)
    gercek_ozet = simulasyon.vaka_kod_ozeti
    monkeypatch.setattr(simulasyon, "vaka_kod_ozeti", lambda kok=None: gercek_ozet(kopya))
    assert _hazirla(w).anahtar == temel.anahtar                          # kopya özdeş
    (kopya / "kural.py").write_bytes((kopya / "kural.py").read_bytes() + b"\n# degisti\n")
    assert _hazirla(w).anahtar == temel.anahtar                          # karar modülü anahtarda yok
    (kopya / "politika.py").write_bytes((kopya / "politika.py").read_bytes() + b"\n# degisti\n")
    assert _hazirla(w).anahtar != temel.anahtar


def test_hazirla_dogrulamalari(w):
    tp = _oyuncak_plan_kucuk(w)
    tk = motor.Takvim(rpt={}, markdown={}, option_sayisi=len(w.optionlar)).sabitle()
    par = {"sezon": SEZON, "kol": "kural"}

    def h(**ek):
        arg = {"plan": tp, "takvim": tk, "karar_gun": KARAR_GUNU, "parametreler": par, **KUCUK, **ek}
        return simulasyon.hazirla("k", **arg)

    h()
    with pytest.raises(ValueError, match="takvim"):
        h(takvim=None)
    with pytest.raises(ValueError, match="karar_gun"):
        h(karar_gun=None)
    with pytest.raises(ValueError, match="sezon"):
        h(parametreler={"kol": "kural"})
    with pytest.raises(ValueError, match="sezon"):
        h(parametreler={"sezon": "AW25", "kol": "kural"})
    with pytest.raises(ValueError, match="kol"):
        h(parametreler={"sezon": SEZON})
    with pytest.raises(ValueError, match="karar gününe"):
        h(karar_gun=KARAR_GUNU + 7)
    with pytest.raises(ValueError, match="karar gününü"):
        h(gun_sayisi=KARAR_GUNU)
    with pytest.raises(ValueError, match="option sayısı"):
        h(takvim=motor.Takvim(rpt={}, markdown={}, option_sayisi=3))
    with pytest.raises(ValueError, match="dünya dışı"):
        h(plan=TransferPlani([0], [10_000], [0], [1], kimlik="k"))
    with pytest.raises(ValueError, match="pozitif"):
        h(plan=TransferPlani([0], [1], [0], [0], kimlik="k"))
    with pytest.raises(ValueError, match="yol"):
        h(parametreler={**par, "yol": 2})
    with pytest.raises(ValueError, match="ölçek"):
        simulasyon.hazirla("k", 0, "orta", parametreler={})
    with pytest.raises(ValueError, match="koşu adı"):
        simulasyon.hazirla("a/b", 0, parametreler={}, **KUCUK)
    with pytest.raises(ValueError, match="Lumoda"):
        simulasyon.hazirla("lumoda", 0, takvim=tk, parametreler={}, **KUCUK)
    with pytest.raises(ValueError, match="Lumoda koşusu"):
        simulasyon.takvim(motor.Kosu(tablolar={}, gercek=pd.DataFrame(), meta={"turler": {"rpt": "x"}}))


def test_onbellek_reddi(tmp_path):
    """İlk Sevkiyat'ın çıktı dizinine (ve altına) yazılmaz; koşmadan reddedilir."""
    for yer in (motor.KOSU_DIZINI, motor.KOSU_DIZINI.parent / "kiriklik_denemesi"):
        with pytest.raises(ValueError, match="salt okunur"):
            simulasyon.kos("lumoda", parametreler={}, onbellek=yer, **KUCUK)
        assert not (motor.KOSU_DIZINI.parent / "kiriklik_denemesi").exists()
    with pytest.raises(ValueError, match="tembel"):
        simulasyon.kos("lumoda", parametreler={}, onbellek=None, **KUCUK)


# ---------------------------------------------------------------------------
# KÜÇÜK koşular (AW24 karar gününden 8 gün sonrasına)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def onbellek(tmp_path_factory):
    return tmp_path_factory.mktemp("kosular")


@pytest.fixture(scope="module")
def lumoda(onbellek):
    return simulasyon.kos("lumoda", parametreler={}, onbellek=onbellek, gun_sayisi=GUN_SAYISI, **KUCUK)


@pytest.fixture(scope="module")
def takvim(lumoda):
    return simulasyon.takvim(lumoda)


def _kucuk_plan(lumoda, w, satir=2) -> tuple[TransferPlani, list[tuple]]:
    """Oyuncak plan: karar günü stok fotoğrafında en az 2 adedi olan (fiziksel mağaza, AW24 Collection SKU)
    hücrelerinden 1'er adet, aynı SKU'nun hücresi olan başka bir fiziksel mağazaya. Dönüş (motor satırları,
    `Plan.hareketler` satırları)."""
    karar = pd.Timestamp(sabitler.KARAR[SEZON])
    magaza, urun, stok = lumoda.tablo("magaza"), lumoda.tablo("urun"), lumoda.tablo("stok")
    fiz = set(magaza.loc[magaza["tip"].isin(sabitler.FIZIKSEL_TIPLER), "magaza_id"].astype(str))
    sku = set(urun.loc[(urun["sezon_kodu"] == SEZON) & (urun["line"] == sabitler.LINE), "urun_id"].astype(str))
    st = stok[stok["tarih"] == karar].astype({"magaza_id": str, "urun_id": str})
    st = st[st["magaza_id"].isin(fiz) & st["urun_id"].isin(sku)].sort_values(["urun_id", "magaza_id"])
    satirlar = []
    for r in st[st["adet"] >= 2].itertuples():
        alici = sorted(set(st.loc[st["urun_id"] == r.urun_id, "magaza_id"]) - {r.magaza_id})
        if alici:
            opt = str(urun.loc[urun["urun_id"].astype(str) == r.urun_id, "option_id"].iloc[0])
            bsira = int(urun.loc[urun["urun_id"].astype(str) == r.urun_id, "beden_sira"].iloc[0])
            satirlar.append((opt, r.urun_id, bsira, r.magaza_id, alici[0], 1))
        if len(satirlar) == satir:
            break
    assert len(satirlar) == satir, "karar günü fotoğrafında yeterli hücre yok"
    return simulasyon.transfer_plani(Plan(kol="oyuncak", sezon=SEZON, hareketler=_hareketler(*satirlar)),
                                     motor.dunya("kucuk")), satirlar


@pytest.fixture(scope="module")
def oyuncak(lumoda, w):
    return _kucuk_plan(lumoda, w)


@pytest.fixture(scope="module")
def kol(lumoda, takvim, oyuncak, onbellek):
    return simulasyon.kos("kural_AW24", plan=oyuncak[0], takvim=takvim, karar_gun=KARAR_GUNU,
                          parametreler={"sezon": SEZON, "kol": "oyuncak"}, onbellek=onbellek, gun_sayisi=GUN_SAYISI,
                          **KUCUK)


def _ayni_kosu(a, b, kayitlar=True):
    assert sorted(a.meta["tablolar"]) == sorted(b.meta["tablolar"])
    for ad in a.meta["tablolar"]:
        pd.testing.assert_frame_equal(a.tablo(ad), b.tablo(ad), obj=ad)
    pd.testing.assert_frame_equal(a.tablo("gercek"), b.tablo("gercek"), obj="gercek")
    if kayitlar:
        assert sorted(a.kayitlar) == sorted(b.kayitlar)
        for ad in a.kayitlar:
            pd.testing.assert_frame_equal(a.kayitlar[ad], b.kayitlar[ad], obj=ad)


@pytest.mark.veri
def test_esdegerlik_kucuk(lumoda, onbellek):
    """Plansız koşu: yuva enjekte edilmez; İlk Sevkiyat'ın `motor.kos` Lumoda'sıyla tablo tablo, gizli gerçek ve
    kayıtlar birebir; anahtar vaka özetini taşır; ikinci çağrı önbellekten aynı kaydı okur."""
    assert lumoda.meta["turler"] == {} and lumoda.meta["vaka"] == simulasyon.vaka_kod_ozeti()
    assert sorted(lumoda.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    print(f"\nKÜÇÜK Lumoda ({GUN_SAYISI} gün): motor {lumoda.meta['motor_sn']} sn, toplam {lumoda.meta['sure_sn']} sn")
    referans = motor.kos(ad="lumoda", parametreler={}, onbellek=None, gun_sayisi=GUN_SAYISI, **KUCUK)
    _ayni_kosu(lumoda, referans)
    tekrar = simulasyon.kos("lumoda", parametreler={}, onbellek=onbellek, gun_sayisi=GUN_SAYISI, **KUCUK)
    assert tekrar.onbellekten and tekrar.meta["anahtar"] == lumoda.meta["anahtar"]


@pytest.mark.veri
def test_kucuk_kol_kosusu_korunum(lumoda, kol, oyuncak, takvim):
    """KÜÇÜK yol 0, AW24, oyuncak plan: karar gününe kadar `satis`, `stok`, `sevkiyat` yolun Lumoda koşusuyla
    birebir; RPT ve fiyat kaydı, `siparis` ve `fiyat` bütün koşu boyunca birebir (aynı mal); planın satırları karar
    gününün `sevkiyat`'ında `elle_transfer` olarak görünür ve koşu Lumoda'dan gerçekten ayrışır."""
    _plan, satirlar = oyuncak
    karar = pd.Timestamp(sabitler.KARAR[SEZON])
    assert sorted(kol.meta["turler"]) == ["elle_transfer", "markdown", "rpt"]
    assert kol.meta["politikalar"]["rpt"]["temel"]["parametreler"]["takvim"] == takvim.kimlik
    print(f"\nKÜÇÜK plan koşusu: motor {kol.meta['motor_sn']} sn, toplam {kol.meta['sure_sn']} sn")

    for ad in ("satis", "stok", "sevkiyat"):
        a, b = kol.tablo(ad), lumoda.tablo(ad)
        a, b = a[a["tarih"] < karar].reset_index(drop=True), b[b["tarih"] < karar].reset_index(drop=True)
        assert len(a) > 0
        pd.testing.assert_frame_equal(a, b, obj=ad)
    # karar gününden önceki gizli gerçek de aynı (talep, ikame, kayıp)
    ga, gb = kol.tablo("gercek"), lumoda.tablo("gercek")
    pd.testing.assert_frame_equal(ga[ga["tarih"] < karar].reset_index(drop=True),
                                  gb[gb["tarih"] < karar].reset_index(drop=True), obj="gercek")
    # aynı mal: sipariş ve fiyat bütün koşu boyunca, RPT ve markdown kaydı Lumoda'nınkiyle aynı
    for ad in ("siparis", "fiyat"):
        pd.testing.assert_frame_equal(kol.tablo(ad), lumoda.tablo(ad), obj=ad)
    for ad in ("rpt", "markdown", "ilk_dagitim"):
        pd.testing.assert_frame_equal(kol.kayitlar[ad], lumoda.kayitlar[ad], obj=f"kayit {ad}")
    assert len(takvim.rpt) > 0

    # planın satırı karar gününün sevkiyat'ında elle_transfer olarak
    sv = kol.tablo("sevkiyat")
    gun = sv[(sv["tarih"] == karar) & (sv["tip"].astype(str) == "elle_transfer")].astype(
        {"kaynak": str, "hedef": str, "urun_id": str})
    for _opt, urun, _b, verici, alici, adet in satirlar:
        var = gun[(gun["kaynak"] == verici) & (gun["hedef"] == alici) & (gun["urun_id"] == urun)]
        assert int(var["adet"].sum()) == adet, (verici, alici, urun)
    lum_sv = lumoda.tablo("sevkiyat")
    lum_gun = lum_sv[(lum_sv["tarih"] == karar) & (lum_sv["tip"].astype(str) == "elle_transfer")]
    assert len(gun) == len(lum_gun) + len(satirlar)                       # Lumoda'nın elle transferleri de yerinde
    assert not kol.tablo("sevkiyat").equals(lumoda.tablo("sevkiyat"))


@pytest.mark.veri
def test_karar_veritabani_kucuk(lumoda):
    """Yol p > 0: KÜÇÜK Lumoda koşusunun yayımlanan biçimi `%TEMP%`'te geçici DuckDB'ye yazılır, `karar_girdisi` onu
    okur, çıkışta dosya silinir; kimlik Lumoda koşusunun anahtarıdır. Yanlış yol ve Lumoda olmayan koşu reddedilir."""
    yol = 3
    lum = SimpleNamespace(meta={**lumoda.meta, "parametreler": {**lumoda.meta["parametreler"], "yol": yol}},
                          tablo=lumoda.tablo)
    with simulasyon.karar_veritabani(lum, yol) as (con, kimlik):
        assert kimlik == lumoda.meta["anahtar"]
        dosya = Path(con.execute("select path from duckdb_databases() where not internal and path is not null")
                     .fetchone()[0])
        assert dosya.exists() and Path(dosya).parent.name.startswith("kiriklik_yol_")
        tablolar = {r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()}
        assert {"stok", "depo_stok", "urun", "siparis", "magaza", "magaza_olay", "sezon", "satis", "takvim",
                "kampanya", "paket"} <= tablolar and len(tablolar) == 18
        g = kaynak.karar_girdisi(con, SEZON)
        assert g.karar == sabitler.KARAR[SEZON] and len(g.hucre) > 0 and g.hucre["stok"].sum() > 0
        assert len(g.satis) > 0 and len(g.stoklu) > 0 and g.magaza["uygun"].any()
    assert not dosya.exists() and not dosya.parent.exists()
    with pytest.raises(ValueError, match="yol"):
        with simulasyon.karar_veritabani(lum, yol + 1):
            pass
    with pytest.raises(ValueError, match="Lumoda koşusu"):
        with simulasyon.karar_veritabani(SimpleNamespace(meta={"turler": {"rpt": "x"}}), 1):
            pass


@pytest.mark.veri
def test_karar_veritabani_yayimlanan_yol_sifir(veri_con):
    """Yol 0: yayımlanan v4 dosyası, salt okunur; kimlik None (öğrenme dosya kimliğini kendisi bulur)."""
    with simulasyon.karar_veritabani(None, 0) as (con, kimlik):
        assert kimlik is None
        assert con.execute("select count(*) from satis").fetchone()[0] > 0
        with pytest.raises(Exception, match="read-only|read only|Cannot execute"):
            con.execute("create table x as select 1")


# ---------------------------------------------------------------------------
# TAM (denetleyici koşar)
# ---------------------------------------------------------------------------


@pytest.mark.veri
@pytest.mark.yavas
def test_esdegerlik_tam():
    """Yol 0 Lumoda (plansız) → yayımlanan biçimi yayımlanan v4: 18 tablonun satır sayıları ve Σ satış adedi DuckDB'deki
    yayımlanan veriyle birebir (bir TAM koşu, ~4 dk, ~8 GB; önbellekte)."""
    if not kaynak.VERITABANI.exists():
        pytest.skip("yayımlanan v4 yok")
    k = simulasyon.kos(simulasyon.lumoda_adi(0), parametreler={})
    print(f"\nkoşu: {'önbellekten' if k.onbellekten else 'yeni'}; motor {k.meta.get('motor_sn')} sn, "
          f"toplam {k.meta.get('sure_sn')} sn; tepe bellek {k.meta.get('tepe_bellek_gb')} GB")
    assert k.meta["turler"] == {}
    t = simulasyon.yayimlanan(k)
    assert len(t) == 18
    con = kaynak.baglan()
    try:
        for ad in sorted(t):
            assert len(t[ad]) == con.execute(f"select count(*) from {ad}").fetchone()[0], ad
        assert int(t["satis"]["adet"].sum()) == int(con.execute("select sum(adet) from satis").fetchone()[0])
    finally:
        con.close()
    assert sorted(k.kayitlar) == ["ilk_dagitim", "markdown", "rpt"]
    assert len(simulasyon.takvim(k).rpt) > 0
