import { defineComponent, h } from 'vue'

// Only replace Nuxt UI primitives; mount the actual business components and
// exercise their DOM events, validation and API payloads.
const container = defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) })
const checkbox = defineComponent({
  props: ['modelValue', 'label', 'disabled'], emits: ['update:modelValue'],
  setup: (props, { emit }) => () => h('label', [h('input', {
    type: 'checkbox', checked: props.modelValue, disabled: props.disabled,
    onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
  }), props.label]),
})
export const uiStubs = {
  UModal: defineComponent({
    props: ['open', 'title'],
    setup: (props, { slots }) => () => props.open ? h('div', { role: 'dialog' }, [
      h('h2', props.title), slots.body?.(), slots.footer?.(),
    ]) : null,
  }),
  UButton: defineComponent({
    props: ['label', 'loading', 'disabled'],
    setup: (props, { slots }) => () => h('button', { disabled: props.disabled || props.loading }, props.label || slots.default?.()),
  }),
  UInput: defineComponent({
    props: ['modelValue'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('input', {
      value: props.modelValue, onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    }),
  }),
  UTextarea: defineComponent({
    props: ['modelValue', 'disabled'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('textarea', {
      value: props.modelValue, disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
    }),
  }),
  USelect: defineComponent({
    props: ['modelValue', 'items'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('select', {
      value: props.modelValue, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value),
    }, (props.items || []).map((item: { value: string; label: string }) => h('option', { value: item.value }, item.label))),
  }),
  UCheckbox: checkbox, USwitch: checkbox,
  UTabs: defineComponent({
    props: ['items', 'modelValue'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('div', (props.items || []).map((item: { value: string; label: string }) =>
      h('button', { onClick: () => emit('update:modelValue', item.value) }, item.label))),
  }),
  UPagination: defineComponent({
    props: ['page', 'disabled'], emits: ['update:page'],
    setup: (props, { emit }) => () => h('button', {
      disabled: props.disabled, onClick: () => emit('update:page', props.page + 1),
    }, '下一页'),
  }),
  UAlert: defineComponent({ props: ['title'], setup: props => () => h('p', props.title) }),
  UFormField: container, UTooltip: container, UBadge: container, UDropdownMenu: container, UIcon: true,
}
