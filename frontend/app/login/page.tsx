'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ShieldCheck } from 'lucide-react'
import { DEMO_PASSWORD, DEMO_USERS, signIn, useSession } from '@/lib/auth'
import { Button } from '@/components/ui/Button'

export default function LoginPage() {
  const router = useRouter()
  const { user, ready } = useSession()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ready && user) router.replace('/dashboard')
  }, [ready, user, router])

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!signIn(username, password)) {
      setError('Username or password is incorrect.')
      return
    }
    router.replace('/dashboard')
  }

  const fill = (name: string) => {
    setUsername(name)
    setPassword(DEMO_PASSWORD)
    setError(null)
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[#1A1A1A]">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight text-[#1A1A1A]">RxGuard</h1>
            <p className="text-xs text-[#6B6A65]">Antibiotic stewardship copilot</p>
          </div>
        </div>

        <form onSubmit={submit} className="rounded-[8px] border border-[#E2E1DC] bg-white p-6">
          <h2 className="text-base font-medium text-[#1A1A1A]">Sign in</h2>

          <label htmlFor="username" className="mt-4 block text-xs font-medium text-[#6B6A65]">Username</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
            className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A] focus:border-[#3730A3] focus:outline-none focus:ring-2 focus:ring-[#3730A3]/20"
          />

          <label htmlFor="password" className="mt-3 block text-xs font-medium text-[#6B6A65]">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A] focus:border-[#3730A3] focus:outline-none focus:ring-2 focus:ring-[#3730A3]/20"
          />

          {error && (
            <p role="alert" className="mt-3 rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-3 py-2 text-xs text-[#8B1A1A]">
              {error}
            </p>
          )}

          <Button type="submit" className="mt-5 w-full">Sign in</Button>
        </form>

        <div className="mt-4 rounded-[8px] border border-[#E2E1DC] bg-[#F4F3EF] p-4">
          <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-[#6B6A65]">Demo accounts</p>
          <p className="mt-1 text-xs text-[#6B6A65]">
            Demonstration sign-in only; it does not secure any data. Password for both:{' '}
            <span className="font-mono text-[#1A1A1A]">{DEMO_PASSWORD}</span>
          </p>
          <div className="mt-3 space-y-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.username}
                type="button"
                onClick={() => fill(u.username)}
                className="flex w-full items-center justify-between rounded-md border border-[#E2E1DC] bg-white px-3 py-2 text-left hover:bg-[#FAFAF8]"
              >
                <span className="text-sm text-[#1A1A1A]">{u.name}</span>
                <span className="font-mono text-[10px] text-[#6B6A65]">{u.username} · {u.role}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
