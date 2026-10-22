"""`beden_paket.kosucu`: dünya kopyası, aynı mal, doğrulama kolu, önbellek anahtarı, yollar.

KÜÇÜK dünyada tam pencere koşuları (~20 sn): İlk Sevkiyat'ın `motor.kos` Lumoda'sı (önbelleksiz,
modülde bir kez), vakanın doğrulama kolu, 7'li bir desen kolu (aynı mal) ve 12'li bir desenin
dönüştürülmemiş `ns`'le kırpılan kolu (kırpmanın pakete duyarlı ölçümü). Vakanın önbelleği modülün
geçici dizininde. `veri` işaretli testler İlk Sevkiyat'ın TAM önbelleğini salt okur (koşmaz).
"""

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from allocation import kaynak as al_kaynak
from allocation import motor
from allocation import olcutler as al_olcutler
from allocation import oyun as al_oyun

import beden_paket
from beden_paket import kosucu, politika, sabitler, simulasyon

P1 = np.array([[1, 1, 2, 2, 1]])
P12 = np.array([[1, 2, 4, 3, 2]])


# ---------------------------------------------------------------------------
# Oyuncak
# ---------------------------------------------------------------------------


def test_ns_donustur_12():
    """Option başına toplam ⌊Σ adet ÷ 12 + ½⌋ paket, mağazalara adet payıyla en büyük kalan
    (eşitlikte magaza_id sırası); payı 0'a yuvarlanan mağaza 0 paket alır ve sayılır."""
    giden = {("O1", "M1"): 70, ("O1", "M2"): 35, ("O1", "M3"): 7, ("O1", "M4"): 7,
             ("O2", "M2"): 14, ("O2", "M1"): 14, ("O3", "M1"): 0}
    ns = kosucu.ns_donustur(giden, 12)
    # O1: 119 adet → ⌊9,92 + ½⌋ = 10 paket; hedef 5,88 / 2,94 / 0,59 / 0,59; taban 5+2+0+0 = 7,
    # kalan 3 en büyük kesirlere: M2 (0,94), M1 (0,88), M3 (0,59; M4'le eşit, magaza_id sırası)
    assert ns[("O1", "M1")] == 6 and ns[("O1", "M2")] == 3 and ns[("O1", "M3")] == 1
    assert ("O1", "M4") not in ns
    # O2: 28 adet → 2 paket, 1 + 1; O3 adetsiz
    assert ns[("O2", "M1")] == 1 and ns[("O2", "M2")] == 1
    assert ("O3", "M1") not in ns and all(v > 0 for v in ns.values())
    oz = kosucu.donusum_ozeti(giden, ns, 12)
    assert oz["lumoda_adet"] == 147 and oz["kol_adet"] == 12 * 12
    assert oz["fark_adet"] == 144 - 147
    assert oz["sifir_hucre"] == 1 and oz["hucre"] == 6
    # option toplamı korunur: |12 × Σ paket − Σ adet| ≤ 6 (O1: 120 − 119 = 1, O2: 24 − 28 = −4)
    assert oz["option_en_buyuk_fark"] == 4 and oz["option_fark_siniri"] == 6
    az = kosucu.ns_donustur({("O1", "M1"): 21, ("O1", "M2"): 7, ("O1", "M3"): 7}, 12)
    assert az == {("O1", "M1"): 2, ("O1", "M2"): 1}                   # 35 → 3 paket; M3 0
    assert kosucu.donusum_ozeti({("O1", "M1"): 21, ("O1", "M2"): 7, ("O1", "M3"): 7}, az, 12)[
        "sifir_hucre"] == 1
    with pytest.raises(ValueError):
        kosucu.ns_donustur(giden, 0)
    # aşağı yuvarlama (14'lü, R22): ⌊Σ ÷ a⌋; O1 119 adet → 8 paket (112 ≤ 119), O2 28 → 2
    asagi = kosucu.ns_donustur(giden, 14, "asagi")
    tops = pd.Series(asagi).groupby(level=0).sum()
    assert tops.to_dict() == {"O1": 8, "O2": 2}
    oz14 = kosucu.donusum_ozeti(giden, asagi, 14, "asagi")
    assert oz14["option_en_buyuk_fark"] == 7 and oz14["option_fark_siniri"] == 13     # 119 − 112 ≤ 13
    assert sum(kosucu.ns_donustur(giden, 14).values()) == 9 + 2                      # yakın: ⌊8,5 + ½⌋ = 9
    with pytest.raises(ValueError):
        kosucu.ns_donustur(giden, 14, "yukari")


