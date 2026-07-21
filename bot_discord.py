import asyncio
import logging
import os
import re
import urllib.parse

import discord
from discord.ext import commands
from dotenv import load_dotenv

from scrapers import (
    SITES,
    buscar_aquitemingressos,
    buscar_bilheteriadigital,
    buscar_blueticket,
    buscar_eticketcenter,
    buscar_guicheweb,
    buscar_ingressodigital,
    buscar_ingressonacional,
    buscar_minhaentrada,
    buscar_pensanoevento,
    canonizar_cidade,
    cancelavel_sleep,
    criar_driver,
    extrair_detalhes,
    resetar_driver,
)

# Domínios de ingresso aceitos pelo !detalhes (os mesmos 9 sites da automação)
DOMINIOS_PERMITIDOS = {url for _, url in SITES}

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bot_eventos")

BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    CANAL_ID = int(os.getenv("CANAL_ID", "0").strip())
except ValueError:
    CANAL_ID = 0
MAX_BUSCAS_SIMULTANEAS = 2

cidades = ["Florianópolis", "Brusque", "Blumenau", "Balneário Camboriú", "Camboriú", "Itapema", "Porto Belo", "Itajaí"]

buscas_ativas: dict[int, asyncio.Event] = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


def parse_cidades(args: str) -> list[str]:
    if not args or not args.strip():
        return []
    return [c.strip() for c in args.split(";") if c.strip()]


async def buscar_eventos(canal, cidades_busca: list[str] = None, cancelar: asyncio.Event = None):
    if cancelar is None:
        cancelar = asyncio.Event()
    base = cidades_busca if cidades_busca else cidades
    lista = [canonizar_cidade(c) for c in base]
    eventos_enviados: set = set()
    resultados: dict[str, int] = {}

    await canal.send("🔍 Iniciando busca de eventos...")
    driver = criar_driver()

    try:
        total_eventos = 0

        # ── Ingresso Nacional (por cidade) ─────────────────────────────────
        await canal.send("🎟️ **Ingresso Nacional**")
        in_total = 0
        for cidade in lista:
            if cancelar.is_set():
                return
            await canal.send(f"📍 Pesquisando em: **{cidade}**")
            n = await buscar_ingressonacional(canal, cidade, driver, cancelar, eventos_enviados)
            if n == 0 and not cancelar.is_set():
                await canal.send(f"⚠️ Nenhum evento encontrado no Ingresso Nacional para {cidade}")
            in_total += n
        resultados["Ingresso Nacional"] = in_total
        total_eventos += in_total

        # ── Blueticket + Guichê Web + Pensa no Evento (por cidade) ─────────
        bt_total = 0
        gw_total = 0
        pe_total = 0

        if not cancelar.is_set():
            for cidade in lista:
                if cancelar.is_set():
                    break

                resetar_driver(driver)
                bt_total += await buscar_blueticket(canal, cidade, driver, cancelar, eventos_enviados)

                if cancelar.is_set():
                    break
                resetar_driver(driver)
                await canal.send(f"🟠 **Guichê Web** em **{cidade}**")
                n = await buscar_guicheweb(canal, cidade, driver, cancelar, eventos_enviados)
                if n == 0 and not cancelar.is_set():
                    await canal.send(f"⚠️ Nenhum evento encontrado no Guichê Web para {cidade}")
                gw_total += n

                if cancelar.is_set():
                    break
                resetar_driver(driver)
                await canal.send(f"🎉 **Pensa no Evento** em **{cidade}**")
                n = await buscar_pensanoevento(canal, cidade, driver, cancelar, eventos_enviados)
                if n == 0 and not cancelar.is_set():
                    await canal.send(f"⚠️ Nenhum evento encontrado no Pensa no Evento para {cidade}")
                pe_total += n

        resultados["Blueticket"] = bt_total
        resultados["Guichê Web"] = gw_total
        resultados["Pensa no Evento"] = pe_total
        total_eventos += bt_total + gw_total + pe_total

        # ── Sites bulk (busca SC inteira, filtra por cidade) ───────────────
        bulk_scrapers = [
            ("Minha Entrada", buscar_minhaentrada),
            ("Bilheteria Digital", buscar_bilheteriadigital),
            ("Aqui Tem Ingressos", buscar_aquitemingressos),
            ("Ingresso Digital", buscar_ingressodigital),
            ("eTicket Center", buscar_eticketcenter),
        ]

        for nome_site, scraper_fn in bulk_scrapers:
            if cancelar.is_set():
                break
            resetar_driver(driver)
            n = await scraper_fn(canal, lista, driver, cancelar, eventos_enviados)
            resultados[nome_site] = n
            total_eventos += n

        # ── Resumo por site ────────────────────────────────────────────────
        if not cancelar.is_set():
            resumo_lines = []
            for nome_site, _ in SITES:
                count = resultados.get(nome_site, 0)
                emoji = "✅" if count > 0 else "➖"
                resumo_lines.append(f"{emoji} **{nome_site}:** {count}")

            embed_resumo = discord.Embed(
                title="📊 Resumo por Site",
                description="\n".join(resumo_lines),
                color=0x00ff00
            )
            await canal.send(embed=embed_resumo)
            await canal.send(f"✅ Busca concluída! Total de eventos encontrados: **{total_eventos}**")

    except Exception as e:
        logger.error(f"Erro na automação: {e}")
        await canal.send(f"❌ Erro na automação: {str(e)}")
    finally:
        driver.quit()


