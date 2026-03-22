# research-tracker-mcp

> The memory and accountability layer for agentic research loops.

Most agent research tools — including auto-research loops — have no persistent audit trail. An agent explores a paper, runs some experiments, reaches a conclusion, and then that work is gone. The next agent starts from scratch, repeats the same mistakes, or worse: builds confidently on a broken implementation.

This is the missing piece.

## What it does

- **Paper store** — search arXiv, download papers locally as markdown
- **Experiment tracking** — checkout/checkin with documentation enforcement. Hypothesis locked at checkout. Checkin refused if docs are incomplete.
- **Lineage graph** — every experiment knows what it was derived from. Generation depth computed automatically. Siblings, cross-paper synthesis, and mixed-generation combinations are all just different graph shapes.
- **Synthesis** — first-class experiment type derived from any combination of other experiments or papers. This is where cross-pollination lives structurally.
- **Ideas backlog** — record future hypotheses with inspiration pointers for the librarian agent
- **Sessions** — wrap an agent run with a goal and mandatory postmortem. Derailed sessions are logged with explanation.
- **Reviews** — methodology, reproduction, and synthesis reviews. Confidence scores are evidence-weighted by reviewer track record, not binary blocks. A single bad review doesn't kill good work.
- **Graph visualization** — interactive D3 force-directed graph exported as self-contained HTML. Opacity = confidence. White ring = surprising result.

## Setup

```bash
git clone https://github.com/yourname/research-tracker-mcp
cd research-tracker-mcp
uv sync
```

## MCP config (stdio — recommended for personal use)

Each agent session spawns its own process. Storage is shared via filesystem.

```json
{
  "mcpServers": {
    "research": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/research-tracker-mcp",
        "run", "server.py",
        "--storage-path", "/path/to/your/research"
      ]
    }
  }
}
```

## MCP config (SSE — for home lab / persistent server)

Run once, all clients connect:

```bash
uv run server.py --transport sse --storage-path ~/research
```

```json
{
  "mcpServers": {
    "research": {
      "transport": "sse",
      "url": "http://localhost:8050/sse"
    }
  }
}
```

## Storage layout

```
~/research/
  index.json                          # fast search index, updated on every write
  reviewers.json                      # reviewer track records + accuracy scores
  papers/
    {arxiv_id}/
      metadata.json
      paper.md
      annotations.md
      experiments/
        {exp_id}/
          manifest.json               # derived_from, concepts, hyperparameter_axes
          hypothesis.md               # LOCKED at checkout — written before any code
          implementation.md
          data.md                     # source, location, structure, preprocessing
          outcomes/
            raw.md                    # numbers, run conditions
            learnings.md              # did it match hypothesis? what did it rule out?
            paper.md                  # optional: numbers-narrative-numbers format
          reviews/
            {review_id}.json
          status.json                 # checked_out_by, intent, locked
  synthesis/
    {synth_id}/                       # same layout as experiments
  ideas/
    {idea_id}.json
  sessions/
    {session_id}.json
  graph.html                          # last export_graph() output
```

## Tool reference

### Papers
| Tool | Description |
|---|---|
| `search_papers` | Search arXiv with optional category and date filters |
| `download_paper` | Fetch and store a paper by arXiv ID |
| `list_papers` | List stored papers with experiment counts |
| `annotate_paper` | Append a timestamped annotation |

### Experiments
| Tool | Description |
|---|---|
| `checkout` | Start an experiment. Scaffolds all doc templates. |
| `checkin` | Complete an experiment. Refuses if docs are unfilled. |
| `get_experiment` | Full detail including all doc files |
| `list_experiments` | List experiments for a paper with confidence scores |
| `browse_stacks` | All currently checked-out experiments (what's in progress) |
| `browse_shelf` | Browse completed experiments by concept |

### Synthesis
| Tool | Description |
|---|---|
| `create_synthesis` | New experiment derived from any mix of experiments/papers |
| `checkin_synthesis` | Complete a synthesis with same doc requirements |
| `list_syntheses` | List synthesis experiments |

### Ideas
| Tool | Description |
|---|---|
| `record_idea` | Add to the backlog with inspiration pointers |
| `list_ideas` | Browse by status (unresearched / in_progress / absorbed) |
| `promote_idea` | Link an idea to the experiment it became |

### Sessions
| Tool | Description |
|---|---|
| `open_session` | Start a session with a goal and agent ID |
| `close_session` | Close with status + mandatory postmortem |
| `list_sessions` | Browse sessions, filter by status |

### Reviews
| Tool | Description |
|---|---|
| `submit_review` | Methodology, reproduction, or synthesis review |
| `get_review_summary` | Aggregated confidence + verdict breakdown |
| `update_reviewer_accuracy` | Update reviewer track record after reproduction resolves a dispute |
| `find_contested` | Experiments with conflicting reviews |
| `list_unreviewed` | Completed experiments needing review (librarian use) |

### Discovery (librarian agent)
| Tool | Description |
|---|---|
| `suggest_synthesis` | Find synthesis candidates from seed experiments |
| `find_contradictions` | Same concepts, opposite outcomes — prime synthesis targets |
| `find_derailments` | Pattern-match failures by type |
| `find_underexplored` | Papers with few experiments |
| `browse_lineage` | Full ancestor + descendant tree for any node |

### Graph
| Tool | Description |
|---|---|
| `get_graph` | Full graph as nodes + edges for agent reasoning |
| `export_graph` | Self-contained interactive HTML visualization |

## The librarian agent pattern

Most agents come in with a goal: implement this paper, test this idea, compare these approaches. They check out experiments, do the work, check in, and leave.

The librarian is different. It roams:

```
1. list_ideas(status="unresearched")
2. find_contradictions()
3. find_underexplored()
4. suggest_synthesis(seed_ids=[...], strategy="open")
5. find_contested()
6. list_unreviewed()
```

Its job is cross-pollination — finding the connections between what's already been done and surfacing the next most interesting experiments. No specific outcome goal. Just look at what's there and ask what's missing.

## Confidence scoring

Reviews are evidence, not gates. A single flawed review doesn't block a good experiment.

Each reviewer has an accuracy score (default 0.7) that's updated via `update_reviewer_accuracy` as reproduction experiments resolve disputes. Confidence = weighted average of verdict scores × reviewer accuracy scores.

| Verdict | Score |
|---|---|
| sound | 1.0 |
| inconclusive | 0.6 |
| overclaiming | 0.4 |
| flawed | 0.2 |

Unreviewed experiments start at confidence 1.0 — benefit of the doubt.

## Inspired by

The gap in [Karpathy's auto-research](https://github.com/KarpathyLab/auto-research) and similar agentic research loops: agents that trick themselves with no audit trail, no hypothesis discipline, and no way to learn from past failures across sessions.