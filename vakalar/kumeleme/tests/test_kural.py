"""`kumeleme.kural`: K1 bölge, K2 ciro sınıfı, K3 bölge × sınıf, K4 konum.

Eşik ve birleşme testleri elle kurulmuş küçük tablolarla çalışır (`_kapsam`, `_satis`); yeni
mağaza ve karar günü testleri `conftest`in 12 mağazalı fikstürünü kullanır; `veri` işaretli test
yayımlanan v4 verisini ister.
"""

import pandas as pd
import pytest
from conftest import KARAR

from kumeleme import kaynak, kural, sabitler


def _kapsam(satirlar, **kolon):
    """satirlar: (magaza_id, bolge, sehir[, kumelenir]) → kapsam benzeri tablo."""
    df = pd.DataFrame([(*s, True)[:4] for s in satirlar],
                      columns=["magaza_id", "bolge", "sehir", "kumelenir"])
    df["yeni"] = ~df["kumelenir"]
    df["gecmis_hafta"] = 80
    df["metropol"] = df["sehir"].isin(kaynak.METROPOL)
    for k, v in kolon.items():
        df[k] = v
    return df


def _satis(ciro: dict[str, float], tarih="2024-09-02") -> pd.DataFrame:
    return pd.DataFrame({"tarih": pd.Timestamp(tarih), "magaza_id": list(ciro),
                         "tutar": [float(v) for v in ciro.values()]})


def _on_magaza():
    ids = [f"M{i:02d}" for i in range(1, 11)]
    return _kapsam([(i, "Marmara", "Bursa") for i in ids]), ids


# ------------------------------------------------------------------ K1


def test_bolge_yayimlanan_bolge():
    k = _kapsam([("M1", "Marmara", "Bursa"), ("M2", "Ege", "Denizli")])
    b = kural.bolge(k)
    assert b.index.name == "magaza_id" and list(b.index) == ["M1", "M2"]
    assert list(b) == ["Marmara", "Ege"]


# ------------------------------------------------------------------ K2


def test_ciro_esikleri():
    """10 mağaza → 2 A / 3 B / 5 C; A en yüksek cirolular."""
    k, ids = _on_magaza()
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids)}        # M10 en yüksek
    s = kural.ciro_sinifi(_satis(ciro), k, KARAR)
    assert s.value_counts().to_dict() == {"C": 5, "B": 3, "A": 2}
    assert sorted(s.index[s == "A"]) == ["M09", "M10"]
    assert sorted(s.index[s == "B"]) == ["M06", "M07", "M08"]
    assert sabitler.CIRO_A == 0.20 and sabitler.CIRO_B == 0.30


def test_ciro_esikleri_67_magaza():
    """Karar günü kapsamının büyüklüğü: 13 / 20 / 34 (yarım yukarı yuvarlama)."""
    ids = [f"M{i:03d}" for i in range(1, 68)]
    k = _kapsam([(i, "Marmara", "Bursa") for i in ids])
    s = kural.ciro_sinifi(_satis({m: float(i + 1) for i, m in enumerate(ids)}), k, KARAR)
    assert s.value_counts().to_dict() == {"C": 34, "B": 20, "A": 13}


def test_ciro_yarim_yukari_yuvarlama():
    """15 mağaza: 0,3 · 15 = 4,5 → 5 (yarım yukarı; Python `round` 4 verirdi): 3 / 5 / 7."""
    ids = [f"M{i:02d}" for i in range(1, 16)]
    k = _kapsam([(i, "Marmara", "Bursa") for i in ids])
    s = kural.ciro_sinifi(_satis({m: float(i + 1) for i, m in enumerate(ids)}), k, KARAR)
    assert s.value_counts().to_dict() == {"C": 7, "B": 5, "A": 3}


