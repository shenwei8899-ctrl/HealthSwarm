import { scopedStorage } from './storage.js'
const key=id=>'member-edit-draft-v1:'+encodeURIComponent(id)
const policy=source=>JSON.stringify([...(source.allowed_fields||[])].sort())+'|'+JSON.stringify([...(source.editable_fields||[])].sort())
export function preserveMemberEdit({id,source,draft,additional,section,uncertain=false}){
 if(!source||!draft||!source.editable_fields?.length)return
 scopedStorage.setStorageSync(key(id),{version:1,id,sourceVersion:source.version,relationshipVersion:source.relationship_version,policy:policy(source),draft,additional,section,uncertain})
}
export function readMemberEdit(id,source){
 const value=scopedStorage.getStorageSync(key(id))
 if(!value||value.id!==id||value.version!==1)return null
 if(!source.editable_fields?.length||value.policy!==policy(source)){clearMemberEdit(id);return null}
 return {...value,conflict:value.uncertain||value.sourceVersion!==source.version||value.relationshipVersion!==source.relationship_version}
}
export function clearMemberEdit(id){scopedStorage.setStorageSync(key(id),null)}
