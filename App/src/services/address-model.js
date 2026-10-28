export function addressPayload(form) {
  const data = {
    name: String(form.name || '').trim(), phone: String(form.phone || '').trim(),
    region: String(form.region || '').trim(), area_id: String(form.area_id || ''),
    detail: String(form.detail || '').trim(),
  }
  if (form.id) { data.id = String(form.id); data.version = Number(form.version) }
  if (typeof form.isDefault === 'boolean') data.isDefault = form.isDefault
  if (typeof form.label === 'string') data.label = form.label.trim()
  return data
}
export function addressErrors(data) {
  const errors = {}
  if (!data.name || [...data.name].length > 50) errors.name = '请填写收货人姓名，最多 50 个字'
  if (!/^1\d{10}$/.test(data.phone)) errors.phone = '请输入正确的 11 位手机号'
  if (!data.area_id || !data.region) errors.region = '请选择完整的省、市、区'
  if (!data.detail || [...data.detail].length > 200) errors.detail = '请填写街道、楼栋及门牌号，最多 200 个字'
  if (data.label && [...data.label].length > 10) errors.label = '地址标签最多 10 个字'
  return errors
}
export function resolveCheckoutAddress(items, preferredId) {
  if (preferredId !== undefined && preferredId !== null && preferredId !== '') return items.find(item => String(item.id) === String(preferredId)) || null
  return items.find(item => item.isDefault) || items[0] || null
}
export function addressText(address) { return `${address.name} ${address.phone}\n${address.region} ${address.detail}` }
export function regionColumns(directory, indices) {
  const provinces = directory.filter(item => Number(item.level) === 1)
  const cities = directory.filter(item => String(item.pid) === String(provinces[indices[0]]?.id))
  const districts = directory.filter(item => String(item.pid) === String(cities[indices[1]]?.id))
  return [provinces, cities, districts]
}
export function regionIndices(directory, areaId) {
  const district = directory.find(item => String(item.id) === String(areaId))
  const city = directory.find(item => String(item.id) === String(district?.pid))
  const provinces = directory.filter(item => Number(item.level) === 1)
  const p = Math.max(0, provinces.findIndex(item => String(item.id) === String(city?.pid)))
  const cities = regionColumns(directory, [p, 0, 0])[1]
  const c = Math.max(0, cities.findIndex(item => String(item.id) === String(city?.id)))
  const districts = regionColumns(directory, [p, c, 0])[2]
  return [p, c, Math.max(0, districts.findIndex(item => String(item.id) === String(areaId)))]
}
