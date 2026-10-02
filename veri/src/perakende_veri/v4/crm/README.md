# Lumoda v4 — B katmanı: CRM

B, v4 çekirdeğinin (A) üstüne müşteri, fiş, online davranış ve yorum
katmanını koyar. Altı algoritmayı besler: müşteri segmentasyonu, terk
tahmini, LTV, ürün önerisi, ürün sıralama, yorum sınıflandırma.

- Tasarım: `docs/superpowers/specs/2026-09-28-veri-v4-crm-design.md`
  (§11 uygulamadaki sapmalar).
- Üretim: `python -m perakende_veri.v4.crm.uret` → `veri/cikti/v4_crm/`
  (Parquet, CSV, DuckDB).
- Tohumlar: A `2026` (değişmez), B `4242` (`crm/sabitler.py`,
  `CRM_TOHUM`). Aynı komut her zaman aynı veriyi üretir.
- A'nın verisi bu katmandan etkilenmez. B, A'yı aynı tohumla bellekte
  yeniden kurar; A'nın yayımlanan 18 tablosu bayt bayt aynı kalır.

## Kısaca nasıl çalışır

**Sonradan ayrıştırma.** B satış yaratmaz, satışa uyar. A'nın temiz
satışını (gün × mağaza × SKU) alır, kendi müşteri nüfusunu kurar, her
günün satışını fişlere, fişleri müşterilere dağıtır. Toplamlar kuruşu
kuruşuna korunur.

Bunun bilerek verilen bedeli: terk eden müşterinin bıraktığı satışı A'nın
sabit toplamı içinde başkaları üstlenir. "Müşteri kaybı satışı ne kadar
düşürür" sorusu bu katmanda cevaplanamaz.

- **Nüfus.** Yedi gizli arketip: trend avcısı, indirim avcısı, klasik
  temelci, aile alışverişçisi, premium sadık, online tutkunu, gelip geçen.
  Her müşterinin gizli tercihleri (alt kategori, kalıp, desen, fiyat
  segmenti, indirim duyarlılığı), bedeni, ziyaret hızı, sepeti, kart okutma
  olasılığı, online payı ve aylık terk olasılığı var.
- **Yaşam döngüsü.** Sözleşmesiz model (BG/NBD ailesi): katılış, gizli
  ömür, aylık terk. Stoksuzluk (60 gün ×1,5), iade (×1,2), tekrarlayan beden
  uyumsuzluğu (×1,3) ve ev mağazasının kapanması terki artırır. Terk eden
  bir daha gelmez.
- **Isınma.** Simülasyon A ile aynı gün (2022-07-04) başlar. Isınmadaki
  fişler yayımlanmaz; 2023 başında her müşterinin gizli bir geçmişi vardır.
- **Eşleştirme.** Birim, fişe ve müşteriye müşterinin tercihi, beden uyumu,
  fişteki ürünlerle tamamlayıcılık, ürünün cinsiyeti ve indirim durumuyla
  dağıtılır. İki aşamalıdır: önce ürün türü (alt kategori × fiyat segmenti ×
  beden) kesin olarak, sonra tür içinde SKU.
- **Online.** Günlük liste özeti bütün pencere için, olay kaydı 13 hafta
  için (2025-09-01 – 2025-11-30). Liste sıralaması enjekte edilebilir bir
  politikadır; tıklama modeli gizlidir.
- **Yorumlar.** Depodaki 7.000 metinlik etiketli Türkçe kütüphaneden
  (`crm/yorum_kutuphanesi.jsonl`) seçilir. Kim yazar ve neden yazar gizlidir.

## Tablolar

Yayımlanan altı tablo. Satır sayıları tam koşudan
(`python -m perakende_veri.v4.crm.uret`, tohum 4242).

| Tablo | İçerik | Satır |
|---|---|---:|
| `musteri` | Kimlikli müşteriler (kart okutmuş ya da online sipariş vermiş) | 2.106.860 |
| `fis` | Satış ve iade fişleri, mağaza + online | 16.764.655 |
| `fis_satir` | Fiş satırları | 31.923.447 |
| `online_liste_gunluk` | Gün × liste × sıra × option özeti | 609.905 |
| `online_olay` | 13 haftalık olay kaydı (yalnız Parquet) | 23.901.935 |
| `yorum` | Ürün yorumları | 74.394 |

