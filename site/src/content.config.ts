import { defineCollection } from 'astro:content'
import { glob } from 'astro/loaders'
import { z } from 'astro/zod'
import { TANIM_ASGARI_UZUNLUK } from './lib/agacSekli'

const alan = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/alan' }),
  schema: z.object({
    // Aşama alanının başlığı ve sırası haritadan gelir (src/data/harita.ts);
    // frontmatter'da tekrar edilirse ikisi zamanla ayrışır. Yalnızca harita
    // dışı raf (temeller) kendi başlığını taşır. Okuma src/lib/alanBasligi.ts
    // üzerinden yapılır, doğrudan data.baslik okunmaz.
    baslik: z.string().optional(),
    // İlk paragraf doğrudan tanımla açılır; hikâyeyle açılan sayfa alıntılanmaz.
    // Alt sınır olmadan boş dize geçiyordu; aynı sınır ağaç doğrulamasında da
    // uygulanır (src/lib/agacSekli.ts).
    tanim: z.string().min(TANIM_ASGARI_UZUNLUK),
  }),
})

const dizi = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/dizi' }),
  schema: z.object({
    baslik: z.string(),
    alan: z.string(),
    ozet: z.string(),
    // Haritadaki algoritma kimlikleri (src/data/harita.ts): dizinin kurduğu
    // ve kendi aşamasında duranlar. Dizinin konusu olmayan, yalnızca söz
    // edilen algoritmalar hiçbir yerde listelenmez (spec §0.1 madde 7).
    algoritmalar: z.array(z.string()).min(1),
    demo: z.boolean().default(false),
  }),
})

// Alan ve dizi frontmatter'da tutulmaz, dosya yolundan türetilir:
//   yazi/transfer/blok-transfer/matematiksel-model.mdx → dizili alan
//   yazi/temeller/urun-hiyerarsisi.mdx                 → tekil alan
const yazi = defineCollection({
  loader: glob({ pattern: '**/*.mdx', base: './src/content/yazi' }),
  schema: z.object({
    baslik: z.string(),
    tip: z.enum(['hikaye', 'anlatici', 'teknik', 'sonuc']),
    sira: z.number().int().positive(),
    ozet: z.string().max(300),
    yazar: z.string(),
    durum: z.enum(['yayinda', 'hazirlaniyor']).default('yayinda'),
  }),
})

const sozluk = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/sozluk' }),
  schema: z.object({
    terim: z.string(),
    kisa: z.string().max(200), // tooltip metni
    ingilizce: z.string().optional(),
    esanlam: z.array(z.string()).default([]),
  }),
})

const kadro = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/kadro' }),
  schema: z.object({
    ad: z.string(),
    rol: z.string(),
    tanitim: z.string().max(200),
  }),
})

export const collections = { alan, dizi, yazi, sozluk, kadro }
