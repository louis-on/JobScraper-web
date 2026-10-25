import { useEffect, useRef, useState } from 'react'

const CONTRACTS = [
  ['cdi', 'CDI'], ['cdd', 'CDD'], ['stage', 'Stage'],
  ['alternance', 'Alternance'], ['interim', 'Intérim'], ['freelance', 'Freelance'],
]
const EXPERIENCES = [
  ['internship', 'Stage'], ['junior', 'Junior'], ['mid', 'Confirmé'],
  ['senior', 'Senior'], ['lead', 'Lead'], ['director', 'Direction'],
]
const WORKPLACES = [
  ['on_site', 'Sur site'], ['remote', 'Télétravail'], ['hybrid', 'Hybride'],
]

const INITIAL = {
  keywordsText: '', title: '', location: 'France', radius_km: '',
  contract_types: [], experience_levels: [], workplace_types: [],
  date_posted: 'any_time', sort_by: 'relevance', max_results: 50,
  selectedSources: [],
}

export default function SearchForm({ sources, searching, demoMode = false, onSearch, onStop }) {
  const [form, setForm] = useState(INITIAL)

  // En mode démo, présélectionner la source Démo : les jobboards réels sont
  // injoignables depuis un aperçu hébergé, donc par défaut on interroge la
  // seule source qui répond ici (l'utilisateur peut toujours changer les cases).
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

  const toggle = (field, value) => () =>
    setForm((prev) => ({
      ...prev,
      [field]: prev[field].includes(value)
        ? prev[field].filter((v) => v !== value)
        : [...prev[field], value],
    }))

  function submit(event) {
    event.preventDefault()
    onSearch({
      keywords: form.keywordsText.split(',').map((k) => k.trim()).filter(Boolean),
      title: form.title.trim(),
      location: form.location.trim() || 'France',
      radius_km: form.radius_km ? Number(form.radius_km) : null,
      contract_types: form.contract_types,
      experience_levels: form.experience_levels,
      workplace_types: form.workplace_types,
      date_posted: form.date_posted,
      sort_by: form.sort_by,
      max_results: Number(form.max_results) || 50,
      sources: form.selectedSources.length ? form.selectedSources : ['all'],
    })
  }

  const checkGroup = (legend, field, options) => (
    <fieldset>
      <legend>{legend}</legend>
      {options.map(([value, label]) => (
        <label key={value} className="check">
          <input type="checkbox" checked={form[field].includes(value)} onChange={toggle(field, value)} />
          {' '}{label}
        </label>
      ))}
    </fieldset>
  )

  return (
    <form className="search-form" onSubmit={submit}>
      <div className="row main-row">
        <label className="grow">
          Mots-clés <small>(séparés par des virgules)</small>
          <input type="text" value={form.keywordsText} onChange={set('keywordsText')} placeholder="python, data engineer…" autoFocus />
        </label>
        <label>
          Localisation
          <input type="text" value={form.location} onChange={set('location')} placeholder="Paris, Nantes, France…" />
        </label>
        <label>
          Rayon
          <select value={form.radius_km} onChange={set('radius_km')}>
            <option value="">Indifférent</option>
            {[5, 10, 25, 50, 100].map((km) => <option key={km} value={km}>{km} km</option>)}
          </select>
        </label>
      </div>

      <details className="filters">
        <summary>Filtres avancés</summary>
        <div className="row">
          <label className="grow">
            Titre de poste exact
            <input type="text" value={form.title} onChange={set('title')} placeholder="Développeur Python…" />
          </label>
          <label>
            Publiées
            <select value={form.date_posted} onChange={set('date_posted')}>
              <option value="any_time">Toutes dates</option>
              <option value="past_24h">Dernières 24 h</option>
              <option value="past_week">7 derniers jours</option>
              <option value="past_month">30 derniers jours</option>
            </select>
          </label>
          <label>
            Trier par
            <select value={form.sort_by} onChange={set('sort_by')}>
              <option value="relevance">Pertinence</option>
              <option value="date">Date (récentes d'abord)</option>
            </select>
          </label>
          <label>
            Résultats max / source <small>(plus = plus lent)</small>
            <select value={form.max_results} onChange={set('max_results')}>
              {[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
        <div className="row checks">
          {checkGroup('Contrat', 'contract_types', CONTRACTS)}
          {checkGroup('Expérience', 'experience_levels', EXPERIENCES)}
          {checkGroup('Lieu de travail', 'workplace_types', WORKPLACES)}
        </div>
      </details>

      <fieldset className="sources">
        <legend>Sources <small>(aucune cochée = toutes)</small></legend>
        {sources.map((source) => (
          <label
            key={source.id}
            className={`check source-check${source.available ? '' : ' unavailable'}`}
            title={source.available ? source.description : source.unavailable_reason}
          >
            <input
              type="checkbox"
              checked={form.selectedSources.includes(source.id)}
              onChange={toggle('selectedSources', source.id)}
              disabled={!source.available}
            />
            {' '}{source.label}
            {!source.available && <small> — {source.unavailable_reason}</small>}
          </label>
        ))}
        {!sources.length && <p className="hint">Chargement des sources…</p>}
      </fieldset>

      <div className="actions">
        {searching
          ? <button type="button" className="stop" onClick={onStop}>⏹ Arrêter</button>
          : <button type="submit" className="primary">🔎 Rechercher</button>}
      </div>
    </form>
  )
}
