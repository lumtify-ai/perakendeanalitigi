"""`beden_paket.oyun`: kol ve koşu adları, ızgara bütçesi, yolun kendi tabloları, depo, option başına
aynı mal, kahinin yalnız ölçümde kalması, KÜÇÜK uçtan uca ızgara (ölçüm önbelleği, aynı koşu iki adla).

KÜÇÜK dünyada tam pencere koşuları (~15 sn): yol 0 ve yol 1'in doğrulama kolu, p2 ve p3_12; önbellek ve
çıktı modülün geçici dizininde. `veri` işaretli test TAM yol 0'ın tasarımlarını koşmadan sınar (İlk
Sevkiyat'ın önbellekli `lumoda`'sı doğrulama kolunun yerine; ikisi birebir aynıdır).
"""

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from allocation import motor
from allocation import oyun as al_oyun

import beden_paket
from beden_paket import hakem, kosucu, oyun, paket_tasarim, sabitler, simulasyon


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    kok = tmp_path_factory.mktemp("beden_paket_oyun")
    return oyun.Ortam(olcek="kucuk", onbellek=kok / "kosular", cikti=kok / "cikti")


@pytest.fixture(scope="module")
def G0(ortam):
    return oyun.YolGirdisi(0, ortam)


@pytest.fixture(scope="module")
def G1(ortam):
    return oyun.YolGirdisi(1, ortam)


# ---------------------------------------------------------------------------
# Adlar ve bütçe
# ---------------------------------------------------------------------------


def test_kol_adlari():
    """Kollar R10'un seti; koşu adları tekil, dosya adına uygun, yol p'de `y<p>_` önekli; doğrulama kolunun
    adı `simulasyon.dogrulama_adi` (kosucu dogrulama'nın koşusu)."""
    assert set(oyun.KOLLAR) == {"dogrulama", "p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham"}
    assert oyun.YOL0_KOLLARI == ("dogrulama", "p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham")
    assert oyun.YOL_KOLLARI == ("dogrulama", "p1", "p2", "p3_12")
    k = oyun.KOLLAR
    assert (k["p1"].K, k["p2"].K, k["p1_12"].K, k["p3_12"].K, k["pm_12"].K, k["p2_ham"].K) == (1, 2, 1, 3, "magaza", 2)
    assert {a for a, v in k.items() if v.adet == 12} == {"p1_12", "p3_12", "pm_12"}
    assert k["p2_ham"].egri == "ham" and k["dogrulama"].K is None
    adlar = [oyun.kosu_adi(y, kol) for y, kol in oyun.izgara_listesi()]
    assert len(adlar) == len(set(adlar))
    assert all(motor._AD_DESENI.match(a) for a in adlar)
    assert oyun.kosu_adi(0, "p2") == "p2" and oyun.kosu_adi(3, "p3_12") == "y3_p3_12"
    assert oyun.kosu_adi(2, "dogrulama") == simulasyon.dogrulama_adi(2) == "y2_dogrulama"
    assert set(oyun.KOSULMAYAN) == {"p3", "p4", "pm", "pk"} and not set(oyun.KOSULMAYAN) & set(oyun.KOLLAR)
    assert "R15" in oyun.KOSULMAYAN["pk"] and "M027" in oyun.KOSULMAYAN["pk"]
    with pytest.raises(KeyError):
        oyun.kosu_adi(0, "p3")


def test_izgara_butcesi(G0, ortam):
    """Yol 0'da 7 koşu (doğrulama `kosucu dogrulama`'nın koşusu: aynı ad, aynı anahtar, önbellekten), yollar
    1–4'te 4'er = 16; bloklar ana 6, ablasyon 1, yol 16."""
    hepsi = oyun.izgara_listesi()
    assert len(hepsi) == 23
    assert [k for y, k in hepsi if y == 0] == list(oyun.YOL0_KOLLARI)
    assert sorted({y for y, _ in hepsi if y}) == [1, 2, 3, 4]
    assert all([k for y, k in hepsi if y == p] == list(oyun.YOL_KOLLARI) for p in (1, 2, 3, 4))
    assert [len(oyun.izgara_listesi(b)) for b in oyun.BLOK_SIRASI] == [6, 1, 16]
    assert oyun.izgara_listesi("ana") + oyun.izgara_listesi("ablasyon") == [s for s in hepsi if s[0] == 0]
    # doğrulama kolu = `python -m beden_paket.kosucu dogrulama`'nın koşusu: anahtar aynı, ızgarada önbellekten
    h = simulasyon.dogrulama_hazirla(0, "kucuk")
    assert G0.lumoda.meta["anahtar"] == h.anahtar and G0.lumoda.dizin.name.startswith("dogrulama_")
    assert simulasyon.onbellekte_mi(h, ortam.onbellek)
    assert simulasyon.kos_dogrulama(0, "kucuk", onbellek=ortam.onbellek).onbellekten


