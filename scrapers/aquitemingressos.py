import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, extrair_cidade, cidade_match, cancelavel_sleep


async def buscar_aquitemingressos(canal, cidades_busca, driver, cancelar, eventos_enviados):
    await canal.send("🟡 **Aqui Tem Ingressos**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    driver.get("https://www.aquitemingressos.com.br/eventos")

    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='__']")
                      or d.find_elements(By.TAG_NAME, "h4")
        )
    except Exception as e:
        logger.info(f"AquiTemIngressos: timeout aguardando cards: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    links_processados: set = set()
    cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='__']")

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            href = card.get_attribute("href") or ""
            if not href or href in links_processados:
                continue
            links_processados.add(href)

            nome = ""
            try:
                nome = card.find_element(By.TAG_NAME, "h4").text.strip()
            except Exception:
                text = card.text.strip()
                nome = text.split("\n")[0] if text else ""
            if not nome:
                continue

            link_imagem = None
            try:
                link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
            except Exception:
                pass

            data = ""
            local = ""
            try:
                parent = card.find_element(By.XPATH, "./..")
                parent_text = parent.text.strip()
                lines = [l.strip() for l in parent_text.split("\n") if l.strip()]

                for line in lines:
                    if line == nome:
                        continue
                    line_lower = line.lower()
                    if any(d in line_lower for d in ["seg,", "ter,", "qua,", "qui,", "sex,", "sáb,", "sab,", "dom,"]) and not data:
                        data = line
                    elif ("SC" in line or "sc" in line.split(",")[-1].strip() if "," in line else False) and not local:
                        local = line
                    elif " - " in line and not local:
                        local = line
            except Exception:
                pass

            cidade_evento = extrair_cidade(local)
            if cidade_evento and normalizar_texto(cidade_evento) in cidades_norm:
                pass
            elif cidade_match(f"{nome} {local} {data}", cidades_norm):
                pass
            else:
                continue

            key = evento_key(nome, data)
            if key in eventos_enviados:
                continue
            eventos_enviados.add(key)

            if href.startswith("/"):
                href = f"https://www.aquitemingressos.com.br{href}"

            embed = discord.Embed(
                title=f"🎫 {nome}",
                description=f"**📅 Data:** {data}\n**📍 Local:** {local}",
                color=0xF5A623,
                url=href
            )
            if link_imagem:
                embed.set_image(url=link_imagem)
            embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
            embed.set_footer(text="Aqui Tem Ingressos")

            await canal.send(embed=embed)
            total += 1
            await cancelavel_sleep(0.5, cancelar)

        except Exception as e:
            logger.warning(f"AquiTemIngressos: erro ao processar card: {e}")
            continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado no Aqui Tem Ingressos para as cidades selecionadas")
    return total
