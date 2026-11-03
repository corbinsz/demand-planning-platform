# How Inventory Intel works

This is the plain-English map of the product. The code lives in `backend/` (the API) and `frontend/` (the screens).

## What a person sees

The first page is a short pitch: know what to reorder before you stock out. The working app opens on **Today**, which answers three questions:

1. What will run out before a new shipment can arrive?
2. What should we buy, and how many?
3. How much cash is sitting in stock that barely sells?

Every important number has a **Why?** control. The longer explanation stays out of the way until someone asks.

Charts and tables still exist under Forecast, Stock, Quiet stock, and More numbers. They are for the second look, not the first.

## One brand, one workspace

A login owns one workspace. A workspace is one brand. Orders, stock, promotions, tokens, and share links all carry that workspace’s id. A request is allowed to see only the workspace in its sign-in token.

Demo mode is the exception used for a sales walkthrough. With `DEMO_MODE=true`, the fictional brand **Northline Athletics** (Salt Lake City) can be viewed without signing in. A second, real workspace still cannot be seen that way. Turn demo mode off before a paying client uses the server.

## Where the numbers come from

Shopify is the sales history. ShipHero is the warehouse. The app keeps both, then:

- Stock on hand is the **latest** ShipHero snapshot in each warehouse, added together. Older snapshots are not added on top.
- A discrepancy is Shopify **available** versus ShipHero **available**. Those are the same kind of number. The old screen compared Shopify available to ShipHero on-hand, which made healthy products look wrong.
- Dead stock and extra stock are valued at **cost**, the amount paid to the supplier, not the price on the site.

## How a forecast is chosen

For each SKU the app tries several methods on the last year of daily sales:

- Repeat last week (a simple baseline).
- Holt-Winters exponential smoothing, the method the app used to run for every SKU.
- Croston and TSB, which are meant for products that sell, then go quiet.
- Gradient boosting on lag features, both per SKU and once across the whole catalog.

It scores them by pretending it is a few weeks in the past, forecasting forward, and comparing that to what actually sold. The score is MASE. **1.0 means “no better than repeating last week.” Lower is better.**

One method is the catalog winner (best demand-weighted score). A single SKU keeps its own winner only when that winner beats the catalog method on that SKU by at least 5%. Otherwise it uses the catalog method, which jumps around less.

The 30-day and 90-day ranges are an 80% band from those past errors. The band always contains the point forecast, and the low end is never negative.

Promotions are not ignored. Days inside a past promotion are replaced with a normal same-weekday level before the model is fit, so a Black Friday spike does not become the new normal. Days inside a future promotion are lifted.

On the fictional Northline catalog the measured result is in `docs/benchmark-results.json`. Holt-Winters won for most of the volume (about 0.73 versus 1.02 for repeating last week). The selector still beat “always Holt-Winters” by a small amount (about 0.72), and it will switch a SKU when another method is clearly better. The point of the harness is that the choice is checked, not claimed.

## Connecting the stores

Shopify: the brand clicks Connect, approves a **read-only** list (products, orders, inventory, locations), and Shopify sends back a token. That token is encrypted before it is saved. The app never asks for write access.

ShipHero: the brand pastes a **refresh token**, not a password. The app trades it for a short-lived access token and stores both encrypted. The password is never accepted.

A token in an environment file is a single-brand fallback. It is ignored as soon as a second workspace exists, so one brand’s token cannot be applied to another.

## Sharing and deleting

A share link is a random address that shows the brief (stockout risk, what to buy, quiet stock) and a PDF. It expires in 14 days and can be opened without a login. It does not include tokens or raw orders.

The signed-in owner can delete imported data, or the whole account, by typing their email. That removes products, orders, stock, rules, promotions, share links, and stored tokens.

An audit log records sign-ins, connects, exports, share links, and the weekly note. It does not store tokens.

## The weekly note

Every Monday at **8:00am Mountain Time (Utah)** the server builds an email: what will stock out, what to buy, and how much cash is in quiet stock. It is sent only if a webhook or SMTP settings exist. Otherwise it stays as a preview on the Today screen. Nothing is emailed by accident.

## What the screens do not do

They do not place the purchase order at the supplier. They do not change Shopify or ShipHero stock. They tell a person what to do, and that person still decides.
