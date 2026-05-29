import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .helpers import logger, evento_key, cancelavel_sleep


async def buscar_ingressonacional(canal, cidade, driver, cancelar, eventos_enviados):
    driver.get("https://www.ingressonacional.com.br/balada")
    await cancelavel_sleep(3, cancelar)
    if cancelar.is_set():
        return 0

    # Remover overlays (chat widgets, cookie banners) que bloqueiam interação
    driver.execute_script(
        "document.querySelectorAll('[class*=wbot], [class*=chat-widget], [class*=cookie]')"
        ".forEach(el => el.style.display='none')"
    )

    try:
        search_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[placeholder*='Pesquise'], input[placeholder*='busca']")
            )
        )
    except Exception:
        # Fallback: buscar qualquer input visível via JS
        try:
            search_box = driver.execute_script(
                "return [...document.querySelectorAll('input')].find(i => i.offsetParent !== null && i.type !== 'hidden')"
            )
            if not search_box:
                raise Exception("nenhum input visível")
        except Exception as e:
            logger.warning(f"Ingresso Nacional: campo de busca não encontrado para {cidade}: {e}")
            return 0

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", search_box)
        search_box.click()
        search_box.clear()
        search_box.send_keys(cidade)
    except Exception:
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}))",
            search_box, cidade
        )

    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return 0

    try:
        search_box.send_keys(Keys.RETURN)
    except Exception:
        driver.execute_script(
            "arguments[0].closest('form')?.submit() || arguments[0].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))",
            search_box
        )

    await cancelavel_sleep(3, cancelar)
    if cancelar.is_set():
        return 0

    total = 0
    try:
        WebDriverWait(driver, 8).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/evento'], [class*='event']")
                      or d.find_elements(By.TAG_NAME, "h2")
        )
    except Exception:
        logger.info(f"Ingresso Nacional: timeout aguardando cards em {cidade}")
        return 0

    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/evento']")
        if not cards:
            for sel in [".events-list > div", "[class*='event'] > div", ".row > div[class*='col']"]:
                cards = driver.find_elements(By.CSS_SELECTOR, sel)
                if cards:
                    break
        if not cards:
            cards = driver.find_elements(By.XPATH, "//div[.//h2 and .//img]")

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                nome = ""
                for tag in ["h2", "h3", "h4", ".event-name", ".event-title"]:
                    try:
                        nome = card.find_element(By.CSS_SELECTOR, tag).text.strip()
                        if nome:
                            break
                    except Exception:
                        continue
                if not nome:
                    continue

                data = ""
                for sel in ["span", ".event-date", ".date", "time"]:
                    try:
                        data = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if data:
                            break
                    except Exception:
                        continue

                link_imagem = None
                try:
                    link_imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
                except Exception:
                    pass

                # Tentar link direto primeiro (card é <a>), depois buscar ancora filha (card é div)
                link = ""
                try:
                    link = card.get_attribute("href") or ""
                except Exception:
                    pass
                if not link or link.startswith("javascript") or link == "#":
                    link = ""
                    for a_sel in ["a[href*='/evento']", "a[href*='/show']", "a[href]"]:
                        try:
                            link = card.find_element(By.CSS_SELECTOR, a_sel).get_attribute("href") or ""
                            if link and not link.startswith("javascript") and link != "#":
                                break
                            link = ""
                        except Exception:
                            continue

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                embed = discord.Embed(
                    title=f"🎭 {nome}",
                    description=f"**📅 Data:** {data}\n**📍 Local:** {cidade}",
                    color=0x5865F2,
                    url=link or ""
                )
                if link_imagem:
                    embed.set_image(url=link_imagem)
                if link:
                    embed.add_field(name="🔗 Link", value=f"[🎟️ Comprar ingresso]({link})", inline=False)
                embed.set_footer(text="Ingresso Nacional")

                await canal.send(embed=embed)
                total += 1
                await cancelavel_sleep(1, cancelar)

            except Exception as e:
                logger.warning(f"Ingresso Nacional: erro ao processar card em {cidade}: {e}")
                continue

    except Exception as e:
        logger.warning(f"Ingresso Nacional: erro ao buscar eventos em {cidade}: {e}")

    return total
