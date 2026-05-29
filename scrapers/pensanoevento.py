import unicodedata
import urllib.parse

import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, cancelavel_sleep


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
        return cidade_uf.split("/")[0].strip()
    return local


async def buscar_pensanoevento(canal, cidade, driver, cancelar, eventos_enviados):
    cidade_normalizada = MAPA_CIDADES.get(cidade.lower().strip())
    if cidade_normalizada is None:
        cidade_normalizada = cidade.strip()

    cidade_busca_norm = _normalizar(cidade_normalizada)
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

                cidade_evento = _cidade_do_local(local)
                if _normalizar(cidade_evento) != cidade_busca_norm:
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
                embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
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
