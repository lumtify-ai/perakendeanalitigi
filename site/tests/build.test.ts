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
  it('türkçe ana sayfa üretilir', () => {
    expect(existsSync(DIST + 'tr/index.html')).toBe(true)
  })

  it('kök adres türkçeye yönlenir', () => {
    expect(existsSync(DIST + 'index.html')).toBe(true)
    expect(oku('index.html')).toContain('/tr/')
  })

  it('sayfa dili türkçe işaretlenir', () => {
    expect(oku('tr/index.html')).toContain('lang="tr"')
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
    const html = oku('tr/index.html')
    expect(html).toContain('href="/tr/veri-seti/"')
    expect(html).toContain('href="/tr/sozluk/"')
  })

  it('sayfa açıklaması meta olarak basılır', () => {
    expect(oku('tr/index.html')).toContain('name="description"')
  })

  it('hiçbir sayfada tarih görünmez', () => {
    // Ana spec'in başarısızlık işareti: "son yazı: 4 ay önce"
    const html = oku('tr/index.html')
    expect(html).not.toMatch(/\d{1,2}\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)/)
  })
})

describe('sözlük', () => {
  it('sözlük sayfası her maddeyi çapayla basar', () => {
    const html = oku('tr/sozluk/index.html')
    expect(html).toContain('id="cover"')
    expect(html).toContain('id="kiriklik"')
    expect(html).toContain('Sell-Through Rate')
  })

  it('sözlük DefinedTermSet olarak işaretlenir', () => {
    expect(oku('tr/sozluk/index.html')).toContain('DefinedTermSet')
  })

  it('tooltip tanımı HTML içinde durur', () => {
    // Yapay zekâ tarayıcıları JS çalıştırmaz; tanım DOM'da olmalı
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('class="terim"')
    expect(html).toContain('yeterlilik süresi')
  })

  it('tooltip için script üretilmez', () => {
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })
})

describe('kadro', () => {
  it('kadro sayfası üç karakteri de tanıtır', () => {
    const html = oku('tr/kadro/index.html')
    expect(html).toContain('Ali')
    expect(html).toContain('Veli')
    expect(html).toContain('Pelin')
    expect(html).toContain('Allocator')
    expect(html).toContain('Planner')
  })
})

