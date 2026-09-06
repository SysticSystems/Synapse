from dataclasses import FrozenInstanceError
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from synapse_engine.Builder.CMakePhaseBuilder import CMakePhaseBuilder
from synapse_engine.Builder.CompilePhaseBuilder import CompilePhaseBuilder
from synapse_engine.Builder.ConanPhaseBuilder import ConanPhaseBuilder
from synapse_engine.Builder.PublishPhaseBuilder import PublishPhaseBuilder
from synapse_engine.Builder.TestPhaseBuilder import TestPhaseBuilder
from synapse_engine.Builder.TidyPhaseBuilder import TidyPhaseBuilder
from synapse_engine.Environment.EnvironmentParser import EnvironmentParser
from synapse_engine.Environment.SynapseConfig import SynapseConfig
from synapse_engine.Runner.LocalRunner import LocalRunner
from synapse_engine.Runner.OCIRunner import OCIRunner
from synapse_engine.Runner.ProcessRunner import ProcessRunner
from synapse_engine.SynapseOrchestrator import SynapseOrchestrator
import synapse


class TestSynapseConfig(unittest.TestCase):
    """Tests for the immutable SynapseConfig data model."""

    def test_synapse_config_instantiation(self):
        config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
            conan_enabled=True,
            conan_remote_name="laptop_server",
            conan_remote_url="http://172.17.0.1:9300",
            conan_login_user="systic_user",
            conan_login_password="secret_password",
            conan_package_user="systic",
            conan_package_channel="stable",
            extra_flags=["-O3"],
            cmake_args={"ENABLE_AVX": "ON"},
        )
        self.assertEqual(config.project_name, "systic")
        self.assertEqual(config.project_version, "0.1.0")
        self.assertEqual(config.build_type, "Release")
        self.assertEqual(config.conan_profile, "toolchains/clang21")
        self.assertEqual(config.target_profile, "targets/release")
        self.assertEqual(config.out_dir, Path(".build-release"))
        self.assertTrue(config.conan_enabled)
        self.assertEqual(config.conan_remote_name, "laptop_server")
        self.assertEqual(config.conan_remote_url, "http://172.17.0.1:9300")
        self.assertEqual(config.conan_login_user, "systic_user")
        self.assertEqual(config.conan_login_password, "secret_password")
        self.assertEqual(config.conan_package_user, "systic")
        self.assertEqual(config.conan_package_channel, "stable")
        self.assertEqual(config.extra_flags, ["-O3"])
        self.assertEqual(config.cmake_args, {"ENABLE_AVX": "ON"})

    def test_synapse_config_defaults(self):
        config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        self.assertTrue(config.conan_enabled)
        self.assertEqual(config.conan_remote_name, "")
        self.assertEqual(config.conan_remote_url, "")
        self.assertEqual(config.conan_login_user, "")
        self.assertEqual(config.conan_login_password, "")
        self.assertEqual(config.conan_package_user, "systic")
        self.assertEqual(config.conan_package_channel, "stable")
        self.assertEqual(config.extra_flags, [])
        self.assertEqual(config.cmake_args, {})

    def test_synapse_config_immutability(self):
        config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        with self.assertRaises(FrozenInstanceError):
            config.project_name = "modified"  # type: ignore

    def test_zero_domain_defaults(self):
        # Missing required positional arguments should raise TypeError
        with self.assertRaises(TypeError):
            SynapseConfig()  # type: ignore


