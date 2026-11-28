import { createSSRApp } from 'vue'
import App from './App.vue'
import { referralEntry } from './services/referral-entry.js'
import { installRouteGuards, guardInitialH5Route } from './services/navigation.js'
import AppNavBar from './components/AppNavBar.vue'
import AppIcon from './components/AppIcon.vue'
import { registerApiAdapters } from './services/index.js'
// #ifdef MP-WEIXIN
import { uploadVoice } from './services/voice-upload.js'
// #endif

export function createApp() {
  // #ifdef MP-WEIXIN
  registerApiAdapters({ transcribeVoice: uploadVoice })
  // #endif
  // #ifdef H5
  const referral = window.location.hash.match(/[?&]ref=([A-Za-z0-9_-]{24})(?:&|$)/)
  if (referral) void referralEntry.capture({query:{ref:referral[1]}})
  guardInitialH5Route(window.location, window.history)
  // #endif
  const app = createSSRApp(App)
  // #ifdef MP-WEIXIN
  let firstPageReady
  const startup = new Promise(resolve => { firstPageReady = resolve })
  app.mixin({
    onReady() {
      if (this.$mpType === 'page') firstPageReady()
    },
  })
  installRouteGuards(startup)
  // #endif
  // #ifndef MP-WEIXIN
  installRouteGuards()
  // #endif
  app.component('AppNavBar', AppNavBar)
  app.component('AppIcon', AppIcon)
  return { app }
}