def _tablolar(sevk_satirlari, paket=None):
    urun = pd.DataFrame({"urun_id": [f"U{b}" for b in range(1, 6)] + ["V1"],
                         "option_id": ["O1"] * 5 + ["O2"], "beden_sira": [1, 2, 3, 4, 5, 1]})
    paket = paket if paket is not None else pd.DataFrame(
        {"paket_id": ["PKT03"] * 5 + ["PKT05"] + ["PKD00-PKT03"] * 5, "beden_seti": ["K"] * 5 + ["S"] + ["K"] * 5,
         "beden_sira": [1, 2, 3, 4, 5, 1] * 1 + [1, 2, 3, 4, 5], "adet": [1, 2, 2, 1, 1, 6, 1, 1, 2, 2, 1]})
    s = pd.DataFrame(sevk_satirlari, columns=["tarih", "hedef", "urun_id", "adet", "tip", "paket_id"])
    s["tarih"] = pd.to_datetime(s["tarih"])
    for c in ("hedef", "urun_id", "tip", "paket_id"):
        s[c] = s[c].astype("category")
    return {"sevkiyat": s, "urun": urun, "paket": paket}


def test_lumoda_giden_oyuncak():
    """Giden paket = beden adedi ÷ paketin o bedendeki içeriği (sevkin `paket_id`'si); replenishment
    sayılmaz; bedenler farklı sayı verirse ya da adet içeriğin katı değilse hata."""
    rows = [("2025-02-07", "M1", f"U{b}", 3 * a, "ilk_dagitim", "PKT03") for b, a in zip(range(1, 6), (1, 2, 2, 1, 1))]
    rows += [("2025-02-07", "M2", f"U{b}", 2 * a, "ilk_dagitim", "PKD00-PKT03")
             for b, a in zip(range(1, 6), (1, 1, 2, 2, 1))]
    rows += [("2025-02-07", "M1", "V1", 12, "ilk_dagitim", "PKT05"),
             ("2025-02-17", "M1", "U4", 5, "replenishment", "PKT03")]
    t = _tablolar(rows)
    assert kosucu.lumoda_giden(t) == {("O1", "M1"): 3, ("O1", "M2"): 2, ("O2", "M1"): 2}
    assert kosucu.giden_adet(t) == {("O1", "M1"): 21, ("O1", "M2"): 14, ("O2", "M1"): 12}
    tablo = kosucu.ilk_dagitim_tablosu(t)
    assert set(tablo["paket_id"]) == {"PKT03", "PKD00-PKT03", "PKT05"}
    bozuk = list(rows)
    bozuk[0] = ("2025-02-07", "M1", "U1", 4, "ilk_dagitim", "PKT03")          # 4 paket, ötekiler 3
    with pytest.raises(RuntimeError):
        kosucu.lumoda_giden(_tablolar(bozuk))
    bozuk[0] = ("2025-02-07", "M1", "U2", 5, "ilk_dagitim", "PKT03")          # 5 ÷ 2 değil
    with pytest.raises(RuntimeError):
        kosucu.lumoda_giden(_tablolar(bozuk))


def _paket_ici_ice_aktarmalar(yol: Path) -> set[str]:
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.ImportFrom) and (d.module or "").startswith("beden_paket"):
            adlar |= {a.name for a in d.names} if d.module == "beden_paket" else {d.module.split(".")[1]}
        elif isinstance(d, ast.Import):
            adlar |= {a.name.split(".")[1] for a in d.names if a.name.startswith("beden_paket.")}
    return adlar


