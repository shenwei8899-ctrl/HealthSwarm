<?php
// Standalone filesystem test; never loads the application or its database.
$root=dirname(__DIR__,2);
require $root.'/scripts/apply-runtime-patches.php';
$tmp=$root.'/runtime/runtime-patch-test-'.bin2hex(random_bytes(6));
foreach (['scripts','patches/thinkphp','thinkphp/library/think/db/connector'] as $dir) mkdir($tmp.'/'.$dir,0777,true);
copy($root.'/scripts/apply-runtime-patches.php',$tmp.'/scripts/apply-runtime-patches.php');
foreach (['Pgsql.php','Pgsql.upstream.sha256'] as $name) copy($root.'/patches/thinkphp/'.$name,$tmp.'/patches/thinkphp/'.$name);
$target=$tmp.'/thinkphp/library/think/db/connector/Pgsql.php';
copy($root.'/tests/fixtures/thinkphp-Pgsql-upstream.php.fixture',$target);
$run=function () use ($tmp) {
    try {healthflowApplyRuntimePatches($tmp); return 0;} catch (RuntimeException $e) {return 1;}
};
if ($run()!==0 || hash_file('sha256',$target)!==hash_file('sha256',$root.'/patches/thinkphp/Pgsql.php')) throw new RuntimeException('Pinned upstream was not patched');
if ($run()!==0) throw new RuntimeException('Repeated install must be idempotent');
file_put_contents($target,"<?php // unknown framework version\n");
if ($run()===0 || file_get_contents($target)!=="<?php // unknown framework version\n") throw new RuntimeException('Unknown version was silently overwritten');
echo "Runtime patch passed: clean upstream, repeated installation, rejected unknown version.\n";
