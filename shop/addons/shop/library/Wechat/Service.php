<?php

namespace addons\shop\library\Wechat;

use fast\Http;
use GuzzleHttp\Client;
use GuzzleHttp\Psr7\Response;
use think\Cache;
use think\Log;
use think\Config;

/**
 * 小程序服务类
 */
class Service
{
    private $appId = '';
    private $appSecret = '';

    public function __construct()
    {
        $config = get_addon_config('shop');
        $this->appId = $config['wx_appid'];
        $this->appSecret = $config['wx_app_secret'];
    }

    /**
     * 批量并发发送
     * @param array $pushList
     * @return bool
     */
    public function subscribeMessageSendMultiple($pushList)
    {
        $url = 'https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token=' . $this->getAccessToken();
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
    public function subscribeMessageSend($pushData)
    {
        $url = 'https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token=' . $this->getAccessToken();
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

    //获取access_token
    public function getAccessToken()
    {
        $access_token = Cache::get('shop' . $this->appId);
        if (!$access_token) {
            $url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=' . $this->appId . '&secret=' . $this->appSecret;
            $res = Http::get($url);
            $res = (array)json_decode($res, true);
            if (isset($res['access_token'])) {
                $access_token = $res['access_token'];
            } elseif (Config::get('app_debug')) {
                Log::write('code:' . $res['errcode'] . ',message：' . $res['errmsg'], 'access_token');
            }
            Cache::set('shop' . $this->appId, $access_token, 7000);
        }
        return $access_token;
    }

    //生成小程序码
    public function getWxCodeUnlimited($param)
    {
        $url = 'https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token=' . $this->getAccessToken();
        $data = array_merge([
            'width' => '280'
        ], $param);
        return Http::post($url, json_encode($data, JSON_UNESCAPED_UNICODE));
    }

    //获取手机号
    public function getWechatMobile($code)
    {
        $access_token = $this->getAccessToken();
        $url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={$access_token}";
        $res = Http::post($url, json_encode(['code' => $code]));
        $res = (array)json_decode($res, true);
        if (!isset($res['phone_info']) && config('app_debug')) {
            \think\Log::write($res);
        }
        return $res['phone_info'] ?? [];
    }

    //获取Session信息
    public function getWechatSession($code)
    {
        $params = [
            'appid'      => $this->appId,
            'secret'     => $this->appSecret,
            'js_code'    => $code,
            'grant_type' => 'authorization_code'
        ];
        $result = Http::sendRequest("https://api.weixin.qq.com/sns/jscode2session", $params, 'GET');
        if ($result['ret']) {
            $json = (array)json_decode($result['msg'], true);
            return $json;
        }
        if (config('app_debug')) {
            Log::write($result);
        }
        return ['errmsg' => config('app_debug') ? $result['msg'] : '网络错误'];
    }
}
