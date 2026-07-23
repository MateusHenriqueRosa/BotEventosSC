# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discord bot that scrapes 9 Brazilian ticket websites for events in Santa Catarina (SC) using Selenium headless Chrome, then posts formatted embeds to a Discord channel. It also has a `!detalhes <link>` command that opens a single ticket page and extracts the lote/setores/preços (batches, sectors, prices). Written in Portuguese (BR).

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

There is no automated test suite, but two manual harnesses exist that run scrapers
without Discord (they print the embeds/tiers to the terminal):

```bash
# Test an event-listing scraper for a city (or "todos")
python test_scrapers.py "Florianópolis" blueticket

# Test the !detalhes extraction against a ticket link (or "todos" for built-in links)
python test_detalhes.py Blueticket
python test_detalhes.py "Nome" "https://www.blueticket.com.br/evento/..."
```

Both use a `MockCanal`/`MockEmbed` pair so no Discord token is needed. Prefer these over
running the full bot when validating a scraper change.

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

The orchestration in `bot_discord.py:buscar_eventos()` calls per-city scrapers in a city loop, then bulk scrapers once each. All share a single Selenium `driver` instance (sequential, not parallel) and a shared `eventos_enviados: set` for cross-site deduplication. Before the loop it maps every city through `canonizar_cidade()` (see below).

Two scrapers iterate multiple categories internally, not just one page:
- **Pensa no Evento** loops `TIPOS = ["Baladas", "Shows", "Eventos"]` — many venues (e.g. Hike Brava) are classified under `Eventos`/`Shows`, so searching only `Baladas` misses them.
- **eTicket Center** loops `festa/`, `show/`, `festival/` URLs.
- **Blueticket** loops `CATEGORIAS = ["Baladas", "Festivais", "Shows Nacionais"]` per city.

### Key shared utilities (`scrapers/helpers.py`)

- `criar_driver()` — creates headless Chrome with custom User-Agent hiding "HeadlessChrome"
- `resetar_driver(driver)` — clears cookies and navigates to about:blank between scrapers
- `normalizar_texto(texto)` — strips accents and lowercases for comparison
- `extrair_cidade(texto)` — extracts city name from strings like "Venue - Cidade/SC"
- `cidade_match(texto, cidades_norm)` — substring match of normalized city names (sorted longest-first to prefer "Balneario Camboriu" over "Camboriu")
- `canonizar_cidade(cidade)` — maps a user-typed city to its canonical accented form via `CIDADES_CANONICAS` (e.g. `"Itajai"` → `"Itajaí"`, `"praia brava"` → `"Itajaí"`). **Ingresso Nacional's on-site search is accent-sensitive**, so `!buscar Itajai` (no accent) returned 0 until this canonicalization was added in `buscar_eventos()`.
- `titulo_bloqueado(titulo)` — returns True if the event **title** matches `PADRAO_TITULO_BLOQUEADO` (stand-up, teatro, fisiculturismo/bodybuilder). Every scraper calls it right after extracting `nome` and `continue`s if blocked. It only ever sees the title, never the venue/location.
- `evento_key(nome, data)` — normalized dedup key
- `cancelavel_sleep(segundos, cancelar)` — async sleep that respects cancellation via `asyncio.Event`

### `!detalhes <link>` — ticket detail extraction (`scrapers/detalhes.py`)

`extrair_detalhes(link, driver, cancelar)` opens one ticket page and returns
`{"titulo", "tiers": [{"nome", "preco", "lote", "taxa", "resumo"}]}`. It is a **generic
text extractor**, not per-site: it collects short lines containing a `R$` price from the
document **and from same-origin iframes** (Blueticket renders its ticket panel inside an
iframe), then regex-parses each line into name/price/lote/taxa. Key rules:

- Only lines with ≤2 prices are kept (value + fee), so a single tier is one line.
- `KEYWORDS` filters to real ticket rows (pista, vip, feminino, masculino, meia, social, backstage, área, lote…).
- Names are cleaned by cutting at the first marker (`Valor:`, `Saiba Mais`, `Lote N`, `R$`, `a partir de`) and stripping UI noise.
- `LIXO_RE` drops cart/total lines; `R$ 0,00` is skipped.
- "a partir de R$ X" summary lines are kept only when no detailed tier already has that price (keeps Bilheteria Digital's per-day price, drops Guichê Web's redundant summaries).

The `!detalhes` command in `bot_discord.py` validates the link against `DOMINIOS_PERMITIDOS`
(the 9 `SITES` domains) before fetching, then formats the tiers into an embed. Works well on
Blueticket, Ingresso Nacional, Guichê Web, Pensa no Evento, Aqui Tem Ingressos and Bilheteria
Digital; Ingresso Digital only exposes a base price (sectors are behind the buy flow).

### Cancellation model

`buscas_ativas: dict[int, asyncio.Event]` maps Discord user ID to an Event. `!parar` sets the event; every scraper checks `cancelar.is_set()` between operations. `MAX_BUSCAS_SIMULTANEAS = 2` limits concurrent Chrome instances.

### Scraper sites are JS-heavy SPAs

Most target sites render via JavaScript. Selenium is required — static HTTP fetches (requests/httpx) will only see "Loading...". When a site changes its HTML structure, the corresponding scraper's CSS selectors need updating. Use browser DevTools or Claude in Chrome to re-map selectors.

Two site quirks worth knowing:
- **Ingresso Nacional is an AngularJS SPA.** There is no search URL; the scraper types the city into the search input, presses Enter, then reads cards (`div.col-sm-6.col-md-3.animated`). Cards have no `href` — the URL must be rebuilt from the Angular scope, mirroring the site's own `direcionar()` function (`_JS_LINK_EVENTO` in the scraper). There are **two card types**: a card with `IDCategoria == 0` is a **casa/venue** → `/{UrlCasa}` (e.g. `/vivabeachclub`); anything else is an **event** → `/evento/{IDEvento}/{urlEvento}` (e.g. `/evento/34613/viva-rasa-...`). Using the root-level casa route for an event silently redirects to the homepage — and then `!detalhes` finds no prices.
- **Blueticket's ticket panel is inside a same-origin iframe.** `!detalhes` must switch into iframes (which `detalhes.py` does) to read the prices.

## Adding a new scraper

1. Create `scrapers/newsite.py` with a function matching one of the two patterns above
2. Export it from `scrapers/__init__.py`
3. Add the site to the `SITES` list in `__init__.py` (this also adds its domain to `!detalhes`'s allowlist)
4. Wire it into `bot_discord.py:buscar_eventos()` — either in the per-city loop or the bulk_scrapers list
5. Use `evento_key()` + `eventos_enviados` set to avoid duplicate sends across sites
6. Call `titulo_bloqueado(nome)` right after extracting the event title and `continue` if it returns True (keeps stand-up/teatro/fisiculturismo out)

## Environment

- `BOT_TOKEN` — Discord bot token (required)
- `CANAL_ID` — Discord text channel ID restricting where `!buscar` works (0 = any channel)
- Docker uses `shm_size: "256m"` for Chrome stability
- ChromeDriver is pre-cached during Docker build via `webdriver-manager`

## Language

All user-facing strings, Discord embeds, log messages, variable names, and comments are in Brazilian Portuguese.
