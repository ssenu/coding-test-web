import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../src/lib/markdown'

describe('renderMarkdown', () => {
  it('마크다운을 HTML로 바꾸고 스크립트를 지운다', () => {
    const html = renderMarkdown('# 제목\n\n**굵게** <script>alert(1)</script><img src=x onerror="alert(1)">')
    expect(html).toContain('<h1>제목</h1>')
    expect(html).toContain('<strong>굵게</strong>')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
  })
})
