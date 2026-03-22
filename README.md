# Stacks

The memory and accountability layer for agentic research loops.

Most agent research tools — including auto-research loops — have no persistent audit trail. An agent explores a paper, runs some experiments, reaches a conclusion, and then that work is gone. The next agent starts from scratch, repeats the same mistakes, or worse: builds confidently on a broken implementation.

This is the missing piece.

## What it does

- **Paper store** — search arXiv, download papers locally as markdown
- **Project store** — paper-free experiment roots for work that isn't driven by a specific paper, or has drifted far enough from its origin that attribution would be misleading
- **Experiment tracking** — checkout/checkin with documentation enforcement. Hypothesis locked at checkout. Checkin refused if docs are incomplete.
- **Lineage graph** — every experiment knows what it was derived from. Generation depth computed automatically. Siblings, cross-paper synthesis, and mixed-generation combinations are all just different graph shapes.
- **Synthesis** — first-class experiment type derived from any combination of experiments, papers, or projects. This is where cross-pollination lives structurally.
- **Ideas backlog** — record future hypotheses with inspiration pointers for the librarian agent
- **Sessions** — wrap an agent run with a goal and mandatory postmortem. Derailed sessions are logged with explanation.
- **Reviews** — methodology, reproduction, and synthesis reviews. Confidence scores are evidence-weighted by reviewer track record, not binary blocks. A single bad review doesn't kill good work.
- **Version control** — git-backed store with auto-commit on checkin, branch-per-agent isolation, and per-experiment rollback.
- **Graph visualization** — interactive D3 force-directed graph exported as self-contained HTML. Opacity = confidence. White ring = surprising result.

## Setup

```bash
git clone https://github.com/yourname/stacks
cd stacks
uv sync
```

## MCP config (stdio — recommended for personal use)

Each agent session spawns its own process. Storage is shared via filesystem.

```json
{
  "mcpServers": {
    "stacks": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/stacks",
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
    "stacks": {
      "transport": "sse",
      "url": "http://localhost:8050/sse"
    }
  }
}
```

## Storage layout

```
~/research/
  .git/
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
  projects/
    {project_id}/
      manifest.json                   # seeded_from, concepts, description
      notes.md                        # running log
      experiments/
        {exp_id}/                     # identical layout to paper experiments
  synthesis/
    {synth_id}/                       # same layout as experiments
  ideas/
    {idea_id}.json
  sessions/
    {session_id}.json
```

## Version control

The store is a git repository. Every file is a plain text or JSON file, so diffs are meaningful and `git log` on an experiment directory is a real audit trail.

**Initial setup:**

```
init_repo(remote_url="https://github.com/you/research-data")
```

This writes a `.gitignore`, makes an initial commit, and pushes to the remote if provided. After this, checkin and checkin_synthesis call `snapshot()` automatically — every completed experiment is committed without any extra steps.

**Normal single-machine workflow:**

Most of the time you don't need to think about branches. Multiple terminals share the same filesystem, checkins auto-commit, and you push manually at the end of a session:

```
push()
```

**Branch-per-agent (multi-agent isolation):**

When running multiple agents that might be writing concurrently, each agent can work on its own branch:

```
# at session open
branch_session(session_id)

# ... agent does work, checkins auto-commit to this branch ...

# at session close
merge_session(session_id)
push()
```

Conflicts are rare because new experiments are new directories. The only shared mutable file is `index.json`, and agents write to different keys within it. `merge_session` does a `--no-ff` merge so the session work appears as a discrete unit in the log.

**Rollback:**

To discard uncommitted changes to a specific experiment without touching anything else:

```
rollback_experiment(experiment_id, paper_id="2301.07041")
```

This restores only that experiment directory to its last committed state. Everything else is untouched.

**Inspection:**

```
git_log(n=20)                                    # recent commits across the store
git_log(experiment_id=..., paper_id=...)         # commits scoped to one experiment
diff_experiment(experiment_id, paper_id=...)     # uncommitted changes in an experiment
```

**On a second machine:**

```bash
git clone https://github.com/you/research-data ~/research
# point MCP config at ~/research, that's it
```

## Tool reference

### Papers
| Tool | Description |
|---|---|
| `search_papers` | Search arXiv with optional category and date filters |
| `download_paper` | Fetch and store a paper by arXiv ID |
| `list_papers` | List stored papers with experiment counts |
| `annotate_paper` | Append a timestamped annotation |

### Projects
| Tool | Description |
|---|---|
| `create_project` | New paper-free experiment root |
| `list_projects` | List projects with experiment counts and seeded_from lineage |
| `annotate_project` | Append a timestamped note to a project's running log |
| `checkout_project_experiment` | Check out an experiment under a project |
| `checkin_project_experiment` | Check in with same doc requirements as paper experiments |
| `list_project_experiments` | List experiments under a project with confidence scores |

### Experiments
| Tool | Description |
|---|---|
| `checkout` | Start an experiment under a paper. Scaffolds all doc templates. |
| `checkin` | Complete an experiment. Refuses if docs are unfilled. Auto-commits. |
| `get_experiment` | Full detail including all doc files |
| `list_experiments` | List experiments for a paper with confidence scores |
| `browse_stacks` | All currently checked-out experiments across papers and projects |
| `browse_shelf` | Browse completed experiments by concept |

### Synthesis
| Tool | Description |
|---|---|
| `create_synthesis` | New experiment derived from any mix of experiments/papers/projects |
| `checkin_synthesis` | Complete a synthesis with same doc requirements. Auto-commits. |
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
| `find_underexplored` | Papers or projects with few experiments |
| `browse_lineage` | Full ancestor + descendant tree for any node |

### Graph
| Tool | Description |
|---|---|
| `get_graph` | Full graph as nodes + edges for agent reasoning |
| `export_graph` | Self-contained interactive HTML visualization |

### Git
| Tool | Description |
|---|---|
| `init_repo` | Initialize storage as a git repo, optional remote |
| `snapshot` | Commit all current changes (called automatically on checkin) |
| `push` | Push to remote |
| `branch_session` | Create and switch to a branch named after a session |
| `merge_session` | Merge a session branch back into main |
| `rollback_experiment` | Restore one experiment directory to last committed state |
| `diff_experiment` | Show uncommitted changes in an experiment |
| `git_log` | Recent commits, optionally scoped to one experiment |

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

## Backfilling existing work

If you have existing experiments or results you want to record after the fact, the checkout/checkin cycle still applies — the timestamps will reflect when you record them, not when the work was done. The `manifest.json` for each experiment has a `created_at` field you can set manually if accurate dating matters for your records.

For bulk backfill, the most practical approach is to write the files directly into the storage directory structure and then call `snapshot("backfill: ...")` once rather than going through the checkout/checkin flow for every entry.

## Inspired by

The gap in Karpathy's auto-research and similar agentic research loops: agents that trick themselves with no audit trail, no hypothesis discipline, and no way to learn from past failures across sessions.


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