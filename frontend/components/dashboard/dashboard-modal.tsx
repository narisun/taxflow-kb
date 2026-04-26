"use client";

import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { AnalyticsDashboard } from "./analytics-dashboard";
import type { Client } from "@/lib/api-client";

interface DashboardModalProps {
  open: boolean;
  onClose: () => void;
  clients: Client[];
}

export function DashboardModal({ open, onClose, clients }: DashboardModalProps) {
  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <ModalHeader onClose={onClose}>Dashboard</ModalHeader>
      <ModalBody className="p-0">
        <AnalyticsDashboard clients={clients} />
      </ModalBody>
    </Modal>
  );
}