# ---------------------------------------------------------------------------
# Oyuncak: ön denetim, kahin
# ---------------------------------------------------------------------------


def test_on_denetim_oyuncak():
    """Option başına depo sınaması: Σ ns × desen_b > depo_b olan option sayılır; atamasız mağaza girmez."""
    depo = pd.DataFrame([[2, 4, 4, 2, 2], [1, 4, 4, 4, 2]], index=["O1", "O2"], columns=oyun.SUTUNLAR)
    D = np.array([[1, 1, 2, 2, 1], [1, 2, 2, 1, 1]])
    atama = pd.Series({"M1": 0, "M2": 1})
    ns = {("O1", "M1"): 1, ("O1", "M2"): 1, ("O2", "M1"): 2, ("O2", "M3"): 9, ("O9", "M1"): 5}
    r = oyun.on_denetim(D, atama, ns, depo)
    # O1: 1-1-2-2-1 + 1-2-2-1-1 = 2-3-4-3-2 ≤ 2-4-4-2-2? 4. beden 3 > 2: aşar (1 adet)
    # O2: 2 × 1-1-2-2-1 = 2-2-4-4-2 ≤ 1-4-4-4-2? 1. beden 2 > 1: aşar (1 adet); M3 atamasız
    assert r == {"option": 2, "option_beden": 2, "asim_adet": 2, "kontrol_option": 2}
    assert oyun.on_denetim(D, atama, {("O1", "M1"): 1}, depo)["option"] == 0


def test_kahin_ayni_mi_oyuncak(G0):
    """Kahin: desenler gerçek paya göre atanır; tasarımdan ayrılan mağaza listelenir, gerçek paya göre
    uyumsuzluk iki atamada hesaplanır."""
    D = np.array([[1, 1, 2, 2, 1], [1, 2, 2, 1, 1]])
    ids = ["M1", "M2", "M3"]
    tas = paket_tasarim.Tasarim(desenler=D, atama=pd.Series([0, 0, 1], index=pd.Index(ids, name="magaza_id")),
                                toplam_uyumsuzluk=0.0, en_iyi_mi=True, yontem="tam")
    buyuk, kucuk = [0.07, 0.17, 0.28, 0.30, 0.18], [0.16, 0.28, 0.29, 0.19, 0.08]
    gercek = pd.DataFrame([buyuk, kucuk, kucuk], index=ids, columns=oyun.SUTUNLAR)
    e = G0.egri
    sahte = type(e)(magaza=e.magaza, profil=pd.Series({"M1": "b", "M2": "b", "M3": "k"}), zincir=e.zincir,
                    kaynak={"M1": "magaza", "M2": "profil", "M3": "magaza"})
    r = oyun.kahin_ayni_mi(tas, sahte, gercek, pd.Series({"M1": 1, "M2": -1, "M3": -1}), pd.Series(1.0, index=ids))
    assert r["farkli_magaza"] == ["M2"] and not r["ayni_atama"] and r["magaza"] == 3
    assert r["ari"] == 1.0 and r["ari_magaza"] == 2                 # okunabilen M1, M3
    assert r["uyumsuzluk_gercek_kahin"] < r["uyumsuzluk_gercek_tasarim"]


def test_kahin_yalniz_olcumde():
    """Gizli gerçek (`hakem`) oyun modülünde yalnız kahin denetiminde okunur: tasarım, ns, ağırlık, depo ve
    koşu yolları hakemi görmez (çalışma zamanı denetimi `test_izgara_kucuk_uctan_uca`'da: hakem kapalıyken
    ızgara koşar). Karar modülleri `oyun`'u ve `hakem`'i hiç içe aktarmaz (`test_sizinti.py`)."""
    agac = ast.parse((Path(beden_paket.__file__).resolve().parent / "oyun.py").read_text(encoding="utf-8"))
    kullanan = set()

    def gez(dugum, yol):
        for c in ast.iter_child_nodes(dugum):
            ad = getattr(c, "name", None)
            alt = yol + [ad] if isinstance(c, (ast.FunctionDef, ast.ClassDef)) else yol
            if isinstance(c, ast.Name) and c.id == "hakem":
                kullanan.add(".".join(yol))
            gez(c, alt)

    gez(agac, [])
    assert kullanan == {"YolGirdisi.kahin"}


