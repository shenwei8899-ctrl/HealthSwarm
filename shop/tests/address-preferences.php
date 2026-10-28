<?php
// Run the actual candidate service with an isolated, transactional in-memory DB adapter.
// This verifies service rules, not PostgreSQL locking or HTTP authentication.
namespace think {
    class Db {
        public static $tables = [];
        private static $snapshot;
        public static function name($table) { return new AddressTestQuery($table); }
        public static function raw($value) { return (object)['expression' => $value]; }
        public static function startTrans() { self::$snapshot = self::$tables; }
        public static function commit() { self::$snapshot = null; }
        public static function rollback() { self::$tables = self::$snapshot; self::$snapshot = null; }
    }
    class AddressTestQuery {
        private $table, $conditions = [], $sort = '';
        public function __construct($table) { $this->table = $table; }
        public function where($key, $value) { $this->conditions[] = [$key, $value]; return $this; }
        public function whereNull($key) { return $this->where($key, null); }
        public function order($field, $direction = '') { $this->sort = $field . ($direction ? ' ' . $direction : ''); return $this; }
        public function lock($value) { return $this; }
        public function alias($value) { return $this; }
        public function join($table, $condition) { return $this; }
        public function field($value) { return $this; }
        public function limit($value) { return $this; }
        private function column($row, $key) {
            if ($this->table === 'shop_area' && in_array($key, ['p.name', 'c.name'])) {
                $city = Db::$tables['shop_area'][$row['pid']] ?? null;
                $target = $key === 'c.name' ? $city : (Db::$tables['shop_area'][$city['pid'] ?? -1] ?? null);
                return $target['name'] ?? null;
            }
            return $row[preg_replace('/^a\./', '', $key)] ?? null;
        }
        private function matches($row) {
            foreach ($this->conditions as [$key, $value]) if ($this->column($row, $key) != $value) return false;
            return true;
        }
        public function select() {
            $rows = array_values(array_filter(Db::$tables[$this->table] ?? [], function ($row) { return $this->matches($row); }));
            if ($this->sort) {
                $sort = $this->sort;
                usort($rows, function ($a, $b) use ($sort) {
                    foreach (explode(',', $sort) as $part) {
                        $tokens = explode(' ', trim($part)); $key = $tokens[0];
                        $order = ($a[$key] ?? 0) <=> ($b[$key] ?? 0);
                        if ($order) return ($tokens[1] ?? '') === 'desc' ? -$order : $order;
                    }
                    return 0;
                });
            }
            return $rows;
        }
        public function count() { return count($this->select()); }
        public function find() { return $this->select()[0] ?? null; }
        public function value($key) { return $this->find()[$key] ?? null; }
        public function update($data) {
            $count = 0;
            foreach (Db::$tables[$this->table] as &$row) if ($this->matches($row)) {
                foreach ($data as $key => $value) {
                    if (is_object($value)) {
                        if ($value->expression !== 'row_version+1') throw new \RuntimeException('Unexpected expression');
                        $row[$key] = (int)$row[$key] + 1;
                    } else $row[$key] = $value;
                }
                $count++;
            }
            return $count;
        }
        public function insertGetId($data) {
            $id = count(Db::$tables[$this->table] ?? []) + 1;
            Db::$tables[$this->table][$id] = $data + ['id' => $id, 'deletetime' => null]; return $id;
        }
    }
}
namespace addons\shop\library\v5 {
    class DomainException extends \RuntimeException {
        public function __construct($message, $code = 0, $status = 0) { parent::__construct($message, $code); }
    }
}
namespace {
    require __DIR__ . '/../addons/shop/library/v5/AddressService.php';
    use think\Db;
    use addons\shop\library\v5\AddressService;
    $checks = 0;
    function check($condition, $message) { global $checks; if (!$condition) throw new \RuntimeException($message); $checks++; }
    function denied($callback, $message) {
        try { $callback(); } catch (\addons\shop\library\v5\DomainException $e) { check(true, $message); return; }
        check(false, $message);
    }
    Db::$tables = [
        'user' => [1 => ['id' => 1], 2 => ['id' => 2]], 'shop_address' => [],
        'shop_area' => [
            1 => ['id' => 1, 'pid' => 0, 'name' => '湖南省', 'level' => 1, 'status' => 'normal'],
            2 => ['id' => 2, 'pid' => 1, 'name' => '长沙市', 'level' => 2, 'status' => 'normal'],
            3 => ['id' => 3, 'pid' => 2, 'name' => '岳麓区', 'level' => 3, 'status' => 'normal', 'zipcode' => '410000'],
        ],
    ];
    $service = new AddressService();
    $input = ['name' => '示例收货人', 'phone' => '13800000000', 'region' => '湖南省 长沙市 岳麓区', 'area_id' => '3', 'detail' => '示例小区 101 室', 'label' => '家', 'isDefault' => false];
    $first = $service->save(1, $input);
    check($first['isDefault'] === true, 'First address becomes default');
    check($first['label'] === '家', 'Label persists');
    $second = $service->save(1, array_replace($input, ['label' => '公司', 'detail' => '示例写字楼 201 室']));
    check($second['isDefault'] === false, 'Second non-default save preserves existing default');
    check($service->listRows(1)['items'][0]['id'] === $first['id'], 'Default remains first');
    $second = $service->save(1, array_replace($second, ['detail' => '示例写字楼 202 室']), $second['id']);
    check($second['version'] === 2 && !$second['isDefault'], 'Edit increments version without changing default');
    check($service->listRows(1)['items'][0]['id'] === $first['id'], 'Editing non-default retains first default');
    denied(function () use ($service, $input, $second) { $service->save(1, $input + ['version' => 1], $second['id']); }, 'Stale version rejected');
    check(Db::$tables['shop_address'][(int)$second['id']]['address'] === '示例写字楼 202 室', 'Conflict leaves original row intact');
    $service->selectDefault(1, $second['id']);
    $rows = $service->listRows(1)['items'];
    check(count(array_filter($rows, function ($r) { return $r['isDefault']; })) === 1, 'Default is unique');
    check($rows[0]['id'] === $second['id'], 'Explicit default action switches default');
    denied(function () use ($service, $first) { $service->save(1, $first, $first['id']); }, 'Stale form cannot restore a previous default');
    denied(function () use ($service, $second) { $service->selectDefault(2, $second['id']); }, 'Other user cannot set default');
    denied(function () use ($service, $second) { $service->remove(2, $second['id']); }, 'Other user cannot delete');
    check($service->listRows(2)['items'] === [], 'Other user sees no addresses');
    $legacy = $input; unset($legacy['label'], $legacy['isDefault']);
    $oldClient = $service->save(1, $legacy);
    check($oldClient['isDefault'] === true, 'Legacy save behavior remains compatible');
    $withoutLabel = array_values(array_filter($service->listRows(1)['items'], function ($row) use ($second) { return $row['id'] === $second['id']; }))[0]; unset($withoutLabel['label']);
    $edited = $service->save(1, $withoutLabel, $second['id']);
    check($edited['label'] === '公司', 'Legacy edit does not erase label');
    $service->remove(1, $oldClient['id']);
    $rows = $service->listRows(1)['items'];
    check(count($rows) === 2 && count(array_filter($rows, function ($r) { return $r['isDefault']; })) === 1, 'Deleting default selects remaining address');
    denied(function () use ($service, $oldClient) { $service->selectDefault(1, $oldClient['id']); }, 'Deleted address cannot be selected');
    denied(function () use ($service, $input) { $service->save(1, array_replace($input, ['label' => str_repeat('长', 11)])); }, 'Long label rejected');
    denied(function () use ($service, $input) { $service->save(1, array_replace($input, ['label' => "家\n公司"])); }, 'Control character rejected');
    denied(function () use ($service, $input) { $service->save(1, array_replace($input, ['isDefault' => 'false'])); }, 'Non-boolean preference rejected');
    check($service->listRows(1)['capabilities']['default_address'] === true, 'New default capability advertised');
    check($service->listRows(1)['capabilities']['address_labels'] === true, 'Label capability advertised');
    foreach ($service->listRows(1)['items'] as $row) $service->remove(1, $row['id']);
    check($service->listRows(1)['items'] === [], 'Last address deletion yields empty list');
    echo json_encode(['passed' => $checks, 'adapter' => 'isolated in-memory', 'productionWrites' => false], JSON_UNESCAPED_UNICODE) . PHP_EOL;
}