def test_net_ciro_birebir_yinelenen_satir_tek_sayilir():
    """Gerçek satışta birebir aynı satırlar vardır: yinelenen girdi aynı sonucu verir; farklı
    `urun_id`li aynı gün aynı tutarlı iki satır ise iki satıştır."""
    k, ids = _on_magaza()
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids)}
    temel = _satis(ciro)
    temel["urun_id"] = "U1"
    temel["adet"] = 1
    ikili = pd.concat([temel, temel.iloc[[0, 9, 9]]], ignore_index=True)       # M01 bir, M10 iki kez daha
    assert kural.net_ciro(ikili, k, KARAR).equals(kural.net_ciro(temel, k, KARAR))
    assert kural.ciro_sinifi(ikili, k, KARAR).equals(kural.ciro_sinifi(temel, k, KARAR))
    farkli = pd.concat([temel, temel.iloc[[9]].assign(urun_id="U2")], ignore_index=True)
    assert kural.net_ciro(farkli, k, KARAR)["M10"] == 2000.0


@pytest.mark.parametrize("hafta, yillik", [(51, True), (52, False), (sabitler.GECMIS_HAFTA_ESIGI, True)])
def test_yillik_siniri(hafta, yillik):
    """52 haftada (tam yıl) ciro ölçeklenmez; 51 haftada ölçeklenir."""
    k, _ = _on_magaza()
    k.loc[0, "gecmis_hafta"] = hafta
    s = _satis({"M01": 100.0})
    s = pd.concat([s, pd.DataFrame({"tarih": [KARAR - pd.Timedelta(days=7 * hafta)],
                                    "magaza_id": ["M01"], "tutar": [100.0]})], ignore_index=True)
    c = kural.net_ciro(s, k, KARAR)["M01"]
    if yillik:
        assert c == pytest.approx(200.0 * 366 / (7 * hafta))
    else:
        assert c == 200.0


def test_net_ciro_yeni_magaza_yillikli_ama_c():
    """Yeni mağazanın raporlanan cirosu yıllıklandırılır; sınıfı yine C."""
    k, ids = _on_magaza()
    k.loc[k["magaza_id"] == "M10", ["kumelenir", "yeni", "gecmis_hafta"]] = [False, True, 19]
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids[:-1])}
    s = pd.concat([_satis(ciro), pd.DataFrame({"tarih": [KARAR - pd.Timedelta(days=133)],
                                               "magaza_id": ["M10"], "tutar": [1000.0]})], ignore_index=True)
    assert kural.net_ciro(s, k, KARAR)["M10"] == pytest.approx(1000.0 * 366 / 133)
    assert kural.ciro_sinifi(s, k, KARAR)["M10"] == "C"


def test_ciro_esitlikte_magaza_kimligi():
    k, ids = _on_magaza()
    s = kural.ciro_sinifi(_satis({m: 500.0 for m in ids}), k, KARAR)        # hepsi eşit
    assert sorted(s.index[s == "A"]) == ["M01", "M02"]
    assert sorted(s.index[s == "B"]) == ["M03", "M04", "M05"]
    # sıra girişten bağımsız
    ters = kural.ciro_sinifi(_satis({m: 500.0 for m in ids}), k.iloc[::-1].reset_index(drop=True), KARAR)
    assert ters.sort_index().equals(s.sort_index())


def test_ciro_net_iade_dusulur():
    """M01 brüt en yüksek ama iadesi onu düşürür: net ciro sıralar."""
    k, ids = _on_magaza()
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids)}
    s = _satis(ciro)
    s = pd.concat([s, pd.DataFrame({"tarih": [pd.Timestamp("2024-10-01")], "magaza_id": ["M10"],
                                    "tutar": [-950.0]})], ignore_index=True)
    sinif = kural.ciro_sinifi(s, k, KARAR)
    assert kural.net_ciro(s, k, KARAR)["M10"] == pytest.approx(50.0)
    assert sinif["M10"] == "C" and sinif["M08"] == "A" and sinif["M09"] == "A"


