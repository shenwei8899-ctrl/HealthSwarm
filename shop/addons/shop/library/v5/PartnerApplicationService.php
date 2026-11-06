<?php

namespace addons\shop\library\v5;

use think\Config;
use think\Db;

class PartnerApplicationService
{
    const POLICY = 'partner-contact-20261101';

    /** 非空提交编号属于合作意向，包括合法编号 0。 */
    public static function isContactIntake(array $application)
    {
        return isset($application['submission_key']) && $application['submission_key'] !== '';
    }

    /** 提交能力仅在对应迁移完成后开放。 */
    public function policy()
    {
        if (strtolower((string)Config::get('database.type')) !== 'pgsql') {
            throw new DomainException('合作申请需要 PostgreSQL 接收服务，请联系管理员完成配置', 50301, 503);
        }
        if (!Db::name('shop_schema_migration')->where('version', '20261101_partner_intake')->find()) {
            throw new DomainException('合作申请暂时无法提交，请稍后重试', 50301, 503);
        }
        return ['policy_version' => self::POLICY];
    }

    /** 申请事实和提交编号在同一事务中保存，丢失响应时返回原申请。 */
    public function submit($userId, $key, array $input)
    {
        $this->policy();
        $key = trim((string)$key);
        if ($key === '' || strlen($key) > 64 || preg_match('/[\x00-\x1f\x7f]/', $key)) {
            throw new DomainException('提交编号无效，请重新进入申请页面', 40003, 400);
        }
        $payload = $this->normalize($input);
        $hash = hash('sha256', Json::canonical($payload));
        Db::startTrans();
        try {
            if (!Db::name('user')->where('id', $userId)->lock(true)->find()) {
                throw new DomainException('请先登录', 40100, 401);
            }
            $row = Db::name('shop_supplier_application')->where('user_id', $userId)->where('submission_key', $key)->find();
            if ($row && !hash_equals($row['submission_hash'], $hash)) {
                throw new DomainException('该提交编号已保存其他内容，请重新填写', 40901, 409);
            }
            if (!$row) {
                $location = $this->location($payload['location_area_id']);
                $now = time();
                $row = [
                    'application_sn' => Identifiers::make('supplierapply'), 'user_id' => $userId,
                    'partner_type' => $payload['partner_type'], 'company_name' => $payload['company_name'],
                    'contact_name' => $payload['contact_name'],
                    'contact_mobile_encrypted' => SecretCipher::encrypt($payload['contact_mobile']),
                    'contact_wechat' => $payload['contact_wechat'], 'location_json' => Json::encode($location),
                    'capacity_summary' => $payload['capacity_summary'],
                    'business_categories_json' => '[]', 'service_areas_json' => '[]', 'qualification_files_json' => '[]',
                    'privacy_consent_version' => self::POLICY, 'submission_key' => $key, 'submission_hash' => $hash,
                    'review_status' => 'pending', 'follow_up_status' => 'pending', 'status' => 'normal', 'version' => 1,
                    'submitted_at' => $now, 'createtime' => $now, 'updatetime' => $now,
                ];
                Db::name('shop_supplier_application')->insert($row);
            }
            Db::commit();
        } catch (\Throwable $error) {
            Db::rollback();
            throw $error;
        }
        return ['application_sn' => $row['application_sn'], 'submitted_at' => (int)$row['submitted_at'], 'policy_version' => self::POLICY];
    }

    /** 管理员在完成权限检查后调用，明文联系方式仅返回专用详情。 */
    public function detail($id)
    {
        $row = Db::name('shop_supplier_application')->where('id', (int)$id)->find();
        if (!$row) throw new DomainException('合作申请不存在', 40413, 404);
        return [
            'id' => (int)$row['id'], 'application_sn' => $row['application_sn'], 'partner_type' => $row['partner_type'],
            'company_name' => $row['company_name'], 'contact_name' => $row['contact_name'],
            'contact_mobile' => SecretCipher::decrypt($row['contact_mobile_encrypted']),
            'contact_wechat' => $row['contact_wechat'] ?? '', 'location' => Json::decode($row['location_json'] ?? '', []),
            'capacity_summary' => $row['capacity_summary'], 'submitted_at' => (int)$row['submitted_at'],
            'follow_up_status' => $row['follow_up_status'] ?? 'pending', 'follow_up_note' => $row['follow_up_note'] ?? '',
            'version' => (int)$row['version'],
        ];
    }

