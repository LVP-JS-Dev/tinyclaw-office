import MemoryView from "@/components/MemoryView";

export const metadata = {
  title: "Memory - TinyClaw Office",
  description: "Browse and search AI agent memories",
};

export default function MemoryPage() {
  return (
    <div className="container py-8">
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Memory</h2>
            <p className="text-muted-foreground mt-2">
              Browse and search persistent memories stored by AI agents
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">All Memories</h3>
            <p className="card-description">
              Search and explore agent memories using semantic search
            </p>
          </div>
          <div className="card-content">
            <MemoryView />
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Memory Statistics</h3>
              <p className="card-description">Overview of memory storage</p>
            </div>
            <div className="card-content">
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Storage Mode</span>
                  <span className="text-sm font-medium">PostgreSQL + pgvector</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Retrieval Methods</span>
                  <span className="text-sm font-medium">RAG, LLM, Hybrid</span>
                </div>
                <div className="flex items-center justify-between border-b pb-3">
                  <span className="text-sm text-muted-foreground">Modalities</span>
                  <span className="text-sm font-medium">Conversation, Document, Media</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Integration</span>
                  <span className="text-sm font-medium">MemU</span>
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Search Tips</h3>
              <p className="card-description">How to effectively search memories</p>
            </div>
            <div className="card-content">
              <div className="space-y-3">
                <div className="rounded-md border p-3">
                  <p className="font-medium text-sm">RAG (Fast)</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Quick vector-based search for real-time queries
                  </p>
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium text-sm">LLM (Deep)</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Semantic understanding for complex reasoning tasks
                  </p>
                </div>
                <div className="rounded-md border p-3">
                  <p className="font-medium text-sm">Hybrid</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Combines fast retrieval with deep semantic analysis
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
