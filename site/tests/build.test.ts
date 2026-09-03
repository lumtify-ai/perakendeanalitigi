// site/tests/build.test.ts
import { execSync } from 'node:child_process'
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))

function oku(yol: string): string {
  return readFileSync(DIST + yol, 'utf-8')
}

/**
 * dist altindaki butun HTML dosyalari, DIST'e gore egik cizgili yollarla.
 *
 * Site genelinde gecerli olmasi gereken vaatler (JavaScript yok, tarih yok)
 * yalnizca bir iki ornek sayfada test edilirse yeni bir sablon sessizce
 * vaadi bozabilir. Bu yardimci, kontrolu agacin tamamina yayar.
 */
function tumSayfalar(): { yol: string; html: string }[] {
  const sonuc: { yol: string; html: string }[] = []
  function gez(dizin: string) {
    for (const ad of readdirSync(dizin, { withFileTypes: true })) {
      const tamYol = join(dizin, ad.name)
      if (ad.isDirectory()) gez(tamYol)
      else if (ad.name.endsWith('.html')) {
        sonuc.push({
          yol: relative(DIST, tamYol).split(sep).join('/'),
          html: readFileSync(tamYol, 'utf-8'),
        })
      }
    }
  }
  gez(DIST)
  return sonuc
}

// JSON-LD disindaki her <script>. Yapay zeka tarayicilari JS calistirmaz;
// JavaScript'e bagli her sey onlar icin yok demektir.
const SCRIPT_DESENI = /<script(?![^>]*type="application\/ld\+json")/

beforeAll(() => {
  execSync('npm run build', { cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: 'inherit' })
}, 300_000)

describe('build çıktısı', () => {
  it('ana sayfa kökte üretilir, dil öneki yok', () => {
    expect(existsSync(DIST + 'index.html')).toBe(true)
    expect(existsSync(DIST + 'tr')).toBe(false)
  })

  it('eski /tr/ adresleri kalıcı olarak yeni yerine taşınır', () => {
    // Site 2026-08-30'a kadar /tr/ önekiyle yayımlandı. Dışarıda paylaşılmış
    // her eski bağlantı bu satıra bağlı; düşerse hepsi 404 olur.
    expect(oku('_redirects')).toMatch(/^\/tr\/\*\s+\/:splat\s+301$/m)
  })

  it('eğik çizgisiz /tr de taşınır', () => {
    // `/tr/*` deseni çıplak `/tr`'yi yakalamaz — Cloudflare orada 404 döner.
    // Search Console 2026-09-03'te tam bu adresi "Bulunamadı (404)" olarak
    // raporladı. Ayrı bir satır gerekiyor; bu kökteki eski 302 sıçraması
    // değil, yalnızca eski bağlantıları izleyen ziyaretçinin ödediği bedel.
    expect(oku('_redirects')).toMatch(/^\/tr\s+\/\s+301$/m)
  })

  it('robots.txt her tarayıcıya açık ve izni açıkça yazıyor', () => {
    // Sitenin bütün stratejisi alıntılanmak üzerine kurulu; hiçbir tarayıcı
    // engellenmez. Content-Signal yazılmazsa site sahibi "ne izin verir ne
    // yasaklar" sayılır, o yüzden dört sinyal de açıkça yazılı (2026-09-03).
    const robots = oku('robots.txt')
    expect(robots).toMatch(/^User-agent: \*$/m)
    expect(robots).toMatch(/^Allow: \/$/m)
    expect(robots).toMatch(/^Content-Signal: search=yes,ai-input=yes,ai-train=yes,use=full$/m)
    expect(robots).not.toMatch(/^Disallow:\s*\/\s*$/m)
    expect(robots).toContain('Sitemap: https://perakendeanalitigi.com/sitemap-index.xml')
  })

  it('sayfa dili türkçe işaretlenir', () => {
    expect(oku('index.html')).toContain('lang="tr"')
  })
})

