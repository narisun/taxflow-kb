"use client";

import { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { cn } from "@/lib/utils";
import { mockInboxMessages } from "@/lib/mock-data";

interface InboxModalProps {
  open: boolean;
  onClose: () => void;
}

type Folder = "inbox" | "drafts" | "sent";

interface Message {
  id: number;
  folder: Folder;
  from: string;
  to: string;
  subject: string;
  preview: string;
  body: string;
  date: string;
  read: boolean;
  type: "email" | "text";
}

const folders: { id: Folder; label: string; icon: string }[] = [
  { id: "inbox", label: "Inbox", icon: "\u{1F4E5}" },
  { id: "drafts", label: "Drafts", icon: "\u{1F4DD}" },
  { id: "sent", label: "Sent", icon: "\u{1F4E4}" },
];

export function InboxModal({ open, onClose }: InboxModalProps) {
  const [activeFolder, setActiveFolder] = useState<Folder>("inbox");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>(mockInboxMessages);

  const folderMessages = messages.filter((m) => m.folder === activeFolder);
  const selectedMessage = selectedId ? messages.find((m) => m.id === selectedId) : null;

  const unreadCount = (folder: Folder) => messages.filter((m) => m.folder === folder && !m.read).length;

  const handleSelect = (id: number) => {
    setSelectedId(id);
    setMessages((prev) => prev.map((m) => m.id === id ? { ...m, read: true } : m));
  };

  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <ModalHeader onClose={onClose}>Inbox</ModalHeader>
      <ModalBody className="p-0 max-h-[70vh]">
        <div className="flex min-h-[450px]">
          {/* Folder nav */}
          <nav className="w-36 shrink-0 border-r border-divider py-2">
            {folders.map((f) => {
              const count = unreadCount(f.id);
              return (
                <button
                  key={f.id}
                  onClick={() => { setActiveFolder(f.id); setSelectedId(null); }}
                  className={cn(
                    "w-full text-left px-3 py-2 text-[13px] flex items-center justify-between transition-colors cursor-pointer",
                    activeFolder === f.id ? "text-apple-blue bg-apple-blue/10 font-medium" : "text-secondary hover:bg-surface-secondary"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-[14px]">{f.icon}</span>
                    {f.label}
                  </span>
                  {count > 0 && (
                    <span className="text-[10px] font-bold bg-apple-blue text-white w-5 h-5 rounded-full flex items-center justify-center">
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Message list */}
          <div className="w-56 shrink-0 border-r border-divider overflow-y-auto scroll-visible">
            {folderMessages.length === 0 ? (
              <div className="flex items-center justify-center h-full text-tertiary text-[12px]">
                No messages
              </div>
            ) : (
              folderMessages.map((msg) => (
                <div
                  key={msg.id}
                  onClick={() => handleSelect(msg.id)}
                  className={cn(
                    "px-3 py-2.5 border-b border-divider cursor-pointer transition-colors",
                    selectedId === msg.id ? "bg-apple-blue/10" : "hover:bg-surface-secondary",
                    !msg.read && "bg-surface-secondary"
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    {!msg.read && <span className="w-1.5 h-1.5 rounded-full bg-apple-blue shrink-0" />}
                    <span className={cn("text-[12px] truncate", !msg.read ? "font-semibold text-primary" : "text-primary")}>
                      {activeFolder === "sent" || activeFolder === "drafts" ? msg.to : msg.from}
                    </span>
                    {msg.type === "text" && (
                      <span className="text-[9px] px-1 py-px rounded bg-surface-tertiary text-tertiary shrink-0">SMS</span>
                    )}
                  </div>
                  {msg.subject && (
                    <div className="text-[11px] text-primary truncate mt-0.5">{msg.subject}</div>
                  )}
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-[10px] text-tertiary truncate flex-1">{msg.preview}</span>
                    <span className="text-[10px] text-tertiary shrink-0 ml-2">{msg.date}</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Reading pane */}
          <div className="flex-1 overflow-y-auto scroll-visible">
            {selectedMessage ? (
              <div className="p-4">
                {/* Message header */}
                <div className="border-b border-divider pb-3 mb-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[14px] font-semibold text-primary">
                      {selectedMessage.subject || (selectedMessage.type === "text" ? "Text Message" : "No Subject")}
                    </span>
                    {selectedMessage.type === "text" && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-tertiary text-secondary">SMS</span>
                    )}
                  </div>
                  <div className="text-[11px] space-y-0.5">
                    <div><span className="text-tertiary">From: </span><span className="text-primary">{selectedMessage.from}</span></div>
                    <div><span className="text-tertiary">To: </span><span className="text-primary">{selectedMessage.to}</span></div>
                    <div><span className="text-tertiary">Date: </span><span className="text-primary">{selectedMessage.date}, 2026</span></div>
                  </div>
                </div>
                {/* Message body */}
                <div className="text-[13px] text-primary leading-relaxed whitespace-pre-wrap">
                  {selectedMessage.body}
                </div>
                {/* Reply/Forward actions */}
                <div className="flex gap-2 mt-4 pt-3 border-t border-divider">
                  <button className="text-[11px] text-secondary hover:text-primary px-3 py-1.5 rounded-md border border-divider hover:bg-surface-secondary transition-colors cursor-pointer">
                    Reply
                  </button>
                  <button className="text-[11px] text-secondary hover:text-primary px-3 py-1.5 rounded-md border border-divider hover:bg-surface-secondary transition-colors cursor-pointer">
                    Forward
                  </button>
                  {selectedMessage.folder === "drafts" && (
                    <button className="text-[11px] text-white bg-apple-blue px-3 py-1.5 rounded-md hover:brightness-110 transition-all cursor-pointer">
                      Send
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-tertiary">
                <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
                  <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-[12px]">Select a message to read</span>
              </div>
            )}
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
