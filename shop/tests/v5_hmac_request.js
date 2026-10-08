const crypto = require('crypto');
const fs = require('fs');

const [method, inputPath, bodyFile, secret] = process.argv.slice(2);
if (!method || !inputPath || !secret) {
  console.error('Usage: node tests/v5_hmac_request.js METHOD /path [body.json|-] SECRET');
  process.exit(2);
}
const body = !bodyFile || bodyFile === '-' ? '' : fs.readFileSync(bodyFile, 'utf8').trim();
const timestamp = Math.floor(Date.now() / 1000);
const nonce = crypto.randomBytes(16).toString('hex');
const pathname = '/' + inputPath.split('?')[0].replace(/^\/+/, '');
const digest = crypto.createHash('sha256').update(body).digest('hex');
const canonical = `${method.toUpperCase()}\n${pathname}\n${timestamp}\n${nonce}\n${digest}`;
const signature = crypto.createHmac('sha256', secret).update(canonical).digest('hex');
console.log(JSON.stringify({
  method: method.toUpperCase(), path: pathname,
  headers: {'X-Client-Id': 'replace-with-client-id', 'X-Timestamp': String(timestamp), 'X-Nonce': nonce, 'X-Signature': signature, 'Idempotency-Key': crypto.randomUUID(), 'Content-Type': 'application/json'},
  body: body ? JSON.parse(body) : null,
}, null, 2));
