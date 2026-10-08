<?php

namespace addons\shop\library\v5;

class AlertService
{
    public static function notify($event, $message, array $context = [])
    {
        $url = trim((string)getenv('ALERT_WEBHOOK_URL'));
        if ($url === '' || !function_exists('curl_init')) {
            return false;
        }
        $payload = json_encode([
            'event' => (string)$event,
            'message' => (string)$message,
            'context' => $context,
            'occurred_at' => date(DATE_ATOM),
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $curl = curl_init($url);
        curl_setopt_array($curl, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 2,
            CURLOPT_TIMEOUT => 4,
        ]);
        $result = curl_exec($curl);
        $ok = $result !== false && curl_getinfo($curl, CURLINFO_HTTP_CODE) < 400;
        curl_close($curl);
        return $ok;
    }
}
