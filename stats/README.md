# Active-user counter

A Cloudflare Worker with a D1 database, at `https://stats.codeprojectsofficial.com`. Job Hunter sends it one
anonymous ping a day (`bot.ping_usage`): a random install id and the version. Nothing else is sent or stored.
Users can turn it off in **Settings > Count me as an active user**.

`GET /stats` returns the numbers (cached for 10 minutes), for the app's About box and the website:

```json
{"daily": 120, "weekly": 540, "monthly": 1240, "installs": 3100, "versions": {"2.0.0": 500, "1.4.3": 40}, "updated": "..."}
```

## Deploy (once)

Both free on Cloudflare's free plan. From this folder:

```
npx wrangler@4.167.0 login
npx wrangler@4.167.0 d1 create job-hunter-stats          # copy the database_id it prints into wrangler.toml
npx wrangler@4.167.0 d1 execute job-hunter-stats --remote --file schema.sql
npx wrangler@4.167.0 deploy
```

Check it: `curl https://stats.codeprojectsofficial.com/stats`
