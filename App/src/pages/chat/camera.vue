<script setup>
import { computed, getCurrentInstance, nextTick, ref } from 'vue'
import { onHide, onReady, onShow, onUnload } from '@dcloudio/uni-app'
import { scopedStorage, storageContext } from '../../services/storage.js'

const instance = getCurrentInstance()
const mounted = ref(false), ready = ref(false), busy = ref(false), error = ref('')
const device = ref('back'), flash = ref('off'), zoom = ref(1), maxZoom = ref(1), lastImage = ref(null)
const topPadding = ref(24)
const cameraIcons = {
  close: '/static/chat/camera-close.svg',
  flashOn: '/static/chat/camera-flash.svg',
  flashOff: '/static/chat/camera-flash-off.svg',
  album: '/static/chat/camera-album.svg',
  flip: '/static/chat/camera-flip.svg',
}
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
    <view class="camera-header">
      <button class="tool-button close-camera" aria-label="关闭相机" hover-class="tool-pressed" @click="close">
        <image class="camera-icon" :src="cameraIcons.close" mode="aspectFit" />
      </button>
      <text>AI 相机</text>
    </view>
    <view class="camera-toolbar">
      <button class="tool-button flash-button" :class="{'flash-on':flash==='on'}" :disabled="busy||device==='front'||!nativeCamera" :aria-label="flash==='on'?'关闭闪光灯':'开启闪光灯'" hover-class="tool-pressed" @click="toggleFlash">
        <image class="camera-icon" :src="flash==='on'?cameraIcons.flashOn:cameraIcons.flashOff" mode="aspectFit" />
      </button>
    </view>
    <view class="viewfinder">
      <!-- #ifdef MP-WEIXIN -->
      <camera v-if="mounted" class="live-camera" :device-position="device" :flash="flash" mode="normal" @initdone="cameraReady" @error="cameraError" @stop="cameraStopped" />
      <!-- #endif -->
      <!-- #ifndef MP-WEIXIN -->
      <view class="camera-placeholder"><text>请在微信小程序中使用实时相机</text><text>也可以从相册选择照片</text></view>
      <!-- #endif -->
      <cover-view class="frame-corner top-left"></cover-view>
      <cover-view class="frame-corner top-right"></cover-view>
      <cover-view class="frame-corner bottom-left"></cover-view>
      <cover-view class="frame-corner bottom-right"></cover-view>
    </view>
    <view class="zoom-row">
      <view class="zoom-pill">
        <button v-for="value in zoomChoices" :key="value" class="zoom-button" :class="{selected:zoom===value}" :disabled="busy||!ready" :aria-label="value+'倍变焦'" @click="setZoom(value)">
          <text>{{value}}{{zoom===value?'×':''}}</text>
        </button>
      </view>
    </view>
    <view class="camera-footer">
      <view v-if="error" class="camera-error"><text>{{error}}</text><button v-if="nativeCamera&&!ready" @click="openCameraSettings">相机权限设置</button></view>
      <view class="capture-controls">
        <view class="capture-side">
          <button class="tool-button album-button" :disabled="busy" aria-label="从相册选择照片" hover-class="tool-pressed" @click="choosePhoto('album')">
            <image v-if="lastImage" class="album-preview" :src="lastImage.localPath" mode="aspectFill" @error="lastImage=null" />
            <image v-else class="camera-icon" :src="cameraIcons.album" mode="aspectFit" />
          </button>
          <text class="control-label" aria-hidden="true">相册</text>
        </view>
        <button class="shutter-button" :class="{busy}" :disabled="!canTakePhoto" aria-label="拍照" hover-class="shutter-pressed" @click="takePhoto">
          <view class="shutter-disc"></view>
        </button>
        <view class="capture-side">
          <button class="tool-button switch-button" :disabled="busy||!nativeCamera||!ready" aria-label="切换前后摄像头" hover-class="tool-pressed" @click="switchCamera">
            <image class="camera-icon" :src="cameraIcons.flip" mode="aspectFit" />
          </button>
          <text class="control-label" aria-hidden="true">翻转</text>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.camera-screen{height:100vh;box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;background:#000;color:#fff;padding-bottom:env(safe-area-inset-bottom)}
.camera-screen button{box-sizing:border-box;margin:0;padding:0;line-height:1;background:transparent;color:inherit;border:0}
.camera-screen button::after{border:0}
.camera-screen button[disabled]{opacity:.4}
.camera-header{position:relative;display:flex;align-items:center;justify-content:center;min-height:96rpx;flex-shrink:0}
.camera-header>text{font-size:34rpx;font-weight:600;letter-spacing:1rpx}
.camera-screen .tool-button{
  display:flex;flex:none;align-items:center;justify-content:center;
  width:88rpx;height:88rpx;min-width:44px;min-height:44px;border-radius:50%;
  border:1px solid rgba(255,255,255,.13);background:#202021;
}
.camera-screen .tool-pressed{background:#353537}
.camera-icon{display:block;width:42rpx;height:42rpx;flex:none}
.camera-screen .close-camera{position:absolute;left:24rpx;top:50%;transform:translateY(-50%);border-color:transparent;background:transparent}
.close-camera .camera-icon{width:46rpx;height:46rpx}
.camera-screen .close-camera.tool-pressed{background:#252526}
.camera-toolbar{display:flex;justify-content:flex-end;padding:0 26rpx 12rpx;flex-shrink:0}
.camera-screen .flash-on{background:#2f2617;border-color:rgba(249,210,119,.3)}
.viewfinder{position:relative;flex:1;min-height:180rpx;background:#161616;overflow:hidden}
.live-camera{width:100%;height:100%}
.camera-placeholder{height:100%;display:flex;flex-direction:column;gap:16rpx;align-items:center;justify-content:center;color:#909090;font-size:24rpx}
.frame-corner{
  position:absolute;width:58rpx;height:58rpx;border:0 solid rgba(255,255,255,.82);
  background:transparent;pointer-events:none;
}
.top-left{top:16%;left:10%;border-top-width:3rpx;border-left-width:3rpx;border-top-left-radius:23rpx}
.top-right{top:16%;right:10%;border-top-width:3rpx;border-right-width:3rpx;border-top-right-radius:23rpx}
.bottom-left{bottom:16%;left:10%;border-bottom-width:3rpx;border-left-width:3rpx;border-bottom-left-radius:23rpx}
.bottom-right{bottom:16%;right:10%;border-bottom-width:3rpx;border-right-width:3rpx;border-bottom-right-radius:23rpx}
.zoom-row{display:flex;align-items:center;justify-content:center;flex:none;padding:14rpx 0 0}
.zoom-pill{display:flex;align-items:center;gap:4rpx;padding:4rpx;border-radius:999px;border:1px solid #303031;background:#171718}
.camera-screen .zoom-button{
  display:flex;align-items:center;justify-content:center;
  min-width:62rpx;height:54rpx;padding:0 12rpx;border-radius:999px;
  font-size:24rpx;line-height:1;font-weight:600;color:#e8e8e5;
}
.camera-screen .zoom-button.selected{color:#f9d277;background:#302819}
.camera-footer{padding:24rpx 54rpx 46rpx;flex-shrink:0}
.capture-controls{display:flex;align-items:center;justify-content:space-between;gap:20rpx}
.capture-side{position:relative;display:flex;justify-content:center;width:104rpx;flex:none}
.control-label{position:absolute;top:100%;margin-top:9rpx;font-size:22rpx;line-height:1;color:#c1c1bd;white-space:nowrap}
.album-button{overflow:hidden}
.album-preview{display:block;width:100%;height:100%}
.camera-screen .shutter-button{
  width:136rpx;height:136rpx;border:4rpx solid #f7f7f5;border-radius:50%;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
.shutter-disc{width:112rpx;height:112rpx;border-radius:50%;background:#f7f7f5;transition:transform .12s ease}
.shutter-pressed .shutter-disc{transform:scale(.93)}
.shutter-button.busy .shutter-disc{opacity:.65}
.camera-error{text-align:center;padding:0 0 24rpx;font-size:24rpx;line-height:1.6;color:#ddd}
.camera-error>text{display:block}
.camera-screen .camera-error button{padding:16rpx;color:#f9d277;font-size:24rpx}
</style>
