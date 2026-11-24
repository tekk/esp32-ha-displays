#!/usr/bin/env bash
# Full rebuild: re-download everything and regenerate data, docs and indexes.
# Limits (file size, hosted budget, …) are in build/config.json.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 build/fetch_pan.py          # official file server → ../guition-cache/pan (≈9 GB, resumable, sha256-verified)
python3 build/scrape_guition.py     # guition.com tables + product pages, images, spec PDFs
python3 build/process_archives.py   # unpack ZIP/RAR, manifests, extract docs into site/docs/b
python3 build/autoadd.py            # new ESP32 display boards from vendor sites → data/auto/boards/
python3 build/build_site.py         # merge → site/data/models.json, archives.json, meta.json
python3 build/features.py           # normalized features[] per board (pictograms)
python3 build/fetch_extra.py        # Waveshare downloads + GitHub repo snapshots → ../guition-cache/extra
python3 build/offline.py            # ≤24 MB → site/, larger → GitHub Release asset list (data/release_assets.json)
python3 build/photos.py             # board photos → site/assets/img/{hd,th} (WebP ≤1600 px + thumbnails)
python3 build/icons.py              # pictogram sprite → site/assets/img/features.svg
python3 build/seo.py                # static board/vendor pages, JSON-LD, sitemap.xml, robots.txt, og-image.png
python3 build/fonts.py              # self-hosted fonts (woff2 + licences) → site/assets/fonts
node build/vendor.mjs               # copy JS libs into site/assets/vendor
node build/build_index.mjs          # prebuilt MiniSearch indexes
python3 build/gen_sw.py             # service worker precache list (offline / PWA)
python3 tests/check_links.py
python3 tests/check_seo.py
# then: build/upload_release.sh   (needs `gh auth login`)
# Incremental monthly update (what the GitHub Action runs): build/update.sh [--dry-run]
