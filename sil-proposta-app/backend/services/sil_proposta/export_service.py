"""
Export service — gera DAM (Word) e WP (Excel).
Migrado de generators/dam.py e generators/wp.py do legado.
"""
import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

AZUL = RGBColor(0x1F, 0x4E, 0x79)
AZUL_CL = RGBColor(0x2E, 0x75, 0xB6)


def generate_dam_document(proposal) -> io.BytesIO:
    """Gera documento Word DAM a partir de uma Proposal."""
    doc = Document()

    # Margens
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)

    dam_data = proposal.dam.dam_json if proposal.dam else {}

    # Capa
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(dam_data.get("titulo", proposal.title))
    run.font.size = Pt(22)
    run.font.color.rgb = AZUL
    run.bold = True

    doc.add_paragraph("")
    doc.add_paragraph(f"Tipo: {proposal.project_type}")
    doc.add_paragraph(f"SAP: {proposal.sap_version}")
    doc.add_paragraph(f"UFs: {', '.join(proposal.states or [])}")

    # Necessidade
    doc.add_heading("1. Necessidade", level=1)
    doc.add_paragraph(dam_data.get("necessidade", proposal.rfp_text or ""))

    # Entregaveis
    doc.add_heading("2. Entregaveis", level=1)
    for d in proposal.deliverables:
        doc.add_paragraph(f"[{d.module}] {d.item}", style="List Bullet")

    # Equipe / WP
    doc.add_heading("3. Equipe e Work Package", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for i, header in enumerate(["Frente", "Nivel", "Dias", "Horas"]):
        table.rows[0].cells[i].text = header

    for r in proposal.resources:
        row = table.add_row()
        row.cells[0].text = r.frente
        row.cells[1].text = r.nivel
        row.cells[2].text = str(r.dias)
        row.cells[3].text = f"{r.horas}h"

    row = table.add_row()
    row.cells[0].text = "Total"
    row.cells[2].text = str(sum(r.dias for r in proposal.resources))
    row.cells[3].text = f"{proposal.total_hours}h"

    # Premissas
    doc.add_heading("4. Premissas Gerais", level=1)
    for i, p_item in enumerate(proposal.premises, 1):
        doc.add_paragraph(f"{i}. {p_item.text}")

    # Comercial
    doc.add_heading("5. Investimento e Condicoes", level=1)
    comercial = dam_data.get("comercial", {})
    valor = proposal.valor or 0
    doc.add_paragraph(f"Valor: R$ {valor:,.2f}")
    doc.add_paragraph(f"Faturamento: {comercial.get('faturamento', '50%/50%')}")
    doc.add_paragraph(f"Garantia: {comercial.get('garantia', '30 dias')}")
    doc.add_paragraph(f"Validade: {comercial.get('validade', '30 dias')}")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
