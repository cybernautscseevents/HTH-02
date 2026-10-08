'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  ClipboardList,
  AlertTriangle,
  Clock,
  Activity,
  TrendingUp,
  ArrowUpRight,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { getStats } from '@/lib/api'
import type { DashboardStats, EvaluationStatus } from '@/types/stewardship'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

interface StatCardProps {
  label: string
  value: number | string
  icon: React.ReactNode
  iconBg: string
  trend?: string
  href?: string
  highlight?: boolean
}

function StatCard({ label, value, icon, iconBg, trend, href, highlight }: StatCardProps) {
  const inner = (
    <div
      className={`rounded-xl border p-5 transition-all group ${
        highlight
          ? 'border-rose-500/30 bg-rose-500/5 hover:border-rose-500/50'
          : 'border-[#2d3148] bg-[#1e2235] hover:border-[#3b4263]'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className={`p-2.5 rounded-xl ${iconBg}`}>{icon}</div>
        {href && (
          <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-slate-300 transition-colors" />
        )}
      </div>
      <p className="mt-4 text-3xl font-bold text-slate-100 tabular-nums">{value}</p>
      <p className="mt-1 text-sm text-slate-400">{label}</p>
      {trend && <p className="mt-2 text-xs text-slate-500">{trend}</p>}
    </div>
  )

  if (href) {
    return <Link href={href}>{inner}</Link>
  }
  return inner
}

const STATUS_ICON: Record<EvaluationStatus, React.ReactNode> = {
  FLAGGED: <AlertTriangle className="w-4 h-4 text-rose-400" />,
  OK: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  INCOMPLETE: <XCircle className="w-4 h-4 text-amber-400" />,
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchStats = async () => {
    try {
      const data = await getStats()
      setStats(data)
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Antibiotic stewardship overview · Updated{' '}
            {new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />}
            onClick={() => {
              setRefreshing(true)
              fetchStats()
            }}
          >
            Refresh
          </Button>
          <Link href="/upload">
            <Button variant="primary" size="sm" leftIcon={<ClipboardList className="w-4 h-4" />}>
              New Prescription
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          label="Total Reviewed"
          value={stats?.total_reviewed ?? 0}
          icon={<ClipboardList className="w-5 h-5 text-indigo-400" />}
          iconBg="bg-indigo-500/10"
          trend="Last 30 days"
        />
        <StatCard
          label="Flagged"
          value={stats?.flagged_count ?? 0}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
          iconBg="bg-rose-500/10"
          href="/timeout"
          highlight={(stats?.flagged_count ?? 0) > 0}
        />
        <StatCard
          label="Pending Review"
          value={stats?.pending_review_count ?? 0}
          icon={<Activity className="w-5 h-5 text-amber-400" />}
          iconBg="bg-amber-500/10"
          highlight={(stats?.pending_review_count ?? 0) > 0}
        />
        <StatCard
          label="High Severity"
          value={stats?.high_severity_count ?? 0}
          icon={<TrendingUp className="w-5 h-5 text-rose-400" />}
          iconBg="bg-rose-500/10"
          highlight={(stats?.high_severity_count ?? 0) > 0}
        />
        <StatCard
          label="48h Reviews Due"
          value={stats?.timeout_due_count ?? 0}
          icon={<Clock className="w-5 h-5 text-amber-400" />}
          iconBg="bg-amber-500/10"
          href="/timeout"
          highlight={(stats?.timeout_due_count ?? 0) > 0}
        />
      </div>

      {/* Recent evaluations */}
      <Card
        title="Recent Evaluations"
        subtitle="Latest prescription reviews"
        action={
          <Link href="/audit">
            <Button variant="ghost" size="sm" rightIcon={<ArrowUpRight className="w-4 h-4" />}>
              View audit log
            </Button>
          </Link>
        }
        noPadding
      >
        <div className="divide-y divide-[#2d3148]">
          {(stats?.recent_evaluations ?? []).map((ev) => (
            <div key={ev.evaluation_id} className="px-6 py-4 hover:bg-[#2d3148]/30 transition-colors">
              <div className="flex items-center gap-4">
                {/* Status icon */}
                <div className="shrink-0">{STATUS_ICON[ev.status]}</div>

                {/* Patient */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-100 font-mono">
                      {ev.patient_id}
                    </span>
                    <Badge variant={ev.status} size="sm">
                      {ev.status}
                    </Badge>
                    {ev.high_count > 0 && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                        {ev.high_count} HIGH
                      </span>
                    )}
                    {ev.moderate_count > 0 && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        {ev.moderate_count} MOD
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">{ev.evaluation_id}</p>
                </div>

                {/* Time */}
                <div className="shrink-0 text-right">
                  <p className="text-xs text-slate-400">
                    {new Date(ev.evaluated_at).toLocaleDateString('en-IN', {
                      day: '2-digit',
                      month: 'short',
                    })}
                  </p>
                  <p className="text-xs text-slate-500">
                    {new Date(ev.evaluated_at).toLocaleTimeString('en-IN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>

                {/* View link */}
                <Link href={`/evaluation/${ev.episode_id}`}>
                  <Button variant="outline" size="sm">
                    View
                  </Button>
                </Link>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link href="/upload">
          <div className="p-5 rounded-xl border border-indigo-500/30 bg-indigo-500/5 hover:bg-indigo-500/10 transition-all cursor-pointer group">
            <ClipboardList className="w-6 h-6 text-indigo-400 mb-3" />
            <p className="text-sm font-semibold text-slate-100">New Prescription</p>
            <p className="text-xs text-slate-400 mt-1">Upload &amp; evaluate a new prescription</p>
          </div>
        </Link>
        <Link href="/timeout">
          <div className="p-5 rounded-xl border border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 transition-all cursor-pointer group">
            <Clock className="w-6 h-6 text-amber-400 mb-3" />
            <p className="text-sm font-semibold text-slate-100">48-Hour Reviews</p>
            <p className="text-xs text-slate-400 mt-1">
              {stats?.timeout_due_count ?? 0} prescriptions due for review
            </p>
          </div>
        </Link>
        <Link href="/culture">
          <div className="p-5 rounded-xl border border-[#2d3148] bg-[#1e2235] hover:border-[#3b4263] transition-all cursor-pointer group">
            <Activity className="w-6 h-6 text-emerald-400 mb-3" />
            <p className="text-sm font-semibold text-slate-100">Culture & Resistance</p>
            <p className="text-xs text-slate-400 mt-1">View organism susceptibility reports</p>
          </div>
        </Link>
      </div>
    </div>
  )
}
