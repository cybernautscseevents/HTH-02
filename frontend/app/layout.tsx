import type { Metadata } from 'next'
import './globals.css'

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
    <html lang="en">
      <body className="min-h-screen bg-[#FAFAF8] font-sans text-[#1A1A1A] antialiased">
        {children}
      </body>
    </html>
  )
}
