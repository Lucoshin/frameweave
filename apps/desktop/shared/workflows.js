export function normalizeWordRows(jsonText) {
  const rows = JSON.parse(jsonText)
  if (!Array.isArray(rows)) throw new Error('批量数据必须是 JSON 数组')
  if (rows.some((row) => !row || Array.isArray(row) || typeof row !== 'object')) {
    throw new Error('JSON 数组的每一项必须是对象')
  }
  return rows
}

export function safeDocxName(value) {
  const safe = String(value || '未命名').replace(/[<>:"/\\|?*]/g, '_').trim()
  return `${safe || '未命名'}.docx`
}
