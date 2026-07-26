"""Pick the best existing CV variant for a job.

Deterministic and free. We only ask the LLM to justify the choice, never to make it
from scratch, because alignment maths is more reliable than a model's taste.
"""
from __future__ import annotations

from app.scoring import TIER1, ats_alignment, find_keywords


def rank_variants(job_description: str, variants: list) -> list[dict]:
    """Score every active variant against a job. Best first."""
    required = find_keywords(job_description)
    jd_low = (job_description or "").lower()
    ranked = []

    for variant in variants:
        if not variant.active:
            continue

        alignment = ats_alignment(job_description, variant.full_text)

        # Lean tags let a specialist CV win when the job clearly leans that way,
        # even if raw keyword counts are close.
        tag_hits = [tag for tag in (variant.lean_tags or []) if tag in jd_low]
        tag_bonus = min(12, 4 * len(tag_hits))

        # Prefer a variant that already covers the tier-1 terms.
        tier1_required = required & TIER1
        tier1_covered = {t for t in tier1_required if t in variant.full_text.lower()}
        tier1_bonus = round(
            8 * len(tier1_covered) / len(tier1_required)
        ) if tier1_required else 0

        ranked.append({
            "variant": variant,
            "name": variant.name,
            "alignment": alignment["score"],
            "matched": alignment["matched"],
            "missing": alignment["missing"],
            "tag_hits": tag_hits,
            "total": alignment["score"] + tag_bonus + tier1_bonus,
        })

    ranked.sort(key=lambda r: r["total"], reverse=True)
    return ranked


def choose(job_description: str, variants: list) -> dict | None:
    ranked = rank_variants(job_description, variants)
    if not ranked:
        return None
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    best["margin"] = best["total"] - runner_up["total"] if runner_up else best["total"]
    best["runner_up"] = runner_up["name"] if runner_up else None
    return best
