import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Set

from .SynapseConfig import SynapseConfig


class EnvironmentParser:
    """Parses environment variables and .env configuration files for Synapse."""

    # Valid Conan settings.build_type values mapped from internal profile/build aliases
    CONAN_BUILD_TYPE_MAP: Dict[str, str] = {
        "debug": "Debug",
        "release": "Release",
        "relwithdebinfo": "RelWithDebInfo",
    }

    # ANSI color codes for diagnostic output
    RED = "\033[0;31m"
    BOLD = "\033[1m"
    NC = "\033[0m"

    def __init__(self, env_path: Path = Path("../.env")) -> None:
        self.env_path = env_path

    def parse_env_file(self) -> Dict[str, str]:
        """Parses key-value pairs from the .env file if present."""
        env_vars: Dict[str, str] = {}
        if not self.env_path.is_file():
            return env_vars

        with open(self.env_path, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                clean_key = key.strip()
                clean_val = val.strip().strip("'\"")
                if clean_key:
                    env_vars[clean_key] = clean_val
        return env_vars

    def _format_error(self, message: str) -> None:
        """Prints a standardized diagnostic error message to stderr."""
        print(f"{self.RED}{self.BOLD}[SYNAPSE CONFIG ERROR]{self.NC} {message}", file=sys.stderr)

    def load_config(
            self,
            profile: Optional[str] = None,
            target_profile: Optional[str] = None,
            build_type: Optional[str] = None,
            project_version: Optional[str] = None,
            extra_flags: Optional[List[str]] = None,
            cmake_args: Optional[Dict[str, str]] = None,
    ) -> SynapseConfig:
        """Loads and strictly validates the Synapse configuration."""
        file_env = self.parse_env_file()

        def resolve_value(key: str) -> Optional[str]:
            return os.getenv(key, file_env.get(key))

        # 1. Project Name validation
        project_name = resolve_value("PROJECT_NAME") or "arrayslotthreadsafe"

        # 2. Project Version resolution (Explicit param > PROJECT_VERSION > SYNAPSE_VERSION > VERSION > Fallback)
        effective_project_version = (
                project_version
                or resolve_value("PROJECT_VERSION")
                or resolve_value("SYNAPSE_VERSION")
                or resolve_value("VERSION")
                or "0.1.0"
        )

        # 3. Base Toolchain Profile validation (--profile:build / toolchain context)
        effective_profile = profile or resolve_value("CONAN_PROFILE") or "toolchains/clang21"

        # 4. Resolve Execution Context Alias
        raw_build_type = (build_type or resolve_value("BUILD_TYPE") or "release").strip().lower()

        if raw_build_type not in self.CONAN_BUILD_TYPE_MAP:
            self._format_error(
                f"Invalid BUILD_TYPE '{raw_build_type}'. Supported values are: "
                f"{', '.join(sorted(self.CONAN_BUILD_TYPE_MAP.keys()))}"
            )
            sys.exit(1)

        # Map to standard Conan settings.build_type ("Debug", "Release", "RelWithDebInfo")
        effective_conan_build_type = self.CONAN_BUILD_TYPE_MAP[raw_build_type]

        # 5. Target Profile resolution (--profile:host / target context)
        effective_target_profile = (
                target_profile
                or resolve_value("TARGET_PROFILE")
                or f"targets/{raw_build_type}"
        )

        # Extract profile stem for directory naming (e.g., '.build-test')
        target_stem = Path(effective_target_profile).stem.lower()

        # 6. Automatically enable BUILD_TESTING for CMake if context is 'test'
        effective_cmake_args = cmake_args.copy() if cmake_args is not None else {}
        if raw_build_type == "relwithdebinfo" and "BUILD_TESTING" not in effective_cmake_args:
            effective_cmake_args["BUILD_TESTING"] = "ON"
            effective_cmake_args["BUILD_BENCHMARKING"] = "ON"

        # 7. Conan Enabled toggle
        conan_enabled_raw = resolve_value("CONAN_ENABLED")
        if conan_enabled_raw is None:
            conan_enabled = True
        else:
            conan_enabled = conan_enabled_raw.strip().lower() in ("true", "1", "on", "yes")

        # 8. Output Directory resolution (.build-test, .build-release, etc.)
        out_dir_raw = resolve_value("OUT_DIR")
        if out_dir_raw:
            out_dir = Path(out_dir_raw)
            if not out_dir.is_absolute():
                out_dir = Path.cwd() / out_dir
        else:
            out_dir = Path.cwd() / f".build-{target_stem}"

        # 9. Conan Remote Configuration
        conan_remote_name = resolve_value("CONAN_REMOTE_NAME") or ""
        conan_remote_url = resolve_value("CONAN_REMOTE_URL") or ""
        conan_login_user = resolve_value("CONAN_LOGIN_USER") or ""
        conan_login_password = resolve_value("CONAN_LOGIN_PASSWORD") or ""
        conan_package_user = resolve_value("CONAN_PACKAGE_USER") or "default"
        conan_package_channel = resolve_value("CONAN_PACKAGE_CHANNEL") or "dev"

        if conan_enabled and conan_remote_url and not conan_remote_name:
            self._format_error("CONAN_ENABLED is active with remote URL set, but CONAN_REMOTE_NAME is missing.")
            sys.exit(1)

        return SynapseConfig(
            project_name=project_name,
            project_version=effective_project_version,
            build_type=effective_conan_build_type,  # Passes "Debug" to Conan
            conan_profile=effective_profile,
            target_profile=effective_target_profile,  # Keeps "targets/test"
            out_dir=out_dir,  # Keeps ".build-test"
            conan_enabled=conan_enabled,
            conan_remote_name=conan_remote_name,
            conan_remote_url=conan_remote_url,
            conan_login_user=conan_login_user,
            conan_login_password=conan_login_password,
            conan_package_user=conan_package_user,
            conan_package_channel=conan_package_channel,
            extra_flags=extra_flags if extra_flags is not None else [],
            cmake_args=effective_cmake_args,
        )