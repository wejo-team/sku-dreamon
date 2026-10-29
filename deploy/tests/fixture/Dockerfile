# 테스트 파생 이미지에만 가상 driver를 넣고 제품 이미지는 그대로 보존한다.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN cp /opt/app/app/main.py /opt/app/app/product_main.py
COPY fixture_app.py /opt/app/app/main.py
COPY guard.py /opt/app/app/fixture_guard.py
ARG FAIL_READY=0
ENV DEP03_CONTAINER_E2E=1 DEP03_READY_FAIL=${FAIL_READY}
USER 10001:10001
