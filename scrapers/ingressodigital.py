import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cidade_match, cancelavel_sleep

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


async def buscar_ingressodigital(canal, cidades_busca, driver, cancelar, eventos_enviados):
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
