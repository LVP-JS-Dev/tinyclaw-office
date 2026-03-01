"use client";

import { useEffect, useState } from "react";

type ServiceStatus = "healthy" | "degraded" | "unhealthy" | "unknown";

interface ServiceHealth {
  service: string;
  status: ServiceStatus;
  url: string;
  description: string;
  metrics?: {
    label: string;
    value: string | number;
  }[];
}

interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: {
    tinyclaw?: ServiceStatus;
    memu?: ServiceStatus;
    gondolin?: ServiceStatus;
    orchestration?: ServiceStatus;
  };
  timestamp: string;
}

const SERVICE_DEFINITIONS: Omit<ServiceHealth, "status">[] = [
  {
    service: "TinyClaw",
    url: "/agents",
    description: "Multi-agent coordination and messaging routing",
    metrics: [
      { label: "Port", value: "3777" },
      { label: "Protocol", value: "HTTP" },
    ],
  },
  {
    service: "MemU",
    url: "/memory",
    description: "Persistent memory storage and retrieval",
    metrics: [
      { label: "Port", value: "8000" },
      { label: "Storage", value: "PostgreSQL" },
    ],
  },
  {
    service: "Gondolin",
    url: "/execute",
    description: "Sandboxed code execution in QEMU VMs",
    metrics: [
      { label: "Port", value: "9000" },
      { label: "Platform", value: "ARM64" },
    ],
  },
  {
    service: "Orchestration",
    url: "/api/health",
    description: "Unified API coordinating all services",
    metrics: [
      { label: "Port", value: "8080" },
      { label: "Protocol", value: "REST" },
    ],
  },
];

function getStatusColor(status: ServiceStatus): string {
  switch (status) {
    case "healthy":
      return "bg-status-healthy";
    case "degraded":
      return "bg-status-degraded";
    case "unhealthy":
      return "bg-status-unhealthy";
    default:
      return "bg-status-unknown";
  }
}

function getStatusText(status: ServiceStatus): string {
  switch (status) {
    case "healthy":
      return "Operational";
    case "degraded":
      return "Degraded";
    case "unhealthy":
      return "Offline";
    default:
      return "Unknown";
  }
}

function ServiceCard({ health }: { health: ServiceHealth }) {
  return (
    <div className="card hover:shadow-md transition-shadow">
      <div className="card-header">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="card-title">{health.service}</h3>
            <p className="card-description mt-1">{health.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`status-dot ${getStatusColor(health.status)} ${
                health.status === "healthy" ? "animate-pulse-slow" : ""
              }`}
              aria-label={`Status: ${health.status}`}
            />
            <span className="text-sm font-medium">{getStatusText(health.status)}</span>
          </div>
        </div>
      </div>
      <div className="card-content">
        {health.metrics && (
          <div className="grid grid-cols-2 gap-4">
            {health.metrics.map((metric, index) => (
              <div key={index} className="space-y-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  {metric.label}
                </p>
                <p className="text-sm font-mono font-medium">{metric.value}</p>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="card-footer">
        <a
          href={health.url}
          className="text-sm text-primary-600 hover:text-primary-700 font-medium"
        >
          View Details →
        </a>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [lastChecked, setLastChecked] = useState<string>("");
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_ORCHESTRATION_URL || "http://localhost:8080"}/health`);
        if (response.ok) {
          const data: HealthResponse = await response.json();
          const servicesWithHealth = SERVICE_DEFINITIONS.map((def) => ({
            ...def,
            status:
              data.services[
                def.service.toLowerCase() as keyof HealthResponse["services"]
              ] || "unknown",
          }));
          setServices(servicesWithHealth);
          setLastChecked(new Date(data.timestamp).toLocaleTimeString());
        } else {
          throw new Error("Health check failed");
        }
      } catch {
        setIsError(true);
        const servicesUnknown = SERVICE_DEFINITIONS.map((def) => ({
          ...def,
          status: "unknown" as ServiceStatus,
        }));
        setServices(servicesUnknown);
      }
    }

    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const overallStatus =
    services.length > 0 && services.every((s) => s.status === "healthy")
      ? "healthy"
      : services.some((s) => s.status === "unhealthy")
        ? "unhealthy"
        : services.some((s) => s.status === "degraded")
          ? "degraded"
          : "unknown";

  return (
    <div className="container py-8">
      <div className="mb-8">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground mt-2">
          Monitor and manage your AI platform services
        </p>
        {lastChecked && (
          <p className="text-xs text-muted-foreground mt-4">
            Last checked: {lastChecked}
            {isError && " (using cached data - API unreachable)"}
          </p>
        )}
      </div>

      <div className="mb-8">
        <div className="flex items-center gap-3 rounded-lg border bg-white p-4 shadow-sm">
          <div className={`status-dot ${getStatusColor(overallStatus)} ${
            overallStatus === "healthy" ? "animate-pulse-slow" : ""
          }`} />
          <div>
            <p className="font-semibold">System Status</p>
            <p className="text-sm text-muted-foreground">
              {overallStatus === "healthy" && "All systems operational"}
              {overallStatus === "degraded" && "Some services experiencing issues"}
              {overallStatus === "unhealthy" && "Critical services offline"}
              {overallStatus === "unknown" && "Unable to determine system status"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4">
        {services.map((service) => (
          <ServiceCard key={service.service} health={service} />
        ))}
      </div>

      <div className="mt-12 grid gap-6 md:grid-cols-2">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Quick Actions</h3>
            <p className="card-description">Common management tasks</p>
          </div>
          <div className="card-content">
            <div className="space-y-2">
              <a
                href="/agents"
                className="block rounded-md border p-3 hover:bg-accent-50 transition-colors"
              >
                <p className="font-medium">Manage Agents</p>
                <p className="text-sm text-muted-foreground">
                  Create and configure AI agents
                </p>
              </a>
              <a
                href="/memory"
                className="block rounded-md border p-3 hover:bg-accent-50 transition-colors"
              >
                <p className="font-medium">Browse Memory</p>
                <p className="text-sm text-muted-foreground">
                  Search and manage agent memories
                </p>
              </a>
              <a
                href="/execute"
                className="block rounded-md border p-3 hover:bg-accent-50 transition-colors"
              >
                <p className="font-medium">Execute Code</p>
                <p className="text-sm text-muted-foreground">
                  Run code in sandboxed environment
                </p>
              </a>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Platform Information</h3>
            <p className="card-description">Version and configuration details</p>
          </div>
          <div className="card-content">
            <div className="space-y-3">
              <div className="flex justify-between border-b pb-2">
                <span className="text-sm text-muted-foreground">TinyClaw</span>
                <span className="text-sm font-medium">Multi-Agent System</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-sm text-muted-foreground">MemU</span>
                <span className="text-sm font-medium">Persistent Memory</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-sm text-muted-foreground">Gondolin</span>
                <span className="text-sm font-medium">Sandboxed Execution</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Dashboard</span>
                <span className="text-sm font-medium">v0.1.0</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
