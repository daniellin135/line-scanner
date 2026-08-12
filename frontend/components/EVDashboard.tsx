"use client";

import { useEffect, useState } from "react";

type EVBet = {
  game_id: number;
  home_team: string;
  away_team: string;
  recommended_bet: string;
  recreational_odds: number;
  expected_value: number;
};

const websocketUrl =
  process.env.NEXT_PUBLIC_EV_STREAM_URL ??
  "ws://localhost:8000/api/v1/ev-stream";

const formatAmericanOdds = (odds: number): string =>
  odds > 0 ? `+${odds}` : String(odds);

export default function EVDashboard(): React.JSX.Element {
  const [bets, setBets] = useState<EVBet[]>([]);
  const [connectionStatus, setConnectionStatus] = useState("Connecting...");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let isUnmounted = false;

    const connect = (): void => {
      socket = new WebSocket(websocketUrl);

      socket.onopen = (): void => setConnectionStatus("Live");
      socket.onmessage = (event: MessageEvent<string>): void => {
        try {
          const payload: unknown = JSON.parse(event.data);
          if (Array.isArray(payload)) {
            setBets(payload as EVBet[]);
          }
        } catch {
          setConnectionStatus("Invalid stream payload");
        }
      };
      socket.onerror = (): void => setConnectionStatus("Connection error");
      socket.onclose = (): void => {
        if (isUnmounted) {
          return;
        }
        setConnectionStatus("Reconnecting...");
        reconnectTimer = setTimeout(connect, 3_000);
      };
    };

    connect();

    return (): void => {
      isUnmounted = true;
      if (reconnectTimer !== undefined) {
        clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, []);

  return (
    <section className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">+EV Opportunities</h1>
          <p className="mt-1 text-sm text-slate-400">
            Live Pinnacle-to-FanDuel moneyline comparisons.
          </p>
        </div>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">
          {connectionStatus}
        </span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900 shadow-xl">
        <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
          <thead className="bg-slate-950 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-5 py-4">Game ID</th>
              <th className="px-5 py-4">Home</th>
              <th className="px-5 py-4">Away</th>
              <th className="px-5 py-4">Recommended Bet</th>
              <th className="px-5 py-4">FanDuel Odds</th>
              <th className="px-5 py-4">Expected Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 text-slate-200">
            {bets.map((bet) => (
              <tr key={`${bet.game_id}-${bet.recommended_bet}`}>
                <td className="px-5 py-4 font-mono text-slate-400">{bet.game_id}</td>
                <td className="px-5 py-4">{bet.home_team}</td>
                <td className="px-5 py-4">{bet.away_team}</td>
                <td className="px-5 py-4 font-medium">{bet.recommended_bet}</td>
                <td className="px-5 py-4 font-mono">
                  {formatAmericanOdds(bet.recreational_odds)}
                </td>
                <td className="px-5 py-4 font-semibold text-emerald-400">
                  ${bet.expected_value.toFixed(2)}
                </td>
              </tr>
            ))}
            {bets.length === 0 && (
              <tr>
                <td className="px-5 py-10 text-center text-slate-500" colSpan={6}>
                  No positive expected-value bets are available right now.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
