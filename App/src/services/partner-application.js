export const partnerPolicyVersion = 'partner-contact-20261101'
export const partnerTypes = [
  { value: 'supplier', label: '供应商', hint: '主要供应哪些产品？可以覆盖哪些城市？能否提供配送？' },
  { value: 'channel', label: '渠道商', hint: '有哪些门店、社群或客户资源？希望怎样开展合作？' },
  { value: 'distributor', label: '经销商', hint: '计划在哪个地区开展业务？目前有哪些销售渠道？' },
]

export function createPartnerApplication({ client, context, newId, reactive = value => value }) {
  const empty = () => ({ type: '', company: '', name: '', phone: '', areaId: '', region: '', note: '', wechat: '', consent: false })
  const state = reactive({ form: empty(), busy: false, saved: false, expired: false, error: '' })
  const owner = context()
  let active = true, generation = 0, fingerprint = '', requestId = ''
  const current = ticket => active && ticket === generation && owner === context()
  function clear() { generation++; state.form = empty(); state.busy = false; state.saved = false; state.expired = true; state.error = '账号已变化，请返回后重新进入' }
  return {
    state,
    checkAccount() { if (owner !== context()) { active = false; clear(); return false } return true },
    dispose() { active = false; clear(); state.error = '' },
    async submit() {
      if (!active || state.busy || state.saved) return
      if (owner !== context()) { active = false; clear(); return }
      const ticket = ++generation
      state.error = ''
      try {
        const f = state.form
        if (!partnerTypes.some(type => type.value === f.type)) throw new Error('请选择合作类型')
        for (const [key, label, max] of [['company','公司／门店名称或个人姓名',200],['name','联系人',100],['phone','手机号',11],['note','合作介绍',500],['wechat','微信号',64]]) {
          if (typeof f[key] !== 'string' || (key !== 'wechat' && !f[key].trim()) || Array.from(f[key].trim()).length > max) throw new Error('请检查' + label)
        }
        if (!/^1\d{10}$/.test(f.phone.trim())) throw new Error('请填写11位手机号')
        if (!/^\d+$/.test(String(f.areaId)) || Number(f.areaId) <= 0 || !f.region) throw new Error('请选择所在省、市、区')
        if (!f.consent) throw new Error('请阅读并同意合作联系说明')
        const payload = { partner_type: f.type, company_name: f.company.trim(), contact_name: f.name.trim(), contact_mobile: f.phone.trim(), location_area_id: Number(f.areaId), capacity_summary: f.note.trim(), contact_wechat: f.wechat.trim(), privacy_consent_version: partnerPolicyVersion }
        const next = JSON.stringify(payload)
        if (next !== fingerprint) { fingerprint = next; requestId = newId() }
        state.busy = true
        await client.submitPartnerApplication(payload, requestId)
        if (!current(ticket)) { if (active && owner !== context()) { active = false; clear() } return }
        state.saved = true; state.form = empty()
      } catch (error) {
        if (current(ticket)) state.error = error.message || '提交失败，请稍后重试'
        else if (active && owner !== context()) { active = false; clear() }
      } finally { if (current(ticket)) state.busy = false }
    },
  }
}
