from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class SynapseConfig:
    """Immutable runtime configuration for the Synapse build orchestration engine."""

    project_name: str
    project_version: str        # Target release or build version (e.g. 0.4.0)
    build_type: str
    conan_profile: str          # Host/Build toolchain profile (e.g. toolchains/clang21)
    target_profile: str         # Target execution profile (e.g. targets/test)
    out_dir: Path
    conan_enabled: bool = True
    conan_remote_name: str = ""
    conan_remote_url: str = ""
    conan_login_user: str = ""
    conan_login_password: str = ""
    conan_package_user: str = "systic"
    conan_package_channel: str = "stable"
    extra_flags: List[str] = field(default_factory=list)
    cmake_args: Dict[str, str] = field(default_factory=dict)