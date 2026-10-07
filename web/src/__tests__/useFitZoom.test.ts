import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { useFitZoom } from '../useFitZoom'

describe('paper fit zoom', () => {
  let wrapper: VueWrapper | undefined
  let element: HTMLElement | undefined
  let resize: () => void
  const disconnect = vi.fn()
  const observe = vi.fn()
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { resize = callback }
      observe = observe
      disconnect = disconnect
    })
  })
  afterEach(() => { wrapper?.unmount(); element?.remove(); vi.unstubAllGlobals() })

  function setup(width = 500, padding = 20) {
    const container = document.createElement('div')
    Object.defineProperty(container, 'clientWidth', { value: width, configurable: true })
    container.style.padding = padding + 'px'
    document.body.appendChild(container)
    element = container
    let state!: ReturnType<typeof useFitZoom>
    wrapper = mount(defineComponent({ setup() { state = useFitZoom(ref(container)); return () => h('div') } }))
    return { state, container }
  }

  it('fits within the available width after container padding', () => {
    const { state } = setup()
    expect(state.zoom.value).toBeCloseTo((500 - 40 - 12) / 810)
  })
  it('restores automatic fitting when the fit-width button sends zero', () => {
    const { state } = setup()
    const auto = state.zoom.value
    state.setManual(0.8)
    expect(state.zoom.value).toBe(0.8)
    state.setManual(0)
    expect(state.manual.value).toBe(0)
    expect(state.zoom.value).toBe(auto)
  })
  it('clamps manual zoom and never emits NaN', () => {
    const { state } = setup()
    state.setManual(2)
    expect(state.zoom.value).toBe(1)
    state.setManual(0.1)
    expect(state.zoom.value).toBe(0.25)
    state.setManual(NaN)
    expect(Number.isFinite(state.zoom.value)).toBe(true)
    expect(state.manual.value).toBe(0)
  })
  it('keeps zoom when hidden and recalculates when a mobile tab becomes visible', () => {
    const { state, container } = setup()
    const previous = state.zoom.value
    Object.defineProperty(container, 'clientWidth', { value: 0, configurable: true })
    resize()
    expect(state.zoom.value).toBe(previous)
    Object.defineProperty(container, 'clientWidth', { value: 390, configurable: true })
    resize()
    expect(state.zoom.value).toBeCloseTo((390 - 40 - 12) / 810)
  })
  it('disconnects the observer when the pane unmounts', () => {
    setup()
    wrapper!.unmount()
    wrapper = undefined
    expect(disconnect).toHaveBeenCalledOnce()
  })
  it('observes a container that appears after mount and its replacement', async () => {
    const target = ref<HTMLElement | null>(null)
    let state!: ReturnType<typeof useFitZoom>
    wrapper = mount(defineComponent({ setup() { state = useFitZoom(target); return () => h('div') } }))
    expect(observe).not.toHaveBeenCalled()
    const first = document.createElement('div')
    Object.defineProperty(first, 'clientWidth', { value: 390 })
    target.value = first
    await nextTick()
    expect(state.zoom.value).toBeCloseTo((390 - 12) / 810)
    state.setManual(0.8)
    const second = document.createElement('div')
    Object.defineProperty(second, 'clientWidth', { value: 600 })
    target.value = second
    await nextTick()
    expect(observe).toHaveBeenLastCalledWith(second)
    expect(disconnect).toHaveBeenCalledOnce()
    expect(state.zoom.value).toBe(0.8)
    state.setManual(0)
    expect(state.zoom.value).toBeCloseTo((600 - 12) / 810)
  })
})
