import {apiBaseUrl} from './config.js'
let sameOrigin=''
// #ifdef H5
// uni-image resolves a root-relative URL against its H5 base; use a complete same-origin URL.
if(typeof window!=='undefined')sameOrigin=window.location.origin
// #endif

export function publicImageUrl(value,{baseUrl=apiBaseUrl,origin=sameOrigin}={}) {
  if(typeof value!=='string'||!value)return ''
  const path=value.replace(/^http:\/\/8\.136\.134\.29(?=\/uploads\/)/,'')
  if(path.startsWith('/minio/public/')||path.startsWith('/uploads/'))return (baseUrl||origin).replace(/\/$/,'')+path
  return value
}
