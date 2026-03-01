"use client";

import { useEffect, useState } from "react";

type AgentStatus = "active" | "idle" | "error" | "unknown";

interface Agent {
  id: string;
  name: string;
  status: AgentStatus;
  type: string;
  channels: string[];
  description?: string;
  lastActivity?: string;
}

interface AgentListProps {
  agents?: Agent[];
  loading?: boolean;
}

function getStatusColor(status: AgentStatus): string {
  switch (status) {
    case "active":
      return "bg-status-healthy";
    case "idle":
      return "bg-status-degraded";
    case "error":
      return "bg-status-unhealthy";
    default:
      return "bg-status-unknown";
  }
}

function getStatusText(status: AgentStatus): string {
  switch (status) {
    case "active":
      return "Active";
    case "idle":
      return "Idle";
    case "error":
      return "Error";
    default:
      return "Unknown";
  }
}

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <div className="card hover:shadow-md transition-shadow">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h3 className="card-title">{agent.name}</h3>
              <div className="flex items-center gap-2">
                <span
                  className={`status-dot ${getStatusColor(agent.status)} ${
                    agent.status === "active" ? "animate-pulse-slow" : ""
                  }`}
                  aria-label={`Status: ${agent.status}`}
                />
                <span className="text-sm font-medium">{getStatusText(agent.status)}</span>
              </div>
            </div>
            {agent.description && (
              <p className="card-description mt-2">{agent.description}</p>
            )}
          </div>
        </div>
      </div>
      <div className="card-content">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Agent ID
              </p>
              <p className="text-sm font-mono font-medium">{agent.id}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Type
              </p>
              <p className="text-sm font-medium">{agent.type}</p>
            </div>
          </div>
          {agent.channels && agent.channels.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">
                Channels
              </p>
              <div className="flex flex-wrap gap-2">
                {agent.channels.map((channel) => (
                  <span
                    key={channel}
                    className="inline-flex items-center rounded-md bg-accent-50 px-2 py-1 text-xs font-medium text-accent-700 ring-1 ring-inset ring-accent-600/20"
                  >
                    {channel}
                  </span>
                ))}
              </div>
            </div>
          )}
          {agent.lastActivity && (
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Last Activity
              </p>
              <p className="text-sm text-muted-foreground">{agent.lastActivity}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentList({ agents: initialAgents, loading: initialLoading = false }: AgentListProps) {
  const [agents, setAgents] = useState<Agent[]>(initialAgents || []);
  const [loading, setLoading] = useState(initialLoading);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // If agents are provided as props, don't fetch
    if (initialAgents !== undefined) {
      return;
    }

    async function fetchAgents() {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch("http://localhost:8080/api/agents");
        if (response.ok) {
          const data = await response.json();
          setAgents(data.agents || []);
        } else {
          throw new Error("Failed to fetch agents");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }

    fetchAgents();
  }, [initialAgents]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
          <p className="text-sm text-muted-foreground">Loading agents...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive-200 bg-destructive-50 p-6">
        <div className="flex items-start gap-3">
          <div className="h-5 w-5 rounded-full bg-destructive-200 flex items-center justify-center flex-shrink-0">
            <span className="text-destructive-700 text-xs">!</span>
          </div>
          <div>
            <h3 className="font-semibold text-destructive-900">Error Loading Agents</h3>
            <p className="text-sm text-destructive-700 mt-1">{error}</p>
            <p className="text-xs text-destructive-600 mt-2">
              Make sure the orchestration service is running on port 8080
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-muted-foreground/25 p-12 text-center">
        <div className="mx-auto h-12 w-12 rounded-full bg-muted-50 flex items-center justify-center mb-4">
          <svg
            className="h-6 w-6 text-muted-foreground"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
            />
          </svg>
        </div>
        <h3 className="text-lg font-semibold">No Agents Found</h3>
        <p className="text-sm text-muted-foreground mt-2">
          Get started by creating your first agent or connecting to TinyClaw.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
