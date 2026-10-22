<?php
namespace addons\shop\library\v5;

class CatalogEligibility
{
    public static function current(array $row, $now = null)
    {
        $now = $now ?? time();
        return ($row['status'] ?? '') === 'normal' && ($row['review_status'] ?? '') === 'approved'
            && (empty($row['valid_from']) || (int)$row['valid_from'] <= $now)
            && (empty($row['valid_to']) || (int)$row['valid_to'] > $now);
    }

    public static function convert($value, $from, $to)
    {
        if (!is_numeric($value) || !is_finite((float)$value) || (float)$value <= 0) return null;
        if ($from === $to && in_array($from, ['g','kg','ml','l','piece','pack'], true)) return (float)$value;
        $units = ['g'=>['mass',1], 'kg'=>['mass',1000], 'ml'=>['volume',1], 'l'=>['volume',1000]];
        if (!isset($units[$from], $units[$to]) || $units[$from][0] !== $units[$to][0]) return null;
        return (float)$value * $units[$from][1] / $units[$to][1];
    }
}
