import { http } from '@/utils/request'

export const publishApi = {
  prepareVideo(data) {
    return http.post('/api/v2/publish/prepare', data, { matrixSilentErrors: true })
  },

  getPrepareSession(sessionId) {
    return http.get(
      `/api/v2/publish/prepare/${encodeURIComponent(sessionId)}`,
      undefined,
      { matrixSilentErrors: true },
    )
  },
}
