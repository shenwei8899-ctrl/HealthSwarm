<?php

namespace addons\shop\library\v5;

use think\Config;
use think\Db;

/**
 * Idempotent database bootstrap for the V5 commerce domain.
 */
class Migrator
{
    const VERSION = '20260930_v5_001';

    public static function migrate()
    {
        $isPostgres = strtolower((string)Config::get('database.type')) === 'pgsql';
        $path = $isPostgres
            ? ROOT_PATH . 'database' . DS . 'postgresql' . DS . '003_v5_schema.sql'
            : ADDON_PATH . 'shop' . DS . 'database' . DS . 'v5_schema.sql';
        if (!is_file($path)) {
            throw new \RuntimeException('V5 schema file not found: ' . $path);
        }

        $prefix = (string)Config::get('database.prefix');
        $sql = file_get_contents($path);
        if ($isPostgres) {
            $sql = str_replace('"fa_', '"' . $prefix, $sql);
        } else {
            $sql = str_replace('__PREFIX__', $prefix, $sql);
        }
        foreach (self::splitStatements($sql) as $statement) {
            Db::execute($statement);
        }

        self::extendLegacyTables($prefix);
        self::seedPolicy();

        $checksum = hash_file('sha256', $path);
        $exists = Db::name('shop_schema_migration')->where('version', self::VERSION)->find();
        $data = [
            'description' => 'Family Nutrition Commerce V5 baseline',
            'checksum'    => $checksum,
            'executed_at' => time(),
        ];
        if ($exists) {
            Db::name('shop_schema_migration')->where('id', $exists['id'])->update($data);
        } else {
            $data['version'] = self::VERSION;
            Db::name('shop_schema_migration')->insert($data);
        }
    }

    protected static function splitStatements($sql)
    {
        $sql = preg_replace('/^\s*--.*$/m', '', $sql);
        $statements = [];
        foreach (explode(';', $sql) as $statement) {
            $statement = trim($statement);
            if ($statement !== '') {
                $statements[] = $statement;
            }
        }
        return $statements;
    }

