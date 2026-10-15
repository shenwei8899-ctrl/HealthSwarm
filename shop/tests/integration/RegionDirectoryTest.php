<?php

require dirname(__DIR__) . '/bootstrap.php';

use addons\shop\library\v5\AddressService;
use think\Db;

$service = new AddressService();
$all = $service->areas(0, true)['items'];
if (count($all) !== (int)Db::name('shop_area')->where('status', 'normal')->count()) {
    throw new RuntimeException('Full directory must contain every active area');
}
$grouped = [];
foreach ($all as $row) $grouped[(string)$row['pid']][] = $row;
if ($service->areas()['items'] !== $grouped['0']) throw new RuntimeException('Existing province query changed');
$hunan = array_values(array_filter($grouped['0'], function ($row) { return $row['name'] === '湖南省'; }));
if (count($hunan) !== 1) throw new RuntimeException('Hunan fixture missing');
$cities = $grouped[(string)$hunan[0]['id']] ?? [];
if (count($cities) < 2) throw new RuntimeException('Hunan cities missing from full directory');
foreach ($cities as $city) {
    $districts = $grouped[(string)$city['id']] ?? [];
    if (!$districts || $districts !== $service->areas($city['id'])['items']) {
        throw new RuntimeException('Districts do not match the existing hierarchy');
    }
}
echo 'Region directory passed: ' . count($all) . ' active areas, ' . count($cities) . " Hunan cities; no data modified.\n";
