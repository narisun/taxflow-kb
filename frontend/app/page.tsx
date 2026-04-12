export default function Home() {
  return (
    <div className="flex flex-col h-full">
      <nav
        className="h-12 flex items-center px-4 gap-3 shrink-0 z-50"
        style={{
          background: "rgba(0, 0, 0, 0.8)",
          backdropFilter: "saturate(180%) blur(20px)",
        }}
      >
        <div className="w-8 h-8 bg-[#0071e3] rounded-md flex items-center justify-center text-white text-sm font-bold">
          T
        </div>
        <span
          className="text-white text-base font-semibold"
          style={{ letterSpacing: "-0.3px" }}
        >
          Tax Brain
        </span>
      </nav>
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-72 shrink-0 bg-[#f5f5f7] border-r border-gray-200">
          <div className="p-4 text-sm text-gray-500">Client Sidebar</div>
        </aside>
        <main className="flex-1 flex flex-col bg-white">
          <div className="p-4 text-sm text-gray-500">Chat Panel</div>
        </main>
        <aside className="w-96 shrink-0 bg-white border-l border-gray-200">
          <div className="p-4 text-sm text-gray-500">Work Panel</div>
        </aside>
      </div>
    </div>
  );
}
