"""Extrai lote, setores e preços da página de um ingresso.

Usado pelo comando !detalhes <link>. O link é o mesmo enviado pela
automação (qualquer um dos 9 sites). A extração é genérica: procura
padrões de preço (R$), lote e palavras-chave de setor (pista, vip,
feminino, masculino, meia entrada, meia social...) no documento e em
iframes de mesma origem (ex: o painel de ingressos do Blueticket).
"""
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .helpers import logger, cancelavel_sleep

PRECO_RE = re.compile(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}")
LOTE_RE = re.compile(r"\d+\s*[º°.]\s*lote|lote\s*:?\s*\d+|\d+[º°]\s*lote", re.IGNORECASE)
TAXA_RE = re.compile(r"\+\s*R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}\s*(?:de\s*)?taxa", re.IGNORECASE)

# Marcadores que indicam o fim do nome do ingresso numa linha.
MARKER_RE = re.compile(
    r"(valor\s*:|saiba mais|lote\s*[:.]?\s*\d|\d+\s*[º°.]\s*lote|R\$|a partir de)",
    re.IGNORECASE,
)
# Ruído de UI a remover do nome.
NOISE_RE = re.compile(r"\b(comprar|esgotado|adicionar|selecione|indispon[íi]vel)\b", re.IGNORECASE)

# Palavras que indicam que a linha é um setor/tipo de ingresso.
KEYWORDS = re.compile(
    r"pista|vip|camarote|backstage|front\s?stage|feminin|masculin|"
    r"meia|inteira|social|open\s?bar|lounge|mesa|bistr|área|area|"
    r"passaporte|combo|day\s?use|cadeira|arquibancada|pel[uú]cia|"
    r"unissex|solidári|estudante|lote|setor|ingresso",
    re.IGNORECASE,
)

# JS que coleta linhas candidatas (com preço) no frame atual.
# Só aceita linhas com no máximo 2 ocorrências de preço (valor + taxa),
# para isolar UM tier por linha e não juntar vários setores num texto só.
_JS_COLETAR = r"""
const out = [];
const seen = new Set();
const els = document.querySelectorAll('body *');
for (const el of els) {
    let t = el.innerText;
    if (!t) continue;
    t = t.replace(/\s+/g, ' ').trim();
    if (t.length < 3 || t.length > 200) continue;
    const precos = t.match(/R\$\s*\d/g) || [];
    if (precos.length < 1 || precos.length > 2) continue;
    if (seen.has(t)) continue;
    seen.add(t);
    out.push(t);
}
return out;
"""

# Linhas que não são ingresso (carrinho, totais, etc.)
LIXO_RE = re.compile(r"^\s*(total|subtotal|valor\s*total|carrinho|frete|doa[çc][aã]o)\b", re.IGNORECASE)


def _coletar_linhas_frame(driver):
    try:
        return driver.execute_script(_JS_COLETAR) or []
    except Exception:
        return []


def _dedupe_substrings(linhas):
    """Remove linhas que são substring de outra maior (mantém a mais
    informativa, ex: a que tem o nome do setor além do preço)."""
    linhas = sorted(set(linhas), key=len, reverse=True)
    mantidas = []
    for l in linhas:
        if not any(l != m and l in m for m in mantidas):
            mantidas.append(l)
    return mantidas


def _parse_linha(linha):
    """Extrai (nome, preco, lote, taxa) de uma linha de ingresso."""
    precos = PRECO_RE.findall(linha)
    if not precos:
        return None
    preco = precos[0]

    taxa_m = TAXA_RE.search(linha)
    taxa = taxa_m.group(0) if taxa_m else ""

    lote_m = LOTE_RE.search(linha)
    lote = lote_m.group(0).strip() if lote_m else ""

    # nome = tudo antes do primeiro marcador (Lote/Valor/Saiba Mais/R$)
    m = MARKER_RE.search(linha)
    nome = linha[: m.start()] if m else linha[: linha.find(preco)]
    nome = re.sub(r"^\s*ingresso\s*:?\s*", "", nome, flags=re.IGNORECASE)
    nome = NOISE_RE.sub("", nome).strip(" -–—•·|:.")
    resumo = bool(re.search(r"a partir de", linha, re.IGNORECASE))
    return {"nome": nome, "preco": preco, "lote": lote, "taxa": taxa, "resumo": resumo}


def _extrair_tiers(driver):
    """Coleta linhas de ingresso do documento e de iframes same-origin."""
    linhas = _coletar_linhas_frame(driver)

    # Entrar em iframes de mesma origem (ex: painel de ingressos Blueticket)
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for idx in range(len(iframes)):
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            if idx >= len(frames):
                break
            driver.switch_to.frame(frames[idx])
            linhas += _coletar_linhas_frame(driver)
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    linhas = _dedupe_substrings(linhas)

    tiers = []
    vistos = set()
    for l in linhas:
        # só linhas que parecem tier de ingresso (tem keyword de setor/tipo)
        if not KEYWORDS.search(l):
            continue
        if LIXO_RE.match(l):
            continue
        parsed = _parse_linha(l)
        if not parsed:
            continue
        # ignora preço zerado (placeholders de carrinho)
        if parsed["preco"].replace(" ", "") in ("R$0,00",):
            continue
        chave = (parsed["nome"].lower(), parsed["preco"], parsed["lote"].lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        tiers.append(parsed)

    # Descarta linhas-resumo ("a partir de R$ X") cujo preço já aparece
    # num tier detalhado (evita redundância), mas mantém quando o site só
    # oferece o resumo (ex: Bilheteria Digital).
    precos_detalhados = {t["preco"] for t in tiers if not t["resumo"]}
    tiers = [t for t in tiers if not (t["resumo"] and t["preco"] in precos_detalhados)]
    return tiers


def _extrair_cabecalho(driver):
    """Título, data e local do evento via meta tags / heurística."""
    try:
        return driver.execute_script(r"""
        function meta(p){const m=document.querySelector(`meta[property="${p}"], meta[name="${p}"]`);return m?m.content:'';}
        const titulo = meta('og:title') || (document.querySelector('h1,h2')||{}).innerText || document.title || '';
        return {titulo: (titulo||'').replace(/\s+/g,' ').trim()};
        """) or {}
    except Exception:
        return {}


async def extrair_detalhes(link, driver, cancelar):
    """Retorna dict com {titulo, tiers:[{nome,preco,lote,taxa}]} do ingresso."""
    driver.get(link)
    try:
        WebDriverWait(driver, 12).until(
            lambda d: PRECO_RE.search(d.find_element(By.TAG_NAME, "body").text)
            or d.find_elements(By.TAG_NAME, "iframe")
        )
    except Exception as e:
        logger.info(f"Detalhes: timeout aguardando página {link}: {e}")

    await cancelavel_sleep(2, cancelar)
    if cancelar.is_set():
        return {"titulo": "", "tiers": []}

    cab = _extrair_cabecalho(driver)
    tiers = _extrair_tiers(driver)
    return {"titulo": cab.get("titulo", ""), "tiers": tiers}
