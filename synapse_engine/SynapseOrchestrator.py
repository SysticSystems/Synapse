from pathlib import Path
from typing import Optional

from .Builder.CMakePhaseBuilder import CMakePhaseBuilder
from .Builder.CompilePhaseBuilder import CompilePhaseBuilder
from .Builder.ConanPhaseBuilder import ConanPhaseBuilder
from .Builder.PublishPhaseBuilder import PublishPhaseBuilder
from .Builder.TestPhaseBuilder import TestPhaseBuilder
from .Builder.TidyPhaseBuilder import TidyPhaseBuilder
from .Environment.SynapseConfig import SynapseConfig
from .Runner.LocalRunner import LocalRunner


class SynapseOrchestrator:
    """High-level façade that executes build phase builders sequentially."""

    def __init__(self, config: SynapseConfig, workspace_dir: Optional[Path] = None) -> None:
        self.config = config
        self.workspace_dir = workspace_dir.resolve() if workspace_dir else Path.cwd().resolve()
        self.local_runner = LocalRunner(self.config)

    def run(
            self,
            run_test: bool = False,
            run_fix: bool = False,
            run_publish: bool = False,
    ) -> None:
        """Executes the pipeline builders based on configuration and phase flags."""

        # 1. Formatting & Static Analysis Fix Phase
        if run_fix:
            tidy_builder = TidyPhaseBuilder(self.config, workspace_dir=self.workspace_dir)
            self.local_runner.run_phase("Clang-Tidy Fix", tidy_builder)
            return

        # 2. Conan Dependency Resolution
        conan_builder = ConanPhaseBuilder(self.config)
        self.local_runner.run_phase("Conan Resolution", conan_builder)

        # 3. CMake Configuration
        cmake_builder = CMakePhaseBuilder(self.config)
        self.local_runner.run_phase("CMake Configuration", cmake_builder)

        # 4. Native Multi-Core Compilation
        compile_builder = CompilePhaseBuilder(self.config)
        self.local_runner.run_phase("Compilation", compile_builder)

        # 5. Testing & Benchmarking Phase
        # Triggers if --test flag is set OR if build_type is 'Testing' / 'Debug'

        should_test = run_test or self.config.build_type == "RelWithDebInfo"
        if should_test:
            test_builder = TestPhaseBuilder(self.config, workspace_dir=self.workspace_dir)
            self.local_runner.run_phase("Testing & Benchmarking", test_builder)

        # 6. Package & Artifact Publishing
        if run_publish:
            publish_builder = PublishPhaseBuilder(self.config, workspace_dir=self.workspace_dir)
            self.local_runner.run_phase("Package & Publish", publish_builder)