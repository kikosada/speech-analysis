FROM python:3.9-slim

# Instala dependencias del sistema necesarias para Azure Speech SDK y ffmpeg
RUN apt-get update && apt-get install -y \
    libstdc++6 \
    libgcc1 \
    libasound2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instala dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código
COPY . .

# Expone el puerto
EXPOSE 10000

# Comando de inicio
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"] 