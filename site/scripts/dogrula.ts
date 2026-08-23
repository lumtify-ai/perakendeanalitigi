// site/scripts/dogrula.ts
//
// Build öncesi içerik değişmezlerini zorlar. Brief bir Astro entegrasyonu
// öneriyordu (astro:build:start içinden astro:content sanal modülünü içe
// aktaran), ama bu modülün entegrasyon bağlamında güvenilir şekilde
// çözüleceği garanti değil — aynı sınıf hata bu projede Vitest tarafında
// zaten bir kez yaşandı. Bunun yerine bu script içerik dosyalarını
// doğrudan diskten okur, Astro'ya hiç bağımlı değildir ve `npm run build`
// öncesinde ayrı bir adım olarak koşar.
//
// Kullanım: tsx scripts/dogrula.ts [icerikKoku]
// icerikKoku verilmezse "src/content" kullanılır.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative, sep } from 'node:path'
import matter from 'gray-matter'
import { hepsiniDogrula, type DiziGirdi, type YaziGirdi } from '../src/lib/dogrula'

type Girdi = { id: string; data: Record<string, unknown>; body: string }

/** Bir alt dizini verilen uzantıya göre özyinelemeli tarar. */
function dosyalariTara(baslangic: string, uzanti: string): string[] {
  const sonuclar: string[] = []

  function gez(dizin: string) {
    let girdiler: string[]
    try {
      girdiler = readdirSync(dizin)
    } catch {
      // Alt dizin (örn. isteğe bağlı bir koleksiyon) hiç yoksa sessizce atla.
      return
    }
    for (const ad of girdiler) {
      const tamYol = join(dizin, ad)
      const bilgi = statSync(tamYol)
      if (bilgi.isDirectory()) {
        gez(tamYol)
      } else if (bilgi.isFile() && extname(ad) === uzanti) {
        sonuclar.push(tamYol)
      }
    }
  }

  gez(baslangic)
  return sonuclar
}

/**
 * Dosya yolunu koleksiyon kökünden itibaren uzantısız bir id'ye çevirir.
 *
 * Astro'nun glob loader'ı ile aynı kuralı izler: id, kökten itibaren göreli
 * yoldur. path.relative Windows'ta ters eğik çizgi (`\`) üretir; id'ler her
 * platformda eğik çizgiyle (`/`) karşılaştırıldığından (bkz. yaziYolunuAyristir),
 * burada normalize edilmezse Windows'ta her yazı "tanımsız alan" hatası alır.
 */
function idUret(koleksiyonKoku: string, dosyaYolu: string): string {
  const goreli = relative(koleksiyonKoku, dosyaYolu)
  const uzantisiz = goreli.slice(0, -extname(goreli).length)
  return uzantisiz.split(sep).join('/')
}

function koleksiyonuOku(icerikKoku: string, altDizin: string, uzanti: string): Girdi[] {
  const koleksiyonKoku = join(icerikKoku, altDizin)
  return dosyalariTara(koleksiyonKoku, uzanti).map((dosyaYolu) => {
    const ham = readFileSync(dosyaYolu, 'utf-8')
    const { data, content } = matter(ham)
    return { id: idUret(koleksiyonKoku, dosyaYolu), data, body: content }
  })
}

function calistir(): void {
  const icerikKoku = process.argv[2] ?? 'src/content'

  const yazilar: YaziGirdi[] = koleksiyonuOku(icerikKoku, 'yazi', '.mdx').map((g) => ({
    id: g.id,
    body: g.body,
    data: g.data as YaziGirdi['data'],
  }))

  const diziler: DiziGirdi[] = koleksiyonuOku(icerikKoku, 'dizi', '.md').map((g) => ({
    id: g.id,
    data: g.data as DiziGirdi['data'],
  }))

  const alanlar = koleksiyonuOku(icerikKoku, 'alan', '.md').map((g) => g.id)
  const terimler = koleksiyonuOku(icerikKoku, 'sozluk', '.md').map((g) => g.id)

  const hatalar = hepsiniDogrula(yazilar, diziler, alanlar, terimler)

  if (hatalar.length === 0) {
    console.log(`İçerik doğrulandı: ${yazilar.length} yazı, ${terimler.length} terim.`)
    return
  }

  for (const hata of hatalar) {
    console.error(hata)
  }
  console.error(`İçerik doğrulaması ${hatalar.length} hatayla başarısız.`)
  process.exitCode = 1
}

calistir()
