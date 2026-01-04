ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QML_DISABLE_DISK_CACHE=1

WORKDIR /app

# Runtime libraries for Qt/PySide6 and OpenGL consumers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon0 \
    libxcb1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

ARG INSTALL_TORCH=1

RUN python -m pip install --upgrade pip \
 && if [ "${INSTALL_TORCH}" = "0" ]; then \
      python - <<'PY' \
from pathlib import Path
src = Path("requirements.txt").read_text().splitlines()
dst = [line for line in src if not line.startswith(("torch==", "torchvision=="))]
Path("/tmp/requirements.notorch.txt").write_text("\n".join(dst) + "\n")
PY
      && pip install --no-cache-dir -r /tmp/requirements.notorch.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

EXPOSE 8000

# Launch the REST API. Adjust the command if you want the GUI entrypoint instead.
CMD ["uvicorn", "fire_uav.api.main_rest:app", "--host", "0.0.0.0", "--port", "8000"]
