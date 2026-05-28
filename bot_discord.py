import discord
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import asyncio
import os
import unicodedata
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("bot_eventos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# CONFIGURAÇÕES - Usar variável de ambiente
BOT_TOKEN = os.getenv("BOT_TOKEN")
CANAL_ID = int(os.getenv("CANAL_ID", "0"))  # ID do canal onde o bot vai responder

# Lista de cidades
cidades = ["Florianópolis", "Brusque", "Blumenau", "Balneário Camboriú", "Camboriú", "Itapema", "Porto Belo", "Itajaí"]

# Controle de execuções ativas: {user_id: asyncio.Event}
# O Event é usado como token de cancelamento — quando setado, sinaliza para parar
buscas_ativas: dict[int, asyncio.Event] = {}


def evento_key(nome: str, data: str) -> str:
    """Gera chave única para deduplicação de eventos."""
    nome_norm = unicodedata.normalize("NFD", nome.lower().strip())
    nome_norm = "".join(c for c in nome_norm if unicodedata.category(c) != "Mn")
    return f"{nome_norm}|{data.strip()}"


def normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    texto = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def extrair_cidade(texto: str) -> str:
    """Extrai nome da cidade de padrões como 'Local - Cidade/SC', 'Cidade, SC', 'Cidade - SC'."""
    for separador_uf in ["/SC", ", SC", " - SC"]:
        if separador_uf in texto:
            parte = texto.split(separador_uf)[0]
            if " - " in parte:
                return parte.rsplit(" - ", 1)[-1].strip()
            if ", " in parte:
                return parte.rsplit(", ", 1)[-1].strip()
            return parte.rsplit(" ", 1)[-1].strip()
    return ""


def cidade_match(texto: str, cidades_norm: dict) -> str | None:
    """Retorna o nome original da cidade se alguma aparecer no texto, ou None."""
    texto_norm = normalizar_texto(texto)
    for cn, c_orig in cidades_norm.items():
        if cn in texto_norm:
            return c_orig
    return None


# Configurar bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def parse_cidades(args: str) -> list[str]:
    """Parseia cidades informadas pelo usuário, separadas por ';'"""
    if not args or not args.strip():
        return []
    return [c.strip() for c in args.split(";") if c.strip()]

async def cancelavel_sleep(segundos: float, cancelar: asyncio.Event):
    """asyncio.sleep que respeita o token de cancelamento."""
    try:
        await asyncio.wait_for(cancelar.wait(), timeout=segundos)
    except asyncio.TimeoutError:
        pass  # Tempo esgotou normalmente, sem cancelamento


def criar_driver() -> webdriver.Chrome:
    """Cria e retorna uma instância do Chrome headless."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def resetar_driver(driver: webdriver.Chrome):
    """Reseta o estado do driver entre scrapers para evitar falhas em cascata."""
    try:
        driver.delete_all_cookies()
        driver.get("about:blank")
    except Exception as e:
        logger.warning(f"Erro ao resetar driver: {e}")


async def _scrape_blueticket_categoria(canal, cidade: str, categoria: str, driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos na Blueticket para uma cidade e categoria específica."""
    import urllib.parse
    import re

    url = f"https://www.blueticket.com.br/search?q={urllib.parse.quote(cidade)}&category={urllib.parse.quote(categoria)}"
    driver.get(url)

    # Aguardar cards ou mensagem de "nenhum resultado" (SPA Vue.js)
    try:
        WebDriverWait(driver, 10).until(lambda d:
            d.find_elements(By.CSS_SELECTOR, "a.event-card") or
            d.find_elements(By.XPATH, "//*[contains(text(),'Nenhuma experiência')]")
        )
    except Exception as e:
        logger.info(f"Blueticket: timeout aguardando cards em {cidade}/{categoria}: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a.event-card")
        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href  = card.get_attribute("href") or ""
                nome  = card.find_element(By.CSS_SELECTOR, ".event-title").text.strip()
                local = card.find_element(By.CSS_SELECTOR, ".event-location").text.strip()
                data  = card.find_element(By.CSS_SELECTOR, ".event-date").text.strip()
                hora  = card.find_element(By.CSS_SELECTOR, ".event-hour").text.strip()

                link_imagem = None
                try:
                    bg = card.find_element(By.CSS_SELECTOR, ".v-image__image").get_attribute("style")
                    match = re.search(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', bg)
                    if match:
                        link_imagem = match.group(1)
                except Exception:
                    pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                icone = "🪩"
                embed = discord.Embed(
                    title=f"{icone} {nome}",
                    description=f"**📅 Data:** {data} às {hora}\n**📍 Local:** {local}\n**🏷️ Categoria:** {categoria}",
                    color=0x1DA1F2,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="Blueticket")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"Blueticket: erro ao processar card em {cidade}/{categoria}: {e}")
                continue
    except Exception as e:
        logger.warning(f"Blueticket: erro geral ao buscar {cidade}/{categoria}: {e}")

    return total


async def buscar_blueticket(canal, cidade: str, driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos na Blueticket para uma cidade."""
    await canal.send(f"🔵 **Blueticket** em **{cidade}**")
    encontrados = await _scrape_blueticket_categoria(canal, cidade, "Baladas", driver, cancelar, eventos_enviados)
    if encontrados == 0 and not cancelar.is_set():
        await canal.send(f"⚠️ Nenhum evento encontrado na Blueticket para {cidade}")
    return encontrados


def cidade_para_slug(cidade: str) -> str:
    """Converte nome de cidade para slug usado pelo Guichê Web.
    Ex: 'Balneário Camboriú' → 'balneario-camboriu'
    """
    slug = unicodedata.normalize("NFD", cidade)
    slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")  # remove acentos
    slug = slug.lower().strip().replace(" ", "-")
    return slug


async def buscar_guicheweb(canal, cidade: str, driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Guichê Web para uma cidade via rota /pesquisa/{slug}."""
    slug = cidade_para_slug(cidade)
    url = f"https://www.guicheweb.com.br/pesquisa/{slug}"
    driver.get(url)

    try:
        WebDriverWait(driver, 8).until(lambda d:
            d.find_elements(By.CSS_SELECTOR, "a.text-reset .Card") or
            d.find_elements(By.XPATH, "//*[contains(text(),'NENHUM EVENTO')]")
        )
    except Exception as e:
        logger.info(f"GuicheWeb: timeout aguardando cards em {cidade}: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a.text-reset")
        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href   = card.get_attribute("href") or ""
                nome   = card.find_element(By.CSS_SELECTOR, "h6.Title").text.strip()
                cidade_card = card.find_element(By.CSS_SELECTOR, ".Cidade").text.strip()
                data   = card.find_element(By.CSS_SELECTOR, ".Data").text.strip()
                imagem = card.find_element(By.CSS_SELECTOR, "img.card-img-top").get_attribute("src")

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎟️ {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {cidade_card}",
                    color=0xE8431A,
                    url=href
                )
                if imagem:
                    embed.set_image(url=imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="Guichê Web")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"GuicheWeb: erro ao processar card em {cidade}: {e}")
                continue
    except Exception as e:
        logger.warning(f"GuicheWeb: erro geral ao buscar {cidade}: {e}")

    return total


async def buscar_pensanoevento(canal, cidade: str, driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Pensa no Evento para uma cidade via parâmetro &cidade=."""
    import urllib.parse

    def normalizar(texto: str) -> str:
        """Remove acentos e converte para minúsculas para comparação."""
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
        return texto.lower().strip()

    def cidade_do_local(local: str) -> str:
        """Extrai a cidade do campo local no formato 'Nome do Local - Cidade/UF'."""
        # Pega a parte após o último " - "
        if " - " in local:
            cidade_uf = local.rsplit(" - ", 1)[-1]  # ex: "Blumenau/SC"
            return cidade_uf.split("/")[0].strip()   # ex: "Blumenau"
        return local

    # Mapa de normalização: nome usado no bot → data-name exato do site
    MAPA_CIDADES = {
        "brusque": "Brusque",
        "blumenau": "Blumenau",
        "balneário camboriú": "Balneário Camboriú",
        "balneario camboriu": "Balneário Camboriú",
        "camboriú": "Camboriú",
        "camboriu": "Camboriú",
        "itapema": "Itapema",
        "portobelo": "Porto Belo",  # não existe no site
        "itajaí": "Itajaí",
        "itajai": "Itajaí",
        "florianópolis": "Florianópolis",
        "florianopolis": "Florianópolis",
        "joinville": "Joinville",
        "jaraguá do sul": "Jaraguá do Sul",
        "jaragua do sul": "Jaraguá do Sul",
        "navegantes": "Navegantes",
        "penha": "Penha",
        "gaspar": "Gaspar",
        "biguaçu": "Biguaçu",
        "biguacu": "Biguaçu",
        "palhoça": "Palhoça",
        "palhoca": "Palhoça",
        "são josé": "São José",
        "sao jose": "São José",
        "criciúma": "Criciúma",
        "criciuma": "Criciúma",
        "laguna": "Laguna",
        "imbituba": "Imbituba",
        "tubarão": "Tubarão",
        "tubarao": "Tubarão",
    }

    cidade_normalizada = MAPA_CIDADES.get(cidade.lower().strip())
    if cidade_normalizada is None:
        cidade_normalizada = cidade.strip()

    # Versão normalizada da cidade buscada para validação
    cidade_busca_norm = normalizar(cidade_normalizada)

    cidade_encoded = urllib.parse.quote(cidade_normalizada)
    url = f"https://www.pensanoevento.com.br/sitev2/eventos/busca?tipo=Baladas&cidade={cidade_encoded}"
    driver.get(url)

    try:
        WebDriverWait(driver, 10).until(lambda d:
            d.find_elements(By.CSS_SELECTOR, "a.hotelsCard") or
            d.find_elements(By.XPATH, "//*[contains(text(),'Nenhum evento')]")
        )
    except Exception as e:
        logger.info(f"PensaNoEvento: timeout aguardando cards em {cidade}: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    ignorados = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a.hotelsCard")
        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href  = card.get_attribute("href") or ""
                nome  = card.find_element(By.CSS_SELECTOR, "h4 span").text.strip()
                data  = card.find_element(By.CSS_SELECTOR, ".text-14.text-light-1").text.strip()
                local = card.find_element(By.CSS_SELECTOR, "p.text-light-1").text.strip()
                imagem = card.find_element(By.CSS_SELECTOR, "img").get_attribute("src")

                cidade_evento = cidade_do_local(local)
                if normalizar(cidade_evento) != cidade_busca_norm:
                    ignorados += 1
                    continue

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎉 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {local}",
                    color=0xFF6B35,
                    url=href
                )
                if imagem:
                    embed.set_image(url=imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="Pensa no Evento")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"PensaNoEvento: erro ao processar card em {cidade}: {e}")
                continue

    except Exception as e:
        logger.warning(f"PensaNoEvento: erro geral ao buscar {cidade}: {e}")

    return total


async def buscar_ingressonacional(canal, cidade: str, driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Ingresso Nacional para uma cidade.
    Navega para /balada a cada cidade para evitar StaleElementReferenceException.
    Usa CSS selectors relativos em vez de XPaths absolutos.
    """
    driver.get("https://www.ingressonacional.com.br/balada")
    await cancelavel_sleep(3, cancelar)
    if cancelar.is_set():
        return 0

    try:
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "form input[type='text'], form input[type='search'], form input")
            )
        )
    except Exception as e:
        logger.warning(f"Ingresso Nacional: campo de busca não encontrado para {cidade}: {e}")
        return 0

    search_box.clear()
    search_box.send_keys(cidade)
    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return 0
    search_box.send_keys(Keys.RETURN)
    await cancelavel_sleep(3, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    try:
        WebDriverWait(driver, 8).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/evento'], [class*='event']")
                      or d.find_elements(By.TAG_NAME, "h2")
        )
    except Exception:
        logger.info(f"Ingresso Nacional: timeout aguardando cards em {cidade}")
        return 0

    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/evento']")
        if not cards:
            for sel in [".events-list > div", "[class*='event'] > div", ".row > div[class*='col']"]:
                cards = driver.find_elements(By.CSS_SELECTOR, sel)
                if cards:
                    break
        if not cards:
            cards = driver.find_elements(By.XPATH, "//div[.//h2 and .//img]")

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                nome = ""
                for tag in ["h2", "h3", "h4", ".event-name", ".event-title"]:
                    try:
                        nome = card.find_element(By.CSS_SELECTOR, tag).text.strip()
                        if nome:
                            break
                    except Exception:
                        continue
                if not nome:
                    continue

                data = ""
                for sel in ["span", ".event-date", ".date", "time"]:
                    try:
                        data = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if data:
                            break
                    except Exception:
                        continue

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except Exception:
                    pass

                link = None
                try:
                    link = card.find_element(By.CSS_SELECTOR, "a[href*='/evento']").get_attribute("href")
                except Exception:
                    try:
                        link = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    except Exception:
                        try:
                            link = card.get_attribute("href")
                        except Exception:
                            pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎭 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {cidade}",
                    color=0x5865F2,
                    url=link or ""
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                if link:
                    embed.add_field(name="🔗 Link", value=link, inline=False)
                embed.set_footer(text="Ingresso Nacional")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(1, cancelar)

            except Exception as e:
                logger.warning(f"Ingresso Nacional: erro ao processar card em {cidade}: {e}")
                continue

    except Exception as e:
        logger.warning(f"Ingresso Nacional: erro ao buscar eventos em {cidade}: {e}")

    return total


