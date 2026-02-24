export const thStyle = {
  textAlign: 'left',
  padding: '11px 14px',
  borderBottom: '2px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 600,
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  background: 'var(--bg-white)',
  position: 'sticky',
  top: 0,
  zIndex: 1,
}

export const tdStyle = {
  padding: '11px 14px',
  borderBottom: '1px solid var(--border-light)',
  color: 'var(--text-primary)',
  fontSize: '13px',
}

export const urgencyConfig = {
  critical: { bg: 'var(--danger-bg)', color: 'var(--danger)', border: 'var(--danger)' },
  high: { bg: 'var(--warning-bg)', color: 'var(--warning)', border: 'var(--warning)' },
  medium: { bg: 'var(--info-bg)', color: 'var(--info)', border: 'var(--info)' },
  low: { bg: 'var(--success-bg)', color: 'var(--success)', border: 'var(--success)' },
}
