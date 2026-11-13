# Architecture Design Document: Interactive Roadmap Lifecycle, Slash-Command Bot & Milestone Automation Engine

* **Target Milestone:** `v0.1.0` (Community Infrastructure & Governance Ergonomics)
* **Status:** Superseded by Native Community Voting (Zero GitHub Actions)
* **Authors:** Sukumar Rastogi (`sukumar1210`)
* **Date:** 2026-11-13
* **Component Tags:** `discussions`, `roadmap`, `bot`, `github-actions`, `community-governance`, `milestones`, `rbac`

> ⚠️ **Architecture Update (2026-11-13)**: *This bot-driven engine design has been superseded by **100% Native Community Voting**. All voting, real-time counting, and ranking are delegated natively to GitHub Discussions ([Live Ideas Leaderboard](https://github.com/sukumar1210/harness-bridge/discussions/categories/ideas?discussions_q=is:open+category:Ideas+%22[Idea]%22+sort:top)), eliminating all custom bot code, runner consumption, and GitHub Actions workflows.*

---

## 1. Context & Motivation

Harness Bridge connects independent AI coding agents (such as Claude Code and Antigravity) into a unified multi-agent collaborative system. As an open-source framework, community input directly guides feature prioritization across driver adapters, session management, and CLI capabilities.

Historically, feature ideation suffered from three core operational friction points:
1. **Disconnected Ideation vs. Roadmap Prioritization**: Community members posted RFC ideas in standalone discussion threads, but there was no standardized bridge connecting an informal discussion post to the official roadmap.
2. **Resource-Wasteful Polling Workflows**: Background GitHub Actions cron jobs running every 30 minutes consumed runner allowances unnecessarily, generated repetitive workflow runs, and added polling lag to vote tallies.
3. **Manual Milestone Synthesis**: Once community voting concluded, maintainers were forced to manually tally votes, create GitHub Milestones, copy-paste tracking issues, and write release announcements across disparate discussion threads.

This document establishes the architecture for an **event-driven, role-gated roadmap lifecycle engine** (`scripts/roadmap_bot.py` and `.github/workflows/roadmap_bot.yml`). It enables contributors to request roadmap consideration with a single comment command (`/request-nomination`), equips maintainers with a GitHub Project triage queue and command-based authorization (`/approve-candidate`, `/open-poll`, `/close-poll`), and automates the entire lifecycle through to GitHub Milestone provisioning and tracking issue creation—all with zero recurring cron jobs.

---

## 2. User Stories & Concrete CUJs

### CUJ 1: Contributor Proposes Feature and Requests Nomination
* **Given**: A community developer drafts a proposal for a new driver adapter in GitHub Discussions under the `Ideas` category.
* **When**: The contributor comments `/request-nomination` on their proposal.
* **Then**:
  1. GitHub Actions detects the slash-command in ~3 seconds.
  2. The bot adds the `nomination-requested` label and places the discussion into the maintainer review queue on GitHub Projects.
  3. The bot reacts `👀` to the comment and confirms receipt with an encouraging public note.

### CUJ 2: Maintainer Reviews, Authorizes, and Queues Candidate
* **Given**: A maintainer triaging incoming community ideas.
* **When**: The maintainer reviews the proposal and comments `/approve-candidate`.
* **Then**:
  1. The bot verifies that the actor has maintainer privileges (`OWNER`, `COLLABORATOR`, `MEMBER`).
  2. The bot swaps the `nomination-requested` label for `roadmap-candidate` and moves the Project card to `Approved for Next Poll`.
  3. The proposal is batched for the upcoming release poll round.

### CUJ 3: Fast-Track Candidate Promotion (`--immediate`)
* **Given**: A high-impact security or core feature proposal requiring immediate community feedback.
* **When**: A maintainer comments `/approve-candidate --immediate` (or `/approve-immediate`).
* **Then**:
  1. The proposal is labeled `roadmap-candidate`.
  2. The bot automatically creates a dedicated `[IDEA-POLL]` ballot comment in central [Discussion #16](https://github.com/sukumar1210/harness-bridge/discussions/16).
  3. The bot appends the feature candidate row directly into the active ballot table inside Discussion #16 (`<!-- ROADMAP:BALLOT:START -->`).
  4. The candidate discussion receives a confirmation link directing voters to the live ballot.

### CUJ 4: Community Voting Cycle & Milestone Finalization
* **Given**: An active voting cycle in Discussion #16 with community members voting via comment upvotes (`▲ Upvote`).
* **When**: The maintainer closes the voting round by commenting `/close-poll milestone=v0.2.0 winners=#17,#19`.
* **Then**:
  1. The bot tallies the final upvote counts from top-level comments (excluding threaded replies).
  2. The bot writes a locked archival summary comment in Discussion #16 and records it in the archive index (`<!-- ROADMAP:ARCHIVE:START -->`).
  3. The bot moves winners (#17, #19) into the "Planned Roadmap: Finalized Features & Target Milestones" table under `v0.2.0` (`<!-- ROADMAP:PLANNED:START -->`).
  4. The bot idempotently creates GitHub Milestone `v0.2.0`.
  5. The bot creates tracking GitHub Issues for each winning feature, assigns them to Milestone `v0.2.0`, and cross-posts announcement links on the original idea discussions.
  6. Non-winning proposals roll over into the backlog for future voting rounds.

---

## 3. High-Level Architecture & Lifecycle State Machine

```
  ┌─────────────────────────────────────────────────────────────────┐
  │ 1. Contributor Posts Idea in 'Ideas' Category (RFC #XX)         │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ 2. Contributor comments: '/request-nomination'                  │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼ [Event: discussion_comment: created]
  ┌─────────────────────────────────────────────────────────────────┐
  │ • Applies 'nomination-requested' label                          │
  │ • Reacts '👀' and confirms review request                       │
  │ • Queues in GitHub Project Triage Board                         │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ 3. Maintainer Triage & Formal Authorization                     │
  │    (Strict role check: OWNER / COLLABORATOR / MEMBER)           │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
       [/approve-candidate]            [/approve-candidate --immediate]
     (Queued for Next Cycle)              (Injected Live into Ballot)
                 │                                 │
                 │                                 ▼
                 │                    Discussion #16 Updated
                 │                    • Ballot comment created
                 │                    • Central table updated
                 ▼                                 │
  ┌─────────────────────────────┐                  │
  │ Maintainer triggers:        │                  │
  │ '/open-poll [milestone]'    │                  │
  └──────────────┬──────────────┘                  │
                 │                                 │
                 ▼                                 │
  ┌────────────────────────────────────────────────┴────────────────┐
  │ 4. Active Community Voting Phase                                │
  │ Community casts '▲ Upvote' on [IDEA-POLL] comments              │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ 5. Maintainer Closes Poll:                                      │
  │ '/close-poll milestone=vX.Y.Z winners=#X,#Y'                    │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼ [Idempotent Automated Execution]
  ┌─────────────────────────────────────────────────────────────────┐
  │ • Verify Maintainer Authorization                               │
  │ • Tally & freeze final votes (filtering comment replies)        │
  │ • Post locked archival summary comment in Discussion 16         │
  │ • Update Discussion 16 Planned Roadmap & Archive Index          │
  │ • Idempotently create GitHub Milestone 'vX.Y.Z'                 │
  │ • Create tracking GitHub Issues linked to milestone             │
  │ • Post celebration notice on winning RFC discussions            │
  │ • Roll over non-winning candidates to ideas backlog             │
  └─────────────────────────────────────────────────────────────────┘
```

---

## 4. Subsystem Design & Technical Specifications

### 4.1 Event-Driven GitHub Actions Workflow (`.github/workflows/roadmap_bot.yml`)
The workflow eliminates recurring cron runs by triggering exclusively on discussion comment creations that begin with a slash:

```yaml
name: Roadmap Lifecycle Bot

on:
  discussion_comment:
    types: [created]
  workflow_dispatch:
    inputs:
      action:
        description: 'Roadmap action to run'
        required: true
        default: 'sync'
        type: choice
        options:
          - sync
          - open-poll

permissions:
  contents: write
  discussions: write
  issues: write

concurrency:
  group: roadmap-discussion-sync
  cancel-in-progress: false
```

#### Invariant: Race Condition Prevention
* Setting `cancel-in-progress: false` within concurrency group `roadmap-discussion-sync` guarantees that concurrent or sequential slash-commands queue up deterministically rather than canceling in-flight mutations, preventing corrupted table overwrites.

### 4.2 Machine-Readable HTML Document Fencing
To guarantee that programmatically updated tables never corrupt surrounding markdown, [Discussion #16](https://github.com/sukumar1210/harness-bridge/discussions/16) is partitioned into machine-readable comment fences:

* `<!-- ROADMAP:BALLOT:START -->` ... `<!-- ROADMAP:BALLOT:END -->`: Encloses the active feature candidates table.
* `<!-- ROADMAP:PLANNED:START -->` ... `<!-- ROADMAP:PLANNED:END -->`: Encloses the finalized roadmap milestone table.
* `<!-- ROADMAP:ARCHIVE:START -->` ... `<!-- ROADMAP:ARCHIVE:END -->`: Encloses the index of concluded voting cycles.

### 4.3 Discussion Body 65KB Limit Guard
GitHub Discussions enforces a strict 65,536-character maximum body payload limit. Appending full voting tables and voter breakdowns for every historical milestone would eventually truncate the post.

**Architectural Solution**:
- Detailed historical breakdowns are posted as **locked archival comments** within Discussion #16.
- The top-level discussion body retains only a compact hyperlink index (`- [Milestone v0.2.0 Voting Results (2 Selected) →](...)`), ensuring infinite scalability across dozens of release cycles.

### 4.4 Two-Tier RBAC & Command Taxonomy

| Command | Allowed Roles | Target Scope | Action Taken |
| :--- | :--- | :--- | :--- |
| `/request-nomination` | Anyone (Contributor / Author) | Any `[Idea]` discussion | Tags `nomination-requested`, reacts `👀`, posts confirmation comment. |
| `/approve-candidate` | Maintainers (`OWNER`, `COLLABORATOR`, `MEMBER`) | Any nominated discussion | Tags `roadmap-candidate`, queues in Project board for next poll round. |
| `/approve-candidate --immediate` | Maintainers | Any nominated discussion | Labels candidate, creates `[IDEA-POLL]` ballot comment in #16, injects live row into active ballot. |
| `/defer-candidate [reason]` | Maintainers | Any nominated discussion | Tags `deferred`, posts feedback explaining reasons for deferral. |
| `/open-poll [milestone]` | Maintainers | Discussion #16 | Batches all queued `roadmap-candidate` discussions into the active ballot. |
| `/sync-votes` | Maintainers / Actions | Discussion #16 | Refreshes live upvote tallies in the active ballot table. |
| `/close-poll milestone=... winners=...` | Maintainers | Discussion #16 | Freezes votes, writes archival comment, updates planned roadmap, creates GitHub Milestone & tracking issues. |

---

## 5. Implementation Architecture (`scripts/roadmap_bot.py`)

The engine is authored as a single, self-contained Python 3.11+ script with **zero third-party dependencies**, utilizing standard library modules (`json`, `re`, `subprocess`, `argparse`, `sys`, `os`) alongside the pre-authenticated `gh` CLI.

### Key Implementation Modules:
1. **`run_graphql` & `run_rest`**: Abstracted HTTP/GraphQL execution wrappers with error parsing and token passing.
2. **`parse_command`**: Robust argument parser supporting named flags (`milestone=v0.2.0`, `winners=#17,#18`), boolean switches (`--immediate`), and positional fallbacks.
3. **`extract_fenced_section` & `replace_fenced_section`**: Regular-expression handlers guaranteeing atomic, idempotent section replacements.
4. **`sync_upvotes_in_body`**: Queries `upvoteCount` via GraphQL, strictly filtering out comment replies (`c.get("replyTo") is not None`), and matches rows by RFC discussion links and comment IDs.
5. **`handle_close_poll`**: Multi-phase transactional orchestrator:
   - Synchronizes final upvotes.
   - Generates and posts archival comment.
   - Appends winners to Planned Roadmap table.
   - Clears active ballot.
   - Creates GitHub Milestone.
   - Creates tracking issues with RFC back-links.
   - Cross-posts celebration notices on winning proposal discussions.

---

## 6. Verification & Test Matrix

The engine is validated by a dedicated test suite in `tests/test_roadmap_bot.py`:

| Test Case | Objective Verified | Status |
| :--- | :--- | :--- |
| `test_parse_command_basic` | Validates slash command name and flag extraction. | Passed |
| `test_parse_command_with_named_and_positional_args` | Verifies key-value (`milestone=v0.2.0`) and positional argument parsing. | Passed |
| `test_fenced_section_extraction_and_replacement` | Ensures atomic content replacement between HTML comment fences without modifying surrounding markdown. | Passed |
| `test_ballot_table_roundtrip` | Validates bidirectional parsing and markdown generation for ballot candidate rows. | Passed |
| `test_generate_ballot_empty` | Verifies graceful fallback message when zero candidates are active. | Passed |
| `test_handle_comment_event_non_slash_command` | Confirms normal discussion comments exit immediately with 0 runner overhead. | Passed |
| `test_handle_comment_unauthorized_maintainer_command` | Asserts unauthorized users attempting maintainer commands receive `CONFUSED` reactions and rejection warnings. | Passed |
| `test_handle_comment_request_nomination_allowed_for_anyone` | Verifies community contributors can successfully request roadmap nomination. | Passed |

---

## 7. Decommissioning of Legacy Assets

The following legacy scripts and workflows have been fully decommissioned from the codebase:

1. **`.github/workflows/sync_roadmap_votes.yml`**: Deleted (superseded by `.github/workflows/roadmap_bot.yml`).
2. **`scripts/sync_roadmap_votes.py`**: Deleted (superseded by `scripts/roadmap_bot.py`).
3. **`scripts/README.md`**: Cleaned of outdated `sync_roadmap_votes.py` documentation.
4. **`Discussion #16` Sync Notes**: Replaced with automated lifecycle instructions and machine-readable HTML fences.
