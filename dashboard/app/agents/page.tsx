import AgentList from "@/components/AgentList";

export const metadata = {
  title: "Agents - TinyClaw Office",
  description: "Manage and monitor your AI agents",
};

export default function AgentsPage() {
  return (
    <div className="container py-8">
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Agents</h2>
            <p className="text-muted-foreground mt-2">
              View and manage all active AI agents in your system
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
          >
            <svg
              className="h-4 w-4 mr-2"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Create Agent
          </button>
        </div>
      </div>

      <div className="space-y-6">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">All Agents</h3>
            <p className="card-description">
              Monitor agent status, channels, and activity
            </p>
          </div>
          <div className="card-content">
            <AgentList />
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Agent Statistics</h3>
              <p className="card-description">Overview of agent activity</p>
            </div>
            <div className="card-content">
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Total Agents</span>
                  <span className="text-sm font-medium">-</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Active Now</span>
                  <span className="text-sm font-medium">-</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Channels</span>
                  <span className="text-sm font-medium">Discord, WhatsApp, Telegram</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Integration</span>
                  <span className="text-sm font-medium">TinyClaw</span>
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Quick Actions</h3>
              <p className="card-description">Common agent management tasks</p>
            </div>
            <div className="card-content">
              <div className="space-y-2">
                <button
                  type="button"
                  className="w-full rounded-md border p-3 text-left hover:bg-accent-50 transition-colors"
                >
                  <p className="font-medium">Create New Agent</p>
                  <p className="text-sm text-muted-foreground">
                    Set up a new AI agent with custom configuration
                  </p>
                </button>
                <button
                  type="button"
                  className="w-full rounded-md border p-3 text-left hover:bg-accent-50 transition-colors"
                >
                  <p className="font-medium">Configure Channels</p>
                  <p className="text-sm text-muted-foreground">
                    Manage messaging channels for agents
                  </p>
                </button>
                <button
                  type="button"
                  className="w-full rounded-md border p-3 text-left hover:bg-accent-50 transition-colors"
                >
                  <p className="font-medium">View Agent Logs</p>
                  <p className="text-sm text-muted-foreground">
                    Access detailed activity logs
                  </p>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
