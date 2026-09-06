import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import List, Optional

from ..Environment.SynapseConfig import SynapseConfig
from .ProcessRunner import ProcessRunner


class OCIRunner:
    """Manages transparent containerized builds via OCI container runtime drivers."""

    def __init__(self, config: SynapseConfig, workspace_dir: Optional[Path] = None) -> None:
        self.config = config
        self.workspace_dir = workspace_dir.resolve() if workspace_dir else Path.cwd().resolve()
        self.runner = ProcessRunner()
        self.engine = self._detect_oci_engine()
        self.image_name = f"{self.config.project_name}_build_image"
        self.container_name = f"{self.config.project_name}_build_container"

    def _detect_oci_engine(self) -> str:
        """Detects whether docker or podman is installed and available."""
        for engine_candidate in ("docker", "podman"):
            if shutil.which(engine_candidate):
                return engine_candidate
        self.runner.log_error("No OCI container runtime found. Please install Docker or Podman.")
        sys.exit(1)

    def _ensure_image_exists(self) -> None:
        """Checks if the build image exists; if missing, triggers build."""
        check_proc = subprocess.run(
            [self.engine, "images", "-q", self.image_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if check_proc.returncode == 0 and check_proc.stdout.strip():
            self.runner.log_info(f"Using existing OCI build image: {self.image_name}")
            return

        self.runner.log_info(f"OCI image '{self.image_name}' not found. Looking for Dockerfile...")
        candidate_dockerfile_dirs = [
            self.workspace_dir / ".github" / "workflows",
            self.workspace_dir,
            self.workspace_dir.parent / "SlotThreadSafe" / ".github" / "workflows",
        ]

        build_context_dir: Optional[Path] = None
        for candidate in candidate_dockerfile_dirs:
            if (candidate / "Dockerfile").is_file():
                build_context_dir = candidate
                break

        if not build_context_dir:
            self.runner.log_error(
                f"Cannot build image '{self.image_name}': Dockerfile not found in search paths."
            )
            sys.exit(1)

        self.runner.log_info(f"Building OCI image '{self.image_name}' from {build_context_dir}...")
        self.runner.run([self.engine, "build", "-t", self.image_name, str(build_context_dir)])

    def _cleanup_stale_container(self) -> None:
        """Forcefully cleans up any existing container with the target name."""
        check_proc = subprocess.run(
            [self.engine, "ps", "-aq", "-f", f"name=^/{self.container_name}$"],
            capture_output=True,
            text=True,
            check=False,
        )
        if check_proc.returncode == 0 and check_proc.stdout.strip():
            self.runner.log_info(f"Cleaning up stale container: {self.container_name}")
            subprocess.run([self.engine, "rm", "-f", self.container_name], check=False, capture_output=True)

    def execute_in_container(self, command_args: List[str]) -> None:
        """Runs the build command inside the OCI container with mounted volumes and signal traps."""
        self._ensure_image_exists()
        self._cleanup_stale_container()

        # Ensure host Conan cache directory exists
        conan_cache_host = self.workspace_dir / ".conan" / "cache" / self.config.conan_profile
        conan_cache_host.mkdir(parents=True, exist_ok=True)

        docker_cmd = [
            self.engine,
            "run",
            "--name",
            self.container_name,
            "--network",
            "host",
            "--security-opt",
            "seccomp=unconfined",
            "-v",
            f"{self.workspace_dir}:/workspace",
            "-v",
            f"{conan_cache_host}:/root/.conan2",
            "-w",
            "/workspace",
        ]

        # Pass environment variables
        env_keys_to_forward = [
            "PROJECT_NAME",
            "BUILD_TYPE",
            "CONAN_PROFILE",
            "OUT_DIR",
            "CONAN_ENABLED",
            "CONAN_REMOTE_NAME",
            "CONAN_REMOTE_URL",
            "CONAN_LOGIN_USER",
            "CONAN_LOGIN_PASSWORD",
            "CONAN_PACKAGE_USER",
            "CONAN_PACKAGE_CHANNEL",
        ]
        for key in env_keys_to_forward:
            val = os.getenv(key)
            if val is not None:
                docker_cmd.extend(["-e", f"{key}={val}"])

        docker_cmd.append(self.image_name)
        docker_cmd.extend(command_args)

        # Setup graceful signal handling for SIGINT / SIGTERM
        def _signal_handler(signum: int, frame: object) -> None:
            self.runner.log_warn(f"Received signal {signum}. Terminating container {self.container_name}...")
            subprocess.run([self.engine, "rm", "-f", self.container_name], check=False, capture_output=True)
            sys.exit(128 + signum)

        original_sigint = signal.signal(signal.SIGINT, _signal_handler)
        original_sigterm = signal.signal(signal.SIGTERM, _signal_handler)

        try:
            self.runner.log_info(f"Launching containerized execution via {self.engine}...")
            self.runner.run(docker_cmd)
        finally:
            # Restore original signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            self._cleanup_stale_container()