def test_vaka_kodu_kosuyu_etkileyenleri_kapsar():
    """Anahtarın vaka kodu (`SIMULASYON_MODULLERI`) `simulasyon`'un paket içi içe aktarma kapanışını
    kapsar (simülasyonu etkileyen vaka kodu anahtarda); ölçüm ve ızgara (kosucu, oyun) dışarıda."""
    paket = Path(beden_paket.__file__).resolve().parent
    kapanis, sira = set(), ["simulasyon"]
    while sira:
        m = sira.pop()
        if m in kapanis:
            continue
        kapanis.add(m)
        sira += sorted(_paket_ici_ice_aktarmalar(paket / f"{m}.py"))
    assert kapanis | {"__init__"} == set(simulasyon.SIMULASYON_MODULLERI)
    assert not {"kosucu", "oyun", "egri", "paket_tasarim", "hakem"} & set(simulasyon.SIMULASYON_MODULLERI)
    assert set(simulasyon.vaka_kod_dosyalari()) == {f"beden_paket/{m}.py" for m in simulasyon.SIMULASYON_MODULLERI}


def test_her_modul_simulasyon_siniflandirilmis():
    """Paketin her modülü `SIMULASYON_MODULLERI` ya da `SIMULASYON_DISI`'ndadır, ikisinde birden değil
    (İlk Sevkiyat `KOSU_MODULLERI` / `KOSU_DISI` kalıbı)."""
    paket = Path(beden_paket.__file__).resolve().parent
    var = {y.stem for y in paket.glob("*.py")}
    ic, dis = set(simulasyon.SIMULASYON_MODULLERI), set(simulasyon.SIMULASYON_DISI)
    assert not ic & dis
    assert var <= ic | dis, sorted(var - ic - dis)


def test_olcum_degisikligi_simulasyonu_bozmaz(tmp_path, monkeypatch):
    """Ölçüm ve ızgara kodu (kosucu, oyun, eğri, tasarım) değişince simülasyonun vaka kodu özeti ve
    koşu anahtarı aynı kalır (yalnız ölçüm yeniden yapılır, Ruling R14); politika değişince değişir."""
    paket = Path(beden_paket.__file__).resolve().parent
    kopya = tmp_path / "beden_paket"
    kopya.mkdir()
    for y in paket.glob("*.py"):
        (kopya / y.name).write_bytes(y.read_bytes())
    once = simulasyon.vaka_kod_ozeti(kopya)
    assert once == simulasyon.vaka_kod_ozeti()
    w = motor.dunya("kucuk")
    m = w.magazalar["magaza_id"].astype(str).tolist()[:3]
    h0 = simulasyon.hazirla("p1", P1, {a: 0 for a in m}, None, olcek="kucuk")
    for ad in ("kosucu", "oyun", "egri", "paket_tasarim", "hakem"):
        y = kopya / f"{ad}.py"
        if y.exists():
            y.write_text(y.read_text(encoding="utf-8") + "\n# ölçüm değişikliği\n", encoding="utf-8")
    assert simulasyon.vaka_kod_ozeti(kopya) == once
    monkeypatch.setattr(simulasyon, "PAKET_KOKU", kopya)
    assert simulasyon.hazirla("p1", P1, {a: 0 for a in m}, None, olcek="kucuk").anahtar == h0.anahtar
    y = kopya / "politika.py"
    y.write_text(y.read_text(encoding="utf-8") + "\n# politika değişikliği\n", encoding="utf-8")
    assert simulasyon.vaka_kod_ozeti(kopya) != once
    assert simulasyon.hazirla("p1", P1, {a: 0 for a in m}, None, olcek="kucuk").anahtar != h0.anahtar


# ---------------------------------------------------------------------------
# Anahtar (koşmadan; KÜÇÜK dünya)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def w_kucuk():
    return motor.dunya("kucuk")


@pytest.fixture(scope="module")
def fiziksel(w_kucuk):
    m = w_kucuk.magazalar
    return m.loc[~m["tip"].astype(str).isin(["Online", "Outlet"]), "magaza_id"].astype(str).tolist()


