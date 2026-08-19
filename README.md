# AppLovin Culinary Catalog Feed — Automation

Runs daily, pulls the latest feed from ChannelAdvisor, filters to classes
starting 3–30 days out, transforms to AppLovin's catalog CSV schema, and
commits the result to `feed/applovin_catalog_feed.csv` in this repo.

## One-time setup

1. **Create a new PUBLIC repo** on your GitHub account (e.g. `applovin-catalog-feed`).
   Keep this separate from any private/internal repos — AppLovin needs to
   reach the output file with no login.

2. **Upload these files** into that repo, preserving folder structure:
   - `transform_feed.py`
   - `.github/workflows/update-feed.yml`
   - `requirements.txt`

3. **Add your ChannelAdvisor credentials as encrypted Secrets** (never pasted
   into chat, never handled by Claude):
   - Go to **Settings → Secrets and variables → Actions** in the new repo
   - Click **New repository secret** and add:
     - `CHANNELADVISOR_FEED_URL` — the export URL from ChannelAdvisor
     - If the export needs HTTP basic auth: `CA_AUTH_USER` and `CA_AUTH_PASS`
     - If it needs an API key header instead: `CA_API_KEY`
     - (Only add the auth secrets your export actually requires.)

4. **Enable Actions** if prompted — go to the **Actions** tab and click
   "I understand my workflows, go ahead and enable them."

5. **Run it once manually** to confirm it works:
   - Actions tab → "Update AppLovin catalog feed" → **Run workflow**
   - Check the run logs. If `transform_feed.py` fails validation or the fetch,
     the run will show a red X with the error message.

6. **Grab the permanent output URL** once a run succeeds:
   ```
   https://raw.githubusercontent.com/<your-username>/<repo-name>/main/feed/applovin_catalog_feed.csv
   ```

7. **Paste that URL into AppLovin's Catalog Manager** as the Source URL
   (Connection type: Public URL, Delimiter: Comma).

## Adjusting the rolling window

Edit the two env vars in `.github/workflows/update-feed.yml`:
```yaml
WINDOW_START_DAYS: "3"     # exclude classes starting sooner than this
WINDOW_END_DAYS: "30"      # exclude classes starting later than this
```

## Adjusting the schedule

The cron line in the workflow (`0 6 * * *`) runs daily at 06:00 UTC. AppLovin
syncs the catalog roughly once a day, so this should run comfortably before
that. Change the cron expression if you want a different time.

## If the ChannelAdvisor feed's column names or format ever change

`transform_feed.py` expects a tab-separated file with these source columns:
`id, item_group_id, title, price, image_link, availability, link,
description, brand, google_product_category, sale_price,
additional_image_link, custom_label_0`

If ChannelAdvisor's export format changes, the script will fail loudly at
the "missing expected columns" check rather than silently producing bad data.
