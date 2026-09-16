import { ApiError } from './api'

const MAX_BYTES = 2 * 1024 * 1024
const MAX_BASE64 = 4 * Math.ceil(MAX_BYTES / 3)
const PHOTO_EDGE = 512

export interface ProfilePhoto { path: string; image: string }

/** Normalize only a picture explicitly selected by the user, before uploading it. */
export async function prepareProfilePhoto(path: string): Promise<ProfilePhoto> {
  let encoded = '', preview = path
  // #ifdef H5
  const response = await fetch(path)
  if (!response.ok) throw new ApiError('头像读取失败，请重新选择')
  const file = await response.blob()
  if (file.size > 20 * 1024 * 1024) throw new ApiError('图片超过 20 MB，请选择较小的图片')
  if (file.type && !/^image\/(jpeg|png|webp)$/.test(file.type)) throw new ApiError('请选择 JPG、PNG 或 WebP 图片')
  const temporaryUrl = URL.createObjectURL(file)
  try {
    const picture = await new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve(image)
      image.onerror = () => reject(new ApiError('图片无法读取，请换一张图片'))
      image.src = temporaryUrl
    })
    const canvas = document.createElement('canvas')
    canvas.width = PHOTO_EDGE; canvas.height = PHOTO_EDGE
    const context = canvas.getContext('2d')
    if (!context) throw new ApiError('图片处理失败，请重试')
    const side = Math.min(picture.naturalWidth, picture.naturalHeight)
    if (!side) throw new ApiError('图片无法读取，请换一张图片')
    context.fillStyle = '#fff'; context.fillRect(0, 0, PHOTO_EDGE, PHOTO_EDGE)
    context.drawImage(picture, (picture.naturalWidth - side) / 2, (picture.naturalHeight - side) / 2, side, side, 0, 0, PHOTO_EDGE, PHOTO_EDGE)
    preview = canvas.toDataURL('image/jpeg', 0.86)
    encoded = preview.split(',')[1] || ''
  } finally { URL.revokeObjectURL(temporaryUrl) }
  // #endif
  // #ifdef MP-WEIXIN
  const info = await new Promise<UniApp.GetImageInfoSuccessData>((resolve, reject) => uni.getImageInfo({
    src: path, success: resolve, fail: () => reject(new ApiError('头像读取失败，请重新选择')),
  }))
  const scale = Math.min(1, PHOTO_EDGE / Math.max(info.width, info.height))
  // Older WeChat versions may not compress an already-small temporary avatar.
  // Fall back to the selected file, with the same upload-size check.
  preview = await new Promise<string>(resolve => uni.compressImage({
    src: info.path || path, quality: 85,
    compressedWidth: Math.max(1, Math.round(info.width * scale)),
    compressedHeight: Math.max(1, Math.round(info.height * scale)),
    success: result => resolve(result.tempFilePath || info.path || path),
    fail: () => resolve(info.path || path),
  }))
  encoded = await new Promise<string>((resolve, reject) => uni.getFileSystemManager().readFile({
    filePath: preview, encoding: 'base64',
    success: result => typeof result.data === 'string' ? resolve(result.data) : reject(new ApiError('头像读取失败，请重新选择')),
    fail: () => reject(new ApiError('头像读取失败，请重新选择')),
  }))
  // #endif
  if (!encoded) throw new ApiError('头像读取失败，请重新选择')
  if (encoded.length > MAX_BASE64) throw new ApiError('图片处理后仍超过 2 MB，请换一张图片')
  return { path: preview, image: encoded }
}
