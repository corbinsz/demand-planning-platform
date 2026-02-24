import POGenerator from '../components/POGenerator'

export default function PurchaseOrders() {
  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Purchase Orders</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Auto-generated PO suggestions sorted by urgency. Select items and export a CSV to send to your supplier.
        </p>
      </div>
      <POGenerator />
    </div>
  )
}
