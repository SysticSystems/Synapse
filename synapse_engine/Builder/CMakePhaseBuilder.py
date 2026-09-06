from pathlib import Path
import subprocess
import sys

from ..Environment.SynapseConfig import SynapseConfig


class CMakePhaseBuilder:
    """Configures CMake relying strictly on the system binary and Conan-generated toolchain."""

    def __init__(self, config: SynapseConfig) -> None:
        self.config = config

    def _resolve_toolchain_file(self) -> Path:
        """Dynamically locates conan_toolchain.cmake across standard Conan 2.x layout configurations."""
        candidate_paths = [
            # 1. Standard Conan 2.x cmake_layout: .build-test/build/Debug/generators/
            self.config.out_dir / "build" / self.config.build_type / "generators" / "conan_toolchain.cmake",
            # 2. Direct build-type subfolder: .build-test/Debug/generators/
            self.config.out_dir / self.config.build_type / "generators" / "conan_toolchain.cmake",
            # 3. Direct generators folder under output dir: .build-test/generators/
            self.config.out_dir / "generators" / "conan_toolchain.cmake",
            # 4. Flat layout under output dir: .build-test/conan_toolchain.cmake
            self.config.out_dir / "conan_toolchain.cmake",
            ]

        for path in candidate_paths:
            if path.is_file():
                return path

        return candidate_paths[0]  # Return default path for diagnostic reporting

    def execute(self) -> None:
        """Configures CMake using the container's native binaries."""
        toolchain_file = self._resolve_toolchain_file()

        if not toolchain_file.is_file():
            print(f"[SYNAPSE ERROR] Toolchain file missing in {self.config.out_dir}: {toolchain_file}", file=sys.stderr)
            print("[SYNAPSE ERROR] Ensure Conan Phase completed before CMake Phase.", file=sys.stderr)
            sys.exit(1)


        cmd = [
            "cmake",
            "-G", "Ninja",
            "-S", ".",
            "-B", str(self.config.out_dir),
            f"-DCMAKE_BUILD_TYPE={self.config.build_type}",  # <-- Pass build_type (e.g. Debug)
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]

        # Append custom user or profile cmake_args
        for key, value in self.config.cmake_args.items():
            # Prevent duplicate -DCMAKE_BUILD_TYPE if already present in cmake_args
            if key != "CMAKE_BUILD_TYPE":
                cmd.append(f"-D{key}={value}")

        print(f"[SYNAPSE INFO] Configuring CMake ({self.config.build_type}) in {self.config.out_dir}...")
        print(f"[SYNAPSE INFO] Using toolchain: {toolchain_file}")
        subprocess.run(cmd, check=True)
        print("[SYNAPSE SUCCESS] CMake configuration complete.")