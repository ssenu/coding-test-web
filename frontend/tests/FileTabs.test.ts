import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import FileTabs from '../src/components/FileTabs.vue'

describe('FileTabs', () => {
  it('파일마다 탭을 만들고 첫 파일을 연다', () => {
    const wrapper = mount(FileTabs, { props: { files: { 'a.py': 'A = 1', 'b.py': 'B = 2' } } })
    const tabs = wrapper.findAll('[role=tab]')
    expect(tabs.map((t) => t.text())).toEqual(['a.py', 'b.py'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')
    expect(wrapper.find('.cm-content').text()).toContain('A = 1')
  })

  it('탭을 누르면 그 파일을 보여 준다', async () => {
    const wrapper = mount(FileTabs, { props: { files: { 'a.py': 'A = 1', 'b.py': 'B = 2' } } })
    await wrapper.findAll('[role=tab]')[1]!.trigger('click')
    expect(wrapper.find('.cm-content').text()).toContain('B = 2')
  })

  it('밖에서 파일 내용이 바뀌면 편집기에 반영한다', async () => {
    const wrapper = mount(FileTabs, { props: { files: { 'a.py': 'old' }, readonly: true } })
    await wrapper.setProps({ files: { 'a.py': 'new' } })
    await nextTick()
    expect(wrapper.find('.cm-content').text()).toContain('new')
    expect(wrapper.find('.cm-content').attributes('contenteditable')).toBe('false')
  })

  it('파일이 없으면 안내 문구를 보여 준다', () => {
    const wrapper = mount(FileTabs, { props: { files: {} } })
    expect(wrapper.text()).toContain('파일이 없습니다.')
  })
})
