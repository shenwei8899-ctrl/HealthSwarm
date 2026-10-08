<?php

namespace app\common\library\token\driver;

/**
 * PostgreSQL-backed token storage. The implementation is SQL-driver agnostic;
 * the configured ThinkPHP connection is PostgreSQL in this deployment.
 */
class Database extends Mysql
{
}
