import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cidade_match, cancelavel_sleep, titulo_bloqueado


async def buscar_aquitemingressos(canal, cidades_busca, driver, cancelar, eventos_enviados):
    await canal.send("🟡 **Aqui Tem Ingressos**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    driver.get("https://www.aquitemingressos.com.br/eventos")

    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "div.product-card")
        )
    except Exception as e:
        logger.info(f"AquiTemIngressos: timeout aguardando cards: {e}")
        return 0

    await cancelavel_sleep(1, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    cards = driver.find_elements(By.CSS_SELECTOR, "div.product-card")

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            title_link = card.find_element(By.CSS_SELECTOR, "a.card-link-title")
            nome = title_link.text.strip()
            href = title_link.get_attribute("href") or ""
            if not nome or not href:
                continue
            # Ignorar card promocional fixo (não é um evento real)
            if "seu evento" in normalizar_texto(nome):
                continue
            if titulo_bloqueado(nome):
                continue
            if href.startswith("/"):
                href = f"https://www.aquitemingressos.com.br{href}"

            data = ""
            try:
                data = card.find_element(By.CSS_SELECTOR, "span.card-event-date").text.strip()
            except Exception:
                pass

            local = ""
            try:
                local = card.find_element(By.TAG_NAME, "small").text.strip()
            except Exception:
                pass

            cidade_encontrada = cidade_match(local, cidades_norm)
            if not cidade_encontrada:
                continue

            link_imagem = None
            try:
                link_imagem = card.find_element(By.CSS_SELECTOR, "img.card-img-top").get_attribute("src")
            except Exception:
                pass

            key = evento_key(nome, data)
            if key in eventos_enviados:
                continue
            eventos_enviados.add(key)

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
