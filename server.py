#!/usr/bin/env python3
"""
Research Tracker MCP Server
Empirical research management: paper discovery, experiment tracking,
synthesis lineage, peer review, and graph visualization.
"""

import json
import os
import re
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

import arxiv
from fastmcp import FastMCP

# ──────────────────────────────────────────────────────────────
# Bootstrap
# ──────────────────────────────────────────────────────────────

mcp = FastMCP("research-tracker")
STORAGE: Path = Path.home() / "research"


def storage() -> Path:
    return STORAGE


def papers_dir() -> Path:
    return storage() / "papers"


def synthesis_dir() -> Path:
    return storage() / "synthesis"


def ideas_dir() -> Path:
    return storage() / "ideas"


def sessions_dir() -> Path:
    return storage() / "sessions"


def projects_dir() -> Path:
    return storage() / "projects"


def index_path() -> Path:
    return storage() / "index.json"


def reviewers_path() -> Path:
    return storage() / "reviewers.json"


def ensure_dirs():
    for d in [papers_dir(), synthesis_dir(), ideas_dir(), sessions_dir(), projects_dir()]:
        d.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────
# Index helpers
# ──────────────────────────────────────────────────────────────

def load_index() -> dict:
    p = index_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"papers": {}, "synthesis": {}, "ideas": {}, "sessions": {}, "projects": {}}


def save_index(idx: dict):
    index_path().write_text(json.dumps(idx, indent=2))


def load_reviewers() -> dict:
    p = reviewers_path()
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_reviewers(rv: dict):
    reviewers_path().write_text(json.dumps(rv, indent=2))


# ──────────────────────────────────────────────────────────────
# ID + time helpers
# ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40]


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_exp_id(name: str) -> str:
    return f"exp-{ts()}-{slugify(name)}"


def make_project_id(name: str) -> str:
    return f"proj-{ts()}-{slugify(name)}"


def make_synth_id(name: str) -> str:
    return f"synth-{ts()}-{slugify(name)}"


def make_idea_id(name: str) -> str:
    return f"idea-{ts()}-{slugify(name)}"


def make_session_id() -> str:
    return f"session-{ts()}-{uuid.uuid4().hex[:6]}"


def make_review_id() -> str:
    return f"review-{ts()}-{uuid.uuid4().hex[:6]}"


# ──────────────────────────────────────────────────────────────
# Graph + confidence helpers
# ──────────────────────────────────────────────────────────────

def _get_manifest(node_id: str, idx: dict) -> Optional[dict]:
    """Locate and load a manifest for any node type."""
    if node_id in idx.get("papers", {}):
        p = papers_dir() / node_id / "metadata.json"
        return json.loads(p.read_text()) if p.exists() else None
    for paper_id in idx.get("papers", {}):
        p = papers_dir() / paper_id / "experiments" / node_id / "manifest.json"
        if p.exists():
            return json.loads(p.read_text())
    if node_id in idx.get("synthesis", {}):
        p = synthesis_dir() / node_id / "manifest.json"
        return json.loads(p.read_text()) if p.exists() else None
    if node_id in idx.get("projects", {}):
        p = projects_dir() / node_id / "manifest.json"
        return json.loads(p.read_text()) if p.exists() else None
    for project_id in idx.get("projects", {}):
        p = projects_dir() / project_id / "experiments" / node_id / "manifest.json"
        if p.exists():
            return json.loads(p.read_text())
    return None


def compute_generation(node_id: str, idx: dict, _visited: set = None) -> int:
    """Generation depth: papers are 0, first-gen experiments are 1, etc."""
    if _visited is None:
        _visited = set()
    if node_id in _visited:
        return 0
    _visited.add(node_id)
    manifest = _get_manifest(node_id, idx)
    if not manifest:
        return 0
    parents = manifest.get("derived_from", [])
    if not parents:
        return 0
    return 1 + max(compute_generation(p, idx, _visited) for p in parents)


def _load_reviews_for(exp_id: str, paper_id: Optional[str] = None, project_id: Optional[str] = None) -> list:
    if paper_id:
        d = papers_dir() / paper_id / "experiments" / exp_id / "reviews"
    elif project_id:
        d = projects_dir() / project_id / "experiments" / exp_id / "reviews"
    else:
        d = synthesis_dir() / exp_id / "reviews"
    if not d.exists():
        return []
    return [json.loads(f.read_text()) for f in d.glob("*.json")]


def compute_confidence(exp_id: str, paper_id: Optional[str] = None, project_id: Optional[str] = None) -> float:
    """Review-weighted confidence score. Unreviewed = 1.0 (benefit of the doubt)."""
    reviews = _load_reviews_for(exp_id, paper_id, project_id)
    if not reviews:
        return 1.0
    reviewers = load_reviewers()
    verdict_scores = {"sound": 1.0, "inconclusive": 0.6, "overclaiming": 0.4, "flawed": 0.2}
    weighted = []
    for r in reviews:
        accuracy = reviewers.get(r.get("reviewer_agent", ""), {}).get("review_accuracy_score", 0.7)
        score = verdict_scores.get(r.get("verdict", "inconclusive"), 0.5)
        weighted.append(score * accuracy)
    return round(sum(weighted) / len(weighted), 3)


# ──────────────────────────────────────────────────────────────
# Documentation templates + validation
# ──────────────────────────────────────────────────────────────

EXPERIMENT_TEMPLATES = {
    "hypothesis.md": (
        "# Hypothesis\n\n"
        "<!-- REQUIRED: State clearly what you expect to happen and WHY.\n"
        "     Write this BEFORE running anything. This is locked at checkout. -->\n\n"
    ),
    "implementation.md": (
        "# Implementation\n\n"
        "## Code Location\n\n<!-- REQUIRED: path/repo/commit -->\n\n"
        "## Key Decisions\n\n<!-- REQUIRED: non-obvious choices made -->\n\n"
        "## What Was Intentionally Omitted\n\n"
    ),
    "data.md": (
        "# Data Documentation\n\n"
        "## Source\n\n<!-- REQUIRED: where did this data come from -->\n\n"
        "## Location on Machine\n\n<!-- REQUIRED: absolute path or mount point -->\n\n"
        "## Structure Description\n\n<!-- REQUIRED: schema, shape, types -->\n\n"
        "## Preprocessing Steps\n\n<!-- REQUIRED: every transformation applied -->\n\n"
        "## Provenance\n\n"
    ),
}

OUTCOMES_TEMPLATES = {
    "raw.md": (
        "# Raw Results\n\n"
        "## Metrics\n\n<!-- REQUIRED: numbers, timestamps, run conditions -->\n\n"
        "## Run Conditions\n\n"
    ),
    "learnings.md": (
        "# Learnings\n\n"
        "## Did the Result Match the Hypothesis?\n\n<!-- REQUIRED -->\n\n"
        "## What Was Surprising?\n\n"
        "## What Does This Rule Out?\n\n"
        "## Next Questions Raised\n\n"
    ),
    "paper.md": (
        "# Paper-Style Summary\n\n"
        "<!-- Optional. numbers → narrative → numbers format. Publishable quality. -->\n\n"
    ),
}

REQUIRED_SECTIONS = {
    "hypothesis.md": ["# Hypothesis"],
    "implementation.md": ["## Code Location", "## Key Decisions"],
    "data.md": ["## Source", "## Location on Machine", "## Structure Description", "## Preprocessing Steps"],
    "outcomes/raw.md": ["## Metrics"],
    "outcomes/learnings.md": ["## Did the Result Match the Hypothesis?"],
}


def _validate_docs(exp_path: Path) -> list[str]:
    errors = []
    for fname, required_sections in REQUIRED_SECTIONS.items():
        fpath = exp_path / fname
        if not fpath.exists():
            errors.append(f"Missing file: {fname}")
            continue
        content = fpath.read_text()
        for section in required_sections:
            idx = content.find(section)
            if idx == -1:
                errors.append(f"{fname}: missing section '{section}'")
                continue
            after = content[idx + len(section):].strip()
            next_sec = re.search(r"\n##", after)
            snippet = after[: next_sec.start()] if next_sec else after
            snippet = re.sub(r"<!--.*?-->", "", snippet, flags=re.DOTALL).strip()
            if len(snippet) < 10:
                errors.append(f"{fname}: section '{section}' appears unfilled")
    return errors


