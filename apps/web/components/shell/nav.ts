import {
  Activity,
  Boxes,
  CalendarClock,
  FileText,
  Gauge,
  Inbox,
  type LucideIcon,
  Plug,
  ScrollText,
  Settings,
  Sparkles,
  Workflow,
  Wrench,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  keywords?: string;
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Operate",
    items: [
      { href: "/", label: "Dashboard", icon: Gauge, keywords: "home overview" },
      { href: "/approvals", label: "Approvals", icon: Inbox, keywords: "review hitl desk" },
      { href: "/executions", label: "Executions", icon: Activity, keywords: "runs history" },
      { href: "/schedules", label: "Schedules", icon: CalendarClock, keywords: "cron timer" },
    ],
  },
  {
    group: "Build",
    items: [
      { href: "/pipelines", label: "Pipelines", icon: Workflow, keywords: "graph builder dag" },
      { href: "/prompts", label: "Prompts", icon: FileText, keywords: "templates variables studio" },
    ],
  },
  {
    group: "Connect",
    items: [
      { href: "/models", label: "Models", icon: Sparkles, keywords: "llm providers openai anthropic ollama" },
      { href: "/mcp-servers", label: "MCP servers", icon: Plug, keywords: "servers connections stdio http" },
      { href: "/tools", label: "Tools", icon: Wrench, keywords: "mcp tools policy approval" },
    ],
  },
  {
    group: "Govern",
    items: [
      { href: "/audit", label: "Audit log", icon: ScrollText, keywords: "history events" },
      { href: "/settings", label: "Settings", icon: Settings, keywords: "members secrets channels workspace" },
    ],
  },
];

export const ALL_NAV = NAV.flatMap((g) => g.items);
export const BRAND_ICON = Boxes;
