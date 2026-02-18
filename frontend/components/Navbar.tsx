'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navbar() {
  const pathname = usePathname();

  const navLinks = [
    { href: '/', label: 'Task Board' },
    { href: '/tasks/new', label: 'New Task' },
    { href: '/workspaces', label: 'Workspaces' },
    { href: '/runners', label: 'Runners' },
    { href: '/quota', label: 'Quota' },
    { href: '/usage', label: 'Usage' },
  ];

  return (
    <nav className="border-b bg-background">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <div className="text-2xl font-bold text-primary">
              AI Task Manager
            </div>
          </Link>

          {/* Navigation Links */}
          <div className="flex gap-6">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`text-sm font-medium transition-colors hover:text-primary ${
                    isActive
                      ? 'text-foreground'
                      : 'text-muted-foreground'
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
