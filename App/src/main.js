import { createSSRApp } from 'vue'
import App from './App.vue'
import { installRouteGuards, guardInitialH5Route } from './services/navigation.js'
import AppNavBar from './components/AppNavBar.vue'
import AppIcon from './components/AppIcon.vue'

export function createApp() {
  // #ifdef H5
  guardInitialH5Route(window.location, window.history)
  // #endif
  installRouteGuards()
  const app = createSSRApp(App)
  app.component('AppNavBar', AppNavBar)
  app.component('AppIcon', AppIcon)
  return { app }
}

