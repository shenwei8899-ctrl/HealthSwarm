import test from 'node:test'
import assert from 'node:assert/strict'
import { uploadMealPhoto, previewMealPhoto, healthImageApiReady } from '../src/services/health-upload.js'
import { setSession } from '../src/services/session.js'

function setup() {
  const memory=new Map();let uploaded,downloaded
  globalThis.window={}
  globalThis.uni={getStorageSync:k=>memory.get(k),setStorageSync:(k,v)=>memory.set(k,v),uploadFile:o=>{uploaded=o},downloadFile:o=>{downloaded=o}}
  setSession({accountId:'synthetic',householdId:'family',token:'test-token'})
  return {upload:()=>uploaded,download:()=>downloaded}
}
test('upload and preview allow only explicitly enabled loopback HTTP',()=>{
  assert.equal(healthImageApiReady('http://127.0.0.1:18550',true),true)
  assert.equal(healthImageApiReady('http://localhost:18550',true),true)
  assert.equal(healthImageApiReady('http://127.0.0.1:18550',false),false)
  assert.equal(healthImageApiReady('http://example.com',true),false)
  assert.equal(healthImageApiReady('http://127.0.0.1.example.com',true),false)
})
test('multipart sends private authentication and meal purpose, never a public URL',async()=>{
  const h=setup(),p=uploadMealPhoto('member','temp-image')
  assert.equal(h.upload().header.Authorization,'Bearer test-token');assert.deepEqual(h.upload().formData,{member_id:'member',purpose:'meal'})
  assert.equal(h.upload().name,'file');h.upload().success({statusCode:201,data:JSON.stringify({upload_id:'image',purpose:'meal'})})
  assert.equal((await p).upload_id,'image')
})
test('late upload from previous login is rejected',async()=>{
  const h=setup(),p=uploadMealPhoto('member','temp-image');setSession({accountId:'other',householdId:'family',token:'other'})
  h.upload().success({statusCode:201,data:'{"upload_id":"image","purpose":"meal"}'});await assert.rejects(p,/账号已切换/)
})
test('network uncertainty and malformed upload receipt never become a usable photo',async()=>{
  const h=setup();let p=uploadMealPhoto('member','temp-image');h.upload().fail();await assert.rejects(p,/结果未知/)
  p=uploadMealPhoto('member','temp-image');h.upload().success({statusCode:201,data:'invalid'});await assert.rejects(p,/响应无法读取/)
  p=uploadMealPhoto('member','temp-image');h.upload().success({statusCode:201,data:'{"upload_id":"image","purpose":"report"}'});await assert.rejects(p,/回执无效/)
})
test('preview requires authenticated success and rejects revoked or changed identity',async()=>{
  const h=setup();let p=previewMealPhoto('image');assert.equal(h.download().header.Authorization,'Bearer test-token')
  h.download().success({statusCode:403});await assert.rejects(p,/无权查看/)
  p=previewMealPhoto('image');setSession({accountId:'other',householdId:'family'});h.download().success({statusCode:200,tempFilePath:'private'});await assert.rejects(p,/账号已切换/)
})
