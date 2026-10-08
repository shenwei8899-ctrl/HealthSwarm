<?php

require __DIR__ . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\v5\JobRunner;
use think\Db;

$runId = 'retention-test-' . bin2hex(random_bytes(6));
Db::name('shop_job_run')->insert([
    'run_id' => $runId,
    'job_name' => 'retention_test',
    'status' => 'success',
    'started_at' => time() - 91 * 86400,
    'finished_at' => time() - 91 * 86400,
]);

try {
    $processed = (new JobRunner())->cleanupIntegrationState();
    if (Db::name('shop_job_run')->where('run_id', $runId)->find()) {
        throw new RuntimeException('90-day job-run retention did not delete the expired row');
    }
    echo 'Job retention test passed; processed=' . $processed . PHP_EOL;
} finally {
    Db::name('shop_job_run')->where('run_id', $runId)->delete();
}
