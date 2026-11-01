<script setup>
import { reactive } from 'vue'
import { onShow, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { accountSettings } from '../../services/account-settings.js'
import { sessionRevision } from '../../services/session.js'
import { newHealthRequestId } from '../../services/health-request-id.js'
import { createFeedbackDraft } from '../../services/product-feedback-draft.js'
const draft=createFeedbackDraft({client:accountSettings,newId:newHealthRequestId,context:sessionRevision,reactive})
const form=draft.state,own=sessionRevision()
let alive=true
onUnload(()=>{alive=false;draft.dispose()})
onShow(()=>{if(own!==sessionRevision()){draft.dispose();form.content='';form.images=[];form.error='账号已切换，请返回设置后重新进入'}})
function back(){if(!form.busy)uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/settings/index'})})}
function addImages(){
 if(form.busy||form.saved||form.images.length>=3)return
 uni.chooseImage({count:3-form.images.length,sizeType:['compressed'],sourceType:['album','camera'],
  success(result){
   if(!alive||own!==sessionRevision())return
   form.error=''
   for(let i=0;i<result.tempFilePaths.length&&form.images.length<3;i++){
    const size=result.tempFiles?.[i]?.size
    if(!Number.isFinite(size)||size>5*1024*1024){form.error='请选择不超过5MB的图片';continue}
    form.images.push({path:result.tempFilePaths[i],size})
   }
  },fail(error){if(alive&&!/cancel/i.test(error.errMsg||''))form.error='图片选择失败，请检查权限后重试'},
 })
}
function preview(path){uni.previewImage({current:path,urls:form.images.map(image=>image.path)})}
</script>
<template>
 <view class="screen product-feedback-screen">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回设置" :disabled="form.busy" @click="back">‹</button><text class="nav-title">反馈</text><text/></view></AppNavBar>
  <view v-if="form.saved" class="feedback-card success-card" role="status"><text class="success-mark">✓</text><text class="feedback-title">反馈已提交</text><text class="feedback-description">谢谢你的建议，我们会认真阅读。</text><button class="submit-feedback" @click="back">返回设置</button></view>
  <view v-else class="feedback-card">
   <text class="feedback-title">填写反馈</text>
   <text class="feedback-description">你的每个建议，都能帮我们做得更好。</text>
   <view class="feedback-input"><textarea v-model="form.content" maxlength="200" :disabled="form.busy" placeholder="请在这里写下对我们产品的反馈" placeholder-class="feedback-placeholder" aria-label="产品反馈内容" :adjust-position="true"/><text class="word-count">{{Array.from(form.content).length}} / 200</text></view>
   <view class="image-heading"><text>添加图片</text><text class="image-count">选填 · {{form.images.length}}/3</text></view>
   <view class="feedback-images"><view v-for="(image,index) in form.images" :key="image.path" class="feedback-image"><image :src="image.path" mode="aspectFill" @click="preview(image.path)"/><button class="remove-image" :aria-label="'移除第'+(index+1)+'张图片'" :disabled="form.busy" @click="form.images.splice(index,1)">×</button></view><button v-if="form.images.length<3" class="add-image" aria-label="添加反馈图片" :disabled="form.busy" @click="addImages"><text>＋</text></button></view>
   <text class="image-note">最多3张，每张不超过5MB</text>
   <text v-if="form.error" class="feedback-error" role="alert">{{form.error}}</text>
   <button class="submit-feedback" :disabled="form.busy||!form.content.trim()" :loading="form.busy" @click="draft.submit">{{form.busy?'正在提交…':'提交反馈'}}</button>
  </view>
 </view>
</template>
<style scoped>
.product-feedback-screen{min-height:100vh;background:var(--ui-canvas-gradient);color:var(--ui-text);padding:0 32rpx calc(env(safe-area-inset-bottom) + 30px)}
.feedback-card{margin-top:24px;padding:24px 20px;border-radius:24px;background:rgba(255,255,255,.86);border:1px solid rgba(255,255,255,.95);box-shadow:0 8px 30px rgba(116,109,151,.035)}.feedback-title{display:block;font-size:22px;font-weight:600;line-height:1.5}.feedback-description{display:block;margin-top:8px;color:var(--ui-muted);font-size:13px;line-height:1.7}.feedback-input{position:relative;margin-top:24px;padding:16px 14px 38px;background:rgba(248,248,251,.65);border:1px solid #e9e8ef;border-radius:15px}.feedback-input textarea{display:block;width:100%;height:180px;font-size:15px;line-height:1.8;box-sizing:border-box}.feedback-placeholder{color:#b4b1be}.word-count{position:absolute;right:14px;bottom:12px;color:#9995a6;font-size:12px}.image-heading{display:flex;justify-content:space-between;align-items:center;margin:28px 0 14px;font-size:16px}.image-count,.image-note{font-size:12px;color:#9995a6}.feedback-images{display:flex;gap:12px;flex-wrap:wrap}.feedback-image,.add-image{position:relative;width:84px;height:84px;border-radius:15px}.feedback-image>image{width:100%;height:100%;border-radius:15px}.add-image{display:flex;align-items:center;justify-content:center;margin:0;border:1px dashed #d7d4e2;background:#f5f4f9;color:#b7b2c6}.add-image text{font-size:36px;font-weight:300;line-height:1}.remove-image{position:absolute;top:-12px;right:-12px;width:44px;height:44px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:transparent;color:#514965;font-size:25px;text-shadow:0 0 4px #fff}.image-note{display:block;margin-top:14px;line-height:1.5}.feedback-error{display:block;margin-top:20px;font-size:13px;line-height:1.6;color:#a53632}.submit-feedback{display:flex;align-items:center;justify-content:center;width:100%;min-height:48px;margin-top:30px;padding:10px;border-radius:14px;background:linear-gradient(105deg,#b6a0f4,#9784ed);color:#fff;font-size:16px;font-weight:500;line-height:1.5}.submit-feedback[disabled]{opacity:.5;color:#fff;background:#b8aadf}.success-card{text-align:center;padding-top:36px}.success-mark{display:block;margin:0 auto 18px;font-size:30px;color:#9180d7}.icon-button{min-width:44px;min-height:44px}@media(max-width:350px){.feedback-card{padding:22px 16px}.feedback-image,.add-image{width:72px;height:72px}.feedback-images{gap:10px}}
</style>
