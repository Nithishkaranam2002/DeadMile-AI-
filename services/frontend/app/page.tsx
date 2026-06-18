export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="mb-4 text-5xl font-bold tracking-tight">
          DeadMile <span className="text-blue-400">AI</span>
        </h1>
        <p className="mb-8 text-lg text-gray-400">
          Intelligent Load Optimization for Small Trucking Carriers
        </p>
        <div className="grid grid-cols-2 gap-4 text-sm text-gray-500">
          <div className="rounded-lg border border-gray-800 p-4">
            <p className="font-medium text-gray-300">Smart Recommendations</p>
            <p>True net profitability scoring</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-4">
            <p className="font-medium text-gray-300">Multi-Hop Chains</p>
            <p>Maximize weekly earnings</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-4">
            <p className="font-medium text-gray-300">Market Intelligence</p>
            <p>Destination market heatmaps</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-4">
            <p className="font-medium text-gray-300">AI Agent</p>
            <p>8 tools, SSE streaming</p>
          </div>
        </div>
      </div>
    </main>
  );
}
