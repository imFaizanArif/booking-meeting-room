import { create } from "zustand";

export type Theme = "light" | "dark" | "system";

interface UIState {
  theme: Theme;
  paletteOpen: boolean;
  setTheme: (theme: Theme) => void;
  setPaletteOpen: (open: boolean) => void;
}

function apply(theme: Theme): void {
  if (typeof document === "undefined") return;
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

/** Only genuinely global client state lives here: theme and the command palette. */
export const useUI = create<UIState>((set) => ({
  theme: "system",
  paletteOpen: false,
  setTheme: (theme) => {
    try {
      localStorage.setItem("ap-theme", theme);
    } catch {
      /* storage unavailable */
    }
    apply(theme);
    set({ theme });
  },
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
}));

export const themeBootScript = `(function(){try{var t=localStorage.getItem('ap-theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=d?'dark':'light';}catch(e){}})();`;
