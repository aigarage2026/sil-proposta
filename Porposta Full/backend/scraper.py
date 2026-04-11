"""
Sil-Proposta — Legislation Scraper
Scrapes DOU, SEFAZ portals, NF-e technical notes
+ Known SAP legislation database as fallback
"""
import httpx
import json
import os
import re
from datetime import datetime
from typing import List, Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ── Known SAP-relevant legislation (always available) ──
KNOWN_LEGISLATION = [
    {
        "nome": "NT 2019.001 v1.70 — Ajustes NF-e/NFC-e 4.0",
        "descricao": "Ajuste nas regras de validacao CST e Codigo de Beneficio Fiscal (cBenef). Inclusao de campo para cBenef com reducao de base de calculo (CST51) + diferimento. Cronograma de ativacao de RV para SP: Homologacao 12/01/2026, Producao 06/04/2026.",
        "url_fonte": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=tW+YMyk/50s=",
        "data_publicacao": "2025-11-15",
        "data_limite_homo": "2026-01-12",
        "data_limite_prod": "2026-04-06",
        "tipo": "federal",
        "fonte": "nfe_portal",
        "ufs_afetadas": ["SP"],
        "setores": ["Comercio", "Industria"],
        "impacto_sap": ["Config", "ABAP", "BAdI"],
    },
    {
        "nome": "NT 2025.003 — Novos campos obrigatorios NF-e 4.0",
        "descricao": "Inclusao de novos campos obrigatorios no XML da NF-e versao 4.0. Campos de rastreabilidade, informacoes de pagamento e dados adicionais de transporte. Requer atualizacao de layouts e BAdIs.",
        "url_fonte": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=tW+YMyk/50s=",
        "data_publicacao": "2026-01-15",
        "data_limite_homo": "2026-06-01",
        "data_limite_prod": "2026-09-01",
        "tipo": "federal",
        "fonte": "nfe_portal",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Comercio", "Industria"],
        "impacto_sap": ["Config", "ABAP", "BAdI"],
    },
    {
        "nome": "IN 1.608/2025-GO — tpIntegra obrigatorio",
        "descricao": "Instrucao Normativa de Goias exige campo tpIntegra=1 em operacoes interestaduais. Impacta BAdI de NF-e para preenchimento automatico do campo quando UF emitente = GO. Fase 2 com novos campos em Jul/2026.",
        "url_fonte": "https://www.sefaz.go.gov.br",
        "data_publicacao": "2025-08-01",
        "data_limite_homo": "2026-04-01",
        "data_limite_prod": "2026-07-01",
        "tipo": "estadual",
        "fonte": "sefaz_go",
        "ufs_afetadas": ["GO"],
        "setores": ["Comercio", "Industria"],
        "impacto_sap": ["ABAP", "BAdI", "Config"],
    },
    {
        "nome": "LC 214/2025 — Reforma Tributaria (IBS/CBS)",
        "descricao": "Lei Complementar da Reforma Tributaria. Substitui ICMS e ISS por IBS (estadual/municipal) e PIS/COFINS por CBS (federal). Cronograma: 2026=teste, 2027-2028=transicao, 2033=extincao ICMS. Impacto massivo em pricing, tax determination e compliance SAP.",
        "url_fonte": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm",
        "data_publicacao": "2025-01-16",
        "data_limite_homo": "2026-07-01",
        "data_limite_prod": "2027-01-01",
        "tipo": "federal",
        "fonte": "planalto",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Comercio", "Industria", "Servicos"],
        "impacto_sap": ["Config", "ABAP", "CPI", "BAdI"],
    },
    {
        "nome": "Lei 14.206 — Padrao Nacional NFS-e",
        "descricao": "Padrao nacional da Nota Fiscal de Servico eletronica (NFS-e). Municipios devem aderir ao sistema nacional ate Jul/2026. Impacta integracao SAP com prefeituras para emissao de NFS-e via API nacional.",
        "url_fonte": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14206.htm",
        "data_publicacao": "2025-06-01",
        "data_limite_homo": "2026-04-01",
        "data_limite_prod": "2026-07-01",
        "tipo": "municipal",
        "fonte": "planalto",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Servicos"],
        "impacto_sap": ["Config", "ABAP", "CPI"],
    },
    {
        "nome": "Portaria SRE 20/2026-SP — cBenef obrigatorio SP",
        "descricao": "Sao Paulo torna obrigatorio o preenchimento do campo cBenef (Codigo de Beneficio Fiscal) em todas as NF-e. Novas regras de validacao ativadas em producao em Jun/2026. Exige mapeamento NCM x cBenef.",
        "url_fonte": "https://www.fazenda.sp.gov.br",
        "data_publicacao": "2026-01-10",
        "data_limite_homo": "2026-03-01",
        "data_limite_prod": "2026-06-01",
        "tipo": "estadual",
        "fonte": "sefaz_sp",
        "ufs_afetadas": ["SP"],
        "setores": ["Comercio", "Industria"],
        "impacto_sap": ["Config", "ABAP", "BAdI"],
    },
    {
        "nome": "Convenio ICMS 235/2025 — Difal novas regras",
        "descricao": "Novas regras para calculo do Diferencial de Aliquota (DIFAL) nas operacoes interestaduais para consumidor final. Altera base de calculo e forma de recolhimento. Vigencia a partir de Ago/2026.",
        "url_fonte": "https://www.confaz.fazenda.gov.br",
        "data_publicacao": "2025-12-20",
        "data_limite_prod": "2026-08-01",
        "tipo": "estadual",
        "fonte": "confaz",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Comercio"],
        "impacto_sap": ["Config"],
    },
    {
        "nome": "eSocial S-1.3 — Eventos de SST obrigatorios",
        "descricao": "Nova versao do eSocial inclui eventos de Saude e Seguranca do Trabalho (SST) como obrigatorios para todas as empresas. Requer integracao SAP HCM com novos layouts de eventos S-2210, S-2220, S-2240.",
        "url_fonte": "https://www.gov.br/esocial",
        "data_publicacao": "2026-02-01",
        "data_limite_homo": "2026-06-01",
        "data_limite_prod": "2026-10-01",
        "tipo": "federal",
        "fonte": "gov_br",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Todos"],
        "impacto_sap": ["Config", "ABAP"],
    },
    {
        "nome": "Decreto 58.100/2026-RS — ICMS ST novos produtos",
        "descricao": "Rio Grande do Sul inclui novos grupos de produtos na Substituicao Tributaria de ICMS (materiais de construcao e autopecas). Impacta tabelas de determinacao de impostos e pricing no SAP.",
        "url_fonte": "https://www.sefaz.rs.gov.br",
        "data_publicacao": "2026-02-15",
        "data_limite_prod": "2026-07-01",
        "tipo": "estadual",
        "fonte": "sefaz_rs",
        "ufs_afetadas": ["RS"],
        "setores": ["Comercio", "Industria"],
        "impacto_sap": ["Config"],
    },
    {
        "nome": "Decreto Municipal 2026/45 — ISS Barueri servicos digitais",
        "descricao": "Municipio de Barueri/SP cria nova faixa de ISS para servicos digitais e SaaS (aliquota de 2.5%). Exige adequacao na determinacao de impostos e NFS-e para novos codigos de servico.",
        "url_fonte": "https://www.barueri.sp.gov.br",
        "data_publicacao": "2026-03-01",
        "data_limite_prod": "2026-06-01",
        "tipo": "municipal",
        "fonte": "prefeitura",
        "ufs_afetadas": ["SP"],
        "setores": ["Servicos"],
        "impacto_sap": ["Config"],
    },
    {
        "nome": "EFD-Reinf R-4000 Fase 2 — Novos eventos retencao",
        "descricao": "Segunda fase da EFD-Reinf inclui novos eventos de retencao (R-4040 pagamentos a cooperativas, R-4080 auto-retencao). Requer novos programas de integracao SAP com SPED.",
        "url_fonte": "https://www.gov.br/receitafederal",
        "data_publicacao": "2026-01-15",
        "data_limite_homo": "2026-05-01",
        "data_limite_prod": "2026-09-01",
        "tipo": "federal",
        "fonte": "receita_federal",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Todos"],
        "impacto_sap": ["Config", "ABAP", "CPI"],
    },
    {
        "nome": "IN RFB 2026/001 — Nota Fiscal de Energia Eletrica eletronica",
        "descricao": "Instituicao da NF3e (Nota Fiscal de Energia Eletrica eletronica) como documento fiscal obrigatorio. Distribuidoras e geradores devem emitir via sistema autorizado pela SEFAZ.",
        "url_fonte": "https://www.gov.br/receitafederal",
        "data_publicacao": "2026-02-01",
        "data_limite_homo": "2026-08-01",
        "data_limite_prod": "2027-01-01",
        "tipo": "federal",
        "fonte": "receita_federal",
        "ufs_afetadas": ["TODAS"],
        "setores": ["Energia"],
        "impacto_sap": ["Config", "ABAP"],
    },
]