Satır sayıları spec'in tahminlerinin üstünde (spec: musteri ~1–1,5M, fis
~10M, fis_satir ~22M). Bu bir bant değil; nüfus ve sepet kalibrasyonunun
sonucu. `fis` iade fişlerini de içerir: mağaza 10.269.867 satış + 1.371.442
iade, online 3.585.044 satış + 1.538.302 iade. `fis_satir`'ın 3.378.770'i
iade satırı; bunların 17.194'ünde orijinal ısınmada (aşağıda). `musteri`'nin
218.046'sının pencerede fişi yok (uyuyan üyeler, aşağıda).

Birimler: para TL, iki ondalık. Adetler adet. Tarihler gün, `fis.saat`
"SS:DD", `online_olay.zaman` saniyeli zaman damgası.

### Sütunlar

| Tablo | Sütunlar | Not |
|---|---|---|
| `musteri` | musteri_id, kayit_tarihi, kayit_kanali (magaza / online), ev_magaza_id, il, yas_grubu, cinsiyet | Anonim müşteri yok. `ev_magaza_id` mağaza kapanışlarından sonraki son durum. |
| `fis` | fis_id, tarih, saat, magaza_id, musteri_id, kanal (magaza / online), fis_tipi (satis / iade), adet, tutar, teslim_tarihi | Online fişlerde `magaza_id` `ONL`. `musteri_id` anonim fişte boş. `adet` ve `tutar` satırların işaretli toplamı. |
| `fis_satir` | fis_satir_id, fis_id, satir_no, urun_id, adet, birim_fiyat, tutar, indirim_tutari, kampanya_id, orijinal_fis_satir_id | İadede adet, tutar ve indirim negatif (A gibi). `orijinal_fis_satir_id` yalnız iadede dolu. |
| `online_liste_gunluk` | tarih, liste, sira, option_id, gosterim, tiklama, sepete_ekleme, satin_alma | Anahtar (tarih, liste, sira, option_id); aşağıya bakın. |
| `online_olay` | oturum_id, musteri_id, zaman, olay_tipi, liste, sira, option_id, fis_id | `olay_tipi`: liste_goruntuleme / tiklama / sepete_ekleme / siparis. `fis_id` yalnız siparişte. |
| `yorum` | yorum_id, fis_satir_id, musteri_id, urun_id, tarih, puan, metin | Yalnız online satış satırlarına. Puan 1–5. |

`birim_fiyat` = |tutar| ÷ |adet|, iki ondalık: ödenen net birim fiyat,
iadede de pozitif. Esas olan `tutar`dır; adet × birim_fiyat bir kuruş
sapabilir.

**Listeler.** A'nın option'larında dolu olan her üst kategori × cinsiyet
için `kategori:<üst>:<cinsiyet>`, `yeni_gelenler`, `indirim` ve 17 alt
kategori araması `arama:<alt>`. Görüntüleme başına ilk 48 sıra (2 × 24)
gösterilir.

A'yla birleşme: `urun_id` → A `urun`, `option_id` → A `urun.option_id`,
`magaza_id` → A `magaza`, `kampanya_id` → A `kampanya`.

## Tutarlılık sözleşmesi

- `fis_satir`'ın (tarih, mağaza, SKU) toplamı A'nın **temiz** satışını
  (iadeler dahil) adet, tutar ve indirim_tutari olarak kuruşu kuruşuna
  verir. Beş tohumda da tutuyor.
- Her iade satırı kendi orijinal satış satırına bağlıdır: aynı mağaza, aynı
  SKU, 7 gün (online 10 gün) önce. Tek istisna aşağıda.
- `online_liste_gunluk.satin_alma`, (tarih, option) düzeyinde online satış
  fiş satırlarının adedine eşittir.
- Olay kaydı penceresindeki her online satış fişi için tam bir `siparis`
  olayı vardır; aynı müşteri, aynı gün. Olay günlerinde her hücrenin
  tıklama ve sepete ekleme sayısı, her listenin görüntüleme sayısı liste
  özetiyle birebir aynıdır.
- Fiş toplamları satır toplamlarına eşittir.
- Terk etmiş müşterinin satış fişi yok, katılıştan önce fiş yok.

