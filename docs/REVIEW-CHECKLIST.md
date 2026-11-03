# Review checklist

You do not need Docker.

**Hosted:** [Deploy the demo to Render](https://render.com/deploy?repo=https://github.com/corbinsz/demand-planning-platform). Sign in with GitHub, pick this branch if it asks, and open the `.onrender.com` URL. The exact clicks are in `docs/PREVIEW.md`. This machine has no Render login, so the URL is created when you click, not before.

**On a laptop, no Docker:** `./scripts/demo.sh`, then http://127.0.0.1:5173/ .

Either way you are looking at the fictional Northline Athletics brand in Salt Lake City. It does not call Shopify or ShipHero.

Plan on about ten minutes. The clock in the product copy is Mountain Time (Utah).

## Click through

1. **Landing.** In one glance you should get “know what to reorder before you stock out,” plus three reasons (warehouse stock, a checked forecast, a buy list). Open **See today’s decisions**.
2. **Today.** Read the sentence at the top. Confirm three columns: stockout risk, what to buy, cash in quiet stock. Open **Why?** on each heading. The explanation should be a sentence, not a formula.
3. **Alerts.** At least one alert should be a full sentence (“Stockout in N days” or an overstock note). Click **Preview the Monday email**. It should read like a note you could forward, and it should say it is sample data.
4. **What to buy.** The list should be most urgent first, with a quantity. The page should say the quantity already subtracts warehouse stock.
5. **Forecast.** The intro should say the method was checked against recent history. A row should show a model name and a 30-day range (low–high), not only one number.
6. **Stock.** Search for a SKU. Open it. On-hand should mention both Salt Lake City and Las Vegas when both have units, not just one building.
7. **Quiet stock.** Dead stock values should be described as cost, not retail. Export a CSV if you want to see the file download.
8. **More numbers.** This is the older dashboard (orders, revenue, a chart). It should load without an error banner.
9. **Promotions.** The list should include a resolution sale and a future launch. Try to save one that ends before it starts. The form should refuse it.
10. **Connections.** You should see Connect Shopify and a ShipHero refresh-token field, and a note that the scopes are read-only. Connecting will not succeed in the demo until app credentials exist. That is expected. The danger zone at the bottom asks you to type an email before deleting data. Do not delete the sample unless you are ready to re-run `./scripts/demo.sh`.
11. **Share.** From the API or the brief, create a share link (`POST /api/reports/share` while the demo is open) and open `/share/<token>`. It should show the three lists with no sidebar full of buttons. The PDF link should download a PDF.
12. **Sign in.** `demo@northline.example` / `northline-demo`. After sign-in you should land on Today for Northline, not an empty brand.
13. **Legal.** `/terms` and `/privacy` should say clearly that they are placeholders.
14. **Keyboard.** Tab from the top of Today. You should see a “Skip to content” link and a visible focus ring. The menu button appears when the window is narrow.

## How to request changes

Reply on the pull request with the screen name and what felt wrong, in plain language. A useful note looks like: “Today, the buy column doesn’t say the supplier lead time.” You do not need to name a file.

If something is broken rather than unclear, say what you clicked and what you expected to happen. Screenshots help. The agent will treat that comment as the next change list.

Please do not paste a live Shopify or ShipHero token into the pull request.
