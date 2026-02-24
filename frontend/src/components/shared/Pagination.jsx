export default function Pagination({ page, pages, onPageChange }) {
  if (pages <= 1) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px', alignItems: 'center' }}>
      <button
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        style={{
          padding: '7px 16px', borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)', background: 'var(--bg-white)',
          color: 'var(--text-primary)', fontSize: '13px', fontWeight: 500,
          opacity: page <= 1 ? 0.4 : 1, cursor: page <= 1 ? 'default' : 'pointer',
        }}
      >Previous</button>
      <span style={{ fontSize: '13px', color: 'var(--text-secondary)', padding: '0 8px' }}>
        {page} / {pages}
      </span>
      <button
        disabled={page >= pages}
        onClick={() => onPageChange(page + 1)}
        style={{
          padding: '7px 16px', borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)', background: 'var(--bg-white)',
          color: 'var(--text-primary)', fontSize: '13px', fontWeight: 500,
          opacity: page >= pages ? 0.4 : 1, cursor: page >= pages ? 'default' : 'pointer',
        }}
      >Next</button>
    </div>
  )
}
