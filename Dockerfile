FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd --gid 1000 app && \
    useradd --uid 1000 --gid 1000 --no-create-home app
COPY --chown=1000:1000 certificados ./certificados
COPY --chown=1000:1000 config ./config
COPY --chown=1000:1000 gestion ./gestion
COPY --chown=1000:1000 templates ./templates
COPY --chown=1000:1000 assets ./assets
COPY --chown=1000:1000 scripts ./scripts
COPY --chown=1000:1000 tests ./tests
COPY --chown=1000:1000 manage.py ./
USER 1000:1000
EXPOSE 8080
CMD ["sh", "scripts/entrypoint.sh"]
