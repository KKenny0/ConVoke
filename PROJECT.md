# ConVoke — Project Brief

**Contract + Invoke** — The notification layer that wakes agents when they have work.

## Context

ConPact (https://github.com/KKenny0/ConPact) is a Multi-Agent Contract Protocol implemented as an MCP server. It provides 12 tools for creating, claiming, updating, and reviewing contracts between coding agents (Claude Code, Codex, OpenClaw). All state lives on the shared filesystem as JSON files.

**ConPact solved "how to collaborate" but not "how to trigger."**

### The Trigger Gap

Current ConPact v1 workflow:

```
Agent A creates contract → [HUMAN manually starts Agent B] → Agent B claims & works → [HUMAN tells Agent A] → Agent A reviews
```

The problem: Agent B only discovers new work when a human starts its session and tells it to check. There's no mechanism for agents to notify each other.

Target workflow with ConVoke:

```
Agent A creates contract → ConVoke notifies Agent B → Agent B wakes & claims → Agent B submits → ConVoke notifies Agent A → Agent A reviews
```

## What ConVoke Does

ConVoke is a **notification bridge** between agents. It watches for contract state changes in a ConPact-enabled project and delivers notifications to the relevant agent's runtime.

Core responsibilities:

1. **Watch** — detect contract state changes (new contract created, submitted, revision_needed)
2. **Route** — determine which agent should be notified based on contract state
3. **Deliver** — send the notification through the agent's available channel
4. **Track** — record notification delivery status to avoid duplicates

## Key Design Constraints

These decisions were made during ConPact design discussions:

### 1. Separate Project, Not a ConPact Module

ConVoke is an independent project. Rationale:
- ConPact stays focused on contract CRUD + state machine
- Notification delivery mechanisms vary wildly per agent/runtime (CLI hooks, webhooks, file watchers, IPC)
- Different users may want different notification backends
- Keeps ConPact install footprint minimal

### 2. ConPact Has No Notification Hooks

ConPact's MCP server does NOT emit events. ConVoke must detect changes by **observing the filesystem** — watching `.agents/contracts/` for file creates, modifications, and moves.

This is intentional: ConPact remains a passive filesystem protocol. ConVoke adds the active layer on top.

### 3. Agent Identity and Channels

Each agent runtime has different notification capabilities:

| Agent | Possible Channels |
|-------|------------------|
| Claude Code | CLI hooks (`settings.json` hooks), cron/scheduled tasks, file watchers |
| Codex | Config-based hooks, file watchers |
| OpenClaw | File watchers, process signals |

ConVoke should NOT assume a specific channel. It should provide a **pluggable notification backend** system.

### 4. Project-Scoped

Like ConPact, ConVoke operates per-project. A ConVoke instance watches one `.agents/` directory.

### 5. Advisory, Not Mandatory

Notifications are best-effort. If ConVoke is not running, agents can still poll via `conpact_check`. ConVoke is an optimization, not a requirement.

## Notification Events

Based on ConPact's state machine, the events that warrant notification:

| Event | Trigger | Notify Who |
|-------|---------|------------|
| `contract_created` | New file in `contracts/` with status `assigned` | The `assignee` |
| `contract_submitted` | File updated, status → `submitted` | The `from` (delegator) |
| `revision_needed` | File updated, status → `revision_needed` | The `assignee` |
| `contract_closed` | File moved to `_archive/` | Both parties (optional) |

## Architecture Direction (To Be Designed)

These are open questions for the implementation phase:

- **Language**: Python (consistent with ConPact) or something else?
- **File watching**: `watchdog` library? OS-native `inotify`/`ReadDirectoryChangesW`? Polling?
- **Delivery backends**: File-based signals? Webhooks? Named pipes? CLI invocation?
- **Process model**: Long-running daemon? One-shot triggered by file events? CLI tool invoked by cron?
- **Config**: Per-project `.agents/convoke.json`? Global config?

## Relationship to ConPact

```
┌─────────────────┐         ┌─────────────────┐
│    ConPact       │         │    ConVoke       │
│  MCP Server      │         │  Notification    │
│                  │         │  Bridge          │
│  • 12 tools      │         │                  │
│  • State machine │◄────────│  • File watcher  │
│  • Atomic writes │ watches │  • Event router  │
│  • CRUD          │ .agents/│  • Delivery      │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         │  .agents/contracts/        │  notification channels
         │  shared filesystem         │  (hooks, webhooks, etc.)
         │                            │
    ┌────▼────┐              ┌────────▼────────┐
    │ Agent A  │              │    Agent B       │
    └─────────┘              └─────────────────┘
```

ConVoke reads ConPact contract files but never writes to them. It's a read-only observer of ConPact state.

## Reference

- ConPact repo: https://github.com/KKenny0/ConPact
- ConPact state machine: `assigned → in_progress → submitted → closed` (with `revision_needed` loop)
- ConPact contract files: `@<assignee>.<id>.json` in `.agents/contracts/`
- ConPact archive: closed contracts moved to `.agents/contracts/_archive/`
