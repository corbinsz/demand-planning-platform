import InventoryTable from '../components/InventoryTable'

export default function Inventory() {
  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: 700, fontFamily: 'Poppins, sans-serif' }}>Inventory</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Latest snapshot for each warehouse. The demo store count sits next to the demo warehouse count. Health badges flag stockouts and overstock.
        </p>
      </div>
      <InventoryTable />
    </div>
  )
}
