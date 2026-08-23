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

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative, resolve, sep } from 'node:path'
import matter from 'gray-matter'
import { hepsiniDogrula, type DiziGirdi, type YaziGirdi } from '../src/lib/dogrula'

type Girdi = { id: string; data: Record<string, unknown>; body: string }
type KoleksiyonSonucu = { girdiler: Girdi[]; eksik: boolean }

/**
 * Bir alt dizini verilen uzantıya göre özyinelemeli tarar.
 *
 * `baslangic`'in var olduğu çağıran tarafından (koleksiyonuOku'da) zaten
 * doğrulanır — burada readdirSync hatası yutulmaz; gerçekten beklenmedik
 * bir durumsa (örn. izin sorunu) script gürültülü şekilde patlar. Sessiz
 * bir catch, boş/yanlış bir kökte "hata yok" yanılsaması yaratan asıl
 * kusurdu.
 */
function dosyalariTara(baslangic: string, uzanti: string): string[] {
  const sonuclar: string[] = []

  function gez(dizin: string) {
    for (const ad of readdirSync(dizin)) {
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

/**
 * Bir koleksiyon dizinini okur. Dizin hiç yoksa boş dizi yerine `eksik: true`
 * döner ki çağıran bunu sessizce "koleksiyon boş" ile karıştırmasın —
 * eksik bir klasör her zaman bir hatadır, boş bir koleksiyon değildir.
 */
function koleksiyonuOku(icerikKoku: string, altDizin: string, uzanti: string): KoleksiyonSonucu {
  const koleksiyonKoku = join(icerikKoku, altDizin)
  if (!existsSync(koleksiyonKoku)) {
    return { girdiler: [], eksik: true }
  }
  const girdiler = dosyalariTara(koleksiyonKoku, uzanti).map((dosyaYolu) => {
    const ham = readFileSync(dosyaYolu, 'utf-8')
    const { data, content } = matter(ham)
    return { id: idUret(koleksiyonKoku, dosyaYolu), data, body: content }
  })
  return { girdiler, eksik: false }
}

function calistir(): void {
  const icerikKokuGirdi = process.argv[2] ?? 'src/content'
  const icerikKoku = resolve(process.cwd(), icerikKokuGirdi)

  if (!existsSync(icerikKoku)) {
    console.error(
      `İçerik kökü bulunamadı: "${icerikKoku}" (verilen argüman: "${icerikKokuGirdi}"). ` +
        'Doğrulama koşulamadı — bu build\'i durdurmalı, sessizce geçmemeli.',
    )
    process.exitCode = 1
    return
  }

  const yaziSonuc = koleksiyonuOku(icerikKoku, 'yazi', '.mdx')
  const diziSonuc = koleksiyonuOku(icerikKoku, 'dizi', '.md')
  const alanSonuc = koleksiyonuOku(icerikKoku, 'alan', '.md')
  const sozlukSonuc = koleksiyonuOku(icerikKoku, 'sozluk', '.md')

  const eksikKlasorler = (
    [
      ['yazi', yaziSonuc],
      ['dizi', diziSonuc],
      ['alan', alanSonuc],
      ['sozluk', sozlukSonuc],
    ] as const
  )
    .filter(([, sonuc]) => sonuc.eksik)
    .map(([ad]) => ad)

  const yazilar: YaziGirdi[] = yaziSonuc.girdiler.map((g) => ({
    id: g.id,
    body: g.body,
    data: g.data as YaziGirdi['data'],
  }))

  const diziler: DiziGirdi[] = diziSonuc.girdiler.map((g) => ({
    id: g.id,
    data: g.data as DiziGirdi['data'],
  }))

  const alanlar = alanSonuc.girdiler.map((g) => g.id)
  const terimler = sozlukSonuc.girdiler.map((g) => g.id)

  // Boş ya da yanlış bir içerik kökünde sessiz "başarı" en tehlikeli kusur
  // sınıfıdır: doğrulama hiç koşmamış olur ama build yine de yayına çıkar.
  // Gerçek bir kullanımda içeriksiz bir build istenen bir şey değil, o
  // yüzden hiç yazı ya da hiç terim bulunamamasını da hata sayıyoruz —
  // kararı script'in kendi takdirine bırakmıyoruz.
  if (yazilar.length === 0 || terimler.length === 0) {
    console.error(
      `İçerik kökünde yeterli içerik bulunamadı: "${icerikKoku}" (verilen argüman: "${icerikKokuGirdi}"). ` +
        `${yazilar.length} yazı, ${terimler.length} terim bulundu.` +
        (eksikKlasorler.length > 0
          ? ` Eksik koleksiyon klasörleri: ${eksikKlasorler.join(', ')}.`
          : ' Bu klasörler var ama içi boş; yanlış kökte mi çalıştırdınız?'),
    )
    process.exitCode = 1
    return
  }

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
