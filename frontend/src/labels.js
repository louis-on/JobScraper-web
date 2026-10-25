// Libellés français partagés par les composants.

export const CONTRACT_LABELS = {
  cdi: 'CDI', cdd: 'CDD', stage: 'Stage', alternance: 'Alternance',
  interim: 'Intérim', freelance: 'Freelance', other: 'Autre',
}

export const EXPERIENCE_LABELS = {
  internship: 'Stage', junior: 'Junior', mid: 'Confirmé',
  senior: 'Senior', lead: 'Lead', director: 'Direction',
}

export const SOURCE_LABELS = {
  linkedin: 'LinkedIn', hellowork: 'HelloWork', francetravail: 'France Travail',
  adzuna: 'Adzuna', wttj: 'WTTJ', demo: 'Démo',
}

export const MATCH_LABELS = {
  both: 'Recrute + emploie déjà',
  hiring_only: 'Recrute',
  employing_only: 'Emploie déjà',
}

export function formatPostedAt(isoDate) {
  if (!isoDate) return null
  const days = Math.floor((Date.now() - new Date(isoDate).getTime()) / 86400000)
  if (days <= 0) return "Aujourd'hui"
  if (days === 1) return 'Il y a 1 jour'
  if (days < 30) return `Il y a ${days} jours`
  return new Date(isoDate).toLocaleDateString('fr-FR')
}
