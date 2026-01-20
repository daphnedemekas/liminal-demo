import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/minimal.css'

try {
  const rootElement = document.getElementById('root')
  if (!rootElement) {
    throw new Error('Root element not found')
  }
  
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
} catch (error) {
  console.error('Failed to render app:', error)
  document.body.innerHTML = `<div style="padding: 20px; font-family: sans-serif;">
    <h1>Error loading app</h1>
    <p>${error instanceof Error ? error.message : String(error)}</p>
    <pre>${error instanceof Error ? error.stack : ''}</pre>
  </div>`
}
