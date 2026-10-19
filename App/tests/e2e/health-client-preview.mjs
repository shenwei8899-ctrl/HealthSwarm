import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
const root = path.resolve(process.env.HEALTH246_H5_DIR || '.codex/client-246-20261016/api-h5')
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }
const server = http.createServer(async (request, response) => {
  if (request.url.startsWith('/api/') || request.url.startsWith('/fixture-')) {
    const upstream = http.request({ hostname: '127.0.0.1', port: 15487, path: request.url, method: request.method, headers: { ...request.headers, host: '127.0.0.1:15487' } }, result => {
      response.writeHead(result.statusCode, result.headers); result.pipe(response)
    })
    upstream.on('error', () => { response.writeHead(502); response.end('Isolated fixture unavailable') })
    request.pipe(upstream); response.on('close', () => upstream.destroy()); return
  }
  try {
    const url = new URL(request.url, 'http://localhost'), target = path.resolve(root, '.' + decodeURIComponent(url.pathname))
    if (target !== root && !target.startsWith(root + path.sep)) { response.writeHead(403); response.end(); return }
    const filename = path.extname(target) ? target : path.join(root, 'index.html')
    const data = await fs.readFile(filename)
    response.writeHead(200, { 'Content-Type': mime[path.extname(filename)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); response.end(data)
  } catch { response.writeHead(404); response.end('Not found') }
})
server.listen(15189, '127.0.0.1', () => console.log('Synthetic client preview ready at http://127.0.0.1:15189'))
