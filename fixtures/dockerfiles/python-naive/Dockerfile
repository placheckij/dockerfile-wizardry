# Bad on purpose: a first-draft Python image. The rules it breaks are listed in
# expected-findings.txt next to this file. Linted only, never built.
FROM python:latest

# a token as a build argument ends up in the image metadata (no value here, so the
# repository's secret scan has nothing to find)
ARG API_TOKEN

WORKDIR /app
ADD . /app
RUN pip install -r requirements.txt

EXPOSE 8000
CMD python app.py
