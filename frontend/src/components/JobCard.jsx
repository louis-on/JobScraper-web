import { CONTRACT_LABELS, EXPERIENCE_LABELS, SOURCE_LABELS } from '../labels.js'

function salaryLabel(job) {
  const { salary_min: min, salary_max: max } = job
  const k = (v) => `${Math.round(v / 1000)} k€`
  if (min && max) return `${k(min)} – ${k(max)} / an`
  if (min) return `à partir de ${k(min)} / an`
  if (max) return `jusqu'à ${k(max)} / an`
  return null
}

function postedLabel(job) {
  if (!job.posted_at) return null
  const days = Math.floor((Date.now() - new Date(job.posted_at).getTime()) / 86400000)
  if (days <= 0) return "Aujourd'hui"
  if (days === 1) return 'Il y a 1 jour'
  if (days < 30) return `Il y a ${days} jours`
  return new Date(job.posted_at).toLocaleDateString('fr-FR')
}

export default function JobCard({ job }) {
  const salary = salaryLabel(job)
  const posted = postedLabel(job)

  return (
    <article className="card">
      <header className="card-head">
        <span className="source" data-source={job.source}>
          {SOURCE_LABELS[job.source] || job.source}
        </span>
        {posted && <span className="date">{posted}</span>}
      </header>

      <h3 className="title">
        <a href={job.url} target="_blank" rel="noopener noreferrer">{job.title}</a>
      </h3>
      <p className="company">{job.company} · {job.location}</p>

      {job.description && <p className="excerpt">{job.description}</p>}

      <div className="badges">
        {job.contract_type && (
          <span className="badge">{CONTRACT_LABELS[job.contract_type] || job.contract_type}</span>
        )}
        {job.experience_level && (
          <span className="badge">{EXPERIENCE_LABELS[job.experience_level] || job.experience_level}</span>
        )}
        {job.remote && <span className="badge remote">Télétravail</span>}
        {salary && <span className="badge salary">{salary}</span>}
      </div>

      {!!job.skills?.length && (
        <div className="skills">
          {job.skills.slice(0, 6).map((skill) => (
            <span key={skill} className="skill">{skill}</span>
          ))}
        </div>
      )}

      <footer>
        <a className="cta" href={job.url} target="_blank" rel="noopener noreferrer">Voir l'offre ↗</a>
      </footer>
    </article>
  )
}