async def buscar_minhaentrada(canal, cidades_busca: list[str], driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Minha Entrada (Baladas e Festas), filtrando por cidades SC."""
    await canal.send("🟢 **Minha Entrada**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    total = 0
    categorias = [("2", "Baladas"), ("6", "Festas")]

    for cat_id, cat_nome in categorias:
        if cancelar.is_set():
            return total

        url = f"https://www.minhaentrada.com.br/agenda-geral?categoria={cat_id}"
        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/evento/']")
                          or d.find_elements(By.XPATH, "//*[contains(text(),'Nenhum evento')]")
            )
        except Exception as e:
            logger.info(f"MinhaEntrada: timeout aguardando cards ({cat_nome}): {e}")
            continue

        await cancelavel_sleep(1, cancelar)
        if cancelar.is_set():
            return total

        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/evento/']")

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href = card.get_attribute("href") or ""
                if not href or "/evento/" not in href:
                    continue

                card_text = card.text.strip()
                if not card_text:
                    continue

                cidade_encontrada = cidade_match(card_text, cidades_norm)
                if not cidade_encontrada:
                    continue

                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                if len(lines) < 2:
                    continue

                nome = ""
                try:
                    nome = card.find_element(By.TAG_NAME, "h4").text.strip()
                except Exception:
                    nome = lines[0]
                if not nome:
                    continue

                data = lines[1] if len(lines) > 1 else ""
                local = lines[-1] if len(lines) > 2 else ""

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except Exception:
                    pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                if href.startswith("/"):
                    href = f"https://www.minhaentrada.com.br{href}"

                embed = discord.Embed(
                    title=f"🎫 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {local}\n**🏷️ Categoria:** {cat_nome}",
                    color=0x00BFA5,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="Minha Entrada")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"MinhaEntrada: erro ao processar card ({cat_nome}): {e}")
                continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no Minha Entrada para as cidades selecionadas")
    return total


async def buscar_bilheteriadigital(canal, cidades_busca: list[str], driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos na Bilheteria Digital para SC, filtrando por cidades."""
    await canal.send("🟣 **Bilheteria Digital**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}

    driver.get("https://www.bilheteriadigital.com/SC")

    try:
        WebDriverWait(driver, 12).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href]") and len(d.find_elements(By.CSS_SELECTOR, "a[href]")) > 5
        )
    except Exception as e:
        logger.info(f"BilheteriaDigital: timeout aguardando cards SC: {e}")
        return 0

    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    MESES = ["janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

    all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    cards = []
    for link in all_links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if (href.startswith("https://www.bilheteriadigital.com/")
            and href != "https://www.bilheteriadigital.com/SC"
            and href != "https://www.bilheteriadigital.com/"
            and text
            and len(text) > 10
            and " - SC" in text.upper()):
            cards.append(link)

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            href = card.get_attribute("href") or ""
            card_text = card.text.strip()
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            nome = lines[0]
            data = ""
            cidade_texto = ""
            local = ""

            for line in lines[1:]:
                line_lower = line.lower()
                if any(m in line_lower for m in MESES) and not data:
                    data = line
                elif " - SC" in line.upper():
                    cidade_texto = line
                elif not local:
                    local = line

            cidade_evento = extrair_cidade(cidade_texto) if cidade_texto else ""
            if not cidade_evento or normalizar_texto(cidade_evento) not in cidades_norm:
                continue

            link_imagem = None
            try:
                link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
            except Exception:
                pass

            key = evento_key(nome, data)
            if key in eventos_enviados:
                continue
            eventos_enviados.add(key)

            embed = discord.Embed(
                title=f"🎫 {nome}",
                description=f"**📅 Data:** {data}\n**📍 Local:** {local}\n**🏙️ Cidade:** {cidade_texto}",
                color=0x6C3BF5,
                url=href
            )
            if link_imagem:
                embed.set_image(url=link_imagem)
            embed.add_field(name="🔗 Link", value=href, inline=False)
            embed.set_footer(text="Bilheteria Digital")

            await canal.send(embed=embed)
            total += 1
            await cancelavel_sleep(0.5, cancelar)

        except Exception as e:
            logger.warning(f"BilheteriaDigital: erro ao processar card: {e}")
            continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado na Bilheteria Digital para as cidades selecionadas")
    return total


async def buscar_aquitemingressos(canal, cidades_busca: list[str], driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Aqui Tem Ingressos, filtrando por cidades SC."""
    await canal.send("🟡 **Aqui Tem Ingressos**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}

    driver.get("https://www.aquitemingressos.com.br/eventos")

    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='__']")
                      or d.find_elements(By.TAG_NAME, "h4")
        )
    except Exception as e:
        logger.info(f"AquiTemIngressos: timeout aguardando cards: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    links_processados: set = set()

    cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='__']")

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            href = card.get_attribute("href") or ""
            if not href or href in links_processados:
                continue
            links_processados.add(href)

            nome = ""
            try:
                nome = card.find_element(By.TAG_NAME, "h4").text.strip()
            except Exception:
                text = card.text.strip()
                nome = text.split("\n")[0] if text else ""
            if not nome:
                continue

            link_imagem = None
            try:
                link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
            except Exception:
                pass

            data = ""
            local = ""
            try:
                parent = card.find_element(By.XPATH, "./..")
                parent_text = parent.text.strip()
                lines = [l.strip() for l in parent_text.split("\n") if l.strip()]

                for line in lines:
                    if line == nome:
                        continue
                    line_lower = line.lower()
                    if any(d in line_lower for d in ["seg,", "ter,", "qua,", "qui,", "sex,", "sáb,", "sab,", "dom,"]) and not data:
                        data = line
                    elif ("SC" in line or "sc" in line.split(",")[-1].strip() if "," in line else False) and not local:
                        local = line
                    elif " - " in line and not local:
                        local = line
            except Exception:
                pass

            cidade_evento = extrair_cidade(local)
            if cidade_evento and normalizar_texto(cidade_evento) in cidades_norm:
                pass
            elif cidade_match(f"{nome} {local} {data}", cidades_norm):
                pass
            else:
                continue

            key = evento_key(nome, data)
            if key in eventos_enviados:
                continue
            eventos_enviados.add(key)

            if href.startswith("/"):
                href = f"https://www.aquitemingressos.com.br{href}"

            embed = discord.Embed(
                title=f"🎫 {nome}",
                description=f"**📅 Data:** {data}\n**📍 Local:** {local}",
                color=0xF5A623,
                url=href
            )
            if link_imagem:
                embed.set_image(url=link_imagem)
            embed.add_field(name="🔗 Link", value=href, inline=False)
            embed.set_footer(text="Aqui Tem Ingressos")

            await canal.send(embed=embed)
            total += 1
            await cancelavel_sleep(0.5, cancelar)

        except Exception as e:
            logger.warning(f"AquiTemIngressos: erro ao processar card: {e}")
            continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no Aqui Tem Ingressos para as cidades selecionadas")
    return total


async def buscar_ingressodigital(canal, cidades_busca: list[str], driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no Ingresso Digital para SC com paginação, filtrando por cidades."""
    await canal.send("🔷 **Ingresso Digital**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}

    total = 0
    pg = 1
    max_paginas = 5

    while pg <= max_paginas:
        if cancelar.is_set():
            return total

        url = f"https://www.ingressodigital.com/pesquisa.php?busca=S&pg={pg}&txt_estado=SC"
        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/evento/']")
                          or d.find_elements(By.XPATH, "//*[contains(text(),'nenhum resultado') or contains(text(),'Nenhum evento')]")
            )
        except Exception as e:
            logger.info(f"IngressoDigital: timeout na página {pg}: {e}")
            break

        await cancelavel_sleep(1, cancelar)
        if cancelar.is_set():
            return total

        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/evento/']")
        if not cards:
            break

        encontrou_nesta_pagina = False

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href = card.get_attribute("href") or ""
                if not href:
                    continue

                card_text = card.text.strip()
                if not card_text:
                    try:
                        parent = card.find_element(By.XPATH, "./..")
                        card_text = parent.text.strip()
                    except Exception:
                        continue
                if not card_text or len(card_text) < 5:
                    continue

                nome = ""
                try:
                    nome = card.find_element(By.CSS_SELECTOR, "h3, h4, h2").text.strip()
                except Exception:
                    lines = card_text.split("\n")
                    nome = lines[0].strip() if lines else ""
                if not nome:
                    continue

                cidade_encontrada = cidade_match(card_text, cidades_norm)
                if not cidade_encontrada:
                    continue

                encontrou_nesta_pagina = True

                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                data = ""
                local = ""
                MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
                for line in lines:
                    if line == nome:
                        continue
                    if any(m in line.lower() for m in MESES_PT) and not data:
                        data = line
                    elif ("SC" in line or "sc" in line) and not local:
                        local = line

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except Exception:
                    pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                if href.startswith("/"):
                    href = f"https://www.ingressodigital.com{href}"

                embed = discord.Embed(
                    title=f"🎟️ {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {local}",
                    color=0x2196F3,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="Ingresso Digital")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"IngressoDigital: erro ao processar card (pg {pg}): {e}")
                continue

        if not encontrou_nesta_pagina and not cards:
            break
        pg += 1

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no Ingresso Digital para as cidades selecionadas")
    return total


async def buscar_eticketcenter(canal, cidades_busca: list[str], driver: webdriver.Chrome, cancelar: asyncio.Event, eventos_enviados: set) -> int:
    """Busca eventos no eTicket Center (Festa, Show, Festival), filtrando por cidades SC."""
    await canal.send("🩷 **eTicket Center**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}

    total = 0
    categorias_url = [
        ("https://www.eticketcenter.com.br/eventos/festa/", "Festa"),
        ("https://www.eticketcenter.com.br/eventos/show/", "Show"),
        ("https://www.eticketcenter.com.br/eventos/festival/", "Festival"),
    ]

    for url_cat, cat_nome in categorias_url:
        if cancelar.is_set():
            return total

        driver.get(url_cat)

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/eventos/']")
                          or d.find_elements(By.XPATH, "//*[contains(text(),'Não Localizamos')]")
            )
        except Exception as e:
            logger.info(f"eTicketCenter: timeout aguardando cards ({cat_nome}): {e}")
            continue

        await cancelavel_sleep(1, cancelar)
        if cancelar.is_set():
            return total

        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/eventos/']")
        cards = [l for l in all_links if l.get_attribute("href") and l.get_attribute("href").count("/") > 5]

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href = card.get_attribute("href") or ""
                card_text = card.text.strip()
                if not card_text:
                    try:
                        parent = card.find_element(By.XPATH, "./..")
                        card_text = parent.text.strip()
                    except Exception:
                        continue
                if not card_text or len(card_text) < 5:
                    continue

                cidade_encontrada = cidade_match(card_text, cidades_norm)
                if not cidade_encontrada:
                    continue

                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                if not lines:
                    continue

                nome = lines[0]
                data = ""
                local = ""

                for line in lines[1:]:
                    if ("/" in line and any(c.isdigit() for c in line) and len(line) < 20) and not data:
                        data = line
                    elif ("/SC" in line or "/sc" in line) and not local:
                        local = line
                    elif not local and line != nome:
                        local = line

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except Exception:
                    pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎫 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {local}\n**🏷️ Categoria:** {cat_nome}",
                    color=0xE91E63,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=href, inline=False)
                embed.set_footer(text="eTicket Center")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"eTicketCenter: erro ao processar card ({cat_nome}): {e}")
                continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no eTicket Center para as cidades selecionadas")
    return total


