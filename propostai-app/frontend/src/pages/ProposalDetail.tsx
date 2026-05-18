import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'
import DetailModal from '@/components/proposal/DetailModal'

const statusBadge: Record<string, string> = {
  draft: 'badge-draft', review: 'badge-review', approved: 'badge-approved', won: 'badge-won', lost: 'badge-lost',
}

export default function ProposalDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [detailFrente, setDetailFrente] = useState<string | null>(null)

  const { data: proposal, isLoading } = useQuery({
    queryKey: ['proposal', id],
    queryFn: () => api.get(`/api/v1/proposals/${id}`).then(r => r.data),
  })

  const approveMut = useMutation({
    mutationFn: () => api.patch(`/api/v1/proposals/${id}/status`, { status: 'approved' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposal', id] }),
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">{t('common.loading')}</div>
  if (!proposal) return <div className="text-center py-20 text-gray-400">Proposta nao encontrada</div>

  const p = proposal
  const conf = p.confidence || {}
  const valor = p.valor ? Number(p.valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '-'

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`badge ${statusBadge[p.status]}`}>{t(`proposal.${p.status}`)}</span>
            {p.main_proc && <span className="badge bg-indigo-50 text-indigo-600 border border-indigo-200">{p.main_proc}</span>}
            {p.generation_mode && <span className="badge bg-gray-100 text-gray-500">{p.generation_mode}</span>}
          </div>
          <h1 className="text-xl font-bold">{p.title}</h1>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <Link to="/proposals" className="btn-secondary">{t('proposal.back')}</Link>
          <a href={`/api/v1/proposals/${id}/export/ps`} className="btn-secondary">⬇ {t('proposal.export_ps')}</a>
          {p.status === 'draft' && (
            <button onClick={() => approveMut.mutate()} className="btn-primary">{t('proposal.approve')} →</button>
          )}
        </div>
      </div>

      {/* Confidence */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        {['escopo', 'horas', 'legislacao', 'comercial'].map(k => (
          <div key={k} className="card !p-4">
            <div className="text-xl font-bold text-teal">{Math.round((conf[k] || 0) * 100)}%</div>
            <div className="text-[11px] font-semibold text-gray-400 mt-0.5">{k.charAt(0).toUpperCase() + k.slice(1)}</div>
            <div className="h-0.5 bg-gray-200 rounded mt-2 overflow-hidden">
              <div className="h-full rounded bg-gradient-to-r from-teal to-emerald-300" style={{ width: `${Math.round((conf[k] || 0) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold">{t('proposal.summary')}</h2>
          <span className="badge bg-teal-light text-teal">IA · {p.main_proc}</span>
        </div>
        <div className="bg-surface rounded-lg p-4 text-sm space-y-1">
          <div className="flex flex-wrap gap-1.5 mb-3">
            <span className="badge bg-blue-50 text-blue-700">{(p.project_type || '').toUpperCase()}</span>
            <span className="badge bg-emerald-50 text-emerald-700">SAP {p.sap_version}</span>
            <span className="badge bg-amber-50 text-amber-700">UFs: {(p.states || []).join(', ')}</span>
          </div>
          <p><b>Total:</b> {p.total_hours}h ({Math.round((p.total_hours || 0) / 8)} dias) · <b className="text-teal">{valor}</b></p>
        </div>
      </div>

      {/* Deliverables */}
      {p.deliverables?.length > 0 && (
        <div className="card mb-4">
          <h2 className="text-sm font-bold mb-3">Entregaveis</h2>
          {[...new Set(p.deliverables.map((d: any) => d.module))].map((mod: any) => (
            <div key={mod} className="mb-3">
              <span className="badge bg-indigo-50 text-indigo-600 border border-indigo-200 mb-1.5">{mod}</span>
              <div className="pl-3 border-l-2 border-indigo-200 space-y-0.5">
                {p.deliverables.filter((d: any) => d.module === mod).map((d: any, i: number) => (
                  <div key={i} className="text-sm text-gray-600"><span className="font-mono text-xs text-indigo-500 mr-1.5">{i + 1}.</span>{d.item}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Work Package */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold">{t('proposal.wp')}</h2>
          <span className="badge bg-amber-50 text-amber-600 border border-amber-200">{p.total_hours}h</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface text-gray-500 text-xs font-bold">
              <th className="text-left p-2">Frente</th><th className="text-left p-2">Nivel</th>
              <th className="text-center p-2">Dias</th><th className="text-center p-2">Horas</th>
              <th className="text-center p-2">Acoes</th>
            </tr>
          </thead>
          <tbody>
            {(p.resources || []).map((r: any, i: number) => (
              <tr key={i} className="border-t border-gray-100">
                <td className="p-2 font-medium">{r.frente}</td>
                <td className="p-2 text-gray-500">{r.nivel}</td>
                <td className="p-2 text-center">{r.dias}</td>
                <td className="p-2 text-center">{r.horas}h</td>
                <td className="p-2 text-center">
                  <button onClick={() => setDetailFrente(r.frente)}
                    className="px-2.5 py-1 rounded-md border border-brand bg-brand-light text-brand text-[11px] font-bold hover:bg-brand hover:text-white transition-all">
                    {t('proposal.detail')}
                  </button>
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-gray-200 bg-surface font-bold">
              <td className="p-2" colSpan={2}>Total</td>
              <td className="p-2 text-center">{(p.resources || []).reduce((s: number, r: any) => s + r.dias, 0)}</td>
              <td className="p-2 text-center">{p.total_hours}h</td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Premises */}
      {p.premises?.length > 0 && (
        <div className="card mb-4">
          <h2 className="text-sm font-bold mb-3">{t('proposal.premises')}</h2>
          <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600">
            {p.premises.map((pr: any, i: number) => <li key={i}>{pr.text}</li>)}
          </ol>
        </div>
      )}

      {/* Investment */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold">{t('proposal.investment')}</h2>
          <span className="badge bg-teal-light text-teal">{valor}</span>
        </div>
        <div className="text-sm text-gray-600 space-y-0.5">
          <p>Modelo: <b>Valor fechado</b> · Faturamento: <b>50% aprovacao + 50% go-live</b></p>
          <p>Garantia: <b>30 dias</b> · Validade: <b>30 dias</b> · Total: <b>{p.total_hours}h</b></p>
        </div>
      </div>

      {/* Detail Modal */}
      {detailFrente && <DetailModal frente={detailFrente} onClose={() => setDetailFrente(null)} />}
    </div>
  )
}
