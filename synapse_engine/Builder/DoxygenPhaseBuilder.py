from pathlib import Path
import subprocess
import sys
from typing import Optional
from ..Environment.SynapseConfig import SynapseConfig


class DoxygenPhaseBuilder:
    """Orchestration phase that executes Doxygen to validate and generate documentation."""

    def __init__(self, config: SynapseConfig, workspace_dir: Optional[Path] = None) -> None:
        self.config = config
        self.workspace_dir = workspace_dir or Path.cwd().resolve()

    def execute(self) -> None:
        """Executes the Doxygen binary against the workspace Doxyfile."""
        print("==> Executing Doxygen Documentation Phase...")
        
        doxyfile_path = self.workspace_dir / "Doxyfile"
        if not doxyfile_path.exists():
            print(f"FATAL: Doxyfile not found at {doxyfile_path}.", file=sys.stderr)
            sys.exit(1)

        try:
            # Invoke system doxygen process
            result = subprocess.run(
                ["doxygen", str(doxyfile_path)],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout:
                print(result.stdout)
                
            print("==> Doxygen generation passed successfully.")

        except subprocess.CalledProcessError as e:
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr, file=sys.stderr)
            print("FATAL: Doxygen reported documentation warnings/errors under strict mode.", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("FATAL: 'doxygen' binary is not installed or not found in system PATH.", file=sys.stderr)
            sys.exit(1)