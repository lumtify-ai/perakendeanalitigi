# Lumoda — Sentetik Moda Perakende Veri Seti

perakendeanalitigi.com'daki vakalar bu veri setini kullanır.
Veri **tamamen sentetiktir**; hiçbir gerçek şirket, müşteri veya kişi
verisi içermez. Lumoda kurgusal bir moda perakende zinciridir.

## Sürümler

| Sürüm | Kapsam | Durum |
|---|---|---|
| **v4** | 2023–2025, 84 mağaza + online, 1.870 option, gizli segment, markdown, kampanya, ikame, açılış/kapanış, 18 tedarikçi, plan tabloları; B katmanı: müşteri, fiş, online davranış, yorum | **Güncel** — sitedeki bütün vakalar ve yazılar bunu kullanır |
| v1, v2, v3 | önceki sürümler | **Arşiv** — dosyaları GitHub Releases'te (`veri-v1`, `veri-v2`, `veri-v3`); üretici kodları depodan kaldırıldı, yalnız kendi etiketlerinde duruyor |

v4 bir alt pakettir (`perakende_veri/v4/`); kökten yalnız dışa aktarma
fonksiyonunu (`disa_aktar.yaz`) kullanır. Arşiv sürümlerden birini yeniden
üretmek için o sürümün etiketini (`git checkout veri-v2` gibi) açıp oradaki
README'yi izleyin.

## v4

`python -m perakende_veri.v4.uret` → `veri/cikti/v4/` (DuckDB, Parquet,
CSV). Tohum `2026`; üretim ~4–5 dakika (son koşu 249 sn). Tasarım:
`docs/superpowers/specs/2026-09-27-veri-v4-cekirdek-design.md`. **Tablo
sözlüğü, gizli gerçek ve politika enjeksiyonu için:
[`src/perakende_veri/v4/README.md`](src/perakende_veri/v4/README.md).**

84 fiziksel mağaza + online (`ONL`) · 1.870 option → 8.506 SKU ·
**2023-01-01 … 2025-12-31** (1.096 gün). Simülasyon 2022-07-04'te başlar.

Önceki sürümlere (v3) göre gelenler:

- **Mağazalar arası fark gizli.** Dört eksen (iklim, gelir, müşteri
  profili, konum) altı segmentte toplanır; tablolarda yok. Satış karışımından
  kümeleme kısmen bulur.
- **Fiyat oynar.** Markdown Lumoda'nın STR kuralıyla, içsel. Kampanyalar
  dışsal. Saf fiyat–talep regresyonu esnekliği yanlış bulur; kampanyalar
  doğru tahmin verir.
- **İkame ve kanibalizasyon.** Stoksuz ürünün talebinin bir kısmı komşu
  option'a geçer; çok option taşıyan mağazada her option daha az satar.
- **Mağaza açılır, kapanır, tadilata girer.** 6 açılış, 4 kapanış, 2
  tadilat; transferleri `sevkiyat`'ta.
- **18 tedarikçi, gizli profil, kalite kontrol.** Gecikme ve hatalı oranı
  sipariş ve kalite tablosundan kısmen öğrenilir.
- **Plan tabloları yayımlanır:** MFP, range, mağaza planı. Plan bilerek naif.
- **Kayıp satış yayımlanmaz.** Gizli gerçekle birlikte ayrıca üretilir.
- **Politikalar enjekte edilebilir.** Vaka kendi replenishment'ını,
  markdown'ını, transferini takar, aynı dünyada koşar.

| Tablo | Satır |
|---|---:|
| `satis` | 17.960.852 |
| `stok` | 10.324.750 |
| `depo_stok` | 4.579.488 |
| `sevkiyat` | 3.735.796 |
| `fiyat` | 120.850 |
| `siparis` | 38.686 |
| `kalite_kontrol` | 7.846 |
| boyut ve plan tabloları (11 tablo) | 12 … 8.506 |

Ham CSV 1,63 GB; Parquet 131 MB; DuckDB 219 MB.

Testler: `pytest -m "not yavas"` (hızlı) ve `pytest -m yavas` (tam koşu:
kalibrasyon bantları, öğrenilebilirlik). Sonuçlar v4 README'sinde.

## İndirme

