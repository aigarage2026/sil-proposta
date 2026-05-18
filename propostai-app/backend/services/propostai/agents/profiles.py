"""
Per-tenant calibration profiles for OrchestratorV5 (v3 §4.5.5 E9).

Why this exists:
- Real-world feedback shows the catalog+LLM pipeline systematically
  underestimates big projects (e.g., EHP upgrades quoted at ~R$30–50k
  when the real engagement is R$400k+). Small fiscal adjustments work
  fine. A per-tenant knob lets each consultancy bias estimates toward
  their actual book of business without forking the catalog.
- "Conservative" here means *larger* estimates (less likely to under-
  deliver), "aggressive" means *smaller* (faster, riskier). The naming
  follows engineering convention, not financial convention.

Selection:
  tenants.features.agent_profile = "default" | "conservative" | "aggressive"

Unknown names fall back to "default" silently — a typo in the feature
dict must never break proposal generation.

The orchestrator applies the profile after `calculate_team()` so the
catalog's per-deliverable hour distribution stays transparent in the
DAM doc, but team-days (and therefore total hours + commercial value)
scale with the profile.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TARIFA_HORA = 250


@dataclass(frozen=True)
class CalibrationProfile:
    name: str
    description: str = ""
    # Multiplier applied to each resource's days post-calculate_team().
    # 1.0 = no change; 1.5 = +50% (compensates for IA underestimation
    # on complex projects); 0.85 = -15% (optimistic on simple demands).
    hours_multiplier: float = 1.0
    # Per-hour rate. Override here so enterprise tenants can quote
    # senior rates without editing the global default.
    tariff_hora: int = DEFAULT_TARIFA_HORA
    # Subtracted from each confidence score in the run output (clamped
    # to [0, 1]). Conservative tenants advertise less certainty.
    confidence_penalty: float = 0.0
    # Minimum QA score before the proposal is flagged as needing
    # human review. The orchestrator does not auto-reject — it just
    # mirrors the threshold on the DAM so the UI can warn.
    qa_min_score: int = 80


DEFAULT_PROFILE = CalibrationProfile(
    name="default",
    description="Calibração padrão do catálogo. Bom para adequações fiscais e demandas pequenas a médias.",
)

CONSERVATIVE_PROFILE = CalibrationProfile(
    name="conservative",
    description=(
        "Estimativas maiores (+50% horas, +10% rigor de confiança, QA ≥ 90). "
        "Recomendado para tenants que fazem muitas implantações grandes (upgrades, "
        "rollouts multi-país) onde a IA historicamente subestima."
    ),
    hours_multiplier=1.5,
    confidence_penalty=0.1,
    qa_min_score=90,
)

AGGRESSIVE_PROFILE = CalibrationProfile(
    name="aggressive",
    description=(
        "Estimativas menores (-15% horas) para tenants que fazem muitas "
        "adequações pontuais simples e querem propostas competitivas em preço."
    ),
    hours_multiplier=0.85,
)


PROFILES: dict[str, CalibrationProfile] = {
    DEFAULT_PROFILE.name: DEFAULT_PROFILE,
    CONSERVATIVE_PROFILE.name: CONSERVATIVE_PROFILE,
    AGGRESSIVE_PROFILE.name: AGGRESSIVE_PROFILE,
}


def resolve_profile_for_tenant(tenant) -> CalibrationProfile:
    """Look up the profile referenced by tenant.features.agent_profile.
    Returns DEFAULT_PROFILE when tenant is None, feature is absent, or
    the name is unknown — never raises.
    """
    if tenant is None:
        return DEFAULT_PROFILE
    features = getattr(tenant, "features", None) or {}
    name = features.get("agent_profile") or DEFAULT_PROFILE.name
    return PROFILES.get(name, DEFAULT_PROFILE)
