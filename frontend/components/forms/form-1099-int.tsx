"use client";

interface Form1099IntData {
  payer_name?: string;
  payer_tin?: string;
  recipient_name?: string;
  recipient_tin?: string;
  interest_income?: number;
  early_withdrawal_penalty?: number;
  interest_on_savings_bonds?: number;
  federal_tax_withheld?: number;
  investment_expenses?: number;
  foreign_tax_paid?: number;
  tax_exempt_interest?: number;
  [key: string]: unknown;
}

export function Form1099Int({ data }: { data: Form1099IntData }) {
  const fmt = (v: number | undefined) =>
    v !== undefined ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "--";

  return (
    <div className="border border-gray-300 rounded-lg overflow-hidden text-[12px]">
      {/* Header */}
      <div className="bg-[#1E3A5F] text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form 1099-INT</span>
        <span className="text-white/70 text-[11px]">Interest Income 2025</span>
      </div>

      <div className="p-3 space-y-2">
        {/* Payer / Recipient */}
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase mb-0.5">Payer</div>
            <div className="font-medium">{data.payer_name || "--"}</div>
            <div className="text-gray-500">TIN: {data.payer_tin || "--"}</div>
          </div>
          <div className="border border-gray-200 rounded p-2">
            <div className="text-[10px] text-gray-400 uppercase mb-0.5">Recipient</div>
            <div className="font-medium">{data.recipient_name || "--"}</div>
            <div className="text-gray-500">TIN: {data.recipient_tin || "***-**-****"}</div>
          </div>
        </div>

        {/* Boxes */}
        <div className="grid grid-cols-2 gap-2">
          {[
            { box: "1", label: "Interest income", value: fmt(data.interest_income) },
            { box: "2", label: "Early withdrawal penalty", value: fmt(data.early_withdrawal_penalty) },
            { box: "3", label: "Interest on U.S. Savings Bonds", value: fmt(data.interest_on_savings_bonds) },
            { box: "4", label: "Federal income tax withheld", value: fmt(data.federal_tax_withheld) },
            { box: "5", label: "Investment expenses", value: fmt(data.investment_expenses) },
            { box: "6", label: "Foreign tax paid", value: fmt(data.foreign_tax_paid) },
            { box: "8", label: "Tax-exempt interest", value: fmt(data.tax_exempt_interest) },
          ].map((item) => (
            <div key={item.box} className="border border-gray-200 rounded p-2">
              <div className="text-[10px] text-gray-400 mb-0.5">
                Box {item.box} - {item.label}
              </div>
              <div className="font-semibold text-[13px]">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
