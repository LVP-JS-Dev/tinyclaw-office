"use client";

import { useEffect, useState } from "react";

type MemoryModality = "conversation" | "document" | "image" | "video" | "audio";
type RetrievalMethod = "rag" | "llm" | "hybrid";

interface Memory {
  memory_id: string;
  resource_url: string;
  modality: MemoryModality;
  user: string;
  agent?: string;
  content: string | Record<string, unknown>;
  summary?: string;
  categories: string[];
  status: string;
  created_at: string;
  updated_at: string;
  relevance_score?: number;
}

interface MemoryRetrieveResponse {
  results: Array<{
    memory: Memory;
    score: number;
    highlights?: string[];
  }>;
  total: number;
  method: RetrievalMethod;
  query_time_ms?: number;
}

interface MemoryViewProps {
  agentId?: string;
  initialMemories?: Memory[];
  loading?: boolean;
}

function getModalityIcon(modality: MemoryModality): string {
  switch (modality) {
    case "conversation":
      return "💬";
    case "document":
      return "📄";
    case "image":
      return "🖼️";
    case "video":
      return "🎥";
    case "audio":
      return "🎵";
    default:
      return "📝";
  }
}

function getModalityColor(modality: MemoryModality): string {
  switch (modality) {
    case "conversation":
      return "bg-blue-50 text-blue-700 ring-blue-600/20";
    case "document":
      return "bg-gray-50 text-gray-700 ring-gray-600/20";
    case "image":
      return "bg-purple-50 text-purple-700 ring-purple-600/20";
    case "video":
      return "bg-red-50 text-red-700 ring-red-600/20";
    case "audio":
      return "bg-green-50 text-green-700 ring-green-600/20";
    default:
      return "bg-slate-50 text-slate-700 ring-slate-600/20";
  }
}

function formatContent(content: string | Record<string, unknown>): string {
  if (typeof content === "string") {
    return content.length > 200 ? content.substring(0, 200) + "..." : content;
  }
  try {
    const str = JSON.stringify(content, null, 2);
    return str.length > 200 ? str.substring(0, 200) + "..." : str;
  } catch {
    return "[Complex content]";
  }
}

