import multiprocessing

from ..Environment.SynapseConfig import SynapseConfig
from ..Runner.ProcessRunner import ProcessRunner


class CompilePhaseBuilder:
    """Executes high-throughput C++ compilation saturating all available CPU cores."""

    def __init__(self, config: SynapseConfig) -> None:
        self.config = config
        self.runner = ProcessRunner()

    def execute(self) -> None:
        """Executes cmake --build with optimal parallelism."""
        cores = multiprocessing.cpu_count()
        self.runner.log_info(f"Compiling project '{self.config.project_name}' using {cores} parallel jobs...")

        build_cmd = [
            "cmake",
            "--build",
            str(self.config.out_dir),
            f"-j{cores}",
        ]
        self.runner.run(build_cmd)
        self.runner.log_success(f"Compilation finished for target directory: {self.config.out_dir}")
