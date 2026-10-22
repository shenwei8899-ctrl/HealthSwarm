// 仅显式开启的本机联调构建可以使用业务密码登录。
export function canUseLocalBusinessLogin(env, { platform = '', hostname = '' } = {}) {
  return env.VITE_LOCAL_BUSINESS_LOGIN === '1' && env.VITE_SERVICE_MODE === 'api' &&
    env.VITE_ALLOW_LOCAL_HEALTH_API === '1' &&
    /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(env.VITE_API_BASE_URL || '') &&
    (platform === 'devtools' || ['localhost', '127.0.0.1'].includes(hostname))
}

// 独立 H5 测试包只在明确指定的站点使用同源真实服务；不影响正式微信构建。
export function canUseH5TestBusinessLogin(env, { h5 = false, origin = '' } = {}) {
  if (!h5 || env.VITE_H5_TEST_LOGIN !== '1' || env.VITE_SERVICE_MODE !== 'api' ||
      env.VITE_API_BASE_URL !== '' || !origin || origin !== env.VITE_H5_TEST_ORIGIN) return false
  try {
    const target = new URL(env.VITE_H5_TEST_ORIGIN)
    return ['http:', 'https:'].includes(target.protocol) && target.origin === env.VITE_H5_TEST_ORIGIN
  } catch { return false }
}
