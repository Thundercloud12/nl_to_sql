import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { userId, cloudinaryUrl, rawMetadata, schemaGraph } = body;

    if (!userId || !cloudinaryUrl || !rawMetadata || !schemaGraph) {
      return NextResponse.json(
        { error: "Missing required fields" },
        { status: 400 }
      );
    }

    // Create DataSource in database
    const dataSource = await prisma.dataSource.create({
      data: {
        userId,
        cloudinaryUrl,
        rawMetadata,
        schemaGraph,
      },
    });

    return NextResponse.json(
      {
        status: "success",
        id: dataSource.id,
        message: "DataSource created successfully",
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("Error creating DataSource:", error);
    return NextResponse.json(
      { error: "Failed to create DataSource" },
      { status: 500 }
    );
  }
}