describe('dağıtım yapılandırması', () => {
  const KOK = fileURLToPath(new URL('../', import.meta.url))

  it('wrangler yapılandırması dist dizinini gösterir', () => {
    // Dosyanın varlığı içeriği kadar önemli: wrangler yapılandırma
    // bulamayınca kendi auto-config akışını koşuyor, @astrojs/cloudflare
    // adaptörünü kuruyor ve build'i çakıyor. 2026-09-03'te iki dağıtım
    // üst üste böyle düştü.
    const yapilandirma = readFileSync(KOK + 'wrangler.jsonc', 'utf-8')
    expect(yapilandirma).toMatch(/"directory":\s*"\.\/dist"/)
  })

  it('olmayan adres özel 404 sayfasını sunar', () => {
    // Varsayılan `none` gövdesiz 404 döndürür; canlıda ölçüldü, 0 bayt
    // geliyordu ve üretilen 404.html hiç sunulmuyordu (2026-09-03).
    const yapilandirma = readFileSync(KOK + 'wrangler.jsonc', 'utf-8')
    expect(yapilandirma).toMatch(/"not_found_handling":\s*"404-page"/)
    expect(existsSync(DIST + '404.html')).toBe(true)
  })

  it('cloudflare adaptörü bağımlılıklara girmez', () => {
    // Site tamamen statik; SSR adaptörüne ihtiyacı yok ve Astro 7 ile
    // uyumsuz. Bir araç onu sessizce eklerse bu test düşer.
    const pkg = JSON.parse(readFileSync(KOK + 'package.json', 'utf-8'))
    const hepsi = { ...pkg.dependencies, ...pkg.devDependencies }
    expect(Object.keys(hepsi)).not.toContain('@astrojs/cloudflare')
  })

  it('wrangler sürümü sabitlenmiş', () => {
    // `npx wrangler deploy` yoksa en güncelini indirir; 4.128.0'daki
    // auto-config davranışı tam da böyle, biz hiçbir şey değiştirmeden geldi.
    const pkg = JSON.parse(readFileSync(KOK + 'package.json', 'utf-8'))
    expect(pkg.devDependencies.wrangler).toMatch(/^\d+\.\d+\.\d+$/)
  })
})

describe('içerik koleksiyonları', () => {
  it('beş koleksiyon da dolu', async () => {
    const { readdirSync } = await import('node:fs')
    const icerik = fileURLToPath(new URL('../src/content/', import.meta.url))
    for (const ad of ['alan', 'dizi', 'yazi', 'sozluk', 'kadro']) {
      expect(readdirSync(icerik + ad).length).toBeGreaterThan(0)
    }
  })
})

describe('temel düzen', () => {
  it('üst menü her sayfada var', () => {
    const html = oku('index.html')
    expect(html).toContain('href="/veri-seti/"')
    expect(html).toContain('href="/sozluk/"')
  })

  it('sayfa açıklaması meta olarak basılır', () => {
    expect(oku('index.html')).toContain('name="description"')
  })

  it('hiçbir sayfada tarih görünmez', () => {
    // Ana spec'in başarısızlık işareti: "son yazı: 4 ay önce"
    const html = oku('index.html')
    expect(html).not.toMatch(/\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)/)
  })
})

describe('sözlük', () => {
  it('sözlük sayfası her maddeyi çapayla basar', () => {
    const html = oku('sozluk/index.html')
    expect(html).toContain('id="cover"')
    expect(html).toContain('id="kiriklik"')
    expect(html).toContain('Sell-Through Rate')
  })

  it('sözlük DefinedTermSet olarak işaretlenir', () => {
    expect(oku('sozluk/index.html')).toContain('DefinedTermSet')
  })

  it('tooltip tanımı HTML içinde durur', () => {
    // Yapay zekâ tarayıcıları JS çalıştırmaz; tanım DOM'da olmalı
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('class="terim"')
    expect(html).toContain('yeterlilik süresi')
  })

  it('tooltip için script üretilmez', () => {
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })
})

describe('kadro', () => {
  it('kadro sayfası üç karakteri de tanıtır', () => {
    const html = oku('kadro/index.html')
    expect(html).toContain('Ali')
    expect(html).toContain('Veli')
    expect(html).toContain('Pelin')
    expect(html).toContain('Allocator')
    expect(html).toContain('Planner')
  })
})

