import { http } from '@/utils/request'
import { materialsApi } from '@/api/materials'

export const imagePublishApi = {
  uploadImage(file, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    return materialsApi.upload(formData, (percent) => {
      if (onProgress) {
        onProgress(percent)
      }
    })
  },
  getDrafts() { return http.get('/api/image-publish/drafts') },
  saveDraft(data) { return http.post('/api/image-publish/drafts', data) },
  deleteDraft(id) { return http.delete(`/api/image-publish/drafts/${id}`) },
  getHistory() { return http.get('/api/image-publish/history') },
}
