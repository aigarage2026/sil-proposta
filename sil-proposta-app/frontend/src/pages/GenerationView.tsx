import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

interface AgentDef {
  id: string; name: string; role: string; color: string
  x: number; y: number
}

const AGENTS: AgentDef[] = [
  { id: 'orch', name: 'Orion',   role: 'Orquestrador',    color: '#60A5FA', x: 50, y: 8 },
  { id: 'ver',  name: 'Valeria', role: 'Versao SAP',      color: '#A78BFA', x: 80, y: 22 },
  { id: 'sd',   name: 'Sofia',   role: 'Agente SD',       color: '#34D399', x: 18, y: 28 },
  { id: 'fi',   name: 'Felix',   role: 'Agente FI',       color: '#4ADE80', x: 38, y: 28 },
  { id: 'abap', name: 'Axel',    role: 'ABAP Estrutural', color: '#C084FC', x: 28, y: 52 },
  { id: 'drc',  name: 'Diana',   role: 'Agente DRC',      color: '#22D3EE', x: 50, y: 48 },
  { id: 'fest', name: 'Estela',  role: 'Fiscal Estadual', color: '#FB923C', x: 12, y: 72 },
  { id: 'ffed', name: 'Fabio',   role: 'Fiscal Federal',  color: '#F87171', x: 32, y: 74 },
  { id: 'eq',   name: 'Eduardo', role: 'Equipe / GP',     color: '#818CF8', x: 52, y: 76 },
  { id: 'com',  name: 'Camila',  role: 'Comercial',       color: '#2DD4BF', x: 72, y: 68 },
]

const CONNS = [
  ['orch','sd'],['orch','fi'],['orch','ver'],['orch','abap'],['orch','drc'],
  ['sd','abap'],['fi','drc'],['fi','abap'],['drc','abap'],
  ['abap','eq'],['fest','eq'],['ffed','eq'],['eq','com'],['com','orch'],
]

type AgentStatus = 'idle' | 'running' | 'done'

