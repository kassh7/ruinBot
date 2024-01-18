FROM python:3.12

RUN apt -y update && apt -y upgrade
ADD ./requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
ADD . /app
RUN mkdir -p /app/usr

CMD [ "python", "main.py" ]