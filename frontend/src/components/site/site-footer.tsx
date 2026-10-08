import Link from "next/link";

import { Logo } from "@/components/brand/logo";

const COLUMNS = [
  { title: "Product", links: [["Features", "/features"], ["Pricing", "/pricing"], ["FAQ", "/faq"], ["How it works", "/#how-it-works"]] },
  { title: "Company", links: [["Contact", "/contact"], ["Help center", "/help"]] },
  { title: "Legal", links: [["Privacy policy", "/privacy"], ["Terms of service", "/terms"], ["Cookies & data", "/cookies"]] },
] as const;

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-bg-subtle">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-4">
        <div className="space-y-3">
          <Logo />
          <p className="text-sm text-muted">Turn long videos into scroll-stopping shorts.</p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <h3 className="text-sm font-semibold text-fg">{col.title}</h3>
            <ul className="mt-3 space-y-2 text-sm text-muted">
              {col.links.map(([label, href]) => (
                <li key={href}>
                  <Link href={href} className="hover:text-fg">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border py-5 text-center text-xs text-muted">
        © Virello Studio. All rights reserved.
      </div>
    </footer>
  );
}
