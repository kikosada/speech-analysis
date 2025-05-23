FROM python:3.9-slim

# Instala dependencias del sistema necesarias para ffmpeg
RUN apt-get update && apt-get install -y \
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
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "600"] 