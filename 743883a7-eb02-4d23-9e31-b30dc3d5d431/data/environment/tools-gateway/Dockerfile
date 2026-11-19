FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app
WORKDIR /app
COPY requirements-locked.txt /app/requirements-locked.txt
RUN pip install --no-cache-dir --require-hashes -r /app/requirements-locked.txt
COPY tools_gateway /app/tools_gateway
RUN mkdir -p /var/wcb/usage /var/wcb/pages && chown -R app:app /app /var/wcb
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WCB_TOOLS_PORT=8790
EXPOSE 8790
USER app
CMD ["python", "-m", "tools_gateway"]
