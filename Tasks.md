# Tasks.md — Planejamento BotEventosSC

## Visão Geral

O bot Discord faz web scraping de sites de ingressos online, filtra por **cidade** (SC) e **categoria** (balada/festa/casa de evento), e envia as informações dos eventos no Discord via embeds.

**Cidades já configuradas no código (linha 21 de `bot_discord.py`):**
Florianópolis, Brusque, Blumenau, Balneário Camboriú, Camboriú, Itapema, Porto Belo, Itajaí

**Categorias-alvo:** Balada, Festa, Casa de Evento

---

## 1. Estado Atual dos Sites

### Sites JÁ implementados:
| Site | Função | Status |
|------|--------|--------|
| ingressonacional.com.br | `buscar_eventos()` (linhas 329-395) | Com bugs críticos |
| blueticket.com.br | `buscar_blueticket()` / `_scrape_blueticket_categoria()` (linhas 58-131) | Seletores não verificáveis (SPA Vue.js) |
| guicheweb.com.br | `buscar_guicheweb()` (linhas 144-196) | Seletores possivelmente desatualizados |
| pensanoevento.com.br | `buscar_pensanoevento()` (linhas 199-315) | Seletores possivelmente desatualizados |

### Sites a ADICIONAR:
| Site | Tipo | Filtro Cidade | Filtro Categoria | Prioridade |
|------|------|---------------|------------------|------------|
| minhaentrada.com.br | SSR | Dropdown (estado + cidade) | URL: `/agenda-geral?categoria=2` (Baladas), `?categoria=6` (Festas) | Alta |
| bilheteriadigital.com/SC | SSR + JS | URL: `/SC` (por estado) | Não possui filtro por categoria | Média |
| aquitemingressos.com.br | SSR | Sem filtro explícito (eventos regionais SC) | Sem filtro explícito | Média |
| ingressodigital.com | SSR (PHP) | Form: `txt_estado=SC`, `txt_cidade=` | URL: `txt_genero=27` (Shows) — sem "Balada" específica | Baixa |
| eticketcenter.com.br | SSR | Sem filtro por cidade | URL: `/eventos/festa/`, `/eventos/show/` | Baixa |

---

## 2. Bugs Mapeados

### BUG-01: `load_dotenv()` nunca é chamado
- **Arquivo:** `bot_discord.py` (linhas 17-18)
- **Problema:** O código usa `os.getenv("BOT_TOKEN")` e `os.getenv("CANAL_ID")` mas nunca chama `load_dotenv()` do pacote `python-dotenv` (que está no `requirements.txt`). Em ambiente local, o arquivo `.env` **não é carregado**, e as variáveis retornam `None`.
- **Impacto:** O bot não inicia em desenvolvimento local. Funciona apenas no Docker/Render porque o `docker-compose.yml` usa `env_file: .env`.
- **Correção:**
  ```python
  # Adicionar no topo de bot_discord.py, após os imports:
  from dotenv import load_dotenv
  load_dotenv()
  ```
- **Por que corrigir:** Qualquer dev que clonar o repo e rodar localmente vai ter o bot falhando silenciosamente com `BOT_TOKEN = None`.

---

### BUG-02: XPaths absolutos no Ingresso Nacional (extremamente frágeis)
- **Arquivo:** `bot_discord.py` (linhas 342-343, 359, 372-374)
- **Problema:** XPaths absolutos como `/html/body/div[1]/div[3]/div/div[2]/div/form/div/div/input` quebram com qualquer mudança mínima no HTML do site (um `<div>` adicionado, uma reestruturação de layout).
- **Impacto:** O scraper do Ingresso Nacional muito provavelmente já está quebrado ou vai quebrar no próximo deploy do site.
- **Correção:**
  1. Acessar o site via navegador e inspecionar os seletores CSS atuais
  2. Substituir XPaths absolutos por seletores CSS relativos, ex:
     ```python
     # Em vez de XPath absoluto:
     search_box = WebDriverWait(driver, 10).until(
         EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][placeholder*='Buscar'], input.search-input"))
     )
     ```
  3. Usar seletores com `By.CSS_SELECTOR` ou `By.XPATH` com caminhos relativos (ex: `//input[@name='search']`)
- **Por que corrigir:** XPaths absolutos são a forma mais frágil de localizar elementos. Qualquer mudança no DOM (mesmo irrelevante) quebra o scraper.

---

### BUG-03: Ingresso Nacional não captura link do evento
- **Arquivo:** `bot_discord.py` (linhas 380-388)
- **Problema:** O embed do Ingresso Nacional **não inclui o link/URL** do evento. Os embeds de Blueticket, GuicheWeb e PensaNoEvento incluem `url=href` e um campo `"🔗 Link"`, mas o Ingresso Nacional não captura o `href` do card.
- **Impacto:** O usuário no Discord vê o evento mas não tem como acessá-lo diretamente.
- **Correção:**
  ```python
  # Adicionar captura do link no loop de eventos:
  link_xpath = f"/html/body/div[1]/div[3]/div/div[3]/div[1]/div[{i}]/a"
  link = driver.find_element(By.XPATH, link_xpath).get_attribute("href")
  
  # E incluir no embed:
  embed = discord.Embed(
      title=f"🎭 {nome}",
      description=f"**📅 Data:** {data}\n**📍 Local:** {cidade}",
      color=0x5865F2,
      url=link  # <-- adicionar
  )
  embed.add_field(name="🔗 Link", value=link, inline=False)
  ```
- **Por que corrigir:** O objetivo do bot é divulgar eventos. Sem o link, o usuário não consegue comprar o ingresso.

---

### BUG-04: Loop de busca do Ingresso Nacional quebra após primeira cidade
- **Arquivo:** `bot_discord.py` (linhas 331-395)
- **Problema:** O scraper navega para `/balada` uma única vez (linha 331), depois para cada cidade: limpa o search box, digita a cidade, e aperta ENTER. Porém, ao submeter a busca, a página **pode navegar para outra URL** (resultados de busca), e ao voltar para buscar a próxima cidade, o `search_box` original não existe mais no DOM.
- **Impacto:** Apenas a primeira cidade é buscada corretamente. As demais falham com `StaleElementReferenceException` ou `NoSuchElementException`.
- **Correção:**
  ```python
  for cidade in lista:
      if cancelar.is_set():
          return
      # Navegar para a página de busca a cada cidade
      driver.get("https://www.ingressonacional.com.br/balada")
      await cancelavel_sleep(2, cancelar)
      
      search_box = WebDriverWait(driver, 10).until(
          EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
      )
      search_box.clear()
      search_box.send_keys(cidade)
      # ...
  ```
- **Por que corrigir:** Sem renavegar para a página base, o bot só consegue buscar eventos na primeira cidade da lista.

---

### BUG-05: `CANAL_ID` definido mas nunca utilizado
- **Arquivo:** `bot_discord.py` (linha 18)
- **Problema:** A variável `CANAL_ID` é lida do `.env` mas **nunca usada** em nenhum comando. O bot responde em qualquer canal onde receber um `!buscar`.
- **Impacto:** Nenhum impacto funcional, mas é uma feature incompleta que pode gerar spam em canais indesejados.
- **Correção:**
  ```python
  @bot.command(name='buscar')
  async def buscar(ctx, *, args: str = None):
      if CANAL_ID and ctx.channel.id != CANAL_ID:
          await ctx.send("⚠️ Este comando só pode ser usado no canal designado.")
          return
      # ... resto do comando
  ```
- **Por que corrigir:** Evita que o bot envie dezenas de embeds em canais errados.

---

### BUG-06: `discord-webhook` no requirements.txt mas nunca importado
- **Arquivo:** `requirements.txt` (linha 4)
- **Problema:** O pacote `discord-webhook==1.4.1` está listado como dependência mas **nunca é importado ou utilizado** em nenhum arquivo do projeto.
- **Impacto:** Aumenta o tamanho da imagem Docker desnecessariamente.
- **Correção:** Remover a linha `discord-webhook==1.4.1` do `requirements.txt`, OU implementar suporte a webhook como alternativa ao bot (para notificações agendadas/automáticas).
- **Por que corrigir:** Dependência morta aumenta superfície de ataque e tamanho do container.

---

### BUG-07: `Dockerfile` listado no `.gitignore` mas tracked no git
- **Arquivo:** `.gitignore` (última linha relevante)
- **Problema:** O `Dockerfile` aparece no `.gitignore` mas já está commitado no repositório. O `.gitignore` só previne novos arquivos de serem adicionados — não remove arquivos já tracked.
- **Impacto:** Confusão para contribuidores. Se alguém editar o Dockerfile, o git vai mostrar mudanças normalmente (porque já é tracked), mas a presença no `.gitignore` sugere que não deveria ser commitado.
- **Correção:** Remover `Dockerfile` do `.gitignore` (já que ele precisa estar no repo para Docker build).
- **Por que corrigir:** Mantém consistência entre o que está tracked e o que o `.gitignore` diz.

