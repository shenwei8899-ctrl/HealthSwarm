<?php

require dirname(__DIR__, 2) . '/addons/shop/library/v5/Migrator.php';

$method = new ReflectionMethod(\addons\shop\library\v5\Migrator::class, 'migrationChecksums');
$method->setAccessible(true);
$sql = "ALTER TABLE example ADD COLUMN IF NOT EXISTS label varchar(64);\n";
$canonical = hash('sha256', $sql);
$variants = [$sql, str_replace("\n", "\r\n", $sql), str_replace("\n", "\r\r\n", $sql)];
foreach ($variants as $source) {
    $checksums = $method->invoke(null, $source);
    if ($checksums[0] !== $canonical) throw new RuntimeException('New migrations must use the canonical checksum');
    foreach ($variants as $historical) {
        if (!in_array(hash('sha256', $historical), $checksums, true)) throw new RuntimeException('Historical line endings must remain readable');
    }
    $changed = $method->invoke(null, str_replace('varchar(64)', 'varchar(65)', $source));
    foreach ($variants as $historical) {
        if (in_array(hash('sha256', $historical), $changed, true)) throw new RuntimeException('Changed SQL must still be rejected');
    }
}
echo "Migration checksums passed: LF, CRLF and historical CRCRLF accepted, changed SQL rejected.\n";
