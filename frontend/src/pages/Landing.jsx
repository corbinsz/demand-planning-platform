import { Link } from 'react-router-dom'
import { track } from '../analytics'

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-top">
        <div className="brand-mark">
          <span aria-hidden="true" style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #9869E3, #E82888)', display: 'inline-block',
          }} />
          Inventory Intel
        </div>
        <nav aria-label="Account">
          <Link to="/login" className="btn ghost">Sign in</Link>
        </nav>
      </header>
      <section className="hero">
        <p className="page-kicker">For Shopify brands on ShipHero</p>
        <h1>Know what to reorder before you stock out.</h1>
        <p>
          See what will run out, what to buy, and where cash is stuck in quiet stock.
          Built from your Shopify sales and your ShipHero warehouse — not a spreadsheet guess.
        </p>
        <div className="cta-row">
          <Link to="/today" className="btn primary" onClick={() => track('open_demo')}>
            See today’s decisions
          </Link>
          <Link to="/login" className="btn ghost">Create a workspace</Link>
        </div>
      </section>
      <section className="proofs" aria-label="Why this is hard to copy">
        <article className="proof">
          <h2>ShipHero is the stock number</h2>
          <p>Shopify and the warehouse disagree. We show both, and we buy against the warehouse.</p>
        </article>
        <article className="proof">
          <h2>The forecast has to earn it</h2>
          <p>Every SKU is checked against recent history. You see the range, not a single magic number.</p>
        </article>
        <article className="proof">
          <h2>A buy list, not a chart</h2>
          <p>The first screen is what to do today. Export it, or send a read-only brief to a partner.</p>
        </article>
      </section>
      <p style={{ marginTop: 28, fontSize: 14 }}>
        <Link to="/terms">Terms</Link>
        {' · '}
        <Link to="/privacy">Privacy</Link>
        {' · '}
        The sample brand is fictional and lives in Salt Lake City.
      </p>
    </div>
  )
}
