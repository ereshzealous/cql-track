FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY cqltrack/ cqltrack/
RUN pip install --no-cache-dir .

FROM python:3.13-slim

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/cqltrack /usr/local/bin/cqltrack

WORKDIR /workspace
ENTRYPOINT ["cqltrack"]
