"use client";

import { useState, useEffect, useMemo } from "react";
import { Modal, ModalHeader, ModalBody } from "@/components/ui/modal";
import { PiiInput } from "@/components/clients/pii-input";

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
  email: string;
  phone: string;
  spouseFirstName: string;
  spouseLastName: string;
  spouseSsn: string;
  spouseDob: string;
  spouseEmail: string;
  spousePhone: string;
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

interface IntakeModalProps {
  open: boolean;
  onClose: () => void;
  /** Called when the user clicks Create/Save. Resolve to throw on failure;
   *  the modal stays open and shows the error inline so the user can retry. */
  onSubmit: (data: IntakeFormData) => Promise<void>;
  /** Edit-mode seed data. The ``*Masked`` strings are the API's mask snippets
   *  for the encrypted PII columns; we surface them so the form can render
   *  them as placeholders (and the eye-icon reveal flow knows there's
   *  something to fetch). */
  editData?: Partial<IntakeFormData> & {
    id?: string;
    ssnMasked?: string;
    dobMasked?: string;
    spouseSsnMasked?: string;
    spouseDobMasked?: string;
    streetMasked?: string;
  };
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
  email: "", phone: "",
  spouseFirstName: "", spouseLastName: "", spouseSsn: "", spouseDob: "",
  spouseEmail: "", spousePhone: "",
  filingStatus: "single", taxYear: 2025,
  street: "", city: "", state: "", zip: "",
  filingFederal: true, filingStates: [],
  dependents: 0, dependentDetails: [],
  familyGroupName: "", notes: "",
};

// ── Field-size limits, mirroring the backend Pydantic schema/DB columns ──
const LIMITS = {
  name: 100,
  ssn: 11,            // XXX-XX-XXXX
  email: 254,
  phone: 20,
  street: 200,
  city: 100,
  zip: 10,
  familyGroup: 200,
  notes: 2000,
} as const;

// ── Client-side validation ─────────────────────────────────────────────────

const _ssnRe = /^\d{3}-?\d{2}-?\d{4}$/;
const _emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const _phoneRe = /^[\d \-()+]{7,20}$/;
const _zipRe = /^\d{5}(-\d{4})?$/;

function validate(form: IntakeFormData): Record<string, string> {
  const errs: Record<string, string> = {};
  if (!form.firstName.trim()) errs.firstName = "First name is required";
  if (!form.lastName.trim()) errs.lastName = "Last name is required";
  if (form.ssn && !_ssnRe.test(form.ssn.trim()))
    errs.ssn = "Use 9 digits — dashes optional";
  if (form.email && !_emailRe.test(form.email.trim()))
    errs.email = "Enter a valid email address";
  if (form.phone && !_phoneRe.test(form.phone.trim()))
    errs.phone = "Use digits, spaces, dashes, parens, leading +";

  const isJoint = form.filingStatus === "mfj" || form.filingStatus === "mfs";
  if (isJoint) {
    if (!form.spouseFirstName.trim()) errs.spouseFirstName = "Required for joint filing";
    if (!form.spouseLastName.trim()) errs.spouseLastName = "Required for joint filing";
    if (form.spouseSsn && !_ssnRe.test(form.spouseSsn.trim()))
      errs.spouseSsn = "Use 9 digits — dashes optional";
    if (form.spouseEmail && !_emailRe.test(form.spouseEmail.trim()))
      errs.spouseEmail = "Enter a valid email address";
    if (form.spousePhone && !_phoneRe.test(form.spousePhone.trim()))
      errs.spousePhone = "Use digits, spaces, dashes, parens, leading +";
  }

  if (form.zip && !_zipRe.test(form.zip.trim()))
    errs.zip = "Use 5 digits or 5+4";

  form.dependentDetails.forEach((d, i) => {
    if (!d.firstName.trim()) errs[`dep${i}_firstName`] = "Required";
    if (!d.lastName.trim()) errs[`dep${i}_lastName`] = "Required";
    if (!d.relationship) errs[`dep${i}_relationship`] = "Required";
    if (d.ssn && !_ssnRe.test(d.ssn.trim()))
      errs[`dep${i}_ssn`] = "Use 9 digits — dashes optional";
  });

  return errs;
}

