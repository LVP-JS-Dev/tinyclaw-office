import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TinyClaw Office - Unified AI Platform Dashboard",
  description: "Manage TinyClaw agents, MemU memory, and Gondolin sandboxed execution",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.className}>
      <body className="min-h-screen bg-slate-50 antialiased">
        <div className="flex min-h-screen flex-col">
          <header className="sticky top-0 z-50 w-full border-b bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80">
            <div className="container flex h-16 items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary-500 to-accent-500" />
                <h1 className="text-xl font-bold">TinyClaw Office</h1>
              </div>
              <nav className="flex items-center gap-6">
                <a href="/" className="text-sm font-medium text-foreground hover:text-primary-600">
                  Dashboard
                </a>
                <a href="/agents" className="text-sm font-medium text-muted-foreground hover:text-primary-600">
                  Agents
                </a>
                <a href="/memory" className="text-sm font-medium text-muted-foreground hover:text-primary-600">
                  Memory
                </a>
                <a href="/execute" className="text-sm font-medium text-muted-foreground hover:text-primary-600">
                  Execute
                </a>
              </nav>
            </div>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="border-t bg-white">
            <div className="container flex h-14 items-center justify-between text-sm">
              <p className="text-muted-foreground">
                © {new Date().getFullYear()} TinyClaw Office. MIT License.
              </p>
              <p className="text-muted-foreground">
                Integration of TinyClaw, MemU, and Gondolin
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