def test_ciro_sinifi_karar_oncesi():
    """Pencere [karar - 1 yıl, karar): öncesi ve karar günü/sonrası satış sınıfı değiştirmez."""
    k, ids = _on_magaza()
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids)}        # M10, M09 → A
    temel = _satis(ciro)
    ek = pd.DataFrame({
        "tarih": pd.to_datetime(["2024-02-06", "2025-02-07", "2025-02-10", "2025-03-03"]),
        "magaza_id": ["M01", "M01", "M01", "M01"], "tutar": [1e6, 1e6, 1e6, 1e6]})
    s = pd.concat([temel, ek], ignore_index=True)
    assert kural.net_ciro(s, k, KARAR).equals(kural.net_ciro(temel, k, KARAR))
    assert kural.ciro_sinifi(s, k, KARAR).equals(kural.ciro_sinifi(temel, k, KARAR))
    # pencerenin ilk günü içeridedir
    ic = pd.concat([temel, pd.DataFrame({
        "tarih": [pd.Timestamp("2024-02-07")], "magaza_id": ["M01"], "tutar": [1e6]})], ignore_index=True)
    assert kural.ciro_sinifi(ic, k, KARAR)["M01"] == "A"


def test_satissiz_magaza_ciro_sifir():
    k, ids = _on_magaza()
    s = _satis({m: 100.0 * (i + 1) for i, m in enumerate(ids[1:])})      # M01 satışsız
    assert kural.net_ciro(s, k, KARAR)["M01"] == 0.0
    assert kural.ciro_sinifi(s, k, KARAR)["M01"] == "C"


def test_kisa_gecmis_yillikla():
    """26 hafta (182 gün) geçmişli mağaza: ciro pencere / 182 ile ölçeklenir ve sıralamaya girer;
    ham ciroyla C'de kalırdı."""
    k, ids = _on_magaza()
    ciro = {m: 600.0 + 10 * i for i, m in enumerate(ids[:-1])}       # M01..M09: 600..680
    s = _satis(ciro)
    ilk = KARAR - pd.Timedelta(days=183)
    kisa = pd.DataFrame({"tarih": [ilk, KARAR - pd.Timedelta(days=1)], "magaza_id": ["M10", "M10"],
                         "tutar": [300.0, 250.0]})                     # ham 550 < hepsi
    s = pd.concat([s, kisa], ignore_index=True)
    k.loc[k["magaza_id"] == "M10", "gecmis_hafta"] = 26
    ciro_yillik = kural.net_ciro(s, k, KARAR)
    assert ciro_yillik["M10"] == pytest.approx(550.0 * 366 / 183)    # 2024 artık yıl: pencere 366 gün
    assert ciro_yillik["M01"] == 600.0                                 # tam geçmiş: ölçeklenmez
    assert kural.ciro_sinifi(s, k, KARAR)["M10"] == "A"
    k.loc[k["magaza_id"] == "M10", "gecmis_hafta"] = 80                # geçmişi tam sayılsa
    assert kural.ciro_sinifi(s, k, KARAR)["M10"] == "C"


def test_ciro_yeni_magaza_siralamaya_girmez():
    """Yeni mağaza en yüksek cirolu da olsa C alır ve eşikleri etkilemez (n = kümelenen sayısı)."""
    k, ids = _on_magaza()
    k.loc[k["magaza_id"] == "M10", ["kumelenir", "yeni"]] = [False, True]
    ciro = {m: 100.0 * (i + 1) for i, m in enumerate(ids)}                # M10 en yüksek
    s = kural.ciro_sinifi(_satis(ciro), k, KARAR)
    assert s["M10"] == "C"
    # 9 kümelenen: round(1.8)=2 A, round(2.7)=3 B, 4 C (+ yeni M10)
    assert s.value_counts().to_dict() == {"C": 5, "B": 3, "A": 2}
    assert sorted(s.index[s == "A"]) == ["M08", "M09"]


# ------------------------------------------------------------------ K3


