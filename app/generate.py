"""LLM generation: bullet rewrites, honest keyword lift, and cover letters.

The alignment lift works like this:
  1. Route the job to the best existing CV variant (deterministic, free).
  2. Measure alignment. Find the keywords the job wants that this CV omits.
  3. Filter those against MASTER_SKILLS_PROFILE.md. Anything the master profile does
     not claim is dropped on the spot, no matter how much it would help the score.
  4. Ask the model to weave the surviving, true skills into existing bullets.
  5. Verify, then re-measure.

Step 3 is the whole ethical load-bearing wall. If alignment lands at 74 because the
job wants CATIA and the user has never touched CATIA, the answer is 74.
"""
from __future__ import annotations

import json
import re

from anthropic import Anthropic

from app import config, verify
from app.cv import editor, router
from app.scoring import ats_alignment

_client: Anthropic | None = None

# Rough Sonnet pricing, USD per token, for the cost counter.
COST_IN = 3.0 / 1_000_000
COST_OUT = 15.0 / 1_000_000


def client() -> Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SYSTEM = """You tailor CVs and write cover letters for a UK graduate mechanical engineer.

ABSOLUTE RULE: you may only re-order, re-word, and re-emphasise facts that already
appear in the SOURCE CV or the MASTER SKILLS PROFILE provided to you. You must never
invent an employer, job title, date, degree, certification, tool, project, or metric.
If you cannot honestly cover a requirement, say so in skills_gap and move on. A
fabricated claim on a job application can cost the candidate the offer or the job, so
a lower alignment score is always the correct trade.

When rewriting a bullet:
- keep it within 15% of the original character length so page layout does not shift
- keep the original achievement intact; you are changing emphasis and vocabulary only
- only introduce a tool or standard if it appears in the MASTER SKILLS PROFILE
- write in British English, past tense, and lead with a verb

Return only valid JSON matching the requested schema."""


PROMPT = """SOURCE CV ({variant_name}):
<cv>
{cv_text}
</cv>

EDITABLE BULLETS (index: text):
{bullets}

MASTER SKILLS PROFILE (the full set of things this candidate can honestly claim):
<master>
{master}
</master>

JOB:
Title: {title}
Company: {company}
Location: {location}
<description>
{description}
</description>

The job asks for these terms which the SOURCE CV does not currently contain:
{missing}

Of those, these ARE supported by the master profile and may be worked in:
{honest_missing}

These are NOT supported and must be ignored entirely, and listed in skills_gap:
{unsupported_missing}

Return JSON:
{{
  "cv_reasoning": "one sentence on why this CV variant fits",
  "bullet_edits": [
    {{"index": <int>, "original": "<exact original text>", "revised": "<rewrite>",
      "why": "<which job requirement this now evidences>"}}
  ],
  "skill_additions": ["<exact skill string to append to a skills line>"],
  "cover_letter": "<150-200 words, British English, addressed to the hiring team>",
  "key_skill_matches": ["..."],
  "skills_gap": ["<honest gaps, including every unsupported term above>"],
  "match_rationale": "<two sentences>"
}}

Edit at most 4 bullets. Prefer bullets whose subject already relates to the requirement."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def tailor(job: dict, variants: list, master_profile: str) -> dict:
    """Produce a tailored application package for one job."""
    description = f"{job.get('title','')}\n{job.get('description','')}"

    choice = router.choose(description, variants)
    if not choice:
        raise RuntimeError("no active CV variants loaded")
    variant = choice["variant"]

    before = ats_alignment(description, variant.full_text)
    missing = before["missing"]

    # The honesty gate: only keywords the master profile already claims survive.
    honest_missing, unsupported = verify.verify_skill_additions(missing, master_profile)

    bullets = variant.bullets or []
    bullet_block = "\n".join(f"{b['index']}: {b['text']}" for b in bullets[:40]) or "(none found)"

    message = client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": PROMPT.format(
                variant_name=variant.name,
                cv_text=variant.full_text[:6000],
                bullets=bullet_block,
                master=master_profile[:6000],
                title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                description=(job.get("description") or "")[:6000],
                missing=", ".join(missing) or "(none)",
                honest_missing=", ".join(honest_missing) or "(none)",
                unsupported_missing=", ".join(unsupported) or "(none)",
            ),
        }],
    )

    raw = message.content[0].text
    try:
        result = _extract_json(raw)
    except json.JSONDecodeError:
        return {
            "error": "model returned unparseable JSON",
            "raw": raw[:500],
            "cv_variant_name": variant.name,
            "flagged": True,
            "flag_reasons": ["generation failed"],
        }

    cost = (message.usage.input_tokens * COST_IN) + (message.usage.output_tokens * COST_OUT)

    sources = [variant.full_text, master_profile]
    flags: list[str] = []

    # Validate every bullet edit independently; drop the ones that fail.
    clean_edits = []
    for edit in result.get("bullet_edits", []):
        issues = verify.verify_bullet_edit(
            edit.get("original", ""), edit.get("revised", ""), sources
        )
        if issues:
            flags.extend(issues)
            continue
        if not editor.check_length(edit.get("original", ""), edit.get("revised", "")):
            flags.append(f"length drift on bullet {edit.get('index')}")
            continue
        clean_edits.append(edit)

    # Re-check skill additions even though we told the model the rules.
    proposed = result.get("skill_additions", [])
    added_skills, rejected_skills = verify.verify_skill_additions(proposed, master_profile)
    if rejected_skills:
        flags.append(f"dropped unsupported skills: {', '.join(rejected_skills)}")

    cover = result.get("cover_letter", "")
    cover_issues = verify.check(cover, sources, allow_company=job.get("company"))
    if cover_issues:
        flags.extend(cover_issues)

    # Re-measure alignment against what the CV will actually say after edits.
    projected = variant.full_text
    for edit in clean_edits:
        projected = projected.replace(edit.get("original", ""), edit.get("revised", ""))
    if added_skills:
        projected += "\n" + ", ".join(added_skills)
    after = ats_alignment(description, projected)

    return {
        "cv_variant_id": variant.id,
        "cv_variant_name": variant.name,
        "cv_reasoning": result.get("cv_reasoning", ""),
        "bullet_edits": clean_edits,
        "added_skills": added_skills,
        "missing_keywords": after["missing"],
        "cover_letter": cover,
        "key_skill_matches": result.get("key_skill_matches", []),
        "skills_gap": result.get("skills_gap", []) + unsupported,
        "match_rationale": result.get("match_rationale", ""),
        "alignment_before": before["score"],
        "alignment_after": after["score"],
        "flagged": bool(flags),
        "flag_reasons": sorted(set(flags)),
        "llm_cost_usd": round(cost, 5),
    }


def write_cv(variant_path: str, application: dict, output_path: str) -> dict:
    """Apply the verified edits to a copy of the .docx, preserving formatting."""
    skill_additions = []
    if application.get("added_skills"):
        targets = editor.find_skills_paragraphs(variant_path)
        if targets:
            skill_additions.append({
                "index": targets[0]["index"],
                "addition": ", " + ", ".join(application["added_skills"]),
            })
    return editor.apply_edits(
        source_path=variant_path,
        output_path=output_path,
        bullet_edits=application.get("bullet_edits", []),
        skill_additions=skill_additions,
    )
