"""Görev 10: yorum kütüphanesi şeması, parti tanımları, denetim."""

import json

import pytest

from perakende_veri.v4.crm.kutuphane import (
    AKSESUAR_GRUBU,
    AKSESUAR_YASAK_KONU,
    AKSESUAR_YASAK_YER_TUTUCU,
    DUYGULAR,
    KATEGORI_GRUPLARI,
    KONULAR,
    MIN_KATEGORI_KONU,
    PUAN_ORANI,
    USLUP_ORANI,
    USLUPLAR,
    YAZAR_YONERGESI,
    RENK_ADLARI,
    denetle,
    renk_adlari_bul,
    ornek_metin_yazdir,
    parti_dosyasi_yaz,
    parti_tanimlari,
)


# ---------------------------------------------------------------------------
# parti_tanimlari
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def partiler():
    return parti_tanimlari()


@pytest.fixture(scope="module")
def slotlar(partiler):
    tumu = []
    for p in partiler:
        tumu.extend(p["slotlar"])
    return tumu


def test_20_parti_200_slot_4000_toplam(partiler, slotlar):
    assert len(partiler) == 20
    for p in partiler:
        assert len(p["slotlar"]) == 200
    assert len(slotlar) == 4000


def test_id_sirali_ve_essiz(slotlar):
    idler = [s["id"] for s in slotlar]
    assert len(set(idler)) == 4000
    assert idler[0] == "Y0001"
    assert idler[-1] == "Y4000"
    assert idler == sorted(idler)


def test_puan_dagilimi_hedefi_tutar(slotlar):
    n = len(slotlar)
    from collections import Counter

    sayim = Counter(s["puan"] for s in slotlar)
    for puan, oran in PUAN_ORANI.items():
        assert sayim[puan] == round(oran * n) or sayim[puan] == pytest.approx(
            oran * n, abs=2
        )


def test_uslup_dagilimi_hedefi_tutar(slotlar):
    n = len(slotlar)
    from collections import Counter

    sayim = Counter(s["uslup"] for s in slotlar)
    for uslup, oran in USLUP_ORANI.items():
        assert sayim[uslup] == pytest.approx(oran * n, abs=2)
    assert set(sayim) == set(USLUPLAR)


def test_yer_tutucu_payi_yaklasik_yuzde_20(slotlar):
    n = len(slotlar)
    dolu = sum(1 for s in slotlar if s["yer_tutucu"])
    assert dolu == pytest.approx(0.20 * n, abs=1)


def test_her_kategori_konu_cifti_asgariyi_gecer(slotlar):
    from collections import Counter

    cift_sayim = Counter()
    for s in slotlar:
        for konu in s["konular"]:
            cift_sayim[(s["kategori_grubu"], konu)] += 1
    for kategori in KATEGORI_GRUPLARI:
        for konu in KONULAR:
            if kategori == AKSESUAR_GRUBU and konu == AKSESUAR_YASAK_KONU:
                continue
            assert cift_sayim[(kategori, konu)] >= MIN_KATEGORI_KONU, (kategori, konu)


def test_aksesuar_beden_kalip_ve_beden_yasak(slotlar):
    for s in slotlar:
        if s["kategori_grubu"] == AKSESUAR_GRUBU:
            assert AKSESUAR_YASAK_KONU not in s["konular"]
            assert AKSESUAR_YASAK_YER_TUTUCU not in s["yer_tutucu"]


def test_duygu_puan_ve_uslupten_dogru_turetilir(slotlar):
    for s in slotlar:
        if s["puan"] == 3:
            assert s["duygu"] == "karisik"
        elif s["puan"] >= 4:
            beklenen = "olumsuz" if s["uslup"] == "celiskili" else "olumlu"
            assert s["duygu"] == beklenen
        else:
            beklenen = "olumlu" if s["uslup"] == "celiskili" else "olumsuz"
            assert s["duygu"] == beklenen


