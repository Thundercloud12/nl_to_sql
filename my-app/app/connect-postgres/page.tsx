"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import {
  Database,
  ArrowLeft,
  Check,
  AlertCircle,
  Loader2,
  ChevronRight,
  ChevronDown,
  Table,
  Shield,
} from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface TableInfo {
  name: string;
  full_name: string;
  row_count: number;
  columns: Array<{
    column_name: string;
    data_type: string;
    is_nullable: boolean;
  }>;
}

interface SchemaInfo {
  name: string;
  tables: TableInfo[];
}

interface IntrospectionResult {
  schemas: SchemaInfo[];
}

export default function ConnectPostgresPage() {
  const router = useRouter();
  const { user } = useUser();

  // Connection form state
  const [connectionName, setConnectionName] = useState("Neon Database");
  const [host, setHost] = useState("ep-morning-bonus-ah7f7zs2-pooler.c-3.us-east-1.aws.neon.tech");
  const [port, setPort] = useState("5432");
  const [database, setDatabase] = useState("neondb");
  const [username, setUsername] = useState("neondb_owner");
  const [password, setPassword] = useState("npg_XZbaxc63pyhM");

  // UI state
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionTested, setConnectionTested] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);

  // Introspection state
  const [introspectionData, setIntrospectionData] = useState<IntrospectionResult | null>(null);
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(new Set());
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set());

  // Creation state
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const buildConnectionString = () => {
    return `postgresql://${username}:${password}@${host}:${port}/${database}`;
  };

  const handleTestConnection = async () => {
    console.log("[CONNECT-POSTGRES] 🧪 Testing connection...");

    if (!connectionName || !host || !port || !database || !username || !password) {
      setTestError("All fields are required");
      return;
    }

    setIsTestingConnection(true);
    setTestError(null);
    setConnectionTested(false);
    setIntrospectionData(null);

    try {
      const connectionString = buildConnectionString();

      // Step 1: Test connection
      console.log("[CONNECT-POSTGRES] 📤 POST /postgres/test-connection");
      const testResponse = await fetch(`${BACKEND_URL}/postgres/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connection_string: connectionString }),
      });

      if (!testResponse.ok) {
        const errorData = await testResponse.json();
        throw new Error(errorData.detail || "Connection test failed");
      }

      const testResult = await testResponse.json();
      console.log("[CONNECT-POSTGRES] ✅ Connection test result:", testResult);

      if (!testResult.success) {
        throw new Error(testResult.message || "Connection test failed");
      }

      // Step 2: Introspect schemas
      console.log("[CONNECT-POSTGRES] 📤 POST /postgres/introspect");
      const introspectResponse = await fetch(`${BACKEND_URL}/postgres/introspect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connection_string: connectionString }),
      });

      if (!introspectResponse.ok) {
        const errorData = await introspectResponse.json();
        throw new Error(errorData.detail || "Introspection failed");
      }

      const introspectionResult: IntrospectionResult = await introspectResponse.json();
      console.log("[CONNECT-POSTGRES] ✅ Introspection result:", introspectionResult);

      setIntrospectionData(introspectionResult);
      setConnectionTested(true);
      setTestError(null);

      // Auto-expand first schema
      if (introspectionResult.schemas.length > 0) {
        setExpandedSchemas(new Set([introspectionResult.schemas[0].name]));
      }
    } catch (error: any) {
      console.error("[CONNECT-POSTGRES] ❌ Error:", error);
      setTestError(error.message || "Failed to connect to database");
      setConnectionTested(false);
    } finally {
      setIsTestingConnection(false);
    }
  };

  const toggleSchema = (schemaName: string) => {
    const newExpanded = new Set(expandedSchemas);
    if (newExpanded.has(schemaName)) {
      newExpanded.delete(schemaName);
    } else {
      newExpanded.add(schemaName);
    }
    setExpandedSchemas(newExpanded);
  };

  const toggleTable = (schemaName: string, tableName: string) => {
    const fullTableName = `${schemaName}.${tableName}`;
    const newSelected = new Set(selectedTables);
    if (newSelected.has(fullTableName)) {
      newSelected.delete(fullTableName);
    } else {
      newSelected.add(fullTableName);
    }
    setSelectedTables(newSelected);
  };

  const handleCreateDatasource = async () => {
    console.log("[CONNECT-POSTGRES] 🚀 Creating datasource...");

    if (!user?.id) {
      setCreateError("User not authenticated");
      return;
    }

    if (selectedTables.size === 0) {
      setCreateError("Please select at least one table");
      return;
    }

    setIsCreating(true);
    setCreateError(null);

    try {
      const connectionString = buildConnectionString();

      console.log("[CONNECT-POSTGRES] 📤 POST /postgres/create-datasource");
      const response = await fetch(`${BACKEND_URL}/postgres/create-datasource`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: user.id,
          connection_string: connectionString,
          connection_name: connectionName,
          allowed_tables: Array.from(selectedTables),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create datasource");
      }

      const result = await response.json();
      console.log("[CONNECT-POSTGRES] ✅ Datasource created:", result);

      // Redirect to dashboard
      router.push("/dashboard");
    } catch (error: any) {
      console.error("[CONNECT-POSTGRES] ❌ Error:", error);
      setCreateError(error.message || "Failed to create datasource");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <Button
            variant="ghost"
            onClick={() => router.push("/dashboard")}
            className="mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>

          <div className="flex items-center gap-3 mb-2">
            <Database className="w-8 h-8 text-blue-600" />
            <h1 className="text-3xl font-bold">Connect PostgreSQL Database</h1>
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Connect to your PostgreSQL database with read-only credentials
          </p>
        </motion.div>

        {/* Connection Form */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card className="p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Shield className="w-5 h-5 text-green-600" />
              Connection Details
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Connection Name *
                </label>
                <Input
                  type="text"
                  placeholder="My Production DB"
                  value={connectionName}
                  onChange={(e) => setConnectionName(e.target.value)}
                  disabled={connectionTested}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Host *</label>
                  <Input
                    type="text"
                    placeholder="localhost"
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    disabled={connectionTested}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Port *</label>
                  <Input
                    type="text"
                    placeholder="5432"
                    value={port}
                    onChange={(e) => setPort(e.target.value)}
                    disabled={connectionTested}
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Database *</label>
                <Input
                  type="text"
                  placeholder="mydb"
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  disabled={connectionTested}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Username *</label>
                <Input
                  type="text"
                  placeholder="readonly_user"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={connectionTested}
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Password *</label>
                <Input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={connectionTested}
                />
              </div>

              {testError && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2"
                >
                  <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-800 dark:text-red-200">{testError}</p>
                </motion.div>
              )}

              {connectionTested && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg flex items-start gap-2"
                >
                  <Check className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-green-800 dark:text-green-200">
                    Connection successful! Select tables below.
                  </p>
                </motion.div>
              )}

              <Button
                onClick={handleTestConnection}
                disabled={isTestingConnection || connectionTested}
                className="w-full"
              >
                {isTestingConnection ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Testing Connection...
                  </>
                ) : connectionTested ? (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    Connection Tested
                  </>
                ) : (
                  "Test Connection & Discover Tables"
                )}
              </Button>
            </div>
          </Card>
        </motion.div>

        {/* Schema Tree */}
        <AnimatePresence>
          {introspectionData && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <Card className="p-6 mb-6">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Table className="w-5 h-5 text-purple-600" />
                  Select Tables ({selectedTables.size} selected)
                </h2>

                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {introspectionData.schemas.map((schema) => (
                    <div key={schema.name} className="border rounded-lg">
                      {/* Schema Header */}
                      <button
                        onClick={() => toggleSchema(schema.name)}
                        className="w-full flex items-center justify-between p-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          {expandedSchemas.has(schema.name) ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                          <Database className="w-4 h-4 text-blue-600" />
                          <span className="font-medium">{schema.name}</span>
                          <span className="text-sm text-gray-500">
                            ({schema.tables.length} tables)
                          </span>
                        </div>
                      </button>

                      {/* Tables List */}
                      <AnimatePresence>
                        {expandedSchemas.has(schema.name) && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="p-3 pt-0 space-y-1">
                              {schema.tables.map((table) => {
                                const fullTableName = table.full_name;
                                const isSelected = selectedTables.has(fullTableName);

                                return (
                                  <button
                                    key={fullTableName}
                                    onClick={() =>
                                      toggleTable(schema.name, table.name)
                                    }
                                    className={`w-full flex items-center gap-3 p-2 rounded-lg transition-colors ${
                                      isSelected
                                        ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800"
                                        : "hover:bg-gray-100 dark:hover:bg-gray-800"
                                    }`}
                                  >
                                    <div
                                      className={`w-5 h-5 flex items-center justify-center rounded border-2 ${
                                        isSelected
                                          ? "bg-blue-600 border-blue-600"
                                          : "border-gray-300 dark:border-gray-600"
                                      }`}
                                    >
                                      {isSelected && (
                                        <Check className="w-3 h-3 text-white" />
                                      )}
                                    </div>
                                    <Table className="w-4 h-4 text-gray-600" />
                                    <div className="flex-1 text-left">
                                      <div className="font-medium">{table.name}</div>
                                      <div className="text-xs text-gray-500">
                                        {table.row_count.toLocaleString()} rows •{" "}
                                        {table.columns.length} columns
                                      </div>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))}
                </div>

                {createError && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-2"
                  >
                    <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-red-800 dark:text-red-200">
                      {createError}
                    </p>
                  </motion.div>
                )}

                <Button
                  onClick={handleCreateDatasource}
                  disabled={selectedTables.size === 0 || isCreating}
                  className="w-full mt-4"
                >
                  {isCreating ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Creating Datasource...
                    </>
                  ) : (
                    `Create Datasource (${selectedTables.size} tables selected)`
                  )}
                </Button>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
