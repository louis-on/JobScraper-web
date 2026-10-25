// Client de l'API JobScraper — toujours en URL relatives (/api/...),
// pour fonctionner aussi bien derrière le proxy Vite en développement
// que servi par FastAPI en production.

export async function fetchSources() {
  const response = await fetch('/api/sources')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

export async function fetchHealth() {
  const response = await fetch('/api/health')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

// --- Recherche croisée annonces x personnes (Apollo) ---

export async function fetchProspectsStatus() {
  const response = await fetch('/api/prospects/status')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

export async function crossSearch(payload) {
  const response = await fetch('/api/cross-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

export async function revealPerson(personId) {
  const response = await fetch('/api/prospects/reveal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ person_id: personId }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return (await response.json()).person
}

// Recherche en streaming (Server-Sent Events) : les offres arrivent au fil
// de l'eau, source par source, sans attendre la fin complète du scraping.
export function streamSearch(criteria, handlers) {
  const params = new URLSearchParams()
  for (const keyword of criteria.keywords) params.append('keywords', keyword)
  if (criteria.title) params.set('title', criteria.title)
  params.set('location', criteria.location || 'France')
  if (criteria.radius_km) params.set('radius_km', String(criteria.radius_km))
  for (const value of criteria.contract_types) params.append('contract_types', value)
  for (const value of criteria.experience_levels) params.append('experience_levels', value)
  for (const value of criteria.workplace_types) params.append('workplace_types', value)
  if (criteria.date_posted && criteria.date_posted !== 'any_time') {
    params.set('date_posted', criteria.date_posted)
  }
  params.set('sort_by', criteria.sort_by)
  params.set('max_results', String(criteria.max_results))
  params.set('sources', criteria.sources.join(','))

  const source = new EventSource(`/api/search/stream?${params.toString()}`)
  const parse = (event) => JSON.parse(event.data)

  source.addEventListener('start', (e) => handlers.onStart?.(parse(e)))
  source.addEventListener('job', (e) => handlers.onJob?.(parse(e).job))
  source.addEventListener('source_done', (e) => handlers.onSourceDone?.(parse(e)))
  source.addEventListener('source_error', (e) => handlers.onSourceError?.(parse(e)))
  source.addEventListener('done', (e) => {
    handlers.onDone?.(parse(e))
    source.close()
  })
  source.onerror = () => {
    // EventSource déclenche aussi onerror en fin de flux normal selon les
    // navigateurs ; on ne signale une erreur que si la connexion est fermée.
    if (source.readyState === EventSource.CLOSED) handlers.onError?.()
  }
  return source
}
