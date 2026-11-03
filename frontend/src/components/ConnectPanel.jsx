import { useEffect, useState } from 'react'
import {
  connectShipHero, deleteWorkspaceData, disconnectProvider, getIntegrationStatus, startShopifyConnect,
} from '../services/api'

export default function ConnectPanel() {
  const [status, setStatus] = useState(null)
  const [shop, setShop] = useState('')
  const [refreshToken, setRefreshToken] = useState('')
  const [message, setMessage] = useState('')

  const load = () => getIntegrationStatus().then((response) => setStatus(response.data)).catch(() => setStatus(null))
  useEffect(() => { load() }, [])

  const startShopify = async (event) => {
    event.preventDefault()
    setMessage('')
    try {
      const response = await startShopifyConnect(shop)
      window.location.assign(response.data.authorize_url)
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Shopify connect is not available on this server yet.')
    }
  }

  const saveShipHero = async (event) => {
    event.preventDefault()
    setMessage('')
    try {
      await connectShipHero(refreshToken)
      setRefreshToken('')
      setMessage('ShipHero is connected. The refresh token is stored encrypted and is not shown again.')
      load()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'ShipHero didn’t accept that refresh token.')
    }
  }

  return (
    <section className="decision-card" style={{ marginBottom: 20 }} aria-labelledby="connect-heading">
      <h2 id="connect-heading" style={{ fontSize: 18 }}>Connect a brand</h2>
      <p>
        Shopify uses a read-only approval screen. ShipHero uses a refresh token, not your password.
        Pasting tokens into a file is the old fallback and is documented for a single-brand server.
      </p>
      <form className="form" onSubmit={startShopify} style={{ marginTop: 12 }}>
        <label htmlFor="shop">Shopify store domain</label>
        <input id="shop" value={shop} onChange={(e) => setShop(e.target.value)} placeholder="your-store.myshopify.com" />
        <button className="btn primary" type="submit">Connect Shopify</button>
        <p>{status?.shopify?.connected ? `Connected to ${status.shopify.shop_domain}. Scopes: ${status.shopify.scopes}` : 'Shopify is not connected.'}</p>
      </form>
      <form className="form" onSubmit={saveShipHero} style={{ marginTop: 16 }}>
        <label htmlFor="refresh">ShipHero refresh token</label>
        <input id="refresh" type="password" autoComplete="off" value={refreshToken} onChange={(e) => setRefreshToken(e.target.value)} />
        <button className="btn ghost" type="submit">Connect ShipHero</button>
        <p>{status?.shiphero?.connected ? 'ShipHero is connected.' : 'ShipHero is not connected.'}</p>
      </form>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button type="button" className="btn ghost" onClick={() => disconnectProvider('shopify').then(load)}>Disconnect Shopify</button>
        <button type="button" className="btn ghost" onClick={() => disconnectProvider('shiphero').then(load)}>Disconnect ShipHero</button>
      </div>
      {message && <p role="status">{message}</p>}
      <p style={{ marginTop: 8, fontSize: 14 }}>
        Shopify scopes requested: read products, orders, inventory, and locations. No write access.
      </p>
    </section>
  )
}

export function DangerZone() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  return (
    <section className="decision-card" style={{ marginTop: 20 }} aria-labelledby="delete-heading">
      <h2 id="delete-heading" style={{ fontSize: 18 }}>Delete this brand’s data</h2>
      <p>This removes orders, stock, forecasts, and stored tokens for the signed-in workspace. It asks you to type your email so it is hard to do by accident.</p>
      <form className="form" onSubmit={async (event) => {
        event.preventDefault()
        try {
          await deleteWorkspaceData(email)
          setMessage('Imported data was deleted.')
        } catch (err) {
          setMessage(err.response?.data?.detail || 'Sign in with the account that owns this workspace, then try again.')
        }
      }}>
        <label htmlFor="confirm-email">Account email</label>
        <input id="confirm-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <button className="btn ghost" type="submit">Delete imported data</button>
      </form>
      {message && <p role="status">{message}</p>}
    </section>
  )
}
