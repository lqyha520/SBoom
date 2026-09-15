export const uiConfig = {
  colors: { primary: 'emerald', secondary: 'sky', neutral: 'zinc' },
  button: { slots: { base: 'cursor-pointer font-medium' } },
  input: { slots: { root: 'w-full' } },
  select: { slots: { base: 'w-full' } },
  textarea: { slots: { root: 'w-full' } },
  modal: { slots: { content: 'rounded-lg', footer: 'justify-end' } },
  slideover: { slots: { content: 'max-w-md', footer: 'justify-end' } },
} as const
