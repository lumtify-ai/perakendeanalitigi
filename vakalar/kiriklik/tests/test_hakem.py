"""`hakem`: kahin girdisi (K8 `kahin`, K22). Dünyanın gizli alanlarını okuyan tek karar-dışı modül.

Dünya `motor.dunya("kucuk")` (~5 sn), takvim oyuncak `Takvim`: yolun Lumoda koşusu gerekmez. Beklenen değerler
motorun günlük döngüsünün düz yeniden oynatımıyla (gün gün: çağrı günü ise durumu kayıttan yenile, fiyat
çarpanı, talep) bağımsız hesaplanır; `hakem` aynı sonucu başka bir yoldan (son çağrı günü) bulur."""

import ast
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from allocation import motor
from perakende_veri.v4.takvim import gun_indisi
from test_tahmin import _girdi, _og

from kiriklik import hakem, kaynak, sabitler, tahmin

IADE = 0.04
KOKU = Path(__file__).resolve().parents[1] / "kiriklik"
GUN_SIFIRI = date(2022, 7, 4)


def _tarih(gun: int) -> date:
    return GUN_SIFIRI + timedelta(days=int(gun))


@pytest.fixture(scope="module")
def w():
    return motor.dunya("kucuk")


def _plan(w):
    """Sezonluk bir option'ın (indirim_gun, çıkış) tarihleri ve fiziksel hücreleri; hücre, penceredeki
    talebi en büyük olan en çok 6 tanesi (talep sıfırsa fiyat ağırlığı sınanmaz)."""
    opt = w.optionlar
    sezonluk = np.flatnonzero(opt["sezonluk"].to_numpy(dtype=bool))
    tip = w.magazalar["tip"].astype(str).to_numpy()[np.asarray(w.hucre_magaza)]
    fiz = np.isin(tip, ("AVM", "Cadde")) & ~np.asarray(w.hucre_outlet_akisi, dtype=bool)
    for o in sezonluk:
        ind, cik = int(opt["indirim_gun"].iloc[o]), int(opt["cikis_gun"].iloc[o])
        if not (60 < ind < cik < w.lam.gun_sayisi - 1):
            continue
        hucre = np.flatnonzero((np.asarray(w.hucre_option) == o) & fiz)
        if len(hucre) < 6:
            continue
        toplam = sum(w.lam.gun(d)[hucre] for d in range(ind, min(cik, ind + 30)))
        sec = hucre[np.argsort(-toplam)[:6]]
        if toplam[np.argsort(-toplam)[:6]].min() > 0:
            return int(o), ind, cik, sec
    pytest.skip("KÜÇÜK dünyada uygun sezonluk option yok")


@pytest.fixture(scope="module")
def sahne(w):
    o, ind, cik, hucre = _plan(w)
    karar = ind - 28
    g = kaynak.KararGirdisi(sezon="AW24", karar=_tarih(karar), indirim=_tarih(ind), cikis=_tarih(cik),
                            hucre=pd.DataFrame(), satis=pd.DataFrame(), stoklu=pd.DataFrame(),
                            magaza=pd.DataFrame(), optionlar=pd.DataFrame(), takvim=pd.DataFrame(),
                            kampanya=pd.DataFrame())
    hucreler = pd.DataFrame({"magaza_id": w.magazalar["magaza_id"].astype(str).to_numpy()[np.asarray(w.hucre_magaza)[hucre]],
                             "urun_id": w.urunler["urun_id"].astype(str).to_numpy()[np.asarray(w.hucre_sku)[hucre]]})
    return {"o": o, "ind": ind, "cik": cik, "karar": karar, "hucre": hucre, "g": g, "hucreler": hucreler}


def _pazartesi(w, gun: int) -> bool:
    return pd.Timestamp(w.takvim["tarih"].iloc[gun]).dayofweek == 0


