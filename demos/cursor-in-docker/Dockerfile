FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl bash \
    && rm -rf /var/lib/apt/lists/*

# The installer detects linux/arm64 (or linux/x64) inside the build and
# downloads that package. The macOS CLI cannot be copied in instead.
RUN curl https://cursor.com/install -fsS | bash

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /work

# Stay up so the demo can exec into the container. Auth is supplied at run time.
CMD ["sleep", "infinity"]