async def scrape_dou(keywords=None, days_back=30):
    """Scrape DOU search - returns whatever is found."""
    if not keywords:
        keywords = ["nota tecnica NF-e", "ICMS cBenef", "reforma tributaria IBS"]
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://www.in.gov.br/consulta/-/buscar/dou",
                        params={"q": kw, "s": "do", "exactDate": "all"}
                    )
                    print(f"DOU '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200 and len(r.text) > 500:
                        # Try JSON embedded in page
                        json_match = re.search(r'var\s+_results?\s*=\s*(\[.*?\]);', r.text, re.DOTALL)
                        if json_match:
                            try:
                                items = json.loads(json_match.group(1))
                                for item in items[:5]:
                                    results.append({
                                        "nome": (item.get("title") or item.get("titulo") or "")[:200],
                                        "descricao": (item.get("content") or item.get("conteudo") or "")[:500],
                                        "url_fonte": "https://www.in.gov.br" + (item.get("urlTitle") or item.get("url") or ""),
                                        "data_publicacao": item.get("pubDate", datetime.now().isoformat()[:10]),
                                        "tipo": "federal",
                                        "fonte": "dou",
                                    })
                            except json.JSONDecodeError:
                                pass
                        # Fallback: extract from HTML
                        if not results:
                            html_matches = re.findall(
                                r'<a[^>]*href="(/web/dou/-/[^"]*)"[^>]*>([^<]{10,200})</a>',
                                r.text
                            )
                            for href, title in html_matches[:5]:
                                results.append({
                                    "nome": title.strip()[:200],
                                    "descricao": title.strip(),
                                    "url_fonte": "https://www.in.gov.br" + href,
                                    "data_publicacao": datetime.now().isoformat()[:10],
                                    "tipo": "federal",
                                    "fonte": "dou",
                                })
                except Exception as e:
                    print(f"DOU scrape error for '{kw}': {e}")
    except Exception as e:
        print(f"DOU scraper general error: {e}")
    print(f"DOU total results: {len(results)}")
    return results


async def scrape_nfe_portal():
    """Scrape NF-e technical notes portal."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=tW+YMyk/50s=")
            print(f"NFe portal: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                # Try multiple patterns
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>\s*(NT\s+\d{4}[\.\-]\d{3}[^<]*)</a>',
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*Nota\s+T[eé]cnica[^<]*)</a>',
                    r'>(NT\s*\d{4}[\.\-]\d{3}[^<]{0,100})<',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"NFe pattern matched: {len(matches)} results")
                        for match in matches[:10]:
                            if len(match) == 2:
                                href, title = match
                            else:
                                href, title = "", match[0] if isinstance(match, tuple) else match
                            full_url = href if href.startswith("http") else ("https://www.nfe.fazenda.gov.br/portal/" + href if href else "")
                            results.append({
                                "nome": title.strip()[:200],
                                "descricao": f"Nota Tecnica NF-e: {title.strip()}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "nfe_portal",
                            })
                        break
    except Exception as e:
        print(f"NF-e portal scraper error: {e}")
    print(f"NFe total results: {len(results)}")
    return results


async def scrape_confaz():
    """Scrape CONFAZ legislation."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.confaz.fazenda.gov.br/legislacao/convenios")
            print(f"CONFAZ: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Conv[eê]nio|Protocolo|Ajuste\s+SINIEF)[^<]*)</a>',
                    r'>(\s*Conv[eê]nio\s+ICMS\s+\d+/\d+[^<]*)<',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"CONFAZ pattern matched: {len(matches)} results")
                        for match in matches[:10]:
                            if len(match) == 2:
                                href, title = match
                            else:
                                href, title = "", match[0] if isinstance(match, tuple) else match
                            full_url = href if href.startswith("http") else ("https://www.confaz.fazenda.gov.br" + href if href else "")
                            results.append({
                                "nome": title.strip()[:200],
                                "descricao": f"CONFAZ: {title.strip()}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "estadual",
                                "fonte": "confaz",
                            })
                        break
    except Exception as e:
        print(f"CONFAZ scraper error: {e}")
    print(f"CONFAZ total results: {len(results)}")
    return results


