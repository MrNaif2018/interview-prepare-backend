FROM python:3.11-slim-bookworm

ENV IN_DOCKER=1

COPY . /app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential python3-dev && \
    groupadd --gid 1000 interviewprepare && \
    useradd --uid 1000 --gid interviewprepare --shell /bin/bash --create-home interviewprepare && \
    pip install -r requirements.txt && \
    apt-get purge -y build-essential python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /root/.cache/pip
ENV PYTHONUNBUFFERED=1
USER interviewprepare
CMD ["sh"]
