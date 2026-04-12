"use client";

interface W2Data {
  employer_name?: string;
  employer_ein?: string;
  employee_name?: string;
  employee_ssn?: string;
  wages?: number;
  federal_tax_withheld?: number;
  social_security_wages?: number;
  social_security_tax?: number;
  medicare_wages?: number;
  medicare_tax?: number;
  box_12?: string;
  state?: string;
  state_wages?: number;
  state_tax?: number;
  [key: string]: unknown;
}

export function W2Form({ data }: { data: W2Data }) {
  const fmt = (v: number | undefined) =>
    v !== undefined ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "--";

  return (
    <div className="border border-gray-300 rounded-lg overflow-hidden text-[12px]">
      {/* Header */}
      <div className="bg-[#1E3A5F] text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form W-2</span>
        <span className="text-white/70 text-[11px]">Wage and Tax Statement 2025</span>
      </div>

      <div className="p-3 space-y-2">
        {/* Employer / Employee */}
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase mb-0.5">Employer</div>
            <div className="font-medium">{data.employer_name || "--"}</div>
            <div className="text-gray-500">EIN: {data.employer_ein || "--"}</div>
          </div>
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase mb-0.5">Employee</div>
            <div className="font-medium">{data.employee_name || "--"}</div>
            <div className="text-gray-500">SSN: {data.employee_ssn || "***-**-****"}</div>
          </div>
        </div>

        {/* Boxes 1-6 */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { box: "1", label: "Wages, tips, other comp.", value: fmt(data.wages) },
            { box: "2", label: "Federal income tax withheld", value: fmt(data.federal_tax_withheld) },
            { box: "3", label: "Social security wages", value: fmt(data.social_security_wages) },
            { box: "4", label: "Social security tax withheld", value: fmt(data.social_security_tax) },
            { box: "5", label: "Medicare wages and tips", value: fmt(data.medicare_wages) },
            { box: "6", label: "Medicare tax withheld", value: fmt(data.medicare_tax) },
          ].map((item) => (
            <div key={item.box} className="border border-gray-200 rounded p-2">
              <div className="text-[10px] text-gray-400 mb-0.5">
                Box {item.box} - {item.label}
              </div>
              <div className="font-semibold text-[13px]">{item.value}</div>
            </div>
          ))}
        </div>

        {/* Box 12 & State */}
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 mb-0.5">Box 12 - Codes</div>
            <div className="font-medium">{data.box_12 || "--"}</div>
          </div>
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 mb-0.5">State: {data.state || "--"}</div>
            <div className="flex justify-between">
              <span>Wages: {fmt(data.state_wages)}</span>
              <span>Tax: {fmt(data.state_tax)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
