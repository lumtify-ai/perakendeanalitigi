# Vesta — Sentetik Moda Perakende Veri Seti (v1)

perakendeanalitigi.com'daki bütün vakalar bu veri setini kullanır.
Veri **tamamen sentetiktir**; hiçbir gerçek şirket, müşteri veya kişi
verisi içermez. Vesta kurgusal bir moda perakende zinciridir.

## Kapsam

25 mağaza · 80 model → 240 option → 1.200 SKU · 2025 yılının tamamı

| Kimlik düzeyi | Örnek | Anlamı |
|---|---|---|
| model | `MDL001` | Tasarım. Fiyat bu düzeyde belirlenir. |
| option | `OPT0001` | Model × renk. Planlamanın ve transfer kararının birimi. |
| SKU | `U0001` | Option × beden. En alt stok birimi. |

## Tablolar

| Tablo | Satır | Açıklama |
|---|---:|---|
| `magaza` | 25 | Mağaza master'ı: şehir, tip, metrekare, kapasite |
| `urun` | 1.200 | SKU master'ı ve ürün hiyerarşisi |
| `takvim` | 365 | Tarih boyutu: hafta, ay, sezon, tatil |
| `satis` | ~530 bin | Günlük satış. **Negatif adet = iade.** |
| `stok` | ~643 bin | Haftalık stok fotoğrafı (pazartesileri) |
| `sevkiyat` | ~209 bin | Depodan mağazaya giren mal |
| `kayip_satis` | ~34 bin | Stoksuzluk yüzünden karşılanamayan talep |

### Ürün hiyerarşisi

Moda perakendesinde hiyerarşi bir sınıflandırma değil, **kararın kendisidir**:
transfer, ikmal ve sevkiyat algoritmalarının hepsi kapsamını bu ağaç üzerinden
tanımlar.

```
cinsiyet          Kadın · Erkek · Unisex
  ana_kategori    Üst Giyim · Alt Giyim · Dış Giyim
    alt_kategori  Tişört · Gömlek · Pantolon · Mont · …
      line        Basic · Denim · Casual · Klasik · Spor
```

Bu ağaca dik iki eksen daha vardır:

- `mevsimsellik` — **Sezonluk** ürün sezonuyla gelir gider; **Devamlı** (NOS)
  ürün yıl boyu satar ve stoğu hiç bitmemelidir. Transfer kararı ikisinde
  farklı işler.
- `sezon_grup` — `S1` (İlkbahar/Yaz) veya `S2` (Sonbahar/Kış).

`beden_sira` kolonu bedenleri XS=1 … XL=5 olarak sıralar. Kırıklık —
ara bedenlerin tükenip uçların kalması — bu sıralama olmadan tespit edilemez.

## Kullanım

En hızlı yol DuckDB dosyasıdır; kurulum gerektirmez:

```sql
-- Aynı modelin aynı bedeni nerede tükenmiş, nerede yığılmış?
WITH son AS (SELECT max(tarih) AS t FROM stok)
SELECT u.model_kodu, u.beden,
       min(s.adet) AS en_az, max(s.adet) AS en_cok
FROM stok s JOIN urun u USING (urun_id), son
WHERE s.tarih = son.t
GROUP BY 1, 2
HAVING min(s.adet) = 0 AND max(s.adet) > 10;
```

CSV ve Parquet sürümleri de aynı klasörde yayımlanır.

## Verinin kasten kusurlu yanları

Sentetik verinin klasik tuzağı fazla temiz olmasıdır. Aşağıdakiler
**bilinçli olarak** üretilir; hata değildir:

| Kusur | Neden var |
|---|---|
| Kayıp satış | Raf boşken gelen müşteri kaydedilmez; talep sansürlüdür |
| Ölü stok | Bazı option'lar bazı mağazalarda hiç tutmaz |
| Beden dengesizliği | Mağazanın beden eğrisi zincirin planından sapar |
| İade | Satışın ~%6'sı negatif satır olarak geri döner |
| Mükerrer satır | Çift girilmiş satışlar |
| Bedelsiz satır | `adet` dolu, `tutar` sıfır — manuel giriş hatası |
| Hayalet stok | Mağazanın çeşidinde olmayan üründe stok görünmesi |

Kirli kayıtlar satırların binde birinden azdır: veriyi kullanılamaz hale
getirmeden temizlik işini geri koyarlar.

### Dengesizlik nereden geliyor?

Bu veri setinin tek en önemli tasarım kararı budur. İkmal, **zincir
genelinde kurulmuş bir plana** göre yapılır: "bu tip mağazada bu üründen
haftada şu kadar satar". Gerçek talep ise **yereldir** — bir option bir
mağazada tutar, diğerinde hiç tutmaz; beden eğrisi semtten semte değişir.

Plan ile gerçek arasındaki bu fark bir yerde ölü stok, bir yerde
stoksuzluk üretir. İkmal her mağazayı kendi gerçek talebine göre
doldursaydı plan hep doğru çıkar ve **transfer edilecek bir şey olmazdı.**

## Bu veri setinin yetmediği yerler

Dürüstlük için: aşağıdakiler bilinçli sadeleştirmelerdir.

- **Sepet kimliği yok.** `satis` günlük toplam düzeyindedir; birlikte satın
  alma analizi yapılamaz. Sepet analizi gerektiren bir vaka geldiğinde
  `v2` üretilecektir.
- **Sell-through yüksek.** İkmal hedefe göre çalıştığı için sezon sonunda
  gerçek hayattakinden az stok kalır; gerçek zincirlerde ilk dağıtım bir
  bahistir ve fazlası eritilir.
- **Fiyat sabit.** İndirim işlem bazında rastgeledir; sezon sonu indirim
  takvimi modellenmemiştir. Fiyatlama alanı geldiğinde `fiyat_gecmisi` ve
  `kampanya` tabloları eklenecektir.
- **Tedarik yok.** Açık sipariş, tedarik süresi ve depo stoğu bu sürümde yok.
- **Transfer geçmişi yok.** Mağazalar arası geçmiş sevkler modellenmemiştir;
  tekrar-transfer soğuma kuralları bu veriyle sınanamaz.

## Yeniden üretim

```bash
cd veri
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m perakende_veri.uret
```

Tohum sabittir (`42`); aynı komut her zaman aynı veriyi üretir. Üretim
birkaç saniye sürer ve `veri/cikti/v1/` altına yazar.

Testler:

```bash
pytest                      # tüm testler
pytest tests/test_kalite.py # yalnızca veri gerçekçiliği doğrulamaları
```

`test_kalite.py` üretilmiş veriye karşı çalışır ve verinin inandırıcılık
eşiklerini korur: mevsimsellik görünür mü, beden dengesizliği var mı,
kayıp satış oranı makul mü, kırıklık oluşuyor mu.

## Lisans

Veri CC BY 4.0 ile dağıtılır (bkz. depo kökündeki `LICENSE-VERI`).
Üretici kod MIT'dir.
