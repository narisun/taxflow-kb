"use client";

import { useState } from "react";
import { cn, fmtTimestamp, fmtDate } from "@/lib/utils";
import { useTimezone } from "@/components/auth/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

type FilingStep = "verify" | "authorize" | "pin" | "submitting" | "result";
type FilingResult = "submitted" | "accepted" | "rejected" | null;

interface FilingWorkflowProps {
  clientName?: string;
  filingStatus?: string;
}

export function FilingWorkflow({ clientName = "Smith, John", filingStatus = "single" }: FilingWorkflowProps) {
  const tz = useTimezone();
  const [step, setStep] = useState<FilingStep>("verify");
  const [result, setResult] = useState<FilingResult>(null);
  const [ssnPrimary, setSsnPrimary] = useState("");
  const [ssnSpouse, setSsnSpouse] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [irsPin, setIrsPin] = useState("");
  const [submitProgress, setSubmitProgress] = useState(0);

  const isJoint = filingStatus === "mfj" || filingStatus === "mfs";

  const handleSubmit = () => {
    setStep("submitting");
    setSubmitProgress(0);
    // Simulate submission progress
    const interval = setInterval(() => {
      setSubmitProgress((p) => {
        if (p >= 100) {
          clearInterval(interval);
          setTimeout(() => {
            setStep("result");
            // 90% chance accepted, 10% rejected for demo
            setResult(Math.random() > 0.1 ? "accepted" : "rejected");
          }, 500);
          return 100;
        }
        return p + 20;
      });
    }, 400);
  };

  const handleReset = () => {
    setStep("verify");
    setResult(null);
    setSsnPrimary("");
    setSsnSpouse("");
    setAuthorized(false);
    setIrsPin("");
    setSubmitProgress(0);
  };

  const stepNumber = step === "verify" ? 1 : step === "authorize" ? 2 : step === "pin" ? 3 : step === "submitting" ? 4 : 4;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="text-[11px] font-semibold text-secondary uppercase tracking-wider">
        E-File Submission
      </div>

      {/* Step indicator */}
      {step !== "result" && (
        <div className="flex items-center gap-1">
          {["Verify", "Authorize", "PIN", "Submit"].map((label, i) => (
            <div key={label} className="flex items-center gap-1 flex-1">
              {i > 0 && <div className="flex-1 h-px bg-divider" />}
              <div className={cn(
                "flex items-center gap-1",
              )}>
                <span className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold",
                  i + 1 < stepNumber ? "bg-brand-green text-white"
                    : i + 1 === stepNumber ? "bg-apple-blue text-white"
                    : "bg-surface-tertiary text-tertiary"
                )}>
                  {i + 1 < stepNumber ? "\u2713" : i + 1}
                </span>
                <span className={cn(
                  "text-[10px]",
                  i + 1 === stepNumber ? "text-primary font-medium" : "text-tertiary"
                )}>
                  {label}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Step 1: Verify SSN */}
      {step === "verify" && (
        <div className="space-y-3">
          <div className="text-[13px] font-medium text-primary">Verify Taxpayer Identity</div>
          <div className="text-[11px] text-tertiary">
            Confirm the Social Security Number for each taxpayer before filing.
          </div>

          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-medium text-tertiary uppercase tracking-wider block mb-1">
                Primary Taxpayer SSN
              </label>
              <div className="text-[11px] text-secondary mb-1">{clientName}</div>
              <Input
                value={ssnPrimary}
                onChange={(e) => setSsnPrimary(e.target.value)}
                placeholder="XXX-XX-XXXX"
                className="text-[13px]"
              />
            </div>

            {isJoint && (
              <div>
                <label className="text-[10px] font-medium text-tertiary uppercase tracking-wider block mb-1">
                  Spouse SSN
                </label>
                <Input
                  value={ssnSpouse}
                  onChange={(e) => setSsnSpouse(e.target.value)}
                  placeholder="XXX-XX-XXXX"
                  className="text-[13px]"
                />
              </div>
            )}
          </div>

          <div className="flex justify-end pt-1">
            <Button
              variant="primary"
              onClick={() => setStep("authorize")}
              disabled={!ssnPrimary || (isJoint && !ssnSpouse)}
              title={!ssnPrimary ? "Enter the primary taxpayer's SSN to continue" : (isJoint && !ssnSpouse) ? "Enter the spouse's SSN for joint filing" : undefined}
              className="text-[12px] px-4 py-1.5"
            >
              Next: Authorize
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: CPA Authorization */}
      {step === "authorize" && (
        <div className="space-y-3">
          <div className="text-[13px] font-medium text-primary">CPA Authorization</div>
          <div className="text-[11px] text-tertiary">
            As the authorized preparer, confirm you are filing on behalf of the taxpayer.
          </div>

          <div className="bg-surface-secondary rounded-lg p-3 space-y-2">
            <div className="text-[11px]">
              <span className="text-tertiary">Client: </span>
              <span className="text-primary font-medium">{clientName}</span>
            </div>
            <div className="text-[11px]">
              <span className="text-tertiary">Filing: </span>
              <span className="text-primary font-medium">{filingStatus.toUpperCase()} &middot; TY 2025</span>
            </div>
            <div className="text-[11px]">
              <span className="text-tertiary">SSN verified: </span>
              <span className="text-primary font-medium">***-**-{ssnPrimary.slice(-4) || "XXXX"}</span>
            </div>
          </div>

          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={authorized}
              onChange={(e) => setAuthorized(e.target.checked)}
              className="w-4 h-4 mt-0.5 accent-apple-blue cursor-pointer"
            />
            <span className="text-[11px] text-primary leading-relaxed">
              I confirm that I am authorized to file this return on behalf of the taxpayer and that all information is accurate to the best of my knowledge.
            </span>
          </label>

          <div className="flex justify-between pt-1">
            <Button variant="ghost" onClick={() => setStep("verify")} className="text-[12px]">
              Back
            </Button>
            <Button
              variant="primary"
              onClick={() => setStep("pin")}
              disabled={!authorized}
              title={!authorized ? "Confirm CPA authorization to continue" : undefined}
              className="text-[12px] px-4 py-1.5"
            >
              Next: IRS PIN
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: IRS PIN */}
      {step === "pin" && (
        <div className="space-y-3">
          <div className="text-[13px] font-medium text-primary">IRS E-File PIN</div>
          <div className="text-[11px] text-tertiary">
            Enter the taxpayer&apos;s IRS Identity Protection PIN (IP PIN) if applicable, or your ERO PIN.
          </div>

          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-medium text-tertiary uppercase tracking-wider block mb-1">
                IRS PIN / ERO PIN
              </label>
              <Input
                value={irsPin}
                onChange={(e) => setIrsPin(e.target.value)}
                placeholder="Enter 5 or 6 digit PIN"
                className="text-[13px]"
                type="password"
              />
            </div>
            <div className="text-[10px] text-tertiary">
              If the taxpayer does not have an IP PIN, enter your ERO (Electronic Return Originator) PIN.
            </div>
          </div>

          <div className="flex justify-between pt-1">
            <Button variant="ghost" onClick={() => setStep("authorize")} className="text-[12px]">
              Back
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={!irsPin}
              title={!irsPin ? "Enter the IRS PIN or ERO PIN to submit" : undefined}
              className="text-[12px] px-4 py-1.5"
            >
              Submit to IRS
            </Button>
          </div>
        </div>
      )}

      {/* Step 4: Submitting */}
      {step === "submitting" && (
        <div className="space-y-4 py-6">
          <div className="text-center">
            <div className="text-[13px] font-medium text-primary mb-2">Submitting to IRS...</div>
            <div className="text-[11px] text-tertiary mb-4">Transmitting return via e-file. Do not close this window.</div>
          </div>
          <Progress value={submitProgress} color="blue" className="h-2" />
          <div className="text-[11px] text-tertiary text-center">
            {submitProgress < 30 ? "Validating return data..." :
             submitProgress < 60 ? "Connecting to IRS MeF system..." :
             submitProgress < 90 ? "Transmitting return..." :
             "Awaiting acknowledgment..."}
          </div>
        </div>
      )}

      {/* Result: Accepted */}
      {step === "result" && result === "accepted" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-full bg-brand-green text-white flex items-center justify-center text-[16px]">{"\u2713"}</span>
            <div>
              <div className="text-[13px] font-semibold text-primary">Return Accepted</div>
              <div className="text-[11px] text-tertiary">IRS acknowledged receipt</div>
            </div>
          </div>

          <div className="bg-surface-secondary rounded-lg p-3 space-y-1.5 text-[11px]">
            <div><span className="text-tertiary">Status: </span><span className="text-brand-green font-medium">Accepted</span></div>
            <div><span className="text-tertiary">Confirmation: </span><span className="text-primary font-medium">2026-FED-{String(Math.floor(Math.random() * 90000 + 10000))}</span></div>
            <div><span className="text-tertiary">Submitted: </span><span className="text-primary">{fmtTimestamp(new Date().toISOString(), tz)}</span></div>
            <div><span className="text-tertiary">Preparer: </span><span className="text-primary">SC (ERO)</span></div>
            <div><span className="text-tertiary">Client: </span><span className="text-primary">{clientName}</span></div>
            <div><span className="text-tertiary">Expected refund: </span><span className="text-primary">2-3 weeks via direct deposit</span></div>
          </div>

          <div className="text-[10px] text-tertiary">
            A copy of the acceptance confirmation has been saved to the client file.
          </div>
        </div>
      )}

      {/* Result: Rejected */}
      {step === "result" && result === "rejected" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-full bg-red-500 text-white flex items-center justify-center text-[16px]">{"\u2717"}</span>
            <div>
              <div className="text-[13px] font-semibold text-primary">Return Rejected</div>
              <div className="text-[11px] text-tertiary">IRS rejected the submission</div>
            </div>
          </div>

          <div className="bg-surface-secondary rounded-lg p-3 space-y-1.5 text-[11px]">
            <div><span className="text-tertiary">Status: </span><span className="text-red-500 font-medium">Rejected</span></div>
            <div><span className="text-tertiary">Submitted: </span><span className="text-primary">{fmtDate(new Date().toISOString(), tz)}</span></div>
            <div><span className="text-tertiary">Reject code: </span><span className="text-primary font-medium">IND-031-04</span></div>
            <div><span className="text-tertiary">Reason: </span><span className="text-primary">SSN/Name mismatch — the primary taxpayer SSN does not match IRS records for the name provided.</span></div>
          </div>

          <div className="bg-badge-review-bg rounded-lg p-3 text-[11px] text-badge-review-text">
            <span className="mr-1">{"\u26A0"}</span>
            Correct the taxpayer name or SSN and resubmit. The return can be resubmitted within 5 business days.
          </div>

          <div className="flex justify-end pt-1">
            <Button variant="primary" onClick={handleReset} className="text-[12px] px-4 py-1.5">
              Correct &amp; Resubmit
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
