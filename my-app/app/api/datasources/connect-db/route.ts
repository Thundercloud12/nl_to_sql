import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { host, port, database, username, password, user_id, displayName } = body;

    if (!host || !port || !database || !username || !password || !user_id) {
      return NextResponse.json(
        { error: "Missing required fields" },
        { status: 400 }
      );
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    
    const response = await fetch(`${backendUrl}/connect_database`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        host,
        port,
        database,
        username,
        password,
        user_id,
        display_name: displayName || `${database}@${host}`
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Failed to connect database" },
        { status: response.status }
      );
    }

    return NextResponse.json({
      success: true,
      data_source_id: data.data_source_id,
      display_name: data.display_name,
      schema: data.schema,
      message: data.message
    });

  } catch (error: any) {
    console.error("Error connecting database:", error);
    return NextResponse.json(
      { error: error.message || "Internal server error" },
      { status: 500 }
    );
  }
}
