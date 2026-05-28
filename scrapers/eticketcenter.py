import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, cidade_match, cancelavel_sleep

CATEGORIAS_URL = [
    ("https://www.eticketcenter.com.br/eventos/festa/", "Festa"),
    ("https://www.eticketcenter.com.br/eventos/show/", "Show"),
    ("https://www.eticketcenter.com.br/eventos/festival/", "Festival"),
]


async def buscar_eticketcenter(canal, cidades_busca, driver, cancelar, eventos_enviados):
    await canal.send("🩷 **eTicket Center**")

    from .helpers import normalizar_texto
    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    total = 0

    for url_cat, cat_nome in CATEGORIAS_URL:
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
