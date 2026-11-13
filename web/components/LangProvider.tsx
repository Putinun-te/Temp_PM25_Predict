"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { type Lang, LANGS, pickLang, type StringKey, translate } from "@/lib/i18n";

const STORAGE_KEY = "pm25-lang";

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: StringKey) => string;
}

const LangContext = createContext<LangState>({
  lang: "en",
  setLang: () => undefined,
  t: (key) => translate("en", key),
});

function readSaved(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(pickLang(window.location.search, readSaved(), navigator.language));
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private windows may block storage; the choice then lasts for this page only.
    }
  }, []);

  const t = useCallback((key: StringKey) => translate(lang, key), [lang]);
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export function useLang(): LangState {
  return useContext(LangContext);
}

export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="lang" role="group" aria-label="Language">
      {LANGS.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={lang === option}
          className={lang === option ? "active" : ""}
          onClick={() => setLang(option)}
        >
          {option === "th" ? "ไทย" : "EN"}
        </button>
      ))}
    </div>
  );
}
