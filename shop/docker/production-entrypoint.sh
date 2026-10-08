#!/bin/sh
set -eu

required_vars="POSTGRES_PASSWORD FASTADMIN_ADMIN_PASSWORD SHOP_V5_MASTER_KEY"
for name in $required_vars; do
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "Missing required production variable: $name" >&2
        exit 1
    fi
done

admin_password_hash="$(printf '%s' "${FASTADMIN_ADMIN_PASSWORD}" | sha256sum | cut -d' ' -f1)"
database_password_hash="$(printf '%s' "${POSTGRES_PASSWORD}" | sha256sum | cut -d' ' -f1)"
if [ "$admin_password_hash" = "47397042055f7a464c1f6aa0848f50d07e67263f586b5be1b711cc829b36dac9" ] \
    || [ "$database_password_hash" = "2e4372be634b405b626b35fbe322e978c901a0f30947bdd95b2b2ee71265c11b" ]; then
    echo "Default local credentials are forbidden in production" >&2
    exit 1
fi

if [ "${#FASTADMIN_ADMIN_PASSWORD}" -lt 12 ] || [ "${#SHOP_V5_MASTER_KEY}" -lt 32 ]; then
    echo "FASTADMIN_ADMIN_PASSWORD must be at least 12 characters and SHOP_V5_MASTER_KEY at least 32 characters" >&2
    exit 1
fi

case "${POSTGRES_PASSWORD}:${FASTADMIN_ADMIN_PASSWORD}:${SHOP_V5_MASTER_KEY}" in
    *replace-with*)
        echo "Replace all placeholder production credentials before startup" >&2
        exit 1
        ;;
esac

mkdir -p runtime public/uploads
chown -R www-data:www-data runtime public/uploads
php scripts/bootstrap-v5.php
exec "$@"