export function IntakeModal({ open, onClose, onSubmit, editData, mode = "create" }: IntakeModalProps) {
  const [form, setForm] = useState<IntakeFormData>({ ...defaultForm });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (editData && mode === "edit") {
      // Strip non-form-field metadata (id, *Masked snippets) before merging
      // so we don't pollute IntakeFormData with extras the form doesn't know
      // about. The masked snippets are read off editData directly by the
      // PiiInput JSX below.
      const {
        id: _id,
        ssnMasked: _sm1,
        dobMasked: _sm2,
        spouseSsnMasked: _sm3,
        spouseDobMasked: _sm4,
        streetMasked: _sm5,
        ...formFields
      } = editData;
      void _id; void _sm1; void _sm2; void _sm3; void _sm4; void _sm5;
      const sanitized = Object.fromEntries(
        Object.entries(formFields).map(([k, v]) => [k, v ?? ""])
      );
      setForm({ ...defaultForm, ...sanitized });
    } else {
      setForm({ ...defaultForm });
    }
    setErrors({});
    setSubmitError(null);
    setSavedSuccess(null);
  }, [editData, mode, open]);

  const set = (field: keyof IntakeFormData, value: string | number | boolean | string[]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((e) => {
      if (!e[field as string]) return e;
      const { [field as string]: _, ...rest } = e;
      void _;
      return rest;
    });
  };

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

  const handleSubmit = async () => {
    setSubmitError(null);
    setSavedSuccess(null);
    const errs = validate(form);
    setErrors(errs);
    if (Object.keys(errs).length > 0) {
      setSubmitError(`Please fix ${Object.keys(errs).length} field${Object.keys(errs).length > 1 ? "s" : ""} above before saving.`);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(form);
      setSavedSuccess(
        mode === "edit"
          ? "Changes saved. Click Close to return."
          : "Client created. Click Close to return, or continue editing."
      );
    } catch (err) {
      // Surface backend validation / network errors inline; modal stays open.
      const raw = err instanceof Error ? err.message : "Unknown error";
      const match = raw.match(/API \d+: (.+)$/);
      let detail = raw;
      if (match) {
        try {
          const parsed = JSON.parse(match[1]);
          detail = typeof parsed.detail === "string"
            ? parsed.detail
            : JSON.stringify(parsed.detail || parsed);
        } catch {
          detail = match[1];
        }
      }
      setSubmitError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  const isJoint = form.filingStatus === "mfj" || form.filingStatus === "mfs";
  const isEdit = mode === "edit";

  const inputCls = "w-full border border-divider rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:border-apple-blue transition-colors bg-surface text-primary placeholder:text-tertiary";
  const inputErrCls = "w-full border border-red-400 rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:border-red-500 transition-colors bg-surface text-primary placeholder:text-tertiary";
  const labelCls = "text-[10px] font-medium text-tertiary uppercase tracking-wider mb-0.5 block";
  const sectionCls = "text-[11px] font-semibold text-primary pb-1 mb-2 border-b border-divider";
  const errCls = "text-[10px] text-red-500 mt-0.5";

  // Helper that returns input className + an inline error span.
  const fieldCls = (key: string) => (errors[key] ? inputErrCls : inputCls);
  const FieldError = ({ k }: { k: string }) =>
    errors[k] ? <div className={errCls}>{errors[k]}</div> : null;

  const errorCount = useMemo(() => Object.keys(errors).length, [errors]);

  return (
    <Modal open={open} onClose={onClose} className="max-w-5xl w-[92vw]">
      <ModalHeader onClose={onClose}>
        <div className="flex-1">
          <div className="text-[15px] font-semibold">{isEdit ? "Edit Client" : "New Client Intake"}</div>
          {savedSuccess && (
            <div className="flex items-center gap-1.5 mt-1">
              <svg className="w-3.5 h-3.5 text-brand-green shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}><path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <span className="text-[11px] text-brand-green font-medium">{savedSuccess}</span>
            </div>
          )}
          {submitError && (
            <div className="flex items-center gap-1.5 mt-1">
              <svg className="w-3.5 h-3.5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}><path d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <span className="text-[11px] text-red-500 font-medium">{submitError}</span>
            </div>
          )}
        </div>
      </ModalHeader>

      <ModalBody className="h-[75vh] p-0 overflow-hidden">
        <div className="overflow-y-auto px-5 py-4 space-y-4 h-full">

          {/* Primary Taxpayer */}
          <div>
            <div className={sectionCls}>Primary Taxpayer</div>
            <div className="grid grid-cols-4 gap-2">
              <div>
                <label className={labelCls}>First Name <span className="text-red-500">*</span></label>
                <input className={fieldCls("firstName")} value={v("firstName")} onChange={(e) => set("firstName", e.target.value)} placeholder="First name" maxLength={LIMITS.name} />
                <FieldError k="firstName" />
              </div>
              <div>
                <label className={labelCls}>Last Name <span className="text-red-500">*</span></label>
                <input className={fieldCls("lastName")} value={v("lastName")} onChange={(e) => set("lastName", e.target.value)} placeholder="Last name" maxLength={LIMITS.name} />
                <FieldError k="lastName" />
              </div>
              <div>
                <label className={labelCls}>SSN</label>
                <PiiInput
                  fieldName="primary_ssn"
                  clientId={editData?.id}
                  maskedValue={editData?.ssnMasked}
                  value={v("ssn")}
                  onChange={(val) => set("ssn", val)}
                  placeholder="XXX-XX-XXXX"
                  maxLength={LIMITS.ssn}
                  inputMode="numeric"
                  className={fieldCls("ssn")}
                  hasError={Boolean(errors.ssn)}
                />
                <FieldError k="ssn" />
              </div>
              <div>
                <label className={labelCls}>
                  Date of Birth
                  {isEdit && editData?.dobMasked && !v("dateOfBirth") && (
                    <span className="ml-1 text-tertiary normal-case">— stored: {editData.dobMasked}</span>
                  )}
                </label>
                <PiiInput
                  fieldName="primary_dob"
                  clientId={editData?.id}
                  maskedValue={editData?.dobMasked}
                  value={v("dateOfBirth")}
                  onChange={(val) => set("dateOfBirth", val)}
                  type="date"
                  className={inputCls}
                />
              </div>
            </div>
          </div>

          {/* Primary Contact */}
          <div>
            <div className={sectionCls}>Primary Contact</div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={labelCls}>Email</label>
                <input type="email" className={fieldCls("email")} value={v("email")} onChange={(e) => set("email", e.target.value)} placeholder="email@example.com" maxLength={LIMITS.email} />
                <FieldError k="email" />
              </div>
              <div>
                <label className={labelCls}>Phone</label>
                <input type="tel" className={fieldCls("phone")} value={v("phone")} onChange={(e) => set("phone", e.target.value)} placeholder="Phone" maxLength={LIMITS.phone} />
                <FieldError k="phone" />
              </div>
            </div>
          </div>

          {/* Filing + Group */}
          <div>
            <div className={sectionCls}>Filing Information</div>
            <div className="grid grid-cols-4 gap-2">
              <div>
                <label className={labelCls}>Filing Status <span className="text-red-500">*</span></label>
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
                <input className={inputCls} value={v("familyGroupName")} onChange={(e) => set("familyGroupName", e.target.value)} placeholder="Family name" maxLength={LIMITS.familyGroup} />
              </div>
            </div>
          </div>

          {/* Spouse — only for MFJ/MFS */}
          {isJoint && (
            <div>
              <div className={sectionCls}>Spouse</div>
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <label className={labelCls}>First Name <span className="text-red-500">*</span></label>
                  <input className={fieldCls("spouseFirstName")} value={v("spouseFirstName")} onChange={(e) => set("spouseFirstName", e.target.value)} placeholder="First name" maxLength={LIMITS.name} />
                  <FieldError k="spouseFirstName" />
                </div>
                <div>
                  <label className={labelCls}>Last Name <span className="text-red-500">*</span></label>
                  <input className={fieldCls("spouseLastName")} value={v("spouseLastName")} onChange={(e) => set("spouseLastName", e.target.value)} placeholder="Last name" maxLength={LIMITS.name} />
                  <FieldError k="spouseLastName" />
                </div>
                <div>
                  <label className={labelCls}>SSN</label>
                  <PiiInput
                    fieldName="spouse_ssn"
                    clientId={editData?.id}
                    maskedValue={editData?.spouseSsnMasked}
                    value={v("spouseSsn")}
                    onChange={(val) => set("spouseSsn", val)}
                    placeholder="XXX-XX-XXXX"
                    maxLength={LIMITS.ssn}
                    inputMode="numeric"
                    className={fieldCls("spouseSsn")}
                    hasError={Boolean(errors.spouseSsn)}
                  />
                  <FieldError k="spouseSsn" />
                </div>
                <div>
                  <label className={labelCls}>
                    Date of Birth
                    {isEdit && editData?.spouseDobMasked && !v("spouseDob") && (
                      <span className="ml-1 text-tertiary normal-case">— stored: {editData.spouseDobMasked}</span>
                    )}
                  </label>
                  <PiiInput
                    fieldName="spouse_dob"
                    clientId={editData?.id}
                    maskedValue={editData?.spouseDobMasked}
                    value={v("spouseDob")}
                    onChange={(val) => set("spouseDob", val)}
                    type="date"
                    className={inputCls}
                  />
                </div>
                <div>
                  <label className={labelCls}>Email</label>
                  <input type="email" className={fieldCls("spouseEmail")} value={v("spouseEmail")} onChange={(e) => set("spouseEmail", e.target.value)} placeholder="email@example.com" maxLength={LIMITS.email} />
                  <FieldError k="spouseEmail" />
                </div>
                <div>
                  <label className={labelCls}>Phone</label>
                  <input type="tel" className={fieldCls("spousePhone")} value={v("spousePhone")} onChange={(e) => set("spousePhone", e.target.value)} placeholder="Phone" maxLength={LIMITS.phone} />
                  <FieldError k="spousePhone" />
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
                  <label className={labelCls}>First Name <span className="text-red-500">*</span></label>
                  <input className={fieldCls(`dep${idx}_firstName`)} value={dep.firstName || ""} onChange={(e) => updateDependent(idx, "firstName", e.target.value)} maxLength={LIMITS.name} />
                  <FieldError k={`dep${idx}_firstName`} />
                </div>
                <div>
                  <label className={labelCls}>Last Name <span className="text-red-500">*</span></label>
                  <input className={fieldCls(`dep${idx}_lastName`)} value={dep.lastName || ""} onChange={(e) => updateDependent(idx, "lastName", e.target.value)} maxLength={LIMITS.name} />
                  <FieldError k={`dep${idx}_lastName`} />
                </div>
                <div>
                  <label className={labelCls}>SSN</label>
                  <input className={fieldCls(`dep${idx}_ssn`)} value={dep.ssn || ""} onChange={(e) => updateDependent(idx, "ssn", e.target.value)} placeholder="XXX-XX-XXXX" maxLength={LIMITS.ssn} inputMode="numeric" />
                  <FieldError k={`dep${idx}_ssn`} />
                </div>
                <div>
                  <label className={labelCls}>DOB</label>
                  <input type="date" className={inputCls} value={dep.dob || ""} onChange={(e) => updateDependent(idx, "dob", e.target.value)} />
                </div>
                <div>
                  <label className={labelCls}>Relationship <span className="text-red-500">*</span></label>
                  <select className={fieldCls(`dep${idx}_relationship`)} value={dep.relationship || ""} onChange={(e) => updateDependent(idx, "relationship", e.target.value)}>
                    {RELATIONSHIPS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                  <FieldError k={`dep${idx}_relationship`} />
                </div>
              </div>
            </div>
          ))}

          {/* Address */}
          <div>
            <div className={sectionCls}>Address</div>
            <div className="grid grid-cols-4 gap-2">
              <div className="col-span-2">
                <label className={labelCls}>
                  Street
                  {isEdit && editData?.streetMasked && !v("street") && (
                    <span className="ml-1 text-tertiary normal-case">— stored securely</span>
                  )}
                </label>
                {/* Street is encrypted at rest. PiiInput shows the eye icon
                    only if the user has can_view_pii. We deliberately do NOT
                    pass the masked snippet (e.g. "Hoove***") as the
                    placeholder — leaking the first 5 chars of an address is
                    too much exposure for screen-share scenarios. */}
                <PiiInput
                  fieldName="street"
                  clientId={editData?.id}
                  maskedValue={editData?.streetMasked}
                  value={v("street")}
                  onChange={(val) => set("street", val)}
                  placeholder={
                    isEdit && editData?.streetMasked
                      ? "Reveal to view — or type a new address"
                      : "Street address"
                  }
                  maxLength={LIMITS.street}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>City</label>
                <input className={inputCls} value={v("city")} onChange={(e) => set("city", e.target.value)} placeholder="City" maxLength={LIMITS.city} />
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
                  <input className={fieldCls("zip")} value={v("zip")} onChange={(e) => set("zip", e.target.value)} placeholder="ZIP code" maxLength={LIMITS.zip} inputMode="numeric" />
                  <FieldError k="zip" />
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
              maxLength={LIMITS.notes}
              onChange={(e) => set("notes", e.target.value)} placeholder="Special circumstances, prior year issues..." />
          </div>

          {/* Persistent status banners */}
        </div>
      </ModalBody>

      {/* Footer — explicit Close (modal does not auto-dismiss on success) */}
      <div className="px-5 py-2.5 border-t border-divider flex items-center justify-between shrink-0 bg-surface-secondary/50">
        <div className="text-[11px] text-tertiary">
          {errorCount > 0 && `${errorCount} field${errorCount > 1 ? "s" : ""} need attention`}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg border border-divider text-[12px] text-secondary hover:bg-surface-tertiary transition-colors cursor-pointer">
            Close
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-1.5 rounded-lg bg-apple-blue text-white text-[12px] font-medium hover:brightness-110 transition-all cursor-pointer disabled:opacity-40"
          >
            {submitting
              ? (isEdit ? "Saving\u2026" : "Creating\u2026")
              : (isEdit ? "Save Changes" : "Create Client")
            }
          </button>
        </div>
      </div>
    </Modal>
  );
}
