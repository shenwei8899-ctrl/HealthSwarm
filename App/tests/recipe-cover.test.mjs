import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {spawnSync} from 'node:child_process'
import {recipeCover} from '../src/utils/recipe-cover.js'
import {recipeCovers} from '../src/data/recipe-covers.js'
import {publicImageUrl} from '../src/services/public-images.js'

test('reviewed covers match the exact saved source without changing business recipe data',()=>{
 const record=recipeCovers[0]
 const dish={name:'夏威夷快手米饭',source:{kb_id:record.kb_id,file_id:record.file_id,file_hash:record.file_hash},portion_quote:'总份数4人份'}
 const before=structuredClone(dish)
 const cover=recipeCover(dish)
 assert.equal(cover.image_url,record.image_url)
 assert.deepEqual(dish,before)
 for(const field of ['kb_id','file_id','file_hash'])assert.equal(recipeCover({...dish,source:{...dish.source,[field]:'other'}}),null)
 assert.equal(recipeCover({name:dish.name}),null)
 cover.image_source.publisher='modified'
 assert.equal(recipeCover(dish).image_source.publisher,'NHLBI')
 assert.equal(recipeCover({...dish,image_url:'https://example.org/saved.jpg'}).image_url,'https://example.org/saved.jpg')
})

test('client media projection comes from the backend reviewed catalog',()=>{
 const result=spawnSync(process.execPath,['scripts/sync-recipe-covers.mjs','--check'],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true})
 assert.equal(result.status,0,result.stderr)
 const owner=JSON.parse(readFileSync(new URL('../../agent/Yuxi-main/backend/package/yuxi/services/data/recipe_covers.json',import.meta.url),'utf8'))
 assert.deepEqual(recipeCovers,owner.covers)
})

test('public media uses the configured mini-program service or complete H5 origin',()=>{
 const image=recipeCovers[0].image_url
 assert.equal(publicImageUrl(image,{baseUrl:'https://app.example/',origin:'http://localhost:5173'}),'https://app.example'+image)
 assert.equal(publicImageUrl(image,{baseUrl:'',origin:'http://localhost:5173'}),'http://localhost:5173'+image)
 assert.equal(publicImageUrl('/static/food/family-meal.jpg'),'/static/food/family-meal.jpg')
 assert.equal(publicImageUrl('https://images.example/rice.jpg'),'https://images.example/rice.jpg')
})
