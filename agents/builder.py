"""Builder: product spec + module(s) + CSV template. Buyer docs are assembled by code."""
from __future__ import annotations

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import Variant


class ModuleSpec(BaseModel):
    name: str
    purpose: str


class SpecOut(BaseModel):
    title: str
    audience: str
    modules: list[ModuleSpec] = Field(min_length=1, max_length=3)
    not_included: list[str] = Field(min_length=1, max_length=4)


class ModuleOut(BaseModel):
    title: str
    intro: str
    steps: list[str] = Field(min_length=4, max_length=14)
    template_columns: list[str] = Field(min_length=2, max_length=8)
    template_rows: list[list[str]] = Field(min_length=1, max_length=5)


def spec(run_id: str, variant: Variant) -> SpecOut:
    user = f"MODE: spec\nPRODUCT IDEA: {variant.title}\nSEGMENT: {variant.segment}\nJOB: {variant.job_to_be_done}"
    return llm.agent_call(run_id, "builder", "product_spec", SpecOut, user, num_predict=450)


def module(run_id: str, variant: Variant, sp: SpecOut, index: int, feedback: str = "") -> ModuleOut:
    m = sp.modules[index]
    user = (f"MODE: module\nPRODUCT: {sp.title}\nAUDIENCE: {sp.audience}\nMODULE: {m.name} - {m.purpose}\n"
            f"JOB: {variant.job_to_be_done}\n" + (f"FIX: {feedback}\n" if feedback else ""))
    return llm.agent_call(run_id, "builder", f"build_module_{index + 1}", ModuleOut, user, num_predict=900)


def user_docs(sp: SpecOut, modules: list[ModuleOut]) -> str:
    """Buyer README, assembled by code from the spec (no new claims)."""
    lines = [f"# {sp.title}: how to use this toolkit", "", f"**Who it is for:** {sp.audience}", "",
             "## What is inside", ""]
    for i, mod in enumerate(modules, start=1):
        lines.append(f"{i}. **{mod.title}**: phase3_step2_module-{i} (checklist) and phase3_step2_template-{i} (CSV)")
    lines += ["", "## How to use it", "",
              "1. Read the module intro.",
              "2. Copy the CSV template into your spreadsheet tool.",
              "3. Work through the checklist in order and tick each step.",
              "", "## What this toolkit does not do", ""]
    lines += [f"- {x}" for x in sp.not_included]
    lines += ["", "## Support", "", "Questions go to the founder by email (address on the store page)."]
    return "\n".join(lines) + "\n"