def test_anahtar_degisir(w_kucuk, fiziksel):
    """Desen, atama, ns, yol değişince anahtar değişir; aynı girdi (sözlük sırası, Series / dict)
    aynı anahtarı verir; içerik vaka kodunu ve İlk Sevkiyat'ın kod özetini taşır."""
    atama = {m: 0 for m in fiziksel}
    oyun = sorted(_oyun_ids(w_kucuk))
    ns = {(oyun[0], fiziksel[0]): 2, ("OYUN-DISI", fiziksel[0]): 5}
    h = kosucu.hazirla("p1", P1, atama, ns, olcek="kucuk")
    ayni = kosucu.hazirla("p1", P1.tolist(), pd.Series(dict(reversed(atama.items()))), dict(ns),
                          olcek="KUCUK")
    assert h.anahtar == ayni.anahtar
    assert h.icerik["vaka"] == simulasyon.vaka_kod_ozeti()
    assert h.icerik["kod"] == motor.kod_ozeti()
    assert h.icerik["olcek"] == "kucuk" and h.icerik["talep_tohumu"] is None
    iki = np.vstack([P1, [[1, 2, 2, 1, 1]]])
    farkli = {
        "desen": kosucu.hazirla("p1", [[1, 2, 2, 1, 1]], atama, ns, olcek="kucuk"),
        "atama": kosucu.hazirla("p1", iki, {**atama, fiziksel[0]: 1}, ns, olcek="kucuk"),
        "ns": kosucu.hazirla("p1", P1, atama, {(oyun[0], fiziksel[0]): 3}, olcek="kucuk"),
        "ns_yok": kosucu.hazirla("p1", P1, atama, None, olcek="kucuk"),
        "yol": kosucu.hazirla("p1", P1, atama, ns, yol=2, olcek="kucuk"),
        "ad": kosucu.hazirla("p1b", P1, atama, ns, olcek="kucuk"),
    }
    anahtarlar = {k: v.anahtar for k, v in farkli.items()}
    assert h.anahtar not in anahtarlar.values() and len(set(anahtarlar.values())) == len(anahtarlar)
    atama2 = kosucu.hazirla("p1", iki, atama, ns, olcek="kucuk")
    assert atama2.anahtar != farkli["atama"].anahtar                     # yalnız atama farklı
    # oyun dışı option'ın ns satırı politikaya girmez (Lumoda'nın kuralı), anahtarı da değiştirmez
    assert kosucu.hazirla("p1", P1, atama, {(oyun[0], fiziksel[0]): 2}, olcek="kucuk").anahtar == h.anahtar
    assert farkli["yol"].icerik["talep_tohumu"] == al_oyun.talep_tohumu(2)
    assert farkli["yol"].icerik["parametreler"]["yol"] == 2
    with pytest.raises(ValueError):
        kosucu.hazirla("p1", P1, {"YOK": 0}, ns, olcek="kucuk")              # dünyada olmayan mağaza
    with pytest.raises(ValueError):
        kosucu.hazirla("p1", P1, atama, {(oyun[0], "YOK"): 1}, olcek="kucuk")
    with pytest.raises(ValueError):
        kosucu.kos("p1", P1, atama, ns, olcek="kucuk", onbellek=motor.KOSU_DIZINI)   # salt okunur


def test_dunya_kopyasi_yayimlananı_bozmaz(w_kucuk):
    """Kopya yalnız `paketler`'de ayrılır (öteki alanlar aynı nesne); yayımlanan dünya değişmez."""
    from perakende_veri.v4.politika import paket_tablosu

    n = len(w_kucuk.paketler)
    w2, harita = kosucu.dunya_kopyasi(w_kucuk, P1)
    assert len(w_kucuk.paketler) == n and len(w2.paketler) > n
    assert w2.cesit is w_kucuk.cesit and w2.lam is w_kucuk.lam
    assert paket_tablosu(w2.paketler)[1] == paket_tablosu(w_kucuk.paketler)[1]   # standart ilk kalır
    assert all(i < len(w2.paketler["paket_id"].unique()) for i in harita.values())


