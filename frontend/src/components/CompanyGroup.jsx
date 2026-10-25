import { MATCH_LABELS, SOURCE_LABELS, formatPostedAt } from '../labels.js'

function JobMini({ job }) {
  const posted = formatPostedAt(job.posted_at)
  return (
    <li className="mini-item">
      <a href={job.url} target="_blank" rel="noopener noreferrer" className="mini-title">
        {job.title}
      </a>
      <span className="mini-meta">
        <span className="source small" data-source={job.source}>
          {SOURCE_LABELS[job.source] || job.source}
        </span>
        {' '}{job.location}
        {posted && <> · {posted}</>}
      </span>
    </li>
  )
}

function PersonMini({ person, isDemo, revealing, onReveal }) {
  return (
    <li className="mini-item person">
      <span className="avatar" aria-hidden="true">
        {(person.first_name || person.display_name || '?').charAt(0)}
      </span>
      <span className="person-body">
        <span className="mini-title">
          {person.revealed && person.linkedin_url ? (
            <a href={person.linkedin_url} target="_blank" rel="noopener noreferrer">
              {person.display_name} ↗
            </a>
          ) : person.display_name}
        </span>
        <span className="mini-meta">
          {person.title || 'Poste inconnu'}
          {person.location
            ? <> · {person.location}</>
            : <> · <em>lieu inconnu avant révélation</em></>}
          {person.has_email && !person.email && <> · ✉️ e-mail connu d'Apollo</>}
          {person.email && <> · ✉️ {person.email}</>}
        </span>
        {!person.revealed && (
          <button
            type="button"
            className="reveal-btn"
            disabled={revealing}
            onClick={() => onReveal(person)}
            title={isDemo
              ? 'Démonstration : données fictives, aucun crédit consommé'
              : 'Appelle l\'enrichissement Apollo : 1 crédit si un profil est trouvé, 0 sinon'}
          >
            {revealing ? 'Révélation…' : isDemo ? '👁 Révéler (démo)' : '👁 Révéler — 1 crédit'}
          </button>
        )}
      </span>
    </li>
  )
}

export default function CompanyGroup({ group, isDemo, revealingId, onReveal }) {
  return (
    <article className="company-group" data-match={group.match_type}>
      <header className="company-head">
        <h3>{group.name}</h3>
        <span className="match-badge" data-match={group.match_type}>
          {MATCH_LABELS[group.match_type]}
        </span>
      </header>

      <div className="company-columns">
        <section aria-label={`Annonces de ${group.name}`}>
          <h4>📢 Annonces <span className="count">({group.jobs.length})</span></h4>
          {group.jobs.length ? (
            <ul className="mini-list">
              {group.jobs.map((job) => (
                <JobMini key={`${job.source}-${job.id}`} job={job} />
              ))}
            </ul>
          ) : (
            <p className="empty-col">Aucune annonce pour ce métier dans cette zone.</p>
          )}
        </section>

        <section aria-label={`Personnes chez ${group.name}`}>
          <h4>👥 Personnes <span className="count">({group.people.length})</span></h4>
          {group.people.length ? (
            <ul className="mini-list">
              {group.people.map((person) => (
                <PersonMini
                  key={person.id}
                  person={person}
                  isDemo={isDemo}
                  revealing={revealingId === person.id}
                  onReveal={onReveal}
                />
              ))}
            </ul>
          ) : (
            <p className="empty-col">Aucun profil Apollo pour ce métier dans cette zone.</p>
          )}
        </section>
      </div>
    </article>
  )
}
