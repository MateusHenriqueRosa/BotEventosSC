import unicodedata

import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, cancelavel_sleep


def cidade_para_slug(cidade):
    slug = unicodedata.normalize("NFD", cidade)
    slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")
    slug = slug.lower().strip().replace(" ", "-")
    return slug


async def buscar_guicheweb(canal, cidade, driver, cancelar, eventos_enviados):
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
                embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
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