# ──────────────────────────────────────────────────────────────
# TOOLS: Papers
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def search_papers(
    query: str,
    max_results: int = 10,
    categories: list[str] = None,
    date_from: str = None,
) -> list[dict]:
    """Search arXiv. Returns id, title, authors, abstract (truncated), categories, published."""
    ensure_dirs()
    client = arxiv.Client()
    results = list(client.results(arxiv.Search(query=query, max_results=max_results,
                                               sort_by=arxiv.SortCriterion.Relevance)))
    out = []
    for r in results:
        arxiv_id = r.entry_id.split("/")[-1]
        cats = r.categories
        if categories and not any(c in cats for c in categories):
            continue
        pub = r.published.isoformat() if r.published else None
        if date_from and pub and pub < date_from:
            continue
        out.append({
            "id": arxiv_id,
            "title": r.title,
            "authors": [a.name for a in r.authors],
            "abstract": r.summary[:500] + ("..." if len(r.summary) > 500 else ""),
            "categories": cats,
            "published": pub,
            "url": r.entry_id,
        })
    return out


@mcp.tool()
def download_paper(arxiv_id: str) -> dict:
    """Download and store a paper by arXiv ID. Stores metadata.json, paper.md, annotations.md."""
    ensure_dirs()
    client = arxiv.Client()
    results = list(client.results(arxiv.Search(id_list=[arxiv_id])))
    if not results:
        return {"error": f"Paper {arxiv_id} not found on arXiv"}
    r = results[0]

    paper_path = papers_dir() / arxiv_id
    paper_path.mkdir(parents=True, exist_ok=True)
    (paper_path / "experiments").mkdir(exist_ok=True)

    metadata = {
        "arxiv_id": arxiv_id,
        "title": r.title,
        "authors": [a.name for a in r.authors],
        "abstract": r.summary,
        "categories": r.categories,
        "published": r.published.isoformat() if r.published else None,
        "url": r.entry_id,
        "pdf_url": r.pdf_url,
        "downloaded_at": now_iso(),
        "derived_from": [],
    }
    (paper_path / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (paper_path / "paper.md").write_text(
        f"# {r.title}\n\n"
        f"**Authors**: {', '.join(a.name for a in r.authors)}  \n"
        f"**Published**: {metadata['published']}  \n"
        f"**ArXiv**: [{arxiv_id}]({r.entry_id})  \n"
        f"**Categories**: {', '.join(r.categories)}\n\n"
        f"## Abstract\n\n{r.summary}\n"
    )
    (paper_path / "annotations.md").write_text(f"# Annotations: {r.title}\n\n")

    idx = load_index()
    idx["papers"][arxiv_id] = {
        "title": r.title,
        "authors": [a.name for a in r.authors],
        "categories": r.categories,
        "published": metadata["published"],
        "downloaded_at": metadata["downloaded_at"],
        "experiments": [],
        "concepts": [],
    }
    save_index(idx)
    return {"status": "downloaded", "arxiv_id": arxiv_id, "title": r.title}


@mcp.tool()
def list_papers() -> list[dict]:
    """List all locally stored papers with experiment counts."""
    ensure_dirs()
    idx = load_index()
    return [
        {
            "arxiv_id": k,
            "title": v["title"],
            "published": v.get("published"),
            "categories": v.get("categories", []),
            "experiment_count": len(v.get("experiments", [])),
        }
        for k, v in idx.get("papers", {}).items()
    ]


@mcp.tool()
def annotate_paper(arxiv_id: str, annotation: str) -> dict:
    """Append a timestamped annotation to a paper."""
    p = papers_dir() / arxiv_id / "annotations.md"
    if not p.exists():
        return {"error": f"Paper {arxiv_id} not stored locally. Run download_paper first."}
    p.write_text(p.read_text() + f"\n---\n*{now_iso()}*\n\n{annotation}\n")
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────
# TOOLS: Experiments (checkout / checkin)
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def checkout(
    arxiv_id: str,
    experiment_name: str,
    agent_id: str,
    intent: str,
    derived_from: list[str] = None,
    concepts: list[str] = None,
    hyperparameter_axes: list[str] = None,
    session_id: str = None,
) -> dict:
    """
    Check out a new experiment on a paper. Scaffolds all required documentation.

    IMPORTANT: Fill in hypothesis.md BEFORE running any code.
    The hypothesis is your commitment — it cannot be changed after checkin begins.

    derived_from: IDs of experiments/papers this builds on (enables lineage graph).
    concepts: searchable tags e.g. ["quantization", "pruning", "fine-tuning"].
    hyperparameter_axes: what dimensions you're exploring e.g. ["bits", "finetune-steps"].
    """
    ensure_dirs()
    idx = load_index()
    if arxiv_id not in idx.get("papers", {}):
        return {"error": f"Paper {arxiv_id} not in local store. Run download_paper first."}

    exp_id = make_exp_id(experiment_name)
    exp_path = papers_dir() / arxiv_id / "experiments" / exp_id
    exp_path.mkdir(parents=True, exist_ok=True)
    (exp_path / "outcomes").mkdir(exist_ok=True)
    (exp_path / "reviews").mkdir(exist_ok=True)

    for fname, content in EXPERIMENT_TEMPLATES.items():
        (exp_path / fname).write_text(content)
    for fname, content in OUTCOMES_TEMPLATES.items():
        (exp_path / "outcomes" / fname).write_text(content)

    manifest = {
        "id": exp_id,
        "name": experiment_name,
        "arxiv_id": arxiv_id,
        "derived_from": derived_from or [],
        "concepts": concepts or [],
        "hyperparameter_axes": hyperparameter_axes or [],
        "session_id": session_id,
        "created_at": now_iso(),
    }
    (exp_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (exp_path / "status.json").write_text(json.dumps({
        "status": "checked_out",
        "checked_out_by": agent_id,
        "intent": intent,
        "checked_out_at": now_iso(),
        "locked": False,
    }, indent=2))

    idx["papers"][arxiv_id].setdefault("experiments", []).append({
        "id": exp_id,
        "name": experiment_name,
        "status": "checked_out",
        "concepts": concepts or [],
    })
    save_index(idx)

    return {
        "experiment_id": exp_id,
        "path": str(exp_path),
        "next_step": "Fill hypothesis.md BEFORE running anything.",
        "required_files": list(REQUIRED_SECTIONS.keys()),
    }


@mcp.tool()
def checkin(
    arxiv_id: str,
    experiment_id: str,
    agent_id: str,
    outcome_direction: Literal["positive", "negative", "inconclusive", "derailed"],
    one_line: str,
    derailment_type: Optional[Literal["implementation_error", "bad_hypothesis", "data_issue", "scope_creep"]] = None,
    surprising: bool = False,
) -> dict:
    """
    Check in a completed experiment. Validates all required documentation.
    REFUSES checkin if any required sections are missing or unfilled.

    one_line: single sentence summary of the outcome — used in index and suggestions.
    derailment_type: required if outcome_direction is 'derailed'.
    """
    exp_path = papers_dir() / arxiv_id / "experiments" / experiment_id
    if not exp_path.exists():
        return {"error": "Experiment not found"}

    status_data = json.loads((exp_path / "status.json").read_text())
    if status_data.get("status") == "complete":
        return {"error": "Already checked in. Experiments are immutable after checkin."}
    if status_data.get("checked_out_by") != agent_id:
        return {"error": f"Checked out by {status_data.get('checked_out_by')}, not {agent_id}."}
    if outcome_direction == "derailed" and not derailment_type:
        return {"error": "derailment_type is required when outcome_direction is 'derailed'."}

    errors = _validate_docs(exp_path)
    if errors:
        return {"error": "Documentation incomplete — cannot check in.", "issues": errors}

    status_data.update({
        "status": "complete",
        "checked_in_at": now_iso(),
        "outcome_direction": outcome_direction,
        "derailment_type": derailment_type,
        "surprising": surprising,
        "locked": True,
    })
    (exp_path / "status.json").write_text(json.dumps(status_data, indent=2))

    manifest = json.loads((exp_path / "manifest.json").read_text())
    manifest.update({"outcome_direction": outcome_direction, "surprising": surprising, "one_line": one_line})
    (exp_path / "manifest.json").write_text(json.dumps(manifest, indent=2))

    idx = load_index()
    for exp in idx["papers"][arxiv_id].get("experiments", []):
        if exp["id"] == experiment_id:
            exp.update({"status": "complete", "outcome_direction": outcome_direction, "one_line": one_line})
    save_index(idx)
    snapshot(f"checkin {experiment_id}: {outcome_direction} — {one_line}",
             session_id=manifest.get("session_id"))
    return {"status": "checked_in", "experiment_id": experiment_id, "outcome": outcome_direction}


@mcp.tool()
def browse_stacks() -> list[dict]:
    """List all currently checked-out experiments across all papers. (What's in progress.)"""
    ensure_dirs()
    idx = load_index()
    out = []
    for paper_id, paper_data in idx.get("papers", {}).items():
        for exp in paper_data.get("experiments", []):
            st_path = papers_dir() / paper_id / "experiments" / exp["id"] / "status.json"
            if not st_path.exists():
                continue
            st = json.loads(st_path.read_text())
            if st.get("status") == "checked_out":
                out.append({
                    "root_type": "paper",
                    "root_id": paper_id,
                    "root_label": paper_data.get("title"),
                    "experiment_id": exp["id"],
                    "name": exp.get("name"),
                    "checked_out_by": st.get("checked_out_by"),
                    "intent": st.get("intent"),
                    "checked_out_at": st.get("checked_out_at"),
                })
    for project_id, project_data in idx.get("projects", {}).items():
        for exp in project_data.get("experiments", []):
            st_path = projects_dir() / project_id / "experiments" / exp["id"] / "status.json"
            if not st_path.exists():
                continue
            st = json.loads(st_path.read_text())
            if st.get("status") == "checked_out":
                out.append({
                    "root_type": "project",
                    "root_id": project_id,
                    "root_label": project_data.get("name"),
                    "experiment_id": exp["id"],
                    "name": exp.get("name"),
                    "checked_out_by": st.get("checked_out_by"),
                    "intent": st.get("intent"),
                    "checked_out_at": st.get("checked_out_at"),
                })
    return out


@mcp.tool()
def browse_shelf(concept: str = None, status: str = "complete") -> list[dict]:
    """Browse available (not checked out) experiments, optionally filtered by concept."""
    ensure_dirs()
    idx = load_index()
    out = []
    for paper_id, paper_data in idx.get("papers", {}).items():
        for exp in paper_data.get("experiments", []):
            if status and exp.get("status") != status:
                continue
            if concept and concept.lower() not in [c.lower() for c in exp.get("concepts", [])]:
                continue
            out.append({
                "root_type": "paper",
                "root_id": paper_id,
                "root_label": paper_data.get("title"),
                "experiment_id": exp["id"],
                "name": exp.get("name"),
                "concepts": exp.get("concepts", []),
                "outcome_direction": exp.get("outcome_direction"),
                "one_line": exp.get("one_line"),
                "confidence": compute_confidence(exp["id"], paper_id),
            })
    for project_id, project_data in idx.get("projects", {}).items():
        for exp in project_data.get("experiments", []):
            if status and exp.get("status") != status:
                continue
            if concept and concept.lower() not in [c.lower() for c in exp.get("concepts", [])]:
                continue
            out.append({
                "root_type": "project",
                "root_id": project_id,
                "root_label": project_data.get("name"),
                "experiment_id": exp["id"],
                "name": exp.get("name"),
                "concepts": exp.get("concepts", []),
                "outcome_direction": exp.get("outcome_direction"),
                "one_line": exp.get("one_line"),
                "confidence": compute_confidence(exp["id"], project_id=project_id),
            })
    return out


@mcp.tool()
def get_experiment(arxiv_id: str, experiment_id: str) -> dict:
    """Get full detail of one experiment: manifest, status, all doc files."""
    exp_path = papers_dir() / arxiv_id / "experiments" / experiment_id
    if not exp_path.exists():
        return {"error": "Not found"}
    result = {
        "manifest": json.loads((exp_path / "manifest.json").read_text()),
        "status": json.loads((exp_path / "status.json").read_text()),
        "confidence": compute_confidence(experiment_id, arxiv_id),
    }
    for fname in ["hypothesis.md", "implementation.md", "data.md"]:
        p = exp_path / fname
        if p.exists():
            result[fname] = p.read_text()
    outcomes_dir = exp_path / "outcomes"
    if outcomes_dir.exists():
        result["outcomes"] = {f.name: f.read_text() for f in outcomes_dir.glob("*.md")}
    return result


@mcp.tool()
def list_experiments(arxiv_id: str) -> list[dict]:
    """List all experiments for a paper with status, outcome, and confidence score."""
    idx = load_index()
    paper = idx.get("papers", {}).get(arxiv_id)
    if not paper:
        return []
    return [
        {**exp, "confidence": compute_confidence(exp["id"], arxiv_id)}
        for exp in paper.get("experiments", [])
    ]


# ──────────────────────────────────────────────────────────────
# TOOLS: Synthesis
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def create_synthesis(
    name: str,
    agent_id: str,
    intent: str,
    hypothesis: str,
    derived_from: list[str],
    concepts: list[str] = None,
    hyperparameter_axes: list[str] = None,
    session_id: str = None,
) -> dict:
    """
    Create a synthesis experiment derived from any combination of experiments/papers.

    derived_from can mix: paper arxiv_ids, experiment_ids, other synthesis_ids.
    The generation depth and lineage are computed automatically from this graph.
    hypothesis is required upfront and written immediately to hypothesis.md.

    Siblings (same root), cross-paper, incestuous (same-paper siblings), cross-gen —
    all are just different graph shapes. No special cases needed.
    """
    ensure_dirs()
    synth_id = make_synth_id(name)
    synth_path = synthesis_dir() / synth_id
    synth_path.mkdir(parents=True, exist_ok=True)
    (synth_path / "outcomes").mkdir(exist_ok=True)
    (synth_path / "reviews").mkdir(exist_ok=True)

    for fname, content in EXPERIMENT_TEMPLATES.items():
        (synth_path / fname).write_text(content)
    for fname, content in OUTCOMES_TEMPLATES.items():
        (synth_path / "outcomes" / fname).write_text(content)
    # Pre-fill the hypothesis (it was required upfront)
    (synth_path / "hypothesis.md").write_text(f"# Hypothesis\n\n{hypothesis}\n")

    manifest = {
        "id": synth_id,
        "name": name,
        "type": "synthesis",
        "derived_from": derived_from,
        "concepts": concepts or [],
        "hyperparameter_axes": hyperparameter_axes or [],
        "session_id": session_id,
        "created_at": now_iso(),
    }
    (synth_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (synth_path / "status.json").write_text(json.dumps({
        "status": "checked_out",
        "checked_out_by": agent_id,
        "intent": intent,
        "checked_out_at": now_iso(),
        "locked": False,
    }, indent=2))

    idx = load_index()
    idx["synthesis"][synth_id] = {
        "name": name,
        "derived_from": derived_from,
        "concepts": concepts or [],
        "status": "checked_out",
        "created_at": manifest["created_at"],
    }
    save_index(idx)
    return {"synthesis_id": synth_id, "path": str(synth_path)}


@mcp.tool()
def checkin_synthesis(
    synthesis_id: str,
    agent_id: str,
    outcome_direction: Literal["positive", "negative", "inconclusive", "derailed"],
    one_line: str,
    derailment_type: Optional[Literal["implementation_error", "bad_hypothesis", "data_issue", "scope_creep"]] = None,
    surprising: bool = False,
) -> dict:
    """Check in a completed synthesis. Same documentation requirements as experiments."""
    synth_path = synthesis_dir() / synthesis_id
    if not synth_path.exists():
        return {"error": "Synthesis not found"}

    errors = _validate_docs(synth_path)
    if errors:
        return {"error": "Documentation incomplete.", "issues": errors}

    status_data = json.loads((synth_path / "status.json").read_text())
    status_data.update({
        "status": "complete",
        "checked_in_at": now_iso(),
        "outcome_direction": outcome_direction,
        "derailment_type": derailment_type,
        "surprising": surprising,
        "locked": True,
    })
    (synth_path / "status.json").write_text(json.dumps(status_data, indent=2))

    manifest = json.loads((synth_path / "manifest.json").read_text())
    manifest.update({"outcome_direction": outcome_direction, "surprising": surprising, "one_line": one_line})
    (synth_path / "manifest.json").write_text(json.dumps(manifest, indent=2))

    idx = load_index()
    if synthesis_id in idx.get("synthesis", {}):
        idx["synthesis"][synthesis_id].update({
            "status": "complete",
            "outcome_direction": outcome_direction,
            "one_line": one_line,
        })
    save_index(idx)
    snapshot(f"checkin synthesis {synthesis_id}: {outcome_direction} — {one_line}",
             session_id=manifest.get("session_id"))
    return {"status": "checked_in", "synthesis_id": synthesis_id}


@mcp.tool()
def list_syntheses(status: str = None) -> list[dict]:
    """List synthesis experiments, optionally filtered by status."""
    ensure_dirs()
    idx = load_index()
    out = []
    for sid, s in idx.get("synthesis", {}).items():
        if status and s.get("status") != status:
            continue
        out.append({
            "id": sid,
            "name": s.get("name"),
            "derived_from": s.get("derived_from", []),
            "concepts": s.get("concepts", []),
            "status": s.get("status"),
            "outcome_direction": s.get("outcome_direction"),
            "confidence": compute_confidence(sid),
        })
    return out


# ──────────────────────────────────────────────────────────────
# TOOLS: Ideas backlog
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def record_idea(
    hypothesis: str,
    name: str = "",
    inspired_by: list[str] = None,
    concepts: list[str] = None,
) -> dict:
    """
    Record a future research idea for the librarian agent to act on.
    inspired_by: experiment/paper IDs that sparked this.
    """
    ensure_dirs()
    idea_id = make_idea_id(name or hypothesis[:30])
    idea = {
        "id": idea_id,
        "name": name,
        "hypothesis": hypothesis,
        "inspired_by": inspired_by or [],
        "concepts": concepts or [],
        "status": "unresearched",
        "created_at": now_iso(),
    }
    (ideas_dir() / f"{idea_id}.json").write_text(json.dumps(idea, indent=2))
    idx = load_index()
    idx.setdefault("ideas", {})[idea_id] = {
        "hypothesis": hypothesis[:120],
        "concepts": concepts or [],
        "status": "unresearched",
    }
    save_index(idx)
    return {"idea_id": idea_id}


@mcp.tool()
def list_ideas(status: Literal["unresearched", "in_progress", "absorbed", "all"] = "unresearched") -> list[dict]:
    """List ideas from the backlog filtered by status."""
    ensure_dirs()
    ideas = [json.loads(f.read_text()) for f in ideas_dir().glob("*.json")]
    if status != "all":
        ideas = [i for i in ideas if i.get("status") == status]
    return sorted(ideas, key=lambda x: x.get("created_at", ""), reverse=True)


@mcp.tool()
def promote_idea(idea_id: str, experiment_id: str) -> dict:
    """Mark an idea as absorbed into a real experiment."""
    p = ideas_dir() / f"{idea_id}.json"
    if not p.exists():
        return {"error": "Idea not found"}
    idea = json.loads(p.read_text())
    idea.update({"status": "absorbed", "experiment_id": experiment_id, "absorbed_at": now_iso()})
    p.write_text(json.dumps(idea, indent=2))
    idx = load_index()
    if idea_id in idx.get("ideas", {}):
        idx["ideas"][idea_id]["status"] = "absorbed"
    save_index(idx)
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────
# TOOLS: Projects (paper-free experiment roots)
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def create_project(
    name: str,
    description: str,
    seeded_from: list[str] = None,
    concepts: list[str] = None,
) -> dict:
    """
    Create a project as a first-class experiment root — no paper required.

    Use this when work has organically moved past any single paper, when you're
    running pure empirical exploration, or when the starting point is an idea
    rather than a paper. Projects are full graph nodes; experiments under them
    participate in lineage, synthesis, contradiction detection, and all discovery
    tools exactly like paper experiments.

    seeded_from: optional list of paper arxiv_ids or other project_ids that
                 inspired this project. Recorded as lineage but not required.
                 Empty seeded_from is valid — pure exploration is a legitimate root.
    """
    ensure_dirs()
    project_id = make_project_id(name)
    proj_path = projects_dir() / project_id
    proj_path.mkdir(parents=True, exist_ok=True)
    (proj_path / "experiments").mkdir(exist_ok=True)

    manifest = {
        "id": project_id,
        "name": name,
        "description": description,
        "seeded_from": seeded_from or [],
        "concepts": concepts or [],
        "created_at": now_iso(),
        "derived_from": seeded_from or [],
    }
    (proj_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (proj_path / "notes.md").write_text(f"# {name}\n\n{description}\n\n---\n\n")

    idx = load_index()
    idx.setdefault("projects", {})[project_id] = {
        "name": name,
        "description": description[:120],
        "seeded_from": seeded_from or [],
        "concepts": concepts or [],
        "created_at": manifest["created_at"],
        "experiments": [],
    }
    save_index(idx)
    return {"project_id": project_id, "path": str(proj_path)}


@mcp.tool()
def list_projects() -> list[dict]:
    """List all projects with experiment counts and seeded_from lineage."""
    ensure_dirs()
    idx = load_index()
    return [
        {
            "project_id": pid,
            "name": p.get("name"),
            "description": p.get("description"),
            "seeded_from": p.get("seeded_from", []),
            "concepts": p.get("concepts", []),
            "experiment_count": len(p.get("experiments", [])),
            "created_at": p.get("created_at"),
        }
        for pid, p in idx.get("projects", {}).items()
    ]


@mcp.tool()
def annotate_project(project_id: str, note: str) -> dict:
    """Append a timestamped note to a project's running log."""
    p = projects_dir() / project_id / "notes.md"
    if not p.exists():
        return {"error": f"Project {project_id} not found."}
    p.write_text(p.read_text() + f"\n---\n*{now_iso()}*\n\n{note}\n")
    return {"status": "ok"}


@mcp.tool()
def checkout_project_experiment(
    project_id: str,
    experiment_name: str,
    agent_id: str,
    intent: str,
    derived_from: list[str] = None,
    concepts: list[str] = None,
    hyperparameter_axes: list[str] = None,
    session_id: str = None,
) -> dict:
    """
    Check out a new experiment under a project (not a paper).

    Identical to checkout() in every way — same documentation requirements,
    same hypothesis-first discipline, same checkin enforcement.
    derived_from can point to paper experiments, other project experiments,
    synthesis nodes, or anything else in the graph.
    """
    ensure_dirs()
    idx = load_index()
    if project_id not in idx.get("projects", {}):
        return {"error": f"Project {project_id} not found. Run create_project first."}

    exp_id = make_exp_id(experiment_name)
    exp_path = projects_dir() / project_id / "experiments" / exp_id
    exp_path.mkdir(parents=True, exist_ok=True)
    (exp_path / "outcomes").mkdir(exist_ok=True)
    (exp_path / "reviews").mkdir(exist_ok=True)

    for fname, content in EXPERIMENT_TEMPLATES.items():
        (exp_path / fname).write_text(content)
    for fname, content in OUTCOMES_TEMPLATES.items():
        (exp_path / "outcomes" / fname).write_text(content)

    manifest = {
        "id": exp_id,
        "name": experiment_name,
        "project_id": project_id,
        "derived_from": derived_from or [],
        "concepts": concepts or [],
        "hyperparameter_axes": hyperparameter_axes or [],
        "session_id": session_id,
        "created_at": now_iso(),
    }
    (exp_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (exp_path / "status.json").write_text(json.dumps({
        "status": "checked_out",
        "checked_out_by": agent_id,
        "intent": intent,
        "checked_out_at": now_iso(),
        "locked": False,
    }, indent=2))

    idx["projects"][project_id].setdefault("experiments", []).append({
        "id": exp_id,
        "name": experiment_name,
        "status": "checked_out",
        "concepts": concepts or [],
    })
    save_index(idx)
    return {
        "experiment_id": exp_id,
        "path": str(exp_path),
        "next_step": "Fill hypothesis.md BEFORE running anything.",
        "required_files": list(REQUIRED_SECTIONS.keys()),
    }


@mcp.tool()
def checkin_project_experiment(
    project_id: str,
    experiment_id: str,
    agent_id: str,
    outcome_direction: Literal["positive", "negative", "inconclusive", "derailed"],
    one_line: str,
    derailment_type: Optional[Literal["implementation_error", "bad_hypothesis", "data_issue", "scope_creep"]] = None,
    surprising: bool = False,
) -> dict:
    """Check in a completed project experiment. Same rules as checkin()."""
    exp_path = projects_dir() / project_id / "experiments" / experiment_id
    if not exp_path.exists():
        return {"error": "Experiment not found"}

    status_data = json.loads((exp_path / "status.json").read_text())
    if status_data.get("status") == "complete":
        return {"error": "Already checked in. Experiments are immutable after checkin."}
    if status_data.get("checked_out_by") != agent_id:
        return {"error": f"Checked out by {status_data.get('checked_out_by')}, not {agent_id}."}
    if outcome_direction == "derailed" and not derailment_type:
        return {"error": "derailment_type is required when outcome_direction is 'derailed'."}

    errors = _validate_docs(exp_path)
    if errors:
        return {"error": "Documentation incomplete — cannot check in.", "issues": errors}

    status_data.update({
        "status": "complete",
        "checked_in_at": now_iso(),
        "outcome_direction": outcome_direction,
        "derailment_type": derailment_type,
        "surprising": surprising,
        "locked": True,
    })
    (exp_path / "status.json").write_text(json.dumps(status_data, indent=2))

    manifest = json.loads((exp_path / "manifest.json").read_text())
    manifest.update({"outcome_direction": outcome_direction, "surprising": surprising, "one_line": one_line})
    (exp_path / "manifest.json").write_text(json.dumps(manifest, indent=2))

    idx = load_index()
    for exp in idx["projects"][project_id].get("experiments", []):
        if exp["id"] == experiment_id:
            exp.update({"status": "complete", "outcome_direction": outcome_direction, "one_line": one_line})
    save_index(idx)
    snapshot(f"checkin {experiment_id}: {outcome_direction} — {one_line}",
             session_id=manifest.get("session_id"))
    return {"status": "checked_in", "experiment_id": experiment_id, "outcome": outcome_direction}


@mcp.tool()
def list_project_experiments(project_id: str) -> list[dict]:
    """List all experiments under a project with status and confidence."""
    idx = load_index()
    project = idx.get("projects", {}).get(project_id)
    if not project:
        return []
    return [
        {**exp, "confidence": compute_confidence(exp["id"], project_id=project_id)}
        for exp in project.get("experiments", [])
    ]


# ──────────────────────────────────────────────────────────────
# TOOLS: Sessions
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def open_session(goal: str, agent_id: str, loop_type: str = "general") -> dict:
    """
    Open a research session. Reference the returned session_id in checkout/create_synthesis
    calls to link work to a session. Enables full audit trail of an agent run.
    """
    ensure_dirs()
    session_id = make_session_id()
    session = {
        "id": session_id,
        "goal": goal,
        "agent_id": agent_id,
        "loop_type": loop_type,
        "status": "open",
        "opened_at": now_iso(),
    }
    (sessions_dir() / f"{session_id}.json").write_text(json.dumps(session, indent=2))
    idx = load_index()
    idx.setdefault("sessions", {})[session_id] = {
        "goal": goal[:120],
        "agent_id": agent_id,
        "status": "open",
        "opened_at": session["opened_at"],
    }
    save_index(idx)
    return {"session_id": session_id}


@mcp.tool()
def close_session(
    session_id: str,
    status: Literal["success", "derailed", "inconclusive"],
    postmortem: str,
) -> dict:
    """
    Close a session with a mandatory postmortem.
    If status is 'derailed', explain clearly what went wrong and why.
    Postmortem must be at least 50 characters — this is not optional.
    """
    p = sessions_dir() / f"{session_id}.json"
    if not p.exists():
        return {"error": "Session not found"}
    if len(postmortem.strip()) < 50:
        return {"error": "Postmortem too short. Write a real explanation (min 50 chars)."}
    session = json.loads(p.read_text())
    session.update({"status": status, "postmortem": postmortem, "closed_at": now_iso()})
    p.write_text(json.dumps(session, indent=2))
    idx = load_index()
    if session_id in idx.get("sessions", {}):
        idx["sessions"][session_id]["status"] = status
    save_index(idx)
    return {"status": "closed", "session_status": status}


@mcp.tool()
def list_sessions(status: str = None) -> list[dict]:
    """List sessions, optionally filtered by status (open/success/derailed/inconclusive)."""
    ensure_dirs()
    sessions = [json.loads(f.read_text()) for f in sessions_dir().glob("*.json")]
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    return sorted([{
        "id": s["id"],
        "goal": s.get("goal"),
        "agent_id": s.get("agent_id"),
        "loop_type": s.get("loop_type"),
        "status": s.get("status"),
        "opened_at": s.get("opened_at"),
        "closed_at": s.get("closed_at"),
        "postmortem_preview": s.get("postmortem", "")[:120] if s.get("postmortem") else None,
    } for s in sessions], key=lambda x: x.get("opened_at", ""), reverse=True)


# ──────────────────────────────────────────────────────────────
# TOOLS: Reviews
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def submit_review(
    target_id: str,
    reviewer_agent: str,
    review_type: Literal["methodology", "reproduction", "synthesis"],
    verdict: Literal["sound", "flawed", "inconclusive", "overclaiming"],
    critique: str,
    paper_id: str = None,
    reproduction_experiment_id: str = None,
) -> dict:
    """
    Submit a review for an experiment or synthesis.

    paper_id: required when reviewing a paper experiment (not a synthesis).
    Reviews are evidence, not gates. Confidence scores are weighted by reviewer
    track record — a single bad review does not block anything.

    review_type:
      methodology   — critique hypothesis, implementation, data docs (no re-running)
      reproduction  — independently re-ran the experiment
      synthesis     — evaluated a cluster of related experiments for coherence

    verdict scoring: sound=1.0, inconclusive=0.6, overclaiming=0.4, flawed=0.2
    All weighted by reviewer accuracy score (computed from prediction vs outcome history).
    """
    if len(critique.strip()) < 30:
        return {"error": "Critique too short. Provide substantive feedback (min 30 chars)."}

    if paper_id:
        reviews_dir = papers_dir() / paper_id / "experiments" / target_id / "reviews"
    else:
        reviews_dir = synthesis_dir() / target_id / "reviews"

    if not reviews_dir.parent.exists():
        return {"error": "Target experiment not found"}
    reviews_dir.mkdir(exist_ok=True)

    review_id = make_review_id()
    review = {
        "id": review_id,
        "target_id": target_id,
        "reviewer_agent": reviewer_agent,
        "review_type": review_type,
        "verdict": verdict,
        "critique": critique,
        "reproduction_experiment_id": reproduction_experiment_id,
        "submitted_at": now_iso(),
    }
    (reviews_dir / f"{review_id}.json").write_text(json.dumps(review, indent=2))

    reviewers = load_reviewers()
    reviewers.setdefault(reviewer_agent, {
        "review_accuracy_score": 0.7,
        "review_count": 0,
        "reviews": [],
    })
    reviewers[reviewer_agent]["review_count"] += 1
    reviewers[reviewer_agent]["reviews"].append(review_id)
    save_reviewers(reviewers)

    return {"status": "submitted", "review_id": review_id,
            "note": "Confidence scores are evidence-weighted, not binary blocks."}


@mcp.tool()
def update_reviewer_accuracy(reviewer_agent: str, accuracy_score: float) -> dict:
    """
    Update a reviewer's accuracy score based on how their reviews track with
    reproduction outcomes. Score should be 0.0-1.0.
    Call this after a reproduction experiment resolves a contested review.
    """
    if not 0.0 <= accuracy_score <= 1.0:
        return {"error": "accuracy_score must be between 0.0 and 1.0"}
    reviewers = load_reviewers()
    reviewers.setdefault(reviewer_agent, {"review_count": 0, "reviews": []})
    reviewers[reviewer_agent]["review_accuracy_score"] = round(accuracy_score, 3)
    save_reviewers(reviewers)
    return {"status": "updated", "reviewer": reviewer_agent, "new_score": accuracy_score}


@mcp.tool()
def get_review_summary(target_id: str, paper_id: str = None) -> dict:
    """Get aggregated review info and confidence score for an experiment or synthesis."""
    reviews = _load_reviews_for(target_id, paper_id)
    if not reviews:
        return {"target_id": target_id, "review_count": 0, "confidence": 1.0, "verdict_breakdown": {}}
    verdict_counts: dict = {}
    for r in reviews:
        v = r.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    return {
        "target_id": target_id,
        "review_count": len(reviews),
        "confidence": compute_confidence(target_id, paper_id),
        "verdict_breakdown": verdict_counts,
        "reviews": [{
            "id": r["id"],
            "reviewer": r.get("reviewer_agent"),
            "type": r.get("review_type"),
            "verdict": r.get("verdict"),
            "critique_preview": r.get("critique", "")[:150],
        } for r in reviews],
    }


@mcp.tool()
def find_contested() -> list[dict]:
    """Find experiments where reviews disagree — prime targets for synthesis or reproduction."""
    ensure_dirs()
    idx = load_index()
    out = []
    for paper_id, paper_data in idx.get("papers", {}).items():
        for exp in paper_data.get("experiments", []):
            reviews = _load_reviews_for(exp["id"], paper_id)
            verdicts = {r.get("verdict") for r in reviews}
            if len(verdicts) > 1 and "sound" in verdicts and verdicts & {"flawed", "overclaiming"}:
                out.append({
                    "paper_id": paper_id,
                    "experiment_id": exp["id"],
                    "name": exp.get("name"),
                    "verdicts": list(verdicts),
                    "review_count": len(reviews),
                    "confidence": compute_confidence(exp["id"], paper_id),
                })
    return out


@mcp.tool()
def list_unreviewed(min_age_hours: int = 0) -> list[dict]:
    """List completed experiments with no reviews yet. For librarian agent use."""
    ensure_dirs()
    idx = load_index()
    now = datetime.now(timezone.utc)
    out = []

    def _check(exp, root_type, root_id, st_base_path):
        if exp.get("status") != "complete":
            return
        if _load_reviews_for(exp["id"],
                              paper_id=root_id if root_type == "paper" else None,
                              project_id=root_id if root_type == "project" else None):
            return
        st_path = st_base_path / exp["id"] / "status.json"
        if st_path.exists() and min_age_hours > 0:
            st = json.loads(st_path.read_text())
            checked_in = st.get("checked_in_at")
            if checked_in:
                age_h = (now - datetime.fromisoformat(checked_in)).total_seconds() / 3600
                if age_h < min_age_hours:
                    return
        out.append({
            "root_type": root_type,
            "root_id": root_id,
            "experiment_id": exp["id"],
            "name": exp.get("name"),
            "outcome_direction": exp.get("outcome_direction"),
            "concepts": exp.get("concepts", []),
        })

    for paper_id, paper_data in idx.get("papers", {}).items():
        base = papers_dir() / paper_id / "experiments"
        for exp in paper_data.get("experiments", []):
            _check(exp, "paper", paper_id, base)
    for project_id, project_data in idx.get("projects", {}).items():
        base = projects_dir() / project_id / "experiments"
        for exp in project_data.get("experiments", []):
            _check(exp, "project", project_id, base)
    return out


# ──────────────────────────────────────────────────────────────
# TOOLS: Librarian / Discovery
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def suggest_synthesis(
    seed_ids: list[str],
    strategy: Literal["sibling", "cross_paper", "cross_gen", "open"] = "open",
    min_confidence: float = 0.3,
) -> list[dict]:
    """
    Given seed experiment IDs, find the best synthesis candidates.

    Finds experiments that share concepts but differ on axes, come from different roots,
    or have surprising / contradictory results worth combining.

    strategy:
      sibling     — same paper root
      cross_paper — different paper roots
      cross_gen   — different generation depths
      open        — no constraint, ranked by overlap + confidence + surprise
    """
    ensure_dirs()
    idx = load_index()

    seed_concepts: set = set()
    seed_paper_ids: set = set()
    seed_project_ids: set = set()
    seed_generations: set = set()
    for seed_id in seed_ids:
        for paper_id, paper_data in idx.get("papers", {}).items():
            for exp in paper_data.get("experiments", []):
                if exp["id"] == seed_id:
                    seed_concepts.update(exp.get("concepts", []))
                    seed_paper_ids.add(paper_id)
                    seed_generations.add(compute_generation(seed_id, idx))
        for project_id, project_data in idx.get("projects", {}).items():
            for exp in project_data.get("experiments", []):
                if exp["id"] == seed_id:
                    seed_concepts.update(exp.get("concepts", []))
                    seed_project_ids.add(project_id)
                    seed_generations.add(compute_generation(seed_id, idx))

    candidates = []

    def _eval_candidate(exp, root_id, root_type):
        if exp["id"] in seed_ids or exp.get("status") != "complete":
            return
        conf = compute_confidence(exp["id"],
                                  paper_id=root_id if root_type == "paper" else None,
                                  project_id=root_id if root_type == "project" else None)
        if conf < min_confidence:
            return
        overlap = seed_concepts & set(exp.get("concepts", []))
        if not overlap:
            return
        is_sibling = (root_id in seed_paper_ids) or (root_id in seed_project_ids)
        gen = compute_generation(exp["id"], idx)
        is_cross_gen = gen not in seed_generations
        if strategy == "sibling" and not is_sibling:
            return
        if strategy == "cross_paper" and is_sibling:
            return
        if strategy == "cross_gen" and not is_cross_gen:
            return
        rationale_parts = [f"Shares concepts: {', '.join(overlap)}."]
        if is_sibling:
            rationale_parts.append(f"Same-{root_type} sibling.")
        else:
            rationale_parts.append(f"Cross-{root_type} lineage.")
        if is_cross_gen:
            rationale_parts.append(f"Different generation (gen {gen}).")
        if exp.get("surprising"):
            rationale_parts.append("Marked surprising — high synthesis value.")
        candidates.append({
            "root_type": root_type,
            "root_id": root_id,
            "experiment_id": exp["id"],
            "name": exp.get("name"),
            "concepts": exp.get("concepts", []),
            "shared_concepts": list(overlap),
            "outcome_direction": exp.get("outcome_direction"),
            "generation": gen,
            "confidence": conf,
            "rationale": " ".join(rationale_parts),
            "score": len(overlap) * conf + (0.3 if exp.get("surprising") else 0),
        })

    for paper_id, paper_data in idx.get("papers", {}).items():
        for exp in paper_data.get("experiments", []):
            _eval_candidate(exp, paper_id, "paper")
    for project_id, project_data in idx.get("projects", {}).items():
        for exp in project_data.get("experiments", []):
            _eval_candidate(exp, project_id, "project")

    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:10]


@mcp.tool()
def find_contradictions() -> list[dict]:
    """
    Find experiments with shared concepts but opposite outcome directions.
    These are the highest-value synthesis targets — same idea, different result.
    """
    ensure_dirs()
    idx = load_index()
    all_exps = [
        {**exp, "root_type": "paper", "root_id": paper_id}
        for paper_id, paper_data in idx.get("papers", {}).items()
        for exp in paper_data.get("experiments", [])
        if exp.get("status") == "complete"
    ] + [
        {**exp, "root_type": "project", "root_id": project_id}
        for project_id, project_data in idx.get("projects", {}).items()
        for exp in project_data.get("experiments", [])
        if exp.get("status") == "complete"
    ]
    out = []
    for i, a in enumerate(all_exps):
        for b in all_exps[i + 1:]:
            shared = set(a.get("concepts", [])) & set(b.get("concepts", []))
            if not shared:
                continue
            if {a.get("outcome_direction"), b.get("outcome_direction")} == {"positive", "negative"}:
                out.append({
                    "experiment_a": {"id": a["id"], "root_type": a["root_type"], "root_id": a["root_id"],
                                     "name": a.get("name"), "outcome": a.get("outcome_direction")},
                    "experiment_b": {"id": b["id"], "root_type": b["root_type"], "root_id": b["root_id"],
                                     "name": b.get("name"), "outcome": b.get("outcome_direction")},
                    "shared_concepts": list(shared),
                    "note": "Opposite outcomes on shared concepts — strong synthesis candidate",
                })
    return out


@mcp.tool()
def find_derailments(derailment_type: str = None) -> list[dict]:
    """
    Find derailed experiments, optionally filtered by type.
    Useful for pattern-matching: if multiple experiments derail on 'data_issue'
    around the same concepts, that's a structural problem worth addressing.
    """
    ensure_dirs()
    idx = load_index()
    out = []
    for paper_id, paper_data in idx.get("papers", {}).items():
        for exp in paper_data.get("experiments", []):
            if exp.get("outcome_direction") != "derailed":
                continue
            st_path = papers_dir() / paper_id / "experiments" / exp["id"] / "status.json"
            if not st_path.exists():
                continue
            st = json.loads(st_path.read_text())
            dt = st.get("derailment_type")
            if derailment_type and dt != derailment_type:
                continue
            out.append({
                "root_type": "paper", "root_id": paper_id,
                "experiment_id": exp["id"], "name": exp.get("name"),
                "derailment_type": dt, "concepts": exp.get("concepts", []),
            })
    for project_id, project_data in idx.get("projects", {}).items():
        for exp in project_data.get("experiments", []):
            if exp.get("outcome_direction") != "derailed":
                continue
            st_path = projects_dir() / project_id / "experiments" / exp["id"] / "status.json"
            if not st_path.exists():
                continue
            st = json.loads(st_path.read_text())
            dt = st.get("derailment_type")
            if derailment_type and dt != derailment_type:
                continue
            out.append({
                "root_type": "project", "root_id": project_id,
                "experiment_id": exp["id"], "name": exp.get("name"),
                "derailment_type": dt, "concepts": exp.get("concepts", []),
            })
    return out


@mcp.tool()
def find_underexplored(max_experiments: int = 2) -> list[dict]:
    """Papers with few experiments relative to their size — candidates for more work."""
    ensure_dirs()
    idx = load_index()
    results = []
    for pid, p in idx.get("papers", {}).items():
        if len(p.get("experiments", [])) <= max_experiments:
            results.append({
                "root_type": "paper", "root_id": pid,
                "label": p.get("title"),
                "experiment_count": len(p.get("experiments", [])),
                "categories": p.get("categories", []),
            })
    for pid, p in idx.get("projects", {}).items():
        if len(p.get("experiments", [])) <= max_experiments:
            results.append({
                "root_type": "project", "root_id": pid,
                "label": p.get("name"),
                "experiment_count": len(p.get("experiments", [])),
                "description": p.get("description", ""),
            })
    return sorted(results, key=lambda x: x["experiment_count"])


@mcp.tool()
def browse_lineage(node_id: str) -> dict:
    """Get the full ancestor and descendant tree for any experiment or synthesis node."""
    ensure_dirs()
    idx = load_index()

    def ancestors(nid, visited=None):
        if visited is None:
            visited = set()
        if nid in visited:
            return []
        visited.add(nid)
        m = _get_manifest(nid, idx)
        if not m:
            return []
        parents = m.get("derived_from", [])
        return list(parents) + [a for p in parents for a in ancestors(p, visited)]

    def descendants(nid):
        desc = []
        for paper_id, paper_data in idx.get("papers", {}).items():
            for exp in paper_data.get("experiments", []):
                mp = papers_dir() / paper_id / "experiments" / exp["id"] / "manifest.json"
                if mp.exists() and nid in json.loads(mp.read_text()).get("derived_from", []):
                    desc.append(exp["id"])
                    desc.extend(descendants(exp["id"]))
        for sid in idx.get("synthesis", {}):
            mp = synthesis_dir() / sid / "manifest.json"
            if mp.exists() and nid in json.loads(mp.read_text()).get("derived_from", []):
                desc.append(sid)
                desc.extend(descendants(sid))
        return list(set(desc))

    return {
        "node_id": node_id,
        "generation": compute_generation(node_id, idx),
        "ancestors": list(set(ancestors(node_id))),
        "descendants": descendants(node_id),
    }


# ──────────────────────────────────────────────────────────────
# TOOLS: Graph
# ──────────────────────────────────────────────────────────────

@mcp.tool()
def get_graph(root_id: str = None, max_depth: int = None) -> dict:
    """
    Return the full research graph as {nodes, edges} for agent reasoning.
    Each node has: id, type, label, generation, status, outcome_direction,
    concepts, confidence, surprising.
    Each edge has: source, target, type (contains | derived_from).
    """
    ensure_dirs()
    idx = load_index()
    nodes, edges, seen = [], [], set()

    for paper_id, paper_data in idx.get("papers", {}).items():
        if root_id and paper_id != root_id:
            continue
        if paper_id not in seen:
            seen.add(paper_id)
            nodes.append({
                "id": paper_id,
                "type": "paper",
                "label": paper_data.get("title", paper_id)[:60],
                "generation": 0,
                "status": "root",
                "concepts": paper_data.get("concepts", []),
                "confidence": 1.0,
            })
        for exp in paper_data.get("experiments", []):
            eid = exp["id"]
            if eid in seen:
                continue
            gen = compute_generation(eid, idx)
            if max_depth is not None and gen > max_depth:
                continue
            seen.add(eid)
            mp = papers_dir() / paper_id / "experiments" / eid / "manifest.json"
            manifest = json.loads(mp.read_text()) if mp.exists() else {}
            nodes.append({
                "id": eid,
                "type": "experiment",
                "label": exp.get("name", eid)[:60],
                "paper_id": paper_id,
                "generation": gen,
                "status": exp.get("status"),
                "outcome_direction": exp.get("outcome_direction"),
                "concepts": exp.get("concepts", []),
                "confidence": compute_confidence(eid, paper_id),
                "surprising": manifest.get("surprising", False),
            })
            edges.append({"source": paper_id, "target": eid, "type": "contains"})
            for parent in manifest.get("derived_from", []):
                edges.append({"source": parent, "target": eid, "type": "derived_from"})

    for sid, s_data in idx.get("synthesis", {}).items():
        if sid in seen:
            continue
        seen.add(sid)
        gen = compute_generation(sid, idx)
        mp = synthesis_dir() / sid / "manifest.json"
        manifest = json.loads(mp.read_text()) if mp.exists() else {}
        nodes.append({
            "id": sid,
            "type": "synthesis",
            "label": s_data.get("name", sid)[:60],
            "generation": gen,
            "status": s_data.get("status"),
            "outcome_direction": s_data.get("outcome_direction"),
            "concepts": s_data.get("concepts", []),
            "confidence": compute_confidence(sid),
            "surprising": manifest.get("surprising", False),
        })
        for parent in manifest.get("derived_from", []):
            edges.append({"source": parent, "target": sid, "type": "derived_from"})

    for idea_id, idea_data in idx.get("ideas", {}).items():
        if idea_data.get("status") == "unresearched":
            nodes.append({
                "id": idea_id,
                "type": "idea",
                "label": idea_data.get("hypothesis", "")[:60],
                "generation": None,
                "status": "unresearched",
                "confidence": None,
            })

    return {"nodes": nodes, "edges": edges,
            "node_count": len(nodes), "edge_count": len(edges)}


@mcp.tool()
def export_graph(output_path: str = None) -> dict:
    """
    Export the research graph as a self-contained interactive HTML file.
    D3 force-directed layout. Nodes colored by type and outcome direction.
    Opacity encodes confidence. Surprising nodes have a white ring.
    Hover for full detail. Drag to explore.
    Returns the path to the generated file.
    """
    graph = get_graph()
    if not output_path:
        output_path = str(storage() / "graph.html")

    node_colors = {"paper": "#4A9EFF", "experiment": "#52c41a", "synthesis": "#FFD93D", "idea": "#FF8B94"}
    outcome_colors = {"positive": "#52c41a", "negative": "#ff4d4f",
                      "inconclusive": "#faad14", "derailed": "#b37feb"}

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Research Graph</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; font-family: 'JetBrains Mono', 'Fira Code', monospace; color: #e6edf3; overflow: hidden; }}
  svg {{ width: 100vw; height: 100vh; }}
  .tooltip {{
    position: fixed; background: #161b22cc; border: 1px solid #30363d;
    backdrop-filter: blur(8px); padding: 12px 16px; border-radius: 8px;
    pointer-events: none; font-size: 12px; max-width: 280px; line-height: 1.7;
    box-shadow: 0 8px 32px #0008; z-index: 100;
  }}
  .tooltip strong {{ color: #79c0ff; font-size: 13px; }}
  .tooltip .dim {{ color: #8b949e; }}
  .legend {{
    position: fixed; bottom: 24px; left: 24px; background: #161b22cc;
    border: 1px solid #30363d; backdrop-filter: blur(8px);
    padding: 14px 18px; border-radius: 8px; font-size: 11px; min-width: 160px;
  }}
  .legend h4 {{ color: #8b949e; margin-bottom: 8px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }}
  .legend-row {{ display: flex; align-items: center; gap: 8px; margin: 5px 0; color: #c9d1d9; }}
  .dot {{ width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }}
  .stats {{
    position: fixed; top: 24px; right: 24px; background: #161b22cc;
    border: 1px solid #30363d; backdrop-filter: blur(8px);
    padding: 14px 18px; border-radius: 8px; font-size: 11px;
    color: #8b949e; line-height: 2;
  }}
  .stats span {{ color: #e6edf3; }}
</style>
</head>
<body>
<svg id="g"></svg>
<div class="tooltip" id="tip" style="display:none"></div>
<div class="legend">
  <h4>Node Type</h4>
  {"".join(f'<div class="legend-row"><div class="dot" style="background:{c}"></div>{t}</div>' for t, c in node_colors.items())}
  <h4 style="margin-top:12px">Outcome</h4>
  {"".join(f'<div class="legend-row"><div class="dot" style="background:{c}"></div>{o}</div>' for o, c in outcome_colors.items())}
  <h4 style="margin-top:12px">Encoding</h4>
  <div class="legend-row"><div class="dot" style="background:#aaa;border:2px solid #fff"></div>surprising</div>
  <div class="legend-row" style="color:#8b949e;font-size:10px">opacity = confidence</div>
</div>
<div class="stats">
  nodes <span>{graph['node_count']}</span> &nbsp; edges <span>{graph['edge_count']}</span>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const G = {json.dumps(graph)};
const NODE_COLORS = {json.dumps(node_colors)};
const OUTCOME_COLORS = {json.dumps(outcome_colors)};
const W = window.innerWidth, H = window.innerHeight;

const svg = d3.select("#g").attr("viewBox", [0, 0, W, H]);
svg.append("defs").append("marker")
  .attr("id","arr").attr("viewBox","0 -5 10 10").attr("refX",22).attr("refY",0)
  .attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto")
  .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","#30363d");

const zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);
const g = svg.append("g");

const sim = d3.forceSimulation(G.nodes)
  .force("link", d3.forceLink(G.edges).id(d=>d.id).distance(d => d.type==="contains" ? 80 : 140))
  .force("charge", d3.forceManyBody().strength(-400))
  .force("center", d3.forceCenter(W/2, H/2))
  .force("collision", d3.forceCollide(d => nodeR(d) + 8));

function nodeR(d) {{
  return d.type==="paper" ? 18 : d.type==="synthesis" ? 14 : d.type==="idea" ? 8 : 10;
}}
function nodeColor(d) {{
  if (d.outcome_direction && OUTCOME_COLORS[d.outcome_direction]) return OUTCOME_COLORS[d.outcome_direction];
  return NODE_COLORS[d.type] || "#888";
}}

const link = g.append("g").selectAll("line").data(G.edges).join("line")
  .attr("stroke", d => d.type==="contains" ? "#21262d" : "#30363d")
  .attr("stroke-width", d => d.type==="contains" ? 1 : 1.5)
  .attr("stroke-dasharray", d => d.type==="contains" ? "4,3" : null)
  .attr("marker-end", d => d.type==="derived_from" ? "url(#arr)" : null);

const node = g.append("g").selectAll("circle").data(G.nodes).join("circle")
  .attr("r", nodeR)
  .attr("fill", nodeColor)
  .attr("stroke", d => d.surprising ? "#fff" : "none")
  .attr("stroke-width", 2.5)
  .attr("opacity", d => d.confidence != null ? Math.max(0.35, d.confidence) : 0.85)
  .style("cursor","pointer")
  .call(d3.drag()
    .on("start", (e,d) => {{ if(!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on("drag",  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
    .on("end",   (e,d) => {{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}));

const label = g.append("g").selectAll("text").data(G.nodes).join("text")
  .attr("font-size", d => d.type==="paper" ? 11 : 9)
  .attr("fill", "#8b949e").attr("text-anchor","middle")
  .attr("dy", d => nodeR(d) + 13)
  .text(d => d.label.length > 32 ? d.label.slice(0,32)+"…" : d.label);

const tip = d3.select("#tip");
node.on("mouseover", (e,d) => {{
  const lines = [
    `<strong>${{d.label}}</strong>`,
    `<span class="dim">type</span> ${{d.type}}`,
    d.generation != null ? `<span class="dim">generation</span> ${{d.generation}}` : "",
    d.status ? `<span class="dim">status</span> ${{d.status}}` : "",
    d.outcome_direction ? `<span class="dim">outcome</span> ${{d.outcome_direction}}` : "",
    d.confidence != null ? `<span class="dim">confidence</span> ${{(d.confidence*100).toFixed(0)}}%` : "",
    d.concepts?.length ? `<span class="dim">concepts</span> ${{d.concepts.join(", ")}}` : "",
    d.surprising ? `<span style="color:#ffd700">★ surprising result</span>` : "",
  ].filter(Boolean).join("<br>");
  tip.style("display","block").style("left",(e.clientX+14)+"px").style("top",(e.clientY-10)+"px").html(lines);
}}).on("mousemove", e => {{
  tip.style("left",(e.clientX+14)+"px").style("top",(e.clientY-10)+"px");
}}).on("mouseout", () => tip.style("display","none"));

sim.on("tick", () => {{
  link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
      .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  node.attr("cx",d=>d.x).attr("cy",d=>d.y);
  label.attr("x",d=>d.x).attr("y",d=>d.y);
}});
</script>
</body>
</html>"""

    Path(output_path).write_text(html)
    return {"status": "exported", "path": output_path,
            "note": "Open in any browser. Drag nodes, scroll to zoom."}


# ──────────────────────────────────────────────────────────────
# TOOLS: Git
# ──────────────────────────────────────────────────────────────

import subprocess


def _git(args: list[str], cwd: Path = None) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    cwd = cwd or storage()
    r = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _git_ok(args: list[str], cwd: Path = None) -> dict:
    code, out, err = _git(args, cwd)
    if code != 0:
        return {"error": err or out}
    return {"ok": True, "output": out}


@mcp.tool()
def init_repo(remote_url: str = None) -> dict:
    """
    Initialize the storage directory as a git repository.
    Writes a sensible .gitignore and makes an initial commit.
    Optionally adds a remote and pushes.

    Run once when setting up a new storage path.
    """
    ensure_dirs()
    root = storage()

    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code == 0:
        return {"error": "Already a git repository. Nothing to do."}

    gitignore = root / ".gitignore"
    gitignore.write_text("__pycache__/\n*.pyc\n*.pyo\n.DS_Store\ngraph.html\n")

    for step in [
        ["init"],
        ["add", "."],
        ["commit", "-m", "init stacks"],
    ]:
        result = _git_ok(step)
        if "error" in result:
            return result

    if remote_url:
        for step in [
            ["remote", "add", "origin", remote_url],
            ["push", "-u", "origin", "main"],
        ]:
            result = _git_ok(step)
            if "error" in result:
                return result
        return {"ok": True, "remote": remote_url}

    return {"ok": True, "note": "Repo initialized locally. Add a remote with git remote add origin <url> when ready."}


@mcp.tool()
def snapshot(message: str, session_id: str = None) -> dict:
    """
    Commit all current changes to the store.

    Called automatically on checkin and checkin_synthesis.
    Can also be called manually at any point — e.g. after annotating
    a paper or recording ideas.

    If the storage directory is not a git repo, returns an error without
    touching anything.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return {"error": "Storage directory is not a git repository. Run init_repo first."}

    code, out, _ = _git(["status", "--porcelain"])
    if code == 0 and not out:
        return {"ok": True, "note": "Nothing to commit."}

    full_msg = f"{message} [{session_id}]" if session_id else message
    for step in [["add", "-A"], ["commit", "-m", full_msg]]:
        result = _git_ok(step)
        if "error" in result:
            return result

    _, sha, _ = _git(["rev-parse", "--short", "HEAD"])
    return {"ok": True, "commit": sha, "message": full_msg}


@mcp.tool()
def push(remote: str = "origin", branch: str = "main") -> dict:
    """Push committed changes to the remote. Run after closing a session."""
    return _git_ok(["push", remote, branch])


@mcp.tool()
def branch_session(session_id: str) -> dict:
    """
    Create and switch to a branch named after a session ID.
    Enables per-agent branch isolation — merge or PR when the session closes.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return {"error": "Not a git repository."}
    result = _git_ok(["checkout", "-b", session_id])
    if "error" in result:
        return result
    return {"ok": True, "branch": session_id}


@mcp.tool()
def merge_session(session_id: str, delete_branch: bool = True) -> dict:
    """
    Merge a session branch back into main and optionally delete it.
    Call after close_session when working with branch-per-agent isolation.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return {"error": "Not a git repository."}

    for step in [
        ["checkout", "main"],
        ["merge", "--no-ff", session_id, "-m", f"merge session {session_id}"],
    ]:
        result = _git_ok(step)
        if "error" in result:
            return result

    if delete_branch:
        _git(["branch", "-d", session_id])

    return {"ok": True, "merged": session_id}


@mcp.tool()
def rollback_experiment(experiment_id: str, paper_id: str = None, project_id: str = None) -> dict:
    """
    Restore a specific experiment directory to its last committed state.
    Discards any uncommitted changes to that experiment only — nothing else is touched.

    Useful when an agent has partially written docs and you want to start over
    without losing the rest of the store.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return {"error": "Not a git repository."}

    if paper_id:
        rel_path = f"papers/{paper_id}/experiments/{experiment_id}"
    elif project_id:
        rel_path = f"projects/{project_id}/experiments/{experiment_id}"
    else:
        return {"error": "Provide either paper_id or project_id."}

    result = _git_ok(["checkout", "HEAD", "--", rel_path])
    if "error" in result:
        return result
    return {"ok": True, "restored": rel_path}


@mcp.tool()
def diff_experiment(experiment_id: str, paper_id: str = None, project_id: str = None) -> dict:
    """
    Show uncommitted changes to a specific experiment directory.
    Useful during review — see exactly what changed since last commit.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return {"error": "Not a git repository."}

    if paper_id:
        rel_path = f"papers/{paper_id}/experiments/{experiment_id}"
    elif project_id:
        rel_path = f"projects/{project_id}/experiments/{experiment_id}"
    else:
        return {"error": "Provide either paper_id or project_id."}

    _, diff, _ = _git(["diff", "HEAD", "--", rel_path])
    _, stat, _ = _git(["diff", "HEAD", "--stat", "--", rel_path])
    return {"path": rel_path, "stat": stat, "diff": diff or "No uncommitted changes."}


@mcp.tool()
def git_log(n: int = 20, experiment_id: str = None, paper_id: str = None, project_id: str = None) -> list[dict]:
    """
    Show recent commits, optionally scoped to a specific experiment directory.
    Gives a chronological record of all agent activity on a piece of work.
    """
    code, _, _ = _git(["rev-parse", "--git-dir"])
    if code != 0:
        return [{"error": "Not a git repository."}]

    args = ["log", f"-{n}", "--pretty=format:%H|%h|%ai|%s"]
    if experiment_id:
        if paper_id:
            args += ["--", f"papers/{paper_id}/experiments/{experiment_id}"]
        elif project_id:
            args += ["--", f"projects/{project_id}/experiments/{experiment_id}"]

    _, out, _ = _git(args)
    if not out:
        return []
    entries = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            entries.append({"sha": parts[1], "full_sha": parts[0],
                             "timestamp": parts[2], "message": parts[3]})
    return entries


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

def main():
    global STORAGE
    parser = argparse.ArgumentParser(description="Research Tracker MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="stdio: each agent spawns its own process (default). "
                             "sse: persistent server, all agents connect over HTTP.")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--storage-path", default=str(Path.home() / "research"),
                        help="Path to research data directory (shared across all agent sessions)")
    args = parser.parse_args()

    STORAGE = Path(args.storage_path).expanduser()
    ensure_dirs()

    if args.transport == "sse":
        print(f"[research-tracker] SSE server on {args.host}:{args.port}")
        print(f"[research-tracker] Storage: {STORAGE}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()