"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LangToggle, useLang } from "./LangProvider";

export default function Header() {
  const { t } = useLang();
  const path = usePathname();
  const onAccuracy = path.startsWith("/accuracy");
  const onHow = path.startsWith("/how");
  return (
    <header className="top">
      <nav aria-label="Pages">
        <Link href="/" aria-current={onAccuracy || onHow ? undefined : "page"}>
          {t("navForecast")}
        </Link>
        <Link href="/accuracy/" aria-current={onAccuracy ? "page" : undefined}>
          {t("navAccuracy")}
        </Link>
        <Link href="/how/" aria-current={onHow ? "page" : undefined}>
          {t("navHow")}
        </Link>
      </nav>
      <LangToggle />
    </header>
  );
}