@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'ID: {bot.user.id}')
    print('------')


@bot.command(name='buscar')
async def buscar(ctx, *, args: str = None):
    """Comando para iniciar a busca de eventos.

    Uso:
      !buscar                    → cidades padrão
      !buscar Blumenau           → cidade específica
      !buscar Blumenau;Itajaí    → múltiplas cidades
    """
    if CANAL_ID and ctx.channel.id != CANAL_ID:
        await ctx.send("⚠️ Este comando só pode ser usado no canal designado.")
        return

    user_id = ctx.author.id

    if user_id in buscas_ativas:
        await ctx.send("⚠️ Você já tem uma busca em andamento. Use `!parar` para cancelá-la antes de iniciar outra.")
        return

    if len(buscas_ativas) >= MAX_BUSCAS_SIMULTANEAS:
        await ctx.send(f"⚠️ Limite de {MAX_BUSCAS_SIMULTANEAS} buscas simultâneas atingido. Aguarde uma busca terminar.")
        return

    cidades_busca = parse_cidades(args)

    if cidades_busca:
        await ctx.send(f"🚀 Buscando eventos em: **{', '.join(cidades_busca)}**")
    else:
        await ctx.send("🚀 Buscando eventos nas cidades padrão...")

    cancelar = asyncio.Event()
    buscas_ativas[user_id] = cancelar

    try:
        await buscar_eventos(ctx.channel, cidades_busca or None, cancelar)
    finally:
        buscas_ativas.pop(user_id, None)

    if cancelar.is_set():
        await ctx.send("🛑 Busca cancelada pelo usuário.")


@bot.command(name='parar', aliases=['cancelar'])
async def parar(ctx):
    """Cancela a busca em andamento do usuário."""
    user_id = ctx.author.id

    if user_id not in buscas_ativas:
        await ctx.send("ℹ️ Você não tem nenhuma busca em andamento.")
        return

    buscas_ativas[user_id].set()
    await ctx.send("🛑 Cancelamento solicitado. Aguarde a operação ser interrompida...")


@bot.command(name='eventos')
async def eventos(ctx, *, args: str = None):
    """Alias para o comando buscar"""
    await buscar(ctx, args=args)


def _site_do_link(link: str) -> str | None:
    """Retorna o nome do site se o domínio do link for permitido, senão None."""
    try:
        host = urllib.parse.urlparse(link).netloc.lower()
    except Exception:
        return None
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for nome, dominio in SITES:
        if host == dominio or host.endswith("." + dominio) or host == "www." + dominio:
            return nome
    return None