def test_kategori_esit_dagitilir(slotlar):
    from collections import Counter

    sayim = Counter(s["kategori_grubu"] for s in slotlar)
    assert set(sayim) == set(KATEGORI_GRUPLARI)
    for kategori in KATEGORI_GRUPLARI:
        assert sayim[kategori] == 4000 // len(KATEGORI_GRUPLARI)


def test_deterministik(partiler):
    tekrar = parti_tanimlari()
    assert tekrar == partiler


def test_parti_dosyasi_yaz(tmp_path, partiler):
    hedef = tmp_path / "test_partiler.json"
    donen = parti_dosyasi_yaz(partiler, yol=hedef)
    assert donen == hedef
    assert hedef.exists()
    yuklenen = json.loads(hedef.read_text(encoding="utf-8"))
    assert yuklenen == partiler


def test_parti_dosyasi_yaz_varsayilan_hedef():
    from perakende_veri.v4.crm.kutuphane import KUTUPHANE_PARTILERI_YOLU

    assert KUTUPHANE_PARTILERI_YOLU.name == "kutuphane_partileri.json"
    assert KUTUPHANE_PARTILERI_YOLU.parent.name == "crm"


# ---------------------------------------------------------------------------
# denetle — yardımcı: geçerli minimal kayıt
# ---------------------------------------------------------------------------

def _kayit(**over):
    temel = {
        "id": "Y0001",
        "kategori_grubu": "Üst Giyim",
        "puan": 5,
        "duygu": "olumlu",
        "konular": ["genel_begeni"],
        "metin": "Kumaşı gerçekten kaliteli, bedeni de tam oturdu, çok memnun kaldım bu üründen.",
        "yer_tutucu": [],
        "uslup": "duz",
        "alt_kategori": None,
    }
    temel.update(over)
    return temel


def _cesitli_gecerli_kayitlar(n=30):
    """Küçük ama şema/uzunluk/türkçe/tekrar denetimlerini geçen çeşitli metinler."""
    kelimeler = [
        "kumaş", "kalite", "beden", "kalıp", "renk", "kargo", "hızlı",
        "fiyat", "değer", "iade", "süreç", "genel", "beğeni", "ürün",
        "gerçekten", "oldukça", "biraz", "oldukça", "tam", "olarak",
        "memnun", "kaldım", "tavsiye", "ederim", "şaşırdım", "güzel",
        "hoş", "şık", "rahat", "kullanışlı",
    ]
    kayitlar = []
    for i in range(n):
        parca = " ".join(kelimeler[i % 5: i % 5 + 10] + [str(i)])
        kayitlar.append(_kayit(
            id=f"Y{i + 1:04d}",
            metin=f"Ürün hakkında düşüncelerim şöyle: {parca} deneyim oldu diyebilirim.",
        ))
    return kayitlar


# ---------------------------------------------------------------------------
# denetle — geçerli girdi
# ---------------------------------------------------------------------------

def test_denetle_gecerli_kayitlarda_temiz_gecer():
    sonuc = denetle(_cesitli_gecerli_kayitlar(30))
    assert sonuc["gecerli"] is True
    assert sonuc["hatalar"] == []
    assert sonuc["olcumler"]["kayit_sayisi"] == 30


def test_denetle_bos_liste_gecersiz():
    sonuc = denetle([])
    assert sonuc["gecerli"] is False
    assert sonuc["hatalar"]


# ---------------------------------------------------------------------------
# denetle — her ihlal türü için sentetik bozuk örnek
# ---------------------------------------------------------------------------

def test_denetle_eksik_alan_yakalar():
    kayit = _kayit()
    del kayit["metin"]
    sonuc = denetle([kayit])
    assert sonuc["gecerli"] is False
    assert any("eksik alan" in h for h in sonuc["hatalar"])


def test_denetle_tekrarli_id_yakalar():
    kayitlar = [_kayit(id="Y0001"), _kayit(id="Y0001", metin="Bambaşka bir yorum metni burada yer alıyor işte.")]
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("tekrarlayan id" in h for h in sonuc["hatalar"])


def test_denetle_gecersiz_puan_yakalar():
    sonuc = denetle([_kayit(puan=7)])
    assert sonuc["gecerli"] is False
    assert any("gecersiz puan" in h for h in sonuc["hatalar"])


