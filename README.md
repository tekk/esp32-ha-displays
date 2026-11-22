# ESP32 Display Catalog (Guition · Waveshare)

Live: https://tekk.github.io/esp32-ha-displays/

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
| `data/curated/` | ručne overené doplnky so zdrojom: Waveshare, komunitné repozitáre, varianty JC1060P470, pinouty, `photos.json` (overené fotky konkrétnych variantov) |
| `data/auto/` | výsledky mesačného updatu (automaticky nájdené GitHub repozitáre, stav zrkadlených repozitárov, Waveshare kandidáti) |
| `site/assets/img/hd`, `th` | fotky dosiek (WebP ≤ 1600 px, < 1 MB) + náhľady (≤ 400 px); zdrojová URL každej fotky je v `models.json → images[].orig/source_page` |
| `site/assets/fonts/` | self-hosted Roboto Condensed, Montserrat, JetBrains Mono, Meslo LG (woff2 + licencie) |
| `tests/` | `check_links.py` (lokálne odkazy, limity Pages), `e2e.py` (headless Chrome + screenshoty) |

### Funkcie / Features
- čistý minimalistický tmavý dizajn s bielym akcentom, tabuľka aj karty, triedenie podľa ľubovoľného stĺpca, výber stĺpcov, export CSV
- fazetové filtre s počtami (vendor, kategória, MCU, veľkosť, rozlíšenie, rozhranie, dotyk, panel, driver IC, Wi-Fi/BT, flash/PSRAM, tagy …), stav filtrov v URL (dá sa zdieľať)
- syntax dotazov: `mcu:esp32-p4 tag:rs485 7"` , klávesa `/` = vyhľadávanie
- detail modelu: všetky parametre (každý s odkazom na zdroj), galéria, PDF, archívy, komunitné odkazy, upozornenia na varianty, konflikty medzi zdrojmi výrobcu, pinouty
- prehliadač archívov: strom súborov, náhľad obrázkov, PDF (natívny iframe), markdown, HTML (sandbox), kód so zvýraznením (UTF-8/GBK), malé archívy (≤ 20 MB) sa dajú celé otvoriť v prehliadači cez JSZip
- fulltextové vyhľadávanie v dokumentácii (vrátane čínštiny)
- **hover náhľad**: podržanie myši (alebo fokus klávesnicou) nad názvom modelu / náhľadom otvorí veľkú kartu – HD fotka vľavo, parametre, porty/konektory, rozhrania, bezdrôtové moduly, MCU/flash/PSRAM vpravo; na dotykových zariadeniach sa nezobrazuje
- **plne offline**: žiadne externé požiadavky (CSP `default-src 'self'`, fonty a knižnice lokálne, externé obrázky v náhľadoch HTML dokumentov sa blokujú); service worker (`site/sw.js`) + `manifest.webmanifest` → web funguje aj bez siete (PWA)

