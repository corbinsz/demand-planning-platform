import { useState, useEffect, useMemo } from 'react'
import { getInventory, getWarehouses } from '../services/api'
import SkuDetailModal from './SkuDetailModal'
import { thStyle, tdStyle } from './shared/tableStyles'
import Pagination from './shared/Pagination'
import SortableHeader from './shared/SortableHeader'
import ProductCards from './ProductCards'
import InfoTooltip from './shared/InfoTooltip'

const HEALTH_INFO = {
  'Out of Stock': 'Available quantity is zero. You are losing sales right now. Place a PO immediately or check if stock is incoming.',
  'Low Stock': 'Below safety threshold (\u226410 units). At current sell rate, you could stock out within days. Check the Forecasting page for reorder suggestions.',
  'Excess': 'Over 500 units available. Capital is tied up in slow-moving stock. Consider running a promotion or pausing reorders.',
  'Healthy': 'Stock levels are within a healthy range. No immediate action needed.',
}

function HealthBadge({ available }) {
  let label, bg, color
  if (available <= 0) {
    label = 'Out of Stock'; bg = 'var(--danger-bg)'; color = 'var(--danger)'
  } else if (available <= 10) {
    label = 'Low Stock'; bg = 'var(--warning-bg)'; color = 'var(--warning)'
  } else if (available > 500) {
    label = 'Excess'; bg = 'var(--excess-bg)'; color = 'var(--excess)'
  } else {
    label = 'Healthy'; bg = 'var(--success-bg)'; color = 'var(--success)'
  }
  return (
    <InfoTooltip text={HEALTH_INFO[label]}>
      <span style={{
        padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
        background: bg, color: color, whiteSpace: 'nowrap', cursor: 'help',
      }}>{label}</span>
    </InfoTooltip>
  )
}

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function InventoryTable() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [search, setSearch] = useState('')
  const [warehouse, setWarehouse] = useState('')
  const [warehouses, setWarehouses] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedSku, setSelectedSku] = useState(null)
  const [sortBy, setSortBy] = useState('sku')
  const [sortDir, setSortDir] = useState('asc')
  const [groupVariants, setGroupVariants] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState(new Set())
  const [viewMode, setViewMode] = useState('table') // 'table' | 'cards'

  const debouncedSearch = useDebounce(search, 350)

  useEffect(() => {
    getWarehouses().then(r => setWarehouses(r.data?.warehouses || [])).catch(() => {})
  }, [])

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [debouncedSearch, warehouse])

  const handleSort = (field, dir) => { setSortBy(field); setSortDir(dir); setPage(1) }

  const toggleGroup = (key) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const groupedRows = useMemo(() => {
    if (!groupVariants) return null
    const groups = {}
    for (const item of items) {
      const key = item.parent_sku || item.sku
      if (!groups[key]) groups[key] = { parent: key, items: [], totalOnHand: 0, totalAvailable: 0, image: null }
      groups[key].items.push(item)
      groups[key].totalOnHand += item.quantity_on_hand
      groups[key].totalAvailable += item.quantity_available
      if (!groups[key].image && item.image_url) groups[key].image = item.image_url
    }
    return Object.values(groups).filter(g => g.items.length > 1)
  }, [items, groupVariants])

  const hasGroups = groupedRows && groupedRows.length > 0

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = { page, per_page: 50, sort_by: sortBy, sort_dir: sortDir }
    if (debouncedSearch) params.search = debouncedSearch
    if (warehouse) params.warehouse = warehouse

    getInventory(params)
      .then(r => {
        setItems(r.data?.items || [])
        setTotal(r.data?.total ?? 0)
        setPages(r.data?.pages ?? 1)
      })
      .catch(err => {
        setItems([])
        setError(err.response?.data?.detail || 'Failed to load inventory data. Check that the backend is running.')
      })
      .finally(() => setLoading(false))
  }, [page, debouncedSearch, warehouse, sortBy, sortDir])

  return (
    <div>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative' }}>
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth="2"
            style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}>
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            type="text"
            placeholder="Search SKU or title..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              background: 'var(--bg-white)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: '9px 12px 9px 36px',
              color: 'var(--text-primary)', fontSize: '13px', width: '280px',
              outline: 'none', transition: 'border-color 0.15s',
            }}
            onFocus={e => e.target.style.borderColor = 'var(--accent)'}
            onBlur={e => e.target.style.borderColor = 'var(--border)'}
          />
        </div>
        <select
          value={warehouse}
          onChange={e => setWarehouse(e.target.value)}
          style={{
            background: 'var(--bg-white)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '9px 14px',
            color: 'var(--text-primary)', fontSize: '13px', outline: 'none',
          }}
        >
          <option value="">All Warehouses</option>
          {warehouses.map(w => <option key={w} value={w}>{w}</option>)}
        </select>
        <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-white)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
          {['table', 'cards'].map(mode => (
            <button key={mode} onClick={() => setViewMode(mode)} style={{
              padding: '5px 12px', borderRadius: '5px', border: 'none', fontSize: '11px', fontWeight: 600,
              background: viewMode === mode ? 'var(--accent)' : 'transparent',
              color: viewMode === mode ? '#fff' : 'var(--text-secondary)', cursor: 'pointer',
              textTransform: 'capitalize',
            }}>{mode}</button>
          ))}
        </div>
        <button
          onClick={() => setGroupVariants(v => !v)}
          style={{
            padding: '7px 14px', borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)', fontSize: '12px', fontWeight: 600,
            background: groupVariants ? 'var(--accent)' : 'var(--bg-white)',
            color: groupVariants ? '#fff' : 'var(--text-secondary)',
            cursor: 'pointer', whiteSpace: 'nowrap',
          }}
        >
          Group Variants
        </button>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {total} items
        </span>
      </div>

      {viewMode === 'table' ? (
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
        }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, width: 44 }}></th>
                  <th style={thStyle}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Health <InfoTooltip text="Stock health status based on available quantity. Out of Stock = 0 units, Low Stock = 1-10, Healthy = 11-500, Excess = 500+. Hover each badge for details." />
                    </span>
                  </th>
                  <SortableHeader label="SKU" field="sku" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortableHeader label="On Hand" field="quantity_on_hand" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <th style={thStyle}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Allocated <InfoTooltip text="Units reserved for open orders that haven't shipped yet. These are spoken for — they reduce your available inventory even though they're still in the warehouse." />
                    </span>
                  </th>
                  <SortableHeader label="Available" field="quantity_available" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <th style={thStyle}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Cost <InfoTooltip text="Your cost per unit from the supplier. Used to calculate inventory value, gross margin, and ROI on stock." />
                    </span>
                  </th>
                  <SortableHeader label="Warehouse" field="warehouse" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <th style={thStyle}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Source <InfoTooltip text="Which platform reported this data. ShipHero = warehouse management (source of truth for stock). Shopify = storefront (source of truth for orders)." />
                    </span>
                  </th>
                  <SortableHeader label="Updated" field="recorded_at" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={11} style={{ ...tdStyle, textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>Loading...</td></tr>
                ) : error ? (
                  <tr><td colSpan={11} style={{ ...tdStyle, textAlign: 'center', padding: '40px' }}>
                    <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: '6px' }}>Error loading data</div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{error}</div>
                  </td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={11} style={{ ...tdStyle, textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>
                    {debouncedSearch ? `No results for "${debouncedSearch}"` : 'No inventory data yet. Connect your Shopify and ShipHero accounts to get started.'}
                  </td></tr>
                ) : items.map((item, i) => {
                  const groupKey = item.parent_sku || item.sku
                  const isGroupParent = hasGroups && groupedRows.some(g => g.parent === groupKey && g.items[0] === item)
                  const isGroupChild = hasGroups && item.parent_sku && groupedRows.some(g => g.parent === item.parent_sku && g.items[0] !== item)
                  const isExpanded = expandedGroups.has(groupKey)

                  if (isGroupChild && !expandedGroups.has(item.parent_sku)) return null

                  return (
                    <tr key={`${item.sku}-${item.warehouse || ''}-${i}`}
                      style={{
                        background: isGroupChild ? 'var(--accent-light)' : i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)',
                        cursor: 'pointer',
                      }}
                      onClick={() => isGroupParent ? toggleGroup(groupKey) : setSelectedSku(item.sku)}
                      onMouseEnter={e => { if (!isGroupChild && i % 2 === 0) e.currentTarget.style.background = 'var(--bg-primary)' }}
                      onMouseLeave={e => { if (!isGroupChild && i % 2 === 0) e.currentTarget.style.background = 'var(--bg-white)' }}
                    >
                      <td style={{ ...tdStyle, width: 44, padding: '6px 8px' }}>
                        {isGroupParent ? (
                          <span style={{ fontSize: '14px', color: 'var(--text-muted)', display: 'inline-block', width: 32, textAlign: 'center' }}>
                            {isExpanded ? '\u25BC' : '\u25B6'}
                          </span>
                        ) : item.image_url ? (
                          <img src={item.image_url} alt="" style={{ width: 32, height: 32, borderRadius: 6, objectFit: 'cover', marginLeft: isGroupChild ? 8 : 0 }} />
                        ) : (
                          <div style={{ width: 32, height: 32, borderRadius: 6, background: 'var(--border-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: isGroupChild ? 8 : 0 }}>
                            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--text-muted)" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                          </div>
                        )}
                      </td>
                      <td style={tdStyle}><HealthBadge available={item.quantity_available} /></td>
                      <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 600, color: 'var(--accent)' }}>
                        {isGroupChild && <span style={{ color: 'var(--text-muted)', marginRight: 4 }}>└</span>}
                        {item.sku}
                        {isGroupParent && (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 400, marginLeft: 6 }}>
                            ({groupedRows.find(g => g.parent === groupKey)?.items.length} variants)
                          </span>
                        )}
                      </td>
                      <td style={tdStyle}>{item.title}</td>
                      <td style={{ ...tdStyle, fontWeight: 500 }}>{item.quantity_on_hand}</td>
                      <td style={tdStyle}>{item.quantity_allocated}</td>
                      <td style={{ ...tdStyle, fontWeight: 600, color: item.quantity_available <= 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
                        {item.quantity_available}
                      </td>
                      <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>
                        {item.cost_price != null ? `$${item.cost_price.toFixed(2)}` : '--'}
                      </td>
                      <td style={tdStyle}>{item.warehouse || '--'}</td>
                      <td style={tdStyle}>
                        <span style={{
                          padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                          background: item.source === 'shiphero' ? 'var(--accent-light)' : 'var(--success-bg)',
                          color: item.source === 'shiphero' ? 'var(--accent)' : 'var(--success)',
                        }}>
                          {item.source}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, fontSize: '12px', color: 'var(--text-muted)' }}>
                        {item.recorded_at ? new Date(item.recorded_at).toLocaleDateString() : '--'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        loading ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>Loading...</div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: '6px' }}>Error loading data</div>
            <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{error}</div>
          </div>
        ) : items.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>
            {debouncedSearch ? `No results for "${debouncedSearch}"` : 'No inventory data yet. Connect your Shopify and ShipHero accounts to get started.'}
          </div>
        ) : (
          <ProductCards items={items} onSelectSku={setSelectedSku} />
        )
      )}

      <Pagination page={page} pages={pages} onPageChange={setPage} />

      {selectedSku && <SkuDetailModal sku={selectedSku} onClose={() => setSelectedSku(null)} />}
    </div>
  )
}
