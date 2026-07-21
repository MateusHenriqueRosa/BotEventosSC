import asyncio
import logging
import re
import unicodedata

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger("bot_eventos")


def evento_key(nome: str, data: str) -> str:
    nome_norm = unicodedata.normalize("NFD", nome.lower().strip())
    nome_norm = "".join(c for c in nome_norm if unicodedata.category(c) != "Mn")
    return f"{nome_norm}|{data.strip()}"


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# Categorias de evento que NÃO interessam (stand-up, teatro, fisiculturismo).
# O regex é aplicado sobre o texto normalizado (minúsculo, sem acento) e casa
# apenas com o TÍTULO do evento — nunca com o local/venue.
PADRAO_TITULO_BLOQUEADO = re.compile(
    r"\bstand[\s\-]?up\b"        # stand up, stand-up, standup
    r"|\bteatr\w*"               # teatro, teatral, teatros
    r"|\bfisicultur\w*"          # fisiculturismo, fisiculturista(s)
    r"|\bbody\s?build\w*"        # bodybuilder, bodybuilding, body building
)


def titulo_bloqueado(titulo: str) -> bool:
    """True se o TÍTULO do evento contém categoria indesejada (stand-up,
    teatro, fisiculturismo/bodybuilder). Use só no nome do evento."""
    if not titulo:
        return False
    return bool(PADRAO_TITULO_BLOQUEADO.search(normalizar_texto(titulo)))


def extrair_cidade(texto: str) -> str:
    for separador_uf in ["/SC", ", SC", " - SC"]:
        if separador_uf in texto:
            parte = texto.split(separador_uf)[0]
            if " - " in parte:
                return parte.rsplit(" - ", 1)[-1].strip()
            if ", " in parte:
                return parte.rsplit(", ", 1)[-1].strip()
            return parte.strip()
    return ""


def cidade_match(texto: str, cidades_norm: dict) -> str | None:
    texto_norm = normalizar_texto(texto)
    for cn, c_orig in sorted(cidades_norm.items(), key=lambda x: len(x[0]), reverse=True):
        if cn in texto_norm:
            return c_orig
    return None


async def cancelavel_sleep(segundos: float, cancelar: asyncio.Event):
    try:
        await asyncio.wait_for(cancelar.wait(), timeout=segundos)
    except asyncio.TimeoutError:
        pass


def criar_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def resetar_driver(driver: webdriver.Chrome):
    try:
        driver.delete_all_cookies()
        driver.get("about:blank")
    except Exception as e:
        logger.warning(f"Erro ao resetar driver: {e}")
