FROM python:3.12-slim

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY . .

CMD ["python", "main.py"]