def test_denetle_gecersiz_duygu_yakalar():
    sonuc = denetle([_kayit(duygu="mutlu")])
    assert sonuc["gecerli"] is False
    assert any("gecersiz duygu" in h for h in sonuc["hatalar"])


def test_denetle_gecersiz_uslup_yakalar():
    sonuc = denetle([_kayit(uslup="komik")])
    assert sonuc["gecerli"] is False
    assert any("gecersiz uslup" in h for h in sonuc["hatalar"])


def test_denetle_gecersiz_konu_yakalar():
    sonuc = denetle([_kayit(konular=["bilinmeyen_konu"])])
    assert sonuc["gecerli"] is False
    assert any("gecersiz konular" in h for h in sonuc["hatalar"])


def test_denetle_bos_konu_yakalar():
    sonuc = denetle([_kayit(konular=[])])
    assert sonuc["gecerli"] is False
    assert any("gecersiz konular" in h for h in sonuc["hatalar"])


def test_denetle_aksesuar_beden_kalip_konu_yasak():
    sonuc = denetle([_kayit(kategori_grubu="Aksesuar", konular=["beden_kalip"])])
    assert sonuc["gecerli"] is False
    assert any("Aksesuar icin yasak konu" in h for h in sonuc["hatalar"])


def test_denetle_aksesuar_beden_yer_tutucu_yasak():
    sonuc = denetle([_kayit(
        kategori_grubu="Aksesuar",
        konular=["renk"],
        yer_tutucu=["beden"],
        metin="Çantanın {beden} ölçüsü tam istediğim gibiydi, çok memnunum.",
    )])
    assert sonuc["gecerli"] is False
    assert any("Aksesuar icin yasak yer_tutucu" in h for h in sonuc["hatalar"])


def test_denetle_yer_tutucu_metinde_eksikse_yakalar():
    sonuc = denetle([_kayit(yer_tutucu=["renk"], metin="Ürün gayet güzeldi, tekrar alırım kesinlikle.")])
    assert sonuc["gecerli"] is False
    assert any("metinde yok" in h for h in sonuc["hatalar"])


def test_denetle_bildirilmemis_yer_tutucu_yakalar():
    sonuc = denetle([_kayit(yer_tutucu=[], metin="Ürünün {renk} tonu fotoğraftakinden farklı çıktı ama güzel.")])
    assert sonuc["gecerli"] is False
    assert any("bildirilmemis yer_tutucu" in h for h in sonuc["hatalar"])


def test_denetle_tam_tekrar_orani_asilinca_yakalar():
    kayitlar = _cesitli_gecerli_kayitlar(20)
    # bir kısmını birebir aynı metinle değiştir (%1 eşiğini aşacak kadar)
    for i in range(1, 6):
        kayitlar[i]["metin"] = kayitlar[0]["metin"]
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("tam metin tekrar orani" in h for h in sonuc["hatalar"])


def test_denetle_yakin_tekrar_orani_asilinca_yakalar():
    taban = (
        "Bu ürünü geçen hafta sipariş ettim ve kargo çok hızlı geldi, "
        "kalitesi de gayet iyiydi diyebilirim"
    )
    kayitlar = []
    for i in range(20):
        if i < 10:
            metin = taban + f" ek not {i}"
        else:
            metin = f"Farklı bir cümle grubu {i} ile hiçbir ortak beş kelimesi olmayan tamamen ayrı bir metin yazıyorum burada."
        kayitlar.append(_kayit(id=f"Y{i + 1:04d}", metin=metin))
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("yakin tekrar orani" in h for h in sonuc["hatalar"])
    assert sonuc["olcumler"]["yakin_tekrar_orani"] > 0.02


def test_denetle_kisa_medyan_yakalar():
    kayitlar = [_kayit(id=f"Y{i + 1:04d}", metin="Çok kısa.") for i in range(10)]
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("kelime medyani" in h for h in sonuc["hatalar"])


