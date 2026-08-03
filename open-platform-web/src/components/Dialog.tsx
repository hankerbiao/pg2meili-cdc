import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

export function Dialog({ open, onOpenChange, title, description, children }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="dialog-content">
          <div className="dialog-header">
            <div><DialogPrimitive.Title>{title}</DialogPrimitive.Title>{description && <DialogPrimitive.Description>{description}</DialogPrimitive.Description>}</div>
            <DialogPrimitive.Close className="icon-button" aria-label="关闭"><X size={18} /></DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, danger = false, onConfirm }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel: string
  danger?: boolean
  onConfirm: () => void | Promise<void>
}) {
  return (
    <AlertDialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Overlay className="dialog-overlay" />
        <AlertDialogPrimitive.Content className="dialog-content compact-dialog">
          <AlertDialogPrimitive.Title>{title}</AlertDialogPrimitive.Title>
          <AlertDialogPrimitive.Description>{description}</AlertDialogPrimitive.Description>
          <div className="dialog-actions">
            <AlertDialogPrimitive.Cancel className="button button-secondary">取消</AlertDialogPrimitive.Cancel>
            <AlertDialogPrimitive.Action className={danger ? 'button button-danger' : 'button button-primary'} onClick={onConfirm}>{confirmLabel}</AlertDialogPrimitive.Action>
          </div>
        </AlertDialogPrimitive.Content>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  )
}
