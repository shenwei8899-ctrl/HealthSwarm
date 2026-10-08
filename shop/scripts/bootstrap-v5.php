<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'tests' . DIRECTORY_SEPARATOR . 'bootstrap.php';

use think\Db;

$prefix = config('database.prefix');
    $addon = get_addon_instance('shop');

if (!$addon) {
    throw new RuntimeException('商城插件无法加载');
}

bootstrapPostgresqlSchema($prefix);
syncPostgresqlSequences($prefix);
$addon->upgrade();

configureAdminWorkspace();

$info = get_addon_info('shop');
if (empty($info['state'])) {
    $info['state'] = 1;
    unset($info['url']);
    set_addon_info('shop', $info);
}

$admin = Db::name('admin')->where('id', 1)->find();
$forceAdminCredentials = filter_var(getenv('FASTADMIN_FORCE_ADMIN_CREDENTIALS'), FILTER_VALIDATE_BOOLEAN);
if ($admin && (empty($admin['password']) || $forceAdminCredentials)) {
    $username = getenv('FASTADMIN_ADMIN_USERNAME') ?: 'liubeiping';
    $password = getenv('FASTADMIN_ADMIN_PASSWORD') ?: 'HealthFlow@2026';
    if ($forceAdminCredentials && (strlen($password) < 12 || $password === 'HealthFlow@2026')) {
        throw new RuntimeException('生产环境后台密码必须至少12位且不能使用默认密码');
    }
    $salt = substr(hash('sha256', uniqid('', true)), 0, 6);
    Db::name('admin')->where('id', 1)->update([
        'username' => $username,
        'nickname' => '刘北萍',
        'password' => md5(md5($password) . $salt),
        'salt' => $salt,
        'updatetime' => time(),
    ]);
}

echo "HealthFlow V5 bootstrap complete.\n";

function syncPostgresqlSequences($prefix)
{
    if (strtolower((string)config('database.type')) !== 'pgsql') {
        return;
    }
    $table = $prefix . 'auth_rule';
    // Existing SQL imports can leave PostgreSQL sequences behind the current
    // MAX(id). Sync the permission sequence before menu upgrade inserts rows.
    Db::execute("SELECT setval(pg_get_serial_sequence('{$table}', 'id'), COALESCE((SELECT MAX(\"id\") FROM \"{$table}\"), 1), true)");
}

function bootstrapPostgresqlSchema($prefix)
{
    $schemaFiles = [
        dirname(__DIR__) . DIRECTORY_SEPARATOR . 'database' . DIRECTORY_SEPARATOR . 'postgresql' . DIRECTORY_SEPARATOR . '002_shop.sql',
        dirname(__DIR__) . DIRECTORY_SEPARATOR . 'database' . DIRECTORY_SEPARATOR . 'postgresql' . DIRECTORY_SEPARATOR . '003_v5_schema.sql',
    ];
    foreach ($schemaFiles as $path) {
        if (!is_file($path)) {
            throw new RuntimeException('PostgreSQL schema file not found: ' . $path);
        }
        $sql = str_replace('__PREFIX__', $prefix, file_get_contents($path));
        foreach (splitPostgresqlStatements($sql) as $statement) {
            try {
                Db::execute($statement);
            } catch (\Exception $e) {
                if (stripos($e->getMessage(), 'already exists') === false) {
                    throw $e;
                }
            }
        }
    }
}

function splitPostgresqlStatements($sql)
{
    $statements = [];
    $buffer = '';
    $single = false;
    $length = strlen($sql);
    for ($i = 0; $i < $length; $i++) {
        $char = $sql[$i];
        $buffer .= $char;
        if ($char === "'" && ($i === 0 || $sql[$i - 1] !== '\\')) {
            if ($single && $i + 1 < $length && $sql[$i + 1] === "'") {
                $buffer .= $sql[++$i];
            } else {
                $single = !$single;
            }
        } elseif ($char === ';' && !$single) {
            $statement = trim(substr($buffer, 0, -1));
            if ($statement !== '') {
                $statements[] = $statement;
            }
            $buffer = '';
        }
    }
    $buffer = trim($buffer);
    if ($buffer !== '') {
        $statements[] = $buffer;
    }
    return $statements;
}

function configureAdminWorkspace()
{
    $ruleNames = ['dashboard', 'general', 'auth', 'addon', 'user'];
    Db::name('auth_rule')->where('name', 'in', $ruleNames)
        ->update(['ismenu' => 0]);
    Db::name('config')->where('name', 'fixedpage')
        ->update(['value' => 'shop/v5/workspace/dashboard']);

    $siteFile = APP_PATH . 'extra' . DIRECTORY_SEPARATOR . 'site.php';
    $site = is_file($siteFile) ? include $siteFile : [];
    $site['fixedpage'] = 'shop/v5/workspace/dashboard';
    file_put_contents($siteFile, "<?php\n\nreturn " . var_export($site, true) . ";\n", LOCK_EX);
    \think\Cache::rm('__menu__');
}
