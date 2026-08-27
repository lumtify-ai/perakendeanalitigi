# Lumoda — Sentetik Moda Perakende Veri Seti (v2)

perakendeanalitigi.com'daki bütün vakalar bu veri setini kullanır.
Veri **tamamen sentetiktir**; hiçbir gerçek şirket, müşteri veya kişi
verisi içermez. Lumoda kurgusal bir moda perakende zinciridir.

## Kapsam

25 mağaza · 80 model → 240 option → 1.200 SKU · 2025 yılının tamamı

| Kimlik düzeyi | Örnek | Anlamı |
|---|---|---|
| model | `MDL003` | Ürün kodu + ürün adı. Tasarım; fiyat bu düzeyde belirlenir. |
| option | `MDL003-SYH` | Model × renk. Planlamanın ve transfer kararının birimi. |
| SKU | `MDL003-SYH-M` | Option × beden. En alt stok birimi. |

Kimlik okunabilir kurulmuştur: **SKU = ürün kodu – renk kodu – beden**.
Bir rapor satırına bakan kişi hangi model, hangi renk, hangi beden
olduğunu id'nin kendisinden görür.

## Tablolar

| Tablo | Satır | Açıklama |
|---|---:|---|
| `magaza` | 25 | Mağaza master'ı: şehir, tip, metrekare, kapasite |
| `urun` | 1.200 | SKU master'ı ve ürün hiyerarşisi |
| `takvim` | 365 | Tarih boyutu: hafta, ay, sezon, tatil |
| `satis` | ~532 bin | Günlük satış. **Negatif adet = iade.** |
| `stok` | ~643 bin | Haftalık stok fotoğrafı (pazartesileri) |
| `sevkiyat` | ~179 bin | Depodan mağazaya giren mal |
| `kayip_satis` | ~46 bin | Stoksuzluk yüzünden karşılanamayan talep |

### Ürün hiyerarşisi

Moda perakendesinde hiyerarşi bir sınıflandırma değil, **kararın kendisidir**:
transfer, ikmal ve sevkiyat algoritmalarının hepsi kapsamını bu ağaç üzerinden
tanımlar.

```
cinsiyet             Kadın · Erkek · Unisex
  ust_kategori       Üst Giyim · Alt Giyim · Dış Giyim
    alt_kategori     Tişört · Gömlek · Pantolon · Mont · …
      line           Basic · Collection · NOS · Outlet
        model        MDL003 "Balıkçı Yaka Kazak"
          option     MDL003-SYH
            SKU      MDL003-SYH-M
```

**Line** ürünün ticari rolünü ve yaşam döngüsünü söyler. Sezonluk/devamlı
ayrımı ayrı bir eksen değildir; line onu zaten taşır:

| Line | Anlamı | Sezon etkisi | Moda riski |
|---|---|---|---|
| `Basic` | Yıl boyu satılan temel ürün | Düşük | Düşük |
| `Collection` | Sezonluk koleksiyon | Tam | **Yüksek** |
| `NOS` | Never Out of Stock — stoğu asla bitmemeli | Neredeyse yok | En düşük |
| `Outlet` | Geçmiş sezondan devreden | Orta | Orta |

Outlet line'ı ağırlıklı olarak outlet mağazalarda bulunur (%15'e karşı %3).
Blok Transfer'in doğal kısıtlarından biri budur: outlet ürününü vitrin
mağazasına göndermek çözüm değildir.

### Beden setleri

Beden tek bir ölçek değildir. Üst giyim harfle, alt giyim numarayla gider;
kadın ve erkek numaraları ayrıdır:

| Beden seti | Kademeler |
|---|---|
| Kadın Harf | XS · S · M · L · XL |
| Kadın Numara | 34 · 36 · 38 · 40 · 42 |
| Erkek Harf | S · M · L · XL · XXL |
| Erkek Numara | 30 · 32 · 34 · 36 · 38 |
| Unisex Harf / Numara | Erkek setleriyle aynı |

Bu yüzden analiz beden **etiketine** değil `beden_sira` kolonundaki
**sıraya** bakar (1…5). Kırıklık — ara bedenlerin tükenip uçların kalması —
etiket üzerinden tanımlanamaz: pantolonda "M" diye bir beden yoktur.
Talep eğrisi de aynı sebeple konumla tanımlıdır; her sette orta kademeler
satar, uçlar durur.

## Kullanım

En hızlı yol DuckDB dosyasıdır; kurulum gerektirmez:

```sql
-- Beden seti bozulmuş (mağaza, option) çiftleri:
-- stok var ama ara bedenler tükenmiş
WITH son AS (SELECT max(tarih) AS t FROM stok)
SELECT st.magaza_id, u.option_id, any_value(u.model_adi) AS urun,
       sum(st.adet) AS kalan_stok
FROM stok st JOIN urun u USING (urun_id), son
WHERE st.tarih = son.t
GROUP BY 1, 2
HAVING sum(st.adet) > 0
   AND count(*) FILTER (WHERE st.adet = 0 AND u.beden_sira IN (2, 3, 4)) > 0
ORDER BY kalan_stok DESC;
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
| Kırıklık | 528 (mağaza, option) çiftinde ara bedenler tükenmiş |
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
Bu yüzden ikmal, bir hücrede kendi gerçekleşen satış hızına göre zaten
6 haftadan fazla stok varsa oraya mal göndermez — ölü stoğun üstüne
ölü stok yığmaz.

## Bu veri setinin yetmediği yerler

Dürüstlük için: aşağıdakiler bilinçli sadeleştirmelerdir.

- **Sepet kimliği yok.** `satis` günlük toplam düzeyindedir; birlikte satın
  alma analizi yapılamaz. Sepet analizi gerektiren bir vaka geldiğinde
  veri seti bu düzeyde yeniden üretilir.
- **Sell-through yüksek.** İkmal hedefe göre çalıştığı için sezon sonunda
  gerçek hayattakinden az stok kalır; gerçek zincirlerde ilk dağıtım bir
  bahistir ve fazlası eritilir.
- **Fiyat sabit.** İndirim işlem bazında rastgeledir; sezon sonu indirim
  takvimi modellenmemiştir. Fiyatlama alanı geldiğinde `fiyat_gecmisi` ve
  `kampanya` tabloları eklenecektir.
- **Sezon kodu yok.** Ürünler `S1`/`S2` gibi bir sezon koduna bağlı değildir;
  sezon davranışı line üzerinden gelir. Koleksiyon devri gerektiren bir vaka
  geldiğinde eklenecektir.
- **Beden setleri beş kademe.** Gerçek zincirlerde ayakkabı 36–45, takım
  elbise 46–58 gibi çok daha uzun setler vardır. Bu sürümde giyim dışına
  çıkılmamıştır.
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
birkaç saniye sürer ve `veri/cikti/v2/` altına yazar.

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
