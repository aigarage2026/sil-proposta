import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import api from '@/lib/api'

const TYPES = ['ams', 'new', 'migration', 'support']
const VERSIONS = ['ecc604', 'ecc605', 's4op', 's4cloud']
const UFS = ['SP', 'GO', 'RJ', 'PR', 'RS', 'SC', 'MG', 'BA', 'PE', 'CE']
const MODELS = ['fixed', 't_m']

function ToggleGroup({ options, value, onChange, labelKey, multi = false }: any) {
  const { t } = useTranslation()
  const selected = multi ? (value || []) : [value]
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt: string) => {
        const active = selected.includes(opt)
        return (
          <button key={opt} type="button"
            className={`px-3.5 py-1.5 rounded-full border text-sm font-medium transition-all ${active ? 'bg-brand border-brand text-white' : 'border-gray-300 text-gray-600 hover:border-brand hover:text-brand hover:bg-brand-light'}`}
            onClick={() => {
              if (multi) onChange(active ? selected.filter((s: string) => s !== opt) : [...selected, opt])
              else onChange(opt)
            }}>
            {labelKey ? t(`${labelKey}.${opt}`) : opt}
          </button>
        )
      })}
    </div>
  )
}

export default function IntakeForm() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const [form, setForm] = useState({ project_type: '', sap_version: '', states: [] as string[], commercial_model: '', rfp_text: '', notes: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))
  const valid = form.project_type && form.sap_version && form.states.length && form.commercial_model && form.rfp_text.length >= 10

  const submit = async () => {
    if (!valid) return
    setLoading(true)
    setError('')
    try {
      // TODO: company_id from context
      const r = await api.post('/api/v1/proposals', { ...form, company_id: 'default', lang: 'pt' })
      nav(`/proposals/${r.data.proposal_id}/generate`, { state: r.data })
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Erro ao gerar proposta')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">{t('intake.title')}</h1>
        <p className="text-sm text-gray-500 mt-1">{t('intake.desc')}</p>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm">{error}</div>}

      <div className="space-y-5">
        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.project_type')}</label>
          <ToggleGroup options={TYPES} value={form.project_type} onChange={(v: string) => set('project_type', v)} labelKey="intake.types" />
        </div>

        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.sap_version')}</label>
          <ToggleGroup options={VERSIONS} value={form.sap_version} onChange={(v: string) => set('sap_version', v)} labelKey="intake.versions" />
        </div>

        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.states')}</label>
          <ToggleGroup options={UFS} value={form.states} onChange={(v: string[]) => set('states', v)} multi />
        </div>

        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.commercial')}</label>
          <ToggleGroup options={MODELS} value={form.commercial_model} onChange={(v: string) => set('commercial_model', v)} labelKey="intake.models" />
        </div>

        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.rfp')}</label>
          <textarea value={form.rfp_text} onChange={e => set('rfp_text', e.target.value)}
            className="input min-h-[100px] resize-y" placeholder="Descreva a necessidade do cliente..." />
        </div>

        <div className="card">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{t('intake.notes')}</label>
          <textarea value={form.notes} onChange={e => set('notes', e.target.value)}
            className="input min-h-[60px] resize-y" placeholder="Observacoes opcionais..." />
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button onClick={() => nav('/proposals')} className="btn-secondary">{t('common.cancel')}</button>
          <button onClick={submit} disabled={!valid || loading} className="btn-primary">
            {loading ? '...' : t('intake.generate')}
          </button>
        </div>
      </div>
    </div>
  )
}
