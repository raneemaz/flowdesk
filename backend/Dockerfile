# FD-065 (production deployment). Not verified by a local `docker build`
# in this project's own dev environment (no Docker available there) -
# verified for real against Render's own build logs during the actual
# guided deployment; see backend/README.md's Deployment section.
FROM python:3.12-slim

# WeasyPrint (FD-045 invoice PDFs) needs a system GTK3 runtime
# (Pango/Cairo/GDK-Pixbuf) that pip cannot provide on its own - the
# exact same requirement backend/README.md's "PDF generation (FD-045)
# on Windows" section documents for local dev, via MSYS2 there instead
# of apt here. Package list per WeasyPrint's own documented Debian
# dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies in their own layer, before the rest of the source, so a
# source-only change doesn't invalidate pip's install cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production
EXPOSE 10000

# Migrations run as a separate step (Render's own "pre-deploy command",
# set to `flask --app wsgi db upgrade` - see backend/README.md), not
# baked into this CMD: running it once per deploy rather than once per
# container/worker avoids every instance racing to migrate
# simultaneously if this service is ever scaled beyond one instance.
# Shell form (not exec-array form) so ${PORT} - set dynamically by
# Render - actually expands; Render defaults to 10000 if unset, but
# every platform's own assigned port should always be respected over a
# hardcoded one.
CMD gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 60 wsgi:app
