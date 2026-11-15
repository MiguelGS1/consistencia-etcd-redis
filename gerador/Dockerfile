# Imagem do contêiner gerador: Python 3.12 com as bibliotecas já instaladas.
# É construída uma vez e fica no cache do Docker, então subir o cluster de novo
# (down -v / up -d) não precisa de internet. O código continua vindo do volume ./gerador -> /app.
FROM python:3.12-slim
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /app
