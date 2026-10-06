FROM ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-venv python3-dev python3-opencv g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/fly-requirements.txt
RUN python3 -m venv --system-site-packages /opt/fly-env \
    && /opt/fly-env/bin/pip install --no-cache-dir -r /tmp/fly-requirements.txt
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
WORKDIR /fly
