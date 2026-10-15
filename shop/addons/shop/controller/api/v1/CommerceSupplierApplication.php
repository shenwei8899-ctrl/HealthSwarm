<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\Identifiers;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\Json;
use think\Db;

class CommerceSupplierApplication extends Base
{
    public function create()
    {
        return $this->execute(function () {
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.supplier_application.create', 'miniapp:' . $userId, $this->request->header('idempotency-key'), $payload, function () use ($payload, $userId) {
                foreach (['company_name', 'contact_name', 'contact_mobile', 'privacy_consent_version'] as $field) {
                    if (empty($payload[$field]) || !is_string($payload[$field]) || !trim($payload[$field])) {
                        throw new DomainException('缺少必填字段: ' . $field, 40001, 400);
                    }
                }
                if (!preg_match('/^1\d{10}$/', (string)$payload['contact_mobile']) || mb_strlen($payload['company_name']) > 200 || mb_strlen($payload['contact_name']) > 100) {
                    throw new DomainException('联系人信息格式无效', 40001, 400);
                }
                foreach (['business_categories', 'service_areas', 'qualification_files'] as $field) {
                    if (isset($payload[$field]) && !is_array($payload[$field])) throw new DomainException('申请资料格式无效', 40001, 400);
                }
                $sn = Identifiers::make('supplierapply');
                $type = isset($payload['partner_type']) ? $payload['partner_type'] : 'supplier';
                if (!in_array($type, ['supplier', 'channel', 'distributor'], true)) throw new DomainException('合作类型无效', 40001, 400);
                Db::name('shop_supplier_application')->insert([
                    'application_sn' => $sn, 'user_id' => $userId, 'company_name' => $payload['company_name'], 'partner_type' => $type,
                    'credit_code' => isset($payload['credit_code']) ? $payload['credit_code'] : '',
                    'contact_name' => $payload['contact_name'],
                    'contact_mobile_encrypted' => \addons\shop\library\v5\SecretCipher::encrypt($payload['contact_mobile']),
                    'business_categories_json' => Json::encode(isset($payload['business_categories']) ? $payload['business_categories'] : []),
                    'service_areas_json' => Json::encode(isset($payload['service_areas']) ? $payload['service_areas'] : []),
                    'capacity_summary' => isset($payload['capacity_summary']) ? $payload['capacity_summary'] : '',
                    'qualification_files_json' => Json::encode(isset($payload['qualification_files']) ? $payload['qualification_files'] : []),
                    'privacy_consent_version' => $payload['privacy_consent_version'],
                    'review_status' => 'pending', 'submitted_at' => time(), 'status' => 'normal', 'version' => 1,
                    'createtime' => time(), 'updatetime' => time(),
                ]);
                return ['application_sn' => $sn, 'review_status' => 'pending'];
            });
        });
    }

    public function detail($application_sn = null)
    {
        $application_sn = $application_sn ?? $this->request->route('application_sn');
        return $this->execute(function () use ($application_sn) {
            $row = Db::name('shop_supplier_application')->where('application_sn', $application_sn)->where('user_id', $this->userId())->find();
            if (!$row) {
                throw new DomainException('合作申请不存在', 40413, 404);
            }
            unset($row['contact_mobile_encrypted']);
            return $row;
        });
    }
}
