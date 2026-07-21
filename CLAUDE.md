# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discord bot that scrapes 9 Brazilian ticket websites for events in Santa Catarina (SC) using Selenium headless Chrome, then posts formatted embeds to a Discord channel. Written in Portuguese (BR).

## Commands

```bash
# Run locally (requires Chrome installed)
python bot_discord.py

# Docker (production on VPS)
docker compose up -d --build
docker compose logs -f

# After code changes on VPS
cd /root/BotEventosSC && git pull && docker compose up -d --build
```

No test suite exists. Verify changes by running the bot and using `!buscar <cidade>` in Discord.

## Architecture

### Two scraper patterns

Scrapers in `scrapers/` follow one of two calling conventions:

1. **Per-city** — receives a single `cidade` string, called once per city in a loop:
   - `buscar_ingressonacional(canal, cidade, driver, cancelar, eventos_enviados)`
   - `buscar_blueticket(canal, cidade, driver, cancelar, eventos_enviados)`
   - `buscar_guicheweb(canal, cidade, driver, cancelar, eventos_enviados)`
   - `buscar_pensanoevento(canal, cidade, driver, cancelar, eventos_enviados)`

2. **Bulk** — receives `cidades_busca` list, loads one page for all of SC, filters by city in Python:
   - `buscar_minhaentrada(canal, cidades_busca, driver, cancelar, eventos_enviados)`
   - `buscar_bilheteriadigital(canal, cidades_busca, driver, cancelar, eventos_enviados)`
   - `buscar_aquitemingressos(canal, cidades_busca, driver, cancelar, eventos_enviados)`
   - `buscar_ingressodigital(canal, cidades_busca, driver, cancelar, eventos_enviados)`
   - `buscar_eticketcenter(canal, cidades_busca, driver, cancelar, eventos_enviados)`

The orchestration in `bot_discord.py:buscar_eventos()` calls per-city scrapers in a city loop, then bulk scrapers once each. All share a single Selenium `driver` instance (sequential, not parallel) and a shared `eventos_enviados: set` for cross-site deduplication.

### Key shared utilities (`scrapers/helpers.py`)

- `criar_driver()` — creates headless Chrome with custom User-Agent hiding "HeadlessChrome"
- `resetar_driver(driver)` — clears cookies and navigates to about:blank between scrapers
- `normalizar_texto(texto)` — strips accents and lowercases for comparison
- `extrair_cidade(texto)` — extracts city name from strings like "Venue - Cidade/SC"
- `cidade_match(texto, cidades_norm)` — substring match of normalized city names (sorted longest-first to prefer "Balneario Camboriu" over "Camboriu")
- `evento_key(nome, data)` — normalized dedup key
- `cancelavel_sleep(segundos, cancelar)` — async sleep that respects cancellation via `asyncio.Event`

### Cancellation model

`buscas_ativas: dict[int, asyncio.Event]` maps Discord user ID to an Event. `!parar` sets the event; every scraper checks `cancelar.is_set()` between operations. `MAX_BUSCAS_SIMULTANEAS = 2` limits concurrent Chrome instances.

### Scraper sites are JS-heavy SPAs

Most target sites render via JavaScript. Selenium is required — static HTTP fetches (requests/httpx) will only see "Loading...". When a site changes its HTML structure, the corresponding scraper's CSS selectors need updating. Use browser DevTools or Claude in Chrome to re-map selectors.

## Adding a new scraper

1. Create `scrapers/newsite.py` with a function matching one of the two patterns above
2. Export it from `scrapers/__init__.py`
3. Add the site to the `SITES` list in `__init__.py`
4. Wire it into `bot_discord.py:buscar_eventos()` — either in the per-city loop or the bulk_scrapers list
5. Use `evento_key()` + `eventos_enviados` set to avoid duplicate sends across sites

## Environment

- `BOT_TOKEN` — Discord bot token (required)
- `CANAL_ID` — Discord text channel ID restricting where `!buscar` works (0 = any channel)
- Docker uses `shm_size: "256m"` for Chrome stability
- ChromeDriver is pre-cached during Docker build via `webdriver-manager`

## Language

All user-facing strings, Discord embeds, log messages, variable names, and comments are in Brazilian Portuguese.
