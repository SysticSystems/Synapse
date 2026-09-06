from pathlib import Path
import re
import sys
from typing import Optional, Tuple

from ..Environment.SynapseConfig import SynapseConfig
from ..Runner.ProcessRunner import ProcessRunner


class PublishPhaseBuilder:
    """Packages and publishes C++ artifacts to the upstream Conan server registry."""

    def __init__(self, config: SynapseConfig, workspace_dir: Path = Path.cwd()) -> None:
        self.config = config
        self.workspace_dir = workspace_dir / "synapse"
        self.runner = ProcessRunner()

    def _get_package_metadata(self) -> Tuple[str, Optional[str]]:
        """Retrieves package name and version from config without hardcoded defaults."""
        pkg_name = self.config.project_name
        pkg_version = self.config.project_version

        conanfile = self.workspace_dir / "conanfile.py"

        # Read conanfile.py if fields are missing in config
        if conanfile.is_file() and (not pkg_name or not pkg_version):
            content = conanfile.read_text(encoding="utf-8")
            if not pkg_name:
                name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if name_match:
                    pkg_name = name_match.group(1).strip()
            if not pkg_version:
                version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if version_match:
                    pkg_version = version_match.group(1).strip()

        # Enforce that project name is provided
        if not pkg_name:
            self.runner.log_error(
                "Project name missing! Define 'PROJECT_NAME' in your .env file or 'name' in conanfile.py."
            )
            sys.exit(1)

        return pkg_name, pkg_version

    def _resolve_profile_path(self) -> Path:
        """Resolves the path to the specified Conan profile."""
        profile_candidates = [
            Path(".conan/profiles") / self.config.conan_profile,
            self.workspace_dir / ".conan" / "profiles" / self.config.conan_profile,
            Path.home() / ".conan2" / "profiles" / self.config.conan_profile,
            ]
        for candidate in profile_candidates:
            if candidate.is_file():
                return candidate
        return Path(".conan/profiles") / self.config.conan_profile

    def execute(self) -> None:
        """Executes conan create and conan upload."""
        if not self.config.conan_enabled:
            self.runner.log_error("Cannot publish artifact: Conan is disabled in configuration.")
            sys.exit(1)

        pkg_name, pkg_version = self._get_package_metadata()

        profile_path = self._resolve_profile_path()

        # Construct reference string representation
        version_str = pkg_version if pkg_version else "<recipe-defined>"
        if self.config.conan_package_user and self.config.conan_package_channel:
            full_package_ref = (
                f"{pkg_name}/{version_str}@{self.config.conan_package_user}/{self.config.conan_package_channel}"
            )
        else:
            full_package_ref = f"{pkg_name}/{version_str}"

        self.runner.log_info(f"Target Reference Identified: {full_package_ref}")
        self.runner.log_info("Packaging recipe and compiling binary package artifact...")

        create_cmd = [
            "conan",
            "create",
            ".",
            f"-pr:b={profile_path}",
            f"-pr:h={profile_path}",
            "-s",
            f"build_type={self.config.build_type}",
            "--build=missing",
        ]

        # Only explicitly pass --version if configured in .env or detected externally
        if self.config.project_version:
            create_cmd.append(f"--version={self.config.project_version}")

        if self.config.conan_package_user:
            create_cmd.append(f"--user={self.config.conan_package_user}")
        if self.config.conan_package_channel:
            create_cmd.append(f"--channel={self.config.conan_package_channel}")

        self.runner.run(create_cmd)

        self.runner.log_info(f"Uploading package upstream to remote '{self.config.conan_remote_name}'...")

        # If pkg_version was not set explicitly, target reference pattern for upload
        upload_target = (
            full_package_ref
            if pkg_version
            else f"{pkg_name}/*@{self.config.conan_package_user}/{self.config.conan_package_channel}"
            if self.config.conan_package_user and self.config.conan_package_channel
            else f"{pkg_name}/*"
        )

        upload_cmd = [
            "conan",
            "upload",
            upload_target,
            "-r",
            self.config.conan_remote_name,
        ]

        self.runner.run(upload_cmd)
        self.runner.log_success(
            f"Package '{upload_target}' successfully published to remote '{self.config.conan_remote_name}'."
        )