---

### BUG-08: Erros silenciados com `except` genérico
- **Arquivo:** `bot_discord.py` (linhas 118-120, 193-194, 308-313, 394)
- **Problema:** Múltiplos blocos `except Exception: continue` ou `except Exception: pass` que engolem erros sem logar nada. Se um seletor CSS mudar no site, o scraper silenciosamente retorna 0 eventos sem indicar o motivo.
- **Impacto:** Debugging extremamente difícil. Impossível saber se o site mudou, se o driver crashou, ou se simplesmente não havia eventos.
- **Correção:**
  ```python
  import logging
  logger = logging.getLogger("bot_eventos")
  
  # Nos blocos except:
  except Exception as e:
      logger.warning(f"Erro ao processar card em {cidade}: {e}")
      continue
  ```
- **Por que corrigir:** Sem logging, é impossível diagnosticar quando um scraper para de funcionar.

---

### BUG-09: Sem deduplicação de eventos
- **Problema:** O mesmo evento pode aparecer em múltiplos sites (ex: um evento em Blumenau pode estar na Blueticket, GuicheWeb E PensaNoEvento). O bot envia todos como embeds separados no Discord.
- **Impacto:** Spam no Discord com eventos duplicados.
- **Correção:**
  ```python
  # Manter um set de eventos já enviados (por nome normalizado + data):
  eventos_enviados: set[str] = set()
  
  def evento_key(nome: str, data: str) -> str:
      return f"{nome.lower().strip()}|{data.strip()}"
  
  # Antes de enviar cada embed:
  key = evento_key(nome, data)
  if key in eventos_enviados:
      continue
  eventos_enviados.add(key)
  ```
- **Por que corrigir:** Melhora a experiência do usuário no Discord.

---

### BUG-10: Driver único compartilhado entre todos os scrapers
- **Arquivo:** `bot_discord.py` (linha 325, usado em linhas 397-419)
- **Problema:** Um único `webdriver.Chrome` é criado e passado para todos os scrapers sequencialmente. Se um scraper falha e deixa o driver em estado inconsistente (ex: popup aberto, página de erro), os scrapers seguintes podem falhar também.
- **Impacto:** Falha em cascata — um site fora do ar pode derrubar todos os scrapers subsequentes.
- **Correção:** Considerar criar um driver novo para cada scraper, OU pelo menos resetar o estado do driver entre scrapers:
  ```python
  driver.delete_all_cookies()
  driver.get("about:blank")
  ```
- **Por que corrigir:** Isolamento de falhas. Um site com problema não deve afetar os demais.

---

## 3. Tarefas de Implementação

### FASE 1 — Correção de Bugs (Prioridade Máxima) ✅ CONCLUÍDA

- [x] **T01:** Adicionar `load_dotenv()` no topo do `bot_discord.py` (BUG-01) — `from dotenv import load_dotenv` + `load_dotenv()` adicionados nas linhas 16-18
- [x] **T02:** Substituir XPaths absolutos do Ingresso Nacional por CSS selectors relativos (BUG-02) — Nova função `buscar_ingressonacional()` com fallback de múltiplos seletores CSS
- [x] **T03:** Capturar e incluir link do evento no embed do Ingresso Nacional (BUG-03) — `url=link` no embed + campo "🔗 Link" adicionados
- [x] **T04:** Renavegar para `/balada` a cada iteração de cidade no Ingresso Nacional (BUG-04) — `driver.get()` chamado no início de cada cidade dentro de `buscar_ingressonacional()`
- [x] **T05:** Implementar uso de `CANAL_ID` para restringir canal de resposta (BUG-05) — Check `if CANAL_ID and ctx.channel.id != CANAL_ID` no comando `!buscar` (linha 557)
- [x] **T06:** Remover `discord-webhook` do requirements.txt (BUG-06) — Linha removida de `requirements.txt`
- [x] **T07:** Remover `Dockerfile` do `.gitignore` (BUG-07) — Linha removida + duplicata de `exemplo_selenium.py` limpa
- [x] **T08:** Adicionar logging com `logging` module nos blocos `except` (BUG-08) — `logger.warning()` / `logger.info()` em todos os scrapers (Blueticket, GuicheWeb, PensaNoEvento, IngressoNacional)
- [x] **T09:** Implementar deduplicação de eventos por nome+data (BUG-09) — Função `evento_key()` (linha 35) + set `eventos_enviados` passado a todos os scrapers
- [x] **T10:** Resetar estado do driver entre scrapers (BUG-10) — Função `resetar_driver()` (linha 72) chamada entre cada scraper em `buscar_eventos()`

