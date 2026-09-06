from pathlib import Path
import shutil
import sys

from ..Environment.SynapseConfig import SynapseConfig
from ..Runner.ProcessRunner import ProcessRunner


class ConanPhaseBuilder:
    """Handles Conan remote configuration, authentication, and composable profile installation."""

    def __init__(self, config: SynapseConfig) -> None:
        self.config = config
        self.runner = ProcessRunner()
        # Resolve the root directory of the 'synapse' package
        self.synapse_root = Path("/workspace")

    def _resolve_profile(self, profile_name: str) -> Path:
        """Resolves a profile path against synapse root, CWD, and global Conan cache."""
        candidates = [
            self.synapse_root / ".conan" / "profiles" / profile_name,
            Path.cwd() / ".conan" / "profiles" / profile_name,
            Path.home() / ".conan2" / "profiles" / profile_name,
            ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        # Fallback to absolute path under synapse root
        return self.synapse_root / ".conan" / "profiles" / profile_name

    def _get_active_profiles(self) -> tuple[Path, Path]:
        """Resolves the base toolchain profile and the target build profile."""
        # 1. Base compiler toolchain profile (e.g., 'toolchains/clang21')
        toolchain_name = getattr(self.config, "conan_profile", "toolchains/clang21")
        toolchain_path = self._resolve_profile(toolchain_name)

        # 2. Build target profile (e.g., 'targets/dev', 'targets/release', 'targets/test')
        target_name = getattr(
            self.config,
            "target_profile",
            f"targets/{self.config.build_type.lower()}"
        )
        target_path = self._resolve_profile(target_name)

        if not toolchain_path.is_file():
            self.runner.log_error(f"Base toolchain profile not found: {toolchain_path}")
            sys.exit(1)

        if not target_path.is_file():
            self.runner.log_error(f"Target build profile not found: {target_path}")
            sys.exit(1)

        return toolchain_path, target_path

    def _ensure_conan_global_conf(self) -> None:
        """Ensures that ~/.conan2/global.conf is initialized for Ninja."""
        conan_home = Path.home() / ".conan2"
        conan_home.mkdir(parents=True, exist_ok=True)
        global_conf = conan_home / "global.conf"

        if not global_conf.is_file():
            cmake_path = shutil.which("cmake") or "cmake"
            global_conf.write_text(
                f"tools.cmake.cmaketoolchain:generator=Ninja\n"
                f"tools.cmake:cmake_program={cmake_path}\n",
                encoding="utf-8",
            )
            self.runner.log_info("Configured Conan 2.x global.conf for Ninja integration.")

    def execute(self) -> None:
        """Executes Conan dependency resolution and toolchain generation."""
        if not self.config.conan_enabled:
            self.runner.log_info("Conan integration is disabled. Skipping Conan phase.")
            return

        self._ensure_conan_global_conf()

        # 1. Remote setup & Authentication
        if self.config.conan_remote_name and self.config.conan_remote_url:
            self.runner.log_info(
                f"Configuring remote registry mapping: {self.config.conan_remote_name} -> {self.config.conan_remote_url}"
            )
            self.runner.run(
                [
                    "conan",
                    "remote",
                    "add",
                    self.config.conan_remote_name,
                    self.config.conan_remote_url,
                    "--force",
                ]
            )

            if self.config.conan_login_user and self.config.conan_login_password:
                self.runner.log_info(f"Authenticating as '{self.config.conan_login_user}'...")
                self.runner.run(
                    [
                        "conan",
                        "remote",
                        "login",
                        self.config.conan_remote_name,
                        self.config.conan_login_user,
                        "--password",
                        self.config.conan_login_password,
                    ]
                )

        # 2. Profile Resolution
        toolchain_pr, target_pr = self._get_active_profiles()

        self.config.out_dir.mkdir(parents=True, exist_ok=True)

        self.runner.log_info(f"Using Toolchain Profile (Build Context): {toolchain_pr}")
        self.runner.log_info(f"Using Target Profile (Host Context): {toolchain_pr} + {target_pr}")

        # 3. Dependency installation & Toolchain generation
        conan_install_cmd = [
            "conan",
            "install",
            ".",
            "-of",
            str(self.config.out_dir),
            "--build=missing",
            f"-pr:b={toolchain_pr}",
            f"-pr:h={toolchain_pr}",
            f"-pr:h={target_pr}",
            f"-s:h=build_type={self.config.build_type}",
            "-g",
            "CMakeDeps",
            "-g",
            "CMakeToolchain",
        ]

        self.runner.run(conan_install_cmd)

        # Locate generated toolchain file for validation
        toolchain_file = self.config.out_dir / "conan_toolchain.cmake"
        if not toolchain_file.is_file():
            # Support Conan layout directories (e.g., generators/)
            toolchain_file = self.config.out_dir / "generators" / "conan_toolchain.cmake"

        self.runner.log_success(f"Conan toolchain successfully verified at {toolchain_file}")