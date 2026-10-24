FROM python:3.12-slim

# tzdata: the slim image has no time zone database, and the config's
# location.timezone needs one.
WORKDIR /app
COPY pyproject.toml README.md ./
COPY weather_provider ./weather_provider
RUN pip install --no-cache-dir tzdata . && rm -rf /root/.cache

# Settings and coastline live in the /config volume (see docker-compose.yml).
ENV WEATHER_PROVIDER_CONFIG=/config/config.toml \
    PYTHONUNBUFFERED=1
VOLUME /config
ENTRYPOINT ["python", "-m", "weather_provider"]
