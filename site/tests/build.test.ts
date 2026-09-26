// site/tests/build.test.ts
import { execSync } from 'node:child_process'
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'
import { algoritmaBul, asamaBul, HARITA } from '../src/data/harita'
import {
  aktifAlgoritmalar,
  asamalar,
  diziler,
  diziSiralamasi,
  noindexBeklenen,
  YAZI_KOKU,
  yayindakiYaziSayisi,
} from './yardimci/icerikDurumu'

const DIST = fileURLToPath(new URL('../dist/', import.meta.url))
/** astro.config.mjs'deki `site`; site haritası mutlak adres basar. */
const SITE = 'https://perakendeanalitigi.com'
/** src/layouts/Temel.astro'nun `dizinlenmesin` ile bastığı etiket. */
const NOINDEX = '<meta name="robots" content="noindex">'


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
    for (const alan of [
      'transfer/index.html',
      'temeller/index.html',
      'rpt/index.html',
      'replenishment/index.html',
    ]) {
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

  it("v3'ün on bir tablosunu da listeler", () => {
    const html = oku('veri-seti/index.html')
    for (const tablo of [
      'magaza', 'urun', 'takvim', 'sezon', 'tedarikci', 'siparis',
      'satis', 'stok', 'depo_stok', 'sevkiyat', 'kayip_satis',
    ]) {
      expect(html).toContain(tablo)
    }
  })

  it("eski dizilerin v2 kullandığını söyler ve v2 release'ine bağlanır", () => {
    const html = oku('veri-seti/index.html')
    expect(html).toContain('releases/tag/veri-v3')
    expect(html).toContain('releases/tag/veri-v2')
    expect(html).toContain('Transfer ve replenishment')
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

  it('Lumtify köprüsü her dizinin son yazısında tam bir kez geçer, başka hiçbir sayfada değil', () => {
    // Huni kuralı: köprü her dizinin SON yazısında durur, başka hiçbir yerde
    // değil. Dizi büyüyünce yeri de kayar; yeni dizi kendi köprüsünü getirir.
    //
    // BEKLENEN_KOPRU_SAYFALARI kasıtlı olarak tüketicidir (exhaustive): bu
    // listede olmayan bir sayfada köprü belirmesi tam da bu testin yakalamak
    // için var olduğu hatadır — bir kadro biyografisine, bir sözlük
    // maddesine, bir dizi özetine ya da paylaşılan bir layout parçasına
    // sızan bir <Lumtify /> ya da düz "lumtify-koprusu" metni. Yeni bir dizi
    // tamamlanıp kendi köprüsünü kazandığında bu listeye tek satır eklenir.
    const BEKLENEN_KOPRU_SAYFALARI = [
      'transfer/blok-transfer/basari-nasil-olculur/index.html',
      'replenishment/depodan-magazaya/basari-nasil-olculur/index.html',
      'rpt/tekrar-siparis/rpt-geldi/index.html',
    ]

    const gecenler = tumSayfalar().filter(({ html }) => html.includes('lumtify-koprusu'))
    for (const { html } of gecenler) {
      expect(html.split('lumtify-koprusu').length - 1).toBe(1)
    }
    expect(gecenler.map(({ yol }) => yol).sort()).toEqual([...BEKLENEN_KOPRU_SAYFALARI].sort())
  })
})

describe('üst menü', () => {
  // Tasarım dokümanı §9. Menüdeki çapa olmadan derin bir yazı sayfasından
  // haritaya giden üst düzey bir yol yoktu. Çapa önce "Alanlar"dı; içerik
  // ağacı Lumtify haritasına oturunca "Harita" oldu.
  it('beş bağlantıyı da her sayfada basar', () => {
    for (const { yol, html } of tumSayfalar()) {
      expect(html, yol).toContain('<a href="/#harita">Harita</a>')
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

  it('Harita bağlantısının hedefi ana sayfada gerçekten var', () => {
    expect(oku('index.html')).toContain('id="harita"')
  })
})

describe('yayın durumu', () => {
  // Tasarım dokümanı §3'ün taslak mekanizması: hazırlanıyor yazı, aktif
  // olmayan aşamanın sayfası ve bütün yazıları hazırlanıyor olan dizinin
  // kapağı ile demosu üretilir ama noindex basar ve site haritasına girmez.
  // Mekanizmanın kendisi tests/yayinDurumu.test.ts'te sentetik ağaç üzerinde
  // sınanıyor; burada beklenen küme içerikten türetilip build çıktısıyla
  // karşılaştırılıyor (tests/yardimci/icerikDurumu.ts).
  it('noindex tam olarak içerikten türeyen taslak sayfalarda basılır', () => {
    const basanlar = tumSayfalar()
      .filter(({ html }) => html.includes(NOINDEX))
      .map(({ yol }) => '/' + yol.replace(/index\.html$/, ''))
      .sort()
    expect(basanlar).toEqual(noindexBeklenen())
    // Meta etiketin dışında "noindex" geçen sayfa da olmamalı (ör. yanlış
    // biçimde basılmış bir etiket); desen ayrışırsa yukarısı boşa geçerdi.
    const ciplak = tumSayfalar()
      .filter(({ html }) => html.includes('noindex') && !html.includes(NOINDEX))
      .map(({ yol }) => yol)
    expect(ciplak).toEqual([])
  })

  it('site haritası noindex olmayan her sayfayı ilan eder, noindex olanı etmez', () => {
    // Önceki hâli /^tr\/…/ desenine bakıyordu; önek kalktığından beri hiçbir
    // sayfayla eşleşmiyor ve boşa geçiyordu.
    const haritaXml = oku('sitemap-0.xml')
    const dislanan = new Set(noindexBeklenen())
    const adresler = tumSayfalar()
      .map(({ yol }) => yol)
      .filter((yol) => yol.endsWith('index.html'))
      .map((yol) => '/' + yol.replace(/index\.html$/, ''))
    expect(adresler.length).toBeGreaterThanOrEqual(15)
    const eksik = adresler.filter((a) => !dislanan.has(a) && !haritaXml.includes(`<loc>${SITE}${a}</loc>`))
    const fazla = adresler.filter((a) => dislanan.has(a) && haritaXml.includes(`<loc>${SITE}${a}</loc>`))
    expect(eksik).toEqual([])
    expect(fazla).toEqual([])
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

describe('adresler', () => {
  it('yayındaki on dört yazının adresi değişmez', () => {
    // İçerik ağacı Lumtify haritasına göre yeniden düzenlendi (2026-09-26);
    // transfer, replenishment ve temeller zaten aşama slug'ında duruyordu ve
    // yerinden kıpırdamamalı. Dışarıda paylaşılmış bağlantıların hepsi bu
    // listeye bağlı; biri kayarsa yönlendirmesiz 404 olur.
    const YAYINDAKILER = [
      ...[
        'magazanin-sorunu',
        'karar-nasil-verilir',
        'matematiksel-model',
        'sql-ve-greedy',
        'mip-ve-pulp',
        'sonuclar',
        'basari-nasil-olculur',
      ].map((y) => `transfer/blok-transfer/${y}`),
      ...[
        'sabahki-toplama-emri',
        'karar-nasil-verilir',
        'koli-mi-acik-mi',
        'kural-tabanli-yontem',
        'tahminle-yontem',
        'basari-nasil-olculur',
      ].map((y) => `replenishment/depodan-magazaya/${y}`),
      'temeller/urun-hiyerarsisi',
    ]
    expect(YAYINDAKILER).toHaveLength(14)
    const eksikler = YAYINDAKILER.filter((yol) => !existsSync(DIST + yol + '/index.html'))
    expect(eksikler).toEqual([])
  })

  it('RPT yeni adresinde', () => {
    // RPT dizisi eski "planlama" alanından haritadaki kendi aşamasına taşındı.
    const RPT_YAZILARI = [
      'ucuncu-pazartesi',
      'rpt-karari-nasil-verilir',
      'ne-kadar-daha-satardi',
      'hangi-urun-rpt-adayi',
      'ne-kadar-ne-zaman',
      'rpt-geldi',
    ]
    const eksikler = RPT_YAZILARI.filter(
      (y) => !existsSync(DIST + `rpt/tekrar-siparis/${y}/index.html`),
    )
    expect(eksikler).toEqual([])
    expect(existsSync(DIST + 'planlama')).toBe(false)
  })

  it('eski RPT adresleri kalıcı olarak taşınır', () => {
    // Cloudflare ilk eşleşen satırı uygular: özel desen (/planlama/rpt/*)
    // genel desenden (/planlama/*) önce gelmezse bütün RPT yazıları dizi
    // yerine aşama sayfasına düşer.
    const yonlendirmeler = oku('_redirects')
    const desenler = [
      /^\/planlama\/rpt\/\*\s+\/rpt\/tekrar-siparis\/:splat\s+301$/m,
      /^\/planlama\/rpt\s+\/rpt\/tekrar-siparis\/\s+301$/m,
      /^\/planlama\/\*\s+\/rpt\/\s+301$/m,
      /^\/planlama\s+\/rpt\/\s+301$/m,
    ]
    for (const desen of desenler) expect(yonlendirmeler).toMatch(desen)
    const yerler = desenler.map((desen) => yonlendirmeler.search(desen))
    expect(yerler[0]).toBeLessThan(yerler[2])
  })
})

/** Bir sayfanın bağladığı bütün stylesheet dosyalarının birleşik içeriği. */
function baglıCss(html: string): string {
  return [...html.matchAll(/<link rel="stylesheet" href="\/([^"]+)"/g)]
    .map(([, dosya]) => oku(dosya))
    .join('')
}

describe('sayfa iskeleti', () => {
  it('body genişlik sınırı taşımaz', () => {
    const css = baglıCss(oku('index.html'))
    expect(css).not.toMatch(/body\s*\{[^}]*max-width/)
    expect(css).not.toMatch(/body\{[^}]*max-width/)
  })

  it('harita sayfaları geniş çerçevede', () => {
    for (const yol of ['index.html', 'sezon-ici/index.html', 'rpt/index.html']) {
      expect(oku(yol), yol).toContain('<main class="duzen-harita"')
    }
    // Yazı sayfası kendi çerçevesinde: 72rem içinde yan menüler ve 40rem
    // okuma sütunu (spec §6; Temel.astro · duzen="yazi").
    expect(oku('transfer/blok-transfer/sonuclar/index.html')).toContain(
      '<main class="duzen-yazi"',
    )
    expect(oku('sozluk/index.html')).toContain('<main class="duzen-okuma"')
  })

  it("ölçüler CSS'te", () => {
    const css = baglıCss(oku('index.html'))
    expect(css).toContain('72rem')
    expect(css).toContain('40rem')
  })

  it('tablo ve kod kendi içinde kayar', () => {
    const css = baglıCss(oku('index.html'))
    const tabloKayar =
      /table\s*\{[^}]*overflow-x:\s*auto/.test(css) || /\.yatay-kaydir\s*\{[^}]*overflow-x:\s*auto/.test(css)
    const kodKayar = /pre\s*\{[^}]*overflow-x:\s*auto/.test(css)
    expect(tabloKayar).toBe(true)
    expect(kodKayar).toBe(true)
  })
})

/**
 * Bir sınıf belirtecini taşıyan öğe sayısı. Ham metinde saymak yanlış olur:
 * Astro bileşen CSS'ini sayfaya gömebilir ve aynı sınıf adı orada da geçer.
 * Yalnızca işaretlemedeki class="..." değerlerine bakılır.
 */
function sinifSay(html: string, uyar: (belirtec: string) => boolean): number {
  let sayi = 0
  for (const [, deger] of html.matchAll(/class="([^"]*)"/g)) {
    if (deger.split(/\s+/).some(uyar)) sayi++
  }
  return sayi
}

/**
 * Faz haritasındaki her aşamanın işaretlemesi, sırayla. Aşama <li>'leri iç
 * içe değil; bir aşama bir sonrakinin başladığı yerde (ya da listenin
 * kapanışında) biter. Liste içinde başka <ol> yok, ilk </ol> haritanın sonu.
 */
function asamaBloklari(html: string): string[] {
  const bas = html.indexOf('<ol class="faz-haritasi">')
  if (bas === -1) return []
  const govde = html.slice(bas, html.indexOf('</ol>', bas))
  return govde
    .split('<li class="asama ')
    .slice(1)
    .map((parca) => '<li class="asama ' + parca)
}

const FAZ_SAYFALARI = [
  'sezon-oncesi/index.html',
  'sezon-ici/index.html',
  'diger-surecler/index.html',
]

describe('harita', () => {
  it('faz sayfaları üretilir', () => {
    for (const yol of FAZ_SAYFALARI) expect(existsSync(DIST + yol), yol).toBe(true)
    // Spec §0.1 madde 8: 6 / 5 / 4 aşama.
    expect(sinifSay(oku('sezon-oncesi/index.html'), (b) => b === 'asama')).toBe(6)
    expect(sinifSay(oku('sezon-ici/index.html'), (b) => b === 'asama')).toBe(5)
    expect(sinifSay(oku('diger-surecler/index.html'), (b) => b === 'asama')).toBe(4)
  })

  it('otuz dört algoritmanın hepsi görünür', () => {
    // Spec §0.1 madde 10: 10 / 9 / 15 algoritma.
    const algoritmaMi = (b: string) => b.startsWith('algoritma--')
    const toplam = FAZ_SAYFALARI.reduce((t, yol) => t + sinifSay(oku(yol), algoritmaMi), 0)
    expect(toplam).toBe(34)
  })

  it('aktif algoritmalar diziye bağlanır', () => {
    // Beklenen küme içerikten türer (tests/yardimci/icerikDurumu.ts): yeni
    // bir dizi yayına girince test kendiliğinden yeni sayıyı bekler.
    const aktifler = aktifAlgoritmalar()
    expect(aktifler.size).toBeGreaterThan(0)
    const aktifMi = (b: string) => b === 'algoritma--aktif'
    for (const faz of HARITA) {
      const beklenen = [...aktifler].filter((id) => algoritmaBul(id)?.faz.slug === faz.slug)
      expect(sinifSay(oku(`${faz.slug}/index.html`), aktifMi), faz.slug).toBe(beklenen.length)
    }
    for (const dizi of diziler().filter((d) => d.yayinda)) {
      const faz = asamaBul(dizi.alan)!.faz.slug
      expect(oku(`${faz}/index.html`), dizi.adres).toContain(`href="${dizi.adres}"`)
    }
  })

  it('durum ekran okuyucuya da metinle iletilir: her algoritma satırı yazıldı/yazılmadı taşır', () => {
    // Spec §8: durum yalnızca renk ve şekille değil, metinle de verilir.
    // DurumNoktasi'nin ● / ○ işareti aria-hidden; yanındaki algoritma-adi
    // yalnızca adı taşıyor, durumu değil — bu yüzden görünmez ama okunur
    // bir sr-only metin (.sr-only) eklenir. Beklenen sayı sınıf sayısından
    // türer (sinifSay), elle yazılmaz.
    const aktifMi = (b: string) => b === 'algoritma--aktif'
    const solukMi = (b: string) => b === 'algoritma--soluk'
    for (const yol of FAZ_SAYFALARI) {
      const html = oku(yol)
      const aktifBeklenen = sinifSay(html, aktifMi)
      const solukBeklenen = sinifSay(html, solukMi)

      const aktifSatirlar = [
        ...html.matchAll(/<li class="algoritma algoritma--aktif">([\s\S]*?)<\/li>/g),
      ]
      // Soluk algoritma iki biçimde basılır: aktif aşamanın listesinde bir
      // <li>, soluk aşamanın tek satırında bir <span> (spec §4).
      const solukSatirlar = [
        ...html.matchAll(/<li class="algoritma algoritma--soluk">([\s\S]*?)<\/li>/g),
        ...html.matchAll(
          /<span class="algoritma algoritma--soluk">([^<]*<span class="sr-only">[^<]*<\/span>)<\/span>/g,
        ),
      ]
      expect(aktifSatirlar.length, yol).toBe(aktifBeklenen)
      expect(solukSatirlar.length, yol).toBe(solukBeklenen)

      for (const [, govde] of aktifSatirlar) {
        expect(govde, yol).toContain('<span class="sr-only">yazıldı</span>')
      }
      for (const [, govde] of solukSatirlar) {
        expect(govde, yol).toContain('<span class="sr-only">yazılmadı</span>')
      }
    }
  })

  it('faz sayfası ilerlemeyi söyler', () => {
    // Spec §4: "3 / 9 algoritma yazıldı". Aktif sayı içerikten türer.
    const aktifler = aktifAlgoritmalar()
    for (const faz of HARITA) {
      const algoritmalar = faz.asamalar.flatMap((a) => a.algoritmalar)
      const aktif = algoritmalar.filter((a) => aktifler.has(a.id)).length
      expect(oku(`${faz.slug}/index.html`), faz.slug).toContain(
        `${aktif} / ${algoritmalar.length} algoritma yazıldı`,
      )
    }
  })

  it('her aşama satırı aktif/toplam taşır', () => {
    const aktifler = aktifAlgoritmalar()
    for (const faz of HARITA) {
      const bloklar = asamaBloklari(oku(`${faz.slug}/index.html`))
      expect(bloklar.length, faz.slug).toBe(faz.asamalar.length)
      faz.asamalar.forEach((asama, i) => {
        const aktif = asama.algoritmalar.filter((a) => aktifler.has(a.id)).length
        expect(bloklar[i], asama.slug).toContain(
          `<span class="asama-ilerleme">${aktif}/${asama.algoritmalar.length}</span>`,
        )
      })
    }
  })

  it('soluk aşama tek blok, algoritmaları bağlantısız ve tek satırda', () => {
    let solukSayisi = 0
    for (const yol of FAZ_SAYFALARI) {
      for (const blok of asamaBloklari(oku(yol))) {
        if (!blok.startsWith('<li class="asama asama--soluk"')) continue
        solukSayisi++
        expect(blok, yol).not.toContain('<a')
        expect(blok, yol).not.toContain('<ul')
        const satirlar = [...blok.matchAll(/<p class="soluk-algoritmalar">([\s\S]*?)<\/p>/g)]
        expect(satirlar.length, yol).toBe(1)
        const [, satir] = satirlar[0]
        const adet = sinifSay(satir, (b) => b === 'algoritma--soluk')
        expect(adet, yol).toBeGreaterThan(0)
        // n algoritma arasında n-1 ayraç.
        expect((satir.match(/·/g) ?? []).length, yol).toBe(adet - 1)
      }
    }
    expect(solukSayisi).toBeGreaterThan(0)
  })

  it('aktif aşama algoritmaları liste halinde', () => {
    let aktifSayisi = 0
    for (const yol of FAZ_SAYFALARI) {
      for (const blok of asamaBloklari(oku(yol))) {
        if (!blok.startsWith('<li class="asama asama--aktif"')) continue
        aktifSayisi++
        expect(blok, yol).toContain('<ul')
        const maddeler = [...blok.matchAll(/<li class="algoritma[^"]*">([\s\S]*?)<\/li>/g)]
        expect(maddeler.length, yol).toBeGreaterThan(0)
        for (const [, govde] of maddeler) expect(govde, yol).toContain('durum-noktasi')
      }
    }
    expect(aktifSayisi).toBeGreaterThan(0)
  })

  it('dizi etiketi yazı sayısını taşır, algoritma adı bağlantısız kalır', () => {
    // Haritada tıklanan tek öğe dizi etiketidir, algoritma adı değil
    // (spec §0.1 madde 5). blok-transfer dizisinin 7 yayındaki yazısı var
    // ("adresler" describe'undaki YAYINDAKILER listesiyle aynı sayı).
    const html = oku('sezon-ici/index.html')
    expect(html).toContain('class="dizi-etiketi"')
    expect(html).toMatch(/class="dizi-etiketi" href="\/transfer\/blok-transfer\/">Blok Transfer · 7 yazı</)

    // Her aktif algoritma satırının içinde yalnızca dizi-etiketi sınıflı <a>
    // olabilir; algoritma adının kendisi bir bağlantı değildir.
    const satirlar = [...html.matchAll(/<li class="algoritma algoritma--aktif">([\s\S]*?)<\/li>/g)]
    expect(satirlar.length).toBeGreaterThan(0)
    for (const [, govde] of satirlar) {
      const baglantilar = [...govde.matchAll(/<a[^>]*>/g)]
      expect(baglantilar.length).toBeGreaterThan(0)
      for (const [baglanti] of baglantilar) {
        expect(baglanti).toContain('class="dizi-etiketi"')
      }
      expect(govde).not.toMatch(/<span class="algoritma-adi"><a/)
    }
  })

  it('hiçbir sayfada değinme izi yok', () => {
    // Değinme kavramı kalktı (spec §0.1 madde 7): okur "X dizisinde
    // değinildi" notlarıyla karşılaşmamalı. Algoritma ya aktif ya soluktur.
    const suclular = tumSayfalar()
      .filter(({ html }) => html.includes('deginme-notu') || /değinildi/i.test(html))
      .map(({ yol }) => yol)
    expect(suclular).toEqual([])
  })

  it('soluk aşamaya bağlantı yok ve sayfası üretilmez', () => {
    // Onaylanmış sapma: alan dosyası olan ama aktif olmayan aşamanın sayfası
    // yine üretilir (taslak dizinin kırıntı yolu ona bağlanır), yalnızca
    // noindex basar ve site haritasına girmez. Her aşamanın durumu içerikten
    // türer; slug listesi elle tutulmaz.
    const haritaXml = oku('sitemap-0.xml')
    const haritaSayfalari = [...FAZ_SAYFALARI, 'index.html']
    const asamaAktifMi = (b: string) => b === 'asama--aktif'
    for (const asama of asamalar()) {
      const adres = `/${asama.slug}/`
      if (!asama.alanVar) {
        expect(existsSync(DIST + asama.slug), `${asama.slug}: alan dosyası yok`).toBe(false)
      } else if (!asama.aktif) {
        expect(existsSync(DIST + asama.slug + '/index.html'), asama.slug).toBe(true)
        expect(oku(asama.slug + '/index.html'), asama.slug).toContain(NOINDEX)
        expect(haritaXml, asama.slug).not.toContain(`<loc>${SITE}${adres}</loc>`)
      }
      if (asama.aktif) {
        expect(oku(`${asama.faz}/index.html`), asama.slug).toContain(`href="${adres}"`)
      } else {
        for (const yol of haritaSayfalari) {
          expect(oku(yol), `${yol} → ${asama.slug}`).not.toContain(`href="${adres}"`)
        }
      }
    }
    for (const faz of HARITA) {
      const beklenen = asamalar().filter((a) => a.faz === faz.slug && a.aktif).length
      expect(sinifSay(oku(`${faz.slug}/index.html`), asamaAktifMi), faz.slug).toBe(beklenen)
    }
  })

  it('aşama listesi tarayıcı numarası basmaz, yalnızca haritanın numarası görünür', () => {
    // "1. 07 Allocation" hatası: <ol> kendi numarasını, bileşen haritanın
    // numarasını basıyordu. Numarayı kapatan kural paylaşılan stil
    // dosyasında; sayfanın bağladığı CSS'te gerçekten var mı diye bakılır.
    for (const yol of FAZ_SAYFALARI) {
      const html = oku(yol)
      expect(html, yol).toContain('<ol class="faz-haritasi">')
      const stiller = [...html.matchAll(/<link rel="stylesheet" href="\/([^"]+)"/g)]
        .map(([, dosya]) => oku(dosya))
        .join('')
      expect(stiller, yol).toMatch(/\.faz-haritasi\{[^}]*list-style(-type)?:none/)
    }
    expect(oku('sezon-ici/index.html')).toContain('<span class="asama-no">07</span>')
    expect(oku('diger-surecler/index.html')).toContain('<span class="asama-no">12</span>')
  })

  it('ana sayfa üç fazı ve Temeller rafını gösterir', () => {
    const html = oku('index.html')
    expect(html).toContain('href="/sezon-oncesi/"')
    expect(html).toContain('href="/sezon-ici/"')
    expect(html).toContain('href="/diger-surecler/"')
    expect(html).toContain('href="/temeller/"')
    expect(html).toContain('id="harita"')
  })

  it('ana sayfada süreç hattı ve Temeller rafı sırayla', () => {
    // Spec §3: tanım, süreç hattı (faz kartları segment başlığı olarak
    // içinde), Temeller rafı. Menünün "Harita" çapası (id="harita") hattın
    // bölümünde durur.
    const html = oku('index.html')
    const bolum = html.indexOf('id="harita"')
    const hat = html.indexOf('<ol class="surec-hatti"')
    const raf = html.indexOf('class="temeller-rafi"')
    const sira = [bolum, hat, raf]
    expect(sira.every((y) => y > -1), sira.join(',')).toBe(true)
    expect([...sira].sort((a, b) => a - b)).toEqual(sira)
    // Bölüm etiketi hattın hemen öncesinde açılır; arada başka bölüm yok.
    expect(html.slice(bolum, hat)).not.toContain('<section')
  })

  it('Diğer Süreçler sayfası kendi fazıyla başlar ve 404 sayfası ona bağlanır', () => {
    const html = oku('diger-surecler/index.html')
    expect(html).toContain('<h1>Diğer Süreçler</h1>')
    expect(html).toContain('"@type":"CollectionPage"')
    expect(oku('404.html')).toContain('href="/diger-surecler/"')
  })

  it('kırıntı yolu fazla başlar', () => {
    const kirinti = (yol: string) => {
      const html = oku(yol)
      const bas = html.indexOf('class="kirinti"')
      expect(bas, yol).toBeGreaterThan(-1)
      return html.slice(bas, html.indexOf('</nav>', bas))
    }
    const yazi = kirinti('replenishment/depodan-magazaya/sabahki-toplama-emri/index.html')
    const sira = ['href="/sezon-ici/"', 'Sezon İçi', 'Replenishment', 'Depodan Mağazaya']
    const yerler = sira.map((parca) => yazi.indexOf(parca))
    expect(yerler.every((y) => y > -1), yerler.join(',')).toBe(true)
    expect([...yerler].sort((a, b) => a - b)).toEqual(yerler)

    expect(kirinti('temeller/urun-hiyerarsisi/index.html')).not.toContain('Sezon')

    // Demo sayfası da fazla başlar; önceden faz basamağı eksikti.
    const demo = kirinti('transfer/blok-transfer/demo/index.html')
    const demoSirasi = [
      'href="/sezon-ici/"',
      'Sezon İçi',
      'href="/transfer/"',
      'href="/transfer/blok-transfer/"',
      'Demo',
    ]
    const demoYerleri = demoSirasi.map((parca) => demo.indexOf(parca))
    expect(demoYerleri.every((y) => y > -1), demoYerleri.join(',')).toBe(true)
    expect([...demoYerleri].sort((a, b) => a - b)).toEqual(demoYerleri)
  })

  it('Temeller rafı sözlüğe ve veri setine bağlanır', () => {
    const html = oku('temeller/index.html')
    const govde = html.slice(html.indexOf('<main'))
    expect(govde).toContain('href="/sozluk/"')
    expect(govde).toContain('href="/veri-seti/"')
  })
})

/** Ana sayfadaki süreç hattının istasyonları, sırayla: açılış etiketi ve gövdesi. */
function istasyonlar(html: string): { acilis: string; govde: string }[] {
  return [...html.matchAll(/(<li class="istasyon[ "][^>]*>)([\s\S]*?)<\/li>/g)].map(
    ([, acilis, govde]) => ({ acilis, govde }),
  )
}

describe('aşama sayfası dizi kartı', () => {
  // Spec §5: aşama sayfası tanım + algoritma satırları + dizi kartları
  // (başlık, özet, yazı sayısı). Sınıf adı yeni bileşenin
  // (DiziKarti.astro) bastığı sabit ad. Beklenen yazı sayısı içerikten
  // türer (tests/yardimci/icerikDurumu.ts · yayindakiYaziSayisi); RPT'ye
  // yeni bir yazı eklendiğinde bu test elle güncellenmeden geçer.
  it('dizi kartı basar', () => {
    const html = oku('rpt/index.html')
    const beklenen = yayindakiYaziSayisi('rpt', 'tekrar-siparis')
    expect(beklenen).toBeGreaterThan(0)
    expect(html).toContain('class="dizi-karti"')
    expect(html).toContain('href="/rpt/tekrar-siparis/"')
    expect(html).toContain(`${beklenen} yazı`)
  })
})

describe('dizi kapağı yazı listesi', () => {
  // Spec §5: numaralı yazı listesi, her satırda sıra, başlık, tip rozeti,
  // özet. Sınıf adı `dizi-yazi-listesi` — ana sayfadaki Temeller rafı ve
  // aşama sayfasındaki tekil "Yazılar" listesi `yazi-listesi` sınıfını
  // zaten kullanıyordu; aynı adı burada da kullanmak o sayfaları
  // istemeden yeniden biçimlendirirdi (kontrolör kararı, brief'teki
  // `ol.yazi-listesi` ifadesinin yerine geçer).
  it('yazıları tip rozetiyle listeler', () => {
    const html = oku('rpt/tekrar-siparis/index.html')
    const bas = html.indexOf('<ol class="dizi-yazi-listesi">')
    expect(bas).toBeGreaterThan(-1)
    const govde = html.slice(bas, html.indexOf('</ol>', bas))
    const maddeler = [...govde.matchAll(/<li>([\s\S]*?)<\/li>/g)]
    expect(maddeler.length).toBe(yayindakiYaziSayisi('rpt', 'tekrar-siparis'))
    for (const [, madde] of maddeler) {
      expect(madde).toContain('class="rozet')
      expect(madde).toContain('<p class="ozet">')
    }
  })

  it('demo bağlantısı olan dizide bağlantı listenin altında durur', () => {
    const html = oku('transfer/blok-transfer/index.html')
    const listeSonu = html.indexOf('</ol>')
    const demoBas = html.indexOf('class="demo-baglanti"')
    expect(listeSonu).toBeGreaterThan(-1)
    expect(demoBas).toBeGreaterThan(listeSonu)
  })
})

describe('ana sayfa süreç hattı', () => {
  it('ana sayfada on beş istasyon', () => {
    // Spec §3: 15 aşama, dolu = aktif, boş halka = soluk. Aktif sayısı
    // içerikten türer (tests/yardimci/icerikDurumu.ts).
    const html = oku('index.html')
    expect(sinifSay(html, (b) => b === 'istasyon')).toBe(15)
    const aktifBeklenen = asamalar().filter((a) => a.aktif).length
    expect(aktifBeklenen).toBeGreaterThan(0)
    expect(sinifSay(html, (b) => b === 'istasyon--aktif')).toBe(aktifBeklenen)
    expect(sinifSay(html, (b) => b === 'istasyon--soluk')).toBe(15 - aktifBeklenen)
    // Durum şekille birlikte metinle de iletilir.
    for (const { acilis, govde } of istasyonlar(html)) {
      const aktif = acilis.includes('istasyon--aktif')
      expect(govde, acilis).toContain(`<span class="sr-only">${aktif ? 'yazıldı' : 'yazılmadı'}</span>`)
    }
  })

  it('istasyonlar faz sırasıyla', () => {
    const html = oku('index.html')
    const sira = istasyonlar(html).map(({ acilis }) => acilis.match(/data-faz="([^"]+)"/)?.[1])
    expect(sira).toEqual(HARITA.flatMap((faz) => faz.asamalar.map(() => faz.slug)))
    // Numara haritanın kendi numarası, iki haneli.
    const numaralar = istasyonlar(html).map(({ govde }) => govde.match(/<span class="asama-no">(\d+)<\/span>/)?.[1])
    expect(numaralar).toEqual(
      HARITA.flatMap((faz) => faz.asamalar.map((a) => String(a.no).padStart(2, '0'))),
    )
    // Segment başlıkları faz sayfasına bağlanır, hattın içinde.
    const hat = html.slice(html.indexOf('<ol class="surec-hatti"'))
    for (const faz of HARITA) expect(hat, faz.slug).toContain(`href="/${faz.slug}/"`)
  })

  it('yatay düzenin ölçüleri haritadan basılır', () => {
    // Aşama eklenince hat kendiliğinden yeniden dizilsin diye CSS hiçbir
    // aşama sayısı yazmaz; SurecHatti.astro haritadan satır içi değişken
    // basar. Beklenen değerler burada da HARITA'dan türer.
    const html = oku('index.html')
    const oranlar = HARITA.map((faz) => `${faz.asamalar.length}fr`).join(' ')
    expect(html).toContain(`<ol class="surec-hatti" style="--oranlar: ${oranlar}">`)
    const adetler = [...html.matchAll(/<ol class="hat-duraklari" style="--adet: (\d+)">/g)].map(([, n]) => Number(n))
    expect(adetler).toEqual(HARITA.map((faz) => faz.asamalar.length))
    // Her istasyon fazı içindeki 1 tabanlı sırasını taşır; yedinci bir aşama
    // eklense de yerleşim bu değerden okunur.
    const sutunlar = istasyonlar(html).map(({ acilis }) => Number(acilis.match(/style="--sutun: (\d+)"/)?.[1]))
    expect(sutunlar).toEqual(HARITA.flatMap((faz) => faz.asamalar.map((_, i) => i + 1)))
  })

  it('aktif istasyon aşamaya ve dizisine bağlanır', () => {
    const html = oku('index.html')
    const aktifler = new Set(asamalar().filter((a) => a.aktif).map((a) => a.slug))
    const yayindakiler = diziler().filter((d) => d.yayinda)
    for (const { acilis, govde } of istasyonlar(html)) {
      if (!acilis.includes('istasyon--aktif')) continue
      const slug = [...aktifler].find((s) => govde.includes(`<a class="asama-adi" href="/${s}/">`))
      expect(slug, acilis).toBeDefined()
      for (const dizi of yayindakiler.filter((d) => asamaBul(d.alan)?.asama.slug === slug)) {
        expect(govde, dizi.adres).toMatch(new RegExp(`class="dizi-etiketi" href="${dizi.adres}">[^<]+ · \\d+ yazı<`))
      }
    }
  })

  it('soluk istasyon bağlantısız', () => {
    let soluk = 0
    for (const { acilis, govde } of istasyonlar(oku('index.html'))) {
      if (!acilis.includes('istasyon--soluk')) continue
      soluk++
      expect(govde, acilis).not.toContain('<a')
    }
    expect(soluk).toBeGreaterThan(0)
  })

  it('üç faz kartı', () => {
    // Spec §3: faz adı (bağlantı), "a / t algoritma yazıldı". Aktif sayı
    // içerikten türer; aktif aşaması olmayan faz "0 / N" gösterir. Kart
    // segmentin başlığıdır: hattın içinde, segmentin durak listesinden önce;
    // faz adı ayrı bir kart satırında tekrarlanmaz.
    const html = oku('index.html')
    expect(sinifSay(html, (b) => b === 'faz-karti')).toBe(3)
    expect(html).not.toContain('faz-kartlari')
    const kartlar = [...html.matchAll(/<header class="faz-karti">([\s\S]*?)<\/header>/g)].map(([, g]) => g)
    expect(kartlar.length).toBe(3)
    const segmentler = html
      .slice(html.indexOf('<ol class="surec-hatti"'))
      .split('<li class="hat-segmenti">')
      .slice(1)
    expect(segmentler.length).toBe(HARITA.length)
    for (const segment of segmentler) {
      expect(segment.indexOf('<header class="faz-karti">')).toBe(0)
      expect(segment.indexOf('</header>')).toBeLessThan(segment.indexOf('<ol class="hat-duraklari"'))
    }
    const aktifler = aktifAlgoritmalar()
    HARITA.forEach((faz, i) => {
      const algoritmalar = faz.asamalar.flatMap((a) => a.algoritmalar)
      const aktif = algoritmalar.filter((a) => aktifler.has(a.id)).length
      expect(kartlar[i], faz.slug).toContain(`href="/${faz.slug}/"`)
      expect(kartlar[i], faz.slug).toContain(`${aktif} / ${algoritmalar.length} algoritma yazıldı`)
      const aktifAsamasiYok = asamalar().every((a) => a.faz !== faz.slug || !a.aktif)
      if (aktifAsamasiYok) expect(kartlar[i], faz.slug).toContain(`0 / ${algoritmalar.length} algoritma yazıldı`)
    })
  })

  it('ana sayfa artık algoritma listesini basmaz', () => {
    // Algoritmalar faz sayfalarında (spec §3).
    const html = oku('index.html')
    expect(sinifSay(html, (b) => b.startsWith('algoritma--'))).toBe(0)
    expect(html).not.toContain('algoritma--')
  })

  it('süreç hattı geniş ekranda yatay, dar ekranda dikey', () => {
    // 64rem ve üstünde segment genişlikleri aşama sayısıyla orantılı; oran,
    // sütun sayısı ve istasyon sütunu CSS'e değişkenle gelir, sayı yazılmaz.
    const css = baglıCss(oku('index.html'))
    expect(css).toMatch(/\.surec-hatti\{[^}]*list-style(-type)?:none/)
    // Derlenmiş CSS medya sorgusunu aralık sözdizimine çevirir: (width>=64rem).
    const genis = css.match(/@media \((?:min-width:\s*|width>=)64rem\)\{[^@]*\.surec-hatti[,{][^@]*/)?.[0] ?? ''
    expect(genis).toMatch(/\.surec-hatti\{[^}]*grid-template-columns:var\(--oranlar\)/)
    expect(genis).toMatch(/\.hat-duraklari\{[^}]*grid-template-columns:repeat\(var\(--adet\),\s*minmax\(0,\s*1fr\)\)/)
    expect(genis).toMatch(/\.istasyon\{[^}]*grid-column:var\(--sutun\)\s*\/\s*span 2/)
    expect(genis).not.toMatch(/nth-child\(\d+\)/)
    expect(genis).not.toMatch(/\dfr \dfr/)
    // Subgrid'i tanımayan tarayıcı için önce düz satır tanımı.
    expect(genis).toMatch(/grid-template-rows:auto var\(--nokta\) auto;grid-template-rows:subgrid/)
  })
})

/** `acilis` ile başlayan öğenin, ilk `kapanis`a kadarki işaretlemesi; yoksa ''. */
function kesit(html: string, acilis: string, kapanis: string): string {
  const bas = html.indexOf(acilis)
  if (bas === -1) return ''
  return html.slice(bas, html.indexOf(kapanis, bas) + kapanis.length)
}

/** Üretilmiş bütün yazı sayfaları: içerikteki her .mdx bir sayfa. */
function yaziSayfalari(): { yol: string; html: string }[] {
  const yollar = (readdirSync(YAZI_KOKU, { recursive: true }) as string[])
    .map((ad) => ad.split(sep).join('/'))
    .filter((ad) => ad.endsWith('.mdx'))
    .map((ad) => `${ad.slice(0, -'.mdx'.length)}/index.html`)
  return yollar.map((yol) => ({ yol, html: oku(yol) }))
}

describe('yazı sayfası yan gezinmesi', () => {
  // Spec §6: 64rem üstünde üç sütun — sol menü (dizinin yazıları), okuma
  // sütunu, sağ menü ("Bu yazıda", h2 başlıkları). Hikâyede sağ menü yok;
  // h2'siz yazıda da yok. 64rem altında dizi listesi başlığın altında bir
  // <details> kutusu. Sayılar içerikten türer (tests/yardimci/icerikDurumu.ts).
  const RPT = diziSiralamasi('rpt', 'tekrar-siparis')

  it('teknik yazıda "Bu yazıda" h2 sayısı kadar bağlantı', () => {
    const html = oku('rpt/tekrar-siparis/ne-kadar-daha-satardi/index.html')
    const menu = kesit(html, '<nav class="bu-yazida"', '</nav>')
    const hedefler = [...menu.matchAll(/<a href="#([^"]+)"/g)].map(([, id]) => id)
    const makale = kesit(html, '<article', '</article>')
    const h2Sayisi = (makale.match(/<h2[\s>]/g) ?? []).length
    expect(h2Sayisi).toBeGreaterThan(0)
    expect(hedefler.length).toBe(h2Sayisi)
    for (const id of hedefler) expect(html, id).toContain(`id="${id}"`)
    expect(menu).toContain('aria-label="Bu yazıda"')
  })

  it('hikâyede "Bu yazıda" yok', () => {
    const html = oku('rpt/tekrar-siparis/ucuncu-pazartesi/index.html')
    expect(html).toContain('rozet-hikaye')
    expect(sinifSay(html, (b) => b === 'bu-yazida')).toBe(0)
  })

  it("h2'siz yazıda boş kutu yok", () => {
    const sayfalar = yaziSayfalari()
    expect(sayfalar.length).toBeGreaterThan(0)
    for (const { yol, html } of sayfalar) {
      if (sinifSay(html, (b) => b === 'bu-yazida') === 0) continue
      expect(kesit(html, '<nav class="bu-yazida"', '</nav>'), yol).toContain('<a ')
    }
  })

  it('sol menü dizinin bütün yazılarını taşır', () => {
    expect(RPT.length).toBeGreaterThan(2)
    const suanki = RPT[2]
    const html = oku(`rpt/tekrar-siparis/${suanki}/index.html`)
    const menu = kesit(html, '<nav class="dizi-yan-menu"', '</nav>')
    expect(menu).toContain('aria-label="Dizinin yazıları"')
    expect((menu.match(/<li[\s>]/g) ?? []).length).toBe(RPT.length)
    for (const slug of RPT) expect(menu).toContain(`href="/rpt/tekrar-siparis/${slug}/"`)
    expect(menu).toMatch(
      new RegExp(`href="/rpt/tekrar-siparis/${suanki}/"[^>]*aria-current="page"`),
    )
    expect((menu.match(/aria-current="page"/g) ?? []).length).toBe(1)
    expect(menu).toContain('href="/rpt/tekrar-siparis/"')
  })

  it('hazırlanıyor yazı sol menüde işaretli', () => {
    // İçerikte hazırlanıyor yazı olmadığında bu test yalnızca dizinin
    // yayındaki yazılarının işaretsiz olduğunu doğrular.
    for (const { dizi, alan } of diziler()) {
      const sira = diziSiralamasi(alan, dizi)
      if (sira.length === 0) continue
      const menu = kesit(oku(`${alan}/${dizi}/${sira[0]}/index.html`), '<nav class="dizi-yan-menu"', '</nav>')
      const isaretli = (menu.match(/hazırlanıyor/g) ?? []).length
      const beklenen = sira.length - yayindakiYaziSayisi(alan, dizi)
      expect(isaretli, `${alan}/${dizi}`).toBe(beklenen)
    }
  })

  it('mobil dizi kutusu', () => {
    const html = oku(`rpt/tekrar-siparis/${RPT[2]}/index.html`)
    const kutu = kesit(html, '<details class="dizi-kutusu"', '</details>')
    expect(kutu).not.toBe('')
    const ozet = kesit(kutu, '<summary', '</summary>')
    expect(ozet).toContain(`3 / ${RPT.length}`)
    expect((kutu.match(/<li[\s>]/g) ?? []).length).toBe(RPT.length)
    // Kutu başlığın altında, yazının gövdesinden önce.
    expect(html.indexOf('<details class="dizi-kutusu"')).toBeGreaterThan(html.indexOf('<h1'))
  })

  it('tekil yazı sol menüsüz', () => {
    const html = oku('temeller/urun-hiyerarsisi/index.html')
    expect(sinifSay(html, (b) => b === 'dizi-yan-menu')).toBe(0)
    expect(sinifSay(html, (b) => b === 'dizi-kutusu')).toBe(0)
    expect(html).toContain('<article')
  })

  it('yazı sonunda önceki/sonraki kalır, liste sol menüye taşındı', () => {
    const html = oku(`rpt/tekrar-siparis/${RPT[2]}/index.html`)
    const son = kesit(html, '<nav class="dizi-gezinme"', '</nav>')
    expect(son).toContain(`rel="prev" href="/rpt/tekrar-siparis/${RPT[1]}/"`)
    expect(son).toContain(`rel="next" href="/rpt/tekrar-siparis/${RPT[3]}/"`)
    expect(son).toContain('href="/rpt/tekrar-siparis/"')
    expect(son).not.toContain('<ol')
  })

  it('geniş öğeler sağ menüye taşmaz', () => {
    // Karar: sağ menü sticky olduğu için geniş öğe (pre, KaTeX, demo,
    // tablo) onun altından geçemez; menüyü örter ya da menü onu örter.
    // Taşma yalnızca sağ sütun boşken (hikâye ya da h2'siz yazı) açılır:
    // okuma sütununun işaretlemesi o zaman `yazi-duzeni--sag-bos` taşır.
    for (const { yol, html } of yaziSayfalari()) {
      const sagMenu = sinifSay(html, (b) => b === 'bu-yazida') > 0
      const sagBos = sinifSay(html, (b) => b === 'yazi-duzeni--sag-bos') > 0
      expect(sagBos, yol).toBe(!sagMenu)
    }
    const css = baglıCss(oku('rpt/tekrar-siparis/ne-kadar-daha-satardi/index.html'))
    // Yazı düzeninde genişleyen her kural sağ-boş değiştiricisine bağlı.
    const genisleyen = [...css.matchAll(/([^{}]*)\{[^}]*--genis-olcu[^}]*\}/g)]
      .map(([, secici]) => secici)
      .filter((secici) => /duzen-yazi|yazi-duzeni/.test(secici))
    expect(genisleyen.length).toBeGreaterThan(0)
    for (const secici of genisleyen) {
      for (const parca of secici.split(',')) expect(parca, parca).toContain('yazi-duzeni--sag-bos')
    }
  })

  it('yan menüler sticky, CSS saf', () => {
    const css = baglıCss(oku('rpt/tekrar-siparis/ne-kadar-daha-satardi/index.html'))
    expect(css).toMatch(/\.dizi-yan-menu[^{]*\{[^}]*position:\s*sticky/)
    expect(css).toMatch(/\.bu-yazida[^{]*\{[^}]*position:\s*sticky/)
  })
})
