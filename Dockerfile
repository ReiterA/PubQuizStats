FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    MPLBACKEND=Agg

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer fonts-dejavu fonts-liberation \
        libegl1 libgl1 libglib2.0-0 libfontconfig1 libdbus-1-3 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m app && mkdir -p /app/data && chown -R app /app/data
USER app

EXPOSE 8765
CMD ["python", "main.py", "--host", "0.0.0.0", "--no-browser"]
