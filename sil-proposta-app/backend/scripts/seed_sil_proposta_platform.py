"""
Seed de dados iniciais da plataforma Sil-Proposta.
Idempotente — pode ser re-executado sem duplicar dados.
"""
import asyncio
from uuid import uuid4

from core.database import async_session, init_db
from models.tenant import Tenant
from models.user import User
from models.company import Company
from core.security import hash_password


KNOWLEDGE_DOCS = [
    {"title": "ECONF 110750 — Conciliacao Financeira", "category": "fiscal",
     "content": "Evento ECONF 110750 (Conciliacao Financeira) NAO tem suporte DRC nativo no SAP. Obrigatorio usar CPI (iFlow)."},
    {"title": "cBenef ICMS — BAdI J_1BNF_ADD_DATA", "category": "fiscal",
     "content": "Campo cBenef e obrigatorio em NF-e para estados com beneficios fiscais. Implementar via BAdI J_1BNF_ADD_DATA."},
    {"title": "IN 1.608/2025-GO — tpIntegra", "category": "fiscal",
     "content": "GO exige campo tpIntegra=1 na NF-e via IN 1.608/2025-GSE. Obrigatorio para operacoes interestaduais."},
    {"title": "Portaria SRE 70/2025 SP — cBenef", "category": "fiscal",
     "content": "SP exige cBenef preenchido conforme Portaria SRE 70/2025. Tabela Z com 310 codigos."},
    {"title": "NT 2024.002 ECONF", "category": "fiscal",
     "content": "Nota Tecnica 2024.002 define eventos ECONF 110750 (autorizacao) e 110751 (cancelamento)."},
    {"title": "Cadeia ABAP Obrigatoria", "category": "abap",
     "content": "Cadeia: BAPI Z -> BAdI -> RFC Z -> iFlow CPI -> Monitor Z. Cada objeto e distinto."},
    {"title": "Regra 4+ ABAP = 3 ABAPers", "category": "abap",
     "content": "4 ou mais desenvolvimentos ABAP independentes exigem 3 ABAPers em paralelo para cumprir prazo."},
    {"title": "SAP Activate — Fases e Horas", "category": "methodology",
     "content": "SAP Activate: Prepare -> Explore -> Realize -> Deploy -> Run. KT AMS minimo 2 dias."},
    {"title": "DAM — Estrutura Padrao Cast Group", "category": "cast_group",
     "content": "DAM: 1.Necessidade, 2.Solucao, 3.Premissas, 4.Equipe, 5.Impactos, 6.Cronograma, 7.Investimento, 8.Condicoes."},
    {"title": "Modelo Comercial Cast Group", "category": "cast_group",
     "content": "Valor fechado, faturamento 50% aprovacao + 50% go-live, garantia 30 dias, validade 30 dias."},
    {"title": "LC 214/2021 — Reforma Tributaria", "category": "reform",
     "content": "IBS/CBS/IS substituem PIS/COFINS/IPI/ICMS/ISS a partir de 2026. Impacta SD, FI, MM, CO."},
    {"title": "DRC vs CPI — Decisao", "category": "integration",
     "content": "DRC nativo: documentos com nota SAP. CPI obrigatorio: eventos sem nota SAP (ECONF, pagamentos)."},
]


async def seed():
    """Seed principal — idempotente."""
    await init_db()

    async with async_session() as db:
        # Verificar se ja existe tenant seed
        from sqlalchemy import select
        result = await db.execute(select(Tenant).where(Tenant.slug == "cast-group-demo"))
        if result.scalar_one_or_none():
            print("Seed ja executado. Pulando.")
            return

        # Tenant demo
        tenant = Tenant(
            name="Cast Group (Demo)",
            slug="cast-group-demo",
            plan_slug="professional",
            max_users=10,
            max_proposals_per_month=100,
        )
        db.add(tenant)
        await db.flush()

        # Owner
        owner = User(
            tenant_id=tenant.id,
            email="admin@castgroup.com.br",
            full_name="Administrador Cast Group",
            password_hash=hash_password("CastGroup2026!"),
            role="owner",
            is_active=True,
            is_email_verified=True,
        )
        db.add(owner)
        await db.flush()

        # Company
        company = Company(
            tenant_id=tenant.id,
            name="Cast Group",
            is_default=True,
        )
        db.add(company)

        # Knowledge docs
        from models.sil_proposta.knowledge_document import KnowledgeDocument
        for doc in KNOWLEDGE_DOCS:
            db.add(KnowledgeDocument(
                tenant_id=tenant.id,
                title=doc["title"],
                content=doc["content"],
                category=doc["category"],
                is_global=True,
            ))

        await db.commit()
        print(f"Seed concluido: tenant={tenant.id}, owner={owner.email}")


if __name__ == "__main__":
    asyncio.run(seed())
