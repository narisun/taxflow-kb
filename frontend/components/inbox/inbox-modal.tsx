"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface EmailDraft {
  id: string;
  to: string;
  subject: string;
  body: string;
  clientName: string;
  createdAt: string;
}

interface InboxModalProps {
  open: boolean;
  onClose: () => void;
  drafts: EmailDraft[];
  onDeleteDraft: (id: string) => void;
}

export function InboxModal({ open, onClose, drafts, onDeleteDraft }: InboxModalProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { toast } = useToast();

  const selectedDraft = selectedId ? drafts.find((d) => d.id === selectedId) : null;

  /** Strip markdown to plain text for mailto body */
  const mdToPlain = (md: string): string =>
    md
      .replace(/^#{1,6}\s+/gm, "")           // headings
      .replace(/\*\*(.+?)\*\*/g, "$1")         // bold
      .replace(/\*(.+?)\*/g, "$1")             // italic
      .replace(/`(.+?)`/g, "$1")               // inline code
      .replace(/^\s*[-*]\s+/gm, "• ")          // bullets
      .replace(/^\s*\d+\.\s+/gm, (m) => m)     // numbered lists (keep)
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // links
      .replace(/\n{3,}/g, "\n\n")              // collapse blank lines
      .trim();

  /** Convert markdown to HTML string for rich clipboard */
  const mdToHtml = (md: string): string => {
    const lines = md.split("\n");
    let html = "";
    for (const line of lines) {
      let l = line
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/`(.+?)`/g, "<code>$1</code>")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
      if (/^#{1,6}\s+/.test(l)) {
        const level = l.match(/^(#+)/)?.[1].length || 2;
        l = `<h${level}>${l.replace(/^#+\s+/, "")}</h${level}>`;
      } else if (/^\s*[-*]\s+/.test(l)) {
        l = `<li>${l.replace(/^\s*[-*]\s+/, "")}</li>`;
      } else if (l.trim() === "") {
        l = "<br>";
      } else {
        l = `<p>${l}</p>`;
      }
      html += l;
    }
    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>)+/g, (m) => `<ul>${m}</ul>`);
    return html;
  };

  const handleCopyPlain = (draft: EmailDraft) => {
    const text = mdToPlain(draft.body);
    navigator.clipboard.writeText(text);
    toast("success", "Copied as plain text");
  };

  const handleCopyHtml = async (draft: EmailDraft) => {
    const html = mdToHtml(draft.body);
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([mdToPlain(draft.body)], { type: "text/plain" }),
        }),
      ]);
      toast("success", "Copied as rich text — paste into any email editor");
    } catch {
      // Fallback: copy plain text
      navigator.clipboard.writeText(mdToPlain(draft.body));
      toast("success", "Copied to clipboard");
    }
  };

  const handleMailto = (draft: EmailDraft) => {
    const plain = mdToPlain(draft.body);
    const mailto = `mailto:${encodeURIComponent(draft.to)}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(plain)}`;
    window.open(mailto, "_blank");
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl w-[88vw]">
      <ModalHeader onClose={onClose}>Drafts</ModalHeader>
      <ModalBody className="p-0">
        <div className="flex min-h-[400px] max-h-[65vh]">
          {/* Draft list */}
          <div className="w-64 shrink-0 border-r border-divider overflow-y-auto">
            {drafts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-tertiary px-4">
                <svg className="w-6 h-6 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-[12px]">No drafts yet</span>
                <span className="text-[10px] mt-1 text-center">Use &quot;Draft email&quot; or &quot;Draft advisory&quot; in the chat to create one</span>
              </div>
            ) : (
              drafts.map((draft) => (
                <div
                  key={draft.id}
                  onClick={() => setSelectedId(draft.id)}
                  className={cn(
                    "px-3 py-2.5 border-b border-divider cursor-pointer transition-colors",
                    selectedId === draft.id ? "bg-apple-blue/10" : "hover:bg-surface-secondary"
                  )}
                >
                  <div className="text-[12px] font-medium text-primary truncate">{draft.clientName}</div>
                  <div className="text-[11px] text-primary truncate mt-0.5">{draft.subject}</div>
                  <div className="text-[10px] text-tertiary truncate mt-0.5">{draft.body.slice(0, 60)}...</div>
                </div>
              ))
            )}
          </div>

          {/* Reading pane */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            {selectedDraft ? (
              <div className="p-4 flex-1 flex flex-col">
                {/* Header */}
                <div className="border-b border-divider pb-3 mb-3">
                  <div className="text-[14px] font-semibold text-primary mb-1">{selectedDraft.subject}</div>
                  <div className="text-[11px] space-y-0.5">
                    <div><span className="text-tertiary">To: </span><span className="text-primary">{selectedDraft.to}</span></div>
                    <div><span className="text-tertiary">Client: </span><span className="text-primary">{selectedDraft.clientName}</span></div>
                  </div>
                </div>
                {/* Body — rendered as HTML from markdown */}
                <div className="text-[13px] text-primary leading-relaxed flex-1 prose-chat">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedDraft.body}</ReactMarkdown>
                </div>
                {/* Actions */}
                <div className="flex gap-2 mt-4 pt-3 border-t border-divider">
                  <button
                    onClick={() => handleCopyHtml(selectedDraft)}
                    className="text-[11px] text-secondary hover:text-primary px-3 py-1.5 rounded-md border border-divider hover:bg-surface-secondary transition-colors cursor-pointer flex items-center gap-1.5"
                    title="Copy as rich text — paste into Gmail, Outlook, etc."
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Copy
                  </button>
                  <button
                    onClick={() => handleCopyPlain(selectedDraft)}
                    className="text-[11px] text-tertiary hover:text-primary px-3 py-1.5 rounded-md border border-divider hover:bg-surface-secondary transition-colors cursor-pointer"
                    title="Copy as plain text"
                  >
                    Plain
                  </button>
                  <button
                    onClick={() => handleMailto(selectedDraft)}
                    className="text-[11px] text-white bg-apple-blue px-3 py-1.5 rounded-md hover:brightness-110 transition-all cursor-pointer flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Open in Email
                  </button>
                  <button
                    onClick={() => { onDeleteDraft(selectedDraft.id); setSelectedId(null); }}
                    className="text-[11px] text-tertiary hover:text-red-500 px-3 py-1.5 rounded-md border border-divider hover:bg-surface-secondary transition-colors cursor-pointer ml-auto"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-tertiary">
                <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
                  <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-[12px]">Select a draft to preview</span>
              </div>
            )}
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