def test_k3_kucuk_hucre_birlesir():
    """Hücre sayıları A,B,C → grup tablosu; her kural dalı."""
    b = kural._birlestir
    assert b({"A": 3, "B": 4, "C": 5}) == {"A": "A", "B": "B", "C": "C"}       # hepsi yeterli
    assert b({"A": 2, "B": 4, "C": 5}) == {"A": "AB", "B": "AB", "C": "C"}     # uç → B
    assert b({"A": 4, "B": 4, "C": 2}) == {"A": "A", "B": "BC", "C": "BC"}
    assert b({"A": 2, "B": 4, "C": 1}) == {"A": "ABC", "B": "ABC", "C": "ABC"}  # ikisi de küçük: C(1) önce
    assert b({"A": 4, "B": 1, "C": 5}) == {"A": "AB", "B": "AB", "C": "C"}     # ortadaki: az olan komşu A (4 < 5)
    assert b({"A": 5, "B": 1, "C": 4}) == {"A": "A", "B": "BC", "C": "BC"}     # ... C (4 < 5)
    assert b({"A": 4, "B": 1, "C": 4}) == {"A": "AB", "B": "AB", "C": "C"}     # eşitlikte A
    assert b({"A": 4, "B": 0, "C": 2}) == {"A": "AC", "C": "AC"}                # boş B: A ile C bitişik
    assert b({"A": 1, "B": 1, "C": 1}) == {"A": "ABC", "B": "ABC", "C": "ABC"}
    assert b({"A": 2, "B": 0, "C": 0}) == {"A": "A"}                            # birleşecek komşu yok
    assert b({"A": 0, "B": 0, "C": 0}) == {}


def test_birlestir_ozellikleri():
    """A/B/C sayılarının 0..8 her bileşimi: sonlanır; her mağazalı sınıf bir gruba düşer; gruplar
    bitişik (A-B-C dizisinde boşluksuz, boş sınıf köprü olabilir) ve ayrık; bölgenin tümü
    K3_EN_AZ'den azsa tek grup, değilse hiçbir grup K3_EN_AZ'den küçük değil."""
    sira = "ABC"
    for a in range(9):
        for b in range(9):
            for c in range(9):
                sayi = {"A": a, "B": b, "C": c}
                h = kural._birlestir(sayi)
                dolu = [x for x in sira if sayi[x] > 0]
                assert set(h) == set(dolu), sayi
                gruplar = {}
                for x in dolu:
                    gruplar.setdefault(h[x], []).append(x)
                for ad, uyeler in gruplar.items():
                    assert ad == "".join(uyeler), sayi                      # etiket = sınıflar A-B-C sırasıyla
                    konum = [sira.index(x) for x in uyeler]
                    ara = [x for x in sira[min(konum):max(konum) + 1] if sayi[x] > 0]
                    assert ara == uyeler, sayi                              # bitişik: aradaki dolu sınıf dışarıda kalmaz
                    if a + b + c >= sabitler.K3_EN_AZ:
                        assert sum(sayi[x] for x in uyeler) >= sabitler.K3_EN_AZ, sayi
                if a + b + c < sabitler.K3_EN_AZ:
                    assert len(gruplar) <= 1, sayi


def test_k3_bolge_ciro_etiketleri():
    """Ege: 2 A + 4 B + 3 C → A, B ile birleşir; Marmara hepsi yeterli; Karadeniz 2 mağaza tek grup."""
    satir = ([(f"E{i}", "Ege", "Denizli") for i in range(9)]
             + [(f"M{i}", "Marmara", "Bursa") for i in range(9)]
             + [("K1", "Karadeniz", "Samsun"), ("K2", "Karadeniz", "Trabzon")])
    k = _kapsam(satir)
    sinif = {f"E{i}": s for i, s in enumerate("AABBBBCCC")}
    sinif |= {f"M{i}": s for i, s in enumerate("AAABBBCCC")} | {"K1": "A", "K2": "C"}
    k3 = kural.bolge_ciro(k, pd.Series(sinif))
    assert list(k3.index) == list(k["magaza_id"])
    assert set(k3[[f"E{i}" for i in range(6)]]) == {"Ege×AB"}
    assert set(k3[[f"E{i}" for i in range(6, 9)]]) == {"Ege×C"}
    assert sorted(set(k3[[f"M{i}" for i in range(9)]])) == ["Marmara×A", "Marmara×B", "Marmara×C"]
    assert set(k3[["K1", "K2"]]) == {"Karadeniz×AC"}
    # birleşmeden sonra hiçbir grup K3_EN_AZ'den küçük değil (tek gruplu küçük bölge hariç)
    sayim = k3[k3.str.startswith(("Ege", "Marmara"))].value_counts()
    assert (sayim >= sabitler.K3_EN_AZ).all()


