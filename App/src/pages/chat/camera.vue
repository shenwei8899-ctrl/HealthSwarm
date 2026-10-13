<script setup>
import { computed, getCurrentInstance, nextTick, ref } from 'vue'
import { onHide, onReady, onShow, onUnload } from '@dcloudio/uni-app'
import { scopedStorage, storageContext } from '../../services/storage.js'

const instance = getCurrentInstance()
const mounted = ref(false), ready = ref(false), busy = ref(false), error = ref('')
const device = ref('back'), flash = ref('off'), zoom = ref(1), maxZoom = ref(1), lastImage = ref(null)
const topPadding = ref(24)
let nativeCamera = false
// #ifdef MP-WEIXIN
nativeCamera = true
// #endif
const zoomChoices = computed(() => [1, 2, 3, 4].filter(value => value <= maxZoom.value))
const canTakePhoto = computed(() => !busy.value && (!nativeCamera || ready.value))
let context, disposed = false, returned = false, selectionVersion = 0
const pageScope = storageContext()
function current(version){return !disposed && !returned && version===selectionVersion && pageScope===storageContext()}
onShow(() => {
  if(pageScope!==storageContext()){close();return}
  lastImage.value=scopedStorage.getStorageSync('last-chat-image')||null
  mounted.value=true
})
onReady(() => {
  try {topPadding.value=(uni.getWindowInfo?uni.getWindowInfo():uni.getSystemInfoSync()).statusBarHeight||24} catch {}
  if(nativeCamera)context=uni.createCameraContext()
})
onHide(()=>{mounted.value=false;ready.value=false})
onUnload(()=>{disposed=true;selectionVersion++;mounted.value=false;context=null})
function cameraReady(event){
  if(disposed||!mounted.value)return
  if(nativeCamera&&!context)context=uni.createCameraContext()
  ready.value=true;error.value='';zoom.value=1
  maxZoom.value=typeof context?.setZoom==='function'?Math.max(1,Number(event.detail?.maxZoom)||1):1
}
function cameraError(){ready.value=false;error.value='相机无法打开，请检查权限，或从相册选择照片'}
function cameraStopped(){ready.value=false}
function close(){uni.navigateBack({fail:()=>uni.redirectTo({url:'/pages/chat/index'})})}
function finish(path,source,version){
  if(!current(version)||!path)return
  const proxy=instance?.proxy
  const channel=proxy?.getOpenerEventChannel?.()||proxy?.$scope?.getOpenerEventChannel?.()
  if(!channel?.emit){error.value='请从聊天输入框打开相机';return}
  returned=true
  channel.emit('photoSelected',{path,source})
  uni.navigateBack({fail(){error.value='照片已选好，请点击左上角返回聊天'}})
}
function choosePhoto(source='album'){
  if(busy.value||returned||disposed||pageScope!==storageContext())return
  const version=++selectionVersion;busy.value=true;error.value=''
  uni.chooseImage({count:1,sizeType:['compressed'],sourceType:[source],
    success(result){finish(result.tempFilePaths?.[0],source,version)},
    fail(result){if(current(version)&&!/cancel/i.test(result.errMsg||''))error.value='照片选择失败，请重试'},
    complete(){if(!disposed&&version===selectionVersion)busy.value=false},
  })
}
function takePhoto(){
  if(!canTakePhoto.value||returned||disposed||pageScope!==storageContext())return
  if(!nativeCamera){choosePhoto('camera');return}
  const version=++selectionVersion;busy.value=true
  context.takePhoto({quality:'normal',
    success(result){finish(result.tempImagePath,'camera',version)},
    fail(){if(current(version))error.value='拍照失败，请重试'},
    complete(){if(!disposed&&version===selectionVersion)busy.value=false},
  })
}
function toggleFlash(){if(!busy.value&&device.value==='back')flash.value=flash.value==='off'?'on':'off'}
async function switchCamera(){
  if(busy.value||!nativeCamera||!ready.value)return
  ready.value=false;zoom.value=1;maxZoom.value=1;flash.value='off';mounted.value=false
  device.value=device.value==='back'?'front':'back'
  await nextTick();if(!disposed)mounted.value=true
}
function setZoom(value){
  if(!ready.value||busy.value||value>maxZoom.value||!context?.setZoom)return
  context.setZoom({zoom:value,success(result){if(!disposed)zoom.value=result.zoom||value},fail(){uni.showToast({title:'当前设备暂不支持此倍率',icon:'none'})}})
}
function openCameraSettings(){uni.openSetting({success(){error.value='';mounted.value=false;nextTick(()=>{if(!disposed)mounted.value=true})}})}
</script>