# ---------------------------------------------------------------------------
# KÜÇÜK koşular
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def onbellek(tmp_path_factory):
    return tmp_path_factory.mktemp("beden_paket_kosular")


@pytest.fixture(scope="module")
def lumoda_kucuk():
    """İlk Sevkiyat'ın Lumoda koşusu (`motor.kos`, KÜÇÜK, tam pencere, önbelleksiz)."""
    return motor.kos(ad="lumoda", parametreler={}, onbellek=None, olcek="kucuk")


@pytest.fixture(scope="module")
def dogrulama(onbellek):
    return kosucu.kos("dogrulama", [sabitler.LUMODA_PAKET], None, None, olcek="kucuk", onbellek=onbellek,
                      tembel=False)


def _oyun_ids(w):
    return set(w.optionlar["option_id"].astype(str).to_numpy()[al_kaynak.oyun_optionlari(w, "SS25")])


def test_dogrulama_kucuk(lumoda_kucuk, dogrulama, w_kucuk):
    """Vakanın koşucusu standart paket ve Lumoda'nın kendi ilk dağıtımıyla İlk Sevkiyat'ın Lumoda'sını
    birebir üretir: bütün ölçütler, gizli gerçek, hareket tabloları ve Lumoda kayıtları aynı (yalnız
    `paket` tablosu eklenen satırları, `sevkiyat.paket_id` kategorileri eklenen kimlikleri taşır)."""
    h = al_kaynak.harita_kur(w_kucuk)
    beklenen = al_olcutler.hesapla(lumoda_kucuk, w_kucuk, h)
    bulunan = kosucu.olc(dogrulama)
    assert {a: bulunan[a] for a in beklenen} == beklenen
    assert beklenen["kirpilan_adet"] > 0                  # Lumoda'nın paketini motor kırpıyor
    assert bulunan["paket_tipi"] == 1                     # 1-2-2-1-1, her beş bedenli sete
    assert bulunan["istenen_adet"] - bulunan["ilk_dagitim_adet"] == bulunan["kirpilan_adet"]
    pd.testing.assert_frame_equal(dogrulama.gercek, lumoda_kucuk.gercek)
    for ad, df in lumoda_kucuk.tablolar.items():
        d = dogrulama.tablolar[ad]
        if ad == "paket":
            pd.testing.assert_frame_equal(d.iloc[:len(df)].reset_index(drop=True), df)
            assert d.iloc[len(df):]["paket_id"].str.startswith("PKD").all()
            continue
        if ad == "sevkiyat":
            assert list(d["paket_id"].cat.categories[:len(df["paket_id"].cat.categories)]) == list(
                df["paket_id"].cat.categories)
            d, df = d.assign(paket_id=d["paket_id"].astype(str)), df.assign(paket_id=df["paket_id"].astype(str))
        pd.testing.assert_frame_equal(d, df, obj=ad)
    for ad in ("ilk_dagitim", "rpt", "markdown"):
        pd.testing.assert_frame_equal(dogrulama.kayitlar[ad], lumoda_kucuk.kayitlar[ad], obj=ad)
    assert dogrulama.meta["turler"] == {"paket_secimi": "beden_paket.politika.PaketSecimi"}


