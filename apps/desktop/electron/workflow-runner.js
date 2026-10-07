import { promises as fs } from 'node:fs'
import path from 'node:path'
import Docxtemplater from 'docxtemplater'
import PizZip from 'pizzip'

import { normalizeWordRows, safeDocxName } from '../shared/workflows.js'

export async function generateWordBatch({ templatePath, outputDirectory, jsonText, filenameField = 'title' }) {
  if (path.extname(templatePath).toLowerCase() !== '.docx') throw new Error('模板必须是 .docx 文件')
  const rows = normalizeWordRows(jsonText)
  const template = await fs.readFile(templatePath)
  const outputs = []

  for (const [index, row] of rows.entries()) {
    const document = new Docxtemplater(new PizZip(template), {
      linebreaks: true,
      paragraphLoop: true,
    })
    document.render(row)
    const filename = safeDocxName(row[filenameField] || `文案-${index + 1}`)
    const outputPath = path.join(outputDirectory, filename)
    await fs.writeFile(outputPath, document.getZip().generate({ type: 'nodebuffer' }))
    outputs.push(outputPath)
  }
  return { count: outputs.length, outputs }
}
