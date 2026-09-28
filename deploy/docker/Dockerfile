FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

COPY pyproject.toml README.md ./
COPY config ./config
COPY apps ./apps
COPY manage.py ./

RUN python -m pip install --upgrade pip \
    && python -m pip install .

COPY . .

# Il processo applicativo non deve girare come root. Le directory runtime
# restano scrivibili dall'utente applicativo e mantengono ownership corretta
# anche quando vengono inizializzati i named volume Docker.
RUN groupadd --gid "${APP_GID}" nokihub \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home nokihub \
    && mkdir -p /app/staticfiles /app/media /app/private_media \
    && chown -R nokihub:nokihub /app/staticfiles /app/media /app/private_media \
    && chown -R nokihub:nokihub /home/nokihub

USER nokihub

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