<template>
  <view class="camera-screen" :style="{paddingTop:topPadding+'px'}">
    <view class="camera-header"><button class="close-camera" aria-label="关闭相机" @click="close"><view></view><view></view></button><text>AI 相机</text></view>
    <view class="camera-toolbar"><button class="flash-button" :class="{'flash-on':flash==='on'}" :disabled="busy||device==='front'||!nativeCamera" aria-label="切换闪光灯" @click="toggleFlash"><text class="flash-symbol">ϟ</text><view v-if="flash==='off'" class="flash-slash"></view></button></view>
    <view class="viewfinder">
      <!-- #ifdef MP-WEIXIN -->
      <camera v-if="mounted" class="live-camera" :device-position="device" :flash="flash" mode="normal" @initdone="cameraReady" @error="cameraError" @stop="cameraStopped" />
      <!-- #endif -->
      <!-- #ifndef MP-WEIXIN -->
      <view class="camera-placeholder"><text>请在微信小程序中使用实时相机</text><text>也可以从相册选择照片</text></view>
      <!-- #endif -->
      <cover-view class="frame-corner top-left"></cover-view><cover-view class="frame-corner top-right"></cover-view><cover-view class="frame-corner bottom-left"></cover-view><cover-view class="frame-corner bottom-right"></cover-view>
    </view>
    <view class="zoom-row"><button v-for="value in zoomChoices" :key="value" :class="{selected:zoom===value}" :disabled="busy||!ready" @click="setZoom(value)">{{value}}{{zoom===value?'x':''}}</button></view>
    <view class="camera-footer">
      <view v-if="error" class="camera-error"><text>{{error}}</text><button v-if="nativeCamera&&!ready" @click="openCameraSettings">相机权限设置</button></view>
      <view class="capture-controls">
        <button class="album-button" :disabled="busy" aria-label="从相册选择照片" @click="choosePhoto('album')"><image v-if="lastImage" :src="lastImage.localPath" mode="aspectFill" @error="lastImage=null"/><view v-else class="album-icon"><view></view><text>相册</text></view></button>
        <button class="shutter-button" :class="{busy}" :disabled="!canTakePhoto" aria-label="拍照" @click="takePhoto"><view></view></button>
        <button class="switch-button" :disabled="busy||!nativeCamera||!ready" aria-label="切换前后摄像头" @click="switchCamera"><text>⇄</text></button>
      </view>
    </view>
  </view>
</template>

<style scoped>
.camera-screen{height:100vh;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;background:#000;color:#fff;padding-bottom:env(safe-area-inset-bottom)}
.camera-screen button{margin:0;padding:0;line-height:1;background:transparent;color:inherit;border:0}.camera-screen button::after{border:0}.camera-screen button[disabled]{opacity:.35}
.camera-header{position:relative;display:flex;align-items:center;justify-content:center;min-height:96rpx;flex-shrink:0}.camera-header>text{font-size:36rpx;font-weight:600;letter-spacing:2rpx}
.close-camera{position:absolute;left:24rpx;top:8rpx;width:80rpx;height:80rpx}.close-camera view{position:absolute;left:20rpx;top:38rpx;width:40rpx;height:4rpx;border-radius:4rpx;background:#fff;transform:rotate(45deg)}.close-camera view:last-child{transform:rotate(-45deg)}
.camera-toolbar{height:66rpx;display:flex;justify-content:flex-end;padding:0 28rpx;flex-shrink:0}.flash-button{position:relative;width:76rpx;height:64rpx;display:flex;align-items:center;justify-content:center}.flash-symbol{font-size:62rpx;font-weight:600}.flash-slash{position:absolute;width:48rpx;height:4rpx;background:#fff;transform:rotate(45deg)}.flash-on{color:#ffd34f!important}
.viewfinder{position:relative;flex:1;min-height:180rpx;background:#161616;overflow:hidden}.live-camera{width:100%;height:100%}.camera-placeholder{height:100%;display:flex;flex-direction:column;gap:16rpx;align-items:center;justify-content:center;color:#909090;font-size:24rpx}
.frame-corner{position:absolute;width:86rpx;height:86rpx;border-color:#fff;border-style:solid;border-width:0;background:transparent;pointer-events:none}.top-left{top:16%;left:10%;border-top-width:3rpx;border-left-width:3rpx;border-top-left-radius:44rpx}.top-right{top:16%;right:10%;border-top-width:3rpx;border-right-width:3rpx;border-top-right-radius:44rpx}.bottom-left{bottom:16%;left:10%;border-bottom-width:3rpx;border-left-width:3rpx;border-bottom-left-radius:44rpx}.bottom-right{bottom:16%;right:10%;border-bottom-width:3rpx;border-right-width:3rpx;border-bottom-right-radius:44rpx}
.zoom-row{height:86rpx;display:flex;align-items:center;justify-content:center;gap:30rpx;background:#101010;flex-shrink:0}.zoom-row button{width:60rpx;height:60rpx;border-radius:50%;font-size:24rpx;font-weight:600}.zoom-row .selected{color:#ffd34f;background:#262626}
.camera-footer{padding:32rpx 44rpx 40rpx;flex-shrink:0}.capture-controls{display:flex;align-items:center;justify-content:space-between;gap:28rpx}.album-button,.switch-button{width:100rpx;height:100rpx;border-radius:22rpx!important;background:#1e1e1e!important;overflow:hidden;display:flex;align-items:center;justify-content:center}.album-button image{width:100%;height:100%}.album-icon{display:flex;flex-direction:column;gap:10rpx;align-items:center;font-size:20rpx}.album-icon>view{width:40rpx;height:32rpx;border:3rpx solid #fff;border-radius:6rpx}.switch-button text{font-size:66rpx;line-height:1}
.shutter-button{width:148rpx;height:148rpx;border:6rpx solid #fff!important;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}.shutter-button>view{width:122rpx;height:122rpx;border-radius:50%;background:#fff}.shutter-button.busy>view{opacity:.5}.camera-error{text-align:center;padding:0 0 24rpx;font-size:24rpx;line-height:1.6;color:#ddd}.camera-error>text{display:block}.camera-error button{padding:16rpx;color:#ffd34f;font-size:24rpx}
</style>
