import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { piniaSessionPersistence } from '@/stores/persistence'
import App from './App.vue'
import router from './router'
import './assets/css/main.css'

const pinia = createPinia()
pinia.use(piniaSessionPersistence)

const app = createApp(App)

app.use(pinia)
app.use(router)

app.mount('#app')
