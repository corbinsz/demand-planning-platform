import { useState, useEffect } from 'react'
import { getPromotions, createPromotion, deletePromotion } from '../services/api'
import { thStyle, tdStyle } from '../components/shared/tableStyles'

export default function Promotions() {
  const [promos, setPromos] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', start_date: '', end_date: '', discount_pct: 0, notes: '' })
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    getPromotions()
      .then(r => setPromos(r.data?.items || []))
      .catch(() => setPromos([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    setSaving(true)
    try {
      await createPromotion({
        ...form,
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
        discount_pct: parseFloat(form.discount_pct) || 0,
      })
      setShowForm(false)
      setForm({ name: '', start_date: '', end_date: '', discount_pct: 0, notes: '' })
      load()
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  const handleDelete = async (id) => {
    await deletePromotion(id)
    load()
  }

  const inputStyle = {
    width: '100%', padding: '8px 12px', borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border)', fontSize: '13px', outline: 'none',
    background: 'var(--bg-white)', color: 'var(--text-primary)',
  }

  const labelStyle = {
    fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase',
    letterSpacing: '0.5px', fontWeight: 600, marginBottom: '4px', display: 'block',
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Promotions</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Track promotional periods to understand their impact on sales velocity and forecasting accuracy.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            padding: '9px 20px', borderRadius: 'var(--radius-sm)', border: 'none',
            background: 'var(--accent)', color: '#fff', fontSize: '13px', fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {showForm ? 'Cancel' : '+ New Promotion'}
        </button>
      </div>

      {showForm && (
        <div style={{
          background: 'var(--bg-white)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: '24px', marginBottom: '20px',
          boxShadow: 'var(--shadow-sm)',
        }}>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', marginBottom: '14px' }}>
            <div style={{ flex: '2 1 200px' }}>
              <label style={labelStyle}>Name</label>
              <input style={inputStyle} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Resolution Sale" />
            </div>
            <div style={{ flex: '1 1 150px' }}>
              <label style={labelStyle}>Start Date</label>
              <input style={inputStyle} type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            </div>
            <div style={{ flex: '1 1 150px' }}>
              <label style={labelStyle}>End Date</label>
              <input style={inputStyle} type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
            </div>
            <div style={{ flex: '1 1 100px' }}>
              <label style={labelStyle}>Discount %</label>
              <input style={inputStyle} type="number" min="0" max="100" value={form.discount_pct} onChange={e => setForm({ ...form, discount_pct: e.target.value })} />
            </div>
          </div>
          <div style={{ marginBottom: '14px' }}>
            <label style={labelStyle}>Notes</label>
            <input style={inputStyle} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Optional notes..." />
          </div>
          <button
            onClick={handleCreate} disabled={saving || !form.name || !form.start_date || !form.end_date}
            style={{
              padding: '9px 24px', borderRadius: 'var(--radius-sm)', border: 'none',
              background: 'var(--accent)', color: '#fff', fontSize: '13px', fontWeight: 600,
              opacity: saving || !form.name || !form.start_date || !form.end_date ? 0.5 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Create Promotion'}
          </button>
        </div>
      )}

      <div style={{
        background: 'var(--bg-white)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
      }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
        ) : promos.length === 0 ? (
          <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>No Promotions</div>
            <div>Create your first promotion to start tracking velocity impact.</div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Start</th>
                <th style={thStyle}>End</th>
                <th style={thStyle}>Discount</th>
                <th style={thStyle}>Notes</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {promos.map((p, i) => (
                <tr key={p.id} style={{ background: i % 2 === 0 ? 'var(--bg-white)' : 'var(--bg-primary)' }}>
                  <td style={tdStyle}>
                    <span style={{
                      padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700,
                      background: p.is_active ? 'var(--success-bg)' : 'var(--border-light)',
                      color: p.is_active ? 'var(--success)' : 'var(--text-muted)',
                    }}>
                      {p.is_active ? 'ACTIVE' : 'ENDED'}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{p.name}</td>
                  <td style={{ ...tdStyle, fontSize: '12px' }}>{p.start_date ? new Date(p.start_date).toLocaleDateString() : '--'}</td>
                  <td style={{ ...tdStyle, fontSize: '12px' }}>{p.end_date ? new Date(p.end_date).toLocaleDateString() : '--'}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: 'var(--accent)' }}>{p.discount_pct}%</td>
                  <td style={{ ...tdStyle, color: 'var(--text-muted)', fontSize: '12px' }}>{p.notes || '--'}</td>
                  <td style={tdStyle}>
                    <button
                      onClick={() => handleDelete(p.id)}
                      style={{
                        padding: '4px 10px', borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border)', background: 'var(--bg-white)',
                        fontSize: '11px', color: 'var(--danger)', fontWeight: 600, cursor: 'pointer',
                      }}
                    >Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
