// 仅显式开启的本机联调构建可以使用业务密码登录。
export function canUseLocalBusinessLogin(env, { platform = '', hostname = '' } = {}) {
  return env.VITE_LOCAL_BUSINESS_LOGIN === '1' && env.VITE_SERVICE_MODE === 'api' &&
    env.VITE_ALLOW_LOCAL_HEALTH_API === '1' &&
    /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(env.VITE_API_BASE_URL || '') &&
    (platform === 'devtools' || ['localhost', '127.0.0.1'].includes(hostname))
}
