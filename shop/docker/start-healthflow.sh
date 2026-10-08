#!/bin/sh
set -eu

php scripts/bootstrap-v5.php
exec php -S 0.0.0.0:8080 -t public public/router.php
