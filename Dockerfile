FROM python:3.12


# 
WORKDIR /code

# 
COPY ./requirements.txt /code/requirements.txt

# 
RUN pip install --no-cache-dir -r requirements.txt

# 
COPY ./app /code/app

ENV PYTHONPATH=/code
ENV PYTHONDONTWRITEBYTECODE=1
