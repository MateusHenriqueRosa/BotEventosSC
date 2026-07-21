import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, evento_key, normalizar_texto, cancelavel_sleep, titulo_bloqueado

BASE_URL = "https://www.bilheteriadigital.com"


async def buscar_bilheteriadigital(canal, cidades_busca, driver, cancelar, eventos_enviados):
    await canal.send("🟣 **Bilheteria Digital**")

    cidades_norm = {normalizar_texto(c): c for c in cidades_busca}
    driver.get(f"{BASE_URL}/SC")

    try:
        WebDriverWait(driver, 12).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "li.box-li-evento")
        )
    except Exception as e:
        logger.info(f"BilheteriaDigital: timeout aguardando cards SC: {e}")
        return 0

    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    cards = driver.find_elements(By.CSS_SELECTOR, "li.box-li-evento")

    for card in cards:
        if cancelar.is_set():
            return total
        try:
            link_el = card.find_element(By.TAG_NAME, "a")
            href = link_el.get_attribute("href") or ""
            if not href:
                continue
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"

            nome = ""
            try:
                nome = card.find_element(By.CSS_SELECTOR, ".titulo-evento-thumb").text.strip()
            except Exception:
                pass
            if not nome:
                continue
            if titulo_bloqueado(nome):
                continue

            data = ""
            try:
                data = card.find_element(By.CSS_SELECTOR, ".data-evento-div").text.strip()
            except Exception:
                pass

            cidade_texto = ""
            try:
                cidade_texto = card.find_element(By.CSS_SELECTOR, ".cidade-box-evento").text.strip()
            except Exception:
                pass

            cidade_evento = cidade_texto.replace(" - SC", "").replace("- SC", "").strip()
            if not cidade_evento or normalizar_texto(cidade_evento) not in cidades_norm:
                continue

            local = ""
            try:
                local = card.find_element(By.CSS_SELECTOR, ".local-box-evento").text.strip()
            except Exception:
                pass

            link_imagem = None
            try:
                link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
            except Exception:
                pass

            key = evento_key(nome, data)
            if key in eventos_enviados:
                continue
            eventos_enviados.add(key)

            local_display = f"{local} — {cidade_texto}" if local else cidade_texto

            embed = discord.Embed(
                title=f"🎫 {nome}",
                description=f"**📅 Data:** {data}\n**📍 Local:** {local_display}",
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
