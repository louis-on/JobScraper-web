import { useEffect, useRef, useState } from 'react'
import { crossSearch, fetchProspectsStatus, revealPerson } from '../api'
import CompanyGroup from './CompanyGroup.jsx'

const INITIAL = {
  metier: '', variantesText: '', location: 'France', radius_km: '',
  selectedSources: [], maxJobs: 50, maxPeople: 100,
  includeJobVariants: false, verifiedOnly: false,
}

const FILTERS = [
  ['all', 'Toutes les entreprises'],
  ['both', 'Recrutent + emploient'],
  ['hiring_only', 'Recrutent'],
  ['employing_only', 'Emploient déjà'],
]

export default function Prospecting({ sources, demoMode = false }) {
  const [form, setForm] = useState(INITIAL)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('all')
  const [revealingId, setRevealingId] = useState(null)
  const [revealError, setRevealError] = useState('')

  useEffect(() => {
    fetchProspectsStatus().then(setStatus).catch(() => setStatus({ available: false, reason: "Statut Apollo indisponible." }))
  }, [])

  // Comme dans l'onglet Annonces : en mode démo, présélectionner la source
  // Démo (les jobboards réels sont injoignables depuis un aperçu hébergé).
  const didPreselect = useRef(false)
  useEffect(() => {
    if (didPreselect.current || !demoMode || !sources.length) return
    if (sources.some((s) => s.id === 'demo')) {
      didPreselect.current = true
      setForm((prev) => ({ ...prev, selectedSources: ['demo'] }))
    }
  }, [demoMode, sources])

  const set = (field) => (event) =>
    setForm((prev) => ({ ...prev, [field]: event.target.value }))
  const setCheck = (field) => (event) =>
    setForm((prev) => ({ ...prev, [field]: event.target.checked }))
  const toggleSource = (id) => () =>
    setForm((prev) => ({
      ...prev,
      selectedSources: prev.selectedSources.includes(id)
        ? prev.selectedSources.filter((s) => s !== id)
        : [...prev.selectedSources, id],
    }))

  async function submit(event) {
    event.preventDefault()
    if (!form.metier.trim()) return
    setLoading(true); setError(''); setRevealError(''); setData(null); setFilter('all')
    try {
      const result = await crossSearch({
        metier: form.metier.trim(),
        title_variants: form.variantesText.split(',').map((v) => v.trim()).filter(Boolean),
        location: form.location.trim() || 'France',
        radius_km: form.radius_km ? Number(form.radius_km) : null,
        sources: form.selectedSources.length ? form.selectedSources : ['all'],
        max_jobs_per_source: Number(form.maxJobs) || 50,
        max_people: Number(form.maxPeople) || 100,
        include_job_variants: form.includeJobVariants,
        verified_email_only: form.verifiedOnly,
      })
      setData(result)
    } catch (e) {
      setError(e.message || 'La recherche croisée a échoué.')
    } finally {
      setLoading(false)
    }
  }

  async function handleReveal(person) {
    setRevealingId(person.id); setRevealError('')
    try {
      const revealed = await revealPerson(person.id)
      setData((prev) => prev && ({
        ...prev,
        companies: prev.companies.map((company) => ({
          ...company,
          people: company.people.map((p) => (p.id === person.id ? revealed : p)),
        })),
      }))
    } catch (e) {
      setRevealError(e.message || 'Révélation impossible.')
    } finally {
      setRevealingId(null)
    }
  }

  const visible = data
    ? data.companies.filter((c) => filter === 'all' || c.match_type === filter)
    : []

  return (
    <div className="prospecting">
      <p className="tab-intro">
        Croisez, pour un même métier et une même zone, les entreprises qui <strong>recrutent</strong>
        {' '}(vos annonces agrégées) et celles qui <strong>emploient déjà</strong> ce profil
        (personnes Apollo — recherche gratuite, noms masqués ; révélation unitaire possible).
      </p>

      {status && !status.available && (
        <p className="global-error">⚠️ {status.reason} La colonne « Personnes » restera vide.</p>
      )}
      {status?.demo && (
        <p className="demo-banner">
          Personnes fictives du mode démo — exemples qui donnent un croisement :
          « Technicien de maintenance » à Nantes, « Développeur Python » à Nantes,
          ou « Data Engineer » à Lille.
          Ajoutez une vraie clé <code>APOLLO_API_KEY</code> (en local) pour des profils réels.
        </p>
      )}

      <form className="search-form" onSubmit={submit}>
        <div className="row main-row">
          <label className="grow">
            Métier *
            <input type="text" value={form.metier} onChange={set('metier')} placeholder="Développeur Python, Data Engineer…" required />
          </label>
          <label>
            Localisation
            <input type="text" value={form.location} onChange={set('location')} placeholder="Paris, Paris, France…" />
          </label>
          <label>
            Rayon <small>(annonces)</small>
            <select value={form.radius_km} onChange={set('radius_km')}>
              <option value="">Indifférent</option>
              {[5, 10, 25, 50, 100].map((km) => <option key={km} value={km}>{km} km</option>)}
            </select>
          </label>
        </div>

        <div className="row">
          <label className="grow">
            Variantes d'intitulé <small>(virgules — surtout pour Apollo : FR + EN conseillés)</small>
            <input type="text" value={form.variantesText} onChange={set('variantesText')} placeholder="Python Developer, Lead Developer Python…" />
          </label>
          <label>
            Annonces / source
            <select value={form.maxJobs} onChange={set('maxJobs')}>
              {[20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label>
            Personnes (Apollo)
            <select value={form.maxPeople} onChange={set('maxPeople')}>
              {[25, 50, 100, 250].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>

        <details className="filters">
          <summary>Options avancées</summary>
          <div className="row checks">
            <label className="check">
              <input type="checkbox" checked={form.includeJobVariants} onChange={setCheck('includeJobVariants')} />
              {' '}Chercher aussi les variantes dans les annonces (plus lent)
            </label>
            <label className="check">
              <input type="checkbox" checked={form.verifiedOnly} onChange={setCheck('verifiedOnly')} />
              {' '}Apollo : profils à e-mail vérifié uniquement
            </label>
          </div>
          <p className="hint">
            Le rayon ne s'applique qu'aux annonces : Apollo filtre par ville/pays, sans rayon
            ni code postal français (utilisez « Ville, France »).
          </p>
        </details>

        <fieldset className="sources">
          <legend>Sources d'annonces <small>(aucune cochée = toutes)</small></legend>
          {sources.map((source) => (
            <label key={source.id} className={`check source-check${source.available ? '' : ' unavailable'}`} title={source.available ? source.description : source.unavailable_reason}>
              <input type="checkbox" checked={form.selectedSources.includes(source.id)} onChange={toggleSource(source.id)} disabled={!source.available} />
              {' '}{source.label}
              {!source.available && <small> — {source.unavailable_reason}</small>}
            </label>
          ))}
        </fieldset>

        <div className="actions">
          <button type="submit" className="primary" disabled={loading || !form.metier.trim()}>
            {loading ? '⏳ Croisement en cours…' : '🧭 Croiser annonces × personnes'}
          </button>
        </div>
      </form>

      {error && <p className="global-error">{error}</p>}
      {loading && (
        <p className="summary"><span className="spinner" aria-hidden="true" /> Recherche parallèle en cours (annonces + personnes)…</p>
      )}

      {data && (
        <>
          <p className="summary">
            <strong>{data.summary.companies}</strong> entreprise(s) : {data.summary.matching_companies} recrutent + emploient,
            {' '}{data.summary.hiring_companies} recrutent ({data.summary.jobs_total} annonce(s)),
            {' '}{data.summary.employing_companies} emploient déjà ({data.summary.people_returned} personne(s) affichée(s)
            sur {data.summary.people_total_entries} profils Apollo correspondants) —
            en {(data.duration_ms / 1000).toFixed(1)} s.
          </p>
          {data.apollo_error && <p className="global-error">⚠️ Personnes : {data.apollo_error}</p>}
          {!!Object.keys(data.summary.job_errors || {}).length && (
            <div className="global-error">
              ⚠️ Sources d'annonces en échec :
              <ul>
                {Object.entries(data.summary.job_errors).map(([src, message]) => (
                  <li key={src}><strong>{src}</strong> — {message}</li>
                ))}
              </ul>
            </div>
          )}
          {revealError && <p className="global-error">⚠️ {revealError}</p>}

          <div className="filter-chips" role="group" aria-label="Filtrer les entreprises">
            {FILTERS.map(([value, label]) => (
              <button key={value} type="button" className={`chip${filter === value ? ' active' : ''}`} onClick={() => setFilter(value)}>
                {label}
              </button>
            ))}
          </div>

          {!visible.length && (
            <p className="empty">Aucune entreprise dans cette catégorie. Essayez d'élargir le métier, la zone ou le rayon.</p>
          )}
          <section className="company-list">
            {visible.map((company) => (
              <CompanyGroup
                key={company.key}
                group={company}
                isDemo={data.apollo_demo}
                revealingId={revealingId}
                onReveal={handleReveal}
              />
            ))}
          </section>
        </>
      )}
    </div>
  )
}
