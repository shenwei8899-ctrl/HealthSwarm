import { createSSRApp } from 'vue'
import App from './App.vue'
import { installRouteGuards, guardInitialH5Route } from './services/navigation.js'
import AppNavBar from './components/AppNavBar.vue'
import AppIcon from './components/AppIcon.vue'
import { registerApiAdapters } from './services/index.js'
// #ifdef MP-WEIXIN
import { transcribeLocalVoice } from './services/voice-local.js'
// #endif

export function createApp() {
  // #ifdef MP-WEIXIN
  registerApiAdapters({ transcribeVoice: transcribeLocalVoice })
  // #endif
  // #ifdef H5
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

