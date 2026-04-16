"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";

export interface DependentDetail {
  firstName: string;
  lastName: string;
  ssn: string;
  dob: string;
  relationship: string;
}

export interface IntakeFormData {
  firstName: string;
  lastName: string;
  ssn: string;
  dateOfBirth: string;
  spouseFirstName: string;
  spouseLastName: string;
  spouseSsn: string;
  spouseDob: string;
  filingStatus: string;
  taxYear: number;
  street: string;
  city: string;
  state: string;
  zip: string;
  filingFederal: boolean;
  filingStates: string[];
  dependents: number;
  dependentDetails: DependentDetail[];
  familyGroupName: string;
  notes: string;
}

interface UploadedDoc {
  name: string;
  formType: string;
  status: "uploading" | "done" | "error";
}

interface IntakeModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: IntakeFormData, files: File[]) => void;
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

const RELATIONSHIPS = [
  { value: "", label: "Select..." },
  { value: "son", label: "Son" },
  { value: "daughter", label: "Daughter" },
  { value: "stepchild", label: "Stepchild" },
  { value: "foster", label: "Foster child" },
  { value: "sibling", label: "Sibling" },
  { value: "parent", label: "Parent" },
  { value: "other", label: "Other" },
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

function detectFormType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("w2") || f.includes("w-2")) return "W-2";
  if (f.includes("1099")) return "1099";
  if (f.includes("1098")) return "1098";
  if (f.includes("k-1") || f.includes("k1")) return "K-1";
  if (f.includes("1040")) return "Prior 1040";
  return "Other";
}