async def buscar_eventos(canal, cidades_busca: list[str] = None, cancelar: asyncio.Event = None):
    """Função que executa a automação do Selenium com suporte a cancelamento."""
    lista = cidades_busca if cidades_busca else cidades
    eventos_enviados: set = set()

    await canal.send("🔍 Iniciando busca de eventos...")

    driver = criar_driver()

    try:
        total_eventos = 0

        # ── Ingresso Nacional ──────────────────────────────────────────────
        await canal.send("🎟️ **Ingresso Nacional**")
        for cidade in lista:
            if cancelar.is_set():
                return
            await canal.send(f"📍 Pesquisando em: **{cidade}**")
            in_total = await buscar_ingressonacional(canal, cidade, driver, cancelar, eventos_enviados)
            if in_total == 0 and not cancelar.is_set():
                await canal.send(f"⚠️ Nenhum evento encontrado no Ingresso Nacional para {cidade}")
            total_eventos += in_total

        # ── Blueticket + Guichê Web + Pensa no Evento ─────────────────────
        if not cancelar.is_set():
            for cidade in lista:
                if cancelar.is_set():
                    return

                resetar_driver(driver)
                bt_total = await buscar_blueticket(canal, cidade, driver, cancelar, eventos_enviados)
                total_eventos += bt_total

                if cancelar.is_set():
                    return
                resetar_driver(driver)
                await canal.send(f"🟠 **Guichê Web** em **{cidade}**")
                gw_total = await buscar_guicheweb(canal, cidade, driver, cancelar, eventos_enviados)
                if gw_total == 0 and not cancelar.is_set():
                    await canal.send(f"⚠️ Nenhum evento encontrado no Guichê Web para {cidade}")
                total_eventos += gw_total

                if cancelar.is_set():
                    return
                resetar_driver(driver)
                await canal.send(f"🎉 **Pensa no Evento** em **{cidade}**")
                pe_total = await buscar_pensanoevento(canal, cidade, driver, cancelar, eventos_enviados)
                if pe_total == 0 and not cancelar.is_set():
                    await canal.send(f"⚠️ Nenhum evento encontrado no Pensa no Evento para {cidade}")
                total_eventos += pe_total

        # ── Novos sites (busca SC inteira, filtra por cidade) ─────────
        if not cancelar.is_set():
            resetar_driver(driver)
            me_total = await buscar_minhaentrada(canal, lista, driver, cancelar, eventos_enviados)
            total_eventos += me_total

        if not cancelar.is_set():
            resetar_driver(driver)
            bd_total = await buscar_bilheteriadigital(canal, lista, driver, cancelar, eventos_enviados)
            total_eventos += bd_total

        if not cancelar.is_set():
            resetar_driver(driver)
            ati_total = await buscar_aquitemingressos(canal, lista, driver, cancelar, eventos_enviados)
            total_eventos += ati_total

        if not cancelar.is_set():
            resetar_driver(driver)
            id_total = await buscar_ingressodigital(canal, lista, driver, cancelar, eventos_enviados)
            total_eventos += id_total

        if not cancelar.is_set():
            resetar_driver(driver)
            etc_total = await buscar_eticketcenter(canal, lista, driver, cancelar, eventos_enviados)
            total_eventos += etc_total

        await canal.send(f"✅ Busca concluída! Total de eventos encontrados: **{total_eventos}**")

    except Exception as e:
        logger.error(f"Erro na automação: {e}")
        await canal.send(f"❌ Erro na automação: {str(e)}")
    finally:
        driver.quit()

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'ID: {bot.user.id}')
    print('------')

