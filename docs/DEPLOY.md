# Deploy one client, cheaply

This is for hosting **one brand** on a small server. The owner of this product is in **Utah**. Schedules in the app use Mountain Time (Utah): the weekly email is Monday at 8:00am. That is 15:00 UTC while Utah is on standard time. It is not a Colorado office and not a Denver data-center requirement. Put the server wherever is cheap. US West or a small VM in Salt Lake City both fine.

Do this before a real client:

1. Set `DEMO_MODE=false` and `AUTO_SEED=false`.
2. Set `SECRET_KEY` to a long random string. The app refuses to boot in non-demo mode if the secret is still a known placeholder.
3. Do not commit `.env`. Do not put store tokens in git.

## What you are renting

A single small Linux VM is enough for one brand. Something like a $5–12/month box (Hetzner, DigitalOcean, or similar) with 1–2 GB of RAM. Postgres can run on the same box via Docker. You do not need a GPU. Forecasts for a few hundred SKUs are a nightly job, not a live cluster.

You also need a domain and HTTPS. Caddy or the host’s load balancer can terminate TLS. Point the domain at the VM.

## Docker on the VM

Install Docker, clone the repo, and create `backend/.env` from `backend/.env.example`. Then set at least:

```bash
DEMO_MODE=false
AUTO_SEED=false
USE_SQLITE=false
SECRET_KEY=paste-a-long-random-string
PUBLIC_APP_URL=https://api.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com
CORS_ORIGINS=https://app.yourdomain.com
SHOPIFY_API_KEY=the-app-key
SHOPIFY_API_SECRET=the-app-secret
```

`SHOPIFY_API_KEY` and `SHOPIFY_API_SECRET` are **your app’s** credentials from the Shopify Partner dashboard, not the brand’s admin token. In the Shopify app setup, set the redirect URL to:

`https://api.yourdomain.com/api/integrations/shopify/callback`

Request only these scopes: `read_products`, `read_orders`, `read_inventory`, `read_locations`.

The brand then clicks **Connect Shopify** in the app. Their token is encrypted in Postgres.

ShipHero: in the app, paste a refresh token (ShipHero’s developer settings). Do not store their password. The app exchanges the refresh token itself.

Weekly email, optional: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM`, or set `DIGEST_WEBHOOK_URL` to a mail hook you already trust. If both are blank, the Monday note stays inside the app.

Start:

```bash
docker compose up -d --build
```

The Compose file in the repo is aimed at a **local demo** (it turns demo mode on and seeds Northline). For a client, override those environment values in `backend/.env` or a production compose override so demo mode stays off. The `environment:` block in `docker-compose.yml` currently forces demo mode; for production, remove `DEMO_MODE`, `AUTO_SEED`, and the demo `SECRET_KEY` from that block so the `.env` values win, or use a separate compose file. Do not ship the demo secret to a client.

Open the health check: `https://api.yourdomain.com/api/health`. `database` should be `ok` and `demo_mode` should be `false`.

Create the brand’s login with **Create a workspace** on the sign-in page. One login, one brand.

## Backups and leaving

Postgres data is in the `pgdata` volume. Snapshot that disk nightly. The brand can also delete their imported data or the whole account from Connections. That removes tokens.

## Cost shape

One VM, one Postgres, no per-seat SaaS bill yet. The expensive part later is support and a second brand, not the server. When you host more than one brand on one box, leave `ALLOW_ENV_CREDENTIALS` false so a token in the environment cannot leak across workspaces.

## A hosted preview from this change

There is no public URL attached to this branch. Hosting one would need the owner’s cloud account. The review path is `./scripts/demo.sh` on a laptop. See `docs/REVIEW-CHECKLIST.md`.
