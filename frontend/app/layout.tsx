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
    <html lang="en" className="dark">
      <body className="bg-[#0f1117] text-slate-100 font-sans antialiased min-h-screen">
        {children}
      </body>
    </html>
  )
}