@bot.command(name='buscar')
async def buscar(ctx, *, args: str = None):
    """Comando para iniciar a busca de eventos.
    
    Uso:
      !buscar                    → cidades padrão
      !buscar Blumenau           → cidade específica
      !buscar Blumenau;Itajaí    → múltiplas cidades
    """
    if CANAL_ID and ctx.channel.id != CANAL_ID:
        await ctx.send("⚠️ Este comando só pode ser usado no canal designado.")
        return

    user_id = ctx.author.id

    if user_id in buscas_ativas:
        await ctx.send("⚠️ Você já tem uma busca em andamento. Use `!parar` para cancelá-la antes de iniciar outra.")
        return

    cidades_busca = parse_cidades(args)

    if cidades_busca:
        await ctx.send(f"🚀 Buscando eventos em: **{', '.join(cidades_busca)}**")
    else:
        await ctx.send("🚀 Buscando eventos nas cidades padrão...")

    cancelar = asyncio.Event()
    buscas_ativas[user_id] = cancelar

    try:
        await buscar_eventos(ctx.channel, cidades_busca or None, cancelar)
    finally:
        buscas_ativas.pop(user_id, None)

    if cancelar.is_set():
        await ctx.send("🛑 Busca cancelada pelo usuário.")


@bot.command(name='parar', aliases=['cancelar'])
async def parar(ctx):
    """Cancela a busca em andamento do usuário."""
    user_id = ctx.author.id

    if user_id not in buscas_ativas:
        await ctx.send("ℹ️ Você não tem nenhuma busca em andamento.")
        return

    buscas_ativas[user_id].set()  # Sinaliza o cancelamento
    await ctx.send("🛑 Cancelamento solicitado. Aguarde a operação ser interrompida...")