**Kirli kayıtların fişte karşılığı yoktur.** B, A'nın temiz satışından
çalışır. A'nın yayımlanan `satis`'indeki 200 mükerrer satır `fis_satir`'da
bir kez görünür. 120 bedelsiz satırın (`tutar` 0) fiş satırlarında ise
gerçek tutar durur. Yani `fis_satir` toplamını yayımlanan `satis`'le
karşılaştıran biri tam bu satırlarda fark bulur. Bu bir veri kalitesi
dersidir: aynı satışı iki sistem iki farklı biçimde kaydetmiş olur.

## Kimlik ve anonimlik

- **Mağaza satış fişi** müşterinin gizli kart okutma olasılığıyla kimlikli
  ya da anonim olur. Kart okutma payı ~%58 (aşağıdaki bantlar). Anonim
  fişte `musteri_id` boştur; fişin gerçek sahibi gizli gerçektedir
  (`anonim_fis_sahibi`). Gerçek sahip kart okutmadığı başka bir gün
  kimlikli görünen bir müşteri olabilir.
- **Online fişlerin hepsi kimliklidir.**
- **Mağaza iade fişi**, orijinal satış fişlerinden biri kimlikliyse
  kimliklidir.
- Aynı müşteri iki kanalda aynı `musteri_id` ile görünür.
- `musteri` yalnız kimlikli müşterileri taşır: ilk kimlikli olayı pencere
  sonuna kadar olan herkes. **Isınmada görünür olup 2023'ten önce terk
  eden uyuyan üyeler de tabloda.** Bunların pencerede fişi yoktur; gerçek
  bir CRM'de de müşteri kaydı silinmez.
- Hiç kimlikli fişi olmayan müşteri tabloda yok.
- `online_olay`'da oturumların %60'ı giriş yapmıştır. Sipariş oturumu her
  zaman giriş yapmıştır (müşteri = fişin sahibi). Giriş yapmış tarama
  oturumunun müşterisi, o gün hayatta ve o güne kadar görünür olmuş online
  müşterilerden çekilir. Anonim oturumda `musteri_id` boş.
- Kişisel veri yok: ad, e-posta, telefon üretilmez. İl ve yaş grubu
  yeterli.

Kimlik biçimleri: müşteri `K0000001`, fiş `F00000001` (tarih, saat
sırasıyla), satır `FS000000001`, yorum `Y0000001`. `oturum_id` tam sayı.

## Dikkat edilecek yerler

- **İade fişi kapanmış mağazada görünebilir.** A, kapanıştan (ya da
  tadilattan) önceki satışın iadesini mağazanın hücresine yazar; B iade
  fişini orijinal mağazada keser. A'nın yayımlanan satış satırlarıyla
  tutarlıdır. "Kapalı mağazada fiş yok" kuralı yalnız satış fişleri
  içindir.
- **Terkten sonra iade.** A'da iade satıştan kesin 7 (online 10) gün sonra
  doğar. Terkten hemen önceki alışverişin iadesi terk gününden sonra
  gelebilir; iade o müşteride kalır.
- **Isınmadaki satışın iadesi.** Pencerenin ilk günlerindeki (2023-01-11'den
  önce) bazı iadelerin orijinali ısınmadadır, yayımlanmaz. Bu iadelerde
  `orijinal_fis_satir_id` boştur.
- **`fis.teslim_tarihi`** yalnız online satış fişinde doludur. Teslimi
  2025-12-31'den sonraya kalanın boştur (A'nın `gerceklesen_teslim`
  kuralı). Gecikme bayrağı gizlidir; yorumların kargo nedeni teslim
  süresinden kısmen okunur.
- **Enjekte hücre.** Listede olmayan ama satın alınan option (gün içinde
  stoğa giren, listeden düşmüş) `arama:<alt>` listesinin 1. sırasına
  eklenir. Aynı (tarih, liste, sıra 1)'de iki option olabilir. Anahtar
  (tarih, liste, sira, option_id)'dir. Bu yüzden sıralama öğrenirken
  `kategori:` listeleri daha temizdir.
- **Sadakat indirimi yok.** Spec, işlem indirimli birimlerin kartlı
  müşterilere daha olası dağıtılmasını istiyordu. A, işlem indirimini
  hücre-gün satırının tamamına uygular; satırdaki her birim aynı fiyattadır.
  B birimleri kartlıya kaydırırsa A'nın tutarı bozulur. Fiş satırları
  indirim durumunu A'nın satırından alır.
