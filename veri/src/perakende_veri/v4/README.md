# Lumoda v4 — çekirdek veri seti

v4, sitenin haritasındaki 34 algoritmanın hepsini besleyebilecek tek veri
setinin çekirdeğidir (spec'teki A parçası). v2 ve v3'ten bağımsız bir alt
pakettir: onları içe aktarmaz, onlara dokunmaz. Yalnız kök
`perakende_veri.disa_aktar.yaz` ortaktır.

- Tasarım: `docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md`
  (§11 uygulamadaki sapmalar).
- Üretim: `python -m perakende_veri.v4.uret` → `veri/cikti/v4/` (CSV,
  Parquet, DuckDB).
- Tohum `2026`. Aynı komut her zaman aynı veriyi üretir.

## Kısaca dünya

- **Pencere 2023-01-01 – 2025-12-31** (1.096 gün). Simülasyon 2022-07-04'te
  başlar; ısınmanın hareketleri yayımlanmaz.
- **84 fiziksel mağaza + online (`ONL`).** Pencere başında 78 mağaza açık.
  6 açılış, 4 kapanış, 2 tadilat var (`magaza_olay`). Mağazalar AVM 47,
  cadde 27, outlet 10.
- **Tek merkez depo** (Gebze). Online depodan satar ve iadesi depoya döner.
- **Mağazalar arasındaki fark gizlidir.** Dört eksen var: iklim, gelir,
  müşteri profili, konum. Bunlar 6 segmentte toplanır. Tablolarda yalnız
  gözlemlenebilir özellikler durur: şehir, tip, m², kat, kapasite.
- **Ürün:** SS23 … AW25 ve ısınmadaki AW22, her sezonda Collection ~210 ve
  Outlet ~40 option. Buna ~120 devamlı option (Basic, NOS) eklenir.
  Toplam 1.870 option, 8.506 SKU. Öznitelikler: kumaş, kalıp, desen, detay,
  fiyat segmenti.
- **Tedarik:** 18 tedarikçi (10 yerli, 8 yurt dışı). Profillerin gecikme,
  kalite, maliyet ve kapasite kısmı gizlidir; uzmanlık `tedarikci`
  tablosunda yayımlanır.
- **Fiyat:** markdown Lumoda'nın kuralıdır ve içseldir. Kampanyalar dışsaldır.
  İşlem indirimi rastgeledir. Enflasyon yok.
- **Talep:** ikame ve kanibalizasyon var. Stoksuz kalan talep veride
  görünmez, gizli gerçekte durur.

## Tablolar

Yayımlanan 18 tablo. Satır sayıları tam koşudan (`python -m perakende_veri.v4.uret`).

| Grup | Tablo | Satır |
|---|---|---:|
| Boyut | `magaza` | 85 |
| | `magaza_olay` | 12 |
| | `urun` | 8.506 |
| | `paket` | 31 |
| | `tedarikci` | 18 |
| | `sezon` | 21 |
| | `takvim` | 1.096 |
| | `kampanya` | 53 |
| Plan | `mfp_plan` | 595 |
| | `range_plan` | 383 |
| | `magaza_plan` | 2.975 |
| Tedarik | `siparis` | 38.686 |
| | `kalite_kontrol` | 7.846 |
| Hareket | `satis` | 17.960.852 |
| | `fiyat` | 120.850 |
| | `stok` | 10.324.750 |
| | `depo_stok` | 4.579.488 |
| | `sevkiyat` | 3.735.796 |

Üretim ~4–5 dakika sürer (son koşu 249 sn: dünya 17, motor 126, tablolar 10,
yazma 96). Çıktı: CSV 1,63 GB (en büyüğü `satis.csv` 871 MB), Parquet
131 MB, DuckDB 219 MB. Hacim spec'in tahmininin 3–4 katıdır (spec §11).

Birimler: para TL, iki ondalık. Stok, sevkiyat, sipariş ve plan
adetleri adettir. **`mfp_plan`'da birimler karışıktır:** `satis_tutari` ve
`brut_marj` TL; `adet`, `donem_sonu_stok` ve `otb` adet.

### Boyut tabloları

| Tablo | Sütunlar | Not |
|---|---|---|
| `magaza` | magaza_id, ad, sehir, bolge, enlem, boylam, tip, metrekare, kat_sayisi, kapasite, acilis_tarihi, kapanis_tarihi | 84 fiziksel + `ONL` (tip `Online`). Gizli eksenler yok. |
| `magaza_olay` | magaza_id, olay (acilis / kapanis / tadilat), karar_tarihi, olay_tarihi, bitis_tarihi | 12 olay. `bitis_tarihi` yalnız tadilatta dolu. |
| `urun` | urun_id, option_id, model_kodu, model_adi, ad, marka, cinsiyet, ust_kategori, alt_kategori, line, sezon_kodu, dalga, renk, renk_kodu, beden_seti, beden, beden_sira, kumas, kalip, desen, detay, detay_alani, fiyat_segmenti, alis_fiyati, liste_fiyati, lansman_tarihi, cikis_tarihi, tedarikci_id | SKU düzeyi. AW22 ürünleri dahil. Devamlıda `sezon_kodu` `DEVAMLI`. |
| `paket` | paket_id, beden_seti, beden_sira, adet | Beden seti başına tek standart paket (`PKT01…`). |
| `tedarikci` | tedarikci_id, ad, ulke, mense, ilk_siparis_hafta, rpt_hafta, moq_option, uzmanlik | Kapasite ve kalite yok; onlar gizli. |
| `sezon` | sezon_kodu, dalga, lansman_tarihi, indirim_baslangic, cikis_tarihi | AW22 dahil 21 satır (7 sezon × 3 dalga). AW25'in indirim ve çıkışı pencere dışında. |
| `takvim` | tarih, hafta, ay, yil, sezon, sezon_kodu, tatil_mi, indirim_donemi_mi | Pencerenin günleri. |
| `kampanya` | kampanya_id, tip (kategori / ikinci_urun / black_friday), baslangic, bitis, kapsam_ust_kategori, kapsam_line, kapsam_bolge, oran | Isınmadakiler dahil. Boş kapsam = hepsi; virgülle ayrılmış liste. Bölgeli kampanya online'ı kapsamaz. |

### Plan tabloları

| Tablo | Sütunlar | Not |
|---|---|---|
| `mfp_plan` | sezon_kodu, ay, kanal (Mağaza / Online), ust_kategori, satis_tutari, adet, brut_marj, donem_sonu_stok, otb | Birimler yukarıda. |
| `range_plan` | sezon_kodu, alt_kategori, fiyat_segmenti, line, option_sayisi, ortalama_fiyat, derinlik | Derinlik = option başına ilk alım. |
| `magaza_plan` | sezon_kodu, magaza_id, ust_kategori, satis_hedefi | İlk dağıtımın mağaza payı buradan. |

Plan bilerek naiftir. "Geçen yılın gerçekleşeni" × büyüme hedefi ×
yönetim iyimserliğidir. Sürprizi, yerel sapmayı ve bu sezonun trendini
bilmez.

### Tedarik tabloları

| Tablo | Sütunlar | Not |
|---|---|---|
| `siparis` | siparis_id, tip (ilk / rpt / surekli), option_id, urun_id, tedarikci_id, siparis_tarihi, planlanan_teslim, gerceklesen_teslim, adet | SKU düzeyi. Pencerede verilen ya da teslim edilen siparişler. Teslimi pencereden sonraya kalanın `gerceklesen_teslim`'i boş. |
| `kalite_kontrol` | siparis_id, teslim_tarihi, numune, hatali | Teslim başına bir satır. Hatalı oran teslimatın tamamına uygulanır; hatalı mal depoya girmez. |

### Hareket tabloları

| Tablo | Sütunlar | Not |
|---|---|---|
| `satis` | tarih, magaza_id, urun_id, adet, tutar, indirim_tutari, kampanya_id | Günlük. **Negatif adet = iade.** ONL dahil. İkameyle gelen satış normal satış görünür. `kampanya_id` fiyatı belirleyen kampanya, yoksa boş. |
| `fiyat` | hafta_baslangic, option_id, hat (normal / outlet / online), indirim_orani | **Haftalık panel:** option × pazartesi × hat, haftanın sonundaki markdown oranı. Kampanya ve işlem indirimi burada yok. |
| `stok` | tarih, magaza_id, urun_id, adet, stoklu_gun | Fiziksel mağaza, pazartesi sabahı fotoğrafı. `stoklu_gun`: önceki 7 günde satışa açılırken rafta mal olan gün sayısı (v3 gibi). |
| `depo_stok` | tarih, urun_id, adet | Depo, **günlük** fotoğraf. |
| `sevkiyat` | tarih, varis_tarihi, kaynak, hedef, urun_id, adet, tip, paket_id | `tarih` çıkış günü. Çıkışı ya da varışı pencerede olan sevkler (2022-12-29…31'de çıkıp pencerede varanlar dahil). Kaynak ve hedef `magaza_id` ya da `DEPO`; `ONL` hiçbir sevkin ucu değildir. `paket_id` yalnız `ilk_dagitim`'da dolu, `paket.paket_id` ile birleşir. |

`sevkiyat.tip` dokuz değer alır:

| Tip | Anlamı |
|---|---|
| `ilk_dagitim` | Dalga ilk dağıtımı, depodan mağazaya, paketle |
| `replenishment` | Haftalık replenishment, depodan mağazaya, tekli |
| `outlet_akisi` | Sezon çıkışında kalan stok outlet mağazalarına |
| `stok_devri` | Penceresi kapanan hücrenin raf stoğu depoya |
| `elle_transfer` | Bölge müdürünün haftalık, kural dışı transferi |
| `acilis_transferi` | Yeni mağazanın açılış malı |
| `kapanis_transferi` | Kapanan mağazanın stoğu |
| `geri_yonlendirme` | Kapalı mağazaya varan mal aynı gün depoya döner. Son tam koşuda 0 satır; başka bir politikada oluşabilir. |
| `iade_depoya` | Kapalı mağazanın müşteri iadesi depoya |

RPT için ayrı tip yok: RPT depoya girer, replenishment'la dağılır.

### Dikkat edilecek yerler

- **Boş `varis_tarihi` iki şey olabilir.** (1) Mal 2025-12-31'de hâlâ
  yolda: çıkışı pencerenin son günlerinde. Son tam koşuda bunlar 4.140
  `replenishment` satırı, hepsi 2025-12-29 çıkışlı. (2) Kirli kayıt: tek
  taraflı transfer. Bunlar yalnız `elle_transfer` satırlarıdır (40 satır)
  ve çıkış günleri pencerenin içindedir (2023-01-16 … 2025-11-24). Tip ve
  çıkış günüyle ayırt edilir.
- **`sevkiyat.tarih` pencereden önce olabilir.** Tablo `siparis` gibi
  çıkış ya da varış gününe göre pencerelenir: 2022-12-29…31'de yola çıkıp
  pencerede varan mal (ilk dağıtım, stok devri, iade) tabloda, `tarih`i
  pencereden önce. Stok korunumu pencere başından kurulabilir. (Son tam
  koşuda o üç günde yola çıkan sevk yok, 0 satır; başka bir politikada
  oluşabilir.)
- **`fiyat`'ta 2023-01-01 yok.** O pazar gününün haftası 2022-12-26'da
  başlar, pencerenin dışındadır.
- **Sürpriz kırpılmaz.** Option sürprizi lognormaldir; birkaç option planın
  çok üstünde (aşırı "hit") satar. Aykırı değer değil, dünyanın parçası.
- **Çıkmış sezonluk stok depoda kalır.** Çıkışta outlet'e gitmeyen ya da
  outlet penceresi biten mal depoya döner ve orada durur (`depo_stok`'ta
  görünür). Bir daha satılmaz, 0 TL getirir; imha ya da tasfiye kaydı
  yok. Batık stok hesabında bu mal alış fiyatıyla sayılmalıdır.
- **Penceresi kapanmış hücreye gelen iade.** Müşteri iadesi rafa döner;
  hücrenin penceresi kapandıysa ertesi gün `stok_devri` ile depoya gider.
  Bu `stok_devri` satırı `sevkiyat`'ta görünür ama o SKU'nun o mağazada
  `stok` satırı yoktur (fotoğraf yalnız penceresi açık hücreleri çeker).

## Kirli kayıtlar

Kasıtlıdır, hata değildir. Temizlik işini veriye geri koyar.

| Tür | Adet | Nasıl görünür |
|---|---:|---|
| Mükerrer satış | 200 | Aynı satış satırı iki kez |
| Bedelsiz satış | 120 | `adet` dolu, `tutar` 0 |
| Hayalet stok | 150 | Mağazanın çeşidinde olmayan SKU'da pazartesi stoğu (1–3 adet, `stoklu_gun` 7) |
| Tek taraflı transfer | 40 | `elle_transfer` satırında `varis_tarihi` boş |

Bunun dışında veri tasarım gereği kusurludur: stoksuz talep kaydedilmez,
plan naiftir, markdown içseldir, ölü stok ve kırıklık oluşur.

## Gizli gerçek

Yayımlanan tablolara girmez. Vakalar kendi koşularında üretir:

```python
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.uret import tablolari_uret
from perakende_veri.v4.tablolar import gizli_gercek

tablolar, dunya, ham = tablolari_uret(Olcek.TAM, donus_ham=True)
gizli = gizli_gercek(dunya, ham)
```

`gizli_gercek` sözlüğü:

| Anahtar | İçerik |
|---|---|
| `kayip_satis` | tarih, magaza_id, urun_id, kayip_adet. İkameden sonra kalan kalıcı kayıp. |
| `ikame_satis` | tarih, magaza_id, urun_id, adet. İkameyle gelen satış; bu adet `satis`'te zaten var. |
| `segment` | Mağaza başına segment ve dört gizli eksen |
| `esneklik` | magaza_id, option_id, esneklik (yalnız taşınan çiftler) |
| `oznitelik_etkisi` | sezon_kodu, segment, option_id, etki (log etki) |
| `trend_tablosu` | sezon_kodu, segment, anahtar, katsayi: trendin yazılı hikâyesi |
| `surpriz` | option_id, surpriz |
| `tedarikci_profili` | Gizli profilin tamamı: gecikme, hatalı oranı, maliyet çarpanı, kapasite, uzmanlık |

`dunya.gercek()` aynı gizli dizileri ham hâliyle verir (sürüklenme ve yaşam
eğrisi oynaması dahil). Kanibalizasyon payı tablo değildir, dünyada bir
fonksiyondur (`cesit.kanibalizasyon_payi`).

`tablolari_uret` tam dünyayı kurar, motoru koşar, tabloları kirletir. Tam
koşu ~5 dakika ve ~5 GB bellek ister; denemeler için
`Olcek.KUCUK` var (20 fiziksel mağaza, option çarpanı 0,15).

## Politika enjeksiyonu

Motor dokuz kararı dışarıdan alır. Varsayılan her zaman Lumoda'nın bugünkü
pratiğidir. Vaka yalnız değiştirdiği kararı verir, dünya aynı kalır:

```python
from perakende_veri.v4.dunya import dunya_kur
from perakende_veri.v4.magaza import Olcek
from perakende_veri.v4.motor import simule_et
from perakende_veri.v4.politika import Politikalar
from perakende_veri.v4.uret import yayimla

def benim_replenishment(g):
    """[C] depodan istenen adet. g bir Gorunum: bugünün stoğu, geçmiş satış, plan…"""
    ...

dunya = dunya_kur(Olcek.TAM)
ham = simule_et(dunya, Politikalar(replenishment=benim_replenishment))
tablolar = yayimla(dunya, ham)        # aynı 18 tablo, kirli
```

| Alan | İmza | Lumoda |
|---|---|---|
| `ilk_dagitim` | `(g, o) -> [M]` paket sayısı | ilk alımın %70'i, `magaza_plan` payıyla |
| `paket_secimi` | `(g, o) -> [M]` paket indisi | set başına tek standart paket |
| `replenishment` | `(g) -> [C]` adet | v3 kuralı: 28 günlük plan hedefi, ölü stok kapısı |
| `rpt` | `(g) -> {option: adet}` | Banu'nun kuralı (3.–6. hafta, STR ≥ %55, ilk alımın %50'si) |
| `markdown` | `(g) -> [O, 3]` oran | STR'ye bağlı kademe (%20/30/40/50/70), haftalık; %30 sezon indirimi tabanı `indirim_gun`'de başlar (motor pazartesiye ek o gün de çağırır) |
| `acilis` | `(g, m) -> Transferler` | yalnız depodan, ne varsa |
| `kapanis` | `(g, m) -> Transferler` | bütün stok depoya |
| `elle_transfer` | `(g) -> Transferler` | bölge müdürünün az sayıda transferi |
| `outlet_akisi` | `(g, os) -> Transferler` | çıkışta kalan stok outlet'e ve depoya |

Tedarikçi seçimi dünyadadır: `dunya_kur(tedarikci_secimi=…)`. Politika
gizli profilden yalnız kapasiteyi görür.

`ONL` transferin ucu olamaz (fiziksel yeri yok, rafı hep 0): motor
kaynağı `ONL` olan transfer satırını atar, hedefi `ONL` olanı depoya
yönlendirir. `mesafe_km`'de `ONL` satır ve sütunu sonsuzdur;
`depo_mesafe_km[ONL]` 0.

**Kural: politika yalnız kamuya açık alanları okur.** `g` bir `Gorunum`'dur
(`motor/durum.py`): bugünün stoğu, yoldaki mal, geçmiş satış, fiyat
oranları, açık siparişler, mağaza durumu. `g.dunya` üzerinden
yalnız yayımlanan bilgiye karşılık gelen alanlar okunur: mağazalar, ürünler,
plan, kampanya, mesafeler, çeşit. **`lam`, `gizli_*`, `esneklik`, `sapma_*`,
`ilk_siparisler` ve `gercek()` okunmaz.** Bu bir sözleşmedir, kodla
zorlanmaz. Gizli gerçeği okuyan politika kıyasta hile yapmış olur.

Rastgelelik politikadan bağımsızdır: talep, iade, ikame ve işlem indirimi
(gün, hücre) anahtarlı sayaçlardan çekilir. İki politika aynı müşteri
akışını görür. Lumoda politikaları dışarıdan enjekte edilince çıktı
varsayılan koşuyla birebir aynıdır (`tests/v4/test_esdegerlik.py`).

## Kalibrasyon bantları

Tam koşuda ölçülür, `tests/v4/test_kalibrasyon.py` (`-m yavas`) kilitler.
Değerler bu belgenin son güncellemesindeki koşudan.

| Ölçüt | Bant | Değer |
|---|---|---|
| Online net ciro payı (yıl yıl) | %15–20 | 2023 0,171 · 2024 0,179 · 2025 0,175 |
| Online iade (adet) | %25–30 | 0,294 |
| Collection tam fiyat STR (SS23–SS25) | %55–70 | 0,559 |
| Bulunabilirlik Basic/NOS | %85–95 | 0,873 (Basic 0,874, NOS 0,870) |
| Bulunabilirlik Collection | %70–85 | 0,739 |
| Stoksuz talebin ikameyle kurtarılan payı | %20–40 | 0,266 |
| Option plan hatası (Collection, MAPE) | %40–55 | 0,461 |
| Kategori × ay plan hatası (SS24 · AW24) | %10–20 | 0,121 · 0,104 |
| Üretim süresi (yazma hariç) | < 600 sn | 149 sn |

Tanımlar `test_kalibrasyon.py`'nin başında. Kısaca: STR'nin payı
lansmandan çıkışa kadar etiket fiyatından brüt satış (mağaza + online),
paydası teslim alınan ilk alım + RPT. Bulunabilirlik pazartesi
fotoğraflarından: Σ `stoklu_gun` ÷ Σ açık gün, fiziksel mağaza. İkame payı
ikame satışı ÷ (ikame satışı + kayıp satış).

Marjı ince olanlar: kategori × ay AW24 (0,104), Collection tam fiyat STR
(0,559). Talebe dokunan her değişiklikten sonra `-m yavas` yeniden koşulur.

**Tam fiyatlı satış etiket fiyatıyla sayılır:** o gün option'ın hattında
markdown ve kampanya yoksa satış tam fiyattır. Rastgele işlem indirimi
(sadakat, personel, kupon) etiketi değiştirmez; bu satışlar tam fiyat sayılır.

## Öğrenilebilirlik

Veri çözülebilir olmalı ama önemsiz olmamalı. `tests/v4/test_ogrenilebilirlik.py`
(`-m yavas`) yalnız yayımlanan tablolardan öğrenir, gizli gerçekle puanlar.

| Test | İddia | Sonuç |
|---|---|---|
| Kümeleme | Satış karışımından k-means (6 küme), ARI 0,4–0,8 | ARI 0,564 (81 mağaza). Outlet, soğuk iklim ve metropol premium tam ayrışır; Anadolu aile ve sıcak sahil bölünür. |
| Esneklik tuzağı | Markdown haftalarıyla saf regresyon belirgin yanlış (göreli hata > 0,4) | ε̂ 0,164, gerçek 1,802, göreli hata 0,909 |
| Kampanyayla esneklik | Kampanya DiD'si havuzda gerçeğin ±%20'sinde | ε̂ 1,746, gerçek 1,850, göreli hata 0,056 (20 kampanya) |
| Trend | SS25'te oversize, slim'den plana göre fazla satar (p < 0,05); fark SS23'ten SS25'e büyür (kayma) | log fark SS25 0,604 (p 7,4e-14), SS23 0,053 |
| Tedarikçi | Sipariş ve kalite verisinden profil sıralaması, Spearman ≥ 0,5 | 0,942 |
| Açılış | Sezon ortası açılışta depo, benzer mağazanın sezonluk karışımının %60'ından azını karşılar | M033 0,594 · M037 0,435 · M041 0,545 · M044 0,564 |

- **Esneklik yalnız havuzda iddia edilir.** Kategori başına: Aksesuar
  0,225, Dış Giyim 0,076, Elbise & Tulum 0,073, Üst Giyim 0,048 göreli
  hata. Alt Giyim'den süzgeçlerden geçen kampanya kalmıyor.
- **Açılış ölçüsü yalnız sezonluk SKU'lardır** (Collection + Outlet).
  Basic/NOS sürekli tedarikle depoda hep vardır; bütün line'larla kapsama
  0,80–0,95. M033'ün marjı ince (0,594). Sezon başı açılışlar (M021 0,600,
  M027 0,456) sezon ortasından belirgin geniş değil; test bu karşıtlığı
  iddia etmez.
- Açılışta "benzer mağaza" gizli segmentle seçilir. Bu testin istisnasıdır:
  öğrenmeyi değil, dünyanın özelliğini sınar.

## Testler

```bash
cd veri
.venv/Scripts/python -m pytest -q -m "not yavas"   # hızlı: birim, yapı, v2/v3 kilitleri
.venv/Scripts/python -m pytest -q -m yavas         # tam koşu: bantlar, öğrenilebilirlik
```

Son koşu: hızlı takım **389 geçti** (232 sn; v2 ve v3 kilitleri dahil),
yavaş takım **16 geçti** (214 sn).
