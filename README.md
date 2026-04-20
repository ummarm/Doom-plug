# Doom-plug

This bundle keeps only these four scrapers from `D3adlyRocket/All-in-One-Nuvio`:

- `4KHDHub`
- `HDHub4u`
- `4khdhub-tv`
- `HindMoviez`

## Files

- `manifest.json`
- `providers/4khdhub.js`
- `providers/4khdhub_tv.js`
- `providers/hdhub4u.js`
- `providers/hindmoviez.js`

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
