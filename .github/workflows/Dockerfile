FROM python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential clang clang-tidy clang-format cmake ninja-build git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir conan==2.*

# --- Synapse lives baked into the image, NOT mounted ---
WORKDIR /workspace
COPY pyproject.toml ./
COPY synapse_engine ./synapse_engine
COPY synapse.py ./synapse.py
COPY .conan ./.conan
RUN pip install --no-cache-dir .

# --- The C++ project being built gets mounted here instead ---
WORKDIR /project

ENTRYPOINT ["synapse"]