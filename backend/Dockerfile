# syntax=docker/dockerfile:1

# Production image for the Django API: Gunicorn, running as a non-root user.
#   docker build --target runtime -t shipscope-backend:prod backend
# The :prod tag keeps this build apart from shipscope-backend:latest, the image Compose
# builds and runs.
# The builder stage installs the locked dependencies into /opt/venv. The runtime stage
# copies in only that virtualenv and the app code.

# Both stages use this image, because the virtualenv's python is a symlink to the
# image's interpreter. The tag names the Debian release, so moving to the next one is
# a deliberate change.
ARG PYTHON_IMAGE=python:3.14-slim-trixie

FROM ${PYTHON_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv

# UV_COMPILE_BYTECODE: compile .pyc files now. The runtime user can't write them into
#   /opt/venv, so without this every process would recompile its imports at startup.
# UV_LINK_MODE: copy packages out of the cache mount, which is a separate filesystem
#   and can't be hardlinked.
# UV_PYTHON_DOWNLOADS: use the image's Python, the only one the runtime stage has.
# UV_PROJECT_ENVIRONMENT: install outside /app, so a bind mount over /app can't hide it.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Mount only the two dependency files, so this layer is rebuilt when they change and
# reused when only code changes. --locked fails the build if uv.lock doesn't match
# pyproject.toml. The cache mount speeds up rebuilds and never ends up in the image.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev


FROM ${PYTHON_IMAGE} AS runtime

# Run python and gunicorn from the virtualenv, don't try to write .pyc files next to
# code the app user can't modify, and send output to the container log unbuffered.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# An unprivileged user with a fixed, high ID that's unlikely to belong to a host account.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Copied as root, so the app user can read the code but not change it.
COPY . .

# WhiteNoise serves the collected files (Django admin, DRF's browsable API). Settings
# require these two variables; the placeholders exist only for this command.
RUN DJANGO_SECRET_KEY=build-only POSTGRES_PASSWORD=build-only \
    python manage.py collectstatic --noinput

USER app

EXPOSE 8000

# Exec form, so Gunicorn runs as PID 1 and receives the SIGTERM from `docker stop` or
# ECS itself, finishing in-flight requests before it exits. The worker count comes from
# WEB_CONCURRENCY, which Gunicorn reads (1 when unset).
#   --bind 0.0.0.0:8000   listen on all interfaces; the default, 127.0.0.1, can't be
#                         reached from outside the container
#   --access-logfile -    write access logs to stdout
#   --worker-tmp-dir      keep the worker heartbeat file in memory; Gunicorn warns that
#                         a disk-backed temp directory can stall workers
#   --no-control-socket   skip the socket for managing Gunicorn by hand: the platform
#                         manages the process, and the app user has no home directory
#                         to create the socket in
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--access-logfile", "-", \
     "--worker-tmp-dir", "/dev/shm", "--no-control-socket"]
