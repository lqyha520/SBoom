import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

// 3dicons, CC0-1.0. Pin the artwork so builds cannot silently change its content.
const source = 'https://cdn.jsdelivr.net/gh/realvjy/3dicons@8884d59e68a7bae0e0e2163af5b6c2ad992c01c8/static/notebook-dynamic-00.png'
const response = await fetch(source, { signal: AbortSignal.timeout(30000) })
if (!response.ok) throw new Error(`Notebook source returned ${response.status}`)
const original = Buffer.from(await response.arrayBuffer())
if (original.subarray(1, 4).toString() !== 'PNG') throw new Error('Expected a PNG notebook image')
const directory = fileURLToPath(new URL('../src/static/illustrations/', import.meta.url))
await mkdir(directory, { recursive: true })
await sharp(original).resize(512, 512, { fit: 'inside', withoutEnlargement: true }).png({ compressionLevel: 9 }).toFile(directory + 'notebook.png')
console.log('Created static/illustrations/notebook.png (512 x 512, transparent PNG).')
