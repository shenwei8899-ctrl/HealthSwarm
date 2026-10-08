FROM php:8.3-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libpng-dev \
        libzip-dev \
        libonig-dev \
        libicu-dev \
        libpq-dev \
        unzip \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" bcmath gd intl mbstring pdo_pgsql zip \
    && rm -rf /var/lib/apt/lists/*

COPY docker/php-preview.ini /usr/local/etc/php/conf.d/zz-healthflow.ini

WORKDIR /var/www/html

CMD ["sh", "docker/start-healthflow.sh"]
