FROM python:3.11-slim

# Configuración del entorno de Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar herramientas del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el proyecto al contenedor
COPY . .

# Puerto expuesto por defecto
EXPOSE 8000

# Comando por defecto si no se usa Procfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
