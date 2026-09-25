# Replenishment — depodan mağazaya

Lumoda v2 sentetik verisi üstünde depo→mağaza replenishment vakası. Sitedeki
[Depodan Mağazaya](https://perakendeanalitigi.com/replenishment/depodan-magazaya/)
dizisinin bütün sayıları buradan çıkar.

Replenishment, satan ürünün aynısını yerine koymaktır. Sezon başında mağazaya
ilk malı koymak (ilk dağıtım) ve tedarikçiye tekrar sipariş vermek (RPT) bu
vakanın kapsamı dışındadır.

## Kurulum ve koşum

    cd vakalar/replenishment
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ../../veri -e ".[dev]"
    .venv/Scripts/python -m pytest -q          # testler (hızlı + @pytest.mark.veri)

Veri yoksa önce üret: `cd veri && .venv/Scripts/python -m perakende_veri.uret`

Senaryo taramasını koşmak (21 talep yolu × 60 senaryo, birkaç saat; yarıda
kalırsa kaldığı yerden devam eder):

    .venv/Scripts/python -m replenishment.kos

Yazıların alıntıladığı bütün sayıları basmak:

    .venv/Scripts/python rapor.py

Demo kadranının JSON'unu üretmek (siteye yazar):

    .venv/Scripts/python senaryolar.py

## Nasıl çalışıyor

Veri setine dokunulmaz. Vaka, v2'nin talebini kısıtlı bir depoyla yeniden
oynatır. Bu meşrudur çünkü Lumoda'nın simülasyonunda talep stoktan bağımsız
üretilir; **gerçek talep = satış + kayıp satış** eksiksiz geri kurulabilir.
`tests/test_esdegerlik.py` bunu kilitler: v2'nin kendi sevkiyat ve iadeleri
girdi olarak verildiğinde motor, v2'nin satış ve kayıp satış tablolarını gün
gün birebir üretir.

| Modül | İşi |
|---|---|
| `dunya.py` | Simülasyonun `cesit` sırasını koruyarak sabit dünyayı (`Dunya`) kurar |
| `kaynak.py` | v2 DuckDB tablolarını `(gün, hücre)` matrislerine pivotlar |
| `motor.py` | Günlük döngü: gelen mal → iade → satış → kayıp; FIFO ve stoklu gün kaydı |
| `depo.py` | Line'a göre alım; Collection/Outlet tek alım, NOS/Basic iki haftada bir tedarik |
| `ihtiyac.py` | Özel gün katsayısı, safety stock aileleri, kural öngörüsü, bedene bölme |
| `tahmin.py` | LightGBM tek global model, haftalık yeniden eğitim, sızıntı kalkanı |
| `dagitim.py` | Koli kuralları (A/B/C), cover önceliği, açık toplama kapasitesi |
| `politika.py` | Üç kol: kural, tahmin (çıplak), tahmin + taban |
| `oyun.py` | Haftalık karar döngüsü ve ölçütler |
| `gecmis.py` | Alternatif talep yolları ve ocak–ağustos geçmişinin yeniden oynatılması |
| `kalibrasyon.py` | Parametreleri **yalnız ön oyun penceresinde** seçer |
| `kos.py` | Senaryo × yol koşucusu; disk önbellekli, paralel |

## Üç kol

Karşılaştırmanın adil olması için üç kol var:

- **kural** — hedef = `max(7 günlük öngörü, güvenlik stoku)`
- **tahmin** — hedef = LightGBM öngörüsü, taban yok (sahada sık yapılan hata)
- **tahmin_taban** — LightGBM öngörüsü + kural kolunun birebir aynı tabanı

`tahmin_taban` ile `kural` arasındaki fark **öngörü** etkisidir; `tahmin` ile
`tahmin_taban` arasındaki fark **politika** etkisidir. Ölçtüğümüz sonuç:
politikanın etkisi öngörünün iki katı.

## Kurulumun iki kritik ayrıntısı

**Sızıntı yok.** Hiçbir karar, karar gününden sonraki veriyi göremez. `oyna`
satış matrisini karar gününden sonrası sıfırlanmış hâlde politikaya verir;
kalibrasyon yalnız ön oyun penceresinde (2025-05-05…08-31) çalışır;
`hiperparametre_sec`'in doğrulama pencereleri oyun dönemine değmez. Üçü de
testle kilitli.

**Sansürlü talep.** Raf boşken satış sıfır yazılır, kayıp satış hiçbir yere
kaydedilmez. Hız bu yüzden takvim gününe değil **stoklu güne** bölünür. Bu
hile değildir: kayıp satış tablosuna dokunulmaz, yalnız mağazanın kendi stok
kaydı kullanılır.

## Senaryo ızgarası

4 alım oranı (%30/60/80/100) × 3 koli kuralı × {3 safety stock ailesi | çıplak
tahmin | tahmin+taban} = **60 senaryo**, 21 talep yolunda (yol 0 gerçek v2
talebi, yollar 1–20 aynı beklenen talepten farklı tohumlarla). Yazılardaki
nokta sayılar yol 0'dan, aralıklar 20 alternatif yoldan gelir.

## Bilinen sınırlar

- Kayıp satışı hiçbir yöntem göremez; düzeltmeden sonra bile hedef, gerçek
  talebin %81,4'ünde kalır.
- Toplama maliyetleri ve haftalık açık kapasite varsayımdır; raporda
  duyarlılıkları basılır.
- Oyun öncesi günlük stok geçmişi yoktur (v2 haftalık fotoğraf tutar); o
  günler stoklu sayılır.
- Kıtlık hiç bağlayıcı olmadı: depo en sıkı senaryoda bile dolu kapandı,
  açık kapasite hiçbir hafta dolmadı, paylaştırma önceliği hiç fark etmedi.