v4'ün hazır dosyaları [`veri-v4` release'inde](https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4).
İki ayrı set var; tam veri için ikisi birlikte kullanılır (anahtarlar
`urun_id`, `magaza_id`, `kampanya_id`).

**A katmanı: perakende verisi** (mağaza, ürün, takvim, fiyat, kampanya,
günlük satış, stok, depo stoku, sevkiyat, sipariş, tedarikçi, planlar; 18 tablo):

| Varlık | Boyut |
|---|---:|
| [`lumoda-v4.duckdb`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4.duckdb) | 209 MB |
| [`lumoda-v4-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-parquet.zip) | 86 MB |
| [`lumoda-v4-csv.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-csv.zip) | 176 MB |

**B katmanı: CRM** (müşteri, fiş, fiş satırı, online liste özeti, online
olay kaydı, yorum; 6 tablo):

| Varlık | Boyut |
|---|---:|
| [`lumoda-v4-crm.duckdb`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm.duckdb) | 1.217 MB |
| [`lumoda-v4-crm-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm-parquet.zip) | 347 MB |
| [`lumoda-v4-crm-csv.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-crm-csv.zip) | 572 MB |
| [`lumoda-v4-olay-parquet.zip`](https://github.com/lumtify-ai/perakendeanalitigi/releases/download/veri-v4/lumoda-v4-olay-parquet.zip) | 163 MB |

B'nin Parquet ve CSV zip'leri olay kaydını içermez; o yalnız Parquet olarak
kendi zip'indedir. B'nin DuckDB dosyası olay kaydı dahil altı tabloyu taşır.
Dosyalar A ve B bölümlerindeki `uret` komutlarıyla yerelde de üretilebilir
(aynı tohum; bit düzeyinde aynılık aynı makine ve numpy sürümünde).

## v4 B katmanı: CRM

`python -m perakende_veri.v4.crm.uret` → `veri/cikti/v4_crm/` (DuckDB,
Parquet, CSV). A'nın satışını (tohum 2026) fişlere ve müşterilere ayrıştırır;
B'nin tohumu `4242`. Tasarım:
`docs/superpowers/specs/2026-09-28-veri-v4-crm-design.md`. **Tablo
sözlüğü, tutarlılık sözleşmesi, gizli gerçek ve bantlar için:
[`src/perakende_veri/v4/crm/README.md`](src/perakende_veri/v4/crm/README.md).**

- **Müşteri nüfusu.** Yedi gizli arketip, gizli tercihler, beden, ziyaret
  hızı, sepet, kart okutma, terk. Mağazada fişlerin ~%58'i kartlı
  (kimlikli), online'ın hepsi.
- **Fişler satışı birebir verir.** `fis_satir`'ın gün × mağaza × SKU
  toplamı A'nın temiz satışına kuruşu kuruşuna eşit; iadeler orijinal fiş
  satırına bağlı.
- **Terk ve LTV gizli.** Stoksuzluk, iade, beden uyumsuzluğu ve ev
  mağazasının kapanması terki artırır. "2026'da gelecek mi" ve 2026
  harcaması gizli gerçekte.
- **Online liste özeti ve 13 haftalık olay kaydı.** Sıralama enjekte
  edilebilir bir politika; tıklamada konum yanlılığı var.
- **Yorumlar** 7.000 metinlik etiketli Türkçe kütüphaneden; kim ve neden
  yazar gizli.

| Tablo | Satır |
|---|---:|
| `fis_satir` | 31.923.447 |
| `online_olay` (yalnız Parquet) | 23.901.935 |
| `fis` (iadeler dahil) | 16.764.655 |
| `musteri` | 2.106.860 |
| `online_liste_gunluk` | 609.905 |
| `yorum` | 74.394 |

Ham CSV 3.146 MB (olay kaydı hariç); Parquet 890 MB; DuckDB 1.217 MB. Üretim
A dahil ~19 dakika ve ~20 GB boş bellek ister.

Testler: `pytest tests/v4/crm -m "not yavas"` ve `-m yavas` (bantlar,
öğrenilebilirlik). Sonuçlar CRM README'sinde.

## Lisans

Veri CC BY 4.0 ile dağıtılır (bkz. depo kökündeki `LICENSE-VERI`).
Üretici kod MIT'dir.
