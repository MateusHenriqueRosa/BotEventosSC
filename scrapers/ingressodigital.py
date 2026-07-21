import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cidade_match, cancelavel_sleep, titulo_bloqueado

CATEGORIAS_ACEITAS = {"show", "festival", "festa", "balada"}


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
                lambda d: d.find_elements(By.CSS_SELECTOR, "div.card-evento")
                          or d.find_elements(By.XPATH, "//*[contains(text(),'nenhum resultado') or contains(text(),'Nenhum evento')]")
            )
        except Exception as e:
            logger.info(f"IngressoDigital: timeout na página {pg}: {e}")
            break

        await cancelavel_sleep(1, cancelar)
        if cancelar.is_set():
            return total

        cards = driver.find_elements(By.CSS_SELECTOR, "div.card-evento")
        if not cards:
            break

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                categoria = ""
                try:
                    categoria = card.find_element(By.CSS_SELECTOR, ".genero-evento-card").text.strip()
                except Exception:
                    pass

                if categoria and categoria.lower() not in CATEGORIAS_ACEITAS:
                    continue

                link_el = card.find_element(By.CSS_SELECTOR, "a[href*='/evento/']")
                href = link_el.get_attribute("href") or ""
                if not href:
                    continue

                nome = ""
                try:
                    nome = card.find_element(By.CSS_SELECTOR, "h3.titulo-card").text.strip()
                except Exception:
                    pass
                if not nome:
                    continue
                if titulo_bloqueado(nome):
                    continue

                card_text = card.text.strip()
                cidade_encontrada = cidade_match(card_text, cidades_norm)
                if not cidade_encontrada:
                    continue

                data = ""
                try:
                    data = card.find_element(By.CSS_SELECTOR, "p.data-evento").text.strip()
                except Exception:
                    pass

                local = ""
                try:
                    ps = card.find_elements(By.CSS_SELECTOR, ".area-cont-card p")
                    for p in ps:
                        txt = p.text.strip()
                        if txt and txt != data:
                            local = txt
                            break
                except Exception:
                    pass

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.CSS_SELECTOR, "img.card-evento-img").get_attribute("src")
                except Exception:
                    pass

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                desc_parts = [f"**📅 Data:** {data}"]
                if local:
                    desc_parts.append(f"**📍 Local:** {local}")
                if categoria:
                    desc_parts.append(f"**🏷️ Categoria:** {categoria}")

                embed = discord.Embed(
                    title=f"🎟️ {nome}",
                    description="\n".join(desc_parts),
                    color=0x2196F3,
                    url=href
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
                embed.set_footer(text="Ingresso Digital")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(0.5, cancelar)

            except Exception as e:
                logger.warning(f"IngressoDigital: erro ao processar card (pg {pg}): {e}")
                continue

        pg += 1

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no Ingresso Digital para as cidades selecionadas")
    return total
