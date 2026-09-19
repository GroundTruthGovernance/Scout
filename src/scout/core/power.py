"""Post-batch power actions (sleep/shutdown), the concrete implementation
of "options to sleep or shutdown the pc after the batch."

`run_command` is injectable so this is unit-testable without actually
suspending or shutting down the machine running the tests — a very easy
way to make a test suite genuinely dangerous otherwise.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable

CommandRunner = Callable[[list[str]], object]


def _default_runner(command: list[str]) -> object:
    return subprocess.run(command, check=False)


def sleep_commands(system: str | None = None) -> list[str]:
    system = system or platform.system()
    if system == "Windows":
        # /h is hibernate; plain rundll32 SetSuspendState call is the
        # standard sleep trigger since Windows has no single builtin CLI
        # verb for "sleep" the way it does for shutdown.
        return ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
    if system == "Darwin":
        return ["pmset", "sleepnow"]
    return ["systemctl", "suspend"]


def shutdown_commands(system: str | None = None) -> list[str]:
    system = system or platform.system()
    if system == "Windows":
        return ["shutdown", "/s", "/t", "0"]
    if system == "Darwin":
        return ["osascript", "-e", 'tell app "System Events" to shut down']
    return ["systemctl", "poweroff"]


def perform_power_action(
    action: str, system: str | None = None, run_command: CommandRunner | None = None
) -> None:
    """action: 'None' | 'Sleep' | 'Shutdown' — matches
    BatchQueuePanel.POST_QUEUE_ACTIONS. 'None' is a deliberate no-op, not
    an error, so callers can pass the post-queue selection straight
    through without a branch."""
    if action == "None":
        return
    if action == "Sleep":
        commands = sleep_commands(system)
    elif action == "Shutdown":
        commands = shutdown_commands(system)
    else:
        raise ValueError(f"Unknown post-queue action: {action!r}")

    runner = run_command or _default_runner
    runner(commands)
