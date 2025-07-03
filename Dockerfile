FROM python:3.9-slim

# 1) install ffmpeg + fontconfig
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
      fontconfig && \
    rm -rf /var/lib/apt/lists/*

# 2) copy & register your custom fonts (optional - subtitle fonts take precedence now)
COPY fonts/ /usr/local/share/fonts/
RUN fc-cache -fv

# 3) bring in the app
WORKDIR /app
COPY . /app

# 4) install Python deps
RUN pip3 install --no-cache-dir -r requirements.txt

CMD ["python3", "muxbot.py"]
