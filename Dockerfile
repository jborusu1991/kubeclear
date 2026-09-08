
FROM python:3.12-slim AS builder

WORKDIR /build


RUN pip install --no-cache-dir poetry==2.4.3

ENV POETRY_VIRTUALENVS_IN_PROJECT=true

COPY pyproject.toml poetry.lock* ./


RUN poetry install --no-root --only main

COPY README.md ./
COPY kubeclear ./kubeclear

RUN poetry build --format wheel --output /dist

RUN pip install --no-cache-dir \
    --prefix=/install \
    --no-deps \
    /dist/*.whl

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 kubeclear

COPY --from=builder /build/.venv /opt/venv
COPY --from=builder /install /usr/local

ENV PATH="/opt/venv/bin:$PATH"

USER kubeclear
WORKDIR /home/kubeclear

ENTRYPOINT ["kubeclear"]
CMD ["--help"]