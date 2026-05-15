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
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

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


# ════════════════════════════════════════════════════════════════════════════
# WP (Excel Work Package) — Cast Group template
# ════════════════════════════════════════════════════════════════════════════
#
# Migrated from legacy/sil-proposta-monolith/backend/generators/wp.py.
# Renders SAP Activate-aligned weekly distribution by resource, with totals
# in days and hours and an obrigatório "KT AMS" deploy row.

HORAS_DIA = 8
SEMANAS_MAX = 6

# colors
WP_AZUL_FILL = PatternFill("solid", fgColor="1F4E79")
WP_AZUL_CL_FILL = PatternFill("solid", fgColor="2E75B6")
WP_CINZA_FILL = PatternFill("solid", fgColor="D9E1F2")
WP_VERDE_FILL = PatternFill("solid", fgColor="E2EFDA")
WP_LARANJA_FILL = PatternFill("solid", fgColor="FCE4D6")

# fonts
WP_FONT_TITLE = Font(name="Calibri", size=16, bold=True, color="1F4E79")
WP_FONT_HEAD = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
WP_FONT_FASE = Font(name="Calibri", size=10, bold=True, color="1F4E79")
WP_FONT_BODY = Font(name="Calibri", size=10)
WP_FONT_TOTAL = Font(name="Calibri", size=10, bold=True)
WP_FONT_SMALL = Font(name="Calibri", size=9, color="595959")
WP_FONT_TOTAL_GERAL_LBL = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
WP_FONT_TOTAL_GERAL_VAL = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
WP_FONT_INFO = Font(name="Calibri", size=9, italic=True, color="7F7F7F")

WP_BORDER_THIN = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)
WP_BORDER_MED = Border(
    left=Side(style="medium", color="595959"),
    right=Side(style="medium", color="595959"),
    top=Side(style="medium", color="595959"),
    bottom=Side(style="medium", color="595959"),
)
WP_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
WP_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _resource_week_distribution(frente: str, total_dias: int) -> dict[int, int]:
    """Spread the resource's days across SAP Activate weeks (Realize phase).

    SD/FI start in week 1, ABAP in week 2 (after specs), GP one day per week.
    Max 5 days/week per resource per week. Up to SEMANAS_MAX weeks.
    """
    dist: dict[int, int] = {}
    if frente in ("SD", "FI"):
        start = 1
    elif "ABAP" in frente:
        start = 2
    elif frente == "GP":
        for s in range(1, min(total_dias + 1, SEMANAS_MAX + 1)):
            dist[s] = 1
        return dist
    else:
        start = 1

    remaining = total_dias
    week = start
    while remaining > 0 and week <= SEMANAS_MAX:
        slice_days = min(5, remaining)
        dist[week] = slice_days
        remaining -= slice_days
        week += 1
    return dist


def _wp_resources_from_proposal(proposal) -> list[dict[str, Any]]:
    """Map proposal.resources → list[dict] the renderer consumes."""
    rows = []
    for r in (proposal.resources or []):
        rows.append(
            {
                "frente": r.frente or "",
                "nivel": r.nivel or "Senior",
                "dias": int(r.dias or 0),
            }
        )
    return rows


def _wp_header(ws, header_row: int, col_td: int, col_th: int) -> None:
    for col, label in ((1, "Frente"), (2, "Recurso"), (3, "Nível")):
        c = ws.cell(row=header_row, column=col, value=label)
        c.font = WP_FONT_HEAD
        c.fill = WP_AZUL_CL_FILL
        c.alignment = WP_CENTER
    for s in range(1, SEMANAS_MAX + 1):
        c = ws.cell(row=header_row, column=3 + s, value=f"Sem {s}")
        c.font = WP_FONT_HEAD
        c.fill = WP_AZUL_CL_FILL
        c.alignment = WP_CENTER
    for col, label in ((col_td, "Total Dias"), (col_th, "Total Horas")):
        c = ws.cell(row=header_row, column=col, value=label)
        c.font = WP_FONT_HEAD
        c.fill = WP_AZUL_FILL
        c.alignment = WP_CENTER
    ws.row_dimensions[header_row].height = 24


