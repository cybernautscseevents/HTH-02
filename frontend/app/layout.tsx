import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const sans = Inter({ subsets: ['latin'], variable: '--font-sans', display: 'swap' })
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' })

export const metadata: Metadata = {
  title: 'RxGuard — Antibiotic Stewardship Copilot',
  description: 'Clinical decision support for antibiotic stewardship. Evidence-based recommendations for pharmacists and clinicians.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-[#FAFAF8] font-sans text-[#1A1A1A] antialiased">
        {children}
      </body>
    </html>
  )
}
