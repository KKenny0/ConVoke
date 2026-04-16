import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from convoke.models import AgentConfig, ConVokeConfig

_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

DEFAULT_CONFIG_NAME = "convoke.yaml"
DEFAULT_WATCH_PATH = ".agents/contracts/"


def load_config(
    cwd: Path | None = None,
    config_path: Path | None = None,
) -> ConVokeConfig:
    """Load and validate convoke.yaml.

    Args:
        cwd: Project root directory. Defaults to Path.cwd().
        config_path: Explicit config file path. Defaults to {cwd}/.agents/convoke.yaml.
    """
    cwd = cwd or Path.cwd()
    config_path = config_path or cwd / ".agents" / DEFAULT_CONFIG_NAME

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Validate agent names
    for name in raw.get("agents", {}):
        if not _AGENT_NAME_RE.match(name):
            raise ValidationError.from_exception_data(
                title="AgentConfig",
                line_errors=[
                    {
                        "type": "value_error",
                        "loc": ("agents", name),
                        "input": name,
                        "msg": f"Agent name '{name}' must match [a-zA-Z0-9_-]+ (no dots allowed)",
                        "ctx": {"error": f"Agent name '{name}' must match [a-zA-Z0-9_-]+ (no dots allowed)"},
                    }
                ],
            )

    # Build agents dict
    agents: dict[str, AgentConfig] = {}
    for name, agent_raw in raw.get("agents", {}).items():
        agents[name] = AgentConfig(
            name=name,
            cli_command=agent_raw["cli_command"],
            args=agent_raw.get("args", []),
            prompt_template=agent_raw.get(
                "prompt_template",
                "You have a new contract from {from_agent}. Use conpact_check to see details.",
            ),
        )

    watch_path_raw = raw.get("watch_path", DEFAULT_WATCH_PATH)
    watch_path = Path(watch_path_raw)
    if not watch_path.is_absolute():
        watch_path = cwd / watch_path
    watch_path = watch_path.resolve()

    return ConVokeConfig(
        agents=agents,
        watch_path=watch_path,
        log_level=raw.get("log_level", "INFO"),
    )