class TestEnvironmentParser(unittest.TestCase):
    """Tests for environment variable and .env configuration resolution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.env_file = self.test_dir / ".env"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_env_file_missing(self):
        parser = EnvironmentParser(self.test_dir / "non_existent.env")
        self.assertEqual(parser.parse_env_file(), {})

    def test_parse_env_file_valid_and_edge_cases(self):
        self.env_file.write_text(
            "# Comment line\n"
            "\n"
            "PROJECT_NAME=systic\n"
            "BUILD_TYPE='Debug'\n"
            'CONAN_PROFILE="clang21"\n'
            "CONAN_ENABLED=true\n"
            "INVALID_LINE_WITHOUT_EQUALS\n"
            "EMPTY_KEY=\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        parsed = parser.parse_env_file()
        self.assertEqual(parsed["PROJECT_NAME"], "systic")
        self.assertEqual(parsed["BUILD_TYPE"], "Debug")
        self.assertEqual(parsed["CONAN_PROFILE"], "clang21")
        self.assertEqual(parsed["CONAN_ENABLED"], "true")
        self.assertEqual(parsed["EMPTY_KEY"], "")
        self.assertNotIn("INVALID_LINE_WITHOUT_EQUALS", parsed)

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_defaults(self):
        # Without any .env file or env variables, standard defaults should apply
        parser = EnvironmentParser(self.test_dir / "empty.env")
        config = parser.load_config()
        self.assertEqual(config.project_name, "arrayslotthreadsafe")
        self.assertEqual(config.project_version, "0.1.0")
        self.assertEqual(config.conan_profile, "toolchains/clang21")
        self.assertEqual(config.build_type, "Release")
        self.assertEqual(config.target_profile, "targets/release")
        self.assertEqual(config.out_dir, Path(".build-release"))
        self.assertTrue(config.conan_enabled)
        self.assertEqual(config.conan_package_user, "default")
        self.assertEqual(config.conan_package_channel, "dev")

    @patch.dict(os.environ, {}, clear=True)
    def test_complete_valid_config(self):
        self.env_file.write_text(
            "PROJECT_NAME=systic\n"
            "PROJECT_VERSION=0.2.0\n"
            "BUILD_TYPE=Release\n"
            "CONAN_PROFILE=toolchains/clang21\n"
            "CONAN_ENABLED=1\n"
            "CONAN_REMOTE_NAME=laptop_server\n"
            "CONAN_REMOTE_URL=http://172.17.0.1:9300\n"
            "CONAN_LOGIN_USER=systic_user\n"
            "CONAN_LOGIN_PASSWORD=topsecret\n"
            "CONAN_PACKAGE_USER=systic\n"
            "CONAN_PACKAGE_CHANNEL=stable\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        config = parser.load_config()
        self.assertEqual(config.project_name, "systic")
        self.assertEqual(config.project_version, "0.2.0")
        self.assertEqual(config.build_type, "Release")
        self.assertEqual(config.conan_profile, "toolchains/clang21")
        self.assertEqual(config.target_profile, "targets/release")
        self.assertEqual(config.out_dir, Path(".build-release"))
        self.assertTrue(config.conan_enabled)
        self.assertEqual(config.conan_remote_name, "laptop_server")
        self.assertEqual(config.conan_remote_url, "http://172.17.0.1:9300")
        self.assertEqual(config.conan_login_user, "systic_user")
        self.assertEqual(config.conan_login_password, "topsecret")
        self.assertEqual(config.conan_package_user, "systic")
        self.assertEqual(config.conan_package_channel, "stable")

    @patch.dict(os.environ, {}, clear=True)
    def test_version_resolution_precedence(self):
        # 1. Fallback default
        parser = EnvironmentParser(self.env_file)
        self.assertEqual(parser.load_config().project_version, "0.1.0")

        # 2. VERSION in .env
        self.env_file.write_text("VERSION=1.0.0\n", encoding="utf-8")
        self.assertEqual(parser.load_config().project_version, "1.0.0")

        # 3. SYNAPSE_VERSION in .env overrides VERSION
        self.env_file.write_text("VERSION=1.0.0\nSYNAPSE_VERSION=2.0.0\n", encoding="utf-8")
        self.assertEqual(parser.load_config().project_version, "2.0.0")

        # 4. PROJECT_VERSION in .env overrides SYNAPSE_VERSION
        self.env_file.write_text(
            "VERSION=1.0.0\nSYNAPSE_VERSION=2.0.0\nPROJECT_VERSION=3.0.0\n", encoding="utf-8"
        )
        self.assertEqual(parser.load_config().project_version, "3.0.0")

        # 5. Explicit argument overrides everything
        self.assertEqual(parser.load_config(project_version="4.0.0").project_version, "4.0.0")

    @patch.dict(os.environ, {}, clear=True)
    def test_build_type_mapping(self):
        parser = EnvironmentParser(self.env_file)

        # debug -> Debug
        config_debug = parser.load_config(build_type="debug")
        self.assertEqual(config_debug.build_type, "Debug")
        self.assertEqual(config_debug.target_profile, "targets/debug")
        self.assertEqual(config_debug.out_dir, Path(".build-debug"))

        # relwithdebinfo -> RelWithDebInfo + auto-enable BUILD_TESTING & BUILD_BENCHMARKING
        config_rel = parser.load_config(build_type="RelWithDebInfo")
        self.assertEqual(config_rel.build_type, "RelWithDebInfo")
        self.assertEqual(config_rel.target_profile, "targets/relwithdebinfo")
        self.assertEqual(config_rel.out_dir, Path(".build-relwithdebinfo"))
        self.assertEqual(config_rel.cmake_args.get("BUILD_TESTING"), "ON")
        self.assertEqual(config_rel.cmake_args.get("BUILD_BENCHMARKING"), "ON")

    @patch.dict(os.environ, {}, clear=True)
    def test_relwithdebinfo_preserves_user_cmake_args(self):
        parser = EnvironmentParser(self.env_file)
        config = parser.load_config(
            build_type="relwithdebinfo",
            cmake_args={"BUILD_TESTING": "OFF", "CUSTOM_FLAG": "1"},
        )
        # Does not override explicitly passed BUILD_TESTING
        self.assertEqual(config.cmake_args["BUILD_TESTING"], "OFF")
        self.assertNotIn("BUILD_BENCHMARKING", config.cmake_args)
        self.assertEqual(config.cmake_args["CUSTOM_FLAG"], "1")

    @patch.dict(os.environ, {}, clear=True)
    def test_invalid_build_type_exits(self):
        parser = EnvironmentParser(self.env_file)
        with self.assertRaises(SystemExit) as cm:
            parser.load_config(build_type="invalid_type")
        self.assertEqual(cm.exception.code, 1)

    @patch.dict(os.environ, {}, clear=True)
    def test_custom_target_profile_and_out_dir(self):
        self.env_file.write_text(
            "TARGET_PROFILE=targets/test\n"
            "OUT_DIR=.build-custom-out\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        config = parser.load_config()
        self.assertEqual(config.target_profile, "targets/test")
        self.assertEqual(config.out_dir, Path(".build-custom-out"))

    @patch.dict(os.environ, {}, clear=True)
    def test_conan_enabled_parsing_variants(self):
        parser = EnvironmentParser(self.env_file)

        for val in ("true", "1", "on", "yes", "TRUE", "Yes"):
            self.env_file.write_text(f"CONAN_ENABLED={val}\n", encoding="utf-8")
            self.assertTrue(parser.load_config().conan_enabled)

        for val in ("false", "0", "off", "no", "FALSE", "No"):
            self.env_file.write_text(f"CONAN_ENABLED={val}\n", encoding="utf-8")
            self.assertFalse(parser.load_config().conan_enabled)

    @patch.dict(os.environ, {}, clear=True)
    def test_conan_remote_validation_missing_name(self):
        # conan_enabled + conan_remote_url without conan_remote_name must exit
        self.env_file.write_text(
            "CONAN_ENABLED=true\n"
            "CONAN_REMOTE_URL=http://172.17.0.1:9300\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        with self.assertRaises(SystemExit) as cm:
            parser.load_config()
        self.assertEqual(cm.exception.code, 1)

    @patch.dict(os.environ, {}, clear=True)
    def test_conan_disabled_bypasses_remote_check(self):
        # When conan is disabled, remote url without name does not raise SystemExit
        self.env_file.write_text(
            "CONAN_ENABLED=false\n"
            "CONAN_REMOTE_URL=http://172.17.0.1:9300\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        config = parser.load_config()
        self.assertFalse(config.conan_enabled)

    @patch.dict(os.environ, {}, clear=True)
    def test_cli_overrides_env_file(self):
        self.env_file.write_text(
            "PROJECT_NAME=systic\n"
            "BUILD_TYPE=Debug\n"
            "CONAN_PROFILE=gcc14\n"
            "CONAN_ENABLED=false\n",
            encoding="utf-8",
        )
        parser = EnvironmentParser(self.env_file)
        config = parser.load_config(
            profile="toolchains/clang21",
            target_profile="targets/clang21",
            build_type="RelWithDebInfo",
        )
        self.assertEqual(config.build_type, "RelWithDebInfo")
        self.assertEqual(config.conan_profile, "toolchains/clang21")
        self.assertEqual(config.target_profile, "targets/clang21")
        self.assertEqual(config.out_dir, Path(".build-clang21"))

    def test_os_environ_overrides_env_file(self):
        self.env_file.write_text("PROJECT_NAME=from_file\n", encoding="utf-8")
        with patch.dict(os.environ, {"PROJECT_NAME": "from_environ"}):
            parser = EnvironmentParser(self.env_file)
            config = parser.load_config()
            self.assertEqual(config.project_name, "from_environ")


class TestProcessRunner(unittest.TestCase):
    """Tests for low-level process execution wrapper."""

    @patch("subprocess.run")
    def test_run_success_list_command(self, mock_sub_run):
        mock_sub_run.return_value = subprocess.CompletedProcess(
            args=["cmake", "--version"], returncode=0, stdout="cmake version 3.28"
        )
        runner = ProcessRunner()
        result = runner.run(["cmake", "--version"], cwd=Path("/tmp"))
        self.assertEqual(result.returncode, 0)
        mock_sub_run.assert_called_once_with(
            ["cmake", "--version"],
            cwd="/tmp",
            env=None,
            check=True,
            capture_output=False,
            text=True,
            shell=False,
        )

    @patch("subprocess.run")
    def test_run_string_command_shell(self, mock_sub_run):
        mock_sub_run.return_value = subprocess.CompletedProcess(
            args="echo hi", returncode=0
        )
        runner = ProcessRunner()
        result = runner.run("echo hi", shell=True)
        self.assertEqual(result.returncode, 0)
        mock_sub_run.assert_called_once_with(
            "echo hi",
            cwd=None,
            env=None,
            check=True,
            capture_output=False,
            text=True,
            shell=True,
        )

    @patch("subprocess.run")
    def test_run_called_process_error(self, mock_sub_run):
        mock_sub_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd="make", stderr="Build failure"
        )
        runner = ProcessRunner()
        with self.assertRaises(subprocess.CalledProcessError):
            runner.run(["make"])

    @patch("subprocess.run")
    def test_run_file_not_found_error(self, mock_sub_run):
        mock_sub_run.side_effect = FileNotFoundError("Executable missing")
        runner = ProcessRunner()
        with self.assertRaises(FileNotFoundError):
            runner.run(["missing_binary"])

    def test_logging_helpers(self):
        # Ensure all logging helpers execute without exception
        ProcessRunner.log_step("Test Step", "ProjectX")
        ProcessRunner.log_info("Info message")
        ProcessRunner.log_success("Success message")
        ProcessRunner.log_warn("Warning message")
        ProcessRunner.log_error("Error message")


class TestLocalRunner(unittest.TestCase):
    """Tests for local phase and pipeline execution runner."""

    def setUp(self):
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        self.local_runner = LocalRunner(self.config)

    def test_run_phase(self):
        mock_builder = MagicMock()
        self.local_runner.run_phase("Phase 1", mock_builder)
        mock_builder.execute.assert_called_once()

    def test_run_pipeline(self):
        builder1 = MagicMock()
        builder2 = MagicMock()
        pipeline = [("Phase 1", builder1), ("Phase 2", builder2)]
        self.local_runner.run_pipeline(pipeline)
        builder1.execute.assert_called_once()
        builder2.execute.assert_called_once()


class TestOCIRunner(unittest.TestCase):
    """Tests for containerized OCI runtime driver."""

    def setUp(self):
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.which")
    def test_detect_oci_engine_docker(self, mock_which):
        mock_which.side_effect = lambda name: "/usr/bin/docker" if name == "docker" else None
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        self.assertEqual(runner.engine, "docker")

    @patch("shutil.which")
    def test_detect_oci_engine_podman(self, mock_which):
        mock_which.side_effect = lambda name: "/usr/bin/podman" if name == "podman" else None
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        self.assertEqual(runner.engine, "podman")

    @patch("shutil.which", return_value=None)
    def test_detect_oci_engine_missing_exits(self, _mock_which):
        with self.assertRaises(SystemExit) as cm:
            OCIRunner(self.config, workspace_dir=self.workspace)
        self.assertEqual(cm.exception.code, 1)

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_ensure_image_exists_image_present(self, mock_sub_run, _mock_which):
        mock_sub_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="sha256:12345\n"
        )
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        with patch.object(runner.runner, "run") as mock_runner_run:
            runner._ensure_image_exists()
            mock_runner_run.assert_not_called()

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_ensure_image_exists_builds_when_missing(self, mock_sub_run, _mock_which):
        mock_sub_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=""
        )
        # Create Dockerfile in workspace candidate directory
        dockerfile_dir = self.workspace / ".github" / "workflows"
        dockerfile_dir.mkdir(parents=True, exist_ok=True)
        (dockerfile_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        with patch.object(runner.runner, "run") as mock_runner_run:
            runner._ensure_image_exists()
            mock_runner_run.assert_called_once_with(
                ["docker", "build", "-t", "systic_build_image", str(dockerfile_dir)]
            )

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_ensure_image_exists_missing_dockerfile_exits(self, mock_sub_run, _mock_which):
        mock_sub_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=""
        )
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        with self.assertRaises(SystemExit) as cm:
            runner._ensure_image_exists()
        self.assertEqual(cm.exception.code, 1)

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_cleanup_stale_container(self, mock_sub_run, _mock_which):
        # 1st call detects existing container
        mock_sub_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="container_id\n"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout=""),
        ]
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        runner._cleanup_stale_container()
        self.assertEqual(mock_sub_run.call_count, 2)
        self.assertIn("rm", mock_sub_run.call_args_list[1][0][0])

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch.dict(os.environ, {"PROJECT_NAME": "systic", "BUILD_TYPE": "Release"})
    def test_execute_in_container(self, _mock_which):
        runner = OCIRunner(self.config, workspace_dir=self.workspace)
        with patch.object(runner, "_ensure_image_exists") as mock_ensure, \
             patch.object(runner, "_cleanup_stale_container") as mock_cleanup, \
             patch.object(runner.runner, "run") as mock_run:
            runner.execute_in_container(["--test"])
            mock_ensure.assert_called_once()
            self.assertGreaterEqual(mock_cleanup.call_count, 2)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "docker")
            self.assertEqual(cmd[1], "run")
            self.assertIn("systic_build_image", cmd)
            self.assertIn("--test", cmd)
            self.assertIn("-e", cmd)
            self.assertIn("PROJECT_NAME=systic", cmd)


class TestCMakePhaseBuilder(unittest.TestCase):
    """Tests for CMake phase configuration builder."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=self.out_dir,
            extra_flags=["-O3"],
            cmake_args={"ENABLE_AVX": "ON", "CMAKE_BUILD_TYPE": "Release"},
        )
        self.builder = CMakePhaseBuilder(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_toolchain_file_found(self):
        gen_dir = self.out_dir / "generators"
        gen_dir.mkdir(parents=True, exist_ok=True)
        toolchain = gen_dir / "conan_toolchain.cmake"
        toolchain.write_text("# toolchain", encoding="utf-8")

        resolved = self.builder._resolve_toolchain_file()
        self.assertEqual(resolved, toolchain)

    def test_resolve_toolchain_file_fallback(self):
        resolved = self.builder._resolve_toolchain_file()
        expected = self.out_dir / "build" / "Release" / "generators" / "conan_toolchain.cmake"
        self.assertEqual(resolved, expected)

    @patch("subprocess.run")
    def test_execute_success(self, mock_sub_run):
        toolchain = self.out_dir / "conan_toolchain.cmake"
        toolchain.write_text("# toolchain", encoding="utf-8")

        with patch.object(self.builder, "_resolve_toolchain_file", return_value=toolchain):
            self.builder.execute()

        mock_sub_run.assert_called_once()
        cmd = mock_sub_run.call_args[0][0]
        self.assertEqual(cmd[0], "cmake")
        self.assertIn("-G", cmd)
        self.assertIn("Ninja", cmd)
        self.assertIn(f"-DCMAKE_BUILD_TYPE={self.config.build_type}", cmd)
        self.assertIn(f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", cmd)
        self.assertIn("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", cmd)
        self.assertIn("-DENABLE_AVX=ON", cmd)

    def test_execute_missing_toolchain_exits(self):
        non_existent = self.out_dir / "non_existent.cmake"
        with patch.object(self.builder, "_resolve_toolchain_file", return_value=non_existent):
            with self.assertRaises(SystemExit) as cm:
                self.builder.execute()
            self.assertEqual(cm.exception.code, 1)


class TestCompilePhaseBuilder(unittest.TestCase):
    """Tests for multi-core compile phase builder."""

    @patch.object(ProcessRunner, "run")
    @patch("multiprocessing.cpu_count", return_value=12)
    def test_execute_parallel_jobs(self, _mock_cpus, mock_run):
        config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        builder = CompilePhaseBuilder(config)
        builder.execute()
        mock_run.assert_called_once_with(["cmake", "--build", ".build-release", "-j12"])


class TestConanPhaseBuilder(unittest.TestCase):
    """Tests for Conan dependency resolution phase builder."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=self.out_dir,
            conan_enabled=True,
            conan_remote_name="laptop_server",
            conan_remote_url="http://172.17.0.1:9300",
            conan_login_user="systic_user",
            conan_login_password="secret_password",
        )
        self.builder = ConanPhaseBuilder(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch.object(ProcessRunner, "run")
    def test_execute_conan_disabled_skips(self, mock_run):
        disabled_config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=self.out_dir,
            conan_enabled=False,
        )
        builder = ConanPhaseBuilder(disabled_config)
        builder.execute()
        mock_run.assert_not_called()

    @patch.object(ProcessRunner, "run")
    def test_execute_with_remote_and_profiles(self, mock_run):
        mock_toolchain = Path("/fake/toolchain")
        mock_target = Path("/fake/target")
        with patch.object(self.builder, "_ensure_conan_global_conf") as mock_conf, \
             patch.object(self.builder, "_get_active_profiles", return_value=(mock_toolchain, mock_target)), \
             patch.object(Path, "is_file", return_value=True):
            self.builder.execute()
            mock_conf.assert_called_once()
            self.assertEqual(mock_run.call_count, 3)

            # 1. remote add
            remote_add_cmd = mock_run.call_args_list[0][0][0]
            self.assertEqual(remote_add_cmd[0:3], ["conan", "remote", "add"])
            self.assertEqual(remote_add_cmd[3], "laptop_server")
            self.assertEqual(remote_add_cmd[4], "http://172.17.0.1:9300")

            # 2. remote login
            login_cmd = mock_run.call_args_list[1][0][0]
            self.assertEqual(login_cmd[0:3], ["conan", "remote", "login"])
            self.assertEqual(login_cmd[3], "laptop_server")
            self.assertEqual(login_cmd[4], "systic_user")

            # 3. conan install
            install_cmd = mock_run.call_args_list[2][0][0]
            self.assertEqual(install_cmd[0:2], ["conan", "install"])
            self.assertIn(f"-pr:b={mock_toolchain}", install_cmd)
            self.assertIn(f"-pr:h={mock_toolchain}", install_cmd)
            self.assertIn(f"-pr:h={mock_target}", install_cmd)
            self.assertIn("-s:h=build_type=Release", install_cmd)
            self.assertIn("CMakeDeps", install_cmd)
            self.assertIn("CMakeToolchain", install_cmd)

    def test_get_active_profiles_missing_exits(self):
        with patch.object(self.builder, "_resolve_profile", return_value=Path("/non_existent")):
            with self.assertRaises(SystemExit) as cm:
                self.builder._get_active_profiles()
            self.assertEqual(cm.exception.code, 1)

    def test_ensure_conan_global_conf(self):
        with tempfile.TemporaryDirectory() as temp_home:
            with patch("pathlib.Path.home", return_value=Path(temp_home)):
                self.builder._ensure_conan_global_conf()
                global_conf = Path(temp_home) / ".conan2" / "global.conf"
                self.assertTrue(global_conf.is_file())
                content = global_conf.read_text(encoding="utf-8")
                self.assertIn("tools.cmake.cmaketoolchain:generator=Ninja", content)


class TestPublishPhaseBuilder(unittest.TestCase):
    """Tests for Conan artifact packaging and publishing phase builder."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
            conan_enabled=True,
            conan_remote_name="laptop_server",
            conan_package_user="systic",
            conan_package_channel="stable",
        )
        self.builder = PublishPhaseBuilder(self.config, workspace_dir=self.workspace)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_execute_conan_disabled_exits(self):
        disabled_config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
            conan_enabled=False,
        )
        builder = PublishPhaseBuilder(disabled_config, workspace_dir=self.workspace)
        with self.assertRaises(SystemExit) as cm:
            builder.execute()
        self.assertEqual(cm.exception.code, 1)

    def test_get_package_metadata_from_config(self):
        pkg_name, pkg_version = self.builder._get_package_metadata()
        self.assertEqual(pkg_name, "systic")
        self.assertEqual(pkg_version, "0.1.0")

    def test_get_package_metadata_fallback_to_conanfile(self):
        no_name_config = SynapseConfig(
            project_name="",
            project_version="",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        synapse_dir = self.workspace / "synapse"
        synapse_dir.mkdir(parents=True, exist_ok=True)
        (synapse_dir / "conanfile.py").write_text(
            'name = "parsed_name"\nversion = "0.3.0"\n', encoding="utf-8"
        )
        builder = PublishPhaseBuilder(no_name_config, workspace_dir=self.workspace)
        pkg_name, pkg_version = builder._get_package_metadata()
        self.assertEqual(pkg_name, "parsed_name")
        self.assertEqual(pkg_version, "0.3.0")

    def test_get_package_metadata_missing_name_exits(self):
        no_name_config = SynapseConfig(
            project_name="",
            project_version="",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        builder = PublishPhaseBuilder(no_name_config, workspace_dir=self.workspace)
        with self.assertRaises(SystemExit) as cm:
            builder._get_package_metadata()
        self.assertEqual(cm.exception.code, 1)

    @patch.object(ProcessRunner, "run")
    def test_execute_publish_commands(self, mock_run):
        self.builder.execute()
        self.assertEqual(mock_run.call_count, 2)

        create_cmd = mock_run.call_args_list[0][0][0]
        self.assertEqual(create_cmd[0:2], ["conan", "create"])
        self.assertIn("-s", create_cmd)
        self.assertIn("build_type=Release", create_cmd)
        self.assertIn("--version=0.1.0", create_cmd)
        self.assertIn("--user=systic", create_cmd)
        self.assertIn("--channel=stable", create_cmd)

        upload_cmd = mock_run.call_args_list[1][0][0]
        self.assertEqual(upload_cmd[0:2], ["conan", "upload"])
        self.assertEqual(upload_cmd[2], "systic/0.1.0@systic/stable")
        self.assertIn("-r", upload_cmd)
        self.assertIn("laptop_server", upload_cmd)


class TestTestPhaseBuilder(unittest.TestCase):
    """Tests for GTest and Benchmark binary discovery and execution phase builder."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=self.out_dir,
        )
        self.builder = TestPhaseBuilder(self.config, workspace_dir=self.out_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_find_targets_and_executable_filtering(self):
        bin_dir = self.out_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        test_bin = bin_dir / "systic_tests"
        bench_bin = bin_dir / "systic_benchmarks"
        excluded_bin = self.out_dir / "CMakeFiles" / "internal_tests"
        non_exec_file = bin_dir / "readme_tests.txt"

        for p in (test_bin, bench_bin, excluded_bin, non_exec_file):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("dummy", encoding="utf-8")

        # Mock is_executable behavior: true for actual binaries, false for txt
        def mock_is_exec(path: Path) -> bool:
            if "CMakeFiles" in path.parts:
                return False
            return path.suffix != ".txt"

        with patch.object(self.builder, "_is_executable", side_effect=mock_is_exec):
            tests, benches = self.builder._find_targets()
            self.assertEqual(len(tests), 1)
            self.assertEqual(tests[0].name, "systic_tests")
            self.assertEqual(len(benches), 1)
            self.assertEqual(benches[0].name, "systic_benchmarks")

    @patch.object(ProcessRunner, "run")
    def test_execute_no_binaries_found_warns_and_returns(self, mock_run):
        with patch.object(self.builder, "_find_targets", return_value=([], [])):
            self.builder.execute()
            mock_run.assert_not_called()

    @patch.object(ProcessRunner, "run")
    def test_execute_runs_gtest_and_bench(self, mock_run):
        test_bin = self.out_dir / "bin" / "core_tests"
        bench_bin = self.out_dir / "bin" / "core_bench"
        with patch.object(self.builder, "_find_targets", return_value=([test_bin], [bench_bin])):
            self.builder.execute()
            self.assertEqual(mock_run.call_count, 2)

            gtest_cmd = mock_run.call_args_list[0][0][0]
            self.assertEqual(gtest_cmd[0], str(test_bin.resolve()))
            self.assertTrue(any(arg.startswith("--gtest_output=xml:") for arg in gtest_cmd))

            bench_cmd = mock_run.call_args_list[1][0][0]
            self.assertEqual(bench_cmd[0], str(bench_bin.resolve()))
            self.assertTrue(any(arg.startswith("--benchmark_out=") for arg in bench_cmd))
            self.assertIn("--benchmark_out_format=json", bench_cmd)

    @patch.object(ProcessRunner, "run", side_effect=Exception("Test crashed"))
    def test_execute_test_failure_exits(self, _mock_run):
        test_bin = self.out_dir / "failing_tests"
        with patch.object(self.builder, "_find_targets", return_value=([test_bin], [])):
            with self.assertRaises(SystemExit) as cm:
                self.builder.execute()
            self.assertEqual(cm.exception.code, 1)


class TestTidyPhaseBuilder(unittest.TestCase):
    """Tests for clang-tidy static analysis auto-remediation phase builder."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=self.workspace / ".build-release",
        )
        self.builder = TidyPhaseBuilder(self.config, workspace_dir=self.workspace)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.which", return_value=None)
    def test_execute_missing_clang_tidy_exits(self, _mock_which):
        with self.assertRaises(SystemExit) as cm:
            self.builder.execute()
        self.assertEqual(cm.exception.code, 1)

    def test_locate_or_generate_compile_commands_present(self):
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        compile_db = self.config.out_dir / "compile_commands.json"
        compile_db.write_text("[]", encoding="utf-8")

        resolved = self.builder._locate_or_generate_compile_commands()
        self.assertEqual(resolved, compile_db)

    @patch("synapse_engine.Builder.CMakePhaseBuilder.CMakePhaseBuilder.execute")
    def test_locate_or_generate_compile_commands_auto_triggers_cmake(self, mock_cmake_exec):
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        compile_db = self.config.out_dir / "compile_commands.json"

        def create_compile_db():
            compile_db.write_text("[]", encoding="utf-8")

        mock_cmake_exec.side_effect = create_compile_db

        resolved = self.builder._locate_or_generate_compile_commands()
        self.assertEqual(resolved, compile_db)
        mock_cmake_exec.assert_called_once()

    @patch("synapse_engine.Builder.CMakePhaseBuilder.CMakePhaseBuilder.execute")
    def test_locate_or_generate_compile_commands_fails_exits(self, mock_cmake_exec):
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        # compile_db remains missing even after CMakePhaseBuilder runs
        with self.assertRaises(SystemExit) as cm:
            self.builder._locate_or_generate_compile_commands()
        self.assertEqual(cm.exception.code, 1)

    def test_collect_source_files(self):
        src_file = self.workspace / "src" / "main.cpp"
        include_file = self.workspace / "include" / "main.hpp"
        ignored_file = self.workspace / "docs" / "readme.cpp"

        for f in (src_file, include_file, ignored_file):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("// test", encoding="utf-8")

        sources = self.builder._collect_source_files()
        self.assertEqual(sources, [include_file, src_file])

    @patch("shutil.which", return_value="/usr/bin/clang-tidy")
    @patch.object(ProcessRunner, "run")
    def test_execute_runs_clang_tidy_fix(self, mock_run, _mock_which):
        compile_db = self.config.out_dir / "compile_commands.json"
        source_file = self.workspace / "src" / "sample.cpp"

        with patch.object(self.builder, "_locate_or_generate_compile_commands", return_value=compile_db), \
             patch.object(self.builder, "_collect_source_files", return_value=[source_file]):
            self.builder.execute()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "/usr/bin/clang-tidy")
        self.assertIn(f"-p={compile_db.parent}", cmd)
        self.assertIn("--fix", cmd)
        self.assertIn("--fix-errors", cmd)
        self.assertIn(str(source_file), cmd)


