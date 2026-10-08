<?php

namespace addons\shop\library\message;

use fast\Http;
use GuzzleHttp\Client;
use GuzzleHttp\Psr7\Response;
use think\Cache;
use think\Log;
use think\Config;

class Mp
{

    private $appId = '';
    private $appSecret = '';

    public function __construct()
    {
        $config = get_addon_config('shop');
        $this->appId = $config['mp_appid'];
        $this->appSecret = $config['mp_app_secret'];
    }

    private function getAccessToken()
    {
        $access_token = Cache::get('shop' . $this->appId);
        if (!$access_token) {
            $url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=' . $this->appId . '&secret=' . $this->appSecret;
            $res = Http::get($url);
            $res = (array)json_decode($res, true);
            if (isset($res['access_token'])) {
                $access_token = $res['access_token'];
            } else if (Config::get('app_debug')) {
                Log::write('code:' . $res['errcode'] . ',message：' . $res['errmsg'], 'access_token');
            }
            Cache::set('shop' . $this->appId, $access_token, 7000);
        }
        return $access_token;
    }



    /**
     * 批量并发发送
     * @param array $pushList
     * @return bool
     */
    public function sendTemplateMessageMultiple($pushList)
    {
        $url = 'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=' . $this->getAccessToken();
        $concurrentSize = 10;
        $promises = [];
        $client = new Client();
        $promiseProcess = function ($promises) {
            $results = \GuzzleHttp\Promise\Utils::unwrap($promises);
            foreach ($results as $key => $response) {
                $res = (array)json_decode($response->getBody()->getContents(), true);
                if (isset($res['errmsg']) && Config::get('app_debug')) {
                    Log::write($res, 'send_msg');
                }
            }
        };
        foreach ($pushList as $index => $item) {
            $promises[] = $client->postAsync($url, ['body' => json_encode($item, JSON_UNESCAPED_UNICODE)]);
            if (count($promises) == $concurrentSize) {
                $promiseProcess($promises);
                $promises = [];
            }
        }
        if ($promises) {
            $promiseProcess($promises);
        }
        return true;
    }

    /**
     * 单次异步发送
     * @param array $pushData
     * @return bool
     */
    public function send($pushData)
    {
        $url = 'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=' . $this->getAccessToken();
        $client = new Client();
        $client->postAsync($url, ['body' => json_encode($pushData, JSON_UNESCAPED_UNICODE)])->then(function (Response $response) {
            $res = (array)json_decode($response->getBody()->getContents(), true);
            if (isset($res['errmsg']) && Config::get('app_debug')) {
                Log::write($res, 'send_msg');
                return false;
            }
        })->wait();
        return true;
    }
}