function MemoryCard({ memory, score }: { memory: Memory; score?: number }) {
  return (
    <div className="card hover:shadow-md transition-shadow">
      <div className="card-header">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xl" role="img" aria-label={memory.modality}>
                {getModalityIcon(memory.modality)}
              </span>
              <span
                className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${getModalityColor(
                  memory.modality
                )}`}
              >
                {memory.modality}
              </span>
              {score !== undefined && (
                <span className="inline-flex items-center rounded-md bg-accent-50 px-2 py-1 text-xs font-medium text-accent-700 ring-1 ring-inset ring-accent-600/20">
                  {Math.round(score * 100)}% match
                </span>
              )}
            </div>
            {memory.summary && (
              <h3 className="card-title">{memory.summary}</h3>
            )}
          </div>
        </div>
      </div>
      <div className="card-content">
        <div className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
              Content
            </p>
            <p className="text-sm text-foreground bg-muted-50 rounded-md p-3 font-mono text-xs overflow-x-auto">
              {formatContent(memory.content)}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Memory ID
              </p>
              <p className="text-sm font-mono font-medium truncate" title={memory.memory_id}>
                {memory.memory_id.slice(0, 8)}...
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                User
              </p>
              <p className="text-sm font-medium">{memory.user}</p>
            </div>
          </div>
          {memory.agent && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                  Agent
                </p>
                <p className="text-sm font-medium">{memory.agent}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                  Status
                </p>
                <p className="text-sm font-medium capitalize">{memory.status}</p>
              </div>
            </div>
          )}
          {memory.categories && memory.categories.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">
                Categories
              </p>
              <div className="flex flex-wrap gap-2">
                {memory.categories.map((category) => (
                  <span
                    key={category}
                    className="inline-flex items-center rounded-md bg-primary-50 px-2 py-1 text-xs font-medium text-primary-700 ring-1 ring-inset ring-primary-600/20"
                  >
                    {category}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Created
              </p>
              <p className="text-xs text-muted-foreground">
                {new Date(memory.created_at).toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                Updated
              </p>
              <p className="text-xs text-muted-foreground">
                {new Date(memory.updated_at).toLocaleString()}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MemoryView({
  agentId,
  initialMemories,
  loading: initialLoading = false,
}: MemoryViewProps) {
  const [memories, setMemories] = useState<Memory[]>(initialMemories || []);
  const [loading, setLoading] = useState(initialLoading);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMethod, setSearchMethod] = useState<RetrievalMethod>("rag");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<Array<{ memory: Memory; score: number }>>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);

  useEffect(() => {
    if (initialMemories !== undefined) {
      return;
    }

    async function fetchMemories() {
      try {
        setLoading(true);
        setError(null);

        const url = agentId
          ? `http://localhost:8080/api/memory/${agentId}?limit=50`
          : null;

        if (!url) {
          setMemories([]);
          return;
        }

        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          setMemories(data.memories || []);
        } else if (response.status === 404) {
          setMemories([]);
        } else {
          throw new Error("Failed to fetch memories");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }

    fetchMemories();
  }, [agentId, initialMemories]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();

    if (!searchQuery.trim()) {
      setShowSearchResults(false);
      return;
    }

    try {
      setIsSearching(true);
      setError(null);

      const response = await fetch("http://localhost:8080/api/memory/retrieve", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          queries: [searchQuery],
          method: searchMethod,
          limit: 20,
          where: agentId ? { agent: agentId } : {},
        }),
      });

      if (response.ok) {
        const data: MemoryRetrieveResponse = await response.json();
        setSearchResults(data.results || []);
        setShowSearchResults(true);
      } else {
        throw new Error("Failed to search memories");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setShowSearchResults(false);
    } finally {
      setIsSearching(false);
    }
  }

  function clearSearch() {
    setSearchQuery("");
    setShowSearchResults(false);
    setSearchResults([]);
  }

  const displayMemories = showSearchResults
    ? searchResults.map((r) => r.memory)
    : memories;
  const displayResults = showSearchResults ? searchResults : undefined;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
          <p className="text-sm text-muted-foreground">Loading memories...</p>
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
            <h3 className="font-semibold text-destructive-900">Error Loading Memories</h3>
            <p className="text-sm text-destructive-700 mt-1">{error}</p>
            <p className="text-xs text-destructive-600 mt-2">
              Make sure the orchestration service is running on port 8080
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleSearch} className="card">
        <div className="card-header">
          <h3 className="card-title">Search Memories</h3>
          <p className="card-description">
            Use semantic search to find relevant memories
          </p>
        </div>
        <div className="card-content">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Enter search query..."
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isSearching}
              />
            </div>
            <div className="flex gap-2">
              <select
                value={searchMethod}
                onChange={(e) => setSearchMethod(e.target.value as RetrievalMethod)}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                disabled={isSearching}
              >
                <option value="rag">RAG (Fast)</option>
                <option value="llm">LLM (Deep)</option>
                <option value="hybrid">Hybrid</option>
              </select>
              <button
                type="submit"
                disabled={isSearching || !searchQuery.trim()}
                className="inline-flex items-center justify-center rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isSearching ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent mr-2" />
                    Searching...
                  </>
                ) : (
                  <>
                    <svg
                      className="h-4 w-4 mr-2"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2}
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                      />
                    </svg>
                    Search
                  </>
                )}
              </button>
              {showSearchResults && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent-50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </div>
      </form>

      {displayMemories.length === 0 ? (
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
                d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold">No Memories Found</h3>
          <p className="text-sm text-muted-foreground mt-2">
            {showSearchResults
              ? "No memories match your search query. Try a different search term."
              : agentId
                ? `No memories found for agent ${agentId}.`
                : "Select an agent to view their memories, or use the search above."}
          </p>
        </div>
      ) : (
        <>
          {showSearchResults && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Found {displayMemories.length} memories using {searchMethod.toUpperCase()} search
              </p>
            </div>
          )}
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {displayResults ? (
              displayResults.map((result) => (
                <MemoryCard
                  key={result.memory.memory_id}
                  memory={result.memory}
                  score={result.score}
                />
              ))
            ) : (
              displayMemories.map((memory) => (
                <MemoryCard key={memory.memory_id} memory={memory} />
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
