"use client";

import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { AnalyticsDashboard } from "./analytics-dashboard";

interface DashboardModalProps {
  open: boolean;
  onClose: () => void;
}

export function DashboardModal({ open, onClose }: DashboardModalProps) {
  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <ModalHeader onClose={onClose}>Dashboard</ModalHeader>
      <ModalBody className="p-0 max-h-[75vh]">
        <AnalyticsDashboard />
      </ModalBody>
    </Modal>
  );
}
