export function Pagination({ page, total, size, onChange }: {
  page: number; total: number; size: number; onChange: (page: number) => void
}) {
  if (total <= size) return null
  return <nav className="pagination" aria-label="Pagination">
    <span>{(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}</span>
    <div>
      <button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous page</button>
      <span>Page {page}</span>
      <button disabled={page * size >= total} onClick={() => onChange(page + 1)}>Next page</button>
    </div>
  </nav>
}