### FASE 2 — Novos Scrapers (Prioridade Alta) ✅ CONCLUÍDA

#### T11: Implementar `buscar_minhaentrada()` ✅
- **Implementado:** `bot_discord.py` linha 512
- **Abordagem:** Busca em bulk — carrega `/agenda-geral?categoria=2` (Baladas) e `?categoria=6` (Festas) uma vez cada, filtra por cidades via `cidade_match()`
- **Seletores:** `a[href*="/evento/"]` para cards, `h4` para nome, `img` para imagem
- **Cor:** `0x00BFA5` | **Footer:** "Minha Entrada"

#### T12: Implementar `buscar_bilheteriadigital()` ✅
- **Implementado:** `bot_discord.py` linha 611
- **Abordagem:** Busca em bulk — carrega `/SC` que lista todos os eventos do estado, filtra por cidade extraindo do padrão "Cidade - SC" via `extrair_cidade()`
- **Seletores:** `a[href]` filtrados por domínio e presença de " - SC" no texto
- **Cor:** `0x6C3BF5` | **Footer:** "Bilheteria Digital"

#### T13: Implementar `buscar_aquitemingressos()` ✅
- **Implementado:** `bot_discord.py` linha 711
- **Abordagem:** Busca em bulk — carrega `/eventos`, extrai cards por `a[href*="__"]`, filtra cidade do campo local via `extrair_cidade()` + `cidade_match()` como fallback
- **Seletores:** `a[href*='__']` para cards, `h4` para nome, parent text para data/local
- **Cor:** `0xF5A623` | **Footer:** "Aqui Tem Ingressos"

#### T14: Implementar `buscar_ingressodigital()` ✅
- **Implementado:** `bot_discord.py` linha 821
- **Abordagem:** Busca paginada — navega `/pesquisa.php?busca=S&pg={n}&txt_estado=SC` (até 5 páginas), filtra por cidade via `cidade_match()`
- **Seletores:** `a[href*='/evento/']` para cards, `h3/h4/h2` para nome
- **Cor:** `0x2196F3` | **Footer:** "Ingresso Digital"

#### T15: Implementar `buscar_eticketcenter()` ✅
- **Implementado:** `bot_discord.py` linha 944
- **Abordagem:** Busca por 3 categorias — `/eventos/festa/`, `/eventos/show/`, `/eventos/festival/`, filtra por cidade via `cidade_match()`
- **Seletores:** `a[href*='/eventos/']` filtrados por profundidade de URL (>5 segmentos)
- **Cor:** `0xE91E63` | **Footer:** "eTicket Center"

**Helpers adicionados (módulo-level):**
- `normalizar_texto()` — remove acentos + lowercase (linha 42)
- `extrair_cidade()` — extrai cidade de padrões "/SC", ", SC", "- SC" (linha 48)
- `cidade_match()` — verifica se alguma cidade da lista aparece no texto (linha 61)

**Integração em `buscar_eventos()`:** Novos scrapers chamados sequencialmente após os existentes (linhas 1100-1124), cada um com `resetar_driver()` entre chamadas

### FASE 3 — Melhorias de Arquitetura (Prioridade Média)

- [ ] **T16:** Refatorar scrapers em módulo separado (`scrapers/`)
  - Criar `scrapers/__init__.py`
  - Criar um arquivo por site: `scrapers/ingresso_nacional.py`, etc.
  - Cada scraper segue interface comum: `async def buscar(canal, cidade, driver, cancelar) -> int`
  - Facilita manutenção individual de cada scraper

- [ ] **T17:** Adicionar comando `!cidades` para listar cidades disponíveis
  - Exibe as 8 cidades padrão
  - Ajuda o usuário a saber quais cidades pode buscar

- [ ] **T18:** Adicionar comando `!sites` para listar sites sendo consultados
  - Lista todos os 9 sites com status (ativo/inativo)
  - Permite ao usuário saber de onde vêm os eventos

- [ ] **T19:** Adicionar resumo final por site
  - Ao final da busca, mostrar tabela com quantidade de eventos por site
  - Ex: "Blueticket: 5 | GuicheWeb: 3 | PensaNoEvento: 8"