def test_ilk4_beden_kucuk(dogrulama, w_kucuk):
    """İlk 4 hafta beden ölçütleri (Ruling R19): pencere `bulunabilirlik_ilk4`'ünki, [b_o, min(b_o + 28,
    c_o)); yöntem İlk Sevkiyat'ın `_beden`'i: pencere sonsuz olunca tam sezon ölçütleri birebir çıkar."""
    h = al_kaynak.harita_kur(w_kucuk)
    tam = al_olcutler.hesapla(dogrulama, w_kucuk, h)
    sonsuz = kosucu.ilk4_beden_olcutleri(dogrulama, w_kucuk, gun=10**5)
    assert sonsuz["kirik_cift_pay_yuzde_ilk4"] == tam["kirik_cift_pay_yuzde"]
    assert sonsuz["beden_kayip_payi_ilk4"] == tam["beden_kayip_payi"]
    assert sonsuz["stoklu_cift_gun_ilk4"] == tam["stoklu_cift_gun"]
    o = kosucu.olc(dogrulama)
    assert al_olcutler.ILK4_GUN == kosucu.ILK4_GUN == 28
    assert 0 < o["stoklu_cift_gun_ilk4"] < o["stoklu_cift_gun"]
    assert o == o | kosucu.ilk4_beden_olcutleri(dogrulama, w_kucuk)
    assert 0 <= o["kirik_cift_pay_yuzde_ilk4"] <= 100 and 0 <= o["beden_kayip_payi_ilk4"] <= 100


def test_lumoda_ns_yoldan(dogrulama, lumoda_kucuk, onbellek):
    """Bir yolun Lumoda `ns`'i: İlk Sevkiyat önbelleği KÜÇÜK'te yok, vakanın doğrulama kolu (aynı
    önbellekten okunur) ve İlk Sevkiyat'ın Lumoda'sıyla aynı."""
    assert kosucu.allocation_lumoda(0, "kucuk") is None
    ns, kaynak = kosucu.lumoda_ns(0, olcek="kucuk", onbellek=onbellek)
    assert kaynak.startswith("vaka:dogrulama_") and ns == kosucu.lumoda_giden(lumoda_kucuk)
    assert ns == kosucu.lumoda_giden(dogrulama)


def test_ayni_mal_kucuk(lumoda_kucuk, w_kucuk, fiziksel, onbellek):
    """Tasarlanmış desenle (1-1-2-2-1, bütün fiziksel mağazalar) her oyun (option, mağaza) çiftine
    Lumoda'nın giden paketi gider: giden adet Lumoda'nın giden adedine eşit, kırpma 0; beş bedenli
    option'larda paket yeni desen, aksesuar standart; yeniden çağrı önbellekten aynı anahtarla."""
    ns = kosucu.lumoda_giden(lumoda_kucuk)
    oyun = _oyun_ids(w_kucuk)
    k = kosucu.kos("p1", P1, {m: 0 for m in fiziksel}, ns, olcek="kucuk", onbellek=onbellek, tembel=False)
    assert not k.onbellekten
    lum = {a: v for a, v in kosucu.giden_adet(lumoda_kucuk).items() if a[0] in oyun}
    kol = {a: v for a, v in kosucu.giden_adet(k).items() if a[0] in oyun}
    assert kol == lum and sum(kol.values()) > 0
    assert kosucu.korunum(k, lum) == {"hucre": len(lum), "fark_hucre": 0, "fark_adet": 0, "net_fark_adet": 0}
    o = kosucu.olc(k)
    assert o["kirpilan_adet"] == 0 and o["kirpilan_hucre"] == 0 and o["kirpilan_option"] == 0
    assert o["paket_tipi"] == 1                           # tek desen (1-1-2-2-1), set başına ayrı kimlik
    t = kosucu.ilk_dagitim_tablosu(k)
    t = t[t["option_id"].isin(oyun)]
    seti = w_kucuk.optionlar.set_index(w_kucuk.optionlar["option_id"].astype(str))["beden_seti"].astype(str)
    aks = t["option_id"].map(seti) == "Standart"
    assert t.loc[~aks, "paket_id"].str.startswith("PKD00-").all() and (~aks).any()
    assert t.loc[aks, "paket_id"].str.startswith("PKT").all()
    # beden adetleri desenin katı: 1-1-2-2-1
    s = k.tablo("sevkiyat", ["hedef", "urun_id", "adet", "tip", "paket_id"])
    s = s[(s["tip"].astype(str) == "ilk_dagitim") & s["paket_id"].astype(str).str.startswith("PKD")]
    b = s["urun_id"].astype(str).map(w_kucuk.urunler.set_index(w_kucuk.urunler["urun_id"].astype(str))["beden_sira"])
    oran = s.assign(b=b.to_numpy()).groupby("b")["adet"].sum()
    assert (oran / oran.loc[1]).tolist() == [1.0, 1.0, 2.0, 2.0, 1.0]
    # önbellekten
    ikinci = kosucu.kos("p1", P1, {m: 0 for m in fiziksel}, ns, olcek="kucuk", onbellek=onbellek)
    assert ikinci.onbellekten and ikinci.meta["anahtar"] == k.meta["anahtar"]
    assert set(ikinci.kayitlar) == {"ilk_dagitim", "rpt", "markdown", "paket_secimi"}