describe('yazı sayfası', () => {
  it('dizili yazı üretilir', () => {
    expect(existsSync(DIST + 'tr/transfer/blok-transfer/sonuclar/index.html')).toBe(true)
  })

  it('tekil alanın yazısı üretilir', () => {
    expect(existsSync(DIST + 'tr/temeller/urun-hiyerarsisi/index.html')).toBe(true)
  })

  it('rozet ve kırıntı yolu basılır', () => {
    const html = oku('tr/transfer/blok-transfer/sonuclar/index.html')
    expect(html).toContain('rozet-sonuc')
    expect(html).toContain('BreadcrumbList')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('teknik ve sonuç yazıları TechArticle işaretlenir', () => {
    expect(oku('tr/transfer/blok-transfer/sonuclar/index.html')).toContain('TechArticle')
  })

  it('hikâye yazısı Article işaretlenir', () => {
    const html = oku('tr/transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('"@type":"Article"')
  })

  it('dizi gezinmesi önceki ve sonrakini verir', () => {
    const html = oku('tr/transfer/blok-transfer/matematiksel-model/index.html')
    expect(html).toContain('href="/tr/transfer/blok-transfer/karar-nasil-verilir/"')
    expect(html).toContain('href="/tr/transfer/blok-transfer/sql-ve-python/"')
  })

  it('hikâye yazısı kadro kutusuyla açılır', () => {
    const html = oku('tr/transfer/blok-transfer/magazanin-sorunu/index.html')
    expect(html).toContain('kadro-kutusu')
    expect(html).toContain('Allocator')
  })
})

describe('dizi sayfası', () => {
  it('beş yazıyı sırayla listeler', () => {
    const html = oku('tr/transfer/blok-transfer/index.html')
    const sira = ['magazanin-sorunu', 'karar-nasil-verilir', 'matematiksel-model', 'sql-ve-python', 'sonuclar']
    const yerler = sira.map((slug) => html.indexOf(slug))
    expect(yerler.every((y) => y > -1)).toBe(true)
    expect([...yerler].sort((a, b) => a - b)).toEqual(yerler)
  })

  it('kısayolu açıkça söyler', () => {
    expect(oku('tr/transfer/blok-transfer/index.html')).toMatch(/hikâye|hikaye/i)
  })

  it('CreativeWorkSeries olarak işaretlenir', () => {
    expect(oku('tr/transfer/blok-transfer/index.html')).toContain('CreativeWorkSeries')
  })
})

describe('alan sayfası', () => {
  it('dizili alan dizileri listeler', () => {
    const html = oku('tr/transfer/index.html')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('tekil alan yazıları listeler', () => {
    const html = oku('tr/temeller/index.html')
    expect(html).toContain('href="/tr/temeller/urun-hiyerarsisi/"')
  })

  it('tanım paragrafıyla açılır', () => {
    // Hikâyeyle açılan sayfa alıntılanmaz (ana spec §9)
    const html = oku('tr/transfer/index.html')
    const govde = html.slice(html.indexOf('<main'))
    expect(govde).toMatch(/Transfer,\s*bir mağazada/)
  })

  // Eski hali yalnizca tr/transfer sayfasinda `<pre` ariyordu ve mevcut alan
  // metninde zaten kod blogu yoktu: test hicbir zaman kirilamazdi. Kural
  // artik build dogrulamasinda zorlaniyor (src/lib/dogrula.ts ·
  // alanGovdeleriDogrula, tests/dogrula.test.ts); burada yalnizca sonucun
  // gercekten oyle oldugu, hem de her alan sayfasi icin dogrulaniyor.
  it('alan sayfası kod içermez', () => {
    for (const alan of ['tr/transfer/index.html', 'tr/temeller/index.html']) {
      expect(oku(alan), alan).not.toContain('<pre')
    }
  })
})

describe('ana sayfa', () => {
  it('tanım paragrafıyla açılır', () => {
    const govde = oku('tr/index.html')
    expect(govde).toMatch(/Perakende analitiği/)
  })

  it('ağacın tamamını gösterir', () => {
    const html = oku('tr/index.html')
    expect(html).toContain('href="/tr/transfer/"')
    expect(html).toContain('href="/tr/temeller/"')
    expect(html).toContain('href="/tr/transfer/blok-transfer/"')
  })

  it('akış veya son yazılar bölümü içermez', () => {
    const html = oku('tr/index.html')
    expect(html).not.toMatch(/son yazılar|en yeni|güncel yazılar/i)
  })
})

describe('veri seti sayfası', () => {
  it('Dataset olarak işaretlenir', () => {
    // Rakipler veri yayınlamaz; bu işaretleme ayrıştırıcıdır
    expect(oku('tr/veri-seti/index.html')).toContain('"@type":"Dataset"')
  })

  it('yedi tabloyu da listeler', () => {
    const html = oku('tr/veri-seti/index.html')
    for (const tablo of ['magaza', 'urun', 'takvim', 'satis', 'stok', 'sevkiyat', 'kayip_satis']) {
      expect(html).toContain(tablo)
    }
  })

  it('üç formatı da duyurur', () => {
    const html = oku('tr/veri-seti/index.html')
    expect(html).toContain('CSV')
    expect(html).toContain('Parquet')
    expect(html).toContain('DuckDB')
  })
})

describe('demo', () => {
  it('demo sayfası üretilir', () => {
    expect(existsSync(DIST + 'tr/transfer/blok-transfer/demo/index.html')).toBe(true)
  })

  it('bütün kombinasyonlar HTML içinde hazır durur', () => {
    // Sunucu yok; sayfa her koşulda anında açılır
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('data-anahtar="4|0"')
    expect(html).toContain('data-anahtar="12|2"')
  })

  it('parametre seçimi radio ile yapılır, script ile değil', () => {
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
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
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('<style')
    expect(html).toContain(':has(')
    expect(html).not.toContain('hidden')
    expect(html).not.toMatch(/<script(?![^>]*type="application\/ld\+json")/)
  })

  it(':has() desteklenmeyen tarayıcı için @supports yedeği var', () => {
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    expect(html).toContain('@supports not selector(:has(*))')
  })

  it('üretilen kural sayısı kombinasyon sayısına eşit', async () => {
    const { default: veri } = await import('../src/data/senaryolar/blok-transfer.json')
    const beklenenAnahtarSayisi = veri.parametreler.reduce(
      (carpim: number, p: { degerler: unknown[] }) => carpim * p.degerler.length,
      1,
    )
    const html = oku('tr/transfer/blok-transfer/demo/index.html')
    const stilEslesme = html.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(stilEslesme).not.toBeNull()
    const stilIcerigi = stilEslesme![1]
    const kuralSayisi = (stilIcerigi.match(/\[data-anahtar="[^"]+"\]\s*\{\s*display:\s*block\s*\}/g) ?? []).length
    expect(kuralSayisi).toBe(beklenenAnahtarSayisi)
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
    expect(sayfalar.map(({ yol }) => yol)).toContain('tr/index.html')
    expect(sayfalar.map(({ yol }) => yol)).toContain(
      'tr/transfer/blok-transfer/sonuclar/index.html',
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
    // yazının sonuna koymak onu beş reklama çevirir ve güveni bitirir.
    const gecenler = tumSayfalar().filter(({ html }) => html.includes('lumtify-koprusu'))
    expect(gecenler.map(({ yol }) => yol)).toEqual([
      'tr/transfer/blok-transfer/sonuclar/index.html',
    ])
    expect(gecenler[0].html.split('lumtify-koprusu').length - 1).toBe(1)
  })
})

describe('üst menü', () => {
  // Tasarım dokümanı §9. "Alanlar" bağlantısı olmadan derin bir yazı
  // sayfasından alanların listesine giden üst düzey bir yol yoktu.
  it('dört bağlantıyı da her sayfada basar', () => {
    for (const { yol, html } of tumSayfalar()) {
      if (yol === 'index.html') continue // kök yönlendirme sayfası
      expect(html, yol).toContain('href="/tr/#alanlar"')
      expect(html, yol).toContain('href="/tr/veri-seti/"')
      expect(html, yol).toContain('href="/tr/sozluk/"')
      expect(html, yol).toContain('href="/tr/kadro/"')
    }
  })

  it('Alanlar bağlantısının hedefi ana sayfada gerçekten var', () => {
    expect(oku('tr/index.html')).toContain('id="alanlar"')
  })
})

describe('hazırlanıyor yazılar', () => {
  it('dizi kapağı hazırlanıyor işaretini basar', () => {
    // Tasarım dokümanı §3: yayınlanmamış yazılar dizide görünür ama
    // "hazırlanıyor" olarak işaretlenir — kapsamı gösterir, kronoloji hissi
    // yaratmaz.
    expect(oku('tr/transfer/blok-transfer/index.html')).toContain('hazırlanıyor')
  })

  it('hazırlanıyor yazı noindex basar', () => {
    expect(oku('tr/transfer/blok-transfer/sonuclar/index.html')).toContain(
      'name="robots" content="noindex"',
    )
  })

  it('yayına açık sayfalar noindex basmaz', () => {
    for (const yol of [
      'tr/index.html',
      'tr/sozluk/index.html',
      'tr/transfer/index.html',
      'tr/temeller/urun-hiyerarsisi/index.html',
    ]) {
      expect(oku(yol), yol).not.toContain('noindex')
    }
  })

  it('site haritası hazırlanıyor adresleri ilan etmez', () => {
    // İlk taramada tek cümlelik yer tutucu sayfalar görmek, geri alması en
    // zor birinci izlenimdir.
    const harita = oku('sitemap-0.xml')
    for (const adres of [
      '/tr/transfer/blok-transfer/sonuclar/',
      '/tr/transfer/blok-transfer/magazanin-sorunu/',
    ]) {
      expect(harita, adres).not.toContain(adres)
    }
  })

  it('site haritası yayına açık adresleri ilan etmeye devam eder', () => {
    const harita = oku('sitemap-0.xml')
    expect(harita).toContain('/tr/transfer/blok-transfer/')
    expect(harita).toContain('/tr/sozluk/')
    expect(harita).toContain('/tr/veri-seti/')
    expect(harita).toContain('/tr/temeller/urun-hiyerarsisi/')
  })

  it('hazırlanıyor yazının sayfası yine de üretilir', () => {
    // Dizi kapağı onlara bağlanıyor; kırık bağlantı bırakılmaz.
    expect(existsSync(DIST + 'tr/transfer/blok-transfer/sonuclar/index.html')).toBe(true)
  })
})

describe('gömülü demo', () => {
  // Tasarım dokümanı §5: terim, kadro ve demo aynı deseni kullanır —
  // tek kaynak, ikinci gösterim. Demo bu deseni tamamlar.
  it('demo sql-ve-python yazısına gömülüdür', () => {
    const html = oku('tr/transfer/blok-transfer/sql-ve-python/index.html')
    expect(html).toContain('data-anahtar="4|0"')
    expect(html).toContain('data-anahtar="12|2"')
  })

  it('gömülü demonun style bloğu article bağlamında derlenir', () => {
    const html = oku('tr/transfer/blok-transfer/sql-ve-python/index.html')
    const baslangic = html.indexOf('<article')
    const bitis = html.indexOf('</article>')
    expect(baslangic).toBeGreaterThan(-1)
    const govde = html.slice(baslangic, bitis)
    expect(govde).toContain('<style')
    expect(govde).toContain(':has(')
    expect(govde).toContain('demo-sonuclar')
  })

  it('gömülü demo da JavaScript getirmez', () => {
    const html = oku('tr/transfer/blok-transfer/sql-ve-python/index.html')
    expect(html).not.toMatch(SCRIPT_DESENI)
  })
})

describe('KaTeX', () => {
  it('satır içi ve blok matematik build sırasında derlenir', () => {
    const html = oku('tr/transfer/blok-transfer/matematiksel-model/index.html')
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
    expect(oku('tr/transfer/blok-transfer/matematiksel-model/index.html')).toContain(
      '"@type":"TechArticle"',
    )
  })

  it('anlatıcı yazı Article işaretlenir', () => {
    expect(oku('tr/temeller/urun-hiyerarsisi/index.html')).toContain('"@type":"Article"')
  })

  it('tekil sayfalarda da BreadcrumbList var', () => {
    // Tasarım dokümanı §11 "her sayfa" diyor. Ana sayfa hariç: orada kırıntı
    // yolu anlamsızdır.
    for (const yol of ['tr/sozluk/index.html', 'tr/kadro/index.html', 'tr/veri-seti/index.html']) {
      expect(oku(yol), yol).toContain('BreadcrumbList')
    }
  })

  it('JSON-LD adresleri yapılandırmadaki origin ile üretilir', () => {
    // Alan adı hâlâ açık bir soru; elle yazılan origin değişince üç JSON-LD
    // sessizce yanlış URL basardı.
    const html = oku('tr/transfer/blok-transfer/index.html')
    expect(html).toContain('"item":"https://perakendeanalitigi.com/tr/transfer/"')
    expect(html).toContain('"url":"https://perakendeanalitigi.com/tr/transfer/blok-transfer/')
  })
})

describe('tekil alan yazısı', () => {
  it('dizi gezinmesi taşımaz', () => {
    // Tekil alan yazısı bir algoritmaya ait değildir; önceki/sonraki yoktur.
    const html = oku('tr/temeller/urun-hiyerarsisi/index.html')
    expect(html).not.toContain('dizi-gezinme')
    expect(html).not.toContain('rel="prev"')
    expect(html).not.toContain('rel="next"')
  })

  it('kırıntı yolu iki basamaklıdır', () => {
    const html = oku('tr/temeller/urun-hiyerarsisi/index.html')
    expect(html).toContain('href="/tr/temeller/"')
    expect(html).toContain('"position":2')
    expect(html).not.toContain('"position":3')
  })
})
