# Open the demo without Docker

This agent cannot publish a live URL. Render, Fly, Railway, and Vercel all ask for your login, and none of those credentials are on this machine. The path below is one click after you sign in. You do not install Docker.

## Click this

[Deploy the demo to Render](https://render.com/deploy?repo=https://github.com/corbinsz/demand-planning-platform)

1. Sign in to Render with GitHub. The free tier is enough for this demo.
2. Render reads `render.yaml` from the repo. If it asks which branch, choose `cursor/productize-inventory-forecast-3faf` until this pull request is merged, then `main`.
3. Confirm the service name `inventory-intel-demo`. Leave the environment values as they are. They turn on demo mode and the fictional Northline brand. They are not real store tokens.
4. Wait for the deploy (the first build installs Python and the website). Open the URL Render shows, ending in `.onrender.com`.
5. You should see “Know what to reorder before you stock out.” Click **See today’s decisions**. The first time, that list can take up to a minute while forecasts are checked. After that it is cached.

The free instance sleeps when nobody is using it. The next visit wakes it, which can take half a minute. That is the tradeoff for not paying.

If Render refuses the free plan for a Docker service, switch the instance to Starter (about $7 a month) and deploy again. Same button, same file.

## What you are looking at

Fictional brand, Salt Lake City warehouse, no customer data. Connect Shopify will explain that the server has no app key yet. That is expected on the preview.

## If you would rather not create a Render account

From the project folder, without Docker:

```bash
./scripts/demo.sh
```

Then open http://127.0.0.1:5173/ . That is the same demo, on your machine.
