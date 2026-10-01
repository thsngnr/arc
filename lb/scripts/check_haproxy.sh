#!/bin/bash
# HAProxy canlı mı?
pidof haproxy >/dev/null 2>&1
exit $?
