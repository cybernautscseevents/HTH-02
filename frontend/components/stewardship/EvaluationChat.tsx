'use client'

import React, { useState } from 'react'
import { MessageCircle, Send } from 'lucide-react'
import { askEvaluation } from '@/lib/api'
import type { ChatAnswer, ChatTurn } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'

const SUGGESTIONS = [
  'Why was this flagged?',
  'What information is missing?',
  'What does the culture change?',
  'Which sources support the findings?',
]

interface Message extends ChatTurn {
  meta?: ChatAnswer
}

/**
 * Questions about one evaluation, answered by the backend from that evaluation only.
 * Nothing is sent until the user asks; one question is at most one model call.
 */
export function EvaluationChat({ evaluationId }: { evaluationId: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [left, setLeft] = useState<number | null>(null)

  async function ask(question: string) {
    const text = question.trim()
    if (!text || pending) return
    const history: ChatTurn[] = messages.map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: text }])
    setDraft('')
    setPending(true)
    setError(null)
    try {
      const answer = await askEvaluation(evaluationId, text, history)
      setMessages((m) => [...m, { role: 'assistant', content: answer.answer, meta: answer }])
      setLeft(answer.questions_left)
    } catch (e) {
      setMessages((m) => m.slice(0, -1))
      setDraft(text)
      setError(e instanceof Error ? e.message : 'The question could not be sent.')
    } finally {
      setPending(false)
    }
  }

  const exhausted = left === 0

  return (
    <div className="rounded-lg border border-[#E2E1DC] bg-white p-4 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <MessageCircle className="h-4 w-4 text-[#3730A3]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[#1A1A1A]">
          Ask about this result
        </span>
        {left !== null && (
          <span className="ml-auto text-xs text-[#6B6A65]">{left} questions left</span>
        )}
      </div>
      <p className="mb-3 text-xs text-[#6B6A65]">
        Answers explain this evaluation only. They never change a finding; the pharmacist decides.
      </p>

      {messages.length > 0 && (
        <div className="mb-3 max-h-80 space-y-2 overflow-y-auto">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`rounded-md px-3 py-2 ${
                m.role === 'user'
                  ? 'ml-8 bg-[#F4F3EF] text-[#1A1A1A]'
                  : 'mr-8 border border-[#E2E1DC] text-[#1A1A1A]'
              }`}
            >
              <p className="whitespace-pre-line leading-relaxed">{m.content}</p>
              {m.meta && (
                <p className="mt-1 text-xs text-[#6B6A65]">
                  {m.meta.generated_by === 'AI_WORDED'
                    ? `AI-worded${m.meta.model ? ` (${m.meta.model})` : ''}`
                    : `Not answered by AI${m.meta.fallback_reason ? `: ${m.meta.fallback_reason}` : ''}`}
                  {m.meta.cached && ' · repeated question, no new call'}
                </p>
              )}
            </div>
          ))}
          {pending && <p className="mr-8 px-3 py-2 text-xs text-[#6B6A65]">Thinking…</p>}
        </div>
      )}

      {messages.length === 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              disabled={pending || exhausted}
              className="rounded-full border border-[#E2E1DC] px-3 py-1 text-xs text-[#1A1A1A] hover:bg-[#F4F3EF] disabled:opacity-45"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mb-2 text-xs text-[#8B1A1A]">{error}</p>}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          ask(draft)
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={500}
          disabled={exhausted}
          placeholder={exhausted ? 'No questions left for this evaluation' : 'Ask a question…'}
          className="flex-1 rounded-md border border-[#C8C7C0] px-3 py-2 text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#3730A3]/30"
        />
        <Button
          type="submit"
          size="sm"
          isLoading={pending}
          disabled={!draft.trim() || pending || exhausted}
          leftIcon={<Send className="h-3.5 w-3.5" />}
        >
          Ask
        </Button>
      </form>
    </div>
  )
}
