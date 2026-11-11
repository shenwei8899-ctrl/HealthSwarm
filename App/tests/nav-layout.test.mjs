import test from 'node:test'
import assert from 'node:assert/strict'
import {standardNavGeometry} from '../src/services/nav-layout.js'

for(const viewportWidth of [320,375,390,430]){
  for(const inset of [12,16,20,28]){
    for(const rightWidth of [0,44,88]){
      test(`screen center and capsule clearance: ${viewportWidth}/${inset}/${rightWidth}`,()=>{
        const row={left:inset,right:viewportWidth-inset,width:viewportWidth-2*inset}
        const capsuleLeft=viewportWidth-97
        const g=standardNavGeometry({viewportWidth,row,leftWidth:44,rightWidth,capsuleLeft,title:'AI 记住的事'})
        assert.equal(row.left+g.center,viewportWidth/2)
        assert.ok(g.width>0)
        assert.ok(g.center-g.width/2>=44+8)
        assert.ok(row.left+g.center+g.width/2<=capsuleLeft-16-(g.actionsBelow?0:rightWidth))
        if(rightWidth&&!g.actionsBelow)assert.ok(row.right-g.rightInset<=capsuleLeft-8)
      })
    }
  }
}
test('actions move below only when needed and rejoin after their width shrinks',()=>{
  const base={viewportWidth:375,row:{left:16,right:359,width:343},leftWidth:44,capsuleLeft:278,title:'计划'}
  const wide=standardNavGeometry({...base,rightWidth:88})
  const narrow=standardNavGeometry({...base,rightWidth:20})
  assert.equal(wide.actionsBelow,true)
  assert.equal(narrow.actionsBelow,false)
  assert.equal(wide.center,narrow.center)
})
test('asymmetric page padding and desktop H5 still center on the viewport',()=>{
  for(const [viewportWidth,row] of [[390,{left:12,right:360,width:348}],[1024,{left:288,right:736,width:448}]]){
    const g=standardNavGeometry({viewportWidth,row,leftWidth:44,rightWidth:44,title:'饮食记录'})
    assert.equal(row.left+g.center,viewportWidth/2)
    assert.equal(g.rightInset,0)
  }
})
test('long titles stay within safe bounds and empty or no-button states remain valid',()=>{
  for(const title of ['', '实测指标与修改历史'.repeat(20)]){
    const g=standardNavGeometry({viewportWidth:320,row:{left:16,right:304,width:288},capsuleLeft:223,title})
    assert.equal(g.center,144)
    assert.equal(g.actionsBelow,false)
    assert.ok(g.width>=0&&g.width<=288)
  }
})
