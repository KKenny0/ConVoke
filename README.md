```
   __________  _   ___    ______  __ __ ______
  / ____/ __ \/ | / / |  / / __ \/ //_// ____/
 / /   / / / /  |/ /| | / / / / / ,<  / __/
/ /___/ /_/ / /|  / | |/ / /_/ / /| |/ /___
\____/\____/_/ |_/  |___/\____/_/ |_/_____/
```

**Contract + Invoke** — The notification layer that wakes agents when they have work.

## What is ConVoke?

ConVoke is a notification bridge for [ConPact](https://github.com/KKenny0/ConPact) (Multi-Agent Contract Protocol). It fills the **trigger gap** — when Agent A creates a contract for Agent B, Agent B has no way to know about it until a human tells it. ConVoke solves this by watching for contract state changes and actively waking the relevant agent.

```
Before ConVoke:
  Agent A creates contract → [HUMAN starts Agent B] → Agent B works

With ConVoke:
  Agent A creates contract → ConVoke notifies Agent B → Agent B wakes & claims
```

## How It Works

ConVoke is a long-running daemon that watches `.agents/contracts/` for file events and routes notifications to the right agent via CLI invocation.

```
┌─────────────────┐         ┌─────────────────┐
│    ConPact       │         │    ConVoke       │
│  MCP Server      │         │  Notification    │
│                  │         │  Bridge          │
│  • 12 tools      │         │                  │
│  • State machine │◄────────│  • File watcher  │
│  • Atomic writes │ watches │  • Event router  │
│  • CRUD          │ .agents/│  • CLI notifier  │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
    ┌────▼────┐              ┌────────▼────────┐
    │ Agent A  │              │    Agent B       │
    └─────────┘              └─────────────────┘
```

### Notification Events

| Event | Trigger | Notifies |
|-------|---------|----------|
| `contract_created` | New file with status `assigned` | The assignee |
| `contract_submitted` | Status → `submitted` | The delegator |
| `revision_needed` | Status → `revision_needed` | The assignee |
| `contract_closed` | File moved to `_archive/` | Both parties |

## Quick Start

```bash
# Install
pip install convoke

# Initialize configuration
convoke init

# Start watching (foreground)
convoke start

# Start as background daemon
convoke start -d

# Check status
convoke status

# Stop daemon
convoke stop
```

## Configuration

ConVoke reads its config from `.agents/convoke.yaml` (project-scoped, co-located with ConPact):

```yaml
agents:
  claude-code:
    cli_command: claude
    args: ["-p"]
    prompt_template: "You have a new contract from {from_agent}. Check it with conpact_check and claim it."
  codex:
    cli_command: codex
    args: []
    prompt_template: "New task from {from_agent}: {objective}. Use conpact_check to see details."
```

## Key Design Principles

- **Read-only observer** — ConVoke never writes to ConPact contract files
- **Advisory** — If ConVoke is not running, agents can still poll via `conpact_check`
- **Pluggable** — CLI invocation as the default backend, extensible for future channels
- **Cross-platform** — Supports both Unix and Windows daemon management

## Status

ConVoke is currently in the design phase. See the [ConPact](https://github.com/KKenny0/ConPact) repository for the contract protocol it builds upon.

## License

MIT
