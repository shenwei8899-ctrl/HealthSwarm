<?php

namespace addons\shop\library\service;

use RuntimeException;

class UnitConverter
{
    private static $units = [
        'mg' => ['dimension' => 'weight', 'factor' => '0.001'],
        'g'  => ['dimension' => 'weight', 'factor' => '1'],
        'kg' => ['dimension' => 'weight', 'factor' => '1000'],
        'ml' => ['dimension' => 'volume', 'factor' => '1'],
        'l'  => ['dimension' => 'volume', 'factor' => '1000'],
        '个' => ['dimension' => 'count', 'factor' => '1'],
        '只' => ['dimension' => 'count', 'factor' => '1'],
        '枚' => ['dimension' => 'count', 'factor' => '1'],
        '份' => ['dimension' => 'count', 'factor' => '1'],
        '盒' => ['dimension' => 'count', 'factor' => '1'],
        '袋' => ['dimension' => 'count', 'factor' => '1'],
    ];

    public static function convert($quantity, $fromUnit, $toUnit, $scale = 3)
    {
        $fromUnit = self::normalizeUnit($fromUnit);
        $toUnit = self::normalizeUnit($toUnit);
        if (!isset(self::$units[$fromUnit]) || !isset(self::$units[$toUnit])) {
            throw new RuntimeException('不支持的计量单位换算');
        }
        if (self::$units[$fromUnit]['dimension'] !== self::$units[$toUnit]['dimension']) {
            throw new RuntimeException('不同计量维度不能换算');
        }
        if (!is_numeric($quantity) || (float)$quantity < 0) {
            throw new RuntimeException('数量必须是非负数');
        }

        $base = bcmul((string)$quantity, self::$units[$fromUnit]['factor'], 6);
        return bcdiv($base, self::$units[$toUnit]['factor'], $scale);
    }

    public static function normalizeUnit($unit)
    {
        $unit = trim((string)$unit);
        $aliases = [
            '克' => 'g',
            '千克' => 'kg',
            '公斤' => 'kg',
            '毫克' => 'mg',
            '毫升' => 'ml',
            '升' => 'l',
            'L' => 'l',
            'ML' => 'ml',
            'KG' => 'kg',
            'G' => 'g',
        ];
        return isset($aliases[$unit]) ? $aliases[$unit] : strtolower($unit);
    }
}

