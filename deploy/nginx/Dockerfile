# 공식 Nginx에 동일 네트워크 readiness 검사에 필요한 curl만 추가한다.
FROM nginx:1.30.6-alpine3.24
RUN apk add --no-cache curl
ENTRYPOINT ["nginx"]
CMD ["-c", "/etc/nginx/runtime/active.conf", "-g", "daemon off;"]