def _takvim(w, sahne, kayitlar: dict[int, float]) -> motor.Takvim:
    """`kayitlar`: gün → option'ın normal hat oranı (sıfır oran = kayıtsız gün)."""
    O = len(w.optionlar)
    md = {}
    for gun, oran in kayitlar.items():
        if oran:
            m = np.zeros((O, 3))
            m[sahne["o"], 0] = oran
            md[gun] = m
    return motor.Takvim(rpt={}, markdown=md, option_sayisi=O)


def _bekle(w, sahne, tk, iade=IADE):
    """Motorun günlük döngüsünün düz yeniden oynatımı: durum çağrı günlerinde (pazartesi ya da sezonluk
    option'ın indirim günü) kayıttan yenilenir; oran = max(durum, kampanya); talep = λ · (1 − oran)^(−ε)."""
    opt = w.optionlar
    cagri = set(int(x) for x in opt["indirim_gun"].to_numpy()[opt["sezonluk"].to_numpy(dtype=bool)])
    hucre, o = sahne["hucre"], sahne["o"]
    hm, eps = np.asarray(w.hucre_magaza)[hucre], np.asarray(w.esneklik_hucre, dtype=float)[hucre]
    liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)[np.asarray(w.hucre_sku)[hucre]]
    durum = np.zeros((len(opt), 3))
    evre = {"tam": [], "ind": []}
    for d in range(0, sahne["cik"]):
        if _pazartesi(w, d) or d in cagri:
            durum = tk.markdown_gunu(d)
        faz = ("tam" if sahne["karar"] + sabitler.VARIS_GUN <= d < sahne["ind"]
               else "ind" if sahne["ind"] <= d < sahne["cik"] else None)
        if faz is None:
            continue
        oran = np.maximum(durum[o, 0], w.kampanya_takvimi(d)[hm, o])
        talep = w.lam.gun(d)[hucre] * (1.0 - oran) ** (-eps)
        evre[faz].append((talep, liste * (1.0 - oran)))
    sonuc = {}
    for faz, gunler in evre.items():
        talep = np.array([t for t, _ in gunler])
        fiyat = np.array([f for _, f in gunler])
        sonuc[f"mu_{faz}"] = talep.sum(axis=0)
        sonuc[f"fiyat_{faz}"] = (talep * fiyat).sum(axis=0) / talep.sum(axis=0) * (1.0 - iade)
    return pd.DataFrame(sonuc)


def _hesapla(w, sahne, tk, iade=IADE):
    return hakem.kahin_girdisi(w, tk, sahne["g"], sahne["hucreler"], iade)


# ---------------------------------------------------------------- şema


@pytest.mark.veri
def test_kahin_semasi_tahminle_ayni(w, sahne):
    t = hakem.kahin_girdisi(w, _takvim(w, sahne, {}), sahne["g"], sahne["hucreler"], IADE)
    tahmin_cikti = tahmin.ufuk_talebi(_girdi(["A", "B"], [("A", 1, 10, 3)], []), _og())
    assert list(t.columns) == tahmin.KOLONLAR == list(tahmin_cikti.columns)
    assert t.dtypes.to_dict() == tahmin_cikti.dtypes.to_dict()
    assert len(t) == len(sahne["hucreler"])
    pd.testing.assert_frame_equal(t[["magaza_id", "urun_id"]], sahne["hucreler"], check_dtype=False)


@pytest.mark.veri
def test_kahin_hucre_sirasi_hucrelerin(w, sahne):
    ters = sahne["hucreler"].iloc[::-1].reset_index(drop=True)
    t = hakem.kahin_girdisi(w, _takvim(w, sahne, {}), sahne["g"], ters, IADE)
    a = hakem.kahin_girdisi(w, _takvim(w, sahne, {}), sahne["g"], sahne["hucreler"], IADE)
    pd.testing.assert_frame_equal(t, a.iloc[::-1].reset_index(drop=True))


# ---------------------------------------------------------------- fiyat yolu kayıttan


