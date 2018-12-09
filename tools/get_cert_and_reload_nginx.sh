#!/bin/bash
# Downloading cert from S3 ,to /etc/nginx/ssl/ and reload nginx.
# 1. Rename old cert to .bak.
# 2. Downloading cert named .tmp from S3.
# 3. Remove the name .tmp.
# 4. Reload nginx.

set -e

CMDNAME=$(basename "$0")

myhelp() {
    echo "Usage: $CMDNAME -b BUCKET -d DOMAIN" 1>&2
}

while getopts b:d: OPT; do
  case $OPT in
    "b" ) BUCKET=${OPTARG} ;;
    "d" ) DOMAIN=${OPTARG} ;;
      * ) myhelp;
          exit 1 ;;
  esac
done

if [ -z "$BUCKET" ]; then
    myhelp
    echo "Error: BUCKET must be specified."
    exit 1
fi

if [ -z "$DOMAIN" ]; then
    myhelp
    echo "Error: DOMAIN must be specified."
    exit 1
fi

# rename old certs.
if [ -e /etc/nginx/ssl/"$DOMAIN" ]; then
    if [ -e /etc/nginx/ssl/"$DOMAIN".bak ]; then
        rm -rf /etc/nginx/ssl/"$DOMAIN".bak
    fi
    cp -r /etc/nginx/ssl/"$DOMAIN" /etc/nginx/ssl/"$DOMAIN".bak
fi

sudo aws s3 cp s3://"$BUCKET"/"$DOMAIN" /etc/nginx/ssl/"$DOMAIN".tmp --recursive

# If downloading from S3 succeeded, reload nginx.
if [ -e /etc/nginx/ssl/"$DOMAIN".tmp ]; then
    mkdir -p /etc/nginx/ssl/"$DOMAIN"
    cp -r /etc/nginx/ssl/"$DOMAIN".tmp/* /etc/nginx/ssl/"$DOMAIN"
    rm -rf /etc/nginx/ssl/"$DOMAIN".tmp
    sudo service nginx reload
fi