# ------------------------------------------------------------------ K4


def test_konum_kurali(monkeypatch):
    k = _kapsam([("M1", "Marmara", "İstanbul"), ("M2", "İç Anadolu", "Ankara"),
                 ("M3", "Ege", "İzmir"), ("M4", "Ege", "Bodrum"), ("M5", "Ege", "Denizli"),
                 ("M6", "İç Anadolu", "Konya"), ("M7", "Doğu Anadolu", "Erzurum"),
                 ("M8", "Marmara", "Bursa")])
    s = kural.konum(k)
    assert list(s) == ["metropol", "metropol", "metropol", "sicak_sahil", "ılıman", "karasal",
                       "soguk", "ılıman"]
    # turistik şehir tabloda başka sınıfta olsa da sicak_sahil'dir
    monkeypatch.setitem(kaynak.SEHIR_IKLIM, "Bodrum", "karasal")
    assert kural.konum(k)["M4"] == "sicak_sahil"
    # metropol bayrağı iklimin önündedir (İzmir sicak_sahil tablosunda)
    assert kaynak.SEHIR_IKLIM["İzmir"] == "sicak_sahil" and s["M3"] == "metropol"
    with pytest.raises(ValueError, match="Atlantis"):
        kural.konum(_kapsam([("M9", "Ege", "Atlantis")]))


# ------------------------------------------------------------------ fikstür: yeni mağaza, karar günü


def _fiks_kapsam(tablolar):
    return kaynak.kapsam(tablolar["magaza"], tablolar["magaza_olay"], tablolar["satis"], KARAR)


def test_yeni_magaza_etiket_alir(tablolar):
    """M09 (10 hafta) yeni: K1/K4 statik, K2 ve K3'te C; kapsamdaki herkes etiketli, kapsam dışı yok."""
    k = _fiks_kapsam(tablolar)
    assert list(k.loc[k["yeni"], "magaza_id"]) == ["M09"]
    k1, k2, k4 = kural.bolge(k), kural.ciro_sinifi(tablolar["satis"], k, KARAR), kural.konum(k)
    k3 = kural.bolge_ciro(k, k2)
    for s in (k1, k2, k3, k4):
        assert list(s.index) == list(k["magaza_id"]) and not s.isna().any()
    assert (k1["M09"], k2["M09"], k4["M09"]) == ("Marmara", "C", "ılıman")
    assert k3["M09"].startswith("Marmara×") and "C" in k3["M09"].split("×")[1]
    # 8 kümelenen: round(1.6)=2 A, round(2.4)=2 B, 4 C (+ yeni M09)
    assert k2.value_counts().to_dict() == {"C": 5, "A": 2, "B": 2}
    assert k4["M08"] == "sicak_sahil" and k4["M01"] == "metropol"


def test_ciro_fikstur_karar_sonrasi_satis_etkisiz(tablolar):
    """Fikstürde karar gününden sonra (2025-02-10) her açık mağazaya satır eklenmiştir."""
    k = _fiks_kapsam(tablolar)
    once = tablolar["satis"][tablolar["satis"]["tarih"] < KARAR]
    assert kural.net_ciro(tablolar["satis"], k, KARAR).equals(kural.net_ciro(once, k, KARAR))


