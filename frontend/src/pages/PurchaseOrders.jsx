import POGenerator from '../components/POGenerator'

export default function PurchaseOrders() {
  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>What to buy</h1>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          The buy list, most urgent first. Quantities already subtract what ShipHero has on hand. Export a CSV for your supplier.
        </p>
      </div>
      <POGenerator />
    </div>
  )
}
