import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'

const statusBadge: Record<string, string> = {
  draft: 'badge-draft', review: 'badge-review', approved: 'badge-approved', won: 'badge-won', lost: 'badge-lost',
}

export default function ProposalList() {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['proposals'],
    queryFn: () => api.get('/api/v1/proposals').then(r => r.data),
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">{t('common.loading')}</div>

  const proposals = data?.proposals || []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{t('nav.proposals')}</h1>
          <p className="text-sm text-gray-500 mt-1">{proposals.length} propostas</p>
        </div>
        <Link to="/proposals/new" className="btn-primary">+ {t('nav.new')}</Link>
      </div>

      {proposals.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg mb-2">{t('common.no_results')}</p>
          <Link to="/proposals/new" className="text-brand font-semibold hover:underline">Criar primeira proposta</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {proposals.map((p: any) => (
            <Link key={p.id} to={`/proposals/${p.id}`} className="card flex items-center justify-between group cursor-pointer">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`badge ${statusBadge[p.status] || 'badge-draft'}`}>
                    {t(`proposal.${p.status}`) || p.status}
                  </span>
                  {p.main_proc && <span className="badge bg-indigo-50 text-indigo-600 border border-indigo-200">{p.main_proc}</span>}
                </div>
                <h3 className="text-sm font-bold text-surface-dark truncate group-hover:text-brand transition-colors">{p.title}</h3>
                <div className="flex items-center gap-4 mt-1 text-xs text-gray-400">
                  <span>{p.sap_version}</span>
                  <span>{(p.states || []).join(', ')}</span>
                  <span>{new Date(p.created_at).toLocaleDateString('pt-BR')}</span>
                </div>
              </div>
              <div className="text-right flex-shrink-0 ml-4">
                {p.total_hours && <div className="text-lg font-bold text-surface-dark">{p.total_hours}h</div>}
                {p.valor && <div className="text-sm font-semibold text-teal">R$ {Number(p.valor).toLocaleString('pt-BR')}</div>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
