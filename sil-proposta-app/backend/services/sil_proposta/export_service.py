"""
DAM (Word) generator — Cast Group template.

Migrated from legacy/sil-proposta-monolith/backend/generators/dam.py (v3
Onda 5). The legacy module rendered the full Cast Group DAM template
(cover, summary, sections 1–8). This module:

  - Keeps that rich layout and style choices (Arial 11pt, AZUL/AZUL_CL
    headings, D9E1F2 table-row backgrounds, page breaks between sections).
  - Replaces the legacy `(sections, payload)` dict-based interface with a
    SQLAlchemy `Proposal` model entry point. A small adapter,
    `_proposal_to_sections`, bridges the two so the renderer stays close
    to the legacy code that arquitetos have already validated.

The rendering function intentionally avoids pulling in any non-stdlib
dependency beyond `python-docx`. No DB access — call sites are expected
to load the Proposal eagerly with its relationships (resources, deliverables,
premises) before invoking generate_dam_document().
"""
from __future__ import annotations

import datetime
import io
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

# ── palette ─────────────────────────────────────────────────────────────────

AZUL = RGBColor(0x1F, 0x4E, 0x79)
AZUL_CL = RGBColor(0x2E, 0x75, 0xB6)
HEADER_BG_HEX = "D9E1F2"


# ── low-level helpers ───────────────────────────────────────────────────────


def _set_cell_bg(cell, hex_color: str) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tc_pr.append(shd)


def _h1(doc, text: str):
    p = doc.add_heading(text, level=1)
    if p.runs:
        p.runs[0].font.color.rgb = AZUL
        p.runs[0].font.size = Pt(14)
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(8)
    return p


def _h2(doc, text: str):
    p = doc.add_heading(text, level=2)
    if p.runs:
        p.runs[0].font.color.rgb = AZUL_CL
        p.runs[0].font.size = Pt(12)
    p.paragraph_format.space_before = Pt(10)
    return p


def _body(doc, text: str):
    p = doc.add_paragraph(text)
    if p.runs:
        p.runs[0].font.size = Pt(11)
    p.paragraph_format.space_after = Pt(6)
    return p


def _add_kv_row(table, col1: str, col2: str, bg: str | None = None, bold_col1: bool = True):
    row = table.add_row()
    c1, c2 = row.cells[0], row.cells[1]
    c1.text = col1
    c2.text = col2
    if bold_col1 and c1.paragraphs and c1.paragraphs[0].runs:
        c1.paragraphs[0].runs[0].bold = True
    if bg:
        _set_cell_bg(c1, bg)
        _set_cell_bg(c2, bg)
    c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    c2.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return row