- **Kapanan ev mağazası.** Müşterilerin bir kısmı en yakın mağazaya geçer.
  Geçmeyenlerin terk olasılığı ×2, online payı ×2 olur (ilde başka mağaza
  olsa bile).
- **Hediye alımı.** Kartlı giyim birimlerinin ~%9'u müşterinin kendi
  cinsiyetinin dışında bir ürün (aksesuarda ~%25). Giyimde bunlar hediye
  sayılır ve yorum yazmaz (Unisex ve aksesuar bu kuralın dışında).
- **2026 LTV kısıtsız.** Gizli 2026 LTV, 2025 sonu nüfusunu kendi gizli
  hızıyla bir yıl ileri simüle eder; arkasında A'nın satışı yok. Bu yüzden
  2026 ziyareti 2025'te gerçekleşenden yüksektir. Sıralamaya dayalı
  ölçütler (Spearman) etkilenmez.

## Yorumlar

Kütüphane 7.000 etiketli Türkçe metin. Etiketler: üst kategori grubu,
puan, duygu, konular (beden/kalıp, kumaş/kalite, renk, kargo/teslimat,
fiyat/değer, iade süreci, genel beğeni). Gizli alanlar: `alt_kategori`
(metin ürün türünü adıyla anıyorsa yalnız o türe gider), `cinsiyet_ipucu`,
`yas_ipucu` (yalnız uyan müşteriye gider).

- İlk 4.000 metin için kullanıcı 20 örnekle üslup onayı verdi. Sonra
  talebe göre ağırlıklı 3.000 metin eklendi (kategori, alt kategori, puan,
  konu).
- Metinlerde gerçek renk, beden, mevsim, özel gün ya da şehir adı yok.
  Renk ve beden `{renk}`, `{beden}` yer tutucusuyla SKU'dan gelir.
- Aynı metin en fazla 25 kez kullanılır.
- **Kim yazar (gizli).** Online satış satırı başına taban olasılık × gizli
  nedenlerin çarpanı. Nedenler: hatalı tedarikçi (tedarikçinin hatalı
  oranı üst çeyrekte) ×1,5 → kumaş/kalite; beden uyumsuzluğu ×2 →
  beden/kalıp (iade edildiyse iade süreci de); geciken teslimat ×1,8 →
  kargo; indirim ≥ %50 ×1,2 → fiyat/değer.
- Olumsuz nedenli yorum 1–3 puan alır; nedensiz ya da yalnız fiyat
  nedenli yorum 4–5. Uyan metin kalmazsa puan ±1 kayabilir.
- Yorum tarihi teslimden 1–10 gün sonra.
- Çelişki süzgeci: iade anlatan metin yalnız iade edilmiş satıra, olumsuz
  kargo metni yalnız geciken satıra, "indirimde aldım" diyen metin yalnız
  indirimli satıra gider.

## Gizli gerçek

Yayımlanan tablolara girmez, `uret` yazmaz. Vakalar kendi koşularında
üretir:

```python
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.crm.uret import tablolari_uret_crm

tablolar, ham = tablolari_uret_crm(Olcek.TAM, donus_ham=True)
gizli = ham.gizli_gercek()        # crm_gizli_gercek(...)
```

| Anahtar | İçerik |
|---|---|
| `musteri_gizli` | Her müşteri (nüfus satırı): arketip, bütün gizli parametreler ve tercih vektörleri, hayatta, terk ve görünür olma tarihi, tetik durumu |
| `anonim_fis_sahibi` | fis_id, musteri, musteri_id: anonim fişin gerçek sahibi |
| `bos_ziyaret` | tarih, magaza_id, musteri, musteri_id, urun_id, adet: stoksuzluk yüzünden alınamayan birimler (fişte yok) |
| `terk` | musteri, musteri_id, terk_tarihi |
| `ltv_2026` | Hayatta olma olasılığı, analitik ve gerçekleşen 2026 ziyaret ve harcaması, `geri_gelecek_2026` |
| `tiklama_modeli` | Bakılma eğrisi, tıklama sabiti, option × arketip ilgisi, günlük ilgi, enjekte hücreler |
| `yorum_etiket` | Kütüphane kimliği, gerçek konular, duygu, nedenler, üslup |
| `kargo_gecikme` | fis_id, kesilmemiş teslim tarihi, teslim süresi, gecikme |
| `fis_satir_gizli` | Satır başına beden uyumsuz adet ve işlem indirimli adet |

