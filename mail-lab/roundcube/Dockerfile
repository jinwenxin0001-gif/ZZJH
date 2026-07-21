FROM roundcube/roundcubemail:1.6.x-apache

USER root
COPY certs/ca/zzjh-mail-lab-ca.crt /usr/local/share/ca-certificates/zzjh-mail-lab-ca.crt
RUN update-ca-certificates