def test_kirpma_pakete_duyarli_kucuk(lumoda_kucuk, w_kucuk, fiziksel, onbellek):
    """12'li desene 7'li `ns` (dönüştürülmemiş): motor kırpar; kırpılan adet istenen − giden paket ×
    seçilen paketin adedi (12), İlk Sevkiyat'ın 7'yi varsayan sayısı değil."""
    ns = kosucu.lumoda_giden(lumoda_kucuk)
    k = kosucu.kos("p12_kirp", P12, {m: 0 for m in fiziksel}, ns, olcek="kucuk", onbellek=onbellek)
    kirp = motor.kirpma_tablosu(k, w_kucuk)
    kirp = kirp[kirp["option_id"].isin(_oyun_ids(w_kucuk))]
    assert len(kirp)
    seti = w_kucuk.optionlar.set_index(w_kucuk.optionlar["option_id"].astype(str))["beden_seti"].astype(str)
    boy = np.where(kirp["option_id"].map(seti) == "Standart", 6, 12)
    beklenen = int(((kirp["istenen_paket"] - kirp["giden_paket"]).to_numpy() * boy).sum())
    o = kosucu.olc(k)
    assert o["kirpilan_adet"] == beklenen and o["kirpilan_hucre"] == len(kirp)
    standart_varsayan = al_olcutler.hesapla(k, w_kucuk, al_kaynak.harita_kur(w_kucuk))["kirpilan_adet"]
    assert standart_varsayan != beklenen                      # İlk Sevkiyat'ın 7'yi varsayan sayısı
    assert o["istenen_adet"] - o["ilk_dagitim_adet"] == beklenen


def test_dogrula_onbellek_yoksa_basarisiz(dogrulama, monkeypatch, capsys):
    """`dogrula` İlk Sevkiyat'ın önbellekli Lumoda koşusu yoksa kıyası yapılmış saymaz (çıkış 1), ölçütler
    birebir olsa bile; önbellek varsa ve aynıysa 0."""
    o = {"bulunabilirlik": 0.5, "kirpilan_adet": 3.0}
    monkeypatch.setattr(kosucu, "kos_dogrulama", lambda yol, olcek: dogrulama)
    monkeypatch.setattr(kosucu, "olc", lambda k: dict(o))
    monkeypatch.setattr(kosucu, "_referans", lambda yol: dict(o))
    monkeypatch.setattr(kosucu, "allocation_lumoda", lambda yol, olcek: None)
    assert kosucu.dogrula(0, "tam") == 1
    assert "giden paket kıyaslanamadı" in capsys.readouterr().out
    class Kayit:                                          # İlk Sevkiyat önbelleği yerine (dizin adı)
        dizin = Path("lumoda_x")
        tablo = staticmethod(dogrulama.tablo)

    monkeypatch.setattr(kosucu, "allocation_lumoda", lambda yol, olcek: Kayit())
    assert kosucu.dogrula(0, "tam") == 0


# ---------------------------------------------------------------------------
# Gerçek veri: İlk Sevkiyat önbelleği (salt okunur, TAM koşu yok)
# ---------------------------------------------------------------------------


def _al_kosu_dizini(ad: str):
    return [d for d in motor.KOSU_DIZINI.glob(f"{ad}_*") if d.is_dir() and "yaziliyor" not in d.name]


