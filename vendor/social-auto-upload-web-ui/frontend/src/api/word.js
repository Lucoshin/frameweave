import { http } from '@/utils/request'

export const wordApi = {
  generate(data) {
    return http.post('/api/v2/word/generate', data)
  },
}
