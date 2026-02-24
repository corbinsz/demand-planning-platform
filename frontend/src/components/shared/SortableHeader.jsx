import { thStyle } from './tableStyles'

export default function SortableHeader({ label, field, sortBy, sortDir, onSort, style }) {
  const active = sortBy === field
  return (
    <th
      style={{ ...thStyle, cursor: 'pointer', userSelect: 'none', ...style }}
      onClick={() => onSort(field, active && sortDir === 'asc' ? 'desc' : 'asc')}
    >
      {label}{' '}
      <span style={{ opacity: active ? 1 : 0.3, fontSize: '10px' }}>
        {active && sortDir === 'desc' ? '\u25BC' : '\u25B2'}
      </span>
    </th>
  )
}
