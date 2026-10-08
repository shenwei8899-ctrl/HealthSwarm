import { getProfile,newMember,normalizeMember,saveProfile } from './profile.js'
// Local simulation; production signed invitation credentials must be issued by the server.
const read=()=>uni.getStorageSync('family-invites-v1') || {}
export function createInvite(memberId=null) {
  const profile=getProfile(),member=profile.members.find(m=>m.id===memberId)
  if(member?.claimedBy || profile.viewerAccount && profile.viewerAccount!=='creator')return ''
  const invites=read(),key=memberId?'member-'+memberId:'family'
  const existing=Object.entries(invites).find(([,i])=>i.key===key)
  if(existing)return existing[0]
  const token='demo-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8)
  invites[token]={key,memberId,householdName:profile.householdName,inviter:'家庭创建人',claims:[]}
  uni.setStorageSync('family-invites-v1',invites);return token
}
export function getInvite(token){return read()[token] || null}
export function shareInvite(token){return {title:'邀请你加入我的家庭，核对你的健康资料',path:'/pages/invite/index?token='+token}}
export function acceptInvite(token,account) {
  const invites=read(),invite=invites[token],profile=getProfile()
  if(!invite)return {error:'邀请不存在'}
  if(!account?.trim())return {error:'请先登录'}
  const previous=invite.claims.find(c=>c.account===account)
  if(previous)return {id:previous.id}
  let member=profile.members.find(m=>m.id===invite.memberId)
  if(invite.memberId && (!member || member.claimedBy || invite.claims.length))return {error:'该成员档案已被认领，不能重复加入'}
  if(!invite.memberId){member=normalizeMember(newMember(profile.members.length));member.name='受邀家人';profile.members.push(member)}
  member.claimedBy=account;profile.viewerAccount=account
  invite.claims.push({account,id:member.id})
  uni.setStorageSync('family-invites-v1',invites);saveProfile(profile)
  return {id:member.id}
}