def test_denetle_uzun_medyan_yakalar():
    uzun_metin = " ".join(["kelime"] * 30)
    kayitlar = [_kayit(id=f"Y{i + 1:04d}", metin=uzun_metin) for i in range(10)]
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("kelime medyani" in h for h in sonuc["hatalar"])


def test_denetle_turkce_karakter_orani_dusukse_yakalar():
    kayitlar = _cesitli_gecerli_kayitlar(20)
    for k in kayitlar:
        k["metin"] = "urun gayet iyi geldi, begendim, kargo da hizliydi bu sefer ok oldu"
        k["uslup"] = "duz"
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("turkce karakter orani" in h for h in sonuc["hatalar"])


def test_denetle_yazim_hatali_uslup_turkce_karakter_istisna():
    kayitlar = _cesitli_gecerli_kayitlar(20)
    for k in kayitlar:
        k["metin"] = "urun gayet iyi geldi begendim kargo da hizliydi bu sefer ok oldu tesekkurler"
        k["uslup"] = "yazim_hatali"
    sonuc = denetle(kayitlar)
    # yazim_hatali disi metin olmadigindan turkce_karakter_orani olcumu
    # uretilmez / hataya donusmez
    assert not any("turkce karakter orani" in h for h in sonuc["hatalar"])


def test_denetle_etiket_dengesi_yalniz_tam_esikte_kontrol_edilir():
    kayitlar = _cesitli_gecerli_kayitlar(30)
    for k in kayitlar:
        k["puan"] = 5
        k["duygu"] = "olumlu"
    sonuc_kucuk = denetle(kayitlar, tam_esik=1000)
    assert not any("dagilimi hedeften sapiyor" in h for h in sonuc_kucuk["hatalar"])

    sonuc_zorlanmis = denetle(kayitlar, tam_esik=10)
    assert any("dagilimi hedeften sapiyor" in h for h in sonuc_zorlanmis["hatalar"])


def test_denetle_kategori_konu_kapsama_esigi_tam_esikte_kontrol_edilir():
    kayitlar = _cesitli_gecerli_kayitlar(30)
    for k in kayitlar:
        k["konular"] = ["genel_begeni"]
    sonuc_zorlanmis = denetle(kayitlar, tam_esik=10)
    assert not sonuc_zorlanmis["gecerli"]
    assert any("cifti icin yalniz" in h for h in sonuc_zorlanmis["hatalar"])


