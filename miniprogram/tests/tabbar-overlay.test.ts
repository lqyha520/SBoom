import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { hideNativeTabBar, tabBarObscured, useTabBarOverlay } from '../src/services/tabbar-overlay'

const runtime = globalThis as typeof globalThis & { uni?: typeof uni }

test('closing a popup restores the custom bar without showing a second native bar', () => {
  const original = runtime.uni
  const calls: string[] = []
  runtime.uni = {
    hideTabBar: () => { calls.push('hide') },
    showTabBar: () => { calls.push('show') },
  } as unknown as typeof uni
  const open = ref(false)
  const scope = effectScope()
  try {
    scope.run(() => useTabBarOverlay(() => open.value))
    assert.equal(tabBarObscured.value, false)
    open.value = true
    assert.equal(tabBarObscured.value, true)
    open.value = false
    assert.equal(tabBarObscured.value, false)
    open.value = true
    scope.stop()
    assert.equal(tabBarObscured.value, false)
    assert.deepEqual(calls, ['hide', 'hide'])
    scope.stop()
    assert.equal(calls.length, 2)
  } finally {
    scope.stop()
    if (original) runtime.uni = original
    else delete runtime.uni
  }
})

test('overlapping popups keep the custom bar hidden until the last owner closes', () => {
  const original = runtime.uni
  const calls: string[] = []
  runtime.uni = {
    hideTabBar: () => { calls.push('hide') },
    showTabBar: () => { calls.push('show') },
  } as unknown as typeof uni
  const first = effectScope()
  const second = effectScope()
  const open = ref(true)
  try {
    first.run(() => useTabBarOverlay(() => true))
    second.run(() => useTabBarOverlay(() => open.value))
    assert.equal(tabBarObscured.value, true)
    first.stop()
    assert.equal(tabBarObscured.value, true)
    open.value = false
    assert.equal(tabBarObscured.value, false)
    assert.deepEqual(calls, ['hide', 'hide'])
  } finally {
    first.stop(); second.stop()
    if (original) runtime.uni = original
    else delete runtime.uni
  }
})

test('custom navigation hides the native bar without an animated transition', () => {
  const original = runtime.uni
  let options: Parameters<typeof uni.hideTabBar>[0]
  runtime.uni = { hideTabBar: (value: typeof options) => { options = value } } as typeof uni
  try {
    hideNativeTabBar()
    assert.equal(options?.animation, false)
    assert.equal(typeof options?.fail, 'function')
  } finally {
    if (original) runtime.uni = original
    else delete runtime.uni
  }
})
