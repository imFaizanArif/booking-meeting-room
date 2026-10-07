import { useQuery } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

export type Server = Schemas["MCPServerOut"];
export type Tool = Schemas["MCPToolOut"];
export type Transport = Schemas["TransportType"];
export type RiskLevel = Schemas["RiskLevel"];

/** Every key starts with "mcp": the workspace stream invalidates ["mcp"] on mcp.server_status_changed. */
export const mcpKeys = {
  all: ["mcp"] as const,
  servers: ["mcp", "servers"] as const,
  server: (id: string) => ["mcp", "servers", id] as const,
  tools: ["mcp", "tools"] as const,
};

export function useServers() {
  return useQuery({
    queryKey: mcpKeys.servers,
    queryFn: async () => unwrap(await api.GET("/api/v1/mcp/servers")),
  });
}

export function useServer(id: string | null | undefined) {
  return useQuery({
    queryKey: mcpKeys.server(id ?? ""),
    queryFn: async () => unwrap(await api.GET("/api/v1/mcp/servers/{server_id}", { params: { path: { server_id: id! } } })),
    enabled: !!id,
  });
}

export function useTools() {
  return useQuery({
    queryKey: mcpKeys.tools,
    queryFn: async () => unwrap(await api.GET("/api/v1/mcp/tools", { params: { query: { include_stale: true } } })),
  });
}

export const TRANSPORTS: { value: Transport; label: string; description: string }[] = [
  { value: "stdio", label: "stdio", description: "Runs a local command on the worker host" },
  { value: "streamable_http", label: "Streamable HTTP", description: "Remote server over HTTP (recommended)" },
  { value: "sse_legacy", label: "SSE (legacy)", description: "Older HTTP + server-sent events transport" },
];

export function transportLabel(t: Transport): string {
  return TRANSPORTS.find((x) => x.value === t)?.label ?? t;
}

export const RISK_LEVELS: { value: RiskLevel; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

/** Quote one argv element for display so the command line reads exactly as it will run. */
export function shellQuote(arg: string): string {
  if (arg === "") return "''";
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, `'\\''`)}'`;
}

export function commandLine(command: string, args: string[]): string {
  return [command, ...args].map(shellQuote).join(" ");
}
