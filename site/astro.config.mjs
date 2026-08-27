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
  i18n: {
    locales: ['tr'],
    defaultLocale: 'tr',
    routing: {
      prefixDefaultLocale: true,
      // Astro statik çıktıda gerçek bir HTTP yönlendirmesi üretemez; bunu
      // açık bırakınca kök adrese "Redirecting from / to /tr/" yazan,
      // meta-refresh'i 2 saniye gecikmeli bir HTML sayfası konuyordu ve
      // ziyaretçi onu gözle görüyordu. Kapalı: kök adrese hiç dosya
      // üretilmiyor ve yönlendirmeyi Cloudflare kenarda yapıyor
      // (public/_redirects). Bedeli: `astro dev`/`preview` altında "/"
      // 404 verir — yayında doğru davranış için kabul edilen takas.
      redirectToDefaultLocale: false,
    },
  },
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
  },
})
