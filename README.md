# Synapse
> This README and parts of this project's scaffolding were generated with AI assistance.
> 
Python build orchestrator for C++ projects. Runs Conan → CMake → Compile → Test → Tidy → Publish as containerized pipeline phases, so the host machine only needs Docker/Podman — no compiler, no CMake, no Conan, no Python deps installed locally.

## When to use this

- You maintain multiple C++ projects and want identical build/test/tidy/publish behavior across all of them without duplicating CI config per repo.
- You want builds to run identically on any machine (dev laptop, CI runner) regardless of installed toolchain versions.
- You don't need this if you have a single C++ project — a plain `CMakeLists.txt` + `CMakePresets.json` + one CI workflow will do the job with less overhead.

## Requirements

- Docker or Podman on the host. Nothing else.

## Directory structure
```
synapse_engine/
├── Environment/
│ ├── SynapseConfig.py
│ └── EnvironmentParser.py
├── Builder/
│ ├── ConanPhaseBuilder.py
│ ├── CMakePhaseBuilder.py
│ ├── CompilePhaseBuilder.py
│ ├── TestPhaseBuilder.py
│ ├── TidyPhaseBuilder.py
│ └── PublishPhaseBuilder.py
├── Runner/
│ ├── ProcessRunner.py
│ ├── LocalRunner.py
│ └── OCIRunner.py
└── SynapseOrchestrator.py
.github/workflows/
└── Dockerfile
.conan/profiles/toolchains
└──profiles (debug, relwithdebinfo, release)
└──toolchains (clang21)
.example.env
pyproject.toml
synapse.py
```


## Usage

**1. Configure**
```bash
cp .example.env .env
```

**2. Run**
```bash
./synapse.py
```
This builds `${PROJECT_NAME}_build_image` if missing, then runs Conan install, CMake generation, and compilation inside the container.

**3. Options**
```bash
./synapse.py --help
```

| Flag | Description | Default |
|---|---|---|
| `--profile PROFILE` | Conan profile from `.conan/profiles/` | `debug` |
| `--type TYPE` | Build type: `Release`, `Debug`, `RelWithDebInfo` | `Release` |
| `--test` | Run GTest/Google Benchmark suites in-container | off |
| `--fix` | Run `clang-tidy --fix` in-container | off |
| `--publish` | `conan create` + upload to Conan remote | off |
| `--env-file ENV_FILE` | Path to custom env file | `.env` |