Gizli tablolarda `musteri` nüfus indisidir (her müşteri). `musteri_id`
yayımlanan kimliktir, hiç görünür olmamış müşteride boştur.

Tam koşu ~20 GB bellek ister. Denemeler için `Olcek.KUCUK` var; bantlar
yalnız TAM'da anlamlıdır.

## Sıralama politikası enjeksiyonu

Online listelerin sıralaması dışarıdan verilebilir. Politika
`siralama(g) -> {liste: option dizisi}` imzasında bir fonksiyondur. `g` bir
`GunGorunum`'dur ve yalnız o sabah bilinen yayımlanabilir veriyi taşır:
liste adları, option'ın kategori ve arama listesi, uygunluk (depo stoğu
> 0, satış penceresinde, ONL'de satılır), son 7 günün online satışı,
lansman günü, online indirim oranı.

```python
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.crm.online import online_uret, lumoda_siralama
from perakende_veri.v4.crm.tablolar import crm_tablolari
from perakende_veri.v4.crm.uret import tablolari_uret_crm

def benim_siralama(g):
    """g bir GunGorunum; liste başına option dizisi döner."""
    return {ad: dizi[::-1] for ad, dizi in lumoda_siralama(g).items()}

_, ham = tablolari_uret_crm(Olcek.TAM, donus_ham=True)
online = online_uret(ham.girdi, ham.crm, ham.tohum, siralama=benim_siralama)
tablolar = crm_tablolari(ham.girdi, ham.crm, online, ham.yorumlar, hazir=ham.hazir)
```

**Lumoda'nın sıralaması** (`lumoda_siralama`): kategori ve arama listeleri
son 7 günün online satışına göre azalan. Yeni ürünün satışı olmadığı için
alta düşer; bu bilerek duran bir geri besleme döngüsüdür. `yeni_gelenler`
son 28 günün lansmanları, yeni önce. `indirim` online indirim oranına göre.
Depoda stoğu biten option listeden kalkar.

- Motor her listeyi 48'e keser, dönen her option'ın uygun olduğunu
  doğrular.
- **Satın almalar sıralamadan bağımsızdır:** A'nın online satışı sabittir.
  Sıralama yalnız gösterim, tıklama ve sepete eklemeyi değiştirir; sipariş
  olayları aynı kalır.
- Gerçek tıklama modeli aynıdır: tıklama sabiti bir kez, Lumoda'nın
  sıralamasıyla ayarlanır. Başka politika aynı sabitle koşar.
- **Politika gizli gerçeği okumaz.** Bu bir sözleşmedir, kodla zorlanmaz.

## Kalibrasyon bantları

Tam koşuda, yayımlanan tablolardan ölçülür
(`tests/v4/crm/test_crm_kalibrasyon.py`, `-m yavas`). Yayımlanan tohum
4242 ve dört tohum daha (1, 2, 3, 4); A hep 2026. Kaynak:
`veri/araclar/v4_crm_cok_tohum.py` (commit 1fc8a2a).

| Ölçüt | Bant | Tohum 4242 | 5 tohumda aralık | Geçen |
|---|---|---|---|---|
| Mağazada kart okutma payı | %50–60 | 0,5758 | 0,5751–0,5758 | 5/5 |
| Fiş başına adet: mağaza | 2,0–2,5 | 2,212 | 2,212 | 5/5 |
| Fiş başına adet: online | 1,6–2,0 | 1,809 | 1,809 | 5/5 |
| Kartlı müşteri yıllık ziyaret | 2,5–4 | 3,170 | 3,164–3,170 | 5/5 |
| Ertesi yıl dönme oranı | %45–65 | 0,5557 | 0,5556–0,5562 | 5/5 |
| Yeni müşterinin yıllık aktif payı | %25–40 | 0,2780 | 0,2776–0,2781 | 5/5 |
| Online satırlarda yorum oranı | %0,9–1,5 (karar; spec %4–8) | 0,0117 | 0,0117 | 5/5 |
| Yorum ortalama puanı | 4,0–4,4 | 4,179 | 4,171–4,187 | 5/5 |
| Giriş yapmış oturum payı | %55–65 | 0,6000 | 0,6000 | 5/5 |

