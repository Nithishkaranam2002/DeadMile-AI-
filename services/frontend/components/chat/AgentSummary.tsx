"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { parseDriverSummary, stripMarkdownTables } from "@/lib/agent-response";
import { Button } from "@/components/ui/button";

interface AgentSummaryProps {
  content: string;
}

export function AgentSummary({ content }: AgentSummaryProps) {
  const [expanded, setExpanded] = useState(false);
  const summary = parseDriverSummary(content);
  const fullText = stripMarkdownTables(content);

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div>
          <p className="font-medium leading-snug">{summary.headline}</p>
          {summary.topLoadId && (
            <p className="mt-1 text-xs text-text-secondary">
              Full rankings, profit breakdown, and map routes are in the panel on the right →
            </p>
          )}
        </div>
      </div>

      {summary.insight && (
        <p className="rounded-md border border-border/60 bg-background/50 px-3 py-2 text-xs leading-relaxed text-text-secondary">
          {summary.insight}
        </p>
      )}

      {summary.bullets.length > 0 && (
        <ul className="space-y-1 text-xs text-text-secondary">
          {summary.bullets.slice(0, 3).map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-primary">•</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}

      {fullText.length > 120 && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs text-text-secondary"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <>
              Hide details <ChevronUp className="ml-1 h-3 w-3" />
            </>
          ) : (
            <>
              Show full analysis <ChevronDown className="ml-1 h-3 w-3" />
            </>
          )}
        </Button>
      )}

      {expanded && (
        <div className="max-h-64 overflow-y-auto rounded-md border border-border/60 bg-background/40 p-3 text-xs leading-relaxed text-text-secondary whitespace-pre-wrap">
          {fullText}
        </div>
      )}
    </div>
  );
}
