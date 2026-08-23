import { defineCollection } from 'astro:content'
import { glob } from 'astro/loaders'
import { z } from 'astro/zod'
import { TANIM_ASGARI_UZUNLUK } from './lib/agacSekli'

const alan = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/alan' }),
  schema: z.object({
    baslik: z.string(),
    // İlk paragraf doğrudan tanımla açılır; hikâyeyle açılan sayfa alıntılanmaz.
    // Alt sınır olmadan boş dize geçiyordu; aynı sınır ağaç doğrulamasında da
    // uygulanır (src/lib/agacSekli.ts).
    tanim: z.string().min(TANIM_ASGARI_UZUNLUK),
    sira: z.number().int(),
  }),
})

const dizi = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/dizi' }),
  schema: z.object({
    baslik: z.string(),
    alan: z.string(),
    ozet: z.string(),
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
