<?php

if (PHP_SAPI !== 'cli') throw new RuntimeException('CLI only');
$options = getopt('', ['apply', 'reenable']);
require dirname(__DIR__) . '/tests/bootstrap.php';

use think\Db;

$provinces = Db::name('shop_area')->where('level', 1)->where('status', 'normal')->order('id')->select();
if (!$provinces) throw new RuntimeException('Import the administrative region directory first');
$codes = [];
foreach ($provinces as $province) {
    $code = (string)$province['adcode'];
    if (!preg_match('/^\d{6}$/', $code) || isset($codes[$code])) throw new RuntimeException('Missing or duplicate province code');
    $codes[$code] = true;
}
echo 'Province-level nationwide coverage: ' . count($provinces) . " regions.\n";
if (!isset($options['apply'])) {
    echo "Dry run; no changes. Use --apply to explicitly enable nationwide delivery.\n";
    exit;
}

$added = 0;
$enabled = 0;
$keptDisabled = 0;
Db::startTrans();
try {
    foreach ($provinces as $province) {
        $areaCode = 'NATIONWIDE-' . $province['adcode'];
        $existing = Db::name('shop_delivery_area')->where('area_code', $areaCode)->where('supplier_id', 0)->find();
        if ($existing) {
            if ($existing['province_code'] !== $province['adcode'] || $existing['city_code'] !== '' || $existing['district_code'] !== '') {
                throw new RuntimeException('Conflicting delivery rule: ' . $areaCode);
            }
            if ($existing['status'] !== 'normal') {
                if (!isset($options['reenable'])) { $keptDisabled++; continue; }
                Db::name('shop_delivery_area')->where('id', $existing['id'])->update([
                    'status' => 'normal', 'version' => (int)$existing['version'] + 1, 'updatetime' => time(),
                ]);
                $enabled++;
            }
            continue;
        }
        Db::name('shop_delivery_area')->insert([
            'area_code' => $areaCode, 'name' => $province['name'],
            'province_code' => $province['adcode'], 'city_code' => '', 'district_code' => '',
            'supplier_id' => 0, 'status' => 'normal', 'version' => 1,
            'createtime' => time(), 'updatetime' => time(),
        ]);
        $added++;
    }
    Db::commit();
} catch (\Throwable $e) { Db::rollback(); throw $e; }
echo 'Nationwide delivery configured; added: ' . $added . ', re-enabled: ' . $enabled . ', kept disabled: ' . $keptDisabled . ". Existing district/city rules preserved.\n";
