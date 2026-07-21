import discord
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .helpers import logger, evento_key, cancelavel_sleep, titulo_bloqueado

BASE_URL = "https://www.ingressonacional.com.br"
CDN_URL = "https://cdnin.blob.core.windows.net/cdn"


async def buscar_ingressonacional(canal, cidade, driver, cancelar, eventos_enviados):
    driver.get(BASE_URL)
    await cancelavel_sleep(3, cancelar)
    if cancelar.is_set():
        return 0

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
            lambda d: d.find_elements(By.CSS_SELECTOR, "div.col-sm-6.col-md-3.animated")
                      or d.find_elements(By.XPATH, "//*[contains(text(),'Nenhum evento')]")
        )
    except Exception:
        logger.info(f"Ingresso Nacional: timeout aguardando cards em {cidade}")
        return 0

    await cancelavel_sleep(1, cancelar)

    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "div.col-sm-6.col-md-3.animated")

        for card in cards:
            if cancelar.is_set():
                return total
            try:
                nome = ""
                try:
                    nome = card.find_element(By.CSS_SELECTOR, "h2.ng-binding").text.strip()
                except Exception:
                    try:
                        nome = card.find_element(By.TAG_NAME, "h2").text.strip()
                    except Exception:
                        continue
                if not nome:
                    continue
                if titulo_bloqueado(nome):
                    continue

                data = ""
                try:
                    data = card.find_element(By.CSS_SELECTOR, "span.ng-binding").text.strip()
                except Exception:
                    pass

                cidade_card = ""
                try:
                    h4_elements = card.find_elements(By.CSS_SELECTOR, "h4.ng-binding")
                    if h4_elements:
                        cidade_card = h4_elements[-1].text.strip()
                except Exception:
                    pass

                link_imagem = None
                try:
                    img = card.find_element(By.CSS_SELECTOR, "img.img-responsive")
                    link_imagem = img.get_attribute("ng-src") or img.get_attribute("src")
                except Exception:
                    pass

                url_evento = ""
                try:
                    url_evento = driver.execute_script(
                        "var scope = angular.element(arguments[0]).scope();"
                        "return scope && scope.evento ? scope.evento.urlEvento : '';",
                        card
                    )
                except Exception:
                    pass

                link = f"{BASE_URL}/{url_evento}" if url_evento else ""

                key = evento_key(nome, data)
                if key in eventos_enviados:
                    continue
                eventos_enviados.add(key)

                desc_parts = []
                if data:
                    desc_parts.append(f"**📅 Data:** {data}")
                if cidade_card:
                    desc_parts.append(f"**📍 Local:** {cidade_card}")
                else:
                    desc_parts.append(f"**📍 Local:** {cidade}")

                embed = discord.Embed(
                    title=f"🎭 {nome}",
                    description="\n".join(desc_parts),
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
