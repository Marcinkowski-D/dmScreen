# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:debian

# Fast Python, predictable uv, and a fixed cache path you can mount from the host
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/uv-cache \
    UV_PYTHON_PREFERENCE=only-managed

# (Optional but handy) Runtime libs for Pillow, plus git for hatch-vcs versioning, tini for signals
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates tini \
      libjpeg62-turbo libpng16-16 zlib1g libtiff6 libopenjp2-7 libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Create the uv cache dir (will usually be bind-mounted)
RUN mkdir -p /uv-cache && chmod 777 /uv-cache
VOLUME ["/uv-cache"]

# Your code will be bind-mounted to /app
WORKDIR /app

# Container listens on 80 (map 8900:80 on the host)
EXPOSE 80

CMD ["/bin/bash","run_docker.sh"]
