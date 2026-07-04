FROM python:3.12-slim

WORKDIR /srv/petjourney

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 运行时数据（sqlite + 上传文件）挂载到卷，见 docker-compose.yml
RUN mkdir -p data/uploads

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
