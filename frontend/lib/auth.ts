'use client'

import { useCallback, useEffect, useState } from 'react'

/**
 * Demo sign-in. There is no authentication on the backend, so this only gates the screens and
 * names the reviewer on reviews and signed plans. It is not a security boundary: the accounts
 * and the password are in the page source.
 */
export type Role = 'doctor' | 'pharmacist'

export interface DemoUser {
  username: string
  name: string
  role: Role
  badge: string
  initials: string
}

export const DEMO_PASSWORD = 'stewardship'

export const DEMO_USERS: DemoUser[] = [
  { username: 'priya', name: 'Dr. Priya Mehta', role: 'pharmacist', badge: 'PHARMACIST · ID-0042', initials: 'PM' },
  { username: 'suresh', name: 'Dr. Suresh Kumar', role: 'doctor', badge: 'PHYSICIAN · ID-0031', initials: 'SK' },
]

const STORAGE_KEY = 'rxguard.session'

export function signIn(username: string, password: string): DemoUser | null {
  const user = DEMO_USERS.find((u) => u.username === username.trim().toLowerCase())
  if (!user || password !== DEMO_PASSWORD) return null
  try {
    localStorage.setItem(STORAGE_KEY, user.username)
  } catch {
    // Storage blocked: the session lasts only until the page reloads.
  }
  return user
}

export function signOut(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing stored, nothing to clear.
  }
}

function storedUser(): DemoUser | null {
  try {
    const username = localStorage.getItem(STORAGE_KEY)
    return DEMO_USERS.find((u) => u.username === username) ?? null
  } catch {
    return null
  }
}

/** The signed-in user. `ready` is false until storage has been read, so callers do not redirect early. */
export function useSession() {
  const [user, setUser] = useState<DemoUser | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setUser(storedUser())
    setReady(true)
  }, [])

  const logout = useCallback(() => {
    signOut()
    setUser(null)
  }, [])

  return { user, ready, logout }
}

/** Reviewer name as recorded in the audit log, e.g. "Dr. Priya Mehta (Pharmacist)". */
export function reviewerLabel(user: DemoUser | null): string {
  if (!user) return 'Unknown reviewer'
  return `${user.name} (${user.role === 'pharmacist' ? 'Pharmacist' : 'Physician'})`
}