@pytest.mark.veri
def test_kahin_fiyat_yolu_kayittan(w, sahne):
    """İndirim gününde %40, iki hafta sonra bir pazartesi kayıtsız (= sıfıra dönüş): `fiyat_ind` iki rejimin
    talep ağırlıklı ortalaması, düz yeniden oynatımla eşit; `fiyat_tam` indirimsiz."""
    ind = sahne["ind"]
    geri = next(d for d in range(ind + 14, ind + 28) if _pazartesi(w, d))
    tk = _takvim(w, sahne, {ind: 0.4, geri: 0.0})
    t = _hesapla(w, sahne, tk)
    b = _bekle(w, sahne, tk)
    for k in ("mu_tam", "mu_ind", "fiyat_tam", "fiyat_ind"):
        np.testing.assert_allclose(t[k].to_numpy(), b[k].to_numpy(), rtol=1e-9, err_msg=k)
    liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)[np.asarray(w.hucre_sku)[sahne["hucre"]]]
    assert (t["fiyat_ind"] < liste * (1 - IADE) - 1e-9).all()          # indirimli günler var
    assert (t["fiyat_ind"] > liste * 0.6 * (1 - IADE) + 1e-9).all()    # ama bütün evre değil


@pytest.mark.veri
def test_kahin_kalici_yuzde_kirk_liste_carpi_altmis(w, sahne):
    """%40 indirim günden çıkışa kadar sürerse (kampanya %40'ı aşmayan hücrelerde) `fiyat_ind` = liste × 0,6 ×
    (1 − iade) ve `mu_ind` = Σ λ · 0,6^(−ε)."""
    hucre, ind, cik = sahne["hucre"], sahne["ind"], sahne["cik"]
    hm = np.asarray(w.hucre_magaza)[hucre]
    kamp = np.max([w.kampanya_takvimi(d)[hm, sahne["o"]] for d in range(ind, cik)], axis=0)
    ok = kamp <= 0.4
    if not ok.any():
        pytest.skip("seçili hücrelerin hepsinde %40 üstü kampanya var")
    # indirim gününden sonraki pazartesilerin hepsinde aynı kayıt: durum sürekli %40
    tk = _takvim(w, sahne, {d: 0.4 for d in range(ind, cik) if d == ind or _pazartesi(w, d)})
    t = _hesapla(w, sahne, tk)
    liste = w.urunler["liste_fiyati"].to_numpy(dtype=float)[np.asarray(w.hucre_sku)[hucre]]
    np.testing.assert_allclose(t["fiyat_ind"].to_numpy()[ok], (liste * 0.6 * (1 - IADE))[ok], rtol=1e-12)
    eps = np.asarray(w.esneklik_hucre, dtype=float)[hucre]
    lam = sum(w.lam.gun(d)[hucre] for d in range(ind, cik))
    np.testing.assert_allclose(t["mu_ind"].to_numpy()[ok], (lam * 0.6 ** (-eps))[ok], rtol=1e-9)


@pytest.mark.veri
def test_kahin_kayitsiz_takvim_tam_fiyat(w, sahne):
    """Markdown kaydı yoksa fiyat liste (kampanya yoksa) ve iade payıyla; iade parametresi doğrudan çarpar."""
    tk = _takvim(w, sahne, {})
    t0, t1 = _hesapla(w, sahne, tk, 0.0), _hesapla(w, sahne, tk, 0.10)
    np.testing.assert_allclose(t1["fiyat_tam"].to_numpy(), t0["fiyat_tam"].to_numpy() * 0.9, rtol=1e-12)
    np.testing.assert_allclose(t1["mu_tam"].to_numpy(), t0["mu_tam"].to_numpy())   # iade talebi değiştirmez
    b = _bekle(w, sahne, tk, 0.0)
    np.testing.assert_allclose(t0["fiyat_ind"].to_numpy(), b["fiyat_ind"].to_numpy(), rtol=1e-9)


@pytest.mark.veri
def test_kahin_kosudan_takvim_kurulur(w, sahne, monkeypatch):
    """`lumoda_kosusu` `Takvim` değilse `motor.takvim(kosu, w)` ile kurulur."""
    tk = _takvim(w, sahne, {sahne["ind"]: 0.4})
    cagrilar = []
    monkeypatch.setattr(motor, "takvim", lambda kosu, w=None: cagrilar.append((kosu, w)) or tk)
    sahte = object()
    t = hakem.kahin_girdisi(w, sahte, sahne["g"], sahne["hucreler"], IADE)
    assert cagrilar == [(sahte, w)]
    pd.testing.assert_frame_equal(t, _hesapla(w, sahne, tk))


