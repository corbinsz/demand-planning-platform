import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('ii_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Dashboard
export const getDashboard = () => api.get('/dashboard')
export const getSalesTrend = (days = 30) => api.get('/dashboard/sales-trend', { params: { days } })

// Inventory
export const getInventory = (params) => api.get('/inventory', { params })
export const getReconciledInventory = () => api.get('/inventory/reconciled')
export const getDiscrepancies = () => api.get('/inventory/discrepancies')
export const getWarehouses = () => api.get('/inventory/warehouses')
export const getSkuDetail = (sku) => api.get(`/inventory/sku/${encodeURIComponent(sku)}`)

// Forecasting
export const getForecasts = (params) => api.get('/forecasting', { params })
export const getSkuForecast = (sku) => api.get(`/forecasting/${encodeURIComponent(sku)}`)
export const getReorderAlerts = () => api.get('/forecasting/alerts')

// Purchase Orders
export const getPurchaseOrders = () => api.get('/purchase-orders')
export const getPOSuggestions = () => api.get('/purchase-orders/suggestions')
export const getReorderRules = (params) => api.get('/purchase-orders/rules', { params })
export const updateReorderRule = (sku, data) => api.put(`/purchase-orders/rules/${encodeURIComponent(sku)}`, data)

// Analytics / Reports
export const getABCClassification = (params) => api.get('/analytics/abc', { params })
export const getDeadStock = (params) => api.get('/analytics/dead-stock', { params })
export const getExcessStock = (params) => api.get('/analytics/excess-stock', { params })

// CSV Exports
export const exportABCCsv = (params) => api.get('/analytics/abc/export', { params, responseType: 'blob' })
export const exportDeadStockCsv = (params) => api.get('/analytics/dead-stock/export', { params, responseType: 'blob' })
export const exportExcessStockCsv = (params) => api.get('/analytics/excess-stock/export', { params, responseType: 'blob' })

// Promotions
export const getPromotions = (params) => api.get('/promotions', { params })
export const createPromotion = (data) => api.post('/promotions', data)
export const updatePromotion = (id, data) => api.put(`/promotions/${id}`, data)
export const deletePromotion = (id) => api.delete(`/promotions/${id}`)

// Sync
export const getSyncStatus = () => api.get('/sync/status')
export const testShopifyConnection = () => api.post('/sync/test-shopify')
export const testShipHeroConnection = () => api.post('/sync/test-shiphero')
export const triggerShopifySync = () => api.post('/sync/trigger/shopify')
export const triggerShipHeroSync = () => api.post('/sync/trigger/shiphero')

export const getSession = () => api.get('/auth/session')
export const login = (body) => api.post('/auth/login', body)
export const register = (body) => api.post('/auth/register', body)
export const getToday = () => api.get('/today')
export const getDigest = () => api.get('/digest')
export const getBrief = () => api.get('/reports/brief')
export const createShareLink = () => api.post('/reports/share')
export const getSharedBrief = (token) => api.get(`/reports/share/${token}`)
export const getIntegrationStatus = () => api.get('/integrations/status')
export const startShopifyConnect = (shop) => api.post('/integrations/shopify/start', { shop })
export const connectShipHero = (refreshToken) => api.post('/integrations/shiphero/connect', { refresh_token: refreshToken })
export const disconnectProvider = (provider) => api.delete(`/integrations/${provider}`)
export const deleteWorkspaceData = (confirm) => api.delete('/account/data', { data: { confirm } })

export default api
