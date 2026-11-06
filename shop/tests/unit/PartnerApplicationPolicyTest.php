<?php

namespace think {
    class Config
    {
        public static $databaseType = 'pgsql';
        public static function get($key) { return self::$databaseType; }
    }

    class Db
    {
        public static $migrated = false;
        public static $queries = 0;
        public static function name($table)
        {
            if ($table !== 'shop_schema_migration') throw new \RuntimeException('Unexpected table access');
            self::$queries++;
            return new self();
        }
        public function where($column, $value)
        {
            if ($column !== 'version' || $value !== '20261101_partner_intake') throw new \RuntimeException('Unexpected migration lookup');
            return $this;
        }
        public function find() { return self::$migrated ? ['version' => '20261101_partner_intake'] : null; }
    }
}

namespace {
    $library = dirname(__DIR__, 2) . '/addons/shop/library/v5/';
    require $library . 'DomainException.php';
    require $library . 'PartnerApplicationService.php';

    use addons\shop\library\v5\{DomainException, PartnerApplicationService};
    use think\{Config, Db};

    function policyAssert($value, $message) { if (!$value) throw new \RuntimeException($message); }
    function policyReject($callback, $message)
    {
        try { $callback(); }
        catch (DomainException $error) {
            policyAssert($error->getCode() === 50301 && $error->getHttpStatus() === 503, 'Invalid rejection contract');
            policyAssert(strpos($error->getMessage(), $message) !== false, 'Rejection does not explain the prerequisite');
            return;
        }
        throw new \RuntimeException('Expected unavailable policy');
    }

    $service = new PartnerApplicationService();
    foreach (['0', 'synthetic-key'] as $key) {
        policyAssert(PartnerApplicationService::isContactIntake(['submission_key' => $key]), 'Every nonempty submission key is a contact intake');
    }
    foreach ([[], ['submission_key' => null], ['submission_key' => '']] as $application) {
        policyAssert(!PartnerApplicationService::isContactIntake($application), 'Legacy applications retain their review flow');
    }
    foreach (['mysql', 'sqlite', ''] as $databaseType) {
        Config::$databaseType = $databaseType;
        Db::$queries = 0;
        Db::$migrated = true;
        policyReject(function () use ($service) { $service->policy(); }, 'PostgreSQL');
        policyReject(function () use ($service) { $service->submit(1, 'synthetic-key', []); }, 'PostgreSQL');
        policyAssert(Db::$queries === 0, 'Unsupported database must be rejected before a query');
    }
    Config::$databaseType = 'pgsql';
    Db::$migrated = false;
    policyReject(function () use ($service) { $service->policy(); }, '暂时无法提交');
    Db::$migrated = true;
    policyAssert($service->policy() === ['policy_version' => PartnerApplicationService::POLICY], 'Migrated PostgreSQL policy is unavailable');
    echo "Partner policy passed: unsupported databases rejected before queries, migration required, ready PostgreSQL accepted. No database used.\n";
}
