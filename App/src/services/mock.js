// Frontend fixtures only. API adapters can replace these asynchronous methods.
import { getProfile, saveProfile, getRecords, updateRecord } from '../utils/profile.js'
const wait = () => new Promise(resolve => setTimeout(resolve, 180))
const read = key => uni.getStorageSync(key) || []
const write = (key, value) => uni.setStorageSync(key, JSON.parse(JSON.stringify(value)))
export const mockService = {
  async addresses() { await wait(); return read('frontend-addresses-v1') },
  async saveAddress(address) {
    await wait()
    if (!address.name?.trim() || !/^1\d{10}$/.test(address.phone || '') || !address.region?.trim() || !address.detail?.trim()) throw new Error('请完整填写收件人、11 位手机号、地区和详细地址')
    const addresses = read('frontend-addresses-v1')
    const entry = { ...address, id: address.id || 'addr-'+Date.now(), isDemo: true }
    const index = addresses.findIndex(item => item.id === entry.id)
    index < 0 ? addresses.push(entry) : addresses.splice(index, 1, entry)
    write('frontend-addresses-v1', addresses); uni.setStorageSync('frontend-selected-address-v1', entry.id)
    return entry
  },
  async selectAddress(id) { await wait(); uni.setStorageSync('frontend-selected-address-v1', id) },
  selectedAddress() { return read('frontend-addresses-v1').find(a => a.id === uni.getStorageSync('frontend-selected-address-v1')) || null },
  async addReport(memberId, source) {
    await wait(); const profile=getProfile(), member=profile.members.find(m=>String(m.id)===String(memberId))
    if (!member) throw new Error('成员不存在')
    const report={id:'report-'+Date.now(),name:source+' · 示例报告',status:'review',createdAt:new Date().toISOString(),shared:false,isDemo:true}
    member.reports=[...(member.reports||[]),report];member.reportStatus='review';saveProfile(profile);return report
  },
  async confirmReport(memberId, reportId, shared) {
    await wait();const profile=getProfile(),member=profile.members.find(m=>String(m.id)===String(memberId)),report=member?.reports?.find(r=>r.id===reportId)
    if(!report)throw new Error('报告不存在')
    const viewer=profile.viewerAccount||'creator'
    if(Boolean(shared)!==Boolean(report.shared)&&member.claimedBy!==viewer)throw new Error('报告共享只能由本人授权')
    report.status='done';report.shared=Boolean(shared);member.reportStatus='done';saveProfile(profile);return report
  },
  async correctRecord(id, patch) {
    await wait();const record=getRecords().find(r=>String(r.id)===String(id));if(!record)throw new Error('记录不存在')
    updateRecord(record.id,{...patch,id:record.id,version:(record.version||1)+1,updatedAt:new Date().toISOString()})
    return getRecords().find(r=>r.id===record.id)
  },
  async login() { await wait();uni.setStorageSync('frontend-session-v1',{accountId:'demo-creator',isDemo:true});return {isDemo:true} },
}