async def scrape_planalto():
    """Scrape Portal da Legislação — Planalto (Leis Complementares e Ordinárias recentes)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www4.planalto.gov.br/legislacao")
            print(f"Planalto: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Lei\s+Complementar|Lei\s+n|Decreto\s+n|Medida\s+Provis|Emenda\s+Constitucional)[^<]*)</a>',
                    r'<a[^>]*href="(/ccivil_03[^"]*)"[^>]*>([^<]{10,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"Planalto pattern matched: {len(matches)} results")
                        for href, title in matches[:10]:
                            full_url = href if href.startswith("http") else "https://www4.planalto.gov.br" + href
                            results.append({
                                "nome": title.strip()[:200],
                                "descricao": f"Legislação Federal: {title.strip()}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "planalto",
                            })
                        break
    except Exception as e:
        print(f"Planalto scraper error: {e}")
    print(f"Planalto total results: {len(results)}")
    return results


async def scrape_normas_leg():
    """Scrape normas.leg.br — Pesquisa de Normas Jurídicas."""
    results = []
    keywords = ["reforma tributária", "nota fiscal eletrônica", "ICMS", "IBS CBS"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://normas.leg.br/",
                        params={"q": kw}
                    )
                    print(f"Normas.leg '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        matches = re.findall(
                            r'<a[^>]*href="(/norma/[^"]*)"[^>]*>([^<]{10,300})</a>',
                            r.text, re.IGNORECASE
                        )
                        for href, title in matches[:5]:
                            results.append({
                                "nome": title.strip()[:200],
                                "descricao": f"Norma jurídica: {title.strip()}",
                                "url_fonte": "https://normas.leg.br" + href,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "normas_leg",
                            })
                except Exception as e:
                    print(f"Normas.leg error for '{kw}': {e}")
    except Exception as e:
        print(f"Normas.leg general error: {e}")
    print(f"Normas.leg total results: {len(results)}")
    return results


async def scrape_lexml():
    """Scrape LexML Brasil — busca integrada de legislação."""
    results = []
    keywords = ["reforma tributária IBS", "nota fiscal eletrônica", "SPED obrigações acessórias"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://www.lexml.gov.br/busca/search",
                        params={"keyword": kw, "f.tipoDocumento": "Legislação"}
                    )
                    print(f"LexML '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="(https?://www\.lexml\.gov\.br/urn/[^"]*)"[^>]*>([^<]{10,300})</a>',
                            r'<a[^>]*href="(/urn/[^"]*)"[^>]*>([^<]{10,300})</a>',
                            r'class="titulo"[^>]*>([^<]{10,300})<',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            if matches:
                                for match in matches[:5]:
                                    if len(match) == 2:
                                        href, title = match
                                    else:
                                        href, title = "", match[0] if isinstance(match, tuple) else match
                                    full_url = href if href.startswith("http") else "https://www.lexml.gov.br" + href if href else ""
                                    results.append({
                                        "nome": title.strip()[:200],
                                        "descricao": f"LexML: {title.strip()}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "federal",
                                        "fonte": "lexml",
                                    })
                                break
                except Exception as e:
                    print(f"LexML error for '{kw}': {e}")
    except Exception as e:
        print(f"LexML general error: {e}")
    print(f"LexML total results: {len(results)}")
    return results


async def scrape_sped():
    """Scrape Portal SPED — Sistema Público de Escrituração Digital."""
    results = []
    pages = [
        ("http://sped.rfb.gov.br/pagina/show/1494", "EFD-ICMS/IPI"),
        ("http://sped.rfb.gov.br/pagina/show/1516", "EFD-Contribuições"),
        ("http://sped.rfb.gov.br/pagina/show/1644", "EFD-Reinf"),
    ]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for url, modulo in pages:
                try:
                    r = await client.get(url)
                    print(f"SPED {modulo}: status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        matches = re.findall(
                            r'<a[^>]*href="(/pagina/show/\d+)"[^>]*>([^<]{10,200})</a>',
                            r.text, re.IGNORECASE
                        )
                        if not matches:
                            matches = re.findall(
                                r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Guia|Leiaute|Nota\s+T|Manual|Tabela)[^<]*)</a>',
                                r.text, re.IGNORECASE
                            )
                        for href, title in matches[:5]:
                            full_url = href if href.startswith("http") else "http://sped.rfb.gov.br" + href
                            results.append({
                                "nome": f"SPED {modulo}: {title.strip()[:180]}",
                                "descricao": f"Portal SPED — {modulo}: {title.strip()}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "sped_rfb",
                            })
                except Exception as e:
                    print(f"SPED {modulo} error: {e}")
    except Exception as e:
        print(f"SPED general error: {e}")
    print(f"SPED total results: {len(results)}")
    return results


async def scrape_esocial():
    """Scrape eSocial — Documentação Técnica."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.gov.br/esocial/pt-br/documentacao-tecnica")
            print(f"eSocial: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Leiaute|Manual|Nota\s+T|Vers[aã]o|S-\d|Layout)[^<]*)</a>',
                    r'<a[^>]*href="(https://www\.gov\.br/esocial[^"]*)"[^>]*>([^<]{10,200})</a>',
                    r'<a[^>]*href="([^"]*documentacao-tecnica[^"]*)"[^>]*>([^<]{10,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"eSocial pattern matched: {len(matches)} results")
                        for href, title in matches[:10]:
                            full_url = href if href.startswith("http") else "https://www.gov.br" + href
                            results.append({
                                "nome": f"eSocial: {title.strip()[:180]}",
                                "descricao": f"eSocial Documentação Técnica: {title.strip()}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "esocial",
                            })
                        break
    except Exception as e:
        print(f"eSocial scraper error: {e}")
    print(f"eSocial total results: {len(results)}")
    return results


async def scrape_reforma_rfb():
    """Scrape Receita Federal — Reforma do Consumo (IBS/CBS)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-consumo")
            print(f"Reforma RFB: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:IBS|CBS|Split\s+Payment|Reforma|Regulamenta|Tribut)[^<]*)</a>',
                    r'<a[^>]*href="(https://www\.gov\.br/receitafederal[^"]*reforma[^"]*)"[^>]*>([^<]{10,200})</a>',
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]{15,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"Reforma RFB pattern matched: {len(matches)} results")
                        for href, title in matches[:10]:
                            title_clean = title.strip()
                            if len(title_clean) < 10 or title_clean.lower() in ("saiba mais", "clique aqui", "acesse"):
                                continue
                            full_url = href if href.startswith("http") else "https://www.gov.br" + href
                            results.append({
                                "nome": f"Reforma Tributária RFB: {title_clean[:170]}",
                                "descricao": f"Receita Federal — Reforma do Consumo: {title_clean}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "federal",
                                "fonte": "reforma_rfb",
                            })
                        break
    except Exception as e:
        print(f"Reforma RFB scraper error: {e}")
    print(f"Reforma RFB total results: {len(results)}")
    return results


async def scrape_reforma_portais():
    """Scrape portais independentes da Reforma Tributária (.com e .org.br)."""
    results = []
    portais = [
        ("https://www.reformatributaria.com/", "reformatributaria.com"),
        ("https://www.reformatributaria.org.br", "reformatributaria.org.br"),
    ]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for url, fonte in portais:
                try:
                    r = await client.get(url)
                    print(f"{fonte}: status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:IBS|CBS|Reforma|Tribut|Split|Regulamenta|Imposto\s+Seletivo)[^<]*)</a>',
                            r'<h[23][^>]*>([^<]*(?:IBS|CBS|Reforma|Tribut)[^<]*)</h[23]>',
                            r'<a[^>]*href="([^"]*(?:artigo|noticia|post|blog)[^"]*)"[^>]*>([^<]{15,200})</a>',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            if matches:
                                for match in matches[:5]:
                                    if len(match) == 2:
                                        href, title = match
                                    else:
                                        href, title = "", match[0] if isinstance(match, tuple) else match
                                    title_clean = title.strip()
                                    if len(title_clean) < 10:
                                        continue
                                    full_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/") if href else url
                                    results.append({
                                        "nome": title_clean[:200],
                                        "descricao": f"Reforma Tributária ({fonte}): {title_clean}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "federal",
                                        "fonte": fonte,
                                    })
                                break
                except Exception as e:
                    print(f"{fonte} error: {e}")
    except Exception as e:
        print(f"Reforma portais general error: {e}")
    print(f"Reforma portais total results: {len(results)}")
    return results


async def scrape_camara():
    """Scrape Câmara dos Deputados — proposições tributárias."""
    results = []
    keywords = ["reforma tributária", "nota fiscal eletrônica", "IBS CBS"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://www.camara.leg.br/busca-portal/proposicoes/pesquisa-simplificada",
                        params={"termo": kw, "order": "data", "d": "DESC"}
                    )
                    print(f"Câmara '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="(https://www\.camara\.leg\.br/proposicoes[^"]*)"[^>]*>([^<]{10,200})</a>',
                            r'<a[^>]*href="(/proposicoes/\d+)"[^>]*>([^<]{10,200})</a>',
                            r'<a[^>]*href="([^"]*proposicoes[^"]*)"[^>]*>([^<]*(?:PL|PLP|PEC|MP)[^<]*)</a>',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            if matches:
                                for href, title in matches[:5]:
                                    full_url = href if href.startswith("http") else "https://www.camara.leg.br" + href
                                    results.append({
                                        "nome": title.strip()[:200],
                                        "descricao": f"Câmara dos Deputados: {title.strip()}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "federal",
                                        "fonte": "camara",
                                    })
                                break
                except Exception as e:
                    print(f"Câmara error for '{kw}': {e}")
    except Exception as e:
        print(f"Câmara general error: {e}")
    print(f"Câmara total results: {len(results)}")
    return results


async def scrape_senado():
    """Scrape Senado Federal — proposições e legislação."""
    results = []
    keywords = ["reforma tributária", "IBS CBS", "nota fiscal"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://www25.senado.leg.br/web/atividade/materias",
                        params={"q": kw, "p": "1"}
                    )
                    print(f"Senado '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="(https://www25\.senado\.leg\.br/web/atividade/materias/-/materia/\d+)"[^>]*>([^<]{10,200})</a>',
                            r'<a[^>]*href="(/web/atividade/materias/-/materia/\d+)"[^>]*>([^<]{10,200})</a>',
                            r'<a[^>]*href="([^"]*materia[^"]*)"[^>]*>([^<]*(?:PL|PLP|PEC|MP)\s+\d+[^<]*)</a>',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            if matches:
                                for href, title in matches[:5]:
                                    full_url = href if href.startswith("http") else "https://www25.senado.leg.br" + href
                                    results.append({
                                        "nome": title.strip()[:200],
                                        "descricao": f"Senado Federal: {title.strip()}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "federal",
                                        "fonte": "senado",
                                    })
                                break
                except Exception as e:
                    print(f"Senado error for '{kw}': {e}")
    except Exception as e:
        print(f"Senado general error: {e}")
    print(f"Senado total results: {len(results)}")
    return results


# ══════════════════════════════════════════════════════════
# SCRAPERS ESTADUAIS
# ══════════════════════════════════════════════════════════

SEFAZ_PORTALS = [
    {"uf": "SP", "url": "https://portal.fazenda.sp.gov.br/", "base": "https://portal.fazenda.sp.gov.br", "fonte": "sefaz_sp"},
    {"uf": "RJ", "url": "https://www.fazenda.rj.gov.br/", "base": "https://www.fazenda.rj.gov.br", "fonte": "sefaz_rj"},
    {"uf": "MG", "url": "https://www.fazenda.mg.gov.br/", "base": "https://www.fazenda.mg.gov.br", "fonte": "sefaz_mg"},
    {"uf": "RS", "url": "https://www.sefaz.rs.gov.br/", "base": "https://www.sefaz.rs.gov.br", "fonte": "sefaz_rs"},
    {"uf": "PR", "url": "https://www.sefaz.pr.gov.br/", "base": "https://www.sefaz.pr.gov.br", "fonte": "sefaz_pr"},
    {"uf": "SC", "url": "https://www.sefaz.sc.gov.br/", "base": "https://www.sefaz.sc.gov.br", "fonte": "sefaz_sc"},
    {"uf": "BA", "url": "https://www.sefaz.ba.gov.br/", "base": "https://www.sefaz.ba.gov.br", "fonte": "sefaz_ba"},
    {"uf": "PE", "url": "https://www.sefaz.pe.gov.br/", "base": "https://www.sefaz.pe.gov.br", "fonte": "sefaz_pe"},
    {"uf": "CE", "url": "https://www.sefaz.ce.gov.br/", "base": "https://www.sefaz.ce.gov.br", "fonte": "sefaz_ce"},
    {"uf": "MT", "url": "https://www.sefaz.mt.gov.br/", "base": "https://www.sefaz.mt.gov.br", "fonte": "sefaz_mt"},
    {"uf": "GO", "url": "https://www.sefaz.go.gov.br/", "base": "https://www.sefaz.go.gov.br", "fonte": "sefaz_go"},
]


async def scrape_sefaz_all():
    """Scrape all state SEFAZ portals for ICMS, NF-e and fiscal legislation."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
            for portal in SEFAZ_PORTALS:
                uf = portal["uf"]
                try:
                    r = await client.get(portal["url"])
                    print(f"SEFAZ-{uf}: status={r.status_code} len={len(r.text)}")
                    if r.status_code != 200:
                        continue
                    patterns = [
                        r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:ICMS|NF-e|NFC-e|Decreto|Portaria|Resolução|Instrução|RICMS|Substituição|DIFAL|cBenef|Regulament)[^<]*)</a>',
                        r'<a[^>]*href="([^"]*(?:legislacao|decreto|portaria|resolucao|icms)[^"]*)"[^>]*>([^<]{15,200})</a>',
                        r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Lei\s+n|Decreto\s+n|Portaria\s+n|Resolução\s+n)[^<]*)</a>',
                    ]
                    found = False
                    for pattern in patterns:
                        matches = re.findall(pattern, r.text, re.IGNORECASE)
                        if matches:
                            print(f"SEFAZ-{uf} matched: {len(matches)} results")
                            for href, title in matches[:8]:
                                title_clean = title.strip()
                                if len(title_clean) < 10:
                                    continue
                                full_url = href if href.startswith("http") else portal["base"] + "/" + href.lstrip("/")
                                results.append({
                                    "nome": f"[{uf}] {title_clean[:190]}",
                                    "descricao": f"SEFAZ-{uf}: {title_clean}",
                                    "url_fonte": full_url,
                                    "data_publicacao": datetime.now().isoformat()[:10],
                                    "tipo": "estadual",
                                    "fonte": portal["fonte"],
                                    "ufs_afetadas": [uf],
                                })
                            found = True
                            break
                    if not found:
                        # Fallback: extract any legislation-looking links
                        fallback = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>([^<]{20,200})</a>', r.text)
                        for href, title in fallback[:3]:
                            title_clean = title.strip()
                            if any(kw in title_clean.lower() for kw in ["icms", "nf-e", "decreto", "portaria", "legisla", "fiscal", "tribut"]):
                                full_url = href if href.startswith("http") else portal["base"] + "/" + href.lstrip("/")
                                results.append({
                                    "nome": f"[{uf}] {title_clean[:190]}",
                                    "descricao": f"SEFAZ-{uf}: {title_clean}",
                                    "url_fonte": full_url,
                                    "data_publicacao": datetime.now().isoformat()[:10],
                                    "tipo": "estadual",
                                    "fonte": portal["fonte"],
                                    "ufs_afetadas": [uf],
                                })
                except Exception as e:
                    print(f"SEFAZ-{uf} error: {e}")
    except Exception as e:
        print(f"SEFAZ all general error: {e}")
    print(f"SEFAZ all total results: {len(results)}")
    return results


