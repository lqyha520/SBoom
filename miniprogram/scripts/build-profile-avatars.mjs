import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

// Original, local artwork. All five portraits share a palette and proportions
// so they look the same in WeChat and H5, regardless of the device's emoji font.
const eyes = '<ellipse cx="76" cy="103" rx="4.5" ry="6" fill="#34463e"/><ellipse cx="116" cy="103" rx="4.5" ry="6" fill="#34463e"/><circle cx="77" cy="101" r="1.3" fill="#fff"/><circle cx="117" cy="101" r="1.3" fill="#fff"/>'
const cheeks = '<ellipse cx="61" cy="118" rx="10" ry="5" fill="#edb0a1" opacity=".55"/><ellipse cx="131" cy="118" rx="10" ry="5" fill="#edb0a1" opacity=".55"/>'
const mouth = '<path d="M90 126q6 6 12 0" fill="none" stroke="#536057" stroke-width="3" stroke-linecap="round"/>'
const portraits = {
  fox: ['#f8e9d9', `<path d="M44 88 43 36Q44 28 52 35L80 58M112 58l28-23q8-7 9 1l-1 52" fill="#df945e"/><path d="m51 66 1-20 17 15m54 0 17-15 1 20" fill="#f5c4aa"/><path d="M43 82Q47 56 96 55t53 27l9 24-18 28q-13 20-44 21t-44-21l-18-28Z" fill="#e8a46d"/><path d="M39 105q18-13 34-5l23 24 23-24q16-8 34 5l-18 29q-16 18-39 18t-39-18Z" fill="#fff7e8"/>${eyes}${cheeks}<path d="M87 118q9-7 18 0-9 14-18 0" fill="#46534a"/>${mouth}<path d="m71 151 25 8 25-8-5 21H76Z" fill="#6e9c82"/>`],
  panda: ['#e5eee8', `<circle cx="55" cy="59" r="23" fill="#4d6055"/><circle cx="137" cy="59" r="23" fill="#4d6055"/><ellipse cx="96" cy="104" rx="63" ry="55" fill="#fffdf5"/><ellipse cx="72" cy="102" rx="17" ry="21" transform="rotate(22 72 102)" fill="#4d6055"/><ellipse cx="120" cy="102" rx="17" ry="21" transform="rotate(-22 120 102)" fill="#4d6055"/><circle cx="75" cy="101" r="5" fill="#fff"/><circle cx="117" cy="101" r="5" fill="#fff"/><circle cx="76" cy="102" r="3" fill="#2f4035"/><circle cx="116" cy="102" r="3" fill="#2f4035"/>${cheeks}<ellipse cx="96" cy="119" rx="7" ry="5" fill="#4d6055"/>${mouth}<path d="M76 150q20 12 40 0l-4 22H80Z" fill="#8fb69a"/><path d="m130 153 13-14m-8 9 0-10m3 6 9-2" stroke="#6c9579" stroke-width="4" stroke-linecap="round"/>`],
  penguin: ['#e1edf7', `<ellipse cx="96" cy="108" rx="61" ry="70" fill="#557386"/><path d="m47 96-18 31q-6 13 12 10m104-41 18 31q6 13-12 10" fill="#557386"/><path d="M49 95Q47 64 70 62q16-1 26 17 10-18 26-17 23 2 21 33l4 22q0 45-51 46t-51-46Z" fill="#fbfcf5"/>${eyes}${cheeks}<path d="M86 119q10-9 20 0l-10 10Z" fill="#e6af5b"/><path d="M48 145q48 18 96 0l-4 13q-44 17-88 0Z" fill="#b9d1bf"/><path d="m123 155 14-2 3 22-14 3Z" fill="#9ebfaa"/>`],
  deer: ['#f2eadc', `<g stroke="#aa855b" stroke-width="7" stroke-linecap="round" fill="none"><path d="m69 67-8-29 5-17m-6 17-14-6m77 35 8-29-5-17m6 17 14-6"/></g><path d="M59 81Q25 82 28 56q24-5 40 17m65 8q34 1 31-25-24-5-40 17" fill="#cfaa7e"/><path d="M52 72 39 64m101 8 13-8" stroke="#ecc6a7" stroke-width="9" stroke-linecap="round"/><ellipse cx="96" cy="111" rx="52" ry="51" fill="#d8b187"/><ellipse cx="96" cy="128" rx="32" ry="27" fill="#f7e7d0"/><circle cx="89" cy="80" r="3" fill="#fff3df"/><circle cx="104" cy="82" r="3" fill="#fff3df"/>${eyes}${cheeks}<ellipse cx="96" cy="118" rx="7" ry="5" fill="#705d48"/>${mouth}<path d="m77 153 19 7 19-7-5 19H82Z" fill="#84a394"/>`],
  rabbit: ['#f6e6eb', `<ellipse cx="70" cy="57" rx="17" ry="37" transform="rotate(-13 70 57)" fill="#fffcf5"/><ellipse cx="122" cy="57" rx="17" ry="37" transform="rotate(13 122 57)" fill="#fffcf5"/><ellipse cx="70" cy="54" rx="8" ry="26" transform="rotate(-13 70 54)" fill="#eac0c2"/><ellipse cx="122" cy="54" rx="8" ry="26" transform="rotate(13 122 54)" fill="#eac0c2"/><ellipse cx="96" cy="112" rx="60" ry="48" fill="#fffcf5"/>${eyes}${cheeks}<path d="M90 118q6-5 12 0l-6 7Z" fill="#d69296"/>${mouth}<path d="m94 157-19-9-4 22 23-9m4-4 19-9 4 22-23-9" fill="#8fb5a0"/><circle cx="96" cy="159" r="5" fill="#6d9a83"/>`],
}
const output = fileURLToPath(new URL('../src/static/avatars/', import.meta.url))
await mkdir(output, { recursive: true })
for (const [key, [background, drawing]] of Object.entries(portraits)) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 192 192"><rect width="192" height="192" rx="96" fill="${background}"/><circle cx="155" cy="36" r="7" fill="#fff" opacity=".5"/><circle cx="30" cy="149" r="5" fill="#fff" opacity=".6"/>${drawing}</svg>`
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9, palette: true }).toFile(output + key + '.png')
}
console.log('Built five local 192 × 192 profile portraits.')
