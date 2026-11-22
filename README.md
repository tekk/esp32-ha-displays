# GUITION//CATALOG

Statický, vyhľadávateľný katalóg všetkých displejových dosiek **Guition** (JC…, ESP32-…, „CYD“) a vybraných dosiek **Waveshare ESP32-P4**: parametre, obrázky, PDF špecifikácie, kompletný strom súborov každého ZIP/RAR archívu z oficiálneho file servera a vstavaný prehliadač dokumentácie.
*Static, searchable catalog of all Guition display boards plus selected Waveshare ESP32-P4 boards – specs, images, spec PDFs, full file tree of every official archive and a built-in documentation browser.*

## Čo obsahuje / Contents

| | |
|---|---|
| `site/` | hotový statický web (nasadzuje sa iba tento priečinok) / the deployable static site |
| `site/data/models.json` | 104 modelov (Guition 97, Waveshare 7), normalizované parametre + zdroj (URL) ku každej hodnote |
| `site/data/archives.json` | 60 súborov z pan.jczn1688.com (8,7 GB) s mapovaním na modely |
| `site/data/manifests/<slug>.json` | kompletný strom súborov každého archívu (`path,size,blob,kind`) |
| `site/docs/b/` | extrahovaná dokumentácia (schémy, datasheety, README, vybrané demo zdrojáky), deduplikovaná podľa obsahu |
| `site/data/search-*.json` | predpočítané MiniSearch indexy (modely + fulltext dokumentácie) |
| `build/` | scraper + build skripty, limity v `build/config.json` |
| `data/curated/` | ručne overené doplnky so zdrojom: Waveshare, komunitné repozitáre, varianty JC1060P470, pinouty |
| `tests/` | `check_links.py` (lokálne odkazy, limity Pages), `e2e.py` (headless Chrome + screenshoty) |

### Funkcie / Features
- tmavý „terminal/hacker“ dizajn, tabuľka aj karty, triedenie podľa ľubovoľného stĺpca, výber stĺpcov, export CSV
- fazetové filtre s počtami (vendor, kategória, MCU, veľkosť, rozlíšenie, rozhranie, dotyk, panel, driver IC, Wi-Fi/BT, flash/PSRAM, tagy …), stav filtrov v URL (dá sa zdieľať)
- syntax dotazov: `mcu:esp32-p4 tag:rs485 7"` , klávesa `/` = vyhľadávanie
- detail modelu: všetky parametre (každý s odkazom na zdroj), galéria, PDF, archívy, komunitné odkazy, upozornenia na varianty, konflikty medzi zdrojmi výrobcu, pinouty
- prehliadač archívov: strom súborov, náhľad obrázkov, PDF (natívny iframe), markdown, HTML (sandbox), kód so zvýraznením (UTF-8/GBK), malé archívy (≤ 20 MB) sa dajú celé otvoriť v prehliadači cez JSZip
- fulltextové vyhľadávanie v dokumentácii (vrátane čínštiny)

### Dátové pravidlá / Data rules
Žiadne vymyslené parametre. Každá hodnota pochádza z reálneho zdroja (guition.com tabuľka modelov EN/SK, produktové stránky, PDF, waveshare.com / docs.waveshare.com, komunitné repozitáre) a jej URL je uložená. Prázdne = neznáme. Ak si zdroje výrobcu odporujú, zobrazí sa varovanie „source conflict“.
*No invented specs; every value has a stored source URL; empty = unknown; manufacturer-internal disagreements are flagged.*

## Hosting a offline súbory / Hosting & offline files
**Všetky ZIP/RAR a dokumenty sú dostupné offline** (nezávisle od pan.jczn1688.com):
- súbory ≤ 24 MB sú priamo v `site/` (`files/archives`, `files/pan`, `files/guition`, `files/waveshare`, `files/repos`) → servíruje ich GitHub/Cloudflare Pages,
- väčšie súbory (archívy Guition do ~620 MB, Waveshare demo, snapshoty GitHub repozitárov) sú **GitHub Release assets** v release `files-v1`:
  `https://github.com/tekk/esp32-ha-displays/releases/download/files-v1/<asset>`; súbory > 2 GB by sa rozdelili na `.001/.002…` (spojenie: `cat name.0* > name`),