class TestSynapseOrchestrator(unittest.TestCase):
    """Tests for high-level pipeline orchestration."""

    def setUp(self):
        self.config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="Release",
            conan_profile="toolchains/clang21",
            target_profile="targets/release",
            out_dir=Path(".build-release"),
        )
        self.orchestrator = SynapseOrchestrator(self.config)

    @patch("synapse_engine.Runner.LocalRunner.LocalRunner.run_phase")
    def test_default_pipeline_execution(self, mock_run_phase):
        self.orchestrator.run(run_test=False, run_fix=False, run_publish=False)
        self.assertEqual(mock_run_phase.call_count, 3)
        phase_names = [call_args[0][0] for call_args in mock_run_phase.call_args_list]
        self.assertEqual(phase_names, ["Conan Resolution", "CMake Configuration", "Compilation"])

    @patch("synapse_engine.Runner.LocalRunner.LocalRunner.run_phase")
    def test_fix_runs_tidy_and_returns_early(self, mock_run_phase):
        self.orchestrator.run(run_fix=True)
        self.assertEqual(mock_run_phase.call_count, 1)
        phase_name = mock_run_phase.call_args[0][0]
        self.assertEqual(phase_name, "Clang-Tidy Fix")

    @patch("synapse_engine.Runner.LocalRunner.LocalRunner.run_phase")
    def test_test_flag_triggers_testing_phase(self, mock_run_phase):
        self.orchestrator.run(run_test=True)
        self.assertEqual(mock_run_phase.call_count, 4)
        phase_names = [call_args[0][0] for call_args in mock_run_phase.call_args_list]
        self.assertEqual(
            phase_names,
            ["Conan Resolution", "CMake Configuration", "Compilation", "Testing & Benchmarking"],
        )

    @patch("synapse_engine.Runner.LocalRunner.LocalRunner.run_phase")
    def test_relwithdebinfo_auto_triggers_testing_phase(self, mock_run_phase):
        debug_config = SynapseConfig(
            project_name="systic",
            project_version="0.1.0",
            build_type="RelWithDebInfo",
            conan_profile="toolchains/clang21",
            target_profile="targets/relwithdebinfo",
            out_dir=Path(".build-relwithdebinfo"),
        )
        orchestrator = SynapseOrchestrator(debug_config)
        orchestrator.run(run_test=False)
        self.assertEqual(mock_run_phase.call_count, 4)
        phase_names = [call_args[0][0] for call_args in mock_run_phase.call_args_list]
        self.assertIn("Testing & Benchmarking", phase_names)

    @patch("synapse_engine.Runner.LocalRunner.LocalRunner.run_phase")
    def test_publish_flag_triggers_publish_phase(self, mock_run_phase):
        self.orchestrator.run(run_publish=True)
        self.assertEqual(mock_run_phase.call_count, 4)
        phase_names = [call_args[0][0] for call_args in mock_run_phase.call_args_list]
        self.assertEqual(
            phase_names,
            ["Conan Resolution", "CMake Configuration", "Compilation", "Package & Publish"],
        )


