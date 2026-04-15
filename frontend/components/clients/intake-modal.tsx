"use client";

import { useState, useEffect } from "react";
import { Modal } from "@/components/ui/modal";

export interface DependentDetail {
  firstName: string;
  lastName: string;
  ssn: string;
  dob: string;
  relationship: string;
}

export interface IntakeFormData {
  // Primary taxpayer
  firstName: string;
  lastName: string;
  ssn: string;
  dateOfBirth: string;
  // Spouse
  spouseFirstName: string;
  spouseLastName: string;
  spouseSsn: string;
  spouseDob: string;
  // Filing info
  filingStatus: string;
  taxYear: number;
  // Address
  street: string;
  city: string;
  state: string;
  zip: string;
  // Filing needs
  filingFederal: boolean;
  filingStates: string[];
  // Dependents
  dependents: number;
  dependentDetails: DependentDetail[];
  // Other
  familyGroupName: string;
  notes: string;
}

interface IntakeModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: IntakeFormData) => void;
  editData?: Partial<IntakeFormData> & { id?: number };
  mode?: "create" | "edit";
}

const STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY","DC",
];

const FILING_STATUSES = [
  { value: "single", label: "Single" },
  { value: "mfj", label: "Married Filing Jointly" },
  { value: "mfs", label: "Married Filing Separately" },
  { value: "hoh", label: "Head of Household" },
  { value: "qw", label: "Qualifying Surviving Spouse" },
];

const defaultForm: IntakeFormData = {
  firstName: "", lastName: "", ssn: "", dateOfBirth: "",
  spouseFirstName: "", spouseLastName: "", spouseSsn: "", spouseDob: "",
  filingStatus: "single", taxYear: 2025,
  street: "", city: "", state: "", zip: "",
  filingFederal: true, filingStates: [],
  dependents: 0, dependentDetails: [],
  familyGroupName: "", notes: "",
};