@pytest.mark.veri
def test_allocation_onbellegi_degismedi():
    """İlk Sevkiyat'ın `lumoda` ve `y<p>_lumoda` koşuları bu .venv'de aynı anahtarı verir ve önbellekten
    salt okunur açılır (vakanın kodu İlk Sevkiyat'ın anahtarına girmez)."""
    if not _al_kosu_dizini("lumoda"):
        pytest.skip("İlk Sevkiyat önbelleği yok")
    once = sorted(p.name for p in motor.KOSU_DIZINI.iterdir())
    assert kosucu.allocation_anahtari(0) == al_oyun.MEVCUT_ANAHTARLAR["lumoda"]
    k = kosucu.allocation_lumoda(0)
    assert k is not None and k.meta["anahtar"] == al_oyun.MEVCUT_ANAHTARLAR["lumoda"]
    yollar = json.loads((motor.KOSU_DIZINI.parent / "yollar.json").read_text(encoding="utf-8"))["yollar"]
    for p in range(1, sabitler.YOL_SAYISI):
        assert kosucu.allocation_anahtari(p) == yollar[str(p)]["kosular"]["lumoda"]["anahtar"]
        assert kosucu.allocation_lumoda(p) is not None
    assert sorted(p.name for p in motor.KOSU_DIZINI.iterdir()) == once


@pytest.mark.veri
def test_lumoda_giden_ilk_sevkiyat_onbellegi():
    """İlk Sevkiyat'ın önbellekli `lumoda`'sından giden paket: oyun option'larında adet toplamı İlk
    Sevkiyat ölçütünün `ilk_dagitim_adet`'i; 7'li paket katı; makul büyüklük (210 option)."""
    k = kosucu.allocation_lumoda(0)
    if k is None:
        pytest.skip("İlk Sevkiyat önbelleği yok")
    olc = json.loads((motor.KOSU_DIZINI.parent / "oyun.json").read_text(encoding="utf-8"))[
        "kosular"]["lumoda"]["olcutler"]
    u = k.tablo("urun", ["option_id", "line", "sezon_kodu"])
    oyun = set(u.loc[(u["line"].astype(str) == "Collection") & (u["sezon_kodu"].astype(str) == "SS25"),
                     "option_id"].astype(str))
    ns = kosucu.lumoda_giden(k)
    adet = kosucu.giden_adet(k)
    assert set(ns) == set(adet)
    assert sum(v for (o, _), v in adet.items() if o in oyun) == olc["ilk_dagitim_adet"]
    assert len(oyun) == 210 and len({o for o, _ in ns if o in oyun}) == 210
    assert len({m for o, m in ns if o in oyun}) == 69          # vakanın kapsamı: SS25 karar günü 69 aday
    print(f"\nİlk Sevkiyat lumoda, oyun: (option, mağaza) {sum(a[0] in oyun for a in ns)}, "
          f"giden paket {sum(v for a, v in ns.items() if a[0] in oyun)}")


@pytest.mark.veri
def test_olc_ilk_sevkiyat_lumoda():
    """Vakanın ölçümü (`olc`; pakete duyarlı kırpma dahil) İlk Sevkiyat'ın önbellekli TAM `lumoda`
    koşusunda İlk Sevkiyat'ın kayıtlı ölçütlerini birebir verir (koşu yok; ~1 dk, ~3 GB): standart
    7'li pakette kırpılan adet İlk Sevkiyat'ınkiyle aynı, istenen − giden = kırpılan."""
    k = kosucu.allocation_lumoda(0)
    if k is None:
        pytest.skip("İlk Sevkiyat önbelleği yok")
    ref = json.loads((motor.KOSU_DIZINI.parent / "oyun.json").read_text(encoding="utf-8"))[
        "kosular"]["lumoda"]["olcutler"]
    o = kosucu.olc(k)
    assert {a: o[a] for a in ref} == ref
    assert o["istenen_adet"] - o["ilk_dagitim_adet"] == o["kirpilan_adet"] > 0
    assert o["paket_tipi"] == 1                           # 1-2-2-1-1 (aksesuar desen sayılmaz)
