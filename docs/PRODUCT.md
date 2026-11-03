# Why a Shopify brand would pay for this

A brand already has Shopify and ShipHero. They do not have a calm answer to “what do we buy on Monday?” Someone exports two spreadsheets, guesses a cover target, and finds out a size is gone when the ads are still running. That miss is the thing they will pay to avoid.

Inventory Intel is that Monday answer. The first screen is not a chart. It is the stockouts that will happen inside supplier lead time, the units to buy, and the cash stuck in quiet stock, in sentences.

## What is hard to copy

A generic “AI forecast” demo is easy to fake. Three things here are not:

**ShipHero is the stock number, and it is reconciled.** Shopify’s available count and the warehouse’s available count are stored separately and compared directly. The buy math uses the warehouse total across every location, using only the latest snapshot per warehouse. A tool that only reads Shopify will tell you to reorder product that is sitting in Salt Lake City, or will miss a warehouse entirely. Getting this wrong is how brands overbuy.

**The forecast has to beat a dumb baseline, in public.** Every SKU is scored by replaying recent history (a rolling-origin backtest). The score is MASE, where 1.0 means “no better than repeating last week.” The screen shows which method won and an 80% range from the actual misses. On the fictional Northline catalog, Holt-Winters is the catalog winner (demand-weighted MASE about 0.73 versus 1.02 for repeating last week). Letting each SKU switch when another method is clearly better moves that to about 0.72. The gain is small on this smooth catalog, and that is the point: the product will not pretend a worse method is smarter. Croston and TSB are in the race for bursty sizes and win only when the replay says so. A competitor who shows one confident number with no replay is easier to impress and easier to disprove.

**The output is a purchase.** Suggested quantity covers about eight weeks of the chosen forecast, minus what ShipHero has, and a supplier minimum applies only when an order is actually needed. The old version could ratchet that minimum upward every night. The buy list sorts by urgency, exports to CSV, and the same three lists become a PDF or a read-only link a founder can forward. A forecast that never becomes a buy list does not change the purchase order.

## Who it is for first

One brand, one hosted copy, a fixed price for the dashboard. The workspace, encrypted tokens, and deletion path are the groundwork for more than one brand later. They are not a finished multi-tenant billing system.

## What we do not claim

The sample brand is invented. The model does not promise next month’s sales. It says what was least wrong recently, and how wide the miss has been. A person still sends the purchase order.
