import unicodedata
import urllib.parse

import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, cancelavel_sleep, titulo_bloqueado


# Categorias de evento pesquisadas no Pensa no Evento (ignoramos "Gastronomia").
# O site classifica muitas baladas/festas em "Eventos" (ex: Arraiá do Hike) e
# shows em "Shows", então buscar só "Baladas" perde bastante coisa.
TIPOS = ["Baladas", "Shows", "Eventos"]


MAPA_CIDADES = {
    "brusque": "Brusque",
    "blumenau": "Blumenau",
    "balneário camboriú": "Balneário Camboriú",
    "balneario camboriu": "Balneário Camboriú",
    "camboriú": "Camboriú",
    "camboriu": "Camboriú",
    "itapema": "Itapema",
    "portobelo": "Porto Belo",
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


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _cidade_do_local(local):
    if " - " in local:
        cidade_uf = local.rsplit(" - ", 1)[-1]
    else:
        cidade_uf = local
    return cidade_uf.split("/")[0].split(",")[0].strip()


async def _scrape_pensanoevento_tipo(canal, cidade_encoded, cidade_busca_norm, tipo,
                                     driver, cancelar, eventos_enviados):
    url = f"https://www.pensanoevento.com.br/sitev2/eventos/busca?tipo={tipo}&cidade={cidade_encoded}"
    driver.get(url)

    try:
        WebDriverWait(driver, 10).until(lambda d:
            d.find_elements(By.CSS_SELECTOR, "a.hotelsCard") or
            d.find_elements(By.XPATH, "//*[contains(text(),'Nenhum evento')]")
        )
    except Exception as e:
        logger.info(f"PensaNoEvento: timeout aguardando cards ({tipo}): {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a.hotelsCard")
        for card in cards:
            if cancelar.is_set():
                return total
            try:
                href  = card.get_attribute("href") or ""
                nome  = card.find_element(By.CSS_SELECTOR, "h4 span").text.strip()
                if titulo_bloqueado(nome):
                    continue
                data  = card.find_element(By.CSS_SELECTOR, ".text-14.text-light-1").text.strip()
                local = card.find_element(By.CSS_SELECTOR, "p.text-light-1").text.strip()
                imagem = card.find_element(By.CSS_SELECTOR, "img").get_attribute("src")

                cidade_evento = _cidade_do_local(local)
                if _normalizar(cidade_evento) != cidade_busca_norm:
                    continue

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎉 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {local}\n**🏷️ Categoria:** {tipo}",
                    color=0xFF6B35,
                    url=href
                )
                if imagem:
                    embed.set_image(url=imagem)
                embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
                embed.set_footer(text="Pensa no Evento")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"PensaNoEvento: erro ao processar card ({tipo}): {e}")
                continue

    except Exception as e:
        logger.warning(f"PensaNoEvento: erro geral ({tipo}): {e}")

    return total


async def buscar_pensanoevento(canal, cidade, driver, cancelar, eventos_enviados):
    cidade_normalizada = MAPA_CIDADES.get(cidade.lower().strip())
    if cidade_normalizada is None:
        cidade_normalizada = cidade.strip()

    cidade_busca_norm = _normalizar(cidade_normalizada)
    cidade_encoded = urllib.parse.quote(cidade_normalizada)

    total = 0
    for tipo in TIPOS:
        if cancelar.is_set():
            return total
        total += await _scrape_pensanoevento_tipo(
            canal, cidade_encoded, cidade_busca_norm, tipo,
            driver, cancelar, eventos_enviados
        )

    return total
