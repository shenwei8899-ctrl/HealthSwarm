<?php

namespace addons\shop\library\v5;

use think\Db;

class IdempotencyService
{
    public function run($scope, $clientId, $key, array $payload, callable $callback, $ttl = 86400)
    {
        $key = trim((string)$key);
        if ($key === '' || strlen($key) > 64) {
            throw new DomainException('Idempotency-Key缺失或长度无效', 40003, 400);
        }
        $hash = hash('sha256', Json::canonical($payload));
        $now = time();
        $record = Db::name('shop_idempotency_record')->where([
            'scope'          => $scope,
            'client_id'      => $clientId,
            'idempotency_key'=> $key,
        ])->find();

        if ($record) {
            if (!hash_equals($record['request_hash'], $hash)) {
                throw new DomainException('相同幂等键对应了不同请求内容', 40901, 409);
            }
            if ($record['status'] === 'succeeded') {
                return Json::decode($record['response_body'], []);
            }
            if ($record['status'] === 'processing' && (int)$record['locked_until'] > $now) {
                throw new DomainException('相同请求正在处理中', 40902, 409, ['retryable' => true]);
            }
            Db::name('shop_idempotency_record')->where('id', $record['id'])->update([
                'status'       => 'processing',
                'locked_until' => $now + 60,
                'updatetime'   => $now,
            ]);
            $id = $record['id'];
        } else {
            try {
                $id = Db::name('shop_idempotency_record')->insertGetId([
                    'scope'           => $scope,
                    'client_id'       => $clientId,
                    'idempotency_key' => $key,
                    'request_hash'    => $hash,
                    'status'          => 'processing',
                    'locked_until'    => $now + 60,
                    'expires_at'      => $now + $ttl,
                    'createtime'      => $now,
                    'updatetime'      => $now,
                ]);
            } catch (\Exception $e) {
                throw new DomainException('相同请求正在处理中', 40902, 409, ['retryable' => true]);
            }
        }

        try {
            $result = call_user_func($callback);
            Db::name('shop_idempotency_record')->where('id', $id)->update([
                'response_code'=> 0,
                'response_body'=> Json::encode($result),
                'status'       => 'succeeded',
                'locked_until' => 0,
                'updatetime'   => time(),
            ]);
            return $result;
        } catch (\Exception $e) {
            Db::name('shop_idempotency_record')->where('id', $id)->update([
                'response_code'=> $e->getCode() ?: 50000,
                'response_body'=> Json::encode(['message' => $e->getMessage()]),
                'status'       => 'failed',
                'locked_until' => 0,
                'updatetime'   => time(),
            ]);
            throw $e;
        }
    }
}
