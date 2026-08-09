FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY brandos ./brandos

# No CMD by default — this container is invoked on-demand by the
# scheduler (docker compose exec app python -m brandos.run_digest),
# not run as a long-lived process. Keeps it simple: one job, one exit code.
CMD ["python", "-m", "brandos.run_digest"]
