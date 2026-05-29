import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, extrair_cidade, cancelavel_sleep

MESES = ["janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


async def buscar_bilheteriadigital(canal, cidades_busca, driver, cancelar, eventos_enviados):
    await canal.send("🟣 **Bilheteria Digital**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    driver.get("https://www.bilheteriadigital.com/SC")

    try:
        WebDriverWait(driver, 12).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href]") and len(d.find_elements(By.CSS_SELECTOR, "a[href]")) > 5
        )
    except Exception as e:
        logger.info(f"BilheteriaDigital: timeout aguardando cards SC: {e}")
        return 0

    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    cards = []
    for link in all_links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if (href.startswith("https://www.bilheteriadigital.com/")
            and href != "https://www.bilheteriadigital.com/SC"
            and href != "https://www.bilheteriadigital.com/"
            and text and len(text) > 10
            and " - SC" in text.upper()):
            cards.append(link)

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            href = card.get_attribute("href") or ""
            if not href:
                continue
            card_text = card.text.strip()
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            nome = lines[0]
            data = ""
            cidade_texto = ""
            local = ""

            for line in lines[1:]:
                line_lower = line.lower()
                if any(m in line_lower for m in MESES) and not data:
                    data = line
                elif " - SC" in line.upper():
                    cidade_texto = line
                elif not local:
                    local = line

            cidade_evento = extrair_cidade(cidade_texto) if cidade_texto else ""
            if not cidade_evento or normalizar_texto(cidade_evento) not in cidades_norm:
                continue

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
                description=f"**📅 Data:** {data}\n**📍 Local:** {local}\n**🏙️ Cidade:** {cidade_texto}",
                color=0x6C3BF5,
                url=href
            )
            if link_imagem:
                embed.set_image(url=link_imagem)
            embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({href})", inline=False)
            embed.set_footer(text="Bilheteria Digital")

            await canal.send(embed=embed)
            total += 1
            await cancelavel_sleep(0.5, cancelar)

        except Exception as e:
            logger.warning(f"BilheteriaDigital: erro ao processar card: {e}")
            continue

    if total == 0 and not cancelar.is_set():
        await canal.send("⚠️ Nenhum evento encontrado na Bilheteria Digital para as cidades selecionadas")
    return total
