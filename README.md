# Doom-plug

This bundle keeps only these seven scrapers from `D3adlyRocket/All-in-One-Nuvio`:

- `4KHDHub`
- `HDHub4u`
- `4khdhub-tv`
- `HindMoviez`
- `MovieBlast`
- `MoviesDrive`
- `StreamFlix`

## Files

- `manifest.json`
- `providers/4khdhub.js`
- `providers/4khdhub_tv.js`
- `providers/hdhub4u.js`
- `providers/hindmoviez.js`
- `providers/movieblast.js`
- `providers/moviesdrive.js`
- `providers/streamflix.js`

## How to publish

1. Create a new GitHub repository.
2. Upload this folder's contents to that repository.
3. Use the raw GitHub URL to your `manifest.json` in Nuvio.

Example raw URL format:

```text
https://raw.githubusercontent.com/<your-user>/<your-repo>/main/manifest.json
```

## Notes

- The provider files were copied from the GPL-3.0 licensed upstream repo:
  `https://github.com/D3adlyRocket/All-in-One-Nuvio`
- If you keep redistributing these files, keep the original license terms and attribution in mind.
- `4KHDHub`, `4khdhub-tv`, and `HDHub4u` now read domain data from this repo's `domains.json`.
- `HindMoviez` now returns resolved direct URLs instead of relying on the upstream Cloudflare worker.
- `4KHDHub`, `4khdhub-tv`, and `HDHub4u` are patched to prefer FSL-family links first, but they fall back to the original available links if no FSL link exists.

## Upstream monitoring

This repo now includes a GitHub Actions workflow at `.github/workflows/upstream-sync.yml`.

- It checks the upstream repo every day.
- Real sync work only happens every 2 days, anchored from `2026-04-20`.
- That means the cadence lands on dates like `2026-04-20`, `2026-04-22`, `2026-04-24`, `2026-04-26`, `2026-04-28`, and so on.
- If one of the tracked upstream scrapers changes, the workflow updates the local provider file, preserves Doom-plug's local patches, bumps the affected version numbers in `manifest.json`, and opens a pull request automatically.
- You can also run it manually from the GitHub Actions tab with `force=true`.

Tracked upstream files:

- `providers/4khdhub.js`
- `providers/4khdhub_tv.js`
- `providers/hdhub4u.js`
- `providers/hindmoviez.js`
- `providers/movieblast.js`
- `providers/moviesdrive.js`
- `providers/streamflix.js`
