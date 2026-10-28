<?php

/** 合成纯边界测试；不加载应用、数据库或真实来源校验 HTTP。 */
namespace think {
    final class Db
    {
        public static $calls = 0;

        public static function __callStatic($name, $arguments)
        {
            self::$calls++;
            throw new \RuntimeException('Forbidden database call: ' . $name);
        }
    }
}

namespace addons\shop\library\v5 {
    function curl_init($url = null)
    {
        $GLOBALS['referenceContractHttpCalls'] = ($GLOBALS['referenceContractHttpCalls'] ?? 0) + 1;
        throw new \RuntimeException('Forbidden HTTP call');
    }

    $files = ['DomainException.php', 'Json.php', 'AgentMealSourceService.php', 'AgentSkuSelectionService.php',
        'RecommendationPackageService.php', 'PurchaseListService.php', 'MealCommerceService.php'];
    foreach ($files as $file) {
        $source = $GLOBALS['referenceContractSources'][$file]
            ?? file_get_contents(dirname(__DIR__, 2) . '/addons/shop/library/v5/' . $file);
        eval('?>' . $source);
    }

    class SyntheticReferenceVerifier extends AgentMealSourceService
    {
        public $receipts = [];

        /** 用合成签名和保存回执替换外部 HTTP，生产签名服务须独立验收。 */
        public function validateProof(array $proof)
        {
            $raw = $proof['payload'] ?? '';
            if (!hash_equals(hash_hmac('sha256', $raw, 'synthetic-contract-only'), $proof['signature'] ?? '')
                || !isset($this->receipts[$raw])) {
                throw new DomainException('Synthetic saved source rejected', 40301, 403);
            }
            return $this->receipts[$raw];
        }
    }

    function referenceAssert($condition, $message)
    {
        if (!$condition) throw new \RuntimeException($message);
    }

    function referenceReject($callback, $code)
    {
        try { $callback(); }
        catch (DomainException $error) {
            referenceAssert($error->getCode() === $code, 'Wrong rejection code');
            return;
        }
        throw new \RuntimeException('Expected rejection ' . $code);
    }

    function referenceCase($name, $callback)
    {
        try { $callback(); }
        catch (\Throwable $error) { throw new \RuntimeException($name . ': ' . $error->getMessage(), 0, $error); }
        $GLOBALS['referenceContractCases'][] = $name;
    }

    /** 回执只给出已保存的包装数量，不生成营养数值。 */
    function referenceFixture($kind = 'reference_plan')
    {
        $source = ['kind'=>$kind, 'uid'=>'synthetic-a', 'preview_id'=>'synthetic-preview',
            'request_id'=>'synthetic-request', 'trade_policy'=>'catalog_v1'];
        $raw = Json::canonical($source);
        $proof = ['payload'=>$raw, 'signature'=>hash_hmac('sha256', $raw, 'synthetic-contract-only')];
        $version = $kind === 'reference_plan' ? 'reference:synthetic-preview' : 'conversation:synthetic-request';
        $payload = ['user_ref'=>'uid:synthetic-a', 'family_ref'=>$version, 'menu_version_ref'=>$version,
            'ingredient_requirements'=>[], 'nutrition_validation'=>['status'=>'reference_only'],
            'items'=>[['sku_id'=>'11', 'quantity'=>2], ['sku_id'=>'22', 'quantity'=>1]], 'agent_source_proof'=>$proof];
        $verifier = new SyntheticReferenceVerifier();
        $verifier->receipts[$raw] = ['available'=>true, 'selection_mode'=>'reference', 'items'=>$payload['items']];
        return [$verifier, $payload];
    }

    $GLOBALS['referenceContractCases'] = [];
    referenceCase('all five candidate services load without application bootstrap', function () {
        foreach (['AgentMealSourceService', 'AgentSkuSelectionService', 'RecommendationPackageService',
            'PurchaseListService', 'MealCommerceService'] as $name) {
            referenceAssert(class_exists(__NAMESPACE__ . '\\' . $name, false), 'Missing candidate service');
        }
    });
    foreach (['reference_plan', 'conversation_catalog'] as $kind) {
        referenceCase($kind . ' accepts saved signed reference with empty requirements', function () use ($kind) {
            [$verifier, $payload] = referenceFixture($kind);
            referenceAssert($verifier->validateReferencePayload($payload) === true, 'Valid reference rejected');
        });
    }
    foreach (['owner', 'version', 'quantity', 'sku', 'empty_items', 'duplicate', 'zero', 'fraction', 'status', 'signature', 'saved_source'] as $mode) {
        referenceCase('reference rejects ' . $mode, function () use ($mode) {
            [$verifier, $payload] = referenceFixture();
            $code = 40301;
            if ($mode === 'owner') $payload['user_ref'] = 'uid:synthetic-other';
            if ($mode === 'version') $payload['menu_version_ref'] = 'reference:synthetic-other';
            if ($mode === 'quantity') $payload['items'][0]['quantity'] = 3;
            if ($mode === 'sku') $payload['items'][0]['sku_id'] = '33';
            if ($mode === 'empty_items') $payload['items'] = [];
            if ($mode === 'duplicate') { $payload['items'][] = $payload['items'][0]; $code = 40004; }
            if ($mode === 'zero') { $payload['items'][0]['quantity'] = 0; $code = 40004; }
            if ($mode === 'fraction') { $payload['items'][0]['quantity'] = 1.5; $code = 40004; }
            if ($mode === 'status') $payload['nutrition_validation']['status'] = 'passed';
            if ($mode === 'signature') $payload['agent_source_proof']['signature'] = str_repeat('0', 64);
            if ($mode === 'saved_source') $verifier->receipts = [];
            referenceReject(function () use ($verifier, $payload) { $verifier->validateReferencePayload($payload); }, $code);
        });
    }
    referenceCase('reference rejects a saved receipt with empty expected items', function () {
        [$verifier, $payload] = referenceFixture();
        $verifier->receipts[$payload['agent_source_proof']['payload']]['items'] = [];
        referenceReject(function () use ($verifier, $payload) { $verifier->validateReferencePayload($payload); }, 40301);
    });
    referenceCase('reference requires reference selection mode in current receipt', function () {
        [$verifier, $payload] = referenceFixture();
        $verifier->receipts[$payload['agent_source_proof']['payload']]['selection_mode'] = 'formal';
        referenceReject(function () use ($verifier, $payload) { $verifier->validateReferencePayload($payload); }, 40301);
    });
    foreach (['family', 'requirements'] as $mode) {
        referenceCase('conversation reference rejects ' . $mode, function () use ($mode) {
            [$verifier, $payload] = referenceFixture('conversation_catalog');
            if ($mode === 'family') $payload['family_ref'] = 'conversation:synthetic-other';
            else $payload['ingredient_requirements'] = [['ingredient_id'=>'synthetic']];
            referenceReject(function () use ($verifier, $payload) { $verifier->validateReferencePayload($payload); }, 40301);
        });
    }
    referenceCase('formal legacy source retains non-reference branch', function () {
        $verifier = new SyntheticReferenceVerifier();
        referenceAssert($verifier->validateReferencePayload(['agent_source_proof'=>[]]) === false, 'Legacy source promoted');
        referenceAssert(AgentMealSourceService::nutritionAllowsTrade(['nutrition_status'=>'passed']), 'Formal passed rejected');
    });
    referenceCase('unrecognized reference_only cannot trade', function () {
        referenceAssert(!AgentMealSourceService::nutritionAllowsTrade(['nutrition_status'=>'reference_only']), 'Missing source accepted');
        $proof = ['payload'=>Json::encode(['kind'=>'conversation_catalog', 'trade_policy'=>'unrecognized'])];
        referenceAssert(!AgentMealSourceService::nutritionAllowsTrade([
            'nutrition_status'=>'reference_only', 'agent_source_proof_json'=>Json::encode($proof)]), 'Unknown policy accepted');
    });
    referenceCase('saved reference stays reference_only rather than passed', function () {
        [, $payload] = referenceFixture();
        $package = ['nutrition_status'=>'reference_only', 'agent_source_proof_json'=>Json::encode($payload['agent_source_proof'])];
        referenceAssert(AgentMealSourceService::nutritionAllowsTrade($package), 'Reference trade not allowed');
        referenceAssert($package['nutrition_status'] === 'reference_only', 'Reference promoted to passed');
    });
    referenceCase('legacy create still rejects empty ingredient requirements before database access', function () {
        referenceReject(function () {
            (new RecommendationPackageService())->create('synthetic', ['agent_task_id'=>'synthetic', 'family_ref'=>'synthetic',
                'user_ref'=>'synthetic', 'menu_version_ref'=>'synthetic', 'catalog_version'=>'synthetic',
                'nutrition_validation'=>['status'=>'passed'], 'ingredient_requirements'=>[]], 'synthetic');
        }, 40004);
    });

    $authority = ['user_ref'=>'uid:synthetic-a', 'family_ref'=>'synthetic-family', 'menu_version_ref'=>'synthetic-v1',
        'nutrition_validation'=>['status'=>'passed'], 'items'=>[['sku_id'=>'11', 'quantity'=>2]],
        'ingredient_requirements'=>[['sku_id'=>'11', 'food_id'=>'synthetic-food', 'source_ref'=>'synthetic-source',
            'merchant_snapshot'=>['sku_id'=>'11'], 'required_value'=>100, 'required_unit'=>'g']]];
    referenceCase('formal direct SKU keeps passed authority branch', function () use ($authority) {
        referenceAssert(AgentSkuSelectionService::hasDirect($authority['ingredient_requirements']), 'Missing direct SKU');
        referenceAssert(!AgentSkuSelectionService::hasDirect([]), 'Reference misclassified as formal SKU');
        AgentSkuSelectionService::assertReceipt($authority, ['available'=>true, 'purchase_authority'=>$authority]);
    });
    foreach (['owner', 'version', 'sku', 'quantity', 'empty_items', 'reference_status'] as $mode) {
        referenceCase('formal direct SKU rejects ' . $mode, function () use ($authority, $mode) {
            $payload = $authority;
            $receipt = ['available'=>true, 'purchase_authority'=>$authority];
            if ($mode === 'owner') $payload['user_ref'] = 'uid:synthetic-other';
            if ($mode === 'version') $payload['menu_version_ref'] = 'synthetic-other';
            if ($mode === 'sku') $payload['items'][0]['sku_id'] = '22';
            if ($mode === 'quantity') $payload['items'][0]['quantity'] = 3;
            if ($mode === 'empty_items') $payload['items'] = [];
            if ($mode === 'reference_status') $receipt['purchase_authority']['nutrition_validation']['status'] = 'reference_only';
            referenceReject(function () use ($payload, $receipt) { AgentSkuSelectionService::assertReceipt($payload, $receipt); }, 40944);
        });
    }
    referenceAssert(\think\Db::$calls === 0 && ($GLOBALS['referenceContractHttpCalls'] ?? 0) === 0, 'External boundary used');
    echo json_encode(['status'=>'passed', 'cases'=>$GLOBALS['referenceContractCases'],
        'scope'=>'synthetic pure boundaries; signed-source HTTP and PostgreSQL/checkout not exercised',
        'database_calls'=>\think\Db::$calls, 'http_calls'=>$GLOBALS['referenceContractHttpCalls'] ?? 0,
        'business_writes'=>0], JSON_UNESCAPED_SLASHES) . "\n";
}
