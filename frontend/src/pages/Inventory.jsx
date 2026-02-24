import InventoryTable from '../components/InventoryTable'

export default function Inventory() {
  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Inventory</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Live stock levels reconciled across Shopify and ShipHero. Health badges flag stockouts and overstock before they cost you revenue.
        </p>
      </div>
      <InventoryTable />
    </div>
  )
}
