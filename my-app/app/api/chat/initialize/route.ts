import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { auth } from "@clerk/nextjs/server";

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();

    if (!userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await req.json();
    const { dataSourceId } = body;

    if (!dataSourceId) {
      return NextResponse.json(
        { error: "dataSourceId is required" },
        { status: 400 }
      );
    }

    // Fetch DataSource from DB
    const dataSource = await prisma.dataSource.findUnique({
      where: { id: dataSourceId },
    });

    if (!dataSource) {
      return NextResponse.json(
        { error: "DataSource not found" },
        { status: 404 }
      );
    }

    // Verify user owns this DataSource
    if (dataSource.userId !== userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 403 }
      );
    }

    // Check for existing session for this user + dataSource
    const existingSession = await prisma.session.findFirst({
      where: {
        userId,
        dataSourceId,
      },
      orderBy: {
        createdAt: "desc",
      },
    });

    // Get all sessions for this dataSource (for resuming)
    const allSessions = await prisma.session.findMany({
      where: {
        userId,
        dataSourceId,
      },
      select: {
        id: true,
        createdAt: true,
      },
      orderBy: {
        createdAt: "desc",
      },
    });

    return NextResponse.json(
      {
        status: "success",
        dataSource: {
          id: dataSource.id,
          cloudinaryUrl: dataSource.cloudinaryUrl,
          rawMetadata: dataSource.rawMetadata,
          schemaGraph: dataSource.schemaGraph,
        },
        existingSession: existingSession ? {
          id: existingSession.id,
          conversationHistory: existingSession.conversationHistory,
          lastResult: existingSession.lastResult,
          lastPlan: existingSession.lastPlan,
        } : null,
        allSessions,
      },
      { status: 200 }
    );
  } catch (error) {
    console.error("Error initializing chat:", error);
    return NextResponse.json(
      { error: "Failed to initialize chat" },
      { status: 500 }
    );
  }
}