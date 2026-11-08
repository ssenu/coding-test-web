// 문제 마크다운을 HTML로 바꾸고 위험한 태그와 속성을 제거한다.
import DOMPurify from 'dompurify'
import { marked } from 'marked'

export function renderMarkdown(source: string): string {
  const html = marked.parse(source ?? '', { async: false, gfm: true, breaks: true })
  return DOMPurify.sanitize(html)
}