    protected static function extendLegacyTables($prefix)
    {
        $columns = [
            'shop_recommendation_package' => [
                'request_digest' => "char(64) NOT NULL DEFAULT '' COMMENT 'Agent创建请求摘要'",
            ],
            'shop_service_plan' => [
                'request_digest' => "char(64) NOT NULL DEFAULT '' COMMENT 'Agent创建请求摘要'",
            ],
            'shop_goods' => [
                'sale_type'             => "varchar(20) NOT NULL DEFAULT 'normal' COMMENT 'normal/bundle/service'",
                'business_category_code'=> "varchar(50) NOT NULL DEFAULT '' COMMENT '稳定业务分类编码'",
                'agent_visible'         => "tinyint unsigned NOT NULL DEFAULT 0 COMMENT 'Agent目录可见'",
                'catalog_status'        => "varchar(20) NOT NULL DEFAULT 'draft' COMMENT '目录状态'",
                'data_completeness'     => "varchar(20) NOT NULL DEFAULT 'insufficient' COMMENT '资料完整度'",
                'catalog_version'       => "bigint unsigned NOT NULL DEFAULT 0 COMMENT '目录版本'",
                'row_version'           => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
            ],
            'shop_goods_sku' => [
                'sku_code'           => "varchar(64) NOT NULL DEFAULT '' COMMENT '稳定SKU编码'",
                'net_content_value'  => "decimal(14,3) NOT NULL DEFAULT 0 COMMENT '包装净含量'",
                'net_content_unit'   => "varchar(20) NOT NULL DEFAULT '' COMMENT '净含量单位'",
                'safety_stock'       => "int unsigned NOT NULL DEFAULT 0 COMMENT '安全库存'",
                'reserved_stock'     => "int unsigned NOT NULL DEFAULT 0 COMMENT '占用库存'",
                'stock_updated_at'   => "bigint unsigned NOT NULL DEFAULT 0 COMMENT '库存更新时间'",
                'row_version'        => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
            ],
            'shop_category' => [
                'business_category_code' => "varchar(50) NOT NULL DEFAULT '' COMMENT '稳定业务分类编码'",
                'agent_visible'          => "tinyint unsigned NOT NULL DEFAULT 0 COMMENT 'Agent目录可见'",
                'row_version'            => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
            ],
            'shop_carts' => [
                'source_type'     => "varchar(30) NOT NULL DEFAULT '' COMMENT '来源类型'",
                'source_ref'      => "varchar(64) NOT NULL DEFAULT '' COMMENT '来源编号'",
                'source_version'  => "int unsigned NOT NULL DEFAULT 0 COMMENT '来源版本'",
                'purchase_item_id'=> "bigint unsigned NOT NULL DEFAULT 0 COMMENT '采购项'",
                'row_version'     => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
            ],
            'shop_order' => [
                'order_type' => "varchar(20) NOT NULL DEFAULT 'normal' COMMENT 'normal/plan'",
                'row_version'=> "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
                'request_id' => "varchar(64) NOT NULL DEFAULT '' COMMENT '请求追踪号'",
            ],
            'shop_order_goods' => [
                'row_version' => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
            ],
            'shop_order_aftersales' => [
                'aftersale_sn'=> "varchar(64) DEFAULT NULL COMMENT 'V1售后单号'",
                'batch_id'    => "bigint unsigned NOT NULL DEFAULT 0 COMMENT '计划批次'",
                'source_type' => "varchar(20) NOT NULL DEFAULT 'normal' COMMENT '售后来源'",
                'reason_code' => "varchar(50) NOT NULL DEFAULT '' COMMENT '标准售后原因码'",
                'request_id'  => "varchar(64) NOT NULL DEFAULT '' COMMENT '幂等请求号'",
                'row_version' => "int unsigned NOT NULL DEFAULT 1 COMMENT '乐观锁版本'",
                'cancelled_at'=> "bigint unsigned NOT NULL DEFAULT 0 COMMENT '撤销时间'",
                'result_confirmed_at'=> "bigint unsigned NOT NULL DEFAULT 0 COMMENT '用户确认处理结果时间'",
            ],
            'shop_coupon' => [
                'source_scope'            => "varchar(100) NOT NULL DEFAULT 'normal' COMMENT '适用业务来源'",
                'plan_allowed'            => "tinyint unsigned NOT NULL DEFAULT 0 COMMENT '是否适用专属计划'",
                'refund_allocation_rule'  => "varchar(30) NOT NULL DEFAULT 'proportional' COMMENT '退款分摊规则'",
            ],
            'shop_freight' => [
                'temperature_zone'       => "varchar(30) NOT NULL DEFAULT 'ambient' COMMENT '温层'",
                'supplier_id'            => "bigint unsigned NOT NULL DEFAULT 0 COMMENT '供应商'",
                'delivery_slot_required' => "tinyint unsigned NOT NULL DEFAULT 0 COMMENT '是否必须选择配送时段'",
            ],
        ];

        foreach ($columns as $logicalTable => $definitions) {
            $table = $prefix . $logicalTable;
            foreach ($definitions as $column => $definition) {
                if (!self::columnExists($table, $column)) {
                    try {
                        Db::execute("ALTER TABLE \"{$table}\" ADD COLUMN IF NOT EXISTS \"{$column}\" " . self::postgresDefinition($definition));
                    } catch (\Exception $e) {
                        if (stripos($e->getMessage(), 'already exists') === false) {
                            throw $e;
                        }
                    }
                }
            }
        }

        Db::execute("UPDATE \"{$prefix}shop_goods_sku\" SET \"sku_code\" = 'SKU-' || \"id\"::text WHERE \"sku_code\" = '' OR \"sku_code\" IS NULL");

        $indexes = [
            'shop_goods' => [
                'idx_goods_agent_catalog'    => '(`agent_visible`,`catalog_status`,`updatetime`)',
                'idx_goods_business_category'=> '(`business_category_code`)',
            ],
            'shop_goods_sku' => [
                'uk_sku_code' => 'UNIQUE (`sku_code`)',
            ],
            'shop_category' => [
                'idx_category_business_code' => '(`business_category_code`)',
                'idx_category_agent_visible' => '(`agent_visible`,`status`)',
            ],
            'shop_carts' => [
                'idx_cart_source' => '(`user_id`,`source_type`,`source_ref`)',
            ],
            'shop_order' => [
                'idx_order_type_status' => '(`order_type`,`orderstate`,`paystate`,`shippingstate`)',
            ],
            'shop_order_aftersales' => [
                'idx_aftersale_batch' => '(`batch_id`,`status`)',
                'uk_aftersale_sn' => 'UNIQUE (`aftersale_sn`)',
            ],
        ];
        foreach ($indexes as $logicalTable => $definitions) {
            $table = $prefix . $logicalTable;
            foreach ($definitions as $index => $definition) {
                if (!self::indexExists($table, $index)) {
                    $unique = strpos($definition, 'UNIQUE ') === 0 ? 'UNIQUE ' : '';
                    $columns = $unique ? substr($definition, 7) : $definition;
                    $columns = str_replace('`', '"', $columns);
                    $indexSql = $unique ? 'CREATE UNIQUE INDEX' : 'CREATE INDEX';
                    Db::execute($indexSql . " IF NOT EXISTS \"{$index}\" ON \"{$table}\" {$columns}");
                }
            }
        }
    }

    protected static function columnExists($table, $column)
    {
        $rows = Db::query("SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ? AND column_name = ?", [$table, $column]);
        return !empty($rows);
    }

    protected static function indexExists($table, $index)
    {
        $rows = Db::query("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND tablename = ? AND indexname = ?", [$table, $index]);
        return !empty($rows);
    }

    protected static function postgresDefinition($definition)
    {
        $definition = preg_replace('/\s+COMMENT\s+\'([^\']|\'\')*\'/i', '', $definition);
        $definition = preg_replace('/\s+UNSIGNED\b/i', '', $definition);
        $definition = preg_replace('/\bTINYINT\b/i', 'smallint', $definition);
        $definition = preg_replace('/\bLONGTEXT\b|\bMEDIUMTEXT\b/i', 'text', $definition);
        return trim($definition);
    }

    protected static function seedPolicy()
    {
        $version = '2026-09-30-v1';
        if (Db::name('shop_policy_version')->where([
            'policy_type'    => 'plan_non_refund',
            'policy_version' => $version,
        ])->find()) {
            return;
        }
        $content = 'AI专属计划为一次性购买的21天定制服务。支付成功后，不支持因个人原因取消或退款；平台未履约、错漏发、食品质量问题以及法律规定必须处理的情形除外。';
        Db::name('shop_policy_version')->insert([
            'policy_type'    => 'plan_non_refund',
            'policy_version' => $version,
            'title'          => 'AI专属计划付款与退款提示',
            'content'        => $content,
            'content_hash'   => hash('sha256', $content),
            'effective_at'   => time(),
            'status'         => 'active',
            'createtime'     => time(),
            'updatetime'     => time(),
        ]);
    }
}
