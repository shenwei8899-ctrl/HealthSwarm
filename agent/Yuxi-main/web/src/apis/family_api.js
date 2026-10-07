import { apiGet, apiPost, apiPut, buildQuery } from './base'

const memberPath = (fid, mid) =>
  `/api/family/${encodeURIComponent(fid)}/members/${encodeURIComponent(mid)}`

export const familyApi = {
  list: () => apiGet('/api/family'),
  create: (name) => apiPost('/api/family', { name }),
  get: (fid) => apiGet(`/api/family/${encodeURIComponent(fid)}`),
  addMember: (fid, payload) => apiPost(`/api/family/${encodeURIComponent(fid)}/members`, payload),
  updateProfile: (fid, mid, payload) => apiPut(memberPath(fid, mid), payload),
  confirm: (fid, mid, expectedVersion) =>
    apiPost(memberPath(fid, mid) + '/confirm', { expected_version: expectedVersion }),
  history: (fid, mid) => apiGet(memberPath(fid, mid) + '/history'),
  invite: (fid, mid) => apiPost(memberPath(fid, mid) + '/invite'),
  join: (code) => apiPost('/api/family/join', { code }),
  authorize: (fid, mid, payload) => apiPut(memberPath(fid, mid) + '/authorization', payload),
  measurements: (fid, mid, params) =>
    apiGet(memberPath(fid, mid) + '/measurements?' + buildQuery(params)),
  addMeasurement: (fid, mid, payload) => apiPost(memberPath(fid, mid) + '/measurements', payload),
  correctMeasurement: (fid, mid, id, payload) =>
    apiPut(memberPath(fid, mid) + '/measurements/' + encodeURIComponent(id), payload),
  statistics: (fid, days) =>
    apiGet(`/api/family/${encodeURIComponent(fid)}/statistics?${buildQuery({ days })}`)
}
