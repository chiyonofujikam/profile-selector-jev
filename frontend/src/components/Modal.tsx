import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

type Props = { title: string; children: ReactNode; onClose: () => void }

export function Modal({ title, children, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current!
    dialog.showModal()
    dialog.querySelector<HTMLElement>('input[required]')?.focus()
    return () => dialog.close()
  }, [])

  return <dialog ref={ref} className="modal" aria-labelledby="modal-title" onCancel={onClose}
    onClick={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="modal-heading"><h2 id="modal-title">{title}</h2>
      <button onClick={onClose} aria-label="Close dialog">×</button></div>
    <div className="modal-content">{children}</div>
  </dialog>
}
