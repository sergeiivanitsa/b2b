FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS release
COPY .github/ci/python-bootstrap.lock /locks/python-bootstrap.lock
COPY .github/ci/python-gateway-runtime.lock /locks/python-runtime.lock
COPY .release/gateway/wheelhouse/ /wheelhouse/
COPY .release/gateway/gateway_api-0.1.0-py3-none-any.whl /wheelhouse/gateway_api-0.1.0-py3-none-any.whl
COPY .release/gateway/project-wheel.sha256 /wheelhouse/project-wheel.sha256
COPY shared /app/shared
RUN cd /wheelhouse \
    && sha256sum -c wheelhouse.sha256 \
    && sha256sum -c project-wheel.sha256 \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps --only-binary=:all: --require-hashes -r /locks/python-bootstrap.lock \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps --only-binary=:all: --require-hashes -r /locks/python-runtime.lock \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps /wheelhouse/gateway_api-0.1.0-py3-none-any.whl \
    && python -m pip check \
    && python -c "import importlib.metadata as m,json; rows=sorted((d.metadata['Name'].lower().replace('_','-'),d.version) for d in m.distributions()); open('/app/python-installed.json','w',encoding='utf-8',newline='\n').write(json.dumps(rows,separators=(',',':'))+'\n')" \
    && python -c "import gateway_api.main" \
    && rm -rf /wheelhouse /locks

EXPOSE 8001
CMD ["uvicorn", "gateway_api.main:app", "--host", "0.0.0.0", "--port", "8001"]

FROM base AS local
COPY .github/ci/python-bootstrap.lock /locks/python-bootstrap.lock
COPY .github/ci/python-gateway-runtime.lock /locks/python-runtime.lock
COPY services/gateway_api /app/services/gateway_api
COPY shared /app/shared
RUN python -m pip install --no-deps --only-binary=:all: --require-hashes -r /locks/python-bootstrap.lock \
    && python -m pip install --no-deps --only-binary=:all: --require-hashes -r /locks/python-runtime.lock \
    && python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/local-wheel /app/services/gateway_api \
    && python -m pip install --no-index --find-links=/tmp/local-wheel --no-deps /tmp/local-wheel/gateway_api-0.1.0-py3-none-any.whl \
    && python -m pip check \
    && rm -rf /tmp/local-wheel /locks /app/services/gateway_api

EXPOSE 8001
CMD ["uvicorn", "gateway_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
