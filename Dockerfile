
FROM ubuntu:latest
RUN apt-get update -y && apt-get install -y python-boto python-flask && apt-get clean
COPY app.py /opt
WORKDIR /opt
ENTRYPOINT ["python"]
CMD ["app.py"]

