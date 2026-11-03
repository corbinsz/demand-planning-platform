import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { SessionProvider } from './session'
import { installMonitoring } from './monitoring'
import './index.css'

installMonitoring()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SessionProvider>
      <App />
    </SessionProvider>
  </React.StrictMode>
)
