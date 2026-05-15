import { useEffect } from 'react'
import { DETAIL_DATA, getDetailKey } from '@/data/sap-transactions'

interface Props {
  frente: string
  onClose: () => void
}

export default function DetailModal({ frente, onClose }: Props) {
  const key = getDetailKey(frente)
  const data = DETAIL_DATA[key]

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  if (!data) return null

  const isAbap = key === 'ABAP'

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center animate-[fadeIn_.2s_ease]" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-white rounded-2xl w-full max-w-[720px] max-h-[85vh] overflow-hidden flex flex-col shadow-2xl animate-[modalIn_.25s_ease]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-surface">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg text-white" style={{ background: data.color }}>{data.icon}</div>
            <div>
              <h2 className="text-base font-bold">{data.label}</h2>
              <p className="text-xs text-gray-500">{frente} · Senior</p>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg border border-gray-200 bg-white text-gray-400 hover:bg-red-500 hover:text-white hover:border-red-500 flex items-center justify-center transition-all text-lg">x</button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Transactions */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-xs font-bold text-gray-700">Transacoes SAP</h3>
              <span className="badge text-[9px]" style={{ background: `${data.color}18`, color: data.color }}>{data.transactions.length} transacoes</span>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {data.transactions.map((tx, i) => (
                <div key={i} className="bg-surface border border-gray-200 rounded-lg p-2 hover:border-brand hover:bg-brand-light transition-all">
                  <div className="text-xs font-extrabold font-mono text-brand">{tx.code}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5 leading-tight">{tx.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Activities */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-xs font-bold text-gray-700">Atividades detalhadas</h3>
              <span className="badge text-[9px]" style={{ background: `${data.color}18`, color: data.color }}>{data.activities.length} atividades</span>
            </div>
            <ul className="space-y-0.5">
              {data.activities.map((act, i) => (
                <li key={i} className="relative pl-5 py-1 border-b border-gray-100 last:border-0 text-xs text-gray-600">
                  <span className="absolute left-1 text-brand font-bold">▸</span>{act}
                </li>
              ))}
            </ul>
          </div>

          {/* ABAP Code */}
          {isAbap && data.codeExamples && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <h3 className="text-xs font-bold text-gray-700">Codigo ABAP a ser desenvolvido</h3>
                <span className="badge bg-amber-50 text-amber-600 text-[9px]">{data.codeExamples.length} objetos</span>
              </div>
              {data.codeExamples.map((ex, i) => (
                <div key={i} className="mb-4">
                  <div className="text-xs font-bold text-gray-700 mb-1">{ex.title}</div>
                  <div className="relative bg-[#0D1117] border border-[#21262D] rounded-xl p-4 overflow-x-auto">
                    <span className="absolute top-2 right-3 text-[9px] font-bold px-2 py-0.5 rounded bg-white/[.06] text-white/30">{ex.lang}</span>
                    <pre className="text-[11px] leading-relaxed text-[#C9D1D9] font-mono whitespace-pre" dangerouslySetInnerHTML={{ __html: ex.code }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
