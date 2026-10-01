FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        rsyslog \
        iproute2 \
        iptables \
        procps \
        python3 \
        ca-certificates \
        net-tools \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/remote

COPY rsyslog/rsyslog.conf /etc/rsyslog.conf
COPY scripts/setup-lvs-dr.sh /usr/local/bin/setup-lvs-dr.sh
COPY scripts/99-lvs-dr.conf /etc/sysctl.d/99-lvs-dr.conf
COPY scripts/entrypoint-hf.sh /entrypoint.sh

RUN chmod +x /usr/local/bin/setup-lvs-dr.sh /entrypoint.sh

EXPOSE 514/tcp 514/udp

VOLUME ["/var/log/remote"]

ENTRYPOINT ["/entrypoint.sh"]