@bot.command(name='eventos')
async def eventos(ctx, *, args: str = None):
    """Alias para o comando buscar"""
    await buscar(ctx, args=args)

@bot.command(name='ajuda')
async def ajuda(ctx):
    """Mostra os comandos disponíveis"""
    embed = discord.Embed(
        title="📋 Comandos Disponíveis",
        description="Lista de comandos do bot de eventos",
        color=0x00ff00
    )
    embed.add_field(name="!buscar", value="Busca eventos nas cidades padrão", inline=False)
    embed.add_field(name="!buscar <cidade>", value="Busca em uma cidade específica\nEx: `!buscar Florianópolis`", inline=False)
    embed.add_field(name="!buscar <cidade1>;<cidade2>", value="Busca em múltiplas cidades\nEx: `!buscar Blumenau;Itajaí`", inline=False)
    embed.add_field(name="!eventos", value="Mesmo que !buscar", inline=False)
    embed.add_field(name="!parar", value="Cancela a busca em andamento (também: `!cancelar`)", inline=False)
    embed.add_field(name="!ajuda", value="Mostra esta mensagem", inline=False)
    await ctx.send(embed=embed)

# Iniciar bot
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Configure o BOT_TOKEN no arquivo .env antes de executar!")
        print("💡 Copie o .env.example para .env e adicione suas credenciais")
    elif CANAL_ID == 0:
        print("⚠️ CANAL_ID não configurado no .env, mas o bot vai iniciar")
        bot.run(BOT_TOKEN)
    else:
        bot.run(BOT_TOKEN)
