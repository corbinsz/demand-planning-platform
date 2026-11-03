import { useId, useState } from 'react'

/** Short label, with the reasoning one click away. */
export default function Explain({ text, children }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  return (
    <span className="explain">
      {children}
      <button
        type="button"
        className="explain-btn"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? 'Hide' : 'Why?'}
      </button>
      {open && <span id={panelId} className="explain-panel" role="note">{text}</span>}
    </span>
  )
}
