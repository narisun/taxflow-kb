"use client";

export function GenericForm({
  formType,
  data,
}: {
  formType: string;
  data: Record<string, unknown>;
}) {
  const entries = Object.entries(data || {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== ""
  );

  return (
    <div className="border border-gray-300 rounded-lg overflow-hidden text-[12px]">
      {/* Header */}
      <div className="bg-[#1E3A5F] text-white px-4 py-2 flex items-center justify-between">
        <span className="font-bold text-[14px]">Form {formType}</span>
        <span className="text-white/70 text-[11px]">Tax Year 2025</span>
      </div>

      <div className="p-3">
        {entries.length === 0 ? (
          <p className="text-gray-400 text-center py-4">No extracted data available</p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {entries.map(([key, value]) => (
              <div key={key} className="border border-gray-200 rounded p-2">
                <div className="text-[10px] text-gray-400 uppercase mb-0.5">
                  {key.replace(/_/g, " ")}
                </div>
                <div className="font-medium text-[13px]">
                  {typeof value === "number"
                    ? `$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
                    : String(value)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
