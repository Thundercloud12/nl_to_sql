import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { userId, dataSourceId } = body;

    if (!userId || !dataSourceId) {
      return NextResponse.json(
        { error: "userId and dataSourceId are required" },
        { status: 400 }
      );
    }

    // Create new session
    const session = await prisma.session.create({
      data: {
        userId,
        dataSourceId,
        conversationHistory: [],
      },
    });

    return NextResponse.json(
      {
        id: session.id,
        userId: session.userId,
        dataSourceId: session.dataSourceId,
        message: "Session created successfully",
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("Error creating session:", error);
    return NextResponse.json(
      { error: "Failed to create session" },
      { status: 500 }
    );
  }
}