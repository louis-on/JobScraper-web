import { useEffect, useRef, useState } from 'react'
import { fetchHealth, fetchSources, streamSearch } from './api'
import JobCard from './components/JobCard.jsx'
import SearchForm from './components/SearchForm.jsx'

export default function App() {
  const [sources, setSources] = useState([])
  const [health, setHealth] = useState(null)
  const [jobs, setJobs] = useState([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const [meta, setMeta] = useState(null)
  const [globalError, setGlobalError] = useState('')
  // État par source pendant le streaming : loading | done | error | stopped (+ compteur)
  const [sourceStates, setSourceStates] = useState({})
  const streamRef = useRef(null)

  useEffect(() => {
    fetchSources().then(setSources).catch(() =>
      setGlobalError("Impossible de joindre l'API. Le serveur est-il lancé ?"))
    fetchHealth().then(setHealth).catch(() => {})
    return () => streamRef.current?.close()
  }, [])

  const sourceLabel = (id) => sources.find((s) => s.id === id)?.label || id

  function stopSearch() {
    streamRef.current?.close()
    streamRef.current = null
    setSearching(false)
    setSourceStates((prev) => {
      const next = { ...prev }
      for (const state of Object.values(next)) {
        if (state.status === 'loading') state.status = 'stopped'
      }
      return next
    })
  }

  function runSearch(criteria) {
    streamRef.current?.close()
    setJobs([])
    setMeta(null)
    setGlobalError('')
    setSearched(true)
    setSearching(true)
    setSourceStates({})

    streamRef.current = streamSearch(criteria, {
      onStart({ sources: queried }) {
        setSourceStates(Object.fromEntries(
          queried.map((id) => [id, { status: 'loading', count: 0 }]),
        ))
      },
      onJob(job) {
        setJobs((prev) => [...prev, job])
        setSourceStates((prev) => prev[job.source]
          ? { ...prev, [job.source]: { ...prev[job.source], count: prev[job.source].count + 1 } }
          : prev)
      },
      onSourceDone({ source, count }) {
        setSourceStates((prev) => prev[source]
          ? { ...prev, [source]: { ...prev[source], status: 'done', count } }
          : prev)
      },
      onSourceError({ source, error }) {
        setSourceStates((prev) => prev[source]
          ? { ...prev, [source]: { ...prev[source], status: 'error', error } }
          : prev)
      },
      onDone(summary) {
        setMeta(summary)
        setSearching(false)
        streamRef.current = null
      },
      onError() {
        setSearching((wasSearching) => {
          if (wasSearching) {
            setGlobalError('La connexion au serveur a été interrompue pendant la recherche.')
          }
          return false
        })
      },
    })
  }

  const failedSources = meta ? Object.keys(meta.errors || {}) : []

  return (
    <div className="page">
      <header className="site-header">
        <h1>🧭 JobScraper</h1>
        <p>
          Une seule recherche sur LinkedIn, HelloWork, France Travail,
          Welcome to the Jungle et Adzuna.
        </p>
        {health?.demo && (
          <p className="demo-banner">
            Mode démo actif : la source « Démo » renvoie des offres fictives, sans accès réseau.
          </p>
        )}
      </header>

      <main>
        <SearchForm sources={sources} searching={searching} onSearch={runSearch} onStop={stopSearch} />

        {globalError && <p className="global-error">{globalError}</p>}

        {!!Object.keys(sourceStates).length && (
          <section className="source-states" aria-live="polite">
            {Object.entries(sourceStates).map(([id, state]) => (
              <span key={id} className="state-chip" data-status={state.status} title={state.error || ''}>
                {state.status === 'loading'
                  ? <span className="spinner" aria-hidden="true" />
                  : state.status === 'done' ? '✅'
                  : state.status === 'error' ? '⚠️' : null}
                {' '}{sourceLabel(id)} · {state.count}
              </span>
            ))}
          </section>
        )}

        {searched && !searching && meta ? (
          <p className="summary">
            <strong>{meta.total}</strong> offre{meta.total > 1 ? 's' : ''} trouvée{meta.total > 1 ? 's' : ''}
            {' '}en {(meta.duration_ms / 1000).toFixed(1)} s
            {!!failedSources.length && (
              <> — sources en échec : {failedSources.map(sourceLabel).join(', ')}</>
            )}
          </p>
        ) : searching ? (
          <p className="summary">
            Recherche en cours… {jobs.length} offre{jobs.length > 1 ? 's' : ''} pour le moment
          </p>
        ) : null}

        {searched && !searching && jobs.length === 0 && (
          <p className="empty">
            Aucune offre ne correspond à ces critères. Essayez d'élargir les mots-clés,
            la localisation ou le rayon.
          </p>
        )}

        <section className="grid">
          {jobs.map((job) => (
            <JobCard key={`${job.source}-${job.id}`} job={job} />
          ))}
        </section>
      </main>

      <footer className="site-footer">
        <p>
          Offres agrégées depuis leurs sites d'origine — « Voir l'offre » ouvre la page source.
          Outil personnel, sans affiliation avec les jobboards cités.
        </p>
      </footer>
    </div>
  )
}
