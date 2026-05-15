// Onda 6 prep — per v3 §17.4 the Portal SPA will lazy-load each product
// under `agn-portal/src/products/{slug}/`. Until the Portal SPA exists
// in an accessible environment, we own the layout locally so the
// upcoming move is a `git mv` instead of a refactor.
//
// All page imports use React.lazy so vite emits a separate chunk per
// route. The current monolithic frontend will adopt these lazy imports
// from App.tsx in the next commit — keeps the regression surface small.
import { lazy } from 'react'
import { Navigate, type RouteObject } from 'react-router-dom'

const ProposalList = lazy(() => import('@/pages/ProposalList'))
const IntakeForm = lazy(() => import('@/pages/IntakeForm'))
const ProposalDetail = lazy(() => import('@/pages/ProposalDetail'))
const GenerationView = lazy(() => import('@/pages/GenerationView'))

// Routes are mounted under the product's basePath in the Portal SPA.
// Today it's mounted at the SPA root; tomorrow at `/sil-proposta/*`.
// Keeping them relative makes either mount point work without changes.
export const silPropostaRoutes: RouteObject[] = [
  { index: true, element: <Navigate to="proposals" replace /> },
  { path: 'proposals', element: <ProposalList /> },
  { path: 'proposals/new', element: <IntakeForm /> },
  { path: 'proposals/:id', element: <ProposalDetail /> },
  { path: 'proposals/:id/generate', element: <GenerationView /> },
]

export const silPropostaProduct = {
  slug: 'sil-proposta',
  label: 'Sil-Proposta',
  basePath: '/',
  routes: silPropostaRoutes,
}