def _format_brl(value: float) -> str:
    """R$ 1.234,56 — BR formatting."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── adapter: Proposal model → renderer dict ─────────────────────────────────


def _proposal_to_sections(proposal) -> dict[str, Any]:
    """Build the dict shape the legacy renderer expects from a SQLAlchemy
    Proposal (and its loaded relationships).

    Pulls from proposal.dam.dam_json when present — that's the AI-generated
    structured content. Falls back to direct columns when dam_json is missing
    (e.g., a draft proposal that hasn't been generated yet).
    """
    dam_json = (proposal.dam.dam_json if getattr(proposal, "dam", None) else None) or {}
    comercial = dam_json.get("comercial") or {}

    valor_referencia = comercial.get("valor_referencia")
    if valor_referencia is None and proposal.valor is not None:
        valor_referencia = float(proposal.valor)

    return {
        "titulo": dam_json.get("titulo") or proposal.title,
        "tipo_projeto": proposal.project_type,
        "versao_sap": proposal.sap_version,
        "ufs": proposal.states or [],
        "necessidade": dam_json.get("necessidade") or proposal.rfp_text or "",
        "plano": dam_json.get("plano") or {"needs_cpi": bool(proposal.needs_cpi)},
        "reforma": dam_json.get("reforma") or {},
        "entregaveis": [
            f"[{d.module}] {d.item}" for d in (proposal.deliverables or [])
        ] or dam_json.get("entregaveis") or [],
        "premissas": [p.text for p in (proposal.premises or [])]
        or dam_json.get("premissas")
        or [],
        "equipe": [
            {
                "frente": r.frente,
                "nivel": r.nivel,
                "dias": r.dias,
                "horas": r.horas,
            }
            for r in (proposal.resources or [])
        ],
        "total_horas": proposal.total_hours or sum((r.horas or 0) for r in (proposal.resources or [])),
        "comercial": {
            "valor_referencia": valor_referencia,
            "faturamento": comercial.get("faturamento", "50%/50%"),
            "garantia": comercial.get("garantia", "30 dias"),
            "validade": comercial.get("validade", "30 dias"),
        },
    }


# ── public entry point ─────────────────────────────────────────────────────


def generate_dam_document(proposal) -> io.BytesIO:
    """Build a Cast Group DAM .docx from a Proposal and return an in-memory buffer."""
    sections = _proposal_to_sections(proposal)
    return _render(sections)


def _render(sections: dict[str, Any]) -> io.BytesIO:
    doc = Document()

    # ── margins ────────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)

    # ── base style ─────────────────────────────────────────────────────
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    data_hoje = datetime.date.today().strftime("%d/%m/%Y")
    titulo_demanda = (sections.get("titulo") or "Proposta SAP")[:80]

    # ── COVER ──────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("CAST GROUP PARTNER")
    run.bold = True
    run.font.size = Pt(18)
    run.font.color.rgb = AZUL

    doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(titulo_demanda)
    run.bold = True
    run.font.size = Pt(14)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("DAM — Documento de Arquitetura de Melhoria — v1")
    run.font.size = Pt(12)
    run.font.color.rgb = AZUL_CL

    doc.add_paragraph()

    cover_table = doc.add_table(rows=0, cols=2)
    cover_table.style = "Table Grid"
    cover_table.columns[0].width = Inches(2.0)
    cover_table.columns[1].width = Inches(4.5)

    cover_rows = [
        ("Dados da Solicitação", "", HEADER_BG_HEX),
        ("Nome do Cliente", "", None),
        ("Solicitante", "", None),
        ("", "", None),
        ("Preenchimento Cast Group", "", HEADER_BG_HEX),
        ("Data criação", data_hoje, None),
        ("Arquiteto", "Sil-Proposta (IA)", None),
        ("Código PMS", "OP —", None),
    ]
    for c1, c2, bg in cover_rows:
        _add_kv_row(cover_table, c1, c2, bg=bg)

    doc.add_page_break()

    # ── SUMÁRIO ────────────────────────────────────────────────────────
    _h1(doc, "Sumário")
    for item in (
        "1. Necessidade",
        "2. Solução",
        "3. Premissas Gerais",
        "4. Equipe do Projeto",
        "5. Análise de Impactos",
        "6. Cronograma",
        "7. Investimento",
        "8. Condições de Faturamento",
    ):
        _body(doc, item)
    doc.add_page_break()

    # ── 1. NECESSIDADE ─────────────────────────────────────────────────
    _h1(doc, "1. Necessidade")
    ufs = ", ".join(sections.get("ufs") or [])
    ver = sections.get("versao_sap", "")
    tipo = sections.get("tipo_projeto", "")
    _body(
        doc,
        f"O cliente opera SAP {ver} e necessita de desenvolvimento/configuração "
        f"para adequação fiscal e operacional nas UFs: {ufs}. "
        f"Tipo de projeto: {tipo}.",
    )

    _h2(doc, "1.1 Benefício esperado pelo cliente")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    _add_kv_row(
        t,
        "Benefício esperado pelo cliente",
        "Garantir conformidade fiscal, eliminar riscos de autuação e automatizar processos manuais.",
        bg=HEADER_BG_HEX,
    )

    _h2(doc, "1.2 Quadro resumo do processo atual")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for c1, c2 in [
        ("Processo atual", sections.get("necessidade") or "Processo atual descrito na RFP."),
        ("Transações do processo atual", "VA01, VF01, J1BNFE, FI (baixa de títulos)"),
        ("Sistemas externos e interfaces", "Gateway de pagamento / TEF / maquininha"),
        ("Volume de dados", "A confirmar com o cliente"),
        ("Áreas e processos impactados", "Vendas, Faturamento, Financeiro (FI), TI"),
        ("Demanda relacionada a compliance?", "Sim — legislação fiscal vigente"),
    ]:
        _add_kv_row(t, c1, c2)

    _h2(doc, "1.3 Quadro resumo do processo futuro")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for c1, c2 in [
        (
            "Processo futuro",
            "Integração automatizada entre os sistemas de pagamento e o SAP, com transmissão fiscal automatizada.",
        ),
        ("Entradas do processo", "Dados de pagamento vindos do gateway/TEF/maquininha"),
        ("Saídas do processo", "NF-e com Grupo YA preenchido (Cenário 1) e Evento ECONF (Cenário 2)"),
        ("Clientes", "N/A"),
    ]:
        _add_kv_row(t, c1, c2)

    doc.add_page_break()

    # ── 2. SOLUÇÃO ─────────────────────────────────────────────────────
    _h1(doc, "2. Solução")
    _h2(doc, "2.1 Resumo da Solução")

    plano = sections.get("plano") or {}
    needs_cpi = bool(plano.get("needs_cpi"))
    canal = "SAP CPI (evento sem suporte DRC nativo)" if needs_cpi else "SAP DRC"
    _body(
        doc,
        f"A solução utiliza {canal} para transmissão fiscal. "
        f"Fluxo: FI Baixa → ABAP Z monta payload → {canal} → SEFAZ → protocolo retorna ao ECC.",
    )

    reforma = sections.get("reforma") or {}
    decisao = reforma.get("decisao")
    if decisao == "fazer_agora":
        _body(doc, "⚠ Reforma Tributária (LC 214): impacto identificado — entregáveis incluídos no escopo.")
    elif decisao == "planejar":
        _body(
            doc,
            "ℹ Reforma Tributária (LC 214): recomenda-se planejamento. "
            "Roadmap incluído como seção informativa.",
        )

    _h2(doc, "2.2 Escopo da melhoria")

    t = doc.add_table(rows=0, cols=4)
    t.style = "Table Grid"
    hdr = t.add_row()
    for i, h in enumerate(["Mód.", "Produto / Entregável", "Escopo", "Premissas"]):
        hdr.cells[i].text = h
        if hdr.cells[i].paragraphs and hdr.cells[i].paragraphs[0].runs:
            hdr.cells[i].paragraphs[0].runs[0].bold = True
        _set_cell_bg(hdr.cells[i], HEADER_BG_HEX)

    for row_data in [
        ("SD", "Entendimento do cenário", "Sim", "Análise da legislação e geração do DAM"),
        ("FI", "Entendimento do cenário", "Sim", "Análise do fluxo financeiro"),
        ("FI", "Configuração / especificação", "Sim", "Conciliação bancária + trigger do evento"),
        ("SD", "Configuração / especificação", "Sim", "BAPI Z + BAdI + RFC + monitor"),
        ("ABAP", "Ajuste de programas", "Sim", "BAPI, BAdI, RFC, evento, monitor, CPI"),
        ("SD", "Testes de validação", "Sim", "Testes unitários — interface da maquininha"),
        ("FI", "Testes de validação", "Sim", "Testes unitários — dados para XML e evento"),
        ("ABAP", "Testes de validação", "Sim", "Suporte aos testes"),
        ("SD", "Auxílio testes integrados (1 dia útil)", "Sim", ""),
        ("FI", "Auxílio testes integrados (1 dia útil)", "Sim", ""),
        ("ABAP", "Auxílio testes integrados (1 dia útil)", "Sim", ""),
        ("SD", "Acompanhamento Go Live (1 dia útil)", "Sim", ""),
        ("FI", "Acompanhamento Go Live (1 dia útil)", "Sim", ""),
        ("ABAP", "Acompanhamento Go Live (1 dia útil)", "Sim", ""),
    ]:
        row = t.add_row()
        for i, val in enumerate(row_data):
            row.cells[i].text = val

    doc.add_page_break()

    # ── 3. PREMISSAS ───────────────────────────────────────────────────
    _h1(doc, "3. Premissas Gerais")
    for p_text in sections.get("premissas") or []:
        p = doc.add_paragraph(style="List Number")
        p.add_run(p_text)

    _h2(doc, "Definição de Alteração de Escopo")
    for item in [
        "Qualquer inclusão de novos itens ou alteração de já existentes não previstos nesta proposta.",
        "Alteração de regras de negócio, lógicas, layout ou apresentações previamente acordadas.",
        "Alteração de cronogramas sem aviso mínimo de 1 semana.",
        "Liberação de consultores sem aviso prévio de 7 dias.",
        "Quaisquer atividades não previstas neste documento.",
    ]:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(item)

    doc.add_page_break()

    # ── 4. EQUIPE ──────────────────────────────────────────────────────
    _h1(doc, "4. Equipe do Projeto")
    for recurso in sections.get("equipe") or []:
        frente = recurso.get("frente", "")
        nivel = recurso.get("nivel", "Senior")
        _body(doc, f"• Consultor {frente} — {nivel}")

    doc.add_page_break()

    # ── 5. IMPACTOS ────────────────────────────────────────────────────
    _h1(doc, "5. Análise de Impactos")
    t = doc.add_table(rows=0, cols=5)
    t.style = "Table Grid"
    hdr = t.add_row()
    for i, h in enumerate(
        ["Id", "Impacto", "Solução de Contorno", "Probabilidade", "Classificação"]
    ):
        hdr.cells[i].text = h
        if hdr.cells[i].paragraphs and hdr.cells[i].paragraphs[0].runs:
            hdr.cells[i].paragraphs[0].runs[0].bold = True
        _set_cell_bg(hdr.cells[i], HEADER_BG_HEX)
    row = t.add_row()
    for i, v in enumerate(
        [
            "01",
            "Erros durante o Go Live",
            "Extenso ciclo de testes em QAS + homologação SEFAZ",
            "Média",
            "Moderado",
        ]
    ):
        row.cells[i].text = v

    # ── 6. CRONOGRAMA ──────────────────────────────────────────────────
    doc.add_page_break()
    _h1(doc, "6. Cronograma")
    equipe = sections.get("equipe") or []
    semanas = max((int(r.get("dias", 10)) // 5 for r in equipe), default=4) if equipe else 4
    _body(
        doc,
        f"Macro cronograma: aproximadamente {semanas} semanas para execução das atividades e suporte.",
    )
    _body(doc, "Este cronograma será detalhado após a aprovação desta proposta e poderá sofrer alterações.")
    _body(doc, "O início do projeto será planejado a partir da aprovação desta proposta.")

    # ── 7. INVESTIMENTO ────────────────────────────────────────────────
    doc.add_page_break()
    _h1(doc, "7. Investimento")
    total_h = int(sections.get("total_horas") or 528)
    comercial = sections.get("comercial") or {}
    valor = comercial.get("valor_referencia")
    if valor is None:
        valor = total_h * 230  # fallback: hourly default

    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    _add_kv_row(t, "Título da Demanda", "Total", bg=HEADER_BG_HEX)
    _add_kv_row(t, titulo_demanda[:60], _format_brl(float(valor)))

    _body(doc, "")
    _body(
        doc,
        "É importante destacar que, conforme o modelo de Sustentação da Cast Group, "
        "todas as melhorias são consideradas como 'valor fechado' e possuem garantia de 30 dias.",
    )

    # ── 8. CONDIÇÕES DE FATURAMENTO ────────────────────────────────────
    _h1(doc, "8. Condições de Faturamento")
    validade = comercial.get("validade", "30 dias")
    garantia = comercial.get("garantia", "30 dias")
    faturamento = comercial.get("faturamento", "50%/50%")
    for item in [
        f"Esta proposta tem validade de {validade}.",
        "Os valores incluem ISS, PIS e COFINS atualmente em vigor.",
        f"Faturamento: {faturamento} (aprovação / Go-Live).",
        "Em caso de paralisação: Cast reserva-se o direito de faturar o % de avanço.",
        f"Garantia pós go-live: {garantia}.",
    ]:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(item)

    # ── serialize ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