İzleme satırları (bant değil, 4242): yorum sayısı 74.394 (hedef 60–80 bin) ·
hatalı tedarikçide kalite konulu yorum katı 2,5 (≥ 2) · çapraz cinsiyet
payı giyimde %9,3 (%8–15), aksesuarda %24,7 · tutarlılık sözleşmesi 5/5.

Tanımlar kısaca. "Aktif": o yıl en az bir kartlı satış fişi olan müşteri
(mağaza ya da online). Yıllık ziyaret: Σ kartlı satış fişi ÷ Σ yıllık
aktif; online siparişler dahil, 2023–2025 havuzlanmış. Dönme: Y'nin
aktiflerinden Y+1'de de aktif olanların payı. Yeni payı: Y'nin
aktiflerinde `kayit_tarihi` Y içinde olanların payı. Yorum oranı: yorum ÷
penceredeki online satış satırı.

Yıl yıl (4242): ziyaret 3,011 / 3,161 / 3,321 · dönme 2023→24 0,542,
2024→25 0,569 · yeni payı 0,260 / 0,270 / 0,302.

## Öğrenilebilirlik

`tests/v4/crm/test_crm_ogrenilebilirlik.py` (`-m yavas`). Öğrenen yalnız
B'nin altı tablosunu ve A'nın `urun`'unu okur; gizli gerçek yalnız puanlar.

| Algoritma | Yöntem | Ölçüt | Hedef | Tohum 4242 | 5 tohumda aralık | Geçen |
|---|---|---|---|---|---|---|
| Segmentasyon | ≥ 3 kartlı fişi olanlar; RFM + 17 alt kategori payı + indirimli satır payı + online payı, k-means (7) | gizli arketipe ARI | ≥ 0,08 (karar; spec 0,3–0,7) | 0,0954 | 0,0923–0,0954 | 5/5 |
| Terk | RFM üzerinde lojistik regresyon, 5 kat | "2026'da gelecek mi" AUC | 0,70–0,85 | 0,8179 | 0,8172–0,8179 | 5/5 |
| LTV | 2025 harcaması × P(geri gelir) | gerçekleşen 2026 harcamasıyla Spearman | 0,4–0,7 | 0,6363 | 0,6353–0,6363 | 5/5 |
| Öneri | ürün–ürün birlikte alım (kosinüs) | son sepette recall@10 ÷ popülerlik | ≥ 1,2 | 1,892 | 1,863–1,892 | 5/5 |
| Sıralama | konum yanlılığı düzeltmeli (IPS) tıklama oranı | gerçek ilgiyle Spearman, IPS − saf | ≥ 0,1 | 0,1546 | 0,1534–0,1546 | 5/5 |
| Yorum konuları | TF-IDF + lojistik, metin grubuna göre bölme | makro F1 | ≥ 0,60 (karar; spec 0,60–0,85) | 0,9560 | 0,9465–0,9696 | 5/5 |

