import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { APP_TITLE } from "@/const";
import { trpc } from "@/lib/trpc";
import { useState, useEffect } from "react";

export default function Home() {
  const [activeTab, setActiveTab] = useState("control");
  const [isLoading, setIsLoading] = useState(false);

  // Trading config state
  const [privateKey, setPrivateKey] = useState("");
  const [rpcUrl, setRpcUrl] = useState("https://api.mainnet-beta.solana.com");
  const [period, setPeriod] = useState(10);
  const [multiplier, setMultiplier] = useState(3);
  const [tradeAmountPercent, setTradeAmountPercent] = useState(50);
  const [slippageTolerance, setSlippageTolerance] = useState(1.5);
  const [autoTrade, setAutoTrade] = useState(false);
  const [testAmount, setTestAmount] = useState(5);

  // Queries and mutations
  const configQuery = trpc.trading.getConfig.useQuery();

  const updateConfigMutation = trpc.trading.updateConfig.useMutation();
  const startBotMutation = trpc.trading.startBot.useMutation();
  const stopBotMutation = trpc.trading.stopBot.useMutation();
  const testTransactionMutation = trpc.trading.testTransaction.useMutation();
  const botStatusQuery = trpc.trading.getBotStatus.useQuery(undefined, {
    refetchInterval: 5000, // Refresh every 5 seconds
  });
  const logsQuery = trpc.trading.getLogs.useQuery({ limit: 50 }, {
    refetchInterval: 3000, // Refresh every 3 seconds
  });
  const tradeHistoryQuery = trpc.trading.getTradeHistory.useQuery({ limit: 20 }, {
    refetchInterval: 10000, // Refresh every 10 seconds
  });
  const tradeStatsQuery = trpc.trading.getTradeStats.useQuery(undefined, {
    refetchInterval: 10000,
  });

  // Load config when available
  useEffect(() => {
    if (configQuery.data) {
      setPrivateKey(configQuery.data.solanaPrivateKey || "");
      setRpcUrl(configQuery.data.rpcUrl || "https://api.mainnet-beta.solana.com");
      setPeriod(configQuery.data.period || 10);
      setMultiplier(parseFloat(configQuery.data.multiplier?.toString() || "3"));
      setTradeAmountPercent(configQuery.data.tradeAmountPercent || 50);
      setSlippageTolerance(parseFloat(configQuery.data.slippageTolerance?.toString() || "1.5"));
      setAutoTrade(configQuery.data.autoTrade || false);
    }
  }, [configQuery.data]);

  const handleSaveConfig = async () => {
    setIsLoading(true);
    try {
      await updateConfigMutation.mutateAsync({
        solanaPrivateKey: privateKey,
        rpcUrl,
        period,
        multiplier,
        tradeAmountPercent,
        slippageTolerance,
        autoTrade,
      });
      alert("Configuration saved successfully!");
    } catch (error) {
      alert(`Error saving configuration: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartBot = async () => {
    setIsLoading(true);
    try {
      await startBotMutation.mutateAsync();
      alert("Bot started successfully!");
      botStatusQuery.refetch();
    } catch (error) {
      alert(`Error starting bot: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopBot = async () => {
    setIsLoading(true);
    try {
      await stopBotMutation.mutateAsync();
      alert("Bot stopped successfully!");
      botStatusQuery.refetch();
    } catch (error) {
      alert(`Error stopping bot: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestTransaction = async (type: "buy" | "sell") => {
    setIsLoading(true);
    try {
      const result = await testTransactionMutation.mutateAsync({
        transactionType: type,
        amount: testAmount,
      });

      if (result.success) {
        alert(`Test ${type.toUpperCase()} transaction successful!\nTX Hash: ${result.txHash}`);
        logsQuery.refetch();
        tradeHistoryQuery.refetch();
      } else {
        alert(`Test ${type.toUpperCase()} transaction failed: ${result.error}`);
      }
    } catch (error) {
      alert(`Error executing test transaction: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-purple-900 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-bold text-white">🤖 Solana Trading Bot</h1>
            <p className="text-purple-200">SuperTrend Strategy - Automated Trading</p>
          </div>
        </div>

        {/* Bot Status */}
        <Card className="mb-8 bg-slate-800 border-purple-500">
          <CardHeader>
            <CardTitle className="text-purple-300">Bot Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <Label className="text-gray-400">Status</Label>
                <p className={`text-lg font-bold ${botStatusQuery.data?.isRunning ? "text-green-400" : "text-gray-400"}`}>
                  {botStatusQuery.data?.isRunning ? "🟢 Running" : "🔴 Stopped"}
                </p>
              </div>
              <div>
                <Label className="text-gray-400">SOL Balance</Label>
                <p className="text-lg font-bold text-white">
                  {botStatusQuery.data && "balance" in botStatusQuery.data ? (botStatusQuery.data.balance?.toFixed(4) || "0.0000") : "0.0000"} SOL
                </p>
              </div>
              <div>
                <Label className="text-gray-400">USDC Balance</Label>
                <p className="text-lg font-bold text-white">
                  {botStatusQuery.data && "usdcBalance" in botStatusQuery.data ? ((botStatusQuery.data as any).usdcBalance?.toFixed(2) || "0.00") : "0.00"} USDC
                </p>
              </div>
              <div>
                <Label className="text-gray-400">Current Price</Label>
                <p className="text-lg font-bold text-white">
                  ${botStatusQuery.data && "currentPrice" in botStatusQuery.data ? (botStatusQuery.data.currentPrice?.toFixed(2) || "0.00") : "0.00"}
                </p>
              </div>
              <div>
                <Label className="text-gray-400">Trend</Label>
                <p className={`text-lg font-bold ${botStatusQuery.data && "trend" in botStatusQuery.data && botStatusQuery.data.trend === "up" ? "text-green-400" : "text-red-400"}`}>
                  {botStatusQuery.data && "trend" in botStatusQuery.data && botStatusQuery.data.trend === "up" ? "📈 Up" : "📉 Down"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Main Content */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4 bg-slate-800">
            <TabsTrigger value="control">Control</TabsTrigger>
            <TabsTrigger value="config">Configuration</TabsTrigger>
            <TabsTrigger value="logs">Logs</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
          </TabsList>

          {/* Control Tab */}
          <TabsContent value="control">
            <Card className="bg-slate-800 border-purple-500">
              <CardHeader>
                <CardTitle className="text-purple-300">Bot Control</CardTitle>
                <CardDescription>Start/stop the trading bot and run test transactions</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex gap-4">
                  <Button
                    onClick={handleStartBot}
                    disabled={isLoading || botStatusQuery.data?.isRunning}
                    className="flex-1 bg-green-600 hover:bg-green-700"
                    size="lg"
                  >
                    ▶️ Start Bot
                  </Button>
                  <Button
                    onClick={handleStopBot}
                    disabled={isLoading || !botStatusQuery.data?.isRunning}
                    className="flex-1 bg-red-600 hover:bg-red-700"
                    variant="destructive"
                    size="lg"
                  >
                    ⏹️ Stop Bot
                  </Button>
                </div>

                <div className="border-t border-slate-600 pt-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Test Transactions</h3>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="testAmount" className="text-gray-300">
                        Test Amount (SOL)
                      </Label>
                      <Input
                        id="testAmount"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={testAmount}
                        onChange={(e) => setTestAmount(parseFloat(e.target.value))}
                        className="bg-slate-700 border-slate-600 text-white"
                      />
                    </div>
                    <div className="flex gap-4">
                      <Button
                        onClick={() => handleTestTransaction("buy")}
                        disabled={isLoading}
                        className="flex-1 bg-blue-600 hover:bg-blue-700"
                      >
                        📈 Test BUY
                      </Button>
                      <Button
                        onClick={() => handleTestTransaction("sell")}
                        disabled={isLoading}
                        className="flex-1 bg-orange-600 hover:bg-orange-700"
                      >
                        📉 Test SELL
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Configuration Tab */}
          <TabsContent value="config">
            <Card className="bg-slate-800 border-purple-500">
              <CardHeader>
                <CardTitle className="text-purple-300">Trading Configuration</CardTitle>
                <CardDescription>Set up your bot parameters</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <Label htmlFor="privateKey" className="text-gray-300">
                    Solana Private Key (Base58)
                  </Label>
                  <Input
                    id="privateKey"
                    type="password"
                    placeholder="Enter your private key"
                    value={privateKey}
                    onChange={(e) => setPrivateKey(e.target.value)}
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                  <p className="text-xs text-gray-400 mt-2">🔒 Your private key is stored securely and never shared</p>
                </div>

                <div>
                  <Label htmlFor="rpcUrl" className="text-gray-300">
                    RPC URL
                  </Label>
                  <Input
                    id="rpcUrl"
                    placeholder="https://api.mainnet-beta.solana.com"
                    value={rpcUrl}
                    onChange={(e) => setRpcUrl(e.target.value)}
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="period" className="text-gray-300">
                      SuperTrend Period
                    </Label>
                    <Input
                      id="period"
                      type="number"
                      min="1"
                      value={period}
                      onChange={(e) => setPeriod(parseInt(e.target.value))}
                      className="bg-slate-700 border-slate-600 text-white"
                    />
                  </div>
                  <div>
                    <Label htmlFor="multiplier" className="text-gray-300">
                      SuperTrend Multiplier
                    </Label>
                    <Input
                      id="multiplier"
                      type="number"
                      step="0.1"
                      value={multiplier}
                      onChange={(e) => setMultiplier(parseFloat(e.target.value))}
                      className="bg-slate-700 border-slate-600 text-white"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="tradeAmountPercent" className="text-gray-300">
                      Trade Amount (% of balance)
                    </Label>
                    <Input
                      id="tradeAmountPercent"
                      type="number"
                      min="1"
                      max="100"
                      value={tradeAmountPercent}
                      onChange={(e) => setTradeAmountPercent(parseInt(e.target.value))}
                      className="bg-slate-700 border-slate-600 text-white"
                    />
                  </div>
                  <div>
                    <Label htmlFor="slippageTolerance" className="text-gray-300">
                      Slippage Tolerance (%)
                    </Label>
                    <Input
                      id="slippageTolerance"
                      type="number"
                      step="0.1"
                      value={slippageTolerance}
                      onChange={(e) => setSlippageTolerance(parseFloat(e.target.value))}
                      className="bg-slate-700 border-slate-600 text-white"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    id="autoTrade"
                    type="checkbox"
                    checked={autoTrade}
                    onChange={(e) => setAutoTrade(e.target.checked)}
                    className="w-4 h-4"
                  />
                  <Label htmlFor="autoTrade" className="text-gray-300 cursor-pointer">
                    Enable Automatic Trading
                  </Label>
                </div>

                <Button
                  onClick={handleSaveConfig}
                  disabled={isLoading}
                  className="w-full bg-purple-600 hover:bg-purple-700"
                  size="lg"
                >
                  💾 Save Configuration
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Logs Tab */}
          <TabsContent value="logs">
            <Card className="bg-slate-800 border-purple-500">
              <CardHeader>
                <CardTitle className="text-purple-300">Activity Logs</CardTitle>
                <CardDescription>Real-time bot activity and trading events</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {logsQuery.data && logsQuery.data.length > 0 ? (
                    logsQuery.data.map((log, idx) => (
                      <div key={idx} className="p-3 bg-slate-700 rounded text-sm text-gray-300 border-l-2 border-purple-500">
                        <div className="flex justify-between">
                          <span className="font-mono">{log.message}</span>
                          <span className="text-gray-500 text-xs">
                            {log.createdAt ? new Date(log.createdAt).toLocaleTimeString() : ""}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-gray-400 text-center py-8">No logs yet</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Trades Tab */}
          <TabsContent value="trades">
            <Card className="bg-slate-800 border-purple-500">
              <CardHeader>
                <CardTitle className="text-purple-300">Trade History</CardTitle>
                <CardDescription>Recent trades executed by the bot</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {tradeHistoryQuery.data && tradeHistoryQuery.data.length > 0 ? (
                    tradeHistoryQuery.data.map((trade, idx) => (
                      <div key={idx} className="p-4 bg-slate-700 rounded border-l-4 border-purple-500">
                        <div className="flex justify-between items-start">
                          <div>
                            <p className="font-semibold text-white">
                              {trade.tradeType === "buy" ? "📈" : "📉"} {trade.tradeType.toUpperCase()} {parseFloat(trade.amountIn).toFixed(4)}
                            </p>
                            <p className="text-sm text-gray-400">
                              Price: ${parseFloat(trade.priceAtExecution).toFixed(2)} | Out: {parseFloat(trade.amountOut).toFixed(4)}
                            </p>
                          </div>
                          <span className="text-xs text-gray-500">
                            {trade.createdAt ? new Date(trade.createdAt).toLocaleString() : ""}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-gray-400 text-center py-8">No trades yet</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

