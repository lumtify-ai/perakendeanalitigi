import { fileURLToPath } from 'node:url'
import { defineConfig } from 'astro/config'
import mdx from '@astrojs/mdx'
import sitemap from '@astrojs/sitemap'
import { unified } from '@astrojs/markdown-remark'
import tailwindcss from '@tailwindcss/vite'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { hazirlaniyorAdresleri, sitemapSuzgeci } from './src/lib/yayinDurumu.mjs'

// Windows'ta new URL().pathname baştaki eğik çizgiyle sürücü harfini bozar
const YAZI_KOKU = fileURLToPath(new URL('./src/content/yazi/', import.meta.url))

export default defineConfig({
  site: 'https://perakendeanalitigi.com',
  // Dil öneki yok: site tek dilli ve öyle kalacak. İngilizce bir gün
  // gelirse ayrı bir alan adında, ayrı depoda ve ayrı terim sözlüğüyle
  // gelecek — yani `/tr/` öneki hiçbir zaman bir `/en/` ile eşleşmeyecekti.
  // Önek kaldırıldığında kök adres gerçek ana sayfa oldu; `_redirects`
  // artık yalnızca eski `/tr/…` adreslerini 301 ile yeni yerine taşıyor.
  integrations: [
    mdx(),
    // Hazırlanıyor yazılar üretilir ve dizi kapağından bağlanır ama site
    // haritasında ilan edilmez; aynı sayfalar <meta name="robots" content=
    // "noindex"> de basar (src/layouts/Temel.astro).
    sitemap({ filter: sitemapSuzgeci(hazirlaniyorAdresleri(YAZI_KOKU)) }),
  ],
  markdown: {
    // markdown.remarkPlugins / rehypePlugins Astro 7'de kullanımdan kalktı;
    // eklentiler artık @astrojs/markdown-remark'ın unified() işlemcisine
    // verilir. Davranış aynı, uyarı kalkar.
    processor: unified({
      remarkPlugins: [remarkMath],
      rehypePlugins: [rehypeKatex],
    }),
  },
  vite: {
    plugins: [tailwindcss()],
    build: {
      // Vite küçük varlıkları base64 data: URI olarak CSS'e gömer. Tek bir
      // KaTeX fontu bu sınırın altında kalıyordu ve yayında CSP'ye takıldı:
      //   Loading the font 'data:font/woff2;base64,...' violates the
      //   following Content Security Policy directive: "font-src 'self'"
      // CSP'yi gevşetip data: eklemek yerine gömmeyi kapatıyoruz; font-src
      // 'self' anlamlı bir güvence olarak kalsın. Bedeli tek bir küçük
      // istek, o da bir yıllık immutable önbellekle geliyor.
      assetsInlineLimit: 0,
    },
  },
})
