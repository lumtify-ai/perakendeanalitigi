---
baslik: İlk Sevkiyat
alan: allocation
algoritmalar: [ilk-sevkiyat, strateji-oneri]
ozet: >-
  Yeni bir ürün daha tek satış görmeden hangi mağazaya kaç paket gider ve
  ne kadarı depoda kalır? Kategori planından pay veren kural, benzer
  ürünlerin izi ve tahmin aynı sezonda karşılaştırılır.
# Spec §8 demo: true ister; src/data/senaryolar/ilk-sevkiyat.json gelene
# kadar false (Demo.astro dosyasız demo sayfasında build'i durdurur).
demo: false
---

Bu dizi, sezon başında yeni bir ürünün mağazalara ilk dağıtımını baştan
kurar: kararın neden satış görmeden verildiği, malı mağazalara
paylaştırmanın kurala ve tahmine dayanan yolları, malın ne kadarının
depoda tutulacağı ve sezon sonunda başarının nasıl ölçüleceği.
