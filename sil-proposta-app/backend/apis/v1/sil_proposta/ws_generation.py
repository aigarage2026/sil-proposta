"""
WebSocket endpoint para streaming de geracao de propostas.
Envia eventos em tempo real conforme cada agente processa.
"""
import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import decode_token
from core.logger import get_logger
from schemas.intake import IntakePayload

router = APIRouter()
logger = get_logger()


@router.websocket("/ws/proposals/generate")
async def ws_generate(websocket: WebSocket):
    """WebSocket para streaming de geracao de proposta."""
    await websocket.accept()

    try:
        # Receber payload inicial
        data = await websocket.receive_json()
        token = data.get("token", "")
        payload_data = data.get("payload", {})

        # Validar token
        try:
            claims = await decode_token(token)
            tenant_id = claims["tenant_id"]
            user_id = claims["sub"]
        except Exception:
            await websocket.send_json({"type": "error", "msg": "Token invalido"})
            await websocket.close()
            return

        payload = IntakePayload(**payload_data)

        # Definir agentes a executar
        agents = [
            ("orch", "Orion (Orquestrador)"),
            ("ver", "Valeria (Versao SAP)"),
            ("sd", "Sofia (SD)"),
            ("fi", "Felix (FI)"),
            ("abap", "Axel (ABAP)"),
            ("drc", "Diana (DRC)"),
            ("fest", "Estela (Fiscal Estadual)"),
            ("ffed", "Fabio (Fiscal Federal)"),
            ("eq", "Eduardo (Equipe/GP)"),
            ("com", "Camila (Comercial)"),
        ]

        await websocket.send_json({"type": "start", "msg": "Analisando intake...", "total_agents": len(agents)})

        # Simular execucao de cada agente
        for i, (ag_id, ag_name) in enumerate(agents):
            await websocket.send_json({
                "type": "agent",
                "id": ag_id,
                "name": ag_name,
                "status": "running",
                "progress": round((i / len(agents)) * 100),
            })

            # Delay variavel simulando processamento
            await asyncio.sleep(0.5 + 0.3 * (hash(ag_id) % 4))

            await websocket.send_json({
                "type": "agent",
                "id": ag_id,
                "name": ag_name,
                "status": "done",
                "progress": round(((i + 1) / len(agents)) * 100),
            })

        # Gerar proposta real
        from services.sil_proposta.demo_generation_service import gerar_proposta_demo
        result = gerar_proposta_demo(payload)

        await websocket.send_json({
            "type": "complete",
            "progress": 100,
            "result": result,
        })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "msg": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