# ---------------------------------------------------------------------------
# Yolun girdileri (KÜÇÜK)
# ---------------------------------------------------------------------------


def test_yol_kendi_tablolari(G0, G1, ortam, monkeypatch):
    """Yol p'nin eğrisi, ns'i ve deposu o yolun doğrulama koşusunun tablolarından (talep tohumu yolun);
    yol 0 KÜÇÜK'te de doğrulama koşusundan (yayımlanan DuckDB yalnız TAM yol 0). ns yollarda aynı çıkar
    (spec §0/16), eğri yolun satışından ayrılır."""
    assert ortam.yayimlanan_mi(0) is False and oyun.Ortam().yayimlanan_mi(0) and not oyun.Ortam().yayimlanan_mi(1)
    assert G1.lumoda.dizin.name.startswith("y1_dogrulama_")
    assert G1.lumoda.meta["talep_tohumu"] == al_oyun.talep_tohumu(1) and G0.lumoda.meta["talep_tohumu"] is None
    assert G1.kaynak_adi == f"vaka:{G1.lumoda.dizin.name}"
    oyun_ids = set(G1.oyun_ids)
    assert G1.ns(7) == {a: v for a, v in kosucu.lumoda_giden(G1.lumoda).items() if a[0] in oyun_ids}
    assert G1.ns(7) == G0.ns(7)                         # Lumoda'nın ilk dağıtımı talep yolundan bağımsız (§0/16)
    assert not G1.egri.n.equals(G0.egri.n)              # eğri yolun satışından
    # yayımlanan biçim yolun kendi koşusundan kurulur
    gorulen = []
    asil = motor.yayimlanan_bicim
    monkeypatch.setattr(oyun.motor, "yayimlanan_bicim", lambda t, o: gorulen.append(t["satis"]) or asil(t, o))
    yeni = oyun.YolGirdisi(1, ortam)
    pd.testing.assert_frame_equal(yeni.egri.magaza, G1.egri.magaza)
    pd.testing.assert_frame_equal(gorulen[0], G1.lumoda.tablo("satis"))
    b = G1.bilgi()
    assert b["kaynak"] == G1.kaynak_adi and b["lumoda_anahtar"] == G1.lumoda.meta["anahtar"]