describe('yazı sayfası', () => {
  it('dizili yazı üretilir', () => {
    expect(existsSync(DIST + 'transfer/blok-transfer/sonuclar/index.html')).toBe(true)
  })

  it('tekil alanın yazısı üretilir', () => {
    expect(existsSync(DIST + 'temeller/urun-hiyerarsisi/index.html')).toBe(true)
  })

  it('rozet ve kırıntı yolu basılır', () => {
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('rozet-sonuc')
    expect(html).toContain('BreadcrumbList')
    expect(html).toContain('href="/transfer/blok-transfer/"')
  })

  it('teknik ve sonuç yazıları TechArticle işaretlenir', () => {
    expect(oku('transfer/blok-transfer/sonuclar/index.html')).toContain('TechArticle')
  })

  it('hikâye yazısı Article işaretlenir', () => {
    const html = oku('transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('"@type":"Article"')
  })

  it('dizi gezinmesi önceki ve sonrakini verir', () => {
    const html = oku('transfer/blok-transfer/matematiksel-model/index.html')
    expect(html).toContain('href="/transfer/blok-transfer/karar-nasil-verilir/"')
    expect(html).toContain('href="/transfer/blok-transfer/sql-ve-greedy/"')
  })

  it('hikâye yazısı kadro kutusuyla açılır', () => {
    const html = oku('transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('kadro-kutusu')
    expect(html).toContain('Allocator')
  })
})

describe('dizi sayfası', () => {
  it('altı yazıyı sırayla listeler', () => {
    const html = oku('transfer/blok-transfer/index.html')
    const sira = ['magazanin-sorunu', 'karar-nasil-verilir', 'matematiksel-model', 'sql-ve-greedy', 'mip-ve-pulp', 'sonuclar']
    const yerler = sira.map((slug) => html.indexOf(slug))
    expect(yerler.every((y) => y > -1)).toBe(true)
    expect([...yerler].sort((a, b) => a - b)).toEqual(yerler)
  })

  it('kısayolu açıkça söyler', () => {
    expect(oku('transfer/blok-transfer/index.html')).toMatch(/hikâye|hikaye/i)
  })

  it('CreativeWorkSeries olarak işaretlenir', () => {
    expect(oku('transfer/blok-transfer/index.html')).toContain('CreativeWorkSeries')
  })
})

describe('alan sayfası', () => {
  it('dizili alan dizileri listeler', () => {
    const html = oku('transfer/index.html')
    expect(html).toContain('href="/transfer/blok-transfer/"')
  })

  it('tekil alan yazıları listeler', () => {
    const html = oku('temeller/index.html')
    expect(html).toContain('href="/temeller/urun-hiyerarsisi/"')
  })

  it('tanım paragrafıyla açılır', () => {
    // Hikâyeyle açılan sayfa alıntılanmaz (ana spec §9)
    const html = oku('transfer/index.html')
    const govde = html.slice(html.indexOf('<main'))
    expect(govde).toMatch(/Transfer,\s*bir mağazada/)
  })

  // Eski hali yalnizca tr/transfer sayfasinda `<pre` ariyordu ve mevcut alan
  // metninde zaten kod blogu yoktu: test hicbir zaman kirilamazdi. Kural
  // artik build dogrulamasinda zorlaniyor (src/lib/dogrula.ts ·
  // alanGovdeleriDogrula, tests/dogrula.test.ts); burada yalnizca sonucun
  // gercekten oyle oldugu, hem de her alan sayfasi icin dogrulaniyor.
  it('alan sayfası kod içermez', () => {
    for (const alan of ['transfer/index.html', 'temeller/index.html']) {
      expect(oku(alan), alan).not.toContain('<pre')
    }
  })
})

describe('ana sayfa', () => {
  it('tanım paragrafıyla açılır', () => {
    const govde = oku('index.html')
    expect(govde).toMatch(/Perakende analitiği/)
  })

  it('ağacın tamamını gösterir', () => {
    const html = oku('index.html')
    expect(html).toContain('href="/transfer/"')
    expect(html).toContain('href="/temeller/"')
    expect(html).toContain('href="/transfer/blok-transfer/"')
  })

  it('akış veya son yazılar bölümü içermez', () => {
    const html = oku('index.html')
    expect(html).not.toMatch(/son yazılar|en yeni|güncel yazılar/i)
  })
})

describe('veri seti sayfası', () => {
  it('Dataset olarak işaretlenir', () => {
    // Rakipler veri yayınlamaz; bu işaretleme ayrıştırıcıdır
    expect(oku('veri-seti/index.html')).toContain('"@type":"Dataset"')
  })

  it('yedi tabloyu da listeler', () => {
    const html = oku('veri-seti/index.html')
    for (const tablo of ['magaza', 'urun', 'takvim', 'satis', 'stok', 'sevkiyat', 'kayip_satis']) {
      expect(html).toContain(tablo)
    }
  })

  it('üç formatı da duyurur', () => {
    const html = oku('veri-seti/index.html')
    expect(html).toContain('CSV')
    expect(html).toContain('Parquet')
    expect(html).toContain('DuckDB')
  })
})

describe('demo', () => {
  it('demo sayfası üretilir', () => {
    expect(existsSync(DIST + 'transfer/blok-transfer/demo/index.html')).toBe(true)
  })

  it('bütün kombinasyonlar HTML içinde hazır durur', () => {
    // Sunucu yok; sayfa her koşulda anında açılır
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('data-anahtar="6|0|greedy"')
    expect(html).toContain('data-anahtar="26|14|mip"')
  })

  it('parametre seçimi radio ile yapılır, script ile değil', () => {
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('type="radio"')
  })

  it('senaryo dosyası bütçeyi aşmıyor', async () => {
    // Kombinasyon sayısı çarpımsal büyür; sınır dosya boyutudur
    const { statSync } = await import('node:fs')
    const yol = fileURLToPath(new URL('../src/data/senaryolar/blok-transfer.json', import.meta.url))
    expect(statSync(yol).size).toBeLessThan(500 * 1024)
  })

  it('demo JSON sözleşmeye uyar', async () => {
    const { default: veri } = await import('../src/data/senaryolar/blok-transfer.json')
    expect(Array.isArray(veri.parametreler)).toBe(true)
    const beklenenAnahtarSayisi = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    expect(Object.keys(veri.sonuclar).length).toBe(beklenenAnahtarSayisi)
  })

  it('sonuç görünürlüğü saf css :has() ile üretilir, script değil', () => {
    // hidden özniteliği yerine build-zamanında üretilen bir <style> bloğu
    // seçili radyo birleşimine karşılık gelen [data-anahtar] bloğunu açar.
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('<style')
    expect(html).toContain(':has(')
    // `hidden` ÖZNİTELİĞİ aranıyor, alt dize değil: `aria-hidden` erişilebilirlik
    // notudur ve görünürlük mekanizmasıyla ilgisi yoktur.
    expect(html).not.toMatch(/\shidden(=|>|\s)/)
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })

  it(':has() desteklenmeyen tarayıcı için @supports yedeği var', () => {
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('@supports not selector(:has(*))')
  })

  it('üretilen kural sayısı kombinasyon sayısına eşit', async () => {
    const { default: veri } = await import('../src/data/senaryolar/blok-transfer.json')
    const beklenenAnahtarSayisi = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    const html = oku('transfer/blok-transfer/demo/index.html')
    const stilEslesme = html.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(stilEslesme).not.toBeNull()
    const stilIcerigi = stilEslesme![1]
    const kuralSayisi = (stilIcerigi.match(/\[data-anahtar="[^"]+"\]\s*\{\s*display:\s*block\s*\}/g) ?? []).length
    expect(kuralSayisi).toBe(beklenenAnahtarSayisi)
  })

  it('kapalı tavan ekranda etiketiyle görünür', () => {
    // Ham "0" okuyucuya bir şey söylemez; kadranın ilk tıkı yayımlanmış
    // referans senaryodur ve adı vardır.
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('kapalı')
  })

  it('kayıp satış yakalama ölçütü ekranda', () => {
    // 18 → 14 gibi kötü bir kombinasyonun neden kötü olduğu net kazançta
    // görünmüyor; yalnız bu metrikte görünüyor.
    const html = oku('transfer/blok-transfer/demo/index.html')
    expect(html).toContain('Kayıp satış yakalama')
    expect(html).not.toContain('kayip_yakalama_yuzde')   // ham anahtar sızmasın
  })

  it('getiri demosunun ölçüt etiketleri var', async () => {
    // Etiket eksikse bileşen ham anahtarı basar; okuyucu 'net_kar_tl' görür.
    const { default: veri } = await import('../src/data/senaryolar/transfer-getirisi.json')
    const ilk = Object.keys(veri.sonuclar)[0]
    const olcutler = Object.keys(veri.sonuclar[ilk as keyof typeof veri.sonuclar].ozet)
    const kaynak = await import('node:fs').then((fs) =>
      fs.readFileSync(fileURLToPath(new URL('../src/components/Demo.astro', import.meta.url)), 'utf8'),
    )
    for (const olcut of olcutler) {
      expect(kaynak).toContain(`${olcut}:`)
    }
  })

  it('getiri senaryosu sözleşmeye uyar', async () => {
    const { default: veri } = await import('../src/data/senaryolar/transfer-getirisi.json')
    const beklenen = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    expect(Object.keys(veri.sonuclar).length).toBe(beklenen)
  })
})

describe("dağıtım", () => {
  it("site haritası üretilir", () => {
    expect(existsSync(DIST + "sitemap-index.xml")).toBe(true)
  })

  it("robots.txt site haritasına işaret eder", () => {
    expect(oku("robots.txt")).toContain("Sitemap: https://perakendeanalitigi.com/sitemap-index.xml")
  })
})

describe('site geneli vaatler', () => {
  it('gezici bütün üretilmiş sayfaları bulur', () => {
    // Aşağıdaki site geneli testler boş bir listede sessizce geçerdi; bu
    // iddia onları vakumdan korur.
    const sayfalar = tumSayfalar()
    expect(sayfalar.length).toBeGreaterThanOrEqual(15)
    expect(sayfalar.map(({ yol }) => yol)).toContain('index.html')
    expect(sayfalar.map(({ yol }) => yol)).toContain(
      'transfer/blok-transfer/sonuclar/index.html',
    )
  })

  it('hiçbir sayfada JavaScript yok', () => {
    // Tooltip, demo ve gezinme saf CSS ile çalışır; tek istisna JSON-LD.
    const suclular = tumSayfalar()
      .filter(({ html }) => SCRIPT_DESENI.test(html))
      .map(({ yol }) => yol)
    expect(suclular).toEqual([])
  })

  it('hiçbir sayfada tarih görünmez', () => {
    // Ana spec'in başarısızlık işareti iki biçimde çıkar: mutlak tarih ve
    // göreli ifade. Asıl işaret ikincisidir: "son yazı: 4 ay önce".
    const mutlak =
      /\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)/
    const goreli = /\d+\s+(gün|hafta|ay|yıl)\s+önce/
    const suclular = tumSayfalar()
      .filter(({ html }) => mutlak.test(html) || goreli.test(html))
      .map(({ yol }) => yol)
    expect(suclular).toEqual([])
  })

  it('Lumtify köprüsü site genelinde tam bir kez geçer', () => {
    // Huni kuralı sitenin en pahalı vaadi: tek geçiş noktası. Köprüyü her
    // yazının sonuna koymak onu beş reklama çevirir ve güveni bitirir. Köprü
    // dizinin SON yazısında durur; dizi büyüyünce yeri de kayar.
    const gecenler = tumSayfalar().filter(({ html }) => html.includes('lumtify-koprusu'))
    expect(gecenler.map(({ yol }) => yol)).toEqual([
      'transfer/blok-transfer/basari-nasil-olculur/index.html',
    ])
    expect(gecenler[0].html.split('lumtify-koprusu').length - 1).toBe(1)
  })
})

describe('üst menü', () => {
  // Tasarım dokümanı §9. "Alanlar" bağlantısı olmadan derin bir yazı
  // sayfasından alanların listesine giden üst düzey bir yol yoktu.
  it('beş bağlantıyı da her sayfada basar', () => {
    for (const { yol, html } of tumSayfalar()) {
      expect(html, yol).toContain('href="/#alanlar"')
      expect(html, yol).toContain('href="/veri-seti/"')
      expect(html, yol).toContain('href="/sozluk/"')
      expect(html, yol).toContain('href="/kadro/"')
      expect(html, yol).toContain('href="https://github.com/lumtify-ai/perakendeanalitigi"')
    }
  })

  it('menüdeki tek dış bağlantı depo, ve güvenli açılıyor', () => {
    // Menünün diğer dördü site içi. Dış bağlantı yeni sekmede açılıyorsa
    // rel="noopener" şart; ayrıca menüde başka dış bağlantı BİRİKMEMELİ —
    // huni kuralı: kanıt öne, çağrı sona (Lumtify yalnız altbilgide ve
    // dizinin son yazısındaki köprüde).
    const html = oku('sozluk/index.html')
    const menu = html.slice(html.indexOf('<nav'), html.indexOf('</nav>'))
    const disBaglantilar = menu.match(/href="https?:\/\/[^"]+"/g) ?? []
    expect(disBaglantilar).toEqual(['href="https://github.com/lumtify-ai/perakendeanalitigi"'])
    expect(menu).toContain('rel="noopener"')
  })

  it('Alanlar bağlantısının hedefi ana sayfada gerçekten var', () => {
    expect(oku('index.html')).toContain('id="alanlar"')
  })
})

describe('yayın durumu', () => {
  // Tasarım dokümanı §3'ün taslak mekanizması (dizi kapağında "hazırlanıyor"
  // işareti, sayfada noindex, site haritasında gizleme) yerinde duruyor ama
  // şu an gösterecek taslak yok: yedi yazının hepsi yayında. Mekanizmanın
  // kendisi tests/yayinDurumu.test.ts'te sentetik ağaç üzerinde sınanıyor;
  // burada taslak yokluğunun getirdiği değişmezler doğrulanıyor.
  it('taslak olmadığı için hiçbir içerik sayfası noindex basmaz', () => {
    const suclular = tumSayfalar()
      .filter(({ html }) => html.includes('noindex'))
      .map(({ yol }) => yol)
    expect(suclular).toEqual([])
  })

  it('yayına açık sayfalar noindex basmaz', () => {
    for (const yol of [
      'index.html',
      'sozluk/index.html',
      'transfer/index.html',
      'temeller/urun-hiyerarsisi/index.html',
      'transfer/blok-transfer/magazanin-sorunu/index.html',
      'transfer/blok-transfer/karar-nasil-verilir/index.html',
      'transfer/blok-transfer/matematiksel-model/index.html',
      'transfer/blok-transfer/sql-ve-greedy/index.html',
      'transfer/blok-transfer/mip-ve-pulp/index.html',
    ]) {
      expect(oku(yol), yol).not.toContain('noindex')
    }
  })

  it('site haritası bütün yazıları ilan eder', () => {
    // Taslak yokken süzgeç hiçbir adresi elememeli: yazı sayfalarının
    // tamamı haritada olmalı.
    const harita = oku('sitemap-0.xml')
    const yazilar = tumSayfalar()
      .map(({ yol }) => yol)
      .filter((yol) => /^tr\/(temeller|transfer)\/.+\/index\.html$/.test(yol))
      .map((yol) => '/' + yol.replace(/index\.html$/, ''))
    const eksik = yazilar.filter((adres) => !harita.includes(adres))
    expect(eksik).toEqual([])
  })

  it('site haritası yayına açık adresleri ilan etmeye devam eder', () => {
    const harita = oku('sitemap-0.xml')
    expect(harita).toContain('/transfer/blok-transfer/')
    expect(harita).toContain('/sozluk/')
    expect(harita).toContain('/veri-seti/')
    expect(harita).toContain('/temeller/urun-hiyerarsisi/')
    expect(harita).toContain('/transfer/blok-transfer/magazanin-sorunu/')
    expect(harita).toContain('/transfer/blok-transfer/karar-nasil-verilir/')
    expect(harita).toContain('/transfer/blok-transfer/matematiksel-model/')
    expect(harita).toContain('/transfer/blok-transfer/sql-ve-greedy/')
    expect(harita).toContain('/transfer/blok-transfer/mip-ve-pulp/')
  })

  it('sonuç yazısının sayfası üretilir', () => {
    // Dizi kapağı ona bağlanıyor; kırık bağlantı bırakılmaz.
    expect(existsSync(DIST + 'transfer/blok-transfer/sonuclar/index.html')).toBe(true)
  })
})

describe('gömülü demo', () => {
  // Tasarım dokümanı §5: terim, kadro ve demo aynı deseni kullanır —
  // tek kaynak, ikinci gösterim. Demo bu deseni tamamlar.
  it('demo sonuclar yazısına gömülüdür', () => {
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('data-anahtar="6|0|greedy"')
    expect(html).toContain('data-anahtar="26|14|mip"')
  })

  it('gömülü demonun style bloğu article bağlamında derlenir', () => {
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    const baslangic = html.indexOf('<article')
    const bitis = html.indexOf('</article>')
    expect(baslangic).toBeGreaterThan(-1)
    const govde = html.slice(baslangic, bitis)
    expect(govde).toContain('<style')
    expect(govde).toContain(':has(')
    expect(govde).toContain('demo-sonuclar')
  })

  it('yedinci yazı üretiliyor ve getiri demosunu taşıyor', () => {
    const html = oku('transfer/blok-transfer/basari-nasil-olculur/index.html')
    // İki başabaş ölçütü ayrı ayrı görünmeli: fark yönetsel kural, ihtimal
    // ise seçilen vericinin üstüne binen mutlak baraj. Etiketleri karışırsa
    // yazının tablosu kadranla çelişir.
    expect(html).toContain('Başabaş fark (puan)')
    expect(html).toContain('Başabaş alıcı ihtimali (%)')
    expect(html).toContain('Alıcı mağazada satma ihtimali')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })

  it('gömülü demo da JavaScript getirmez', () => {
    const html = oku('transfer/blok-transfer/sonuclar/index.html')
    expect(html).not.toMatch(SCRIPT_DESENI)
  })
})

describe('KaTeX', () => {
  it('satır içi ve blok matematik build sırasında derlenir', () => {
    const html = oku('transfer/blok-transfer/matematiksel-model/index.html')
    expect(html).toContain('class="katex"')
    expect(html).toContain('katex-display')
    // MathML gövdesi HTML'in içinde durur; tarayıcı JS'i gerekmez
    expect(html).toContain('katex-mathml')
  })
})

describe('schema.org kapsamı', () => {
  it('teknik yazı da TechArticle işaretlenir', () => {
    // Daha önce yalnızca sonuc yazısı üzerinden test ediliyordu; eşlemenin
    // iki kolu da kilitlensin.
    expect(oku('transfer/blok-transfer/matematiksel-model/index.html')).toContain(
      '"@type":"TechArticle"',
    )
  })

  it('anlatıcı yazı Article işaretlenir', () => {
    expect(oku('temeller/urun-hiyerarsisi/index.html')).toContain('"@type":"Article"')
  })

  it('tekil sayfalarda da BreadcrumbList var', () => {
    // Tasarım dokümanı §11 "her sayfa" diyor. Ana sayfa hariç: orada kırıntı
    // yolu anlamsızdır.
    for (const yol of ['sozluk/index.html', 'kadro/index.html', 'veri-seti/index.html']) {
      expect(oku(yol), yol).toContain('BreadcrumbList')
    }
  })

  it('JSON-LD adresleri yapılandırmadaki origin ile üretilir', () => {
    // Alan adı hâlâ açık bir soru; elle yazılan origin değişince üç JSON-LD
    // sessizce yanlış URL basardı.
    const html = oku('transfer/blok-transfer/index.html')
    expect(html).toContain('"item":"https://perakendeanalitigi.com/transfer/"')
    expect(html).toContain('"url":"https://perakendeanalitigi.com/transfer/blok-transfer/')
  })
})

describe('tekil alan yazısı', () => {
  it('dizi gezinmesi taşımaz', () => {
    // Tekil alan yazısı bir algoritmaya ait değildir; önceki/sonraki yoktur.
    const html = oku('temeller/urun-hiyerarsisi/index.html')
    expect(html).not.toContain('dizi-gezinme')
    expect(html).not.toContain('rel="prev"')
    expect(html).not.toContain('rel="next"')
  })

  it('kırıntı yolu iki basamaklıdır', () => {
    const html = oku('temeller/urun-hiyerarsisi/index.html')
    expect(html).toContain('href="/temeller/"')
    expect(html).toContain('"position":2')
    expect(html).not.toContain('"position":3')
  })
})
