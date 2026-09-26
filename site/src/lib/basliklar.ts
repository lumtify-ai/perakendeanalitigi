// site/src/lib/basliklar.ts
//
// Yazının "Bu yazıda" menüsüne giden başlıklar. Astro'nun render() →
// headings listesinden yalnızca h2'ler alınır; alt başlıklar menüyü
// kalabalıklaştırır (spec §6).

type Baslik = { depth: number; slug: string; text: string }

export function yaziBasliklari(basliklar: Baslik[]): { slug: string; text: string }[] {
  return basliklar
    .filter((baslik) => baslik.depth === 2)
    .map(({ slug, text }) => ({ slug, text }))
}