# ------------------------------------------------------------------ gerçek veri


@pytest.mark.veri
def test_kural_gruplari_ss25():
    """SS25 karar günü: 69 kapsam / 67 kümelenen / 2 yeni; sınıf ve hücre sayıları kayda.

    K2'ye **ham** pencere satırları (yinelenenler dahil) verilir: `net_ciro` tekilleştirmeyi
    kendisi yapar. Kapsam için günlük toplam yeter (yalnız gün ve brüt var/yok okunur)."""
    karar = sabitler.KARAR_GUNU
    con = kaynak.baglan()
    try:
        t = kaynak.yayimlanan_tablolar(con, ("magaza", "magaza_olay"))
        gunluk = con.execute(
            "select tarih::date::timestamp as tarih, magaza_id::varchar as magaza_id, "
            "sum(case when adet > 0 then 1 else 0 end) as adet "
            "from (select distinct * from satis where tarih < ?) group by 1, 2", [karar]).df()
        ham = con.execute("select * from satis where tarih >= ? and tarih < ?",
                          [karar - pd.DateOffset(years=1), karar]).df()
        tekil = con.execute("select count(*) from (select distinct * from satis where tarih >= ? "
                            "and tarih < ?)", [karar - pd.DateOffset(years=1), karar]).fetchone()[0]
    finally:
        con.close()
    assert len(ham) > tekil                                            # gerçek veride yinelenen satır var
    k = kaynak.kapsam(t["magaza"], t["magaza_olay"], gunluk, karar)
    assert len(k) == 69 and int(k["kumelenir"].sum()) == 67 and int(k["yeni"].sum()) == 2
    k1 = kural.bolge(k)
    ciro = kural.net_ciro(ham, k, karar)
    k2 = kural.ciro_sinifi(ham, k, karar)
    assert k2.equals(kural.ciro_sinifi(ham.drop_duplicates(), k, karar))   # girdinin tekilliğinden bağımsız
    k3 = kural.bolge_ciro(k, k2)
    k4 = kural.konum(k)
    kum = k.loc[k["kumelenir"], "magaza_id"]
    yeni = k.loc[k["yeni"], "magaza_id"]
    assert k2[kum].value_counts().to_dict() == {"A": 13, "B": 20, "C": 34}
    assert k2[yeni].tolist() == ["C", "C"]
    sirali = ciro[kum].sort_values(ascending=False)
    esik_a, esik_b = sirali.iloc[12], sirali.iloc[32]                  # 13. ve 33. mağaza
    assert round(esik_a) == 116_405_702 and round(esik_b) == 53_363_214
    assert (ciro[k2[kum].index[k2[kum] == "A"]] >= esik_a).all()
    # yeni mağazanın raporlanan cirosu yıllıklandırılmıştır (M041: 19 hafta), sınıfı C
    assert ciro["M041"] > 2 * 45_000_000 and k2["M041"] == "C"
    # K3: 12 grup; her bölge >= K3_EN_AZ mağazalı, bu yüzden hiçbir grup K3_EN_AZ'den küçük değil
    assert k3.nunique() == 12 and not k3.isna().any() and not k4.isna().any()
    assert (k1.value_counts() >= sabitler.K3_EN_AZ).all()
    assert (k3.value_counts() >= sabitler.K3_EN_AZ).all()
    bas = ["", "K1 bölge:", k1.value_counts().to_string(), "K2 sınıf (kümelenen 67 + 2 yeni):",
           k2.value_counts().to_string(),
           f"K2 eşik: A >= {esik_a:,.0f}, B >= {esik_b:,.0f}; M041 yıllıklı {ciro['M041']:,.0f}",
           f"Pencere satırı {len(ham)}, tekil {tekil}",
           "K3 hücre:", k3.value_counts().sort_index().to_string(),
           "K4 konum:", k4.value_counts().to_string()]
    print(chr(10).join(bas))