**Fotky / Photos.** Z oficiálnych zdrojov: guition.com (produktové galérie – výrobca publikuje max. 800×800 px), waveshare.com / docs.waveshare.com (1600×1200), obrázky „Structure/Dimension“ z oficiálnych archívov (iba ak archív patrí jednoznačne danému modelu). Nikdy sa nepoužije fotka inej dosky – pri zdieľaných produktových stránkach (napr. Waveshare 7/8/10.1") sa berú iba obrázky s názvom presného variantu (`data/curated/photos.json`). AliExpress (captcha) a eBay (403) sa nepoužívajú. `build/photos.py` → `data/raw/photo_stats.json`.

### Dátové pravidlá / Data rules
Žiadne vymyslené parametre. Každá hodnota pochádza z reálneho zdroja (guition.com tabuľka modelov EN/SK, produktové stránky, PDF, waveshare.com / docs.waveshare.com, komunitné repozitáre) a jej URL je uložená. Prázdne = neznáme. Ak si zdroje výrobcu odporujú, zobrazí sa varovanie „source conflict“.
*No invented specs; every value has a stored source URL; empty = unknown; manufacturer-internal disagreements are flagged.*

## Hosting a offline súbory / Hosting & offline files
**Všetky ZIP/RAR a dokumenty sú dostupné offline** (nezávisle od pan.jczn1688.com):
- súbory ≤ 24 MB sú priamo v `site/` (`files/archives`, `files/pan`, `files/guition`, `files/waveshare`, `files/repos`) → servíruje ich GitHub/Cloudflare Pages,
- väčšie súbory (archívy Guition do ~620 MB, Waveshare demo, snapshoty GitHub repozitárov) sú **GitHub Release assets** v release `files-v1`:
  `https://github.com/tekk/esp32-ha-displays/releases/download/files-v1/<asset>`; súbory > 1 GB sa rozdelia na `.001/.002…` (spojenie: `cat name.0* > name`),
- pôvodná URL výrobcu zostáva ako „mirror“, sha256 každého súboru je v `site/data/offline.json`,
- mapovanie *asset ↔ pôvodný názov ↔ URL ↔ sha256* je v `data/release_assets.json` (názvy assetov sú vopred očistené na `[A-Za-z0-9._-]`, aby ich GitHub nepremenoval),
- komunitné repozitáre sa zrkadlia iba ak majú licenčný súbor (alebo sú oficiálne od výrobcu); ostatné sú len odkazy (`offline.mirror_unlicensed_repos` v `build/config.json`).

*All files are available offline: ≤ 24 MB inside `site/`, larger ones as GitHub Release assets (tag `files-v1`), original vendor URL kept as mirror. Upload / re-upload with `build/upload_release.sh` (needs `gh auth login`).*

Limity: web ~11 300 súborov / ~740 MB, žiadny súbor > 24 MB → spĺňa Cloudflare Pages (20 000 súborov, 25 MiB/súbor) aj GitHub Pages (≤ 1 GB). Rozpočty: `build/config.json` (`limits.*`, `offline.*`).

## Mesačný update / Monthly update
`build/update.sh` (= `python3 build/update.py`) skontroluje všetky zdroje a pridá nové/zmenené veci:
1. **pan.jczn1688.com** – nové/zmenené súbory (veľkosť + sha256 shardov) → stiahnutie, rozbalenie dokumentácie (`process_archives.py --only`), umiestnenie do `site/` alebo upload ako release asset, zmazanie lokálnej kópie;
2. **guition.com** – tabuľka modelov EN/SK + produktové stránky zo sitemap → nové dosky, nové PDF/obrázky;
3. **Waveshare** – vyhľadávanie ESP32-P4 v e-shope (nové displejové dosky sa *hlásia* na ručnú kuráciu – parametre sa nevymýšľajú), HEAD všetkých odkazovaných súborov (Content-Length/ETag);
4. **GitHub** – vyhľadávanie nových komunitných repozitárov pre dosky Guition (odkaz k modelu, ak repo menuje číslo modelu a má ≥ 3 ★ alebo licenciu; licencované sa zrkadlia), `pushed_at` zrkadlených repozitárov → obnovenie snapshotu;
5. rebuild (`build_site → offline → photos → build_index → gen_sw → check_links`), commit + push (iba ak sa niečo zmenilo).

```bash
build/update.sh --dry-run          # iba zistí a vypíše zmeny
build/update.sh                    # ostrý beh (commit + push, upload release assetov cez gh)
build/update.sh --no-push --skip github,waveshare
```
Výstupy: `build/last_update/log.txt`, `stats.json` (new_boards, new_files, changed_files, removed_upstream, new_repos, updated_repos, waveshare_candidates, uploaded_assets, bytes_downloaded, errors, warnings, duration_s, commit), `summary.md`. Skript je idempotentný (opakovaný beh bez zmien nič necommitne) a sám neposiela e-mail.

### GitHub Action `.github/workflows/monthly-update.yml`
- spúšťa sa **15. dňa v mesiaci o 06:00 UTC** (`cron: '0 6 15 * *'`) a ručne (*Actions → Monthly catalog update → Run workflow*, vstup `dry_run` – predvolene zapnutý pri ručnom spustení, `skip`);
- runner nemá 18 GB cache: súbory sa spracúvajú po jednom a po uploade mažú (`GUITION_CACHE=$RUNNER_TEMP/cache`), porovnáva sa voči `data/raw/pan_files.json`, `site/data/offline.json`, `data/release_assets.json` a zoznamu assetov release;
- `GITHUB_TOKEN` (`contents: write`) na commit/push a `gh release upload`; po pushi spustí `pages.yml` (`actions: write`);
- log + stats sa nahrajú ako artefakt `update-log-<run_id>` a súhrn je v *job summary*;
- e-mail so súhrnom a prílohami `log.txt` + `stats.json` cez SMTP (`dawidd6/action-send-mail`). **Potrebné repository secrets** (*Settings → Secrets and variables → Actions*):

| Secret | Príklad |
|---|---|
| `SMTP_SERVER` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` (SSL) alebo `587` (STARTTLS) |
| `SMTP_USERNAME` | prihlasovacie meno SMTP |
| `SMTP_PASSWORD` | heslo / app password |
| `MAIL_TO` | adresát(i), oddelení čiarkou |
| `MAIL_FROM` | odosielateľ, napr. `Catalog bot <bot@example.com>` (inak `SMTP_USERNAME`) |

Ak `SMTP_SERVER` alebo `MAIL_TO` chýba, e-mail sa preskočí (notice v logu), zvyšok behu prebehne.

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
Požiadavky: Python 3.10+ (`pip install requests beautifulsoup4 pillow fonttools brotli playwright`), Node 18+, `apt install 7zip libarchive-tools poppler-utils`, ~20 GB disku (cache je mimo repozitára v `../guition-cache`).
```bash
npm install
./build/build_all.sh        # fetch_pan → scrape_guition → process_archives → build_site → fetch_extra → offline → photos → fonts → vendor → build_index → gen_sw → check
```
Rýchly rebuild iba dát a indexov (bez sťahovania): `npm run build`.
Test: `python3 -m http.server -d site 8765 & python3 tests/e2e.py http://localhost:8765/` (headless Chrome, všetky nelokálne požiadavky sú zablokované – test zlyhá pri akejkoľvek externej požiadavke)

## Známe poznámky k dátam / Known data notes
- **JC1060P470** sú dve rôzne dosky: `JC1060P470C_I_W` (žlté PCB, bez krytu) a `JC1060P470C_I_W_Y` (čierny kryt, modul JC-ESP32P4-M3, Ethernet, RS-485, 2×13 header) – rozdielny pinout, rozdielne archívy.
- „Guition 7" ESP32-P4 HMI 1024×600 60FPS“ = rodina JC1060P470; 60 FPS výrobca nepotvrdzuje (komunitné časovanie ≈ 60–65 Hz).
- Waveshare ESP32-P4-WIFI6-Touch-LCD-3.4C má podľa Waveshare rozlíšenie **800×800** (nie 720×720).
- „4× USB-A host“ pri ESP32-P4-Module-DEV-KIT nie je v zdrojoch Waveshare potvrdené – neuvádza sa.
- Tabuľka modelov Guition sa v niektorých bodoch líši od produktových stránok (napr. JC8012P4A1: 1024×600 vs 800×1280) – zobrazené ako konflikt.

## Licencia / License
Kód: MIT. Dáta, obrázky a dokumenty patria ich vlastníkom (Guition / Shenzhen Jingcai Intelligent, Waveshare, autori komunitných repozitárov); web je neoficiálny a s nimi nesúvisí. Knižnice v `site/assets/vendor/` a fonty v `site/assets/fonts/` (SIL OFL 1.1 / Apache 2.0) majú vlastné licencie (priložené).
