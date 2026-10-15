<?php
// Keep the PostgreSQL connector fix reproducible after a clean Composer install.
if (PHP_SAPI !== 'cli') throw new RuntimeException('CLI only');
function healthflowApplyRuntimePatches($root)
{
$target = $root . '/thinkphp/library/think/db/connector/Pgsql.php';
$patch = $root . '/patches/thinkphp/Pgsql.php';
$normalize = function ($path) {
    if (!is_file($path)) throw new RuntimeException('Framework patch input missing: ' . $path);
    return str_replace("\r\n", "\n", file_get_contents($path));
};
$expected = trim(file_get_contents($root . '/patches/thinkphp/Pgsql.upstream.sha256'));
$patched = $normalize($patch);
$current = hash('sha256', $normalize($target));
if (hash_equals(hash('sha256', $patched), $current)) {
    echo "PostgreSQL framework patch already applied.\n";
} elseif (hash_equals($expected, $current)) {
    if (file_put_contents($target, $patched, LOCK_EX) === false) throw new RuntimeException('Cannot apply PostgreSQL framework patch');
    echo "PostgreSQL framework patch applied.\n";
} else {
    throw new RuntimeException('Unexpected ThinkPHP connector version; review the patch before upgrading');
}
}
class HealthflowRuntimePatches
{
    // Composer invokes this in-process; Windows Unicode PHP paths need no shell escaping.
    public static function apply($event = null) { healthflowApplyRuntimePatches(dirname(__DIR__)); }
}
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) HealthflowRuntimePatches::apply();