@bot.command(name='detalhes')
async def detalhes(ctx, *, link: str = None):
    """Mostra lotes, setores e preços de um ingresso.

    Uso: !detalhes <link do ingresso>
    (o link é o mesmo enviado pela automação nos embeds)
    """
    if CANAL_ID and ctx.channel.id != CANAL_ID:
        await ctx.send("⚠️ Este comando só pode ser usado no canal designado.")
        return

    if not link or not link.strip():
        await ctx.send("ℹ️ Uso: `!detalhes <link do ingresso>` — cole o link enviado pela automação.")
        return

    link = link.strip().strip("<>")
    if not re.match(r"^https?://", link, re.IGNORECASE):
        await ctx.send("⚠️ Envie um link válido começando com `http`.")
        return

    site_nome = _site_do_link(link)
    if not site_nome:
        dominios = ", ".join(sorted(DOMINIOS_PERMITIDOS))
        await ctx.send(f"⚠️ Só aceito links dos sites consultados pela automação:\n{dominios}")
        return

    await ctx.send(f"🔎 Buscando lotes e preços em **{site_nome}**...")

    driver = criar_driver()
    cancelar = asyncio.Event()
    try:
        dados = await extrair_detalhes(link, driver, cancelar)
    except Exception as e:
        logger.error(f"Erro no !detalhes ({link}): {e}")
        await ctx.send("❌ Não consegui abrir esse link ou ler os ingressos.")
        return
    finally:
        driver.quit()

    tiers = dados.get("tiers", [])
    if not tiers:
        await ctx.send(
            "⚠️ Não encontrei lotes/preços nessa página. "
            "Pode ser que as vendas ainda não abriram, esgotaram, ou exigem login."
        )
        return

    titulo = dados.get("titulo") or "Ingresso"
    linhas = []
    for t in tiers[:30]:
        nome = t["nome"] or "Ingresso"
        linha = f"🎫 **{nome}** — {t['preco']}"
        extras = []
        if t["lote"]:
            extras.append(t["lote"])
        if t["taxa"]:
            extras.append(t["taxa"].lstrip("+ ").strip())
        if extras:
            linha += f"  ·  _{' · '.join(extras)}_"
        linhas.append(linha)

    descricao = "\n".join(linhas)
    if len(descricao) > 4000:
        descricao = descricao[:4000] + "\n… (lista truncada)"

    embed = discord.Embed(
        title=f"🎟️ {titulo}"[:256],
        description=descricao,
        color=0xFFD700,
        url=link,
    )
    rodape = f"{site_nome} · {len(tiers)} opç" + ("ões" if len(tiers) != 1 else "ão")
    embed.set_footer(text=rodape)
    await ctx.send(embed=embed)


@bot.command(name='cidades')
async def listar_cidades(ctx):
    """Mostra as cidades disponíveis para busca."""
    embed = discord.Embed(
        title="📍 Cidades Disponíveis",
        description="\n".join(f"• {c}" for c in cidades),
        color=0x00ff00
    )
    embed.set_footer(text="Use !buscar <cidade> ou !buscar <cidade1>;<cidade2>")
    await ctx.send(embed=embed)


@bot.command(name='sites')
async def listar_sites(ctx):
    """Mostra os sites de ingressos consultados."""
    embed = discord.Embed(
        title="🌐 Sites Consultados",
        description="\n".join(f"✅ **{nome}** — {url}" for nome, url in SITES),
        color=0x5865F2
    )
    embed.set_footer(text=f"{len(SITES)} sites ativos")
    await ctx.send(embed=embed)


@bot.command(name='ajuda')
async def ajuda(ctx):
    """Mostra os comandos disponíveis"""
    embed = discord.Embed(
        title="📋 Comandos Disponíveis",
        description="Lista de comandos do bot de eventos",
        color=0x00ff00
    )
    embed.add_field(name="!buscar", value="Busca eventos nas cidades padrão", inline=False)
    embed.add_field(name="!buscar <cidade>", value="Busca em uma cidade específica\nEx: `!buscar Florianópolis`", inline=False)
    embed.add_field(name="!buscar <cidade1>;<cidade2>", value="Busca em múltiplas cidades\nEx: `!buscar Blumenau;Itajaí`", inline=False)
    embed.add_field(name="!eventos", value="Mesmo que !buscar", inline=False)
    embed.add_field(name="!detalhes <link>", value="Mostra lotes, setores e preços de um ingresso\nEx: `!detalhes <link enviado pela automação>`", inline=False)
    embed.add_field(name="!cidades", value="Lista as cidades disponíveis para busca", inline=False)
    embed.add_field(name="!sites", value="Lista os sites de ingressos consultados", inline=False)
    embed.add_field(name="!parar", value="Cancela a busca em andamento (também: `!cancelar`)", inline=False)
    embed.add_field(name="!ajuda", value="Mostra esta mensagem", inline=False)
    await ctx.send(embed=embed)


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Configure o BOT_TOKEN no arquivo .env antes de executar!")
        print("💡 Copie o .env.example para .env e adicione suas credenciais")
    elif CANAL_ID == 0:
        print("⚠️ CANAL_ID não configurado no .env, mas o bot vai iniciar")
        bot.run(BOT_TOKEN)
    else:
        bot.run(BOT_TOKEN)
