// site/scripts/sayac-oku.ts
//
// Ziyaret sayacının raporu: `npm run sayac` ya da `npm run sayac -- 7`.
// Gerekenler: CLOUDFLARE_ACCOUNT_ID ve "Account Analytics Read" izinli
// CLOUDFLARE_API_TOKEN ortam değişkenleri.
import { ozetle, sorgu, type Satir } from './sayacOzeti'

const hesap = process.env.CLOUDFLARE_ACCOUNT_ID
const anahtar = process.env.CLOUDFLARE_API_TOKEN
if (!hesap || !anahtar) {
  console.error('CLOUDFLARE_ACCOUNT_ID ve CLOUDFLARE_API_TOKEN tanımlı olmalı.')
  process.exit(1)
}

const gun = Number(process.argv[2] ?? 30)
const yanit = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${hesap}/analytics_engine/sql`,
  { method: 'POST', headers: { Authorization: `Bearer ${anahtar}` }, body: sorgu(gun) },
)
if (!yanit.ok) {
  console.error(`Sorgu reddedildi (${yanit.status}): ${await yanit.text()}`)
  process.exit(1)
}

// SQL API sayıları JSON'da metin olarak da döndürebilir; hepsi Number'dan geçer.
const { data } = (await yanit.json()) as { data: Record<string, string | number>[] }
const satirlar: Satir[] = data.map((d) => ({
  gun: Number(d.gun),
  sayfa: String(d.sayfa),
  ulke: String(d.ulke),
  ag: String(d.ag),
  tarayici: String(d.tarayici),
  istekTuru: String(d.istekTuru),
  goruntuleme: Number(d.goruntuleme),
  tekil: Number(d.tekil),
  yeni: Number(d.yeni),
}))

const ozet = ozetle(satirlar)

console.log(`\nSon ${gun} gün, insan tahmini (botlar ayıklanmış)\n`)
console.log('Gün         Tekil tarayıcı  Yeni  Görüntüleme')
for (const g of ozet.gunler) {
  console.log(
    `${g.gun}  ${String(g.tekil).padStart(14)}  ${String(g.yeni).padStart(4)}  ${String(g.goruntuleme).padStart(11)}`,
  )
}
console.log(
  `Toplam      ${String(ozet.toplam.tekil).padStart(14)}  ${String(ozet.toplam.yeni).padStart(4)}  ${String(ozet.toplam.goruntuleme).padStart(11)}`,
)
console.log('\n"Tekil" her tarayıcıyı günde bir sayar; günler toplanınca aynı kişi birkaç kez sayılır.')
console.log('"Yeni" siteye ilk kez gelen tarayıcıdır; dönüp gelen eski okuru saymaz, önbelleğini silen ya da gizli sekme açan okuru yeniden sayar.')

console.log('\nEn çok okunan sayfalar')
for (const [sayfa, adet] of ozet.sayfalar.slice(0, 15)) {
  console.log(`${String(adet).padStart(6)}  ${sayfa}`)
}

console.log('\nÜlkeler')
for (const [ulke, adet] of ozet.ulkeler.slice(0, 10)) {
  console.log(`${String(adet).padStart(6)}  ${ulke || '(bilinmiyor)'}`)
}

console.log('\nElenen görüntüleme')
for (const [neden, adet] of Object.entries(ozet.elenen)) {
  console.log(`${String(adet).padStart(6)}  ${neden}`)
}
