FROM nginx:1.30.6-alpine
COPY nginx.conf.template /opt/aiced/nginx.conf.template
COPY start.sh /opt/aiced/start.sh
RUN mkdir -p /opt/aiced/logs /opt/aiced/temp/client /opt/aiced/temp/proxy \
    && chown -R nginx:nginx /opt/aiced
USER nginx
WORKDIR /opt/aiced
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/opt/aiced/start.sh"]
