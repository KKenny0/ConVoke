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

## CLI Commands

| Command | Description |
|---------|-------------|
| `convoke` | Show status summary with ASCII art banner |
| `convoke init` | Interactive setup for `.agents/convoke.yaml` |
| `convoke start` | Start daemon in foreground |
| `convoke start -d` | Start as background daemon |
| `convoke stop` | Stop the daemon |
| `convoke status` | Show daemon status, agent availability, recent notifications |
| `convoke test --agent <name>` | Send a test notification |
| `convoke log [-n 20]` | View notification log |

## Tech Stack

- Python 3.11+
- [watchdog](https://python-watchdog.readthedocs.io/) — Filesystem event monitoring
- [Pydantic](https://docs.pydantic.dev/) — Data models and validation
- [Typer](https://typer.tiangolo.com/) — CLI framework
- [PyYAML](https://pyyaml.readthedocs.io/) — Config parsing
- [pyfiglet](https://pypi.org/project/pyfiglet/) — ASCII art banner

## Project Structure

```
convoke/
├── pyproject.toml
├── src/convoke/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point + commands
│   ├── daemon.py           # Main daemon orchestration
│   ├── watcher.py          # File system watcher + debounce
│   ├── router.py           # State transition → notification routing
│   ├── notifier.py         # CLI subprocess invocation
│   ├── config.py           # Config loading and validation
│   ├── models.py           # Pydantic data models
│   └── logging.py          # Logging setup
├── tests/                  # 56 tests
├── docs/                  # Design spec and implementation plan
└── PROJECT.md             # Project brief
```

## Related

- [ConPact](https://github.com/KKenny0/ConPact) — Multi-Agent Contract Protocol

## License

MIT
