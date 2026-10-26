<?php
namespace addons\shop\library\v5;

use think\Cache;

/** Only the server exchanges WeChat phone grants; no credentials are returned to clients. */
class WechatPhoneGateway
{
    public function config()
    {
        // Dedicated credentials must not enable the legacy standalone account registration route.
        $appid = trim((string)getenv('SHOP_WECHAT_PHONE_APP_ID'));
        $enabled = getenv('SHOP_WECHAT_PHONE_ENABLED') === 'true';
        $available = $enabled && preg_match('/^wx[0-9a-f]{16}$/D', $appid) && trim((string)getenv('SHOP_WECHAT_PHONE_APP_SECRET')) !== '';
        return ['available'=>(bool)$available, 'appid'=>$available ? $appid : null,
            'reason'=>$available ? null : 'WECHAT_PHONE_NOT_CONFIGURED'];
    }

    public function exchange($code)
    {
        $config = $this->config();
        if (!$config['available']) throw new DomainException('微信手机号授权尚未配置', 50311, 503);
        $appid = $config['appid'];
        $secret = trim((string)getenv('SHOP_WECHAT_PHONE_APP_SECRET'));
        $cacheKey = 'wechat-phone-token:' . hash('sha256', $appid . ':' . $secret);
        $token = Cache::get($cacheKey);
        if (!is_string($token) || $token === '') {
            $r = $this->post('https://api.weixin.qq.com/cgi-bin/stable_token', [
                'grant_type'=>'client_credential', 'appid'=>$appid, 'secret'=>$secret, 'force_refresh'=>false,
            ]);
            if (!empty($r['errcode']) || !is_string($r['access_token'] ?? null) || (int)($r['expires_in'] ?? 0) <= 120) {
                throw new DomainException('微信手机号服务凭据不可用，请联系管理员', 50312, 503);
            }
            $token = $r['access_token'];
            Cache::set($cacheKey, $token, min(7000, (int)$r['expires_in'] - 120));
        }
        $r = $this->post('https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token=' . rawurlencode($token), ['code'=>$code]);
        $err = (int)($r['errcode'] ?? -1);
        if (in_array($err, [40001, 40014, 42001], true)) {
            Cache::rm($cacheKey);
            throw new DomainException('微信手机号服务凭据暂不可用，请重新授权后重试', 50312, 503);
        }
        if (in_array($err, [40029, 40163], true)) throw new DomainException('手机号授权已失效，请重新点击微信手机号授权', 40061, 400);
        if ($err !== 0) throw new DomainException('微信手机号验证未完成，请重新授权后重试', 50211, 502);
        return $this->validate($r['phone_info'] ?? null, $appid);
    }

    public function validate($info, $appid)
    {
        if (!is_array($info) || ($info['watermark']['appid'] ?? null) !== $appid) {
            throw new DomainException('手机号授权的小程序来源不一致', 40961, 409);
        }
        $stamp = $info['watermark']['timestamp'] ?? null;
        $country = $info['countryCode'] ?? null;
        $national = $info['purePhoneNumber'] ?? null;
        $full = $info['phoneNumber'] ?? null;
        if (!is_int($stamp) || $stamp < time()-600 || $stamp > time()+120 ||
            !is_string($country) || !preg_match('/^[1-9][0-9]{0,3}$/D', $country) ||
            !is_string($national) || !preg_match('/^[0-9]{5,15}$/D', $national) ||
            strlen($country . $national) > 15 || !is_string($full) ||
            !in_array($full, [$national, $country . $national, '+' . $country . $national], true)) {
            throw new DomainException('微信返回的手机号验证信息无效', 50212, 502);
        }
        return ['country_code'=>$country, 'national_number'=>$national, 'app_id'=>$appid];
    }

    protected function post($url, array $payload)
    {
        $curl = curl_init($url);
        curl_setopt_array($curl, [CURLOPT_POST=>true, CURLOPT_POSTFIELDS=>json_encode($payload),
            CURLOPT_HTTPHEADER=>['Content-Type: application/json'], CURLOPT_RETURNTRANSFER=>true,
            CURLOPT_FOLLOWLOCATION=>false, CURLOPT_CONNECTTIMEOUT=>3, CURLOPT_TIMEOUT=>10,
            CURLOPT_SSL_VERIFYPEER=>true, CURLOPT_SSL_VERIFYHOST=>2]);
        $body = curl_exec($curl); $status = (int)curl_getinfo($curl, CURLINFO_HTTP_CODE); curl_close($curl);
        if ($body === false || $status !== 200 || strlen($body)>65536) {
            throw new DomainException('微信手机号服务暂不可用，请先查询绑定状态再重新授权', 50313, 503);
        }
        $result = json_decode($body, true);
        if (!is_array($result)) throw new DomainException('微信手机号服务响应无效', 50212, 502);
        return $result;
    }
}
