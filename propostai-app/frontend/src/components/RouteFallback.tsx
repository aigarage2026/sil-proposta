// Lightweight fallback rendered while a lazy-loaded route chunk arrives.
// Intentionally tiny — heavy spinners during route transitions are worse
// than a blank flash on fast networks. The auth-loading spinner in App.tsx
// covers the cold-start case.
export default function RouteFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="animate-spin w-6 h-6 border-2 border-brand border-t-transparent rounded-full" />
    </div>
  )
}
