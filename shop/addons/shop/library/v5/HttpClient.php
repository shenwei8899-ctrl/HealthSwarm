<?php

namespace addons\shop\library\v5;

class HttpClient
{
    public function postJson($url, array $payload, array $headers = [], $timeout = 10)
    {
        if (!filter_var($url, FILTER_VALIDATE_URL) || !in_array(parse_url($url, PHP_URL_SCHEME), ['http', 'https'], true)) {
            throw new DomainException('外部接口地址无效', 50020, 500);
        }
        $body = Json::encode($payload);
        $headerLines = ['Content-Type: application/json', 'Accept: application/json'];
        foreach ($headers as $name => $value) {
            $headerLines[] = $name . ': ' . $value;
        }
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body, CURLOPT_HTTPHEADER => $headerLines,
            CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => min(5, $timeout), CURLOPT_TIMEOUT => $timeout,
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_MAXREDIRS => 0,
        ]);
        $started = microtime(true);
        $response = curl_exec($ch);
        $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);
        $duration = (int)round((microtime(true) - $started) * 1000);
        if ($response === false || $status < 200 || $status >= 300) {
            throw new DomainException('外部接口调用失败: ' . ($error ?: 'HTTP ' . $status), 50202, 502, [
                'http_status' => $status, 'duration_ms' => $duration,
            ]);
        }
        return ['status' => $status, 'body' => Json::decode($response, ['raw' => mb_substr($response, 0, 2000)]), 'duration_ms' => $duration];
    }
}
