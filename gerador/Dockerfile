# Imagem do contêiner gerador: Python 3.12 com as bibliotecas já instaladas.
# É construída uma vez e fica no cache do Docker, então subir o cluster de novo
# (down -v / up -d) não precisa de internet. O código continua vindo do volume ./gerador -> /app.
# Mesma base do compose da professora (python:3.12-slim)
FROM python:3.12-slim
# Copia só a lista de bibliotecas e instala (sem guardar o cache do pip, para a imagem ficar menor)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
# Pasta em que o compose monta o código (./gerador -> /app)
WORKDIR /app
