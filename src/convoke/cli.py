import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pyfiglet
import typer
import yaml

from convoke.config import load_config
from convoke.daemon import ConVokeDaemon
from convoke.logging import setup_logging

app = typer.Typer(no_args_is_help=False)

DEFAULT_PROMPT = "You have a new contract from {from_agent}. Use conpact_check to see details."

BANNER = pyfiglet.figlet_format("CONVOKE", font="slant")
TAGLINE = "Contract + Invoke — The notification layer for agents"


def _print_banner():
    typer.echo(BANNER)
    typer.echo(f"  {TAGLINE}")
    typer.echo()


def _agents_dir() -> Path:
    return Path.cwd() / ".agents"


def _pid_file() -> Path:
    return _agents_dir() / ".convoke.pid"


def _log_file() -> Path:
    return _agents_dir() / "convoke.log"


def _find_config() -> Path:
    return _agents_dir() / "convoke.yaml"


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """ConVoke — Notification bridge for multi-agent collaboration."""
    if ctx.invoked_subcommand is None:
        _print_banner()

        pid = _read_pid()
        config_path = _find_config()

        project = Path.cwd().name
        typer.echo(f"  Project: {project}")

        if config_path.exists():
            try:
                config = load_config(cwd=Path.cwd())
                agents = ", ".join(config.agents.keys())
                typer.echo(f"  Agents:  {agents}")
            except Exception:
                typer.echo("  Agents:  (config error)")
        else:
            typer.echo("  Agents:  (no config)")

        if pid and _is_process_running(pid):
            typer.echo(f"  Status:  ● Running (PID {pid})")
        else:
            typer.echo("  Status:  ○ Not running")

        typer.echo()
        typer.echo("  Usage:")
        typer.echo("    convoke start [-d]   Start watching")
        typer.echo("    convoke stop         Stop daemon")
        typer.echo("    convoke status       Show status")
        typer.echo("    convoke init         Setup config")
        typer.echo("    convoke test <agent> Send test notification")
        typer.echo("    convoke log [-n 20]  View notification log")


@app.command()
def init():
    """Interactively generate .agents/convoke.yaml."""
    config_path = _find_config()

    if config_path.exists():
        overwrite = typer.confirm(f"Config already exists at {config_path}. Overwrite?")
        if not overwrite:
            typer.echo("Aborted.")
            raise typer.Exit()

    agents_dir = _agents_dir()
    agents_dir.mkdir(parents=True, exist_ok=True)

    typer.echo("  ConVoke Setup")
    typer.echo("  " + "─" * 37)
    typer.echo()

    names_str = typer.prompt("Which agents to configure? (comma-separated)")
    names = [n.strip() for n in names_str.split(",") if n.strip()]

    agents: dict[str, dict] = {}
    for name in names:
        typer.echo()
        cli_cmd = typer.prompt(f"CLI command for {name}", default=name)
        args_str = typer.prompt(f"Arguments for {name}", default="")
        args = [a.strip() for a in args_str.split() if a.strip()]
        prompt = typer.prompt(f"Prompt template for {name}", default=DEFAULT_PROMPT)
        agents[name] = {
            "cli_command": cli_cmd,
            "args": args,
            "prompt_template": prompt,
        }

    config_path.write_text(yaml.dump({"agents": agents}, default_flow_style=False))
    typer.echo()
    typer.echo(f"  ✓ Config written to {config_path}")
    typer.echo("  Run 'convoke start' to begin watching.")


@app.command()
def start(
    detach: bool = typer.Option(False, "-d", help="Run as background daemon"),
    foreground_worker: bool = typer.Option(False, "--foreground-worker", hidden=True),
):
    """Start the ConVoke daemon."""
    config_path = _find_config()
    if not config_path.exists():
        typer.echo(f"✗ Config not found: {config_path}")
        typer.echo("  Run 'convoke init' to create one.")
        raise typer.Exit(1)

    if not foreground_worker:
        pid = _read_pid()
        if pid and _is_process_running(pid):
            typer.echo(f"✗ Daemon already running (PID {pid})")
            raise typer.Exit(1)

    if detach:
        _start_background()
    else:
        _start_foreground()


def _start_background():
    """Start daemon as a background process."""
    _agents_dir().mkdir(parents=True, exist_ok=True)
    log_file = _log_file()

    if sys.platform == "win32":
        log_handle = open(log_file, "a")
        subprocess.Popen(
            [sys.executable, "-m", "convoke.cli", "start", "--foreground-worker"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=log_handle,
            stderr=log_handle,
        )
        typer.echo("● Daemon started in background")
        return

    # Unix: double-fork
    pid = os.fork()
    if pid > 0:
        import time
        time.sleep(0.5)
        return

    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    sys.stdin.close()
    sys.stdout.close()
    sys.stderr.close()
    sys.stdout = open(log_file, "a")
    sys.stderr = open(log_file, "a")

    _write_pid(os.getpid())

    try:
        config = load_config(cwd=Path.cwd())
        setup_logging(log_file=log_file, level=config.log_level)
        daemon = ConVokeDaemon(config)
        daemon.run(foreground=True)
    except Exception as e:
        with open(log_file, "a") as f:
            f.write(f"[{datetime.now()}] ERROR: {e}\n")
    finally:
        _remove_pid()


def _start_foreground():
    """Start daemon in foreground."""
    _print_banner()

    config = load_config(cwd=Path.cwd())
    log_file = _log_file()
    setup_logging(log_file=log_file, level=config.log_level)

    _agents_dir().mkdir(parents=True, exist_ok=True)
    _write_pid(os.getpid())

    agents = ", ".join(f"{a} ({c.cli_command})" for a, c in config.agents.items())
    typer.echo(f"  Watching: {config.watch_path}")
    typer.echo(f"  Agents:   {agents}")
    typer.echo()
    typer.echo(f"  ● Daemon started (PID {os.getpid()})")
    typer.echo("  Waiting for contract events...")
    typer.echo()

    try:
        daemon = ConVokeDaemon(config)
        daemon.run(foreground=True)
    finally:
        _remove_pid()


@app.command()
def stop():
    """Stop the ConVoke daemon."""
    pid = _read_pid()
    if not pid:
        typer.echo("○ No daemon running")
        return

    if not _is_process_running(pid):
        typer.echo(f"○ Stale PID file (PID {pid} not running). Cleaning up.")
        _remove_pid()
        return

    typer.echo(f"● Stopping daemon (PID {pid})...")

    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    _remove_pid()
    typer.echo("✓ Daemon stopped")


@app.command()
def status():
    """Show daemon status and recent notifications."""
    config_path = _find_config()
    pid = _read_pid()

    typer.echo("  ConVoke Status")
    typer.echo("  " + "─" * 37)

    if pid and _is_process_running(pid):
        typer.echo(f"  ● Running  PID: {pid}")
    else:
        typer.echo("  ○ Not running")

    if config_path.exists():
        typer.echo(f"\n  Config:   {config_path}")
        try:
            config = load_config(cwd=Path.cwd())
            typer.echo(f"  Watching: {config.watch_path}")
            typer.echo("\n  Agents:")
            for name, agent in config.agents.items():
                cli_found = _cli_available(agent.cli_command)
                status_icon = "✓" if cli_found else "✗"
                status_txt = "CLI found" if cli_found else "CLI not found"
                args_str = f" {' '.join(agent.args)}" if agent.args else ""
                typer.echo(f"    {name:<15} {agent.cli_command}{args_str}  {status_icon} {status_txt}")
        except Exception as e:
            typer.echo(f"  Config error: {e}")
    else:
        typer.echo("\n  No config found. Run 'convoke init'.")

    log_file = _log_file()
    if log_file.exists():
        typer.echo("\n  Recent notifications:")
        lines = log_file.read_text().strip().split("\n")
        for line in lines[-5:]:
            typer.echo(f"    {line}")


@app.command()
def test(agent: str = typer.Option(..., "--agent", "-a", help="Agent name to test")):
    """Send a test notification to an agent."""
    config_path = _find_config()
    if not config_path.exists():
        typer.echo(f"✗ Config not found: {config_path}")
        raise typer.Exit(1)

    config = load_config(cwd=Path.cwd())
    agent_config = config.agents.get(agent)
    if not agent_config:
        typer.echo(f"✗ Unknown agent: {agent}")
        typer.echo(f"  Available: {', '.join(config.agents.keys())}")
        raise typer.Exit(1)

    test_prompt = f"ConVoke test notification to {agent}. If you see this, ConVoke is working!"
    cmd = [agent_config.cli_command, *agent_config.args, test_prompt]
    typer.echo(f"  Sending test notification to {agent}...")
    typer.echo(f"  Command: {' '.join(cmd[:3])}...")

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        typer.echo("  ✓ Agent process launched successfully")
    except FileNotFoundError:
        typer.echo(f"  ✗ CLI not found: {agent_config.cli_command}")
    except OSError as e:
        typer.echo(f"  ✗ Failed to launch: {e}")


@app.command()
def log(n: int = typer.Option(20, "-n", help="Number of lines to show")):
    """View notification log."""
    log_file = _log_file()
    if not log_file.exists():
        typer.echo("  No log file found. Start the daemon first.")
        return

    lines = log_file.read_text().strip().split("\n")
    typer.echo(f"  ConVoke Log (last {min(n, len(lines))} entries)")
    typer.echo("  " + "─" * 45)
    for line in lines[-n:]:
        typer.echo(f"  {line}")


# --- PID helpers ---

def _read_pid() -> int | None:
    pid_file = _pid_file()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int):
    _agents_dir().mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(pid))


def _remove_pid():
    pid_file = _pid_file()
    if pid_file.exists():
        pid_file.unlink()


def _is_process_running(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _cli_available(command: str) -> bool:
    try:
        subprocess.run(
            [command, "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


if __name__ == "__main__":
    app()
