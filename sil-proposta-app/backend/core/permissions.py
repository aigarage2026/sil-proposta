"""
Permission dependencies — product gating and role checks (v3 §6.3, §16.4).

The authoritative source for what a user can do is the JWT issued by the
Portal. Two dimensions matter:

  1. `products: ["sil-proposta", ...]`
     Did the tenant buy this product? If not, all routes return 403.

  2. `roles: { "sil-proposta": "admin", ... }`
     What role does this user have inside this product?

These dependencies live here (not core/security) so security.py stays
focused on token mechanics and we have a single import point for any
endpoint that needs gating.
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from core.config import get_settings
from core.security import decode_token, security_scheme

settings = get_settings()


async def get_jwt_claims(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> dict:
    """Returns the decoded JWT payload, or 401."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token nao fornecido",
        )
    return await decode_token(credentials.credentials)


def require_product(product_slug: Optional[str] = None):
    """Dependency factory — 403 if the tenant lacks the product.

    By default checks for the local PRODUCT_SLUG (`sil-proposta`).
    Pass an explicit slug to gate cross-product calls.
    """
    target = product_slug or settings.PRODUCT_SLUG

    async def checker(claims: dict = Depends(get_jwt_claims)) -> dict:
        products = claims.get("products") or []
        if target not in products:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Tenant nao tem acesso ao produto '{target}'. "
                    f"Produtos contratados: {products or 'nenhum'}"
                ),
            )
        return claims

    return checker


def require_product_role(allowed_roles: Iterable[str], product_slug: Optional[str] = None):
    """Dependency factory — 403 unless the user has one of `allowed_roles`
    inside the given product (default: local product).

    Platform super_admin bypasses the check.
    """
    target = product_slug or settings.PRODUCT_SLUG
    allowed = set(allowed_roles)

    async def checker(claims: dict = Depends(require_product(target))) -> dict:
        roles = claims.get("roles") or {}
        # Platform super_admin always passes.
        if roles.get("platform") == "super_admin":
            return claims
        product_role = roles.get(target)
        if product_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{product_role}' insuficiente em '{target}'. "
                    f"Necessario: {sorted(allowed)}"
                ),
            )
        return claims

    return checker


async def require_platform_admin(claims: dict = Depends(get_jwt_claims)) -> dict:
    """Dependency — 403 unless the user is super_admin or platform_admin."""
    platform_role = (claims.get("roles") or {}).get("platform")
    if platform_role not in {"super_admin", "platform_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores da plataforma",
        )
    return claims
