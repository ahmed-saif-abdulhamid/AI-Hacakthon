"""Launcher: store-page fields (template-locked) and one launch post DRAFT, never posted."""
from __future__ import annotations

from pydantic import BaseModel, Field

from proveit import llm


class StoreOut(BaseModel):
    product_name: str
    tagline: str
    description: str
    includes: list[str] = Field(min_length=1, max_length=5)
    who_it_is_for: str
    who_it_is_not_for: str


class PostOut(BaseModel):
    title: str
    body: str


def store(run_id: str, title: str, audience: str, modules: list[str], feedback: str = "") -> StoreOut:
    user = (f"MODE: store\nPRODUCT: {title}\nAUDIENCE: {audience}\nMODULES: {'; '.join(modules)}\n"
            + (f"PREVIOUS DRAFT WAS BLOCKED: {feedback}. Remove that content.\n" if feedback else ""))
    return llm.agent_call(run_id, "launcher", "store_copy", StoreOut, user, num_predict=450)


def post(run_id: str, title: str, audience: str, feedback: str = "") -> PostOut:
    user = (f"MODE: post\nPRODUCT: {title}\nAUDIENCE: {audience}\n"
            + (f"PREVIOUS DRAFT WAS BLOCKED: {feedback}. Remove that content.\n" if feedback else ""))
    return llm.agent_call(run_id, "launcher", "launch_post_draft", PostOut, user, num_predict=320)