async def scrape_al_sp():
    """Scrape Assembleia Legislativa de São Paulo — projetos de lei estaduais."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.al.sp.gov.br/alesp/pesquisa-legislacao/")
            print(f"AL-SP: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Lei\s+Complementar|Lei\s+n|Decreto\s+n|Projeto\s+de\s+Lei|ICMS|Tribut)[^<]*)</a>',
                    r'<a[^>]*href="(/alesp/[^"]*legislacao[^"]*)"[^>]*>([^<]{15,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"AL-SP matched: {len(matches)} results")
                        for href, title in matches[:8]:
                            title_clean = title.strip()
                            if len(title_clean) < 10:
                                continue
                            full_url = href if href.startswith("http") else "https://www.al.sp.gov.br" + href
                            results.append({
                                "nome": f"[SP] AL-SP: {title_clean[:180]}",
                                "descricao": f"Assembleia Legislativa SP: {title_clean}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "estadual",
                                "fonte": "al_sp",
                                "ufs_afetadas": ["SP"],
                            })
                        break
    except Exception as e:
        print(f"AL-SP scraper error: {e}")
    print(f"AL-SP total results: {len(results)}")
    return results


async def scrape_imprensa_oficial_sp():
    """Scrape Imprensa Oficial de SP — Diário Oficial do Estado."""
    results = []
    keywords = ["ICMS", "NF-e", "tributário", "fiscal"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://www.imprensaoficial.com.br/",
                        params={"busca": kw}
                    )
                    print(f"Imprensa Oficial SP '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:Decreto|Portaria|Resolução|Lei\s+n|ICMS|Tribut|Fiscal)[^<]*)</a>',
                            r'<a[^>]*href="(/DO/[^"]*)"[^>]*>([^<]{15,200})</a>',
                            r'<a[^>]*href="([^"]*)"[^>]*>([^<]{20,200})</a>',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            filtered = [(h, t) for h, t in matches if any(
                                k in t.lower() for k in ["icms", "decreto", "portaria", "tribut", "fiscal", "nf-e", "lei"]
                            )] if pattern == patterns[-1] else matches
                            if filtered:
                                for href, title in filtered[:5]:
                                    title_clean = title.strip()
                                    if len(title_clean) < 10:
                                        continue
                                    full_url = href if href.startswith("http") else "https://www.imprensaoficial.com.br" + href
                                    results.append({
                                        "nome": f"[SP] DOE-SP: {title_clean[:180]}",
                                        "descricao": f"Diário Oficial SP: {title_clean}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "estadual",
                                        "fonte": "imprensa_oficial_sp",
                                        "ufs_afetadas": ["SP"],
                                    })
                                break
                except Exception as e:
                    print(f"Imprensa Oficial SP error for '{kw}': {e}")
    except Exception as e:
        print(f"Imprensa Oficial SP general error: {e}")
    print(f"Imprensa Oficial SP total results: {len(results)}")
    return results


# ══════════════════════════════════════════════════════════
# SCRAPERS MUNICIPAIS
# ══════════════════════════════════════════════════════════

async def scrape_leis_municipais():
    """Scrape leismunicipais.com.br — portal de legislação municipal."""
    results = []
    keywords = ["ISS", "NFS-e", "nota fiscal serviço", "tributário municipal"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for kw in keywords[:3]:
                try:
                    r = await client.get(
                        "https://leismunicipais.com.br/",
                        params={"q": kw}
                    )
                    print(f"LeisMunicipais '{kw}': status={r.status_code} len={len(r.text)}")
                    if r.status_code == 200:
                        patterns = [
                            r'<a[^>]*href="(https://leismunicipais\.com\.br/[^"]*)"[^>]*>([^<]{15,200})</a>',
                            r'<a[^>]*href="(/[a-z][^"]*)"[^>]*>([^<]*(?:Lei\s+n|Decreto\s+n|ISS|NFS-e|Tribut|Fiscal)[^<]*)</a>',
                        ]
                        for pattern in patterns:
                            matches = re.findall(pattern, r.text, re.IGNORECASE)
                            if matches:
                                for href, title in matches[:5]:
                                    title_clean = title.strip()
                                    if len(title_clean) < 10:
                                        continue
                                    full_url = href if href.startswith("http") else "https://leismunicipais.com.br" + href
                                    results.append({
                                        "nome": title_clean[:200],
                                        "descricao": f"Legislação Municipal: {title_clean}",
                                        "url_fonte": full_url,
                                        "data_publicacao": datetime.now().isoformat()[:10],
                                        "tipo": "municipal",
                                        "fonte": "leis_municipais",
                                    })
                                break
                except Exception as e:
                    print(f"LeisMunicipais error for '{kw}': {e}")
    except Exception as e:
        print(f"LeisMunicipais general error: {e}")
    print(f"LeisMunicipais total results: {len(results)}")
    return results


async def scrape_diario_municipal():
    """Scrape diariomunicipal.com.br — Diário Oficial dos Municípios."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.diariomunicipal.com.br/")
            print(f"Diário Municipal: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:ISS|NFS-e|Tribut|Fiscal|Decreto|Lei\s+Municipal|Taxa)[^<]*)</a>',
                    r'<a[^>]*href="(https://www\.diariomunicipal\.com\.br/[^"]*)"[^>]*>([^<]{15,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"Diário Municipal matched: {len(matches)} results")
                        for href, title in matches[:8]:
                            title_clean = title.strip()
                            if len(title_clean) < 10:
                                continue
                            full_url = href if href.startswith("http") else "https://www.diariomunicipal.com.br" + href
                            results.append({
                                "nome": title_clean[:200],
                                "descricao": f"Diário Oficial Municipal: {title_clean}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "municipal",
                                "fonte": "diario_municipal",
                            })
                        break
    except Exception as e:
        print(f"Diário Municipal scraper error: {e}")
    print(f"Diário Municipal total results: {len(results)}")
    return results


async def scrape_prefeitura_sp():
    """Scrape Prefeitura de São Paulo — legislação tributária municipal."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            # Página de legislação tributária
            urls_to_try = [
                "https://www.prefeitura.sp.gov.br/cidade/secretarias/fazenda/legislacao/index.php",
                "https://www.prefeitura.sp.gov.br/cidade/secretarias/fazenda/",
                "https://www.prefeitura.sp.gov.br/",
            ]
            for url in urls_to_try:
                try:
                    r = await client.get(url)
                    print(f"Prefeitura SP ({url.split('/')[-1] or 'home'}): status={r.status_code} len={len(r.text)}")
                    if r.status_code != 200:
                        continue
                    patterns = [
                        r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:ISS|NFS-e|IPTU|Decreto\s+Municipal|Lei\s+Municipal|Tribut|Código\s+Tributário|Taxa)[^<]*)</a>',
                        r'<a[^>]*href="([^"]*(?:fazenda|tribut|legislacao)[^"]*)"[^>]*>([^<]{15,200})</a>',
                    ]
                    for pattern in patterns:
                        matches = re.findall(pattern, r.text, re.IGNORECASE)
                        if matches:
                            for href, title in matches[:8]:
                                title_clean = title.strip()
                                if len(title_clean) < 10:
                                    continue
                                full_url = href if href.startswith("http") else "https://www.prefeitura.sp.gov.br" + href
                                results.append({
                                    "nome": f"[SP Capital] {title_clean[:185]}",
                                    "descricao": f"Prefeitura SP: {title_clean}",
                                    "url_fonte": full_url,
                                    "data_publicacao": datetime.now().isoformat()[:10],
                                    "tipo": "municipal",
                                    "fonte": "prefeitura_sp",
                                    "ufs_afetadas": ["SP"],
                                })
                            break
                    if results:
                        break
                except Exception as e:
                    print(f"Prefeitura SP error for {url}: {e}")
    except Exception as e:
        print(f"Prefeitura SP general error: {e}")
    print(f"Prefeitura SP total results: {len(results)}")
    return results


async def scrape_abrasf():
    """Scrape ABRASF — Associação Brasileira das Secretarias de Finanças (NFS-e nacional)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.abrasf.org.br/")
            print(f"ABRASF: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:NFS-e|Nota\s+Fiscal\s+de\s+Serviço|Padrão\s+Nacional|ISS|Layout|Modelo\s+Conceitual|Versão)[^<]*)</a>',
                    r'<a[^>]*href="(https://www\.abrasf\.org\.br/[^"]*)"[^>]*>([^<]{15,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"ABRASF matched: {len(matches)} results")
                        for href, title in matches[:8]:
                            title_clean = title.strip()
                            if len(title_clean) < 10:
                                continue
                            full_url = href if href.startswith("http") else "https://www.abrasf.org.br/" + href.lstrip("/")
                            results.append({
                                "nome": f"ABRASF: {title_clean[:190]}",
                                "descricao": f"ABRASF — NFS-e Nacional: {title_clean}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "municipal",
                                "fonte": "abrasf",
                            })
                        break
    except Exception as e:
        print(f"ABRASF scraper error: {e}")
    print(f"ABRASF total results: {len(results)}")
    return results


async def scrape_cnm():
    """Scrape CNM — Confederação Nacional de Municípios (tributação municipal)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            r = await client.get("https://www.cnm.org.br/")
            print(f"CNM: status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:ISS|NFS-e|Tribut|Fiscal|Reforma|IBS|Municipal|Repasse)[^<]*)</a>',
                    r'<a[^>]*href="(https://www\.cnm\.org\.br/[^"]*(?:comunicacao|biblioteca|cms)[^"]*)"[^>]*>([^<]{15,200})</a>',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, r.text, re.IGNORECASE)
                    if matches:
                        print(f"CNM matched: {len(matches)} results")
                        for href, title in matches[:8]:
                            title_clean = title.strip()
                            if len(title_clean) < 10:
                                continue
                            full_url = href if href.startswith("http") else "https://www.cnm.org.br/" + href.lstrip("/")
                            results.append({
                                "nome": f"CNM: {title_clean[:190]}",
                                "descricao": f"CNM — Municípios: {title_clean}",
                                "url_fonte": full_url,
                                "data_publicacao": datetime.now().isoformat()[:10],
                                "tipo": "municipal",
                                "fonte": "cnm",
                            })
                        break
    except Exception as e:
        print(f"CNM scraper error: {e}")
    print(f"CNM total results: {len(results)}")
    return results


async def classify_with_ai(items, api_key):
    """Use OpenAI to classify and enrich scraped items."""
    if not api_key or not items:
        return items
    enriched = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for item in items:
                # Skip items that already have full classification (known legislation)
                if item.get("impacto_sap") and item.get("ufs_afetadas"):
                    enriched.append(item)
                    continue
                prompt = f"""Analise esta legislacao brasileira e retorne um JSON com:
- tipo: "municipal", "estadual" ou "federal"
- setores: array com setores afetados (ex: ["Comercio", "Industria", "Servicos"])
- impacto_sap: array com tipos de impacto SAP (ex: ["Config", "ABAP", "BAdI", "CPI"])
- data_limite_homo: data limite homologacao (YYYY-MM-DD) ou null
- data_limite_prod: data limite producao (YYYY-MM-DD) ou null
- ufs_afetadas: array de UFs (ex: ["SP", "GO"]) ou ["TODAS"]
- descricao_curta: resumo em 1-2 frases do impacto para projetos SAP

Legislacao:
Nome: {item.get('nome','')}
Descricao: {item.get('descricao','')[:800]}

Responda APENAS o JSON, sem markdown."""
                try:
                    r = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                              "temperature": 0.2, "max_tokens": 500}
                    )
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"].strip()
                        content = re.sub(r'^```json\s*', '', content)
                        content = re.sub(r'\s*```$', '', content)
                        ai_data = json.loads(content)
                        item["tipo"] = ai_data.get("tipo", item.get("tipo", "federal"))
                        item["setores"] = ai_data.get("setores", [])
                        item["impacto_sap"] = ai_data.get("impacto_sap", [])
                        item["data_limite_homo"] = ai_data.get("data_limite_homo")
                        item["data_limite_prod"] = ai_data.get("data_limite_prod")
                        item["ufs_afetadas"] = ai_data.get("ufs_afetadas", ["TODAS"])
                        if ai_data.get("descricao_curta"):
                            item["descricao"] = ai_data["descricao_curta"]
                except Exception as e:
                    print(f"AI classify error for '{item.get('nome','')}': {e}")
                enriched.append(item)
    except Exception as e:
        print(f"AI classifier general error: {e}")
        return items
    return enriched


async def scrape_urls(urls: list) -> list:
    """Scrape specific URLs provided by the user, extract text and title."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=HEADERS) as client:
            for url in urls[:10]:  # max 10 URLs
                try:
                    r = await client.get(url)
                    print(f"URL scrape: {url} -> status={r.status_code} len={len(r.text)}")
                    if r.status_code != 200:
                        continue
                    text = r.text
                    # Extract title
                    title_match = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else url.split("/")[-1][:100]
                    # Extract main text content — strip HTML tags
                    # Remove script/style blocks
                    clean = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '', text, flags=re.DOTALL|re.IGNORECASE)
                    # Remove HTML tags
                    clean = re.sub(r'<[^>]+>', ' ', clean)
                    # Collapse whitespace
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    # Take first 3000 chars as description
                    desc = clean[:3000]
                    # Detect type from URL
                    tipo = "federal"
                    url_lower = url.lower()
                    if "sefaz" in url_lower or "fazenda" in url_lower and ".gov.br" in url_lower:
                        # Check for state SEFAZ
                        uf_match = re.search(r'sefaz\.([a-z]{2})\.gov|fazenda\.([a-z]{2})\.gov', url_lower)
                        if uf_match:
                            tipo = "estadual"
                    if "prefeitura" in url_lower or "municipio" in url_lower or ".barueri." in url_lower:
                        tipo = "municipal"
                    if "confaz" in url_lower:
                        tipo = "estadual"

                    results.append({
                        "nome": title[:200],
                        "descricao": desc[:500],
                        "texto_completo": desc[:3000],
                        "url_fonte": url,
                        "data_publicacao": datetime.now().isoformat()[:10],
                        "tipo": tipo,
                        "fonte": "url",
                    })
                except Exception as e:
                    print(f"URL scrape error for {url}: {e}")
    except Exception as e:
        print(f"URL scraper general error: {e}")
    return results


def _normalize_key(nome: str) -> str:
    """Normalize a legislation name into a dedup key.
    Strips prefixes like [SP], removes accents, punctuation, extra spaces,
    and extracts the core identifier (e.g. 'nt 2024 002', 'lc 214 2021',
    'in 1608 2025', 'decreto 58100 2026', 'convenio icms 235 2025').
    """
    import unicodedata
    text = nome.lower().strip()
    # Remove UF prefix like [SP], [GO], etc.
    text = re.sub(r'^\[[A-Za-z]{2}\]\s*', '', text)
    # Remove source prefixes like "SEFAZ-SP:", "DOE-SP:", "ABRASF:", etc.
    text = re.sub(r'^[A-Za-z\u00C0-\u00FF\-]+:\s*', '', text)
    # Remove accents
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    # Try to extract known patterns: "NT 2024.002", "LC 214/2021", "IN 1608/2025", etc.
    patterns = [
        r'(nt\s*\d{4}[\.\-\s]*\d{2,3})',                          # NT 2024.002
        r'(lc?\s*\d{1,4}\s*/?\s*\d{4})',                           # LC 214/2021
        r'(in\s*\d{1,5}\s*/?\s*\d{4})',                            # IN 1608/2025
        r'(decreto\s*(?:municipal\s*)?\d{1,6}\s*/?\s*\d{4})',      # Decreto 58100/2026
        r'(portaria\s*(?:sre\s*)?\d{1,5}\s*/?\s*\d{4})',           # Portaria SRE 20/2026
        r'(convenio\s*icms\s*\d{1,5}\s*/?\s*\d{4})',               # Convênio ICMS 235/2025
        r'(lei\s*\d{1,6}(?:\s*/?\s*\d{4})?)',                      # Lei 14206
        r'(efd[\s\-]*reinf\s*r[\s\-]*\d{4})',                      # EFD-Reinf R-4000
        r'(esocial\s*s[\s\-]*\d[\.\d]*)',                           # eSocial S-1.3
        r'(nf3?s?-?e)',                                             # NFS-e / NF-e / NF3e
        r'(pl[cp]?\s+\d{1,5}\s*/?\s*\d{4})',                       # PL, PLP, PLC
        r'(pec\s+\d{1,5}\s*/?\s*\d{4})',                           # PEC
        r'(mp\s+\d{1,5}\s*/?\s*\d{4})',                            # MP
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            # Normalize: keep only alphanumeric
            return re.sub(r'[^a-z0-9]', '', m.group(1))
    # Fallback: strip all non-alnum chars, take first 60
    return re.sub(r'[^a-z0-9]', '', text)[:60]


def _deduplicate_and_merge(items: list) -> list:
    """Deduplicate legislation items, merging those that refer to the same law.
    When duplicates are found:
    - Keep the item with the richest data (most fields filled)
    - Aggregate all sources (fontes) into a comma-separated list
    - Merge ufs_afetadas, setores, and impacto_sap arrays
    - Keep the longest description
    - Keep earliest dates (data_publicacao) and latest deadlines
    """
    buckets: dict = {}  # key -> merged item
    for item in items:
        nome = item.get("nome", "").strip()
        if not nome:
            continue
        key = _normalize_key(nome)
        if not key:
            continue

        if key not in buckets:
            buckets[key] = dict(item)
            buckets[key]["_fontes"] = {item.get("fonte", "")}
            buckets[key]["_urls"] = {item.get("url_fonte", "")}
            continue

        existing = buckets[key]

        # Aggregate sources
        existing["_fontes"].add(item.get("fonte", ""))
        existing["_urls"].add(item.get("url_fonte", ""))

        # Keep longer description
        new_desc = item.get("descricao", "")
        if len(new_desc) > len(existing.get("descricao", "")):
            existing["descricao"] = new_desc

        # Keep the nome that is more descriptive (longer, but not absurdly so)
        new_nome = item.get("nome", "")
        old_nome = existing.get("nome", "")
        if len(new_nome) > len(old_nome) and len(new_nome) < 250:
            existing["nome"] = new_nome

        # Merge array fields
        for field in ("ufs_afetadas", "setores", "impacto_sap"):
            old_vals = existing.get(field) or []
            new_vals = item.get(field) or []
            if isinstance(old_vals, str):
                old_vals = [old_vals]
            if isinstance(new_vals, str):
                new_vals = [new_vals]
            merged = list(dict.fromkeys(old_vals + new_vals))  # preserve order, no dupes
            if merged:
                existing[field] = merged

        # Keep earliest publication date
        new_pub = item.get("data_publicacao", "")
        old_pub = existing.get("data_publicacao", "")
        if new_pub and old_pub and new_pub < old_pub:
            existing["data_publicacao"] = new_pub

        # Keep latest deadlines (most conservative)
        for date_field in ("data_limite_homo", "data_limite_prod"):
            new_date = item.get(date_field, "")
            old_date = existing.get(date_field, "")
            if new_date and (not old_date or new_date > old_date):
                existing[date_field] = new_date

        # Fill missing fields from the new item
        for k, v in item.items():
            if k not in existing or not existing[k]:
                existing[k] = v

    # Finalize: set fonte to aggregated sources
    result = []
    for item in buckets.values():
        fontes = item.pop("_fontes", set())
        urls = item.pop("_urls", set())
        fontes_clean = sorted(f for f in fontes if f)
        urls_clean = sorted(u for u in urls if u)
        if len(fontes_clean) > 1:
            item["fonte"] = ", ".join(fontes_clean)
        # If multiple source URLs, keep the most official one, store others in description
        if len(urls_clean) > 1:
            # Prefer .gov.br URLs
            gov_urls = [u for u in urls_clean if ".gov.br" in u]
            item["url_fonte"] = gov_urls[0] if gov_urls else urls_clean[0]
            other_urls = [u for u in urls_clean if u != item["url_fonte"]]
            if other_urls:
                item["descricao"] = (item.get("descricao", "") + " | Fontes adicionais: " + ", ".join(other_urls[:3])).strip()
        result.append(item)

    print(f"Dedup: {len(items)} items -> {len(result)} unique (merged {len(items) - len(result)} duplicates)")
    return result


async def run_full_scrape(api_key=""):
    """Run all scrapers + add known legislation as fallback."""
    all_items = []

    # 1. Always include known SAP legislation
    all_items.extend(KNOWN_LEGISLATION)
    print(f"Known legislation: {len(KNOWN_LEGISLATION)} items")

    # 2. Try live scrapers (Federal + Estadual + Municipal)
    scrapers = [
        # ── Federal (13 portais) ──
        ("DOU",              scrape_dou),
        ("NFe Portal",       scrape_nfe_portal),
        ("CONFAZ",           scrape_confaz),
        ("Planalto",         scrape_planalto),
        ("Normas.leg.br",    scrape_normas_leg),
        ("LexML",            scrape_lexml),
        ("SPED",             scrape_sped),
        ("eSocial",          scrape_esocial),
        ("Reforma RFB",      scrape_reforma_rfb),
        ("Reforma Portais",  scrape_reforma_portais),
        ("Câmara",           scrape_camara),
        ("Senado",           scrape_senado),
        # ── Estadual (14 portais: 11 SEFAZs + AL-SP + Imprensa Oficial + CONFAZ já incluso) ──
        ("SEFAZ Todos",      scrape_sefaz_all),
        ("AL-SP",            scrape_al_sp),
        ("Imprensa Oficial SP", scrape_imprensa_oficial_sp),
        # ── Municipal (5 portais) ──
        ("Leis Municipais",  scrape_leis_municipais),
        ("Diário Municipal", scrape_diario_municipal),
        ("Prefeitura SP",    scrape_prefeitura_sp),
        ("ABRASF",           scrape_abrasf),
        ("CNM",              scrape_cnm),
    ]
    for name, fn in scrapers:
        try:
            items = await fn()
            all_items.extend(items)
        except Exception as e:
            print(f"{name} failed: {e}")

    # 3. Deduplicate + aggregate: merge items that refer to the same legislation
    unique = _deduplicate_and_merge(all_items)
    print(f"Total unique items after merge: {len(unique)}")

    # 4. Classify with AI (only items that need it)
    if api_key:
        unique = await classify_with_ai(unique, api_key)

    return unique
