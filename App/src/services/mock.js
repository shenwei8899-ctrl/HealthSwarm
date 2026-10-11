import { getOrders, getOrder, createDemoOrder, updateOrder } from '../utils/orders.js'
import { receiveOrder, pauseOrder, previewResume, resumeOrder, changeOrderBatchAddress, submitOrderAfterSale, remainingRefundPreview, cancelOrderRemaining } from '../utils/order-actions.js'
import { scopedStorage } from './storage.js'
import { setSession } from './session.js'
import { mockDelay } from './mock-control.js'
// Frontend fixtures only. API adapters can replace these asynchronous methods.
import { getProfile, saveProfile, getRecords, updateRecord } from '../utils/profile.js'
const wait = () => mockDelay('data')
const read = key => scopedStorage.getStorageSync(key) || []
const write = (key, value) => scopedStorage.setStorageSync(key, JSON.parse(JSON.stringify(value)))
export const mockService = {
  async orders() { await mockDelay('orders'); return getOrders() },
  async order(id) { await mockDelay('order'); return getOrder(id) },
  async receive(id, index) { await mockDelay('receive'); return receiveOrder(id, index) },
  async pausePlan(id) { await mockDelay('pause'); return pauseOrder(id) },
  async resumePreview(id) { await mockDelay('resume'); return previewResume(id) },
  async resumePlan(id, preview) { await mockDelay('resume'); return resumeOrder(id, preview) },
  async changeBatchAddress(id, index, address) { await mockDelay('address'); return changeOrderBatchAddress(id, index, address) },
  async submitAfterSale(id, form) { await mockDelay('afterSale'); return submitOrderAfterSale(id, form) },
  async refundPreview(id) { await mockDelay('refund'); return remainingRefundPreview(id) },
  async cancelRemaining(id) { await mockDelay('refund'); return cancelOrderRemaining(id) },
  async createOrder(input) { await mockDelay('createOrder'); return createDemoOrder({...input, paymentStatus:'pending'}) },
  async payOrder(id, result) {
    await mockDelay('payment');const order=getOrder(id);if(!order)throw new Error('订单不存在');
    if(order.paymentStatus==='paid')return order;
    if(order.paymentStatus==='unknown')throw new Error('请先查询支付结果，勿重复支付');
    if(result==='success')return updateOrder(id,{status:'paid',paymentStatus:'paid',fulfillmentStatus:'preparing'});
    if(result==='unknown')return updateOrder(id,{status:'pending',paymentStatus:'unknown'});
    return updateOrder(id,{status:'pending',paymentStatus:result==='cancel'?'cancelled':'failed'});
  },
  async paymentResult(id) { await mockDelay('payment');return getOrder(id) },
  async addresses() { await wait(); return read('frontend-addresses-v1') },
  async saveAddress(address) {
    await wait()
    if (!address.name?.trim() || !/^1\d{10}$/.test(address.phone || '') || !address.region?.trim() || !address.detail?.trim()) throw new Error('请完整填写收件人、11 位手机号、地区和详细地址')
    const addresses = read('frontend-addresses-v1')
    const entry = { ...address, id: address.id || 'addr-'+Date.now(), isDemo: true }
    const index = addresses.findIndex(item => item.id === entry.id)
    index < 0 ? addresses.push(entry) : addresses.splice(index, 1, entry)
    write('frontend-addresses-v1', addresses); scopedStorage.setStorageSync('frontend-selected-address-v1', entry.id)
    return entry
  },
  async selectAddress(id) { await wait();if(!read('frontend-addresses-v1').some(address=>address.id===id))throw new Error('地址不存在，请刷新后重新选择');scopedStorage.setStorageSync('frontend-selected-address-v1', id) },
  selectedAddress() { return read('frontend-addresses-v1').find(a => a.id === scopedStorage.getStorageSync('frontend-selected-address-v1')) || null },
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
  async login(account='creator') { await wait();const session={accountId:'demo-'+(account.trim()||'creator'),householdId:'demo-household-'+(account.trim()||'creator'),isDemo:true};setSession(session);return session },
}