export default function GenerationView() {
  const { id } = useParams()
  const loc = useLocation()
  const nav = useNavigate()
  const { t } = useTranslation()

  const [states, setStates] = useState<Record<string, AgentStatus>>(() => {
    const s: Record<string, AgentStatus> = {}
    AGENTS.forEach(a => s[a.id] = 'idle')
    return s
  })
  const [progress, setProgress] = useState(0)
  const [log, setLog] = useState<string[]>([])
  const [done, setDone] = useState(false)
  const canvasRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Simular execucao dos agentes
    const steps = [
      { act: ['orch'], msg: 'Orion: analisando intake...' },
      { done: ['orch'], act: ['ver', 'sd', 'fi'], msg: 'Valeria + Sofia + Felix em paralelo' },
      { done: ['ver'], act: ['drc', 'abap'], msg: 'Diana: ECONF → CPI · Axel: cadeia ABAP' },
      { done: ['sd', 'fi'], act: ['fest', 'ffed'], msg: 'Estela + Fabio: fiscais simultaneos' },
      { done: ['drc', 'abap'], act: ['eq'], msg: 'Eduardo: equipe e GP' },
      { done: ['fest', 'ffed'], act: ['com'], msg: 'Camila: modelo comercial' },
      { done: ['eq', 'com'], msg: '✓ Proposta concluida!' },
    ]

    let idx = 0
    const interval = setInterval(() => {
      if (idx >= steps.length) {
        clearInterval(interval)
        setDone(true)
        setProgress(100)
        return
      }
      const step = steps[idx++]
      setStates(prev => {
        const next = { ...prev }
        step.done?.forEach(id => next[id] = 'done')
        step.act?.forEach(id => next[id] = 'running')
        return next
      })
      setLog(prev => [step.msg, ...prev].slice(0, 10))
      const doneCount = Object.values(states).filter(s => s === 'done').length + (step.done?.length || 0)
      setProgress(Math.round((doneCount / AGENTS.length) * 100))
    }, 1400)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="fixed inset-0 bg-[#060C1A] z-50 flex flex-col font-mono overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_20%_15%,rgba(59,130,246,.12)_0%,transparent_55%),radial-gradient(ellipse_at_80%_80%,rgba(0,255,150,.07)_0%,transparent_55%)]" />
      <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.015) 1px, transparent 1px)', backgroundSize: '48px 48px' }} />

      {/* Topbar */}
      <header className="relative z-10 flex items-center justify-between px-5 h-13 border-b border-white/[.07] bg-[#060C1A]/90 backdrop-blur">
        <div className="flex items-center gap-3">
          <button onClick={() => nav(`/proposals/${id}`)} className="px-3 py-1.5 rounded-lg border border-white/[.12] bg-white/[.04] text-white/60 text-xs font-semibold hover:bg-white/[.08]">← Voltar</button>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/[.06]">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#00FF96] animate-pulse" />
            <span className="text-[11px] font-bold text-emerald-400">{done ? '✓ Concluido' : 'Processando...'}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-24 h-1 rounded bg-white/[.07] overflow-hidden">
              <div className="h-full rounded bg-gradient-to-r from-blue-500 to-emerald-400 transition-all duration-1000" style={{ width: `${progress}%` }} />
            </div>
            <span className="text-xs font-bold text-emerald-400 min-w-[34px]">{progress}%</span>
          </div>
          {done && <button onClick={() => nav(`/proposals/${id}`)} className="px-4 py-1.5 rounded-lg border border-blue-500/50 bg-blue-500/10 text-blue-400 text-xs font-bold hover:bg-blue-500/20">Ver proposta →</button>}
        </div>
      </header>

      {/* Canvas */}
      <div className="relative flex-1" ref={canvasRef}>
        {/* SVG connections */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          {CONNS.map(([a, b], i) => {
            const pa = AGENTS.find(ag => ag.id === a)!
            const pb = AGENTS.find(ag => ag.id === b)!
            const active = states[a] === 'running' || states[b] === 'running'
            const completed = states[a] === 'done' && states[b] === 'done'
            return (
              <line key={i} x1={`${pa.x}%`} y1={`${pa.y}%`} x2={`${pb.x}%`} y2={`${pb.y}%`}
                stroke={active ? 'rgba(0,255,150,.4)' : completed ? 'rgba(74,222,128,.18)' : 'rgba(255,255,255,.05)'}
                strokeWidth={active ? 2 : 1.5} strokeDasharray="7 5"
                className={active ? 'animate-[dash_1s_linear_infinite]' : ''} />
            )
          })}
        </svg>

        {/* Agent nodes */}
        {AGENTS.map(ag => {
          const st = states[ag.id]
          return (
            <div key={ag.id} className="absolute -translate-x-1/2 -translate-y-1/2 text-center w-[90px] z-10 transition-opacity duration-500"
              style={{ left: `${ag.x}%`, top: `${ag.y}%`, opacity: st === 'idle' ? 0.18 : 1 }}>
              {/* Ring */}
              <div className="relative w-16 h-16 mx-auto mb-1">
                <div className={`absolute -inset-1.5 rounded-full border-2 transition-all duration-500 ${
                  st === 'running' ? 'border-emerald-400 shadow-[0_0_22px_rgba(0,255,150,.6)] animate-pulse'
                  : st === 'done' ? 'border-emerald-400/50 shadow-[0_0_12px_rgba(74,222,128,.28)]'
                  : 'border-white/[.06]'
                }`} />
                {/* Avatar circle */}
                <div className="w-16 h-16 rounded-full flex items-center justify-center text-lg font-extrabold"
                  style={{ background: `${ag.color}22`, border: `2px solid ${ag.color}`, color: ag.color }}>
                  {ag.name[0]}
                </div>
              </div>
              <div className="text-[10px] font-bold text-white">{ag.name}</div>
              <div className="text-[8px] text-white/25">{ag.role}</div>
              <span className={`inline-block mt-1 text-[8px] font-bold px-2 py-0.5 rounded-full ${
                st === 'running' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 animate-pulse'
                : st === 'done' ? 'bg-emerald-500/8 text-emerald-300 border border-emerald-400/20'
                : 'bg-white/[.04] text-white/20 border border-white/[.07]'
              }`}>
                {st === 'running' ? 'processando' : st === 'done' ? '✓ concluido' : 'aguardando'}
              </span>
            </div>
          )
        })}
      </div>

      {/* Log panel */}
      <div className="absolute left-4 bottom-4 w-64 bg-[#050A16]/95 border border-white/[.07] rounded-xl p-3 z-20">
        <div className="text-[9px] font-bold text-white/25 uppercase tracking-wide mb-2">Log ao vivo</div>
        {log.map((msg, i) => (
          <div key={i} className="flex gap-2 py-0.5 text-[10px] border-b border-white/[.03] animate-[fadeIn_.25s_ease]">
            <span className="text-emerald-400/50 flex-shrink-0">{new Date().toLocaleTimeString('pt-BR', { hour12: false })}</span>
            <span className="text-slate-400 truncate">{msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