def test_depo_lumodayi_uretir(G0):
    """Depo (ilk sipariş − hatalı) Lumoda'nın giden paketini birebir üretir: beş bedenli her oyun option'ında
    giden = min(istenen, min_b ⌊depo_b ÷ 1-2-2-1-1_b⌋); `depo_payi(a, "depo")` = depo ÷ (a × Σ ağırlık)."""
    w = G0.w
    kayit = G0.lumoda.kayitlar["ilk_dagitim"]
    oid = w.optionlar["option_id"].astype(str).to_numpy()
    istenen = kayit[kayit["indis"] >= 0].groupby("arg0")["deger"].sum()
    istenen.index = oid[istenen.index]
    giden = pd.Series(G0.ns(7)).groupby(level=0).sum()
    c = np.asarray(sabitler.LUMODA_PAKET)
    for o in G0.bes_optionlar:
        tavan = int(np.min(G0.depo.loc[o].to_numpy() // c))
        assert int(giden.get(o, 0)) == min(int(istenen.get(o, 0)), tavan), o
    for a in (7, 12):
        np.testing.assert_allclose(G0.depo_payi(a, "depo") * a * G0.agirlik(a).sum(), G0.depo.sum(axis=0).to_numpy())
    assert set(G0.agirlik(7).index) == set(G0.egri.magaza.index) and G0.agirlik(7).sum() > 0


def test_depo_payi_karar_oncesi(G0, G1):
    """Tasarımın depo payı karar öncesi bilgiden: ilk sipariş adedi (Ruling R16); hata düşülmüş depo
    yalnız ön denetimde. İki tanımla bütün kolların tasarımı ve bağları aynı (KÜÇÜK yol 0 ve 1)."""
    for G in (G0, G1):
        for a in (7, 12):
            np.testing.assert_allclose(G.depo_payi(a) * a * G.agirlik(a).sum(), G.siparis_deposu.sum(axis=0))
            np.testing.assert_allclose(G.depo_payi(a, "depo") * a * G.agirlik(a).sum(), G.depo.sum(axis=0))
        assert (G.siparis_deposu >= G.depo).to_numpy().all()
        assert oyun.depo_tanimlari_ayni(G) == {"ayni": True, "farkli": []}


def test_olcum_kodu_kapsami():
    """Ölçüm kodu özeti içe aktarma anında bir kez kurulur (süreç sürerken dosya değişse de o sürecin
    koduyla ölçülmüş kaydı adlandırır) ve oyun'un ölçüm tarafı yardımcılarını kapsar; kaynak ya da
    `OLCUM_SURUMU` değişince değişir."""
    assert {"olcum_kaydi", "YolGirdisi._giden", "YolGirdisi.giden_adet", "YolGirdisi.bes_optionlar",
            "YolGirdisi.oyun_ids"} <= set(oyun.OLCUM_FONKSIYONLARI)
    assert oyun.olcum_kodu() == oyun.OLCUM_OZETI
    m = oyun.olcum_metinleri()
    assert set(m) >= {"kosucu.py", "olcutler.py", "olcum_kaydi", "YolGirdisi.giden_adet"}
    taban = oyun.olcum_ozeti(m, oyun.OLCUM_SURUMU)
    assert taban == oyun.OLCUM_OZETI
    assert oyun.olcum_ozeti(m | {"YolGirdisi.bes_optionlar": "değişti"}, oyun.OLCUM_SURUMU) != taban
    assert oyun.olcum_ozeti(m, oyun.OLCUM_SURUMU + 1) != taban


def test_ayni_kol_yolun_kol_kumesinde(G1):
    """`ayni_kol` yalnız yolun kol kümesindeki kollara bağlar: yolda p3_12 için p1_12 tasarlanmaz."""
    G1._tasarimlar.clear()
    assert oyun.ayni_kol(G1, "p3_12") is None
    assert (1, 12) not in {(K, a) for K, a, *_ in G1._tasarimlar}       # p1_12 yolun kolu değil
    assert oyun.ayni_kol(G1, "p2") is None and oyun.ayni_kol(G1, "p1") is None


def test_k_egrisi_kucuk(G0):
    """K eğrisi: 7'lide Lumoda + K = 1..4 + mağaza, 12'lide K = 1..4 + mağaza; uyumsuzluk K ile artmaz;
    `ayni` aynı desen ve atamayı veren ilk küçük K'yı gösterir."""
    r = G0.k_egrisi()
    assert [(x["adet"], x["K"]) for x in r] == [(7, "lumoda")] + [(a, K) for a in (7, 12) for K in (1, 2, 3, 4, "magaza")]
    for a in (7, 12):
        u = [x["toplam_uyumsuzluk"] for x in r if x["adet"] == a and x["K"] != "lumoda"]
        assert all(y <= x + 1e-9 for x, y in zip(u, u[1:]))
        for x in r:
            if x["adet"] == a and x["ayni"] is not None:
                assert x["desenler"] == next(y["desenler"] for y in r if y["adet"] == a and y["K"] == x["ayni"])
    assert r[1]["desenler"] == [paket_tasarim.desen_adi(G0.tasarim("p1").desenler[0])]
    k = G0.kahin("p2")
    assert set(k) >= {"ayni_atama", "farkli_magaza", "ari", "uyumsuzluk_gercek_kahin"}


# ---------------------------------------------------------------------------
# Uçtan uca (KÜÇÜK): ızgara, ölçüm önbelleği, aynı mal, aynı koşu iki adla
# ---------------------------------------------------------------------------


def _kapali(*a, **k):
    raise AssertionError("ızgara hakemi okudu")


def test_izgara_kucuk_uctan_uca(ortam, monkeypatch):
    """Bir kol (p2) baştan sona: hakem kapalıyken tasarım ve koşu, `oyun.json` kaydı, `ilerleme.jsonl`
    satırı; yeniden çağrı koşmaz ve ölçmez; ölçüm kodu değişince yalnız yeniden ölçer (koşu önbellekten,
    Ruling R14)."""
    for ad in ("gercek_pay", "kayma", "dunya"):
        monkeypatch.setattr(hakem, ad, _kapali)
    kayit = oyun.kos_hepsi("ana", ortam, adlar={"p2"})
    p2 = kayit["kosular"]["p2"]
    assert set(kayit["kosular"]) >= {"p2"} and "0" in kayit["yollar"]
    assert p2["desenler"] == ["1-1-2-2-1", "1-2-2-1-1"] and p2["K"] == 2 and p2["paket_adet"] == 7
    assert set(p2["atama"]) == set(oyun.YolGirdisi(0, ortam).egri.magaza.index)
    assert p2["egri_kaynagi"].startswith("vaka:dogrulama_") and p2["ns_kaynagi"] == p2["egri_kaynagi"]
    assert p2["olcum_kodu"] == oyun.olcum_kodu() and p2["olcutler"]["paket_tipi"] == 2
    disk = json.loads(ortam.oyun_yolu.read_text(encoding="utf-8"))
    assert disk["kosular"]["p2"]["anahtar"] == p2["anahtar"]
    satirlar = [json.loads(s) for s in ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()]
    assert any(s["ad"] == "p2" and not s["onbellekten"] for s in satirlar)
    dizinler = sorted(p.name for p in ortam.onbellek.iterdir())

    ikinci = oyun.kos_hepsi("ana", ortam, adlar={"p2"})["kosular"]["p2"]
    assert ikinci == p2                                     # önbellekten, yeniden ölçülmedi (aynı kayıt)
    monkeypatch.setattr(oyun, "olcum_kodu", lambda: "baska")
    ucuncu = oyun.kos_hepsi("ana", ortam, adlar={"p2"})["kosular"]["p2"]
    assert ucuncu["olcum_kodu"] == "baska" and ucuncu["anahtar"] == p2["anahtar"]
    assert ucuncu["olcutler"] == p2["olcutler"]
    son = json.loads(ortam.ilerleme_yolu.read_text(encoding="utf-8").splitlines()[-1])
    assert son["ad"] == "p2" and son["onbellekten"]
    assert sorted(p.name for p in ortam.onbellek.iterdir()) == dizinler      # yeni simülasyon yok


def test_ayni_mal_option_basina(ortam):
    """KÜÇÜK'te 7'li ve 12'li kollarda motor hiçbir oyun option'ında kırpmaz (ön denetim de 0 der); 7'lide
    (option, mağaza) başına giden adet Lumoda'nınkine eşit; mağazaya özel 12'li tasarım p3_12'ninkiyle aynıysa
    koşulmaz, kaydı `ayni` ile bağlanır."""
    kayit = oyun.kos_hepsi("ana", ortam, adlar={"p2", "p3_12", "pm_12"})["kosular"]
    for ad in ("p2", "p3_12"):
        k = kayit[ad]
        assert k["on_denetim"]["option"] == 0 and k["on_denetim"]["kontrol_option"] > 0
        assert k["olcutler"]["kirpilan_adet"] == 0 and k["olcutler"]["kirpilan_option"] == 0
        assert k["ayni_mal"] is True
    assert kayit["p2"]["korunum"]["fark_adet"] == 0 and kayit["p2"]["korunum"]["hucre"] > 0
    assert kayit["p3_12"]["olcutler"]["paket_tipi"] == len(kayit["p3_12"]["desenler"])
    # 12'li dönüşüm option toplamını korur: her beş bedenli option'da |12 × Σ paket − Σ Lumoda adedi| ≤ 6
    G = oyun.YolGirdisi(0, ortam)
    lum = pd.Series({a: v for a, v in G.giden_adet.items() if a[0] in set(G.bes_optionlar)}).groupby(level=0).sum()
    kol = pd.Series({a: v for a, v in G.ns(12).items() if a[0] in set(G.bes_optionlar)}).groupby(level=0).sum() * 12
    fark = (kol.reindex(lum.index, fill_value=0) - lum).abs()
    assert len(fark) == len(G.bes_optionlar) and fark.max() <= 6
    d = kayit["p3_12"]["donusum"]
    assert d["option_en_buyuk_fark"] == int(fark.max()) and d["option"] == len(fark)
    assert oyun.ayni_tasarim(G.tasarim("pm_12"), G.tasarim("p3_12"))      # KÜÇÜK verisinde
    assert kayit["pm_12"]["ayni"] == "p3_12" and kayit["pm_12"]["anahtar"] == kayit["p3_12"]["anahtar"]
    assert not any(p.name.startswith("pm_12_") for p in ortam.onbellek.iterdir())


# ---------------------------------------------------------------------------
# Gerçek veri: TAM yol 0'ın tasarımları (koşu yok)
# ---------------------------------------------------------------------------


@pytest.mark.veri
def test_tam_yol0_tasarimlar():
    """TAM yol 0 (yayımlanan DuckDB; ns İlk Sevkiyat'ın önbellekli `lumoda`'sından, doğrulama koluyla
    birebir): depo Lumoda'yı üretir; P1 1-1-2-2-1; P3_12 [1-2-3-4-2, 1-3-4-3-1, 2-3-4-2-1]; hiçbir kol hiçbir
    option'da depoyu aşmaz; 7'lide K ≥ 3 ve mağaza P2 ile aynı; pm_12 = p3_12, p2_ham = p2 (ızgarada
    koşulmaz); kahin denetimi."""
    k = kosucu.allocation_lumoda(0)
    if k is None:
        pytest.skip("İlk Sevkiyat önbelleği yok")
    G = oyun.YolGirdisi(0, oyun.Ortam(ilerleme=False))
    G.__dict__["lumoda"] = k
    assert G.kaynak_adi == "yayimlanan" and len(G.bes_optionlar) == 193 and len(G.egri.magaza) == 69
    test_depo_lumodayi_uretir(G)
    beklenen = {"p1": ["1-1-2-2-1"], "p2": ["1-1-2-2-1", "1-2-2-1-1"],
                "p3_12": ["1-2-3-4-2", "1-3-4-3-1", "2-3-4-2-1"]}
    for kol in ("p1", "p2", "p1_12", "p3_12", "pm_12", "p2_ham"):
        r = oyun.tasarim_kaydi(G, kol)
        print(kol, r["desenler"], r["tasarim"], r["on_denetim"])
        assert r["on_denetim"]["option"] == 0 and r["tasarim"]["depo_uygun"]
        if kol in beklenen:
            assert r["desenler"] == beklenen[kol]
    satir = G.k_egrisi()
    for x in satir:
        print(x)
    assert [x["ayni"] for x in satir if x["adet"] == 7 and x["K"] in (3, 4, "magaza")] == [2, 2, 2]
    # aynı koşu iki adla (ızgaranın koşu sayısı buna dayanır): pm_12 = p3_12, p2_ham = p2
    assert oyun.ayni_kol(G, "pm_12") == "p3_12" and oyun.ayni_kol(G, "p2_ham") == "p2"
    assert [oyun.ayni_kol(G, k) for k in ("p1", "p2", "p1_12", "p3_12")] == [None] * 4
    # R16: karar öncesi (sipariş) ve hata düşülmüş depoyla tasarımlar ve bağlar aynı (koşan TAM geçerli)
    assert oyun.depo_tanimlari_ayni(G) == {"ayni": True, "farkli": []}
    kahin = G.kahin("p2")
    print(kahin)
    assert kahin["ari"] == 1.0 and kahin["farkli_magaza"] == ["M027"]          # Ruling R15
    print("12'li dönüşüm", G.bilgi()["donusum_12"])
    assert G.bilgi()["donusum_12"]["option_en_buyuk_fark"] <= 6


@pytest.mark.veri
def test_tam_yollar_depo_tanimi():
    """TAM yollar 1–4: doğrulama koşusu vakanın önbelleğindeyse (salt okunur; koşmaz, silmez) iki depo
    tanımıyla tasarımlar ve bağlar aynı (R16). Önbellekte olmayan yol atlanır."""
    sinanan = []
    for p in oyun.YOLLAR:
        h = simulasyon.dogrulama_hazirla(p, "tam")
        k = kosucu.salt_okunur_kayit(motor._dizin(simulasyon.KOSU_DIZINI, h.ad, h.anahtar), h.anahtar)
        if k is None:
            continue
        G = oyun.YolGirdisi(p, oyun.Ortam(ilerleme=False))
        G.__dict__["lumoda"] = k
        assert oyun.depo_tanimlari_ayni(G) == {"ayni": True, "farkli": []}, p
        sinanan.append(p)
    print("sınanan yollar", sinanan)
    if not sinanan:
        pytest.skip("yolların TAM doğrulama koşusu önbellekte yok")
