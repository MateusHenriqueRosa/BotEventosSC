"""Script de teste para validar scrapers sem Discord.
Cria um canal mock que imprime os embeds no terminal.
"""
import asyncio
import sys
import os
import logging

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MockEmbed:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.description = kwargs.get("description", "")
        self.url = kwargs.get("url", "")
        self.fields = []
        self.footer_text = ""
        self.image_url = ""

    def set_image(self, url=""):
        self.image_url = url

    def set_footer(self, text=""):
        self.footer_text = text

    def add_field(self, name="", value="", inline=False):
        self.fields.append({"name": name, "value": value})


class MockCanal:
    def __init__(self):
        self.mensagens = []

    async def send(self, content=None, embed=None):
        if content:
            print(f"  💬 {content}")
            self.mensagens.append(content)
        if embed:
            print(f"  📦 EMBED: {embed.title}")
            if embed.description:
                for line in embed.description.split("\n"):
                    print(f"       {line}")
            if embed.url:
                print(f"       URL: {embed.url}")
            if embed.footer_text:
                print(f"       [{embed.footer_text}]")
            self.mensagens.append(embed.title)


# Monkey-patch discord.Embed para usar nosso MockEmbed
import discord
discord.Embed = MockEmbed

from scrapers import criar_driver, resetar_driver
from scrapers.ingresso_nacional import buscar_ingressonacional
from scrapers.blueticket import buscar_blueticket
from scrapers.guicheweb import buscar_guicheweb
from scrapers.pensanoevento import buscar_pensanoevento
from scrapers.minhaentrada import buscar_minhaentrada
from scrapers.bilheteriadigital import buscar_bilheteriadigital
from scrapers.aquitemingressos import buscar_aquitemingressos
from scrapers.ingressodigital import buscar_ingressodigital
from scrapers.eticketcenter import buscar_eticketcenter


async def testar_scraper(nome, scraper_fn, driver, cancelar, eventos_enviados, **kwargs):
    print(f"\n{'='*60}")
    print(f"🧪 TESTANDO: {nome}")
    print(f"{'='*60}")
    canal = MockCanal()
    try:
        n = await scraper_fn(canal, driver=driver, cancelar=cancelar, eventos_enviados=eventos_enviados, **kwargs)
        print(f"\n  ✅ Resultado: {n} evento(s) encontrado(s)")
    except Exception as e:
        print(f"\n  ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
    return canal


async def main():
    cidade_teste = sys.argv[1] if len(sys.argv) > 1 else "Florianópolis"
    cidades_teste = [cidade_teste]

    # Qual scraper testar? Argumento 2 = nome do scraper (ou "todos")
    scraper_alvo = sys.argv[2] if len(sys.argv) > 2 else "todos"

    print(f"🏙️  Cidade: {cidade_teste}")
    print(f"🎯 Scraper: {scraper_alvo}")

    driver = criar_driver()
    cancelar = asyncio.Event()
    eventos_enviados = set()

    scrapers_percidade = {
        "ingressonacional": ("Ingresso Nacional", buscar_ingressonacional, {"cidade": cidade_teste}),
        "blueticket": ("Blueticket", buscar_blueticket, {"cidade": cidade_teste}),
        "guicheweb": ("Guichê Web", buscar_guicheweb, {"cidade": cidade_teste}),
        "pensanoevento": ("Pensa no Evento", buscar_pensanoevento, {"cidade": cidade_teste}),
    }

    scrapers_bulk = {
        "minhaentrada": ("Minha Entrada", buscar_minhaentrada, {"cidades_busca": cidades_teste}),
        "bilheteriadigital": ("Bilheteria Digital", buscar_bilheteriadigital, {"cidades_busca": cidades_teste}),
        "aquitemingressos": ("Aqui Tem Ingressos", buscar_aquitemingressos, {"cidades_busca": cidades_teste}),
        "ingressodigital": ("Ingresso Digital", buscar_ingressodigital, {"cidades_busca": cidades_teste}),
        "eticketcenter": ("eTicket Center", buscar_eticketcenter, {"cidades_busca": cidades_teste}),
    }

    todos = {**scrapers_percidade, **scrapers_bulk}

    try:
        if scraper_alvo == "todos":
            for key, (nome, fn, kwargs) in todos.items():
                resetar_driver(driver)
                await testar_scraper(nome, fn, driver, cancelar, eventos_enviados, **kwargs)
        elif scraper_alvo in todos:
            nome, fn, kwargs = todos[scraper_alvo]
            await testar_scraper(nome, fn, driver, cancelar, eventos_enviados, **kwargs)
        else:
            print(f"❌ Scraper '{scraper_alvo}' não encontrado.")
            print(f"   Opções: {', '.join(todos.keys())}, todos")
    finally:
        driver.quit()

    print(f"\n{'='*60}")
    print(f"📊 Total de eventos únicos: {len(eventos_enviados)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
