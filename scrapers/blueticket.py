import re
import urllib.parse

import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cancelavel_sleep

BASE_URL = "https://www.blueticket.com.br"

CATEGORIAS = ["Baladas", "Festivais", "Shows Nacionais"]


async def _scrape_blueticket_categoria(canal, cidade, cidade_norm, categoria, driver, cancelar, eventos_enviados):
    cidade_param = urllib.parse.quote(f"{cidade}, SC")
    cat_param = urllib.parse.quote(categoria)
    url = f"{BASE_URL}/search?q=&category={cat_param}&city={cidade_param}"
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
                href = card.get_attribute("href") or ""
                if not href:
                    continue
                if href.startswith("/"):
                    href = f"{BASE_URL}{href}"

                nome = ""
                try:
                    nome = card.find_element(By.CSS_SELECTOR, ".event-title").text.strip()
                except Exception:
                    pass
                if not nome:
                    continue

                local = ""
                try:
                    local = card.find_element(By.CSS_SELECTOR, ".event-location").text.strip()
                except Exception:
                    pass

                cidade_evento = ""
                try:
                    cidade_evento = card.find_element(By.CSS_SELECTOR, ".event-city").text.strip()
                except Exception:
                    pass

                # Filtrar: só aceitar eventos da cidade buscada
                if cidade_evento:
                    # ".event-city" vem como "Florianópolis • SC" — extrair só o nome
                    cidade_card = cidade_evento.split("•")[0].strip()
                    if normalizar_texto(cidade_card) != cidade_norm:
                        continue
                else:
                    # Sem info de cidade, pular o card
                    continue

                data = ""
                try:
                    data = card.find_element(By.CSS_SELECTOR, ".event-date").text.strip()
                except Exception:
                    pass

                hora = ""
                try:
                    hora = card.find_element(By.CSS_SELECTOR, ".event-hour").text.strip()
                except Exception:
                    pass

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

                data_display = f"{data} às {hora}" if hora else data
                local_display = f"{local} — {cidade_evento}" if cidade_evento else local

                embed = discord.Embed(
                    title=f"🪩 {nome}",
                    description=f"**📅 Data:** {data_display}\n**📍 Local:** {local_display}\n**🏷️ Categoria:** {categoria}",
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
    cidade_norm = normalizar_texto(cidade)
    total = 0

    for categoria in CATEGORIAS:
        if cancelar.is_set():
            return total
        n = await _scrape_blueticket_categoria(canal, cidade, cidade_norm, categoria, driver, cancelar, eventos_enviados)
        total += n

    if total == 0 and not cancelar.is_set():
        await canal.send(f"⚠️ Nenhum evento encontrado na Blueticket para {cidade}")
    return total
