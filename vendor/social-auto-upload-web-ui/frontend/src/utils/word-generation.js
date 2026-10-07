export function parseTitleLines(value) {
  return String(value ?? '')
    .split(/\r?\n/)
    .map(title => title.trim())
    .filter(Boolean)
}

export function buildWordGenerationPayload({
  titlesText,
  prompt,
  outputDirectory,
  providerId,
  baseUrl,
  apiKey,
  model,
  includeTitle,
  images,
}) {
  return {
    titles: parseTitleLines(titlesText),
    prompt: String(prompt ?? '').trim(),
    output_directory: String(outputDirectory ?? '').trim(),
    provider: {
      provider_id: String(providerId ?? '').trim(),
      base_url: String(baseUrl ?? '').trim(),
      api_key: String(apiKey ?? '').trim(),
      model: String(model ?? '').trim(),
    },
    include_title: includeTitle !== false,
    ...(images ? { images } : {}),
  }
}
