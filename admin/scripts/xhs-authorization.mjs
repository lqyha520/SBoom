/** 所有有数据或副作用的桥接操作都向后台在线核验，来源白名单由调用方先检查。 */
export async function authorizeLocalRequest(request, origin, verifyFetch = fetch) {
  const token = request.headers['x-admin-capability']
  if (typeof token !== 'string' || !token || token.length > 4096) return false
  try {
    const result = await verifyFetch(new URL('/api/v1/local-access/verify', origin), {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, origin, path: request.url, method: request.method }),
    })
    return result.ok && (await result.json()).authorized === true
  } catch { return false }
}