- pôvodná URL výrobcu zostáva ako „mirror“, sha256 každého súboru je v `site/data/offline.json`,
- mapovanie *asset ↔ pôvodný názov ↔ URL ↔ sha256* je v `data/release_assets.json` (názvy assetov sú vopred očistené na `[A-Za-z0-9._-]`, aby ich GitHub nepremenoval),
- komunitné repozitáre sa zrkadlia iba ak majú licenčný súbor (alebo sú oficiálne od výrobcu); ostatné sú len odkazy (`offline.mirror_unlicensed_repos` v `build/config.json`).

*All files are available offline: ≤ 24 MB inside `site/`, larger ones as GitHub Release assets (tag `files-v1`), original vendor URL kept as mirror. Upload / re-upload with `build/upload_release.sh` (needs `gh auth login`).*

Limity: web ~10 200 súborov / ~710 MB, žiadny súbor > 24 MB → spĺňa Cloudflare Pages (20 000 súborov, 25 MiB/súbor) aj GitHub Pages (≤ 1 GB). Rozpočty: `build/config.json` (`limits.*`, `offline.*`).

## Lokálne spustenie / Run locally
```bash
python3 -m http.server -d site 8080     # http://localhost:8080
```

## Nasadenie / Deploy

### GitHub Pages
0. Release assets: `gh auth login && build/upload_release.sh`
1. Vytvor repozitár a pushni (`git remote add origin git@github.com:<user>/guition-catalog.git && git push -u origin main`).
2. Settings → Pages → **Source: GitHub Actions**.
3. Workflow `.github/workflows/pages.yml` pri každom pushi do `main` nahrá priečinok `site/` (bez buildu – všetko je predgenerované).
*Create a repo, push, set Pages source to “GitHub Actions”; the included workflow publishes `site/`.*
Poznámka: repozitár má ~650 MB (dokumentácia v `site/docs/b`). GitHub odporúča repozitáre < 1 GB, žiadny súbor nie je > 25 MB.

### Cloudflare Pages
- **Priamy upload (odporúčané)**:
  ```bash
  npx wrangler login
  npx wrangler pages project create guition-catalog --production-branch main
  npx wrangler pages deploy site --project-name guition-catalog
  ```
- **Napojenie na Git**: Framework preset *None*, Build command `exit 0` (alebo prázdne), **Build output directory `site`**.
- `site/_headers` nastavuje dlhú cache pre obsahovo adresované súbory.

## Rebuild (znovu stiahnuť všetko / re-download everything)
Požiadavky: Python 3.10+ (`pip install requests beautifulsoup4 playwright`), Node 18+, `apt install 7zip libarchive-tools poppler-utils`, ~20 GB disku (cache je mimo repozitára v `../guition-cache`).
```bash
npm install
./build/build_all.sh        # fetch_pan → scrape_guition → process_archives → build_site → vendor → build_index → check
```
Rýchly rebuild iba dát a indexov (bez sťahovania): `npm run build`.
Test: `python3 -m http.server -d site 8765 & python3 tests/e2e.py http://localhost:8765/`

## Známe poznámky k dátam / Known data notes
- **JC1060P470** sú dve rôzne dosky: `JC1060P470C_I_W` (žlté PCB, bez krytu) a `JC1060P470C_I_W_Y` (čierny kryt, modul JC-ESP32P4-M3, Ethernet, RS-485, 2×13 header) – rozdielny pinout, rozdielne archívy.
- „Guition 7" ESP32-P4 HMI 1024×600 60FPS“ = rodina JC1060P470; 60 FPS výrobca nepotvrdzuje (komunitné časovanie ≈ 60–65 Hz).
- Waveshare ESP32-P4-WIFI6-Touch-LCD-3.4C má podľa Waveshare rozlíšenie **800×800** (nie 720×720).
- „4× USB-A host“ pri ESP32-P4-Module-DEV-KIT nie je v zdrojoch Waveshare potvrdené – neuvádza sa.
- Tabuľka modelov Guition sa v niektorých bodoch líši od produktových stránok (napr. JC8012P4A1: 1024×600 vs 800×1280) – zobrazené ako konflikt.

## Licencia / License
Kód: MIT. Dáta, obrázky a dokumenty patria ich vlastníkom (Guition / Shenzhen Jingcai Intelligent, Waveshare, autori komunitných repozitárov); web je neoficiálny a s nimi nesúvisí. Knižnice v `site/assets/vendor/` majú vlastné licencie (priložené).
