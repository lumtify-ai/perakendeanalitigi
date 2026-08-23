# perakendeanalitigi.com

Türkçe perakende analitiği vakaları: her vaka tek bir somut soruyu matematiksel
model, SQL ve Python ile uçtan uca çözer. Kullanılan veri seti, çözüm kodu ve
demo senaryoları burada açık olarak yayımlanır.

Bir [Lumtify](https://lumtify.com) projesidir.

## Depo yapısı

| Dizin | İçerik |
|---|---|
| `site/` | Astro ile üretilen statik site |
| `veri/` | Sentetik moda perakende veri setinin üreticisi (Python) |
| `vakalar/` | Vaka başına tam çözüm kodu: model, SQL, notebook, senaryo önhesaplama |
| `docs/` | Tasarım dokümanı ve uygulama planları |

Sitedeki kod küratörlüdür: okunabilir tek bir SQL ve tek bir Python dosyası
gösterilir. Ham katman — tam çözüm, testler, alternatifler — bu depodadır.

## Dağıtım

Site Cloudflare Pages üzerinde barındırılır.

| Ayar | Değer |
|---|---|
| Build komutu | `npm run build` |
| Çıktı dizini | `site/dist` |
| Kök dizin | `site` |
| İzlenen yollar | `site/*`, `vakalar/*` |

`veri/` izlenen yolların dışındadır: veri üreticisindeki bir Python commit'i
siteyi yeniden kurmaz.

## Veri seti

Tek kurgusal moda perakende zinciri: 25 mağaza, 1.200 SKU (80 model × 3 renk ×
5 beden), 2025 yılı. Bütün vakalar aynı evreni kullanır.

Veri **tamamen sentetiktir**; hiçbir gerçek şirket verisi içermez. Üretim sabit
tohumludur (42), yani aynı komut her zaman aynı veriyi üretir.

Üretilen dosyalar repoya girmez; sürüm etiketiyle GitHub Releases üzerinden
CSV, Parquet ve tek dosya DuckDB olarak dağıtılır.

Yeniden üretmek için:

```bash
cd veri && pip install -e ".[dev]" && python -m perakende_veri.uret
```

## Lisans

Kod MIT (`LICENSE`). Veri setleri ve yazılı içerik CC BY 4.0 (`LICENSE-VERI`).