- [ ] **T20:** Atualizar `Dockerfile` para incluir novos arquivos se modularizado

- [ ] **T21:** Atualizar `README.md` com novos sites e comandos

---

## 4. Estrutura HTML dos Sites (Referência para Scraping)

### ingressonacional.com.br
- **Página:** `/balada`
- **Busca:** Campo de texto (input) — digitar cidade e ENTER
- **Cards:** Div containers com XPath relativo ao container principal
- **Nota:** Site carrega via AJAX (loader gif detectado). Precisa de Selenium.

### blueticket.com.br
- **Página:** `/search?q={cidade}&category={categoria}`
- **SPA Vue.js** — renderiza client-side
- **Cards:** `a.event-card` (a confirmar — SPA retorna "Loading..." no fetch estático)
- **Campos:** `.event-title`, `.event-location`, `.event-date`, `.event-hour`
- **Nota:** Selectors precisam ser verificados com navegador real (Selenium obrigatório)

### guicheweb.com.br
- **Página:** `/pesquisa/{slug-cidade}`
- **Cards:** `a.text-reset` contendo `.Card`
- **Campos:** `h6.Title`, `.Cidade`, `.Data`, `img.card-img-top`
- **Nota:** Retornou "nenhum evento" para Florianópolis e Blumenau — pode não ter cobertura nessas cidades

### pensanoevento.com.br
- **Página:** `/sitev2/eventos/busca?tipo=Baladas&cidade={cidade}`
- **Cards:** `a.hotelsCard`
- **Campos:** `h4 span` (nome), `.text-14.text-light-1` (data), `p.text-light-1` (local)
- **Nota:** Selectors não confirmados no fetch estático (pode ser SPA parcial)

### minhaentrada.com.br (NOVO)
- **Página:** `/agenda-geral?categoria=2` (Baladas), `?categoria=6` (Festas)
- **Filtro:** Dropdown frontend para Estado + Cidade
- **Cards:** `a[href*="/evento/"]`
- **Campos:** `h4` (nome), texto (data/local), `img` S3 (imagem)
- **Link pattern:** `/evento/{slug}-{id}`

### bilheteriadigital.com (NOVO)
- **Página:** `/SC`
- **Carregamento:** JS `eventosPorEstado('SC')`
- **Cards:** `ul > li > a`
- **Link pattern:** `/{slug-date}`
- **Dados:** Nome, data ("20 de Junho"), cidade ("Joinville - SC"), local

### aquitemingressos.com.br (NOVO)
- **Página:** `/eventos`
- **Cards:** `a[href*="__"]`
- **Campos:** `h4 > a` (nome), `<p>` (data + local), `img` CloudFront
- **Link pattern:** `/{slug}___{id}/`

### ingressodigital.com (NOVO)
- **Página:** `/pesquisa.php?busca=S&pg=1&txt_estado=SC`
- **Filtros URL:** `txt_genero`, `txt_estado`, `txt_cidade`, `txt_data`
- **Link pattern:** `/evento/{id}/{slug}`

### eticketcenter.com.br (NOVO)
- **Página:** `/eventos/festa/`, `/eventos/show/`
- **Link pattern:** `/eventos/{cat}/{slug}/{date}/{time}/`
- **Multi-estado:** Filtrar resultados por cidade SC

---

## 5. Ordem de Execução Recomendada

```
FASE 1 (Bugs):     T01 → T07 → T08 → T02+T03+T04 → T05 → T06 → T09 → T10
FASE 2 (Scrapers):  T11 → T12 → T13 → T14 → T15
FASE 3 (Melhorias): T16 → T17 → T18 → T19 → T20 → T21
```

**Estimativa:**
- Fase 1: ~2-3 horas (bugs simples + Ingresso Nacional requer inspeção no navegador)
- Fase 2: ~4-6 horas (5 scrapers novos, cada um requer teste com navegador real)
- Fase 3: ~2-3 horas (refatoração e documentação)

---

## 6. Dependências e Considerações

- **Selenium é obrigatório** para todos os sites — mesmo os SSR usam JS para filtros/carregamento
- **Os seletores CSS precisam ser validados com navegador real** — o WebFetch estático não renderiza JS
- **Sites podem mudar estrutura HTML a qualquer momento** — scrapers precisam de logging robusto para detectar mudanças
- **Rate limiting:** Manter `cancelavel_sleep()` entre requests para não sobrecarregar os sites
- **Nenhuma dependência nova necessária** — Selenium + discord.py já cobrem tudo
