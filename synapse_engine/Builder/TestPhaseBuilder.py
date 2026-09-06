import os
from pathlib import Path
import re
import sys
from typing import List, Tuple

from ..Environment.SynapseConfig import SynapseConfig
from ..Runner.ProcessRunner import ProcessRunner


class TestPhaseBuilder:
    """Scans and executes GTest unit tests and Google Benchmark executables."""

    # Subdirectories within build output to search
    SEARCH_SUBDIRS = ["bin", "."]

    # Matching patterns for test and benchmark binaries
    TEST_PATTERN = re.compile(r"(?:^|_|-)tests?(?:$|_|-|\.exe$)", re.IGNORECASE)
    BENCH_PATTERN = re.compile(r"(?:^|_|-)(?:bench|benchmarks?)(?:$|_|-|\.exe$)", re.IGNORECASE)

    def __init__(self, config: SynapseConfig, workspace_dir: Path = Path.cwd()) -> None:
        self.config = config
        self.workspace_dir = workspace_dir
        self.runner = ProcessRunner()

    def _is_executable(self, path: Path) -> bool:
        """Validates if a path points to a runnable binary."""
        if not path.is_file():
            return False

        # Check UNIX executable permissions or Windows executable extensions
        is_exec = os.access(path, os.X_OK) or path.suffix.lower() == ".exe"
        if not is_exec:
            return False

        # Exclude internal build artifacts and generators
        excluded_parts = {"CMakeFiles", ".ninja", "generators", "CMakeTmp"}
        return not any(part in excluded_parts for part in path.parts)

    def _find_targets(self) -> Tuple[List[Path], List[Path]]:
        """Scans build directory for test and benchmark executables."""
        test_binaries: List[Path] = []
        bench_binaries: List[Path] = []

        if not self.config.out_dir.is_dir():
            return test_binaries, bench_binaries

        # Search candidates in output directory
        for path in self.config.out_dir.rglob("*"):
            if not self._is_executable(path):
                continue

            stem_or_name = path.name
            if self.TEST_PATTERN.search(stem_or_name):
                test_binaries.append(path)
            elif self.BENCH_PATTERN.search(stem_or_name):
                bench_binaries.append(path)

        return test_binaries, bench_binaries

    def execute(self) -> None:
        """Executes discovered test and benchmark binaries."""
        test_binaries, bench_binaries = self._find_targets()

        if not test_binaries and not bench_binaries:
            self.runner.log_warn(
                f"No test or benchmark executables matched patterns in {self.config.out_dir}.\n"
                f"Ensure CMake is invoked with -DBUILD_TESTING=ON / -DBUILD_BENCHMARKING=ON."
            )
            return

        # 1. Run GTest Binaries
        for test_bin in test_binaries:
            xml_output = self.workspace_dir / f"test_results_{test_bin.stem}.xml"
            self.runner.log_info(f"Executing GTest target: {test_bin.relative_to(self.config.out_dir)}")
            try:
                self.runner.run([str(test_bin.resolve()), f"--gtest_output=xml:{xml_output}"])
                if xml_output.is_file():
                    self.runner.log_success(f"Test results exported to {xml_output}")
                else:
                    self.runner.log_warn(f"Test ran but output file {xml_output} was not created.")
            except Exception as exc:
                self.runner.log_error(f"Test execution failed for {test_bin.name}: {exc}")
                sys.exit(1)

        # 2. Run Google Benchmark Binaries
        for bench_bin in bench_binaries:
            json_output = self.workspace_dir / f"bench_results_{bench_bin.stem}.json"
            self.runner.log_info(f"Executing Google Benchmark target: {bench_bin.relative_to(self.config.out_dir)}")
            try:
                self.runner.run(
                    [
                        str(bench_bin.resolve()),
                        f"--benchmark_out={json_output}",
                        "--benchmark_out_format=json",
                    ]
                )
                if json_output.is_file():
                    self.runner.log_success(f"Benchmark results exported to {json_output}")
                else:
                    self.runner.log_warn(f"Benchmark ran but output file {json_output} was not created.")
            except Exception as exc:
                self.runner.log_error(f"Benchmark execution failed for {bench_bin.name}: {exc}")
                sys.exit(1)