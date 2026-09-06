from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Union


class ProcessRunner:
    """Low-level process execution wrapper with color-coded diagnostics."""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"

    @classmethod
    def log_step(cls, phase: str, project: str = "") -> None:
        """Logs a major phase header."""
        project_str = f" | PROJECT: {project}" if project else ""
        print(f"\n{cls.MAGENTA}{cls.BOLD}▶ PHASE: {phase}{project_str}{cls.NC}")
        print(f"{cls.MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{cls.NC}\n", flush=True)

    @classmethod
    def log_info(cls, message: str) -> None:
        """Logs an informational message."""
        print(f"{cls.BLUE}[INFO]{cls.NC} {message}", flush=True)

    @classmethod
    def log_success(cls, message: str) -> None:
        """Logs a success message."""
        print(f"{cls.GREEN}{cls.BOLD}[SUCCESS]{cls.NC} {message}", flush=True)

    @classmethod
    def log_warn(cls, message: str) -> None:
        """Logs a warning message."""
        print(f"{cls.YELLOW}{cls.BOLD}[WARN]{cls.NC} {message}", flush=True)

    @classmethod
    def log_error(cls, message: str) -> None:
        """Logs an error message."""
        print(f"{cls.RED}{cls.BOLD}[ERROR]{cls.NC} {message}", file=sys.stderr, flush=True)

    def run(
        self,
        command: Union[List[str], str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        shell: bool = False,
    ) -> subprocess.CompletedProcess:
        """Executes a command using subprocess.run with error checking and color logging."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        cwd_str = f" in {cwd}" if cwd else ""
        print(f"{self.CYAN}➔ [EXEC]{self.NC} {cmd_str}{cwd_str}", flush=True)

        try:
            return subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                env=env,
                check=check,
                capture_output=capture_output,
                text=text,
                shell=shell,
            )
        except subprocess.CalledProcessError as exc:
            self.log_error(f"Command failed with exit code {exc.returncode}: {cmd_str}")
            if exc.stderr:
                print(f"{self.RED}{exc.stderr}{self.NC}", file=sys.stderr, flush=True)
            raise
        except FileNotFoundError as exc:
            self.log_error(f"Executable not found for command: {cmd_str}")
            raise