# ---------------------------------------------------------------- girdi doğrulama


@pytest.mark.veri
def test_kahin_dunyada_olmayan_hucre_hata(w, sahne):
    h = sahne["hucreler"].copy()
    h.loc[0, "urun_id"] = "YOK-1"
    with pytest.raises(ValueError, match="hücresi olmayan"):
        hakem.kahin_girdisi(w, _takvim(w, sahne, {}), sahne["g"], h, IADE)


@pytest.mark.veri
def test_kahin_online_hucre_hata(w, sahne):
    onl = np.flatnonzero((w.magazalar["tip"].astype(str).to_numpy()[np.asarray(w.hucre_magaza)] == "Online")
                         & (np.asarray(w.hucre_option) == sahne["o"]))
    assert len(onl)
    h = pd.DataFrame({"magaza_id": w.magazalar["magaza_id"].astype(str).to_numpy()[np.asarray(w.hucre_magaza)[onl[:1]]],
                      "urun_id": w.urunler["urun_id"].astype(str).to_numpy()[np.asarray(w.hucre_sku)[onl[:1]]]})
    with pytest.raises(ValueError, match="fiziksel"):
        hakem.kahin_girdisi(w, _takvim(w, sahne, {}), sahne["g"], h, IADE)


@pytest.mark.veri
def test_kahin_dunya_gun_araligi_disinda_hata(w, sahne):
    g = kaynak.KararGirdisi(**{**sahne["g"].__dict__, "cikis": date(2031, 1, 1)})
    with pytest.raises(ValueError, match="gün aralığı"):
        hakem.kahin_girdisi(w, _takvim(w, sahne, {}), g, sahne["hucreler"], IADE)


def test_kahin_bos_hucreler_bos_cikti():
    """Hücre yoksa dünyaya hiç dokunmadan boş şema (w kullanılmaz)."""
    g = kaynak.KararGirdisi(sezon="AW24", karar=date(2024, 12, 9), indirim=date(2025, 1, 2), cikis=date(2025, 2, 24),
                            hucre=pd.DataFrame(), satis=pd.DataFrame(), stoklu=pd.DataFrame(),
                            magaza=pd.DataFrame(), optionlar=pd.DataFrame(), takvim=pd.DataFrame(),
                            kampanya=pd.DataFrame())
    t = hakem.kahin_girdisi(None, None, g, pd.DataFrame({"magaza_id": [], "urun_id": []}), IADE)
    assert list(t.columns) == tahmin.KOLONLAR and len(t) == 0


# ---------------------------------------------------------------- ölçüm sınırı


def test_karar_modulleri_hakemi_ice_aktarmaz():
    """Gizli gerçeğe yalnız ölçüm dokunur: karar modülleri `hakem`i içe aktarmaz (Görev 8 AST kilidi bunu
    bütün karar modülleri için kalıcılaştırır)."""
    karar_modulleri = ("kural", "model", "tahmin", "uygunluk", "kaynak", "olcu", "plan", "sabitler")
    for ad in karar_modulleri:
        yol = KOKU / f"{ad}.py"
        if not yol.exists():
            continue        # henüz yazılmamış (model: Görev 7)
        for dugum in ast.walk(ast.parse(yol.read_text(encoding="utf-8"))):
            if isinstance(dugum, ast.Import):
                adlar = [a.name for a in dugum.names]
            elif isinstance(dugum, ast.ImportFrom):
                adlar = [dugum.module or ""] + [f"{dugum.module}.{a.name}" for a in dugum.names]
            else:
                continue
            assert not any(a == "hakem" or a.endswith(".hakem") or a.startswith("kiriklik.hakem")
                           for a in adlar), f"{ad}.py hakem'i içe aktarıyor"
