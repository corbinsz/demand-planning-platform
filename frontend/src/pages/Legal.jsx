import { Link } from 'react-router-dom'

export function Terms() {
  return (
    <article className="landing legal">
      <p className="page-kicker">Placeholder — replace before you charge a customer</p>
      <h1>Terms of use</h1>
      <p>
        This is not a finished legal agreement. The owner of Inventory Intel needs a lawyer to replace
        this page before selling the product. It is here so the product has a place for those terms.
      </p>
      <p>
        Until then: the sample workspace is fictional, forecasts are decision support and not a promise
        of sales, and you are responsible for purchase orders you place with suppliers.
      </p>
      <p><Link to="/privacy">Privacy</Link> · <Link to="/">Home</Link></p>
    </article>
  )
}

export function Privacy() {
  return (
    <article className="landing legal">
      <p className="page-kicker">Placeholder — replace before you charge a customer</p>
      <h1>Privacy</h1>
      <p>
        This is not a finished privacy policy. Replace it before a real brand connects Shopify or ShipHero.
      </p>
      <ul>
        <li>Store and warehouse tokens are encrypted in the database and are not shown again in the app.</li>
        <li>Each brand is a separate workspace. One brand’s orders are not readable by another.</li>
        <li>You can delete imported data, or the whole account, from Connections.</li>
        <li>The app does not load a third-party analytics or error script. Those stay off unless you configure them.</li>
        <li>The sample brand, Northline Athletics, is invented. It is not a customer.</li>
      </ul>
      <p>The product owner is in Utah. Support hours in the deploy guide use Mountain Time.</p>
      <p><Link to="/terms">Terms</Link> · <Link to="/">Home</Link></p>
    </article>
  )
}