- **Segmentasyon zor.** Gizli parametrelerle k-means ARI'si 0,94'tür:
  arketipler iyi tanımlı. Gözlenen davranıştan ise 0,09 çıkar. Nedeni
  gözlenen kategori paylarının sınırlı olmasıdır. Müşteri yalnız o gün o
  mağazada satılanı alabilir (A'nın satışı sabit), müşteri başına ~7–10
  birim 17 alt kategoriye bölünür. Kalibrasyon düğmeleriyle 0,3'e
  ulaşılamadı. Sepet ve birim fiyat özellik olarak eklenince ARI 0,17–0,23.
- **İndirim avcısı görünür.** Gizli indirim duyarlılığı ile indirimli satır
  payı arasındaki korelasyon 0,53.
- **Arketipler belirgin.** Örnek ortalamalar: online tutkununun online payı
  0,94, klasiğin 0,03; premium yılda 8,2 ziyaret, gelip geçen 0,84;
  indirim avcısının indirim duyarlılığı 0,94, premium'un 0,06.
- **Yorum konuları kolay.** Kütüphane konuları açık yazar, F1 ~0,95–0,97
  bu tasarımın sonucu. Aynı metin farklı müşterilerde tekrarlandığından
  müşteriye göre bölmek ezberi ödüllendirir (F1 0,998). Bu yüzden birincil
  bölme metin grubuna göredir: yer tutucular geri çevrilip aynı kütüphane
  metninden gelen yorumlar aynı tarafa düşer.
- **Sıralama.** Saf tıklama oranının gerçek ilgiyle Spearman'ı 0,83, IPS
  düzeltmesiyle 0,98.
- **Öneri** 200 bin müşterilik sabit bir örneklemde ölçülür: recall@10 0,211,
  popülerlik 0,111.

## Tohuma duyarlılık

B'nin bütün ölçütleri beş tohumda üçüncü ondalıkta ayrılır; tohum
gürültüsü bantların genişliğinin çok altındadır. En geniş aralık yorum F1'de
(0,9465–0,9696) ve segmentasyonun ikincil "+ sepet ve birim fiyat"
satırında (0,169–0,233). Yazılardaki sayılar yayımlanan tohumdan (4242)
gelir.

## Spec'ten sapmalar

Ayrıntı ve gerekçeler spec §11'de. Kısaca:

- Eşleştirme iki aşamalı (tür düzeyinde kesin, tür içinde SKU): hız için.
- Sadakat indirimi eğilimi yok (yukarıda).
- Yorum oranı bandı %4–8 yerine %0,9–1,5; kütüphane ~4.000 yerine 7.000.
- Segmentasyon bandı 0,3–0,7 yerine ARI ≥ 0,08; yorum F1 bandı ≥ 0,60.
- Müşteri–ürün cinsiyet uyumu ve hediye alımı eklendi.
- `fis.teslim_tarihi` ve `fis_satir.fis_satir_id` yayımlanır.
- Satır sayıları spec tahminlerinin üstünde.

## Üretim süresi ve bellek

Son tam koşu (tohum 4242, boş makine): A kurulumu 168 sn (B'ye sayılmaz),
B 898 sn yazma hariç (simülasyon 834, online 27, kargo + yorum 10, tablolar
25), yazma 98 sn (Parquet 27, DuckDB 57, CSV 14); B toplam 997 sn = 16,6 dk.
Beş tohumluk koşuda B 832–911 sn (yazma hariç), eşleştirme 10,7–11,8 dk.

**Bellek:** tohum başına süreç tepesi ~20 GB. **~20 GB boş bellek gerekir.**
Başka uygulamalar ~10 GB tutarken sayfalama başlıyor ve B 20 dakikayı
aşabiliyor (ölçülen en kötü 2.186 sn, ~36 dk).

Çıktı (`veri/cikti/v4_crm/`): Parquet 888 MB (en büyüğü `fis_satir` 437 MB, `online_olay` 211 MB), CSV
3.146 MB (`online_olay` hariç; `fis_satir.csv` 1,97 GB), DuckDB 1.216 MB.

## Dağıtım

Mevcut `veri-v4` release'ine eklenecek dört varlık (A'nınkiler değişmez):

| Varlık | İçerik | Boyut |
|---|---|---:|
| `lumoda-v4-crm.duckdb` | Altı tablo (olay kaydı dahil) | 1.216 MB |
| `lumoda-v4-crm-parquet.zip` | Beş tablo, Parquet (olay kaydı hariç) | 345 MB |
| `lumoda-v4-crm-csv.zip` | Beş tablo, CSV (olay kaydı hariç) | 569 MB |
| `lumoda-v4-olay-parquet.zip` | `online_olay.parquet` | 163 MB |

Zip'ler klasörsüz. Olay kaydı yalnız Parquet'tir ve kendi zip'indedir; CSV
zip'i onu içermez. DuckDB dosyası olay kaydı dahil altı tabloyu taşır.

## Testler

```bash
cd veri
.venv/Scripts/python -m pytest -q tests/v4/crm -m "not yavas"   # hızlı: birim, yapı, KUCUK
.venv/Scripts/python -m pytest -q tests/v4/crm -m yavas         # tam koşu: bantlar, öğrenilebilirlik
.venv/Scripts/python araclar/v4_crm_cok_tohum.py                # 5 tohum (~1,5 sa)
```
