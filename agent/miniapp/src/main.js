import { createSSRApp } from 'vue'
import App from './App.vue'
import AppNavBar from '@prototype/components/AppNavBar.vue'
import AppIcon from '@prototype/components/AppIcon.vue'

export function createApp() {
  const app = createSSRApp(App)
  app.component('AppNavBar', AppNavBar)
  app.component('AppIcon', AppIcon)
  return { app }
}