export function IntakeModal({ open, onClose, onSubmit, editData, mode = "create" }: IntakeModalProps) {
  const [form, setForm] = useState<IntakeFormData>({ ...defaultForm });

  // Initialize form from editData when in edit mode, or reset for create
  useEffect(() => {
    if (editData && mode === "edit") {
      setForm({ ...defaultForm, ...editData });
    } else {
      setForm({ ...defaultForm });
    }
  }, [editData, mode, open]);

  const set = (field: keyof IntakeFormData, value: string | number | boolean | string[]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const toggleState = (code: string) => {
    setForm((prev) => ({
      ...prev,
      filingStates: prev.filingStates.includes(code)
        ? prev.filingStates.filter((s) => s !== code)
        : [...prev.filingStates, code],
    }));
  };

  const handleDependentsChange = (count: number) => {
    const clamped = Math.max(0, Math.min(count, 20));
    const current = form.dependentDetails;
    const newDetails = Array.from({ length: clamped }, (_, i) =>
      current[i] || { firstName: "", lastName: "", ssn: "", dob: "", relationship: "" }
    );
    setForm((prev) => ({ ...prev, dependents: clamped, dependentDetails: newDetails }));
  };

  const updateDependent = (index: number, field: keyof DependentDetail, value: string) => {
    setForm((prev) => {
      const updated = [...prev.dependentDetails];
      updated[index] = { ...updated[index], [field]: value };
      return { ...prev, dependentDetails: updated };
    });
  };

  const handleSubmit = () => {
    onSubmit(form);
    setForm({ ...defaultForm });
    onClose();
  };

  const isJoint = form.filingStatus === "mfj" || form.filingStatus === "mfs";
  const isEdit = mode === "edit";

  const inputCls = "w-full border border-divider rounded-lg px-3 py-2 text-[13px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[11px] font-medium text-tertiary uppercase tracking-wider mb-1 block";
  const sectionCls = "text-[12px] font-semibold text-primary pb-1.5 mb-3 border-b border-divider";

  return (
    <Modal open={open} onClose={onClose}>
      <div className="w-[92vw] max-w-6xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-divider flex items-center justify-between shrink-0">
          <div>
            <div className="text-[16px] font-semibold text-primary">
              {isEdit ? "Edit Client" : "New Client Intake"}
            </div>
            <div className="text-[12px] text-tertiary mt-0.5">
              {isEdit ? "Update taxpayer details" : "Enter taxpayer details to start a new return"}
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg border border-divider flex items-center justify-center text-tertiary hover:text-primary hover:bg-surface-secondary transition-colors cursor-pointer text-[16px]">
            &times;
          </button>
        </div>

        {/* Form body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

          {/* Primary taxpayer */}
          <div>
            <div className={sectionCls}>Primary Taxpayer</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>First Name</label>
                <input className={inputCls} value={form.firstName} onChange={(e) => set("firstName", e.target.value)} placeholder="John" />
              </div>
              <div>
                <label className={labelCls}>Last Name</label>
                <input className={inputCls} value={form.lastName} onChange={(e) => set("lastName", e.target.value)} placeholder="Smith" />
              </div>
              <div>
                <label className={labelCls}>SSN</label>
                <input className={inputCls} value={form.ssn} onChange={(e) => set("ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
              </div>
              <div>
                <label className={labelCls}>Date of Birth</label>
                <input type="date" className={inputCls} value={form.dateOfBirth} onChange={(e) => set("dateOfBirth", e.target.value)} />
              </div>
            </div>
          </div>

          {/* Filing Information */}
          <div>
            <div className={sectionCls}>Filing Information</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Filing Status</label>
                <select className={inputCls} value={form.filingStatus} onChange={(e) => set("filingStatus", e.target.value)}>
                  {FILING_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>Tax Year</label>
                <select className={inputCls} value={form.taxYear} onChange={(e) => set("taxYear", Number(e.target.value))}>
                  <option value={2025}>2025</option>
                  <option value={2024}>2024</option>
                  <option value={2023}>2023</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Dependents</label>
                <input type="number" min={0} max={20} className={inputCls} value={form.dependents} onChange={(e) => handleDependentsChange(Number(e.target.value))} />
              </div>
              <div>
                <label className={labelCls}>Family Group Name</label>
                <input className={inputCls} value={form.familyGroupName} onChange={(e) => set("familyGroupName", e.target.value)} placeholder="e.g. Smith Family" />
              </div>
            </div>
          </div>

          {/* Spouse -- shown for MFJ/MFS */}
          {isJoint && (
            <div>
              <div className={sectionCls}>Spouse</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>First Name</label>
                  <input className={inputCls} value={form.spouseFirstName} onChange={(e) => set("spouseFirstName", e.target.value)} placeholder="Jane" />
                </div>
                <div>
                  <label className={labelCls}>Last Name</label>
                  <input className={inputCls} value={form.spouseLastName} onChange={(e) => set("spouseLastName", e.target.value)} placeholder="Smith" />
                </div>
                <div>
                  <label className={labelCls}>SSN</label>
                  <input className={inputCls} value={form.spouseSsn} onChange={(e) => set("spouseSsn", e.target.value)} placeholder="XXX-XX-XXXX" />
                </div>
                <div>
                  <label className={labelCls}>Date of Birth</label>
                  <input type="date" className={inputCls} value={form.spouseDob} onChange={(e) => set("spouseDob", e.target.value)} />
                </div>
              </div>
            </div>
          )}

          {/* Dependent details */}
          {form.dependentDetails.map((dep, idx) => (
            <div key={idx}>
              <div className={sectionCls}>Dependent {idx + 1}</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>First Name</label>
                  <input className={inputCls} value={dep.firstName} onChange={(e) => updateDependent(idx, "firstName", e.target.value)} />
                </div>
                <div>
                  <label className={labelCls}>Last Name</label>
                  <input className={inputCls} value={dep.lastName} onChange={(e) => updateDependent(idx, "lastName", e.target.value)} />
                </div>
                <div>
                  <label className={labelCls}>SSN</label>
                  <input className={inputCls} value={dep.ssn} onChange={(e) => updateDependent(idx, "ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
                </div>
                <div>
                  <label className={labelCls}>Date of Birth</label>
                  <input type="date" className={inputCls} value={dep.dob} onChange={(e) => updateDependent(idx, "dob", e.target.value)} />
                </div>
                <div>
                  <label className={labelCls}>Relationship</label>
                  <select className={inputCls} value={dep.relationship} onChange={(e) => updateDependent(idx, "relationship", e.target.value)}>
                    <option value="">Select...</option>
                    <option value="son">Son</option>
                    <option value="daughter">Daughter</option>
                    <option value="stepchild">Stepchild</option>
                    <option value="foster">Foster child</option>
                    <option value="sibling">Sibling</option>
                    <option value="parent">Parent</option>
                    <option value="other">Other</option>
                  </select>
                </div>
              </div>
            </div>
          ))}

          {/* Address */}
          <div>
            <div className={sectionCls}>Address</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className={labelCls}>Street</label>
                <input className={inputCls} value={form.street} onChange={(e) => set("street", e.target.value)} placeholder="42 Oak Street" />
              </div>
              <div>
                <label className={labelCls}>City</label>
                <input className={inputCls} value={form.city} onChange={(e) => set("city", e.target.value)} placeholder="Princeton" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>State</label>
                  <select className={inputCls} value={form.state} onChange={(e) => set("state", e.target.value)}>
                    <option value="">--</option>
                    {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>ZIP</label>
                  <input className={inputCls} value={form.zip} onChange={(e) => set("zip", e.target.value)} placeholder="08540" />
                </div>
              </div>
            </div>
          </div>

          {/* Filing needs */}
          <div>
            <div className={sectionCls}>Filing Needs</div>
            <div className="flex items-center gap-2 mb-3">
              <input type="checkbox" id="fed" checked={form.filingFederal} onChange={(e) => set("filingFederal", e.target.checked)}
                className="w-4 h-4 accent-apple-blue cursor-pointer" />
              <label htmlFor="fed" className="text-[13px] text-primary cursor-pointer">Federal Return</label>
            </div>
            <label className={labelCls}>State Returns (select all that apply)</label>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {STATES.map((s) => (
                <button
                  key={s}
                  onClick={() => toggleState(s)}
                  className={`text-[10px] px-2 py-1 rounded-md border cursor-pointer transition-all ${
                    form.filingStates.includes(s)
                      ? "bg-apple-blue text-white border-apple-blue"
                      : "bg-surface text-secondary border-divider hover:border-tertiary"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div>
            <div className={sectionCls}>Notes</div>
            <textarea
              className={`${inputCls} min-h-[60px] resize-none`}
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Special circumstances, prior year issues, etc."
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-divider flex items-center justify-end gap-2 shrink-0 bg-surface-secondary">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-divider text-[13px] text-secondary hover:bg-surface-tertiary transition-colors cursor-pointer">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!form.firstName || !form.lastName}
            className="px-4 py-2 rounded-lg bg-apple-blue text-white text-[13px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-40"
          >
            {isEdit ? "Save Changes" : "Create Client"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
