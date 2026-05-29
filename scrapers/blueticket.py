import re
import urllib.parse

import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, cancelavel_sleep


async def _scrape_blueticket_categoria(canal, cidade, categoria, driver, cancelar, eventos_enviados):
    url = f"https://www.blueticket.com.br/search?q={urllib.parse.quote(cidade)}&category={urllib.parse.quote(categoria)}"
    driver.get(url)

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
                if not href:
                    continue
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

                embed = discord.Embed(
                    title=f"🪩 {nome}",
                    description=f"**📅 Data:** {data} às {hora}\n**📍 Local:** {local}\n**🏷️ Categoria:** {categoria}",
                    color=0x1DA1F2,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
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


async def buscar_blueticket(canal, cidade, driver, cancelar, eventos_enviados):
    await canal.send(f"🔵 **Blueticket** em **{cidade}**")
    encontrados = await _scrape_blueticket_categoria(canal, cidade, "Baladas", driver, cancelar, eventos_enviados)
    if encontrados == 0 and not cancelar.is_set():
        await canal.send(f"⚠️ Nenhum evento encontrado na Blueticket para {cidade}")
    return encontrados
