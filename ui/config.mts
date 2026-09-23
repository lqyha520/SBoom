export const uiConfig = {
  colors: { primary: 'emerald', secondary: 'sky', neutral: 'zinc' },
  button: { slots: { base: 'cursor-pointer font-medium' } },
  input: { slots: { root: 'w-full' } },
  select: { slots: { base: 'w-full' } },
  textarea: { slots: { root: 'w-full' } },
  modal: { slots: { overlay: 'bg-black/40', content: 'rounded-xl bg-default ring-default', header: 'border-b border-default', footer: 'justify-end gap-3 bg-muted border-t border-default' } },
  alert: { defaultVariants: { variant: 'soft' } },
  slideover: { slots: { content: 'max-w-md', footer: 'justify-end' } },
} as const
