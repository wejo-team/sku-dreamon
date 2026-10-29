# 데이터 장치 신원 검사를 공식 PostgreSQL 시작보다 먼저 수행한다.
FROM postgres:17.11-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/postgres/guard-entrypoint.sh deploy/postgres/check-identity.sh /usr/local/bin/
COPY deploy/postgres/init-roles.sh /docker-entrypoint-initdb.d/10-roles.sh
COPY deploy/postgres/postgresql.conf deploy/postgres/pg_hba.conf /etc/postgresql/
RUN chmod 755 /usr/local/bin/guard-entrypoint.sh /usr/local/bin/check-identity.sh \
    /docker-entrypoint-initdb.d/10-roles.sh
ENTRYPOINT ["/usr/local/bin/guard-entrypoint.sh"]
CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
