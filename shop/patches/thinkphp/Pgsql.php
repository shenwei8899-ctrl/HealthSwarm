<?php
// +----------------------------------------------------------------------
// | ThinkPHP [ WE CAN DO IT JUST THINK ]
// +----------------------------------------------------------------------
// | Copyright (c) 2006~2018 http://thinkphp.cn All rights reserved.
// +----------------------------------------------------------------------
// | Licensed ( http://www.apache.org/licenses/LICENSE-2.0 )
// +----------------------------------------------------------------------
// | Author: liu21st <liu21st@gmail.com>
// +----------------------------------------------------------------------

namespace think\db\connector;

use PDO;
use think\db\Connection;

/**
 * Pgsql数据库驱动
 */
class Pgsql extends Connection
{
    protected $builder = '\\think\\db\\builder\\Pgsql';

    /**
     * 解析pdo连接的dsn信息
     * @access protected
     * @param array $config 连接信息
     * @return string
     */
    protected function parseDsn($config)
    {
        $dsn = 'pgsql:dbname=' . $config['database'] . ';host=' . $config['hostname'];
        if (!empty($config['hostport'])) {
            $dsn .= ';port=' . $config['hostport'];
        }
        return $dsn;
    }

    /**
     * 取得数据表的字段信息
     * @access public
     * @param string $tableName
     * @return array
     */
    public function getFields($tableName)
    {
        list($tableName) = explode(' ', trim($tableName));
        $tableName = trim($tableName, "`\"");
        $schema = 'public';
        if (strpos($tableName, '.') !== false) {
            list($schema, $tableName) = explode('.', $tableName, 2);
            $schema = trim($schema, "`\"");
            $tableName = trim($tableName, "`\"");
        }

        // Keep this query in PostgreSQL's catalog instead of relying on the
        // obsolete table_msg() helper from older ThinkPHP distributions.
        $sql = <<<'SQL'
SELECT
    c.column_name AS "field",
    format_type(a.atttypid, a.atttypmod) AS "type",
    (c.is_nullable = 'NO') AS "notnull",
    c.column_default AS "default",
    (pk.attname IS NOT NULL) AS "primary",
    (a.attidentity <> '' OR c.column_default LIKE 'nextval(%') AS "autoinc"
FROM information_schema.columns c
JOIN pg_class cls ON cls.relname = c.table_name
JOIN pg_namespace ns ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
JOIN pg_attribute a ON a.attrelid = cls.oid AND a.attname = c.column_name AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN (
    SELECT i.indrelid, unnest(i.indkey) AS attnum
    FROM pg_index i
    WHERE i.indisprimary
) pkey ON pkey.indrelid = cls.oid AND pkey.attnum = a.attnum
LEFT JOIN pg_attribute pk ON pk.attrelid = cls.oid AND pk.attnum = pkey.attnum
WHERE c.table_schema = :schema AND c.table_name = :table
ORDER BY c.ordinal_position
SQL;

        $pdo = $this->query($sql, ['schema' => $schema, 'table' => $tableName], false, true);
        $result = $pdo->fetchAll(PDO::FETCH_ASSOC);
        $info   = [];
        if ($result) {
            foreach ($result as $key => $val) {
                $val                 = array_change_key_case($val);
                $info[$val['field']] = [
                    'name'    => $val['field'],
                    'type'    => $val['type'],
                    'notnull' => filter_var($val['notnull'], FILTER_VALIDATE_BOOLEAN),
                    'default' => $val['default'],
                    'primary' => filter_var($val['primary'], FILTER_VALIDATE_BOOLEAN),
                    'autoinc' => filter_var($val['autoinc'], FILTER_VALIDATE_BOOLEAN),
                ];
            }
        }
        return $this->fieldCase($info);
    }

    /**
     * 取得数据库的表信息
     * @access public
     * @param string $dbName
     * @return array
     */
    public function getTables($dbName = '')
    {
        $sql    = "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY tablename";
        $pdo    = $this->query($sql, [], false, true);
        $result = $pdo->fetchAll(PDO::FETCH_ASSOC);
        $info   = [];
        foreach ($result as $key => $val) {
            $info[$key] = current($val);
        }
        return $info;
    }

    /**
     * SQL性能分析
     * @access protected
     * @param string $sql
     * @return array
     */
    protected function getExplain($sql)
    {
        return [];
    }

    protected function supportSavepoint()
    {
        return true;
    }
}
