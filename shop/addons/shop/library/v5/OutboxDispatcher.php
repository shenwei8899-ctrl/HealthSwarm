<?php

namespace addons\shop\library\v5;

use think\Db;

class OutboxDispatcher
{
    public function dispatch($limit = 100)
    {
        $events = Db::name('shop_outbox_event')->where('status', 'in', ['pending', 'failed'])
            ->where('next_retry_at', '<=', time())->order('id', 'asc')->limit((int)$limit)->select();
        $processed = 0;
        foreach ($events as $event) {
            $processed++;
            if ($event['destination'] === 'miniapp') {
                Db::name('shop_outbox_event')->where('id', $event['id'])->update(['status' => 'sent', 'sent_at' => time(), 'updatetime' => time()]);
                continue;
            }
            if (strpos($event['destination'], 'supplier:') === 0) {
                Db::name('shop_outbox_event')->where('id', $event['id'])->update(['status' => 'sent', 'sent_at' => time(), 'updatetime' => time()]);
                continue;
            }
            $config = get_addon_config('shop');
            $url = isset($config['v5_agent_callback_url']) ? trim($config['v5_agent_callback_url']) : '';
            $clientId = isset($config['v5_agent_client_id']) ? trim($config['v5_agent_client_id']) : '';
            if ($event['destination'] !== 'agent' || !$url || !$clientId) {
                Db::name('shop_outbox_event')->where('id', $event['id'])->update([
                    'last_error' => 'waiting_for_destination_configuration', 'next_retry_at' => time() + 3600, 'updatetime' => time(),
                ]);
                continue;
            }
            $client = Db::name('shop_integration_client')->where('client_id', $clientId)->where('status', 'normal')->find();
            if (!$client) {
                Db::name('shop_outbox_event')->where('id', $event['id'])->update([
                    'last_error' => 'agent_client_not_found', 'next_retry_at' => time() + 3600, 'updatetime' => time(),
                ]);
                continue;
            }
            $payload = [
                'event_id' => $event['event_id'], 'event_type' => $event['event_type'],
                'occurred_at' => date(DATE_ATOM, (int)$event['createtime']),
                'resource_type' => $event['aggregate_type'], 'resource_ref' => $event['aggregate_ref'],
                'resource_version' => (int)$event['aggregate_version'], 'data' => Json::decode($event['payload_json'], []),
            ];
            $timestamp = time();
            $nonce = bin2hex(random_bytes(16));
            try {
                $signature = SignatureService::sign('POST', parse_url($url, PHP_URL_PATH), $timestamp, $nonce, Json::encode($payload), SecretCipher::decrypt($client['secret_ciphertext']));
                (new HttpClient())->postJson($url, $payload, [
                    'X-Client-Id' => 'shop', 'X-Timestamp' => $timestamp, 'X-Nonce' => $nonce,
                    'X-Signature' => $signature, 'Idempotency-Key' => $event['event_id'],
                ]);
                Db::name('shop_outbox_event')->where('id', $event['id'])->update([
                    'status' => 'sent', 'attempts' => (int)$event['attempts'] + 1,
                    'sent_at' => time(), 'last_error' => '', 'updatetime' => time(),
                ]);
            } catch (\Exception $e) {
                $attempts = (int)$event['attempts'] + 1;
                Db::name('shop_outbox_event')->where('id', $event['id'])->update([
                    'status' => 'failed', 'attempts' => $attempts,
                    'next_retry_at' => time() + min(3600, (int)pow(2, min($attempts, 10)) * 30),
                    'last_error' => mb_substr($e->getMessage(), 0, 1000), 'updatetime' => time(),
                ]);
            }
        }
        return $processed;
    }
}
