FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        keepalived \
        haproxy \
        ipvsadm \
        iptables \
        iproute2 \
        procps \
        curl \
        python3 \
        python3-yaml \
        ca-certificates \
        net-tools \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/keepalived/conf.d \
               /etc/syslog-pin \
               /var/lib/syslog-pin \
               /usr/lib/keepalived \
               /data

COPY keepalived/fwmark-pins.conf /etc/keepalived/conf.d/fwmark-pins.conf
COPY scripts/check_haproxy.sh /usr/lib/keepalived/check_haproxy.sh
COPY haproxy/haproxy.cfg /etc/haproxy/haproxy.cfg
COPY scripts/entrypoint-lb.sh /entrypoint.sh

RUN chmod +x /usr/lib/keepalived/check_haproxy.sh /entrypoint.sh \
    && mkdir -p /run/haproxy

EXPOSE 514/tcp 514/udp 8404/tcp

ENTRYPOINT ["/entrypoint.sh"]