class TestCLI(unittest.TestCase):
    """Tests for synapse CLI entrypoint parsing and dispatch."""

    @patch.object(SynapseOrchestrator, "run")
    @patch.object(EnvironmentParser, "load_config")
    def test_main_cli_dispatch(self, mock_load_config, mock_orch_run):
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        test_args = [
            "synapse",
            "--profile",
            "toolchains/clang21",
            "--type",
            "Debug",
            "--test",
            "--env-file",
            ".env.custom",
        ]

        with patch.object(sys, "argv", test_args):
            synapse.main()

        mock_load_config.assert_called_once_with(
            profile="toolchains/clang21",
            build_type="Debug",
        )
        mock_orch_run.assert_called_once_with(
            run_test=True,
            run_fix=False,
            run_publish=False,
        )

    @patch.object(SynapseOrchestrator, "run")
    @patch.object(EnvironmentParser, "load_config")
    def test_main_cli_defaults(self, mock_load_config, mock_orch_run):
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["synapse"]):
            synapse.main()

        mock_load_config.assert_called_once_with(
            profile=None,
            build_type=None,
        )
        mock_orch_run.assert_called_once_with(
            run_test=False,
            run_fix=False,
            run_publish=False,
        )

    @patch.object(SynapseOrchestrator, "run")
    @patch.object(EnvironmentParser, "load_config")
    def test_main_cli_dispatch_fix(self, mock_load_config, mock_orch_run):
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["synapse", "--fix"]):
            synapse.main()

        mock_orch_run.assert_called_once_with(
            run_test=False,
            run_fix=True,
            run_publish=False,
        )

    @patch.object(SynapseOrchestrator, "run")
    @patch.object(EnvironmentParser, "load_config")
    def test_main_cli_dispatch_publish(self, mock_load_config, mock_orch_run):
        mock_config = MagicMock()
        mock_load_config.return_value = mock_config

        with patch.object(sys, "argv", ["synapse", "--publish"]):
            synapse.main()

        mock_orch_run.assert_called_once_with(
            run_test=False,
            run_fix=False,
            run_publish=True,
        )


if __name__ == "__main__":
    unittest.main()