def test_denetle_jsonl_yolundan_okur(tmp_path):
    kayitlar = _cesitli_gecerli_kayitlar(15)
    yol = tmp_path / "mini_kutuphane.jsonl"
    with open(yol, "w", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
    sonuc = denetle(yol)
    assert sonuc["gecerli"] is True
    assert sonuc["olcumler"]["kayit_sayisi"] == 15


# ---------------------------------------------------------------------------
# ornek_metin_yazdir
# ---------------------------------------------------------------------------

def test_ornek_metin_yazdir_n_kayit_doner():
    kayitlar = _cesitli_gecerli_kayitlar(30)
    ornekler = ornek_metin_yazdir(kayitlar, n=5, tohum=1)
    assert len(ornekler) == 5
    for o in ornekler:
        assert "metin" in o and "puan" in o and "duygu" in o


def test_ornek_metin_yazdir_deterministik():
    kayitlar = _cesitli_gecerli_kayitlar(30)
    a = ornek_metin_yazdir(kayitlar, n=8, tohum=42)
    b = ornek_metin_yazdir(kayitlar, n=8, tohum=42)
    assert a == b


def test_ornek_metin_yazdir_n_kutuphaneden_buyukse_sinirlar():
    kayitlar = _cesitli_gecerli_kayitlar(5)
    ornekler = ornek_metin_yazdir(kayitlar, n=100, tohum=1)
    assert len(ornekler) == 5


# ---------------------------------------------------------------------------
# YAZAR_YONERGESI
# ---------------------------------------------------------------------------

def test_yazar_yonergesi_turkce_ve_anahtar_kurallari_icerir():
    assert isinstance(YAZAR_YONERGESI, str)
    assert "celiskili" in YAZAR_YONERGESI
    assert "{renk}" in YAZAR_YONERGESI
    assert "{beden}" in YAZAR_YONERGESI
    assert "Aksesuar" in YAZAR_YONERGESI


# ---------------------------------------------------------------------------
# Fix round 1: yaygin sablon, duygu tutarliligi, bozuk JSONL satiri
# ---------------------------------------------------------------------------

def test_denetle_yaygin_sablon_sessizce_gecmez():
    """501+ kayit ayni sablonu paylasiyorsa (shingle sinirini asar) gecerli
    olmamali; atlanan shingle sayisi olcumlerde raporlanmali."""
    sablon = "bu urunu aldim ve gercekten cok memnun kaldim tavsiye ederim herkese"
    kayitlar = []
    for i in range(600):
        metin = f"{sablon} benzersiz{i}a benzersiz{i}b"
        kayitlar.append(_kayit(id=f"Y{i + 1:04d}", metin=metin))
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert sonuc["olcumler"]["atlanan_yaygin_shingle"] > 0
    assert any("yaygin" in h or "yakin tekrar" in h for h in sonuc["hatalar"])


def test_denetle_duygu_puan_kuralina_uymuyorsa_yakalar():
    kayitlar = _cesitli_gecerli_kayitlar(10)
    kayitlar[3]["puan"] = 1          # kural: olumsuz, kayit olumlu diyor
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("duygu" in h and "Y0004" in h for h in sonuc["hatalar"])


def test_denetle_duygu_kurali_puan3_celiskili_dogru_kabul_eder():
    kayitlar = _cesitli_gecerli_kayitlar(10)
    kayitlar[0].update(puan=3, duygu="karisik")
    kayitlar[1].update(puan=5, duygu="olumsuz", uslup="celiskili")
    kayitlar[2].update(puan=1, duygu="olumlu", uslup="celiskili")
    sonuc = denetle(kayitlar)
    assert not any("duygu" in h for h in sonuc["hatalar"])


def test_denetle_bozuk_jsonl_satiri_hata_olur_ve_devam_eder(tmp_path):
    kayitlar = _cesitli_gecerli_kayitlar(12)
    yol = tmp_path / "bozuk.jsonl"
    with open(yol, "w", encoding="utf-8") as f:
        for i, k in enumerate(kayitlar):
            if i == 4:
                f.write("{bozuk json satiri\n")
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
    sonuc = denetle(yol)
    assert sonuc["gecerli"] is False
    assert any("satir 5" in h for h in sonuc["hatalar"])
    assert sonuc["olcumler"]["kayit_sayisi"] == 12


# ---------------------------------------------------------------------------
# Görev 10b: alt_kategori ve gerçek renk adı denetimi
# ---------------------------------------------------------------------------

def test_alt_kategori_zorunlu_anahtar():
    kayit = _kayit()
    del kayit["alt_kategori"]
    sonuc = denetle([kayit])
    assert any("eksik alan" in h and "alt_kategori" in h for h in sonuc["hatalar"])


def test_alt_kategori_null_ve_gecerli_kabul():
    kayitlar = _cesitli_gecerli_kayitlar(10)
    kayitlar[0].update(alt_kategori="Gömlek")           # Üst Giyim
    kayitlar[1].update(kategori_grubu="Aksesuar", alt_kategori="Çanta")
    sonuc = denetle(kayitlar)
    assert not any("alt_kategori" in h for h in sonuc["hatalar"])


def test_alt_kategori_yanlis_gruptan_hata_id_ile():
    kayitlar = _cesitli_gecerli_kayitlar(10)
    kayitlar[2].update(alt_kategori="Çanta")            # Üst Giyim'de Çanta yok
    kayitlar[3].update(alt_kategori="Bilinmeyen")
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("alt_kategori" in h and "Y0003" in h for h in sonuc["hatalar"])
    assert any("alt_kategori" in h and "Y0004" in h for h in sonuc["hatalar"])


@pytest.mark.parametrize("metin", [
    "Haki tonu çok güzel duruyor", "Siyahı çok şık", "Sarısı canlı",
    "altın rengi detaylar var", "Altın Rengi toka", "yesil olanı aldim",
    "sari renk", "kirmizi cok guzel", "KIRMIZI", "Kırmızı elbise", "SARI",
    "Lacivert ve bej uyumlu", "kahverengi tonlar", "kahve tonu güzel",
    "petrol rengi harika", "zümrüt yeşili", "zumrut gibi", "mercan rengi",
    "vişne çürüğü tonu", "visne", "kavuniçi", "kavunici ton", "kamel rengi",
    "şarap rengi", "sarap tonu", "nar çiçeği rengi", "fıstık yeşili",
    "sapsarı geldi", "masmavi", "kapkara", "yemyeşil", "bembeyaz", "kıpkırmızı",
    "mosmor", "pespembe", "simsiyah", "sapsari", "kipkirmizi", "yemyesil",
    "kemerin kahvesi", "koyu kahve", "açık kahve", "kahve, koyu kahve", "sarı", "sarısı", "sarıya yakın", "sarıydı", "sarımsı ton", "gri melanj kumaş", "İndigo ton", "füme renk",
    "pudra pembesi", "taba rengi sapı", "mor renk", "gümüşi ton",
])
def test_renk_adi_yakalanir(metin):
    assert renk_adlari_bul(metin), metin


@pytest.mark.parametrize("metin", [
    "moralim düzeldi", "Morali yerine geldi", "grip oldum ama kargo geldi",
    "altına giydim", "altında tişört var",
    "petrolle lekelendi", "kahve içerken döktüm", "hakikaten rahat",
    "hakiki deri gibi", "sarıldım hemen", "tabanı kaymıyor", "tabak gibi",
    "mintan yakası", "zeytinyağı lekesi", "{renk} tonu çok güzel",
    "{renk} rengi tam aradığım gibiydi", "rengi ve tonu çok güzel",
    "{beden} bedeni oturdu", "kahve içerken", "kahve molası verdik",
    "kahvemi döktüm", "kahve lekesi", "şarap lekesi", "nar gibi tatlı bir kumaş",
    "masa başında", "mesai bitti", "kaprisli kumaş", "yemek yerken giydim",
    "bembe", "Vücudu güzel sarıyor", "Kalıbı sarıyor beni",
    "belimi sarıp durmuyor", "sarıcı bir kumaş", "sarılmak istedim",
    "kahve, ton olarak sade", "kahve. Renk güzel", "petrol; ton farklı", "Kumaşı kaliteli, kalıbı rahat",
])
def test_renk_adi_yanlis_pozitif_degil(metin):
    assert renk_adlari_bul(metin) == [], metin


def test_renk_adlari_sozlugu_a_renklerini_icerir():
    for ad in ("siyah", "haki", "bordo", "ekru", "kiremit", "yesil", "indigo",
               "gri", "lacivert", "pudra", "bej", "beyaz"):
        assert ad in RENK_ADLARI
    assert "melanj" not in RENK_ADLARI


def test_denetle_gercek_renk_adi_yakalar_id_ile():
    kayitlar = _cesitli_gecerli_kayitlar(10)
    kayitlar[5]["metin"] = "Haki tonu çok hoş duruyor, kumaşı da gayet kaliteli çıktı gerçekten."
    sonuc = denetle(kayitlar)
    assert sonuc["gecerli"] is False
    assert any("renk adi" in h and "Y0006" in h for h in sonuc["hatalar"])


def test_denetle_renk_yer_tutucusu_renk_adi_sayilmaz():
    kayit = _kayit(
        metin="{renk} rengi tam aradığım tondaydı, kumaşı da gayet kaliteli çıktı.",
        yer_tutucu=["renk"],
    )
    sonuc = denetle([kayit])
    assert not any("renk adi" in h for h in sonuc["hatalar"])


def test_yonerge_alt_kategori_ve_renk_kurallari():
    assert "alt_kategori" in YAZAR_YONERGESI
    assert "kot" in YAZAR_YONERGESI and "Jean" in YAZAR_YONERGESI
    assert "renk adı" in YAZAR_YONERGESI.lower()