def generate_wp_workbook(proposal) -> io.BytesIO:
    """Build the Cast Group Work Package .xlsx for a Proposal."""
    return _render_wp(_wp_resources_from_proposal(proposal), proposal.hours_presale or 0)


def _render_wp(resources: list[dict[str, Any]], presale_hours: int) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "WP_RFP"
    ws.sheet_view.showGridLines = False

    col_td = 3 + SEMANAS_MAX + 1
    col_th = col_td + 1

    # title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_th)
    ws.cell(row=1, column=1, value="WORK PACKAGE — SIL-PROPOSTA").font = WP_FONT_TITLE
    ws.cell(row=1, column=1).alignment = WP_LEFT
    ws.row_dimensions[1].height = 30

    header_row = 3
    _wp_header(ws, header_row, col_td, col_th)

    # fallback when no resources provided — keeps the doc usable for drafts.
    if not resources:
        resources = [
            {"frente": "SD", "nivel": "Senior", "dias": 9},
            {"frente": "FI", "nivel": "Senior", "dias": 11},
            {"frente": "GP", "nivel": "Senior", "dias": 4},
            {"frente": "ABAP 1", "nivel": "Senior", "dias": 14},
            {"frente": "ABAP 2", "nivel": "Senior", "dias": 14},
            {"frente": "ABAP 3", "nivel": "Senior", "dias": 14},
        ]

    current_row = header_row + 1

    # phase header — Recursos
    ws.merge_cells(
        start_row=current_row, start_column=1,
        end_row=current_row, end_column=col_th,
    )
    c = ws.cell(row=current_row, column=1, value="■  Recursos do Projeto")
    c.font = WP_FONT_FASE
    c.fill = WP_CINZA_FILL
    c.alignment = WP_LEFT
    ws.row_dimensions[current_row].height = 20
    current_row += 1

    total_horas_proj = 0

    for rec in resources:
        frente = rec.get("frente", "")
        nivel = rec.get("nivel", "Senior")
        dias = int(rec.get("dias", 0) or 0)
        dist = _resource_week_distribution(frente, dias)

        # left columns
        for col, val, font, align in (
            (1, frente, WP_FONT_BODY, WP_LEFT),
            (2, frente, WP_FONT_BODY, WP_LEFT),
            (3, nivel, WP_FONT_SMALL, WP_CENTER),
        ):
            c = ws.cell(row=current_row, column=col, value=val)
            c.font = font
            c.alignment = align
            c.border = WP_BORDER_THIN

        total_dias_rec = 0
        for s in range(1, SEMANAS_MAX + 1):
            v = dist.get(s, 0)
            c = ws.cell(row=current_row, column=3 + s, value=v if v else None)
            c.alignment = WP_CENTER
            c.border = WP_BORDER_THIN
            if v:
                c.fill = WP_VERDE_FILL if frente not in ("GP",) else WP_CINZA_FILL
                total_dias_rec += v

        horas_rec = total_dias_rec * HORAS_DIA
        total_horas_proj += horas_rec

        c_td = ws.cell(row=current_row, column=col_td, value=total_dias_rec)
        c_td.font = WP_FONT_TOTAL
        c_td.alignment = WP_CENTER
        c_td.border = WP_BORDER_THIN
        c_td.fill = WP_CINZA_FILL

        c_th = ws.cell(row=current_row, column=col_th, value=horas_rec)
        c_th.font = WP_FONT_TOTAL
        c_th.alignment = WP_CENTER
        c_th.border = WP_BORDER_THIN
        c_th.fill = WP_CINZA_FILL

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    # KT AMS — mandatory deploy row
    current_row += 1
    ws.merge_cells(
        start_row=current_row, start_column=1,
        end_row=current_row, end_column=col_th,
    )
    c = ws.cell(row=current_row, column=1, value="■  Deploy — KT AMS (obrigatório)")
    c.font = WP_FONT_FASE
    c.fill = WP_LARANJA_FILL
    c.alignment = WP_LEFT
    ws.row_dimensions[current_row].height = 20
    current_row += 1

    ws.cell(row=current_row, column=1, value="KT AMS").font = WP_FONT_BODY
    ws.cell(row=current_row, column=1).border = WP_BORDER_THIN
    ws.cell(row=current_row, column=2, value="Transferência de conhecimento").font = WP_FONT_SMALL
    ws.cell(row=current_row, column=2).border = WP_BORDER_THIN
    ws.cell(row=current_row, column=3, value="—").alignment = WP_CENTER
    ws.cell(row=current_row, column=3).border = WP_BORDER_THIN
    for s in range(1, SEMANAS_MAX + 1):
        ws.cell(row=current_row, column=3 + s).border = WP_BORDER_THIN
    # KT AMS lands in the last-but-one week.
    kt_col = 3 + SEMANAS_MAX - 1
    ws.cell(row=current_row, column=kt_col, value=2).fill = WP_LARANJA_FILL
    ws.cell(row=current_row, column=kt_col).border = WP_BORDER_THIN
    c = ws.cell(row=current_row, column=col_td, value=2)
    c.font = WP_FONT_TOTAL
    c.alignment = WP_CENTER
    c.border = WP_BORDER_THIN
    c = ws.cell(row=current_row, column=col_th, value=16)
    c.font = WP_FONT_TOTAL
    c.alignment = WP_CENTER
    c.border = WP_BORDER_THIN
    total_horas_proj += 16
    current_row += 2

    # grand total
    ws.merge_cells(
        start_row=current_row, start_column=1,
        end_row=current_row, end_column=col_td - 1,
    )
    c = ws.cell(row=current_row, column=1, value="TOTAL GERAL DO PROJETO")
    c.font = WP_FONT_TOTAL_GERAL_LBL
    c.fill = WP_AZUL_FILL
    c.alignment = WP_LEFT
    c.border = WP_BORDER_MED

    c_th = ws.cell(row=current_row, column=col_th, value=total_horas_proj)
    c_th.font = WP_FONT_TOTAL_GERAL_VAL
    c_th.fill = WP_AZUL_FILL
    c_th.alignment = WP_CENTER
    c_th.border = WP_BORDER_MED
    ws.row_dimensions[current_row].height = 28
    current_row += 2

    # internal cost (pre-sale hours) — only when non-zero
    if presale_hours and presale_hours > 0:
        ws.merge_cells(
            start_row=current_row, start_column=1,
            end_row=current_row, end_column=col_th,
        )
        c = ws.cell(
            row=current_row, column=1,
            value=(
                f"⚙  CUSTO INTERNO — Horas de pré-venda: {presale_hours}h "
                f"(não incluídas na proposta ao cliente)"
            ),
        )
        c.font = WP_FONT_INFO
        c.alignment = WP_LEFT
        current_row += 1

        ws.merge_cells(
            start_row=current_row, start_column=1,
            end_row=current_row, end_column=col_th,
        )
        pct = round((presale_hours / total_horas_proj) * 100, 1) if total_horas_proj else 0
        c = ws.cell(
            row=current_row, column=1,
            value=(
                f"   Total real (faturável + pré-venda): {total_horas_proj + presale_hours}h"
                f"  |  Custo oculto: {pct}%"
            ),
        )
        c.font = WP_FONT_INFO
        c.alignment = WP_LEFT

    # column widths + freeze panes
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 10
    for s in range(1, SEMANAS_MAX + 1):
        ws.column_dimensions[get_column_letter(3 + s)].width = 8
    ws.column_dimensions[get_column_letter(col_td)].width = 12
    ws.column_dimensions[get_column_letter(col_th)].width = 13
    ws.freeze_panes = "D4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
