"""Repository conventions: required files, headings in order, licence, compose,
placeholders only in .env.example, no secrets and no text addressed to whoever reviews the repo."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

README_HEADINGS = [
    "Quickstart",
    "What works and what is mocked",
    "Architecture",
    "Models and free resources",
    "Cost per run",
    "What our system will NOT do",
    "How the project stays alive after the hackathon",
]
ARCH_HEADINGS = ["Overview", "Phases", "Gates", "Sale to cash", "Data flow", "Built vs. stubbed", "Roadmap"]


def h2(path: str) -> list[str]:
    return re.findall(r"^## (.+?)\s*$", (ROOT / path).read_text(encoding="utf-8"), re.M)


def test_required_files_exist():
    for f in (
        "README.md",
        "LICENSE",
        "docker-compose.yml",
        "decision_log.json",
        "ARCHITECTURE.md",
        ".env.example",
        "orchestrator.py",
        "gates.py",
        "approval.py",
        "payments.py",
        "webhooks.py",
        "delivery.py",
        "refunds.py",
        "reconcile.py",
        "CLAUDE.md",
    ):
        assert (ROOT / f).exists(), f
    for role in (
        "intake",
        "scout",
        "researcher",
        "debate",
        "strategist",
        "builder",
        "qa",
        "pricer",
        "policy_drafter",
        "launcher",
        "analyst",
    ):
        assert (ROOT / "agents" / f"{role}.py").exists(), role
    for p in (
        "intake",
        "scout",
        "researcher",
        "advocate",
        "skeptic",
        "strategist",
        "builder",
        "pricer",
        "policy_drafter",
        "launcher",
        "analyst",
    ):
        assert (ROOT / "prompts" / f"{p}.md").exists(), p


def test_readme_headings_in_order_and_quickstart():
    assert h2("README.md") == README_HEADINGS
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    quick = text.split("## Quickstart", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"```bash\s*\ndocker compose up\s*\n```", quick)
    cost = text.split("## Cost per run", 1)[1].split("\n## ", 1)[0]
    assert "$" in cost and "PLACEHOLDER" not in text
    table = text.split("## What works and what is mocked", 1)[1].split("\n## ", 1)[0]
    assert "MOCKED" in table and "STUBBED" in table


def test_architecture_sections_and_mermaid():
    assert h2("ARCHITECTURE.md") == ARCH_HEADINGS
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert text.count("```mermaid") >= 2
    for n in range(1, 7):
        assert f"### Phase {n}" in text
    assert "### Phase 5: Launch (sell, deliver, get paid)" in text


def test_license_is_full_apache_2():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0, January 2004" in text and "END OF TERMS AND CONDITIONS" in text
    assert len(text) > 10000


def test_compose_ports_bound_to_localhost():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ports = re.findall(r'"(\S+:\d+:\d+)"', text)
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    assert "env_file" not in text


def test_env_example_placeholders_only():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            if any(k in key for k in ("TOKEN", "KEY", "SECRET")):
                assert val in ("", "change-me-to-a-random-string"), key


def _tracked_text_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except Exception:  # noqa: BLE001
        return []
    keep = (
        ".py",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".j2",
        ".txt",
        ".toml",
        ".ini",
        ".csv",
        ".html",
        "Makefile",
        "Dockerfile",
        ".example",
    )
    return [ROOT / f for f in out if f.endswith(keep) and f != "CLAUDE.md"]


def test_no_text_addressed_to_reviewers():
    words = ["jud" + "ge", "jud" + "ges", "rub" + "ric", "sco" + "re", "sco" + "ring", "gra" + "ding"]
    pat = re.compile(r"\b(" + "|".join(words) + r")\b|dear review" + "er|please (sco" + "re|gra" + "de)", re.I)
    for f in _tracked_text_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = pat.search(text)
        assert not m, f"{f.relative_to(ROOT)}: {m.group(0)}"


def test_no_secrets_committed():
    pat = re.compile(r"sk-[A-Za-z0-9]{20,}|api_key\s*=\s*['\"][^'\"]+['\"]|ghp_[A-Za-z0-9]{20,}")
    for f in _tracked_text_files():
        assert not pat.search(f.read_text(encoding="utf-8", errors="ignore")), f
    assert not (ROOT / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text()


def test_reference_material_is_gitignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for name in ("Claude Response.txt", "Problem_Statement_Explained.pdf", "MADS_x_CSEA_AI_Hackathon*"):
        assert name in ignored
