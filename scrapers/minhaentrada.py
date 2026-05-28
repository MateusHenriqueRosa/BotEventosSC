import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cidade_match, cancelavel_sleep


async def buscar_minhaentrada(canal, cidades_busca, driver, cancelar, eventos_enviados):
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
