#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys

from synapse_engine.Environment.EnvironmentParser import EnvironmentParser
from synapse_engine.SynapseOrchestrator import SynapseOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="synapse",
        description="Synapse - Modern Zero-Overhead Build System Orchestrator & OCI Execution Driver",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Conan profile located in .conan/profiles/ (e.g., clang21)",
    )
    parser.add_argument(
        "--type",
        type=str,
        default=None,
        help="C++ compilation target type (Release, Debug, RelWithDebInfo)",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Execute GTest test suites and Google Benchmark targets",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Run clang-tidy auto-remediation across source and include directories",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Package artifact with Conan create and publish upstream to remote registry",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to environment definition file (default: .env)",
    )

    args = parser.parse_args()

    # Parse and validate environment and configuration
    env_parser = EnvironmentParser(env_path=args.env_file)
    config = env_parser.load_config(
        profile=args.profile,
        build_type=args.type,
    )

    # Initialize and run orchestrator
    orchestrator = SynapseOrchestrator(config)
    orchestrator.run(
        run_test=args.test,
        run_fix=args.fix,
        run_publish=args.publish
    )


if __name__ == "__main__":
    main()
