// A draft may restore edited facts, never the account or member's current authority.
export function canRestoreOnboardingDraft(draft, profile) {
  if (!Array.isArray(draft?.profile?.members) || draft.profile.householdId !== profile.householdId) return false
  if (profile.isOwner === false) {
    const current = profile.members.find(m => m.id === profile.selfMemberId)
    const saved = draft.profile.members.find(m => m.id === profile.selfMemberId)
    return !!current && draft.profile.selfMemberId === profile.selfMemberId && saved?.version === current.version
  }
  return draft.profile.familyVersion === profile.familyVersion && profile.members.every(m =>
    draft.profile.members.some(saved => saved.id === m.id && saved.version === m.version))
}
