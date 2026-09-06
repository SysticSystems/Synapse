from pathlib import Path
import shutil
import sys
from typing import List

from ..Environment.SynapseConfig import SynapseConfig
from ..Runner.ProcessRunner import ProcessRunner
from .CMakePhaseBuilder import CMakePhaseBuilder


class TidyPhaseBuilder:
    """Automates static analysis and auto-remediation via clang-tidy."""

    CPP_EXTENSIONS = {".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".h"}
    SEARCH_DIRS = ("src", "include", "tests", "bench")

    def __init__(self, config: SynapseConfig, workspace_dir: Path = Path.cwd()) -> None:
        self.config = config
        self.workspace_dir = workspace_dir
        self.runner = ProcessRunner()

    def _locate_or_generate_compile_commands(self) -> Path:
        """Locates compile_commands.json or automatically triggers CMake configure."""
        compile_db = self.config.out_dir / "compile_commands.json"
        if not compile_db.is_file():
            self.runner.log_warn(
                f"compile_commands.json not found at {compile_db}. Auto-triggering CMake configuration..."
            )
            cmake_builder = CMakePhaseBuilder(self.config)
            cmake_builder.execute()

        if not compile_db.is_file():
            self.runner.log_error(
                f"Failed to generate compile_commands.json at {compile_db}. Aborting tidy phase."
            )
            sys.exit(1)

        return compile_db

    def _collect_source_files(self) -> List[Path]:
        """Collects all C/C++ source and header files across target directories."""
        source_files: List[Path] = []
        for dir_name in self.SEARCH_DIRS:
            target_dir = self.workspace_dir / dir_name
            if target_dir.is_dir():
                for file_path in target_dir.rglob("*"):
                    if file_path.is_file() and file_path.suffix in self.CPP_EXTENSIONS:
                        source_files.append(file_path)
        return sorted(source_files)

    def execute(self) -> None:
        """Executes clang-tidy auto-fix across codebase."""
        tidy_bin = shutil.which("clang-tidy")
        if not tidy_bin:
            self.runner.log_error("clang-tidy executable not found on system PATH.")
            sys.exit(1)

        compile_db = self._locate_or_generate_compile_commands()
        sources = self._collect_source_files()

        if not sources:
            self.runner.log_warn("No C++ source or header files found in src/, include/, tests/, or bench/.")
            return

        self.runner.log_info(f"Running clang-tidy --fix on {len(sources)} files...")
        tidy_cmd = [
            tidy_bin,
            f"-p={compile_db.parent}",
            "--fix",
            "--fix-errors",
            "--format-style=file",
        ] + [str(s) for s in sources]

        try:
            self.runner.run(tidy_cmd)
            self.runner.log_success("clang-tidy --fix completed cleanly. Review modifications with git diff.")
        except Exception as exc:
            self.runner.log_warn(
                f"clang-tidy reported issues during execution: {exc}. Manual inspection may be required."
            )
