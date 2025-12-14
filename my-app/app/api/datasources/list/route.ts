import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { auth } from "@clerk/nextjs/server";

export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();

    if (!userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const dataSources = await prisma.dataSource.findMany({
      where: { userId },
      select: {
        id: true,
        cloudinaryUrl: true,
        rawMetadata: true,
        schemaGraph: true,
        createdAt: true,
      },
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json(
      { dataSources },
      { status: 200 }
    );
  } catch (error) {
    console.error("Error fetching DataSources:", error);
    return NextResponse.json(
      { error: "Failed to fetch DataSources" },
      { status: 500 }
    );
  }
}