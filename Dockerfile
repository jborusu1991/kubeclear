FROM python:3.12-slim AS builder

WORKDIR /build


RUN pip install --no-cache-dir --upgrade pip "setuptools>=84.0.0" "msgpack>=1.2.2" \
    && pip install --no-cache-dir poetry==2.4.3

COPY pyproject.toml poetry.lock* README.md ./
COPY kubeclear ./kubeclear


RUN poetry build --format wheel --output /dist


RUN pip install --no-cache-dir \
    --prefix=/install \
    --ignore-installed \
    "setuptools>=84.0.0" "msgpack>=1.2.2" \
    /dist/*.whl

RUN find /install -name "bom.cdx.json" -delete


FROM python:3.12-slim


RUN useradd --create-home --uid 1000 kubeclear


COPY --from=builder /install /usr/local

USER kubeclear
WORKDIR /home/kubeclear

ENTRYPOINT ["kubeclear"]
CMD ["--help"]
