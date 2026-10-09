# perakende-analitik

Yok satma vakasının (stoksuzluk kayıp satışı kestiricileri) ortak paketi.
Yayımlanan v4 verisini okur; kestiriciler ve değerlendirme bu paketin üstünde
durur.

## Kurulum

```
cd vakalar/ortak
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"          # Windows; Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest -q              # hızlı testler
.venv/Scripts/python -m pytest -q -m veri      # gerçek v4 gerektirenler (yavaş)
```

Veri: `veri/cikti/v4/perakende.duckdb` (yayımlanan `lumoda-v4.duckdb`'yi bu adla
koyun ya da `PERAKENDE_V4_DB` ortam değişkeniyle gösterin; indirme:
<https://github.com/lumtify-ai/perakendeanalitigi/releases/tag/veri-v4>). Yoksa
`veri` işaretli testler atlanır. Hakem için ek bağımlılık `perakende-veri`
(üreteç, `veri/`); PyPI'da olmadığı için yol ile kurulur:
`.venv/Scripts/pip install -e ../../veri` (vakalar/ortak içinden).

## Modüller

| Modül | İş |
|---|---|
| `kaynak` | v4'e salt okunur bağlantı; `temiz_satis` (mükerrer satış ayıklanır), `cesit_hucreleri` (mağaza × SKU çeşidi; hayalet stok düşer) |
| `stok` | günlük stok ve gün durumu (`stoklu` / `tukenen` / `bos`): `gunluk_magaza` (pazartesi fotoğrafına çapalı yeniden kurma), `gunluk_online` (depo stoğundan); yalnız uygun hücre-günler |
| `ozellikler` | hücre-gün başına gözlenebilir özellikler (`ekle`): takvim, özel gün, markdown ve kampanya oranı, ürün yaşı, ürün ve mağaza öznitelikleri, kanal; `yol_suresi` |
| `carpanlar` | Basit'in gün karakteri, 2023–2024 stoklu günlerinden: hafta günü (kanal), özel gün, ε̂ kampanya (fark-içinde-fark; karakterde) ve ε̂ markdown (yalnız rapor), yaşam eğrisi, beden payı |
| `talep` | kestiriciler (`egit(gozlem)`, `tahmin(hucre_gunler)`): `Naif` (son 28 gün), `Basit` (±14 gün, karakterle; `karar_ani=t` ile karar anı modu: havuz ve komşuluk yalnız `t`'den önce, `t`'den sonraki hiçbir satır kestirimi değiştirmez, `t` ve sonrası hedef ValueError; `None` bugünkü davranış, birebir), `ML` (LightGBM, Poisson, 2023–2024'ten 4 M stoklu SKU-gün); `komsu_hizlar` |
| `kayip` | kayıp yazımı (`kayip_yaz`: `bos` λ̂, `tukenen` Poisson koşullu fazla, `kayip_saf` karşılaştırma) ve toplama (`ozet`: adet, etiket fiyatıyla TL, brüt marj) |
| `agac` | kaynak ağacı (`kaynak_ata`): her kayıp hücre-gününe tek dal (lojistik, mağaza, allocation, tedarik, planlama, bilinmiyor) |
| `hakem` | gizli gerçeğin tek kapısı: v4'ü yeniden koşar, hücre-gün başına karşılanmayan talebi (`kendi_satis`, `karsilanmayan`, `ikameye_giden`, `kalici_kayip`) çıkarır, yayımlanan veriyle birebir doğrular, `cikti/hakem/`e yazar. `python -m perakende_analitik.hakem` (~dakikalar, GB'lar); `hakem.oku()` |
| `degerlendir` | kestirim ↔ hakem (2025): `eslestir`, `olcutler` (WAPE, yanlılık), `kirilimlar`, `ayrisim`, `cesit_disi`; hakem tablosunu argüman alır, `hakem`i içe aktarmaz |
| `hazirlik` | hazırlık adımları (vakaların `hazirla` akışları çağırır): `gunluk_yaz` (pencere boyunca yıl yıl parquet), `carpanlar_yaz` (öğrenme bitişine dek), `carpanlar_kapanmis(con, gunluk, t)` (karar anı çarpanları, dosyaya yazmaz: yalnız `t`'de kapanmış ve pencereye bütünüyle giren sezonların ve devamlı ürünlerin stoklu günleri, hepsi o sezonların `[ilk lansman, son çıkış)` aralığında, yani çarpanlar yalnız kapanmış sezon kümesiyle değişir; `kapanmis_sezonlar` hangi sezonlar olduğunu verir; v4'te `t = 2025-03-03` için SS23, AW23, SS24, AW24; AW22 pencerenin başında yarım), `kestirici` (naif / basit / ml), `kayip_yaz` (kestiricinin kayıp tablosu; `hedef_araligi=[bas, bit)` tahmini yalnız o aralığa yazar, eğitim havuzu değişmez; `agacli=False` kaynak ağacını atlar). Yazımlar atomik (`.yaziliyor` → `replace`) |
| `sayi_denetimi` | yazılardaki her sayının rapor dosyasında geçtiğini denetler (eşik 10, Türkçe biçim; çitli kod ve `sira` satırı hariç). `python -m perakende_analitik.sayi_denetimi --yazi DIZIN --rapor DOSYA [--komut "rapor üretme komutu"]`; eksik ya da biçimsiz sayıda çıkış 1. Yok-satma vakasının kökündeki `sayi_denetimi.py` sarmalayıcısı yazı dizinini ve rapor yolunu verir; blok-transfer'in sarmalayıcısı yok, modül `--yazi`/`--rapor` ile doğrudan çağrılır (vakanın README'si) |

## Sızıntı kuralı

Kestiriciler yalnız yayımlanan tabloları okur, gizli gerçeği görmez.
`perakende_veri` (gizli gerçeği üreten paket) yalnız `hakem.py`'de içe
aktarılır; paketin hiçbir modülü `hakem`i içe aktarmaz. `degerlendir` hakem
tablosunu argüman olarak alır; tabloyu `hakem.oku()` ile okuyup veren vakanın
raporudur (`vakalar/yok-satma/rapor.py`). `tests/test_sizinti.py` paketteki her
dosyayı `ast` ile tarar ve bu kuralı kilitler.

Karar anı kuralı: `Basit(karar_ani=t)` `t`'de ve sonrasındaki hiçbir satırı
(satış, stok durumu, satırın varlığı) görmez; çarpanları
`hazirlik.carpanlar_kapanmis(con, gunluk, t)` verir. `tests/test_karar_ani.py`
`t`'den sonraki satırları her yönden bozup `t`'den önceki kestirimin birebir
aynı kaldığını sınar.
