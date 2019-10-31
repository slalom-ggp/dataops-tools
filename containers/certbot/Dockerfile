FROM ubuntu:18.04


# Install certbot to create SSH certs (https://certbot.eff.org/lets-encrypt/ubuntubionic-other)
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository universe && \
    add-apt-repository ppa:certbot/certbot && \
    apt-get update \
    apt-get install -y certbot

