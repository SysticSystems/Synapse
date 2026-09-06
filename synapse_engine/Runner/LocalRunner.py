import time
from typing import Any, List

from ..Environment.SynapseConfig import SynapseConfig
from .ProcessRunner import ProcessRunner


class LocalRunner:
    """Handles direct local execution pipeline orchestration."""

    def __init__(self, config: SynapseConfig) -> None:
        self.config = config
        self.runner = ProcessRunner()

    def run_phase(self, phase_name: str, builder: Any) -> None:
        """Executes a single phase builder locally."""
        self.runner.log_step(phase_name, self.config.project_name)
        start_time = time.perf_counter()
        builder.execute()
        duration = time.perf_counter() - start_time
        self.runner.log_success(f"Phase '{phase_name}' completed in {duration:.2f}s")

    def run_pipeline(self, pipeline: List[tuple[str, Any]]) -> None:
        """Executes a sequence of named phase builders sequentially."""
        total_start = time.perf_counter()
        for phase_name, builder in pipeline:
            self.run_phase(phase_name, builder)
        total_duration = time.perf_counter() - total_start
        self.runner.log_success(
            f"All local pipeline phases for '{self.config.project_name}' completed in {total_duration:.2f}s"
        )