    /** 人工跟进只更新备注和联系状态，不创建正式供应商。 */
    public function followUp($id, $adminId, array $input)
    {
        $status = $input['follow_up_status'] ?? '';
        if (!in_array($status, ['pending', 'contacted', 'closed'], true)) throw new DomainException('跟进状态无效', 40001, 400);
        $note = $this->text($input, 'follow_up_note', 1000, false);
        if (!isset($input['version']) || !ctype_digit((string)$input['version'])) throw new DomainException('申请版本无效', 40001, 400);
        Db::startTrans();
        try {
            $row = Db::name('shop_supplier_application')->where('id', (int)$id)->lock(true)->find();
            if (!$row) throw new DomainException('合作申请不存在', 40413, 404);
            if ((int)$row['version'] !== (int)$input['version']) throw new DomainException('申请已被其他人员更新，请重新打开', 40910, 409);
            Db::name('shop_supplier_application')->where('id', $row['id'])->update([
                'follow_up_status' => $status, 'follow_up_note' => $note, 'follow_up_admin_id' => (int)$adminId,
                'follow_up_at' => time(), 'version' => (int)$row['version'] + 1, 'updatetime' => time(),
            ]);
            Db::commit();
        } catch (\Throwable $error) { Db::rollback(); throw $error; }
    }

    private function normalize(array $input)
    {
        if (!isset($input['partner_type']) || !in_array($input['partner_type'], ['supplier', 'channel', 'distributor'], true)) {
            throw new DomainException('请选择合作类型', 40001, 400);
        }
        if (($input['privacy_consent_version'] ?? '') !== self::POLICY) throw new DomainException('请确认合作联系说明', 40001, 400);
        $payload = ['partner_type' => $input['partner_type'], 'privacy_consent_version' => self::POLICY];
        foreach (['company_name' => 200, 'contact_name' => 100, 'contact_mobile' => 11, 'capacity_summary' => 500] as $field => $limit) {
            $payload[$field] = $this->text($input, $field, $limit);
        }
        $payload['contact_wechat'] = $this->text($input, 'contact_wechat', 64, false);
        if (!preg_match('/^1\d{10}$/D', $payload['contact_mobile'])) throw new DomainException('请填写11位手机号', 40001, 400);
        if (!isset($input['location_area_id']) || !ctype_digit((string)$input['location_area_id']) || (int)$input['location_area_id'] < 1) {
            throw new DomainException('请选择所在省、市、区', 40001, 400);
        }
        $payload['location_area_id'] = (int)$input['location_area_id'];
        return $payload;
    }

    private function location($id)
    {
        $rows = [];
        for ($level = 3; $level >= 1; $level--) {
            $row = Db::name('shop_area')->where('id', $id)->where('status', 'normal')->where('level', $level)->find();
            if (!$row) throw new DomainException('地区信息已变化，请重新选择省、市、区', 40001, 400);
            array_unshift($rows, ['id' => (int)$row['id'], 'name' => $row['name']]);
            $id = $row['pid'];
        }
        return $rows;
    }

    private function text(array $input, $field, $limit, $required = true)
    {
        $value = $input[$field] ?? '';
        if (!is_string($value)) throw new DomainException('填写信息格式无效', 40001, 400);
        $value = trim($value);
        if (($required && $value === '') || mb_strlen($value, 'UTF-8') > $limit || preg_match('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/u', $value)) {
            throw new DomainException('请完整填写信息并检查长度', 40001, 400);
        }
        return $value;
    }
}