export function IntakeModal({ open, onClose, onSubmit, editData, mode = "create" }: IntakeModalProps) {
  const [form, setForm] = useState<IntakeFormData>({ ...defaultForm });
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    if (editData && mode === "edit") {
      const sanitized = Object.fromEntries(
        Object.entries(editData).map(([k, v]) => [k, v ?? ""])
      );
      setForm({ ...defaultForm, ...sanitized });
    } else {
      setForm({ ...defaultForm });
      setPendingFiles([]);
      setUploadedDocs([]);
    }
  }, [editData, mode, open]);

  const set = (field: keyof IntakeFormData, value: string | number | boolean | string[]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const v = (field: keyof IntakeFormData): string => String(form[field] ?? "");

  const handleDependentsChange = (count: number) => {
    const c = Math.max(0, Math.min(20, count));
    const current = form.dependentDetails;
    const newDetails = Array.from({ length: c }, (_, i) =>
      current[i] || { firstName: "", lastName: "", ssn: "", dob: "", relationship: "" }
    );
    setForm((prev) => ({ ...prev, dependents: c, dependentDetails: newDetails }));
  };

  const updateDependent = (idx: number, field: keyof DependentDetail, value: string) => {
    setForm((prev) => {
      const deps = [...prev.dependentDetails];
      deps[idx] = { ...deps[idx], [field]: value };
      return { ...prev, dependentDetails: deps };
    });
  };

  const toggleState = (code: string) => {
    setForm((prev) => ({
      ...prev,
      filingStates: prev.filingStates.includes(code)
        ? prev.filingStates.filter((s) => s !== code)
        : [...prev.filingStates, code],
    }));
  };

  const handleAddFiles = useCallback((files: File[]) => {
    const valid = files.filter(f => f.type === "application/pdf" || f.type.startsWith("image/"));
    setPendingFiles(prev => [...prev, ...valid]);
    setUploadedDocs(prev => [
      ...prev,
      ...valid.map(f => ({ name: f.name, formType: detectFormType(f.name), status: "done" as const })),
    ]);
  }, []);

  const handleRemoveFile = (idx: number) => {
    setPendingFiles(prev => prev.filter((_, i) => i !== idx));
    setUploadedDocs(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = () => {
    onSubmit(form, pendingFiles);
    setForm({ ...defaultForm });
    setPendingFiles([]);
    setUploadedDocs([]);
    onClose();
  };

  const isJoint = form.filingStatus === "mfj" || form.filingStatus === "mfs";
  const isEdit = mode === "edit";

  const inputCls = "w-full border border-divider rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[10px] font-medium text-tertiary uppercase tracking-wider mb-0.5 block";
  const sectionCls = "text-[11px] font-semibold text-primary pb-1 mb-2 border-b border-divider";

  return (
    <Modal open={open} onClose={onClose} className="max-w-6xl w-[92vw]">
      <ModalHeader onClose={onClose}>
        <div>
          <div className="text-[15px] font-semibold">{isEdit ? "Edit Client" : "New Client Intake"}</div>
          <div className="text-[11px] text-tertiary mt-0.5">
            {isEdit ? "Update taxpayer details" : "Enter taxpayer details and upload documents"}
          </div>
        </div>
      </ModalHeader>

      <ModalBody className="h-[75vh] p-0 overflow-hidden">
        <div className="grid grid-cols-[1fr_340px] max-md:grid-cols-1 h-full">
          {/* Left: Intake form — scrollable */}
          <div className="overflow-y-auto px-5 py-4 border-r border-divider space-y-4">

            {/* Primary Taxpayer */}
            <div>
              <div className={sectionCls}>Primary Taxpayer</div>
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <label className={labelCls}>First Name</label>
                  <input className={inputCls} value={v("firstName")} onChange={(e) => set("firstName", e.target.value)} placeholder="John" />
                </div>
                <div>
                  <label className={labelCls}>Last Name</label>
                  <input className={inputCls} value={v("lastName")} onChange={(e) => set("lastName", e.target.value)} placeholder="Smith" />
                </div>
                <div>
                  <label className={labelCls}>SSN</label>
                  <input className={inputCls} value={v("ssn")} onChange={(e) => set("ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
                </div>
                <div>
                  <label className={labelCls}>Date of Birth</label>
                  <input type="date" className={inputCls} value={v("dateOfBirth")} onChange={(e) => set("dateOfBirth", e.target.value)} />
                </div>
              </div>
            </div>

            {/* Filing + Group */}
            <div>
              <div className={sectionCls}>Filing Information</div>
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <label className={labelCls}>Filing Status</label>
                  <select className={inputCls} value={form.filingStatus} onChange={(e) => set("filingStatus", e.target.value)}>
                    {FILING_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Tax Year</label>
                  <select className={inputCls} value={form.taxYear} onChange={(e) => set("taxYear", Number(e.target.value))}>
                    <option value={2025}>2025</option><option value={2024}>2024</option><option value={2023}>2023</option>
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Dependents</label>
                  <input type="number" min={0} max={20} className={inputCls} value={form.dependents} onChange={(e) => handleDependentsChange(Number(e.target.value))} />
                </div>
                <div>
                  <label className={labelCls}>Family Group</label>
                  <input className={inputCls} value={v("familyGroupName")} onChange={(e) => set("familyGroupName", e.target.value)} placeholder="Smith Family" />
                </div>
              </div>
            </div>

            {/* Spouse — only for MFJ/MFS */}
            {isJoint && (
              <div>
                <div className={sectionCls}>Spouse</div>
                <div className="grid grid-cols-4 gap-2">
                  <div>
                    <label className={labelCls}>First Name</label>
                    <input className={inputCls} value={v("spouseFirstName")} onChange={(e) => set("spouseFirstName", e.target.value)} placeholder="Jane" />
                  </div>
                  <div>
                    <label className={labelCls}>Last Name</label>
                    <input className={inputCls} value={v("spouseLastName")} onChange={(e) => set("spouseLastName", e.target.value)} placeholder="Smith" />
                  </div>
                  <div>
                    <label className={labelCls}>SSN</label>
                    <input className={inputCls} value={v("spouseSsn")} onChange={(e) => set("spouseSsn", e.target.value)} placeholder="XXX-XX-XXXX" />
                  </div>
                  <div>
                    <label className={labelCls}>Date of Birth</label>
                    <input type="date" className={inputCls} value={v("spouseDob")} onChange={(e) => set("spouseDob", e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            {/* Dependents — dynamic sections */}
            {form.dependentDetails.map((dep, idx) => (
              <div key={idx}>
                <div className={sectionCls}>Dependent {idx + 1}</div>
                <div className="grid grid-cols-5 gap-2">
                  <div>
                    <label className={labelCls}>First Name</label>
                    <input className={inputCls} value={dep.firstName || ""} onChange={(e) => updateDependent(idx, "firstName", e.target.value)} />
                  </div>
                  <div>
                    <label className={labelCls}>Last Name</label>
                    <input className={inputCls} value={dep.lastName || ""} onChange={(e) => updateDependent(idx, "lastName", e.target.value)} />
                  </div>
                  <div>
                    <label className={labelCls}>SSN</label>
                    <input className={inputCls} value={dep.ssn || ""} onChange={(e) => updateDependent(idx, "ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
                  </div>
                  <div>
                    <label className={labelCls}>DOB</label>
                    <input type="date" className={inputCls} value={dep.dob || ""} onChange={(e) => updateDependent(idx, "dob", e.target.value)} />
                  </div>
                  <div>
                    <label className={labelCls}>Relationship</label>
                    <select className={inputCls} value={dep.relationship || ""} onChange={(e) => updateDependent(idx, "relationship", e.target.value)}>
                      {RELATIONSHIPS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            ))}

            {/* Address */}
            <div>
              <div className={sectionCls}>Address</div>
              <div className="grid grid-cols-4 gap-2">
                <div className="col-span-2">
                  <label className={labelCls}>Street</label>
                  <input className={inputCls} value={v("street")} onChange={(e) => set("street", e.target.value)} placeholder="42 Oak Street" />
                </div>
                <div>
                  <label className={labelCls}>City</label>
                  <input className={inputCls} value={v("city")} onChange={(e) => set("city", e.target.value)} placeholder="Princeton" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelCls}>State</label>
                    <select className={inputCls} value={v("state")} onChange={(e) => set("state", e.target.value)}>
                      <option value="">--</option>
                      {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>ZIP</label>
                    <input className={inputCls} value={v("zip")} onChange={(e) => set("zip", e.target.value)} placeholder="08540" />
                  </div>
                </div>
              </div>
            </div>

            {/* Filing Needs */}
            <div>
              <div className={sectionCls}>Filing Needs</div>
              <div className="flex items-center gap-2 mb-2">
                <input type="checkbox" id="fed" checked={form.filingFederal} onChange={(e) => set("filingFederal", e.target.checked)}
                  className="w-3.5 h-3.5 accent-apple-blue cursor-pointer" />
                <label htmlFor="fed" className="text-[12px] text-primary cursor-pointer">Federal Return</label>
              </div>
              <label className={labelCls}>State Returns</label>
              <div className="flex flex-wrap gap-1 mt-0.5">
                {STATES.map((s) => (
                  <button key={s} onClick={() => toggleState(s)}
                    className={`text-[9px] px-1.5 py-0.5 rounded border cursor-pointer transition-all ${
                      form.filingStates.includes(s)
                        ? "bg-apple-blue text-white border-apple-blue"
                        : "bg-surface text-tertiary border-divider hover:border-tertiary"
                    }`}>{s}</button>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div>
              <div className={sectionCls}>Notes</div>
              <textarea className={`${inputCls} min-h-[40px] resize-none`} value={v("notes")}
                onChange={(e) => set("notes", e.target.value)} placeholder="Special circumstances, prior year issues..." />
            </div>
          </div>

          {/* Right: Document upload panel */}
          <div className="flex flex-col h-full overflow-hidden">
            <div className="px-4 py-3 border-b border-divider shrink-0">
              <div className="text-[12px] font-semibold text-primary">Documents</div>
              <div className="text-[10px] text-tertiary mt-0.5">
                Upload W-2s, 1099s, prior year 1040, or any supporting documents
              </div>
            </div>

            {/* Uploaded files list */}
            {uploadedDocs.length > 0 && (
              <div className="px-4 py-2 overflow-y-auto border-b border-divider">
                <div className="space-y-1.5">
                  {uploadedDocs.map((doc, i) => (
                    <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface-secondary/50 border border-divider group">
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] font-medium text-primary truncate">{doc.name}</div>
                        <div className="text-[10px] text-tertiary">{doc.formType}</div>
                      </div>
                      <Badge variant={doc.status === "done" ? "completed" : "pending"} className="text-[9px] shrink-0">
                        {doc.status === "done" ? "Ready" : "Uploading"}
                      </Badge>
                      <button onClick={() => handleRemoveFile(i)}
                        className="w-5 h-5 rounded flex items-center justify-center text-tertiary hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all cursor-pointer shrink-0"
                        title="Remove">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Drop zone */}
            <div className="flex-1 p-4 flex items-center justify-center">
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                onDrop={(e) => { e.preventDefault(); setIsDragging(false); handleAddFiles(Array.from(e.dataTransfer.files)); }}
                onClick={() => fileInputRef.current?.click()}
                className={`w-full h-full border-2 border-dashed rounded-xl flex flex-col items-center justify-center cursor-pointer transition-all ${
                  isDragging ? "border-apple-blue bg-apple-blue/5" : "border-divider hover:border-apple-blue/40 hover:bg-surface-secondary/20"
                }`}
              >
                <input ref={fileInputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.tiff"
                  onChange={(e) => { handleAddFiles(Array.from(e.target.files || [])); e.target.value = ""; }}
                  className="hidden" />
                <div className="text-[20px] mb-2">{"\u{1F4C4}"}</div>
                <div className="text-[12px] text-secondary font-medium">Drop files here</div>
                <div className="text-[10px] text-tertiary mt-0.5">or click to browse</div>
                <div className="flex flex-wrap justify-center gap-1 mt-3 px-4">
                  {["W-2", "1099", "1098", "K-1", "Prior 1040"].map((t) => (
                    <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full bg-surface-secondary text-tertiary border border-divider">{t}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </ModalBody>

      {/* Footer */}
      <div className="px-5 py-2.5 border-t border-divider flex items-center justify-between shrink-0 bg-surface-secondary/50">
        <div className="text-[11px] text-tertiary">
          {pendingFiles.length > 0 && `${pendingFiles.length} document${pendingFiles.length > 1 ? "s" : ""} attached`}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg border border-divider text-[12px] text-secondary hover:bg-surface-tertiary transition-colors cursor-pointer">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={!form.firstName || !form.lastName}
            className="px-4 py-1.5 rounded-lg bg-apple-blue text-white text-[12px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-40">
            {isEdit ? "Save Changes" : "Create Client"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
