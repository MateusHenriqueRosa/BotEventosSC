"""Testa a extração de detalhes de ingresso (!detalhes) com links reais."""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from scrapers import criar_driver, resetar_driver
from scrapers.detalhes import extrair_detalhes

LINKS = {
    "Blueticket": "https://www.blueticket.com.br/evento/41332/06-set-preview-house-mag-w-blazy",
    "Pensa no Evento": "https://www.pensanoevento.com.br/sitev2/eventos/103945/arraia-do-hike",
    "Aqui Tem Ingressos": "https://www.aquitemingressos.com.br/arraia-wine-sunset__23824/",
    "Ingresso Digital": "https://www.ingressodigital.com/evento/21290/starlight-concert-queen-coldplay",
}


async def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else "todos"
    link_custom = sys.argv[2] if len(sys.argv) > 2 else None

    driver = criar_driver()
    cancelar = asyncio.Event()

    try:
        if link_custom:
            itens = [(alvo, link_custom)]
        elif alvo == "todos":
            itens = list(LINKS.items())
        else:
            itens = [(alvo, LINKS[alvo])]

        for nome, link in itens:
            print(f"\n{'='*65}\n🎟️  {nome}\n   {link}\n{'='*65}")
            resetar_driver(driver)
            try:
                d = await extrair_detalhes(link, driver, cancelar)
                print(f"📌 Título: {d['titulo']}")
                print(f"📊 {len(d['tiers'])} tier(s):")
                for t in d["tiers"]:
                    linha = f"   • {t['nome'] or '(sem nome)'} — {t['preco']}"
                    if t["lote"]:
                        linha += f"  [{t['lote']}]"
                    if t["taxa"]:
                        linha += f"  ({t['taxa']})"
                    print(linha)
            except Exception as e:
                import traceback
                print(f"❌ ERRO: {e}")
                traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    asyncio.run